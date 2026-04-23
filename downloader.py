"""Fetch media info and download files from social URLs.

Uses gallery-dl (via subprocess) for image-heavy sites (IG, Pinterest, Twitter)
and yt-dlp (Python API) for video-heavy sites. Both read cookies directly
from the user's Chrome profile via each tool's native `cookies-from-browser`
feature — this is more reliable than manual cookie jar handling.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

import config

_VENV_BIN = Path(sys.executable).parent
GDL_BIN = str(_VENV_BIN / "gallery-dl")

VIDEO_FIRST_HOSTS = ("youtube.com", "youtu.be", "tiktok.com", "vimeo.com", "twitch.tv")
# Hosts where gallery-dl may hand us an adaptive-streaming fragment URL — yt-dlp does proper
# stream assembly, so we delegate video items on these hosts to yt-dlp using the original page URL.
DELEGATE_VIDEO_HOSTS = ("instagram.com", "twitter.com", "x.com", "facebook.com", "fb.com")
CHROME_COOKIES = ("chrome",)
# Prefer QuickTime-friendly codecs (H.264 / AVC + AAC) when IG serves them.
# Fall back to any mergeable video+audio combo, then single-file fallbacks.
YT_FORMAT = (
    "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/"
    "b[vcodec^=avc1][acodec^=mp4a]/"
    "bv*+ba/"
    "b[vcodec!=none][acodec!=none]/"
    "b[vcodec!=none]/"
    "b"
)


def _find_ffmpeg() -> Optional[str]:
    """Locate ffmpeg — PATH first, then common macOS Homebrew/system locations."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    for candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if Path(candidate).exists():
            return candidate
    return None


FFMPEG_PATH = _find_ffmpeg()
FFPROBE_PATH = (str(Path(FFMPEG_PATH).parent / "ffprobe")
                if FFMPEG_PATH and Path(FFMPEG_PATH).parent.joinpath("ffprobe").exists()
                else shutil.which("ffprobe"))

# Make sure ffmpeg's bin dir is on PATH for any subprocess (gallery-dl etc.) we spawn.
if FFMPEG_PATH:
    ff_bin_dir = str(Path(FFMPEG_PATH).parent)
    if ff_bin_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + ff_bin_dir

# Video codecs QuickTime Player decodes natively on current macOS
QT_SAFE_VCODECS = {"h264", "avc", "avc1", "hevc", "h265"}

IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "heic", "bmp", "avif"}
VIDEO_EXTS = {"mp4", "mov", "webm", "mkv", "m4v", "avi"}

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"


# ------------------ public entry points ------------------

def fetch_preview(url: str) -> dict:
    url = _normalize_url(url.strip())
    if not url:
        return {"items": [], "error": "空白的 URL"}

    host = urllib.parse.urlparse(url).netloc.lower()
    video_first = any(h in host for h in VIDEO_FIRST_HOSTS)

    order = ("yt", "gdl") if video_first else ("gdl", "yt")
    errors = []
    for kind in order:
        res = _preview_ytdlp(url) if kind == "yt" else _preview_gdl(url)
        if res.get("items"):
            return res
        if res.get("error"):
            errors.append(f"[{kind}] {res['error']}")

    return {"items": [], "error": " / ".join(errors) or "無法解析這個 URL"}


def _normalize_url(url: str) -> str:
    """Strip known tracking params from social URLs — they sometimes confuse extractors."""
    try:
        u = urllib.parse.urlparse(url)
        host = u.netloc.lower()
        if "instagram.com" in host or "pin.it" in host or "pinterest." in host:
            return f"{u.scheme}://{u.netloc}{u.path}"
    except Exception:
        pass
    return url


def download(item: dict, category: str, filename: str) -> dict:
    dest_dir = config.save_path()
    if category:
        for seg in category.split("/"):
            seg = seg.strip()
            if seg:
                dest_dir = dest_dir / _safe_name(seg, "uncategorized")
    dest_dir.mkdir(parents=True, exist_ok=True)

    ext = (item.get("ext") or "bin").lower()
    filename = _safe_name(filename or item.get("suggested_filename") or "file", "file")
    if not filename.lower().endswith(f".{ext}"):
        filename = f"{filename}.{ext}"
    target = _unique_path(dest_dir / filename)

    url = item.get("url") or ""

    # yt-dlp path — either from a video-first site, or gallery-dl told us to delegate
    if item.get("_source") == "yt":
        return _download_ytdlp(item.get("_yt_url") or url, target)
    if url.startswith("ytdl:"):
        webpage_url = url[len("ytdl:"):]
        # gallery-dl's ytdl: URLs sometimes include a synthetic /N.ext suffix
        webpage_url = re.sub(r"/\d+\.[a-z0-9]+$", "/", webpage_url)
        return _download_ytdlp(webpage_url, target)

    return _download_direct(url, target, referer=item.get("_referer"))


# ------------------ gallery-dl preview (subprocess) ------------------
# Message types in gallery-dl's JSON output:
#   2 = Directory (metadata dict — no URL, but useful for post title)
#   3 = Url (the actual downloadable media URL + metadata)
#   6 = Queue (sub-URL to recursively process — e.g. `pin.it` short links)

GDL_DIRECTORY = 2
GDL_URL = 3
GDL_QUEUE = 6

def _preview_gdl(url: str, _depth: int = 0, _original: Optional[str] = None) -> dict:
    if _depth > 3:
        return {"items": [], "error": "gallery-dl 遞迴深度過深"}
    if not Path(GDL_BIN).exists():
        return {"items": [], "error": f"找不到 gallery-dl（{GDL_BIN}）"}

    original_url = _original or url
    args = [GDL_BIN, "-j", "--cookies-from-browser", "chrome", url]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return {"items": [], "error": "gallery-dl 超時"}

    stdout = proc.stdout.strip()
    stderr_err = _meaningful_error(proc.stderr)

    if not stdout:
        return {"items": [], "error": stderr_err or f"gallery-dl exit {proc.returncode}"}

    try:
        msgs = json.loads(stdout)
    except json.JSONDecodeError as e:
        return {"items": [], "error": f"gallery-dl JSON 解析失敗：{e}"}

    items: list[dict] = []
    source_title: Optional[str] = None
    origin = _origin(original_url)
    orig_host = urllib.parse.urlparse(original_url).netloc.lower()
    delegate_video = any(h in orig_host for h in DELEGATE_VIDEO_HOSTS)

    for msg in msgs:
        if not isinstance(msg, list) or len(msg) < 2:
            continue
        kind = msg[0]

        if kind == GDL_URL:
            media_url = msg[1]
            if not isinstance(media_url, str):
                continue
            meta = msg[2] if len(msg) >= 3 and isinstance(msg[2], dict) else {}
            ext = (meta.get("extension") or _ext_from_url(media_url) or "bin").lower()
            suggested = meta.get("filename") or meta.get("title") or f"item_{len(items) + 1}"
            kind_str = "video" if ext in VIDEO_EXTS else "image"
            item = {
                "url": media_url,
                "thumbnail": meta.get("preview_url") or (media_url if ext in IMAGE_EXTS else ""),
                "ext": ext,
                "title": meta.get("description") or meta.get("title") or "",
                "kind": kind_str,
                "suggested_filename": _safe_name(suggested),
                "_source": "gdl",
                "_referer": origin,
            }
            # Route video items on streaming-prone hosts through yt-dlp (they deliver proper
            # merged output; gallery-dl sometimes hands back audio-only DASH fragments).
            if kind_str == "video" and (delegate_video or media_url.startswith("ytdl:")):
                item["_source"] = "yt"
                item["_yt_url"] = original_url
                item["ext"] = "mp4"
            items.append(item)
            if not source_title:
                source_title = meta.get("post_title") or (meta.get("description") or "")[:80]

        elif kind == GDL_DIRECTORY:
            meta = msg[1] if isinstance(msg[1], dict) else {}
            if not source_title:
                source_title = (meta.get("post_title") or meta.get("title")
                                or (meta.get("description") or "")[:80] or None)

        elif kind == GDL_QUEUE:
            sub_url = msg[1]
            if isinstance(sub_url, str):
                sub = _preview_gdl(sub_url, _depth=_depth + 1, _original=original_url)
                items.extend(sub.get("items") or [])
                if not source_title and sub.get("source_title"):
                    source_title = sub["source_title"]

    if not items:
        return {"items": [], "error": stderr_err or "gallery-dl 沒找到可下載項目"}

    return {"items": items, "source_title": source_title or ""}


# ------------------ yt-dlp preview (Python API) ------------------

def _preview_ytdlp(url: str) -> dict:
    try:
        from yt_dlp import YoutubeDL
    except Exception as e:
        return {"items": [], "error": f"yt-dlp import: {e}"}

    opts = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
        "cookiesfrombrowser": CHROME_COOKIES,
        "format": YT_FORMAT,
    }

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        msg = str(e)
        # Strip ANSI color codes from yt-dlp errors — they look ugly in our UI
        msg = re.sub(r"\x1b\[[0-9;]*m", "", msg)
        return {"items": [], "error": f"yt-dlp: {msg}"}

    if not info:
        return {"items": [], "error": "yt-dlp 無回傳"}

    entries = info.get("entries") if info.get("_type") in ("playlist", "multi_video") else None
    raw = list(entries) if entries else [info]
    items = [i for i in (_yt_info_to_item(e) for e in raw) if i]
    return {"items": items, "source_title": info.get("title", "")}


def _yt_info_to_item(info: dict) -> Optional[dict]:
    if not info:
        return None
    ext = (info.get("ext") or "mp4").lower()
    title = info.get("title") or info.get("id") or "video"
    return {
        "url": info.get("webpage_url") or info.get("url"),
        "thumbnail": info.get("thumbnail") or "",
        "ext": ext,
        "title": title,
        "kind": "video",
        "suggested_filename": _safe_name(title),
        "_source": "yt",
        "_yt_url": info.get("webpage_url") or info.get("url"),
    }


# ------------------ downloads ------------------

def _download_direct(url: str, target: Path, referer: Optional[str] = None) -> dict:
    try:
        headers = {"User-Agent": _UA}
        if referer:
            headers["Referer"] = referer
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=180) as resp, open(target, "wb") as out:
            while True:
                chunk = resp.read(1 << 15)
                if not chunk:
                    break
                out.write(chunk)
        return {"ok": True, "path": str(target)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _download_ytdlp(webpage_url: str, target: Path) -> dict:
    try:
        from yt_dlp import YoutubeDL
    except Exception as e:
        return {"ok": False, "error": f"yt-dlp import: {e}"}

    opts = {
        "outtmpl": str(target.with_suffix("")) + ".%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "cookiesfrombrowser": CHROME_COOKIES,
        "format": YT_FORMAT,
        "merge_output_format": "mp4",
    }
    if FFMPEG_PATH:
        opts["ffmpeg_location"] = FFMPEG_PATH

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(webpage_url, download=True)
            real_path = ydl.prepare_filename(info)
            p = Path(real_path)
            if not p.exists():
                mp4 = p.with_suffix(".mp4")
                if mp4.exists():
                    real_path = str(mp4)
    except Exception as e:
        msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e))
        return {"ok": False, "error": msg}

    # If the downloaded file uses a codec QuickTime can't decode natively (e.g. VP9),
    # re-encode to H.264 + AAC in-place. IG serves VP9-only for many Reels/Stories,
    # so this is the step that makes those files actually playable.
    real_path = _ensure_quicktime_compat(real_path)
    return {"ok": True, "path": real_path}


def _probe_video_codec(path: str) -> Optional[str]:
    if not FFPROBE_PATH:
        return None
    try:
        r = subprocess.run(
            [FFPROBE_PATH, "-v", "error",
             "-select_streams", "v:0",
             "-show_entries", "stream=codec_name",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=30,
        )
        return (r.stdout or "").strip().lower() or None
    except Exception:
        return None


def _ensure_quicktime_compat(path: str) -> str:
    """Re-encode to H.264/AAC MP4 if the video codec isn't QuickTime-friendly."""
    if not FFMPEG_PATH:
        return path
    vcodec = _probe_video_codec(path)
    if vcodec is None or vcodec in QT_SAFE_VCODECS:
        return path

    p = Path(path)
    tmp = p.with_name(p.stem + ".__converting__.mp4")
    try:
        subprocess.run(
            [FFMPEG_PATH, "-y",
             "-i", str(p),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart",
             str(tmp)],
            capture_output=True, timeout=600, check=True,
        )
    except Exception:
        if tmp.exists():
            try: tmp.unlink()
            except Exception: pass
        return path  # conversion failed — keep original file rather than lose it

    # Atomic swap: replace original with converted file
    try:
        p.unlink()
    except Exception:
        pass
    final = p.with_suffix(".mp4")
    tmp.rename(final)
    return str(final)


# ------------------ helpers ------------------

def _ext_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    if ext and len(ext) <= 5 and ext.isalnum():
        return ext
    return ""


def _safe_name(s: str, fallback: str = "item") -> str:
    s = re.sub(r"[/\\:*?\"<>|]", "_", s or "")
    s = s.strip().strip(".")
    return s or fallback


def _unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    stem, suffix = p.stem, p.suffix
    i = 2
    while True:
        cand = p.with_name(f"{stem} ({i}){suffix}")
        if not cand.exists():
            return cand
        i += 1


def _origin(url: str) -> str:
    u = urllib.parse.urlparse(url)
    return f"{u.scheme}://{u.netloc}/"


def _meaningful_error(text: str) -> str:
    """Extract the last error-level line from gallery-dl stderr, ignoring info chatter."""
    if not text:
        return ""
    last = ""
    for line in text.splitlines():
        clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        if not clean:
            continue
        low = clean.lower()
        if "[info]" in low or "[debug]" in low:
            continue
        if "error" in low or "failed" in low or "exception" in low:
            last = clean
        elif not last:
            last = clean
    return last


# Kept for api.proxy_image backwards compat (uses browser_cookie3 for thumbnail fetching)
def _cookie_jar_for(url: str):
    try:
        import browser_cookie3
        host = urllib.parse.urlparse(url).netloc
        domain = ".".join(host.split(".")[-2:]) if "." in host else host
        return browser_cookie3.chrome(domain_name=domain)
    except Exception:
        return None
