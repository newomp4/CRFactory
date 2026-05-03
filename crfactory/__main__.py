from __future__ import annotations
import argparse
import threading
import time
import webbrowser

import uvicorn

from .config import AppConfig


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="crfactory",
        description="Scrape YouTube shorts, stitch your CTA, batch-output ready-to-upload clips.",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--storage-root",
        help="Override storage root path (also persists to ~/.crfactory/config.json)",
    )
    args = parser.parse_args()

    if args.storage_root:
        AppConfig(storage_root=args.storage_root).save()

    if not args.no_browser:
        url = f"http://{args.host}:{args.port}/"
        def _open() -> None:
            time.sleep(1.0)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run("crfactory.server:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
