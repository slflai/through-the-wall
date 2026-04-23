"""JS-facing API exposed via pywebview. Every public method is callable from the UI."""
from __future__ import annotations

import base64
import mimetypes
import shutil
import urllib.parse
from pathlib import Path
from typing import Optional

import config
import downloader


class Api:
    # ========== URL preview ==========

    def fetch_preview(self, url: str) -> dict:
        return downloader.fetch_preview(url)

    # ========== Download ==========

    def download_many(self, items: list, category: str) -> dict:
        results = []
        for it in items:
            filename = it.get("filename") or it.get("suggested_filename") or "file"
            res = downloader.download(it, category or "", filename)
            results.append({**res, "filename": filename})
        ok_count = sum(1 for r in results if r.get("ok"))
        return {"results": results, "ok": ok_count, "failed": len(results) - ok_count}

    # ========== Categories (folder tree) ==========

    def list_categories(self) -> dict:
        root = config.save_path()
        tree = _scan_tree(root, root)
        cfg = config.load()
        raw_recent = cfg.get("recent_categories", [])
        # Auto-prune recent categories whose folders no longer exist
        live_recent = [c for c in raw_recent if _resolve_under(root, c) and _resolve_under(root, c).is_dir()]
        if live_recent != raw_recent:
            cfg["recent_categories"] = live_recent
            config.save(cfg)
        return {"root": str(root), "tree": tree, "recent": live_recent}

    def remember_category(self, category: str) -> dict:
        if not category:
            return {"ok": True}
        cfg = config.load()
        recent = [c for c in cfg.get("recent_categories", []) if c != category]
        recent.insert(0, category)
        cfg["recent_categories"] = recent[:10]
        config.save(cfg)
        return {"ok": True}

    def forget_category(self, category: str) -> dict:
        cfg = config.load()
        cfg["recent_categories"] = [c for c in cfg.get("recent_categories", []) if c != category]
        config.save(cfg)
        return {"ok": True}

    def create_category(self, path: str) -> dict:
        if not path:
            return {"ok": False, "error": "empty"}
        root = config.save_path()
        target = root
        for seg in path.split("/"):
            seg = seg.strip()
            if seg:
                target = target / seg
        target.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "path": str(target.relative_to(root))}

    def rename_folder(self, rel_path: str, new_name: str) -> dict:
        try:
            if not rel_path or "/" in new_name or not new_name.strip():
                return {"ok": False, "error": "invalid name"}
            root = config.save_path()
            src = _resolve_under(root, rel_path)
            if not src or not src.is_dir():
                return {"ok": False, "error": "folder not found"}
            dst = src.parent / new_name.strip()
            if dst.exists():
                return {"ok": False, "error": "已有同名資料夾"}
            src.rename(dst)
            return {"ok": True, "new_path": str(dst.relative_to(root))}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def delete_folder(self, rel_path: str, recursive: bool = False) -> dict:
        try:
            if not rel_path:
                return {"ok": False, "error": "不能刪除根目錄"}
            root = config.save_path()
            src = _resolve_under(root, rel_path)
            if not src or not src.is_dir():
                return {"ok": False, "error": "folder not found"}
            if recursive:
                shutil.rmtree(src)
            else:
                src.rmdir()
            return {"ok": True}
        except OSError as e:
            if "not empty" in str(e).lower() or e.errno == 66:
                return {"ok": False, "error": "資料夾不為空，請用遞迴刪除", "not_empty": True}
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def move_folder(self, rel_path: str, target_parent: str) -> dict:
        try:
            if not rel_path:
                return {"ok": False, "error": "不能移動根目錄"}
            root = config.save_path()
            src = _resolve_under(root, rel_path)
            if not src or not src.is_dir():
                return {"ok": False, "error": "folder not found"}
            parent = root
            if target_parent:
                parent = _resolve_under(root, target_parent) or root
            if not parent.is_dir():
                return {"ok": False, "error": "target invalid"}
            if _is_ancestor(src, parent) or src == parent:
                return {"ok": False, "error": "不能移到自己底下"}
            dst = parent / src.name
            if dst.exists():
                return {"ok": False, "error": "目標已有同名資料夾"}
            shutil.move(str(src), str(dst))
            return {"ok": True, "new_path": str(dst.relative_to(root))}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ========== Library ==========

    def list_library(self, category: str = "") -> dict:
        root = config.save_path()
        folder = root
        if category:
            folder = _resolve_under(root, category) or root
        if not folder.exists():
            return {"items": [], "subfolders": []}

        items, subfolders = [], []
        for p in sorted(folder.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name.startswith("."):
                continue
            if p.is_dir():
                subfolders.append({"name": p.name, "path": str(p.relative_to(root))})
            else:
                items.append({
                    "name": p.name,
                    "path": str(p.relative_to(root)),
                    "abs_path": str(p),
                    "size": p.stat().st_size,
                    "mtime": p.stat().st_mtime,
                })
        return {"items": items, "subfolders": subfolders, "current": category}

    def read_file_as_data_url(self, abs_path: str) -> dict:
        try:
            p = Path(abs_path)
            if not p.is_file():
                return {"ok": False, "error": "not a file"}
            if p.stat().st_size > 20 * 1024 * 1024:
                return {"ok": False, "error": "too large"}
            mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
            b64 = base64.b64encode(p.read_bytes()).decode("ascii")
            return {"ok": True, "data_url": f"data:{mime};base64,{b64}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def reveal_in_finder(self, abs_path: str) -> dict:
        import subprocess
        try:
            subprocess.run(["open", "-R", abs_path], check=False)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def rename_file(self, abs_path: str, new_name: str) -> dict:
        try:
            p = Path(abs_path)
            new_name = (new_name or "").strip()
            if not new_name or "/" in new_name:
                return {"ok": False, "error": "invalid name"}
            new_path = p.with_name(new_name)
            if new_path.exists():
                return {"ok": False, "error": "已有同名檔案"}
            p.rename(new_path)
            return {"ok": True, "abs_path": str(new_path)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def move_file(self, abs_path: str, target_category: str) -> dict:
        try:
            root = config.save_path()
            src = Path(abs_path)
            if not src.is_file():
                return {"ok": False, "error": "not a file"}
            target_dir = root
            if target_category:
                target_dir = _resolve_under(root, target_category) or root
            target_dir.mkdir(parents=True, exist_ok=True)
            dst = target_dir / src.name
            if dst.exists():
                dst = _unique_path(dst)
            shutil.move(str(src), str(dst))
            return {"ok": True, "abs_path": str(dst)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def delete_file(self, abs_path: str) -> dict:
        try:
            Path(abs_path).unlink()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ========== Config ==========

    def get_config(self) -> dict:
        return config.load()

    def set_save_path(self, path: str) -> dict:
        try:
            cfg = config.load()
            cfg["save_path"] = str(Path(path).expanduser())
            config.save(cfg)
            Path(cfg["save_path"]).mkdir(parents=True, exist_ok=True)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ========== Thumbnail proxy (handles hotlink-protected images) ==========

    def proxy_image(self, url: str) -> dict:
        try:
            import urllib.request
            cj = downloader._cookie_jar_for(url)
            opener = urllib.request.build_opener()
            if cj is not None:
                opener.add_handler(urllib.request.HTTPCookieProcessor(cj))
            opener.addheaders = [
                ("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"),
                ("Referer", _origin(url)),
            ]
            with opener.open(url, timeout=20) as resp:
                data = resp.read()
                mime = resp.headers.get_content_type()
            b64 = base64.b64encode(data).decode("ascii")
            return {"ok": True, "data_url": f"data:{mime};base64,{b64}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ========== helpers ==========

def _scan_tree(root: Path, current: Path, depth: int = 0) -> list:
    if depth > 5:
        return []
    out = []
    try:
        for p in sorted(current.iterdir(), key=lambda x: x.name.lower()):
            if p.is_dir() and not p.name.startswith("."):
                rel = str(p.relative_to(root))
                out.append({
                    "name": p.name,
                    "path": rel,
                    "children": _scan_tree(root, p, depth + 1),
                })
    except Exception:
        pass
    return out


def _resolve_under(root: Path, rel: str) -> Optional[Path]:
    """Safely resolve a relative path within root. Returns None if escapes root."""
    try:
        candidate = (root / rel).resolve()
        root_resolved = root.resolve()
        if root_resolved == candidate or root_resolved in candidate.parents:
            return candidate
    except Exception:
        pass
    return None


def _is_ancestor(ancestor: Path, descendant: Path) -> bool:
    try:
        descendant.resolve().relative_to(ancestor.resolve())
        return True
    except Exception:
        return False


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
