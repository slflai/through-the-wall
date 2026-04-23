"""Through the Wall — launch entry point. Creates a native pywebview window."""
from pathlib import Path

import webview

from api import Api

APP_ROOT = Path(__file__).resolve().parent
UI_INDEX = APP_ROOT / "ui" / "index.html"


def main():
    api = Api()
    window = webview.create_window(
        title="Through the Wall",
        url=str(UI_INDEX),
        js_api=api,
        width=1100,
        height=760,
        min_size=(900, 600),
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
