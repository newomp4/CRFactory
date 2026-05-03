from __future__ import annotations
import re

from yt_dlp import YoutubeDL


def normalize_handle(handle: str) -> str:
    h = handle.strip()
    if h.startswith("http"):
        return h.rstrip("/")
    if h.startswith("@"):
        return f"https://www.youtube.com/{h}"
    return f"https://www.youtube.com/@{h}"


_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def parse_video_id(s: str) -> str | None:
    s = s.strip()
    if _VIDEO_ID_RE.match(s):
        return s
    m = re.search(r"(?:v=|/shorts/|youtu\.be/|/embed/)([A-Za-z0-9_-]{11})", s)
    return m.group(1) if m else None


def _entry_to_item(d: dict, channel_fallback: str | None = None) -> dict:
    thumb = d.get("thumbnail")
    if not thumb and d.get("thumbnails"):
        thumb = d["thumbnails"][-1].get("url")
    return {
        "id": d.get("id"),
        "title": d.get("title"),
        "channel": d.get("channel") or d.get("uploader") or channel_fallback,
        "view_count": d.get("view_count") or 0,
        "duration": d.get("duration"),
        "thumbnail": thumb,
        "upload_date": d.get("upload_date"),
    }


def list_channel_shorts(handle_or_url: str, limit: int = 100, cookies_browser: str | None = None) -> list[dict]:
    base = normalize_handle(handle_or_url)
    url = f"{base}/shorts"

    opts = {
        "extract_flat": True,
        "quiet": True,
        "skip_download": True,
        "playlistend": max(limit * 3, limit + 10),
    }
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    fallback = info.get("channel") or info.get("uploader")
    items: list[dict] = []
    for d in info.get("entries") or []:
        if not d or not d.get("id"):
            continue
        items.append(_entry_to_item(d, channel_fallback=fallback))
    items.sort(key=lambda x: x["view_count"] or 0, reverse=True)
    return items[:limit]


def fetch_video_metadata(url_or_id: str, cookies_browser: str | None = None) -> dict:
    vid = parse_video_id(url_or_id)
    url = url_or_id.strip() if url_or_id.strip().startswith("http") else f"https://www.youtube.com/watch?v={vid or url_or_id.strip()}"
    opts = {"quiet": True, "skip_download": True}
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
    with YoutubeDL(opts) as ydl:
        d = ydl.extract_info(url, download=False)
    return _entry_to_item(d)
