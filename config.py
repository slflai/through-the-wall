import json
from pathlib import Path

APP_DIR = Path.home() / ".through-the-wall"
CONFIG_FILE = APP_DIR / "config.json"

DEFAULTS = {
    "save_path": str(Path.home() / "Desktop" / "through-the-wall"),
    "cookie_browser": "chrome",
    "recent_categories": [],
}


def load():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            return {**DEFAULTS, **data}
        except Exception:
            pass
    return dict(DEFAULTS)


def save(data):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def save_path() -> Path:
    p = Path(load()["save_path"]).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p
