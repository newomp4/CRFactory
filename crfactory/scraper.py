from __future__ import annotations

from yt_dlp import YoutubeDL


def normalize_handle(handle: str) -> str:
    h = handle.strip()
    if h.startswith("http"):
        return h.rstrip("/")
    if h.startswith("@"):
        return f"https://www.youtube.com/{h}"
    return f"https://www.youtube.com/@{h}"


def list_channel_shorts(handle_or_url: str, limit: int = 100) -> list[dict]:
    base = normalize_handle(handle_or_url)
    url = f"{base}/shorts"

    opts = {
        "extract_flat": True,
        "quiet": True,
        "skip_download": True,
        "playlistend": max(limit * 3, limit + 10),
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    entries = info.get("entries") or []
    items: list[dict] = []
    for d in entries:
        if not d or not d.get("id"):
            continue
        thumb = d.get("thumbnail")
        if not thumb and d.get("thumbnails"):
            thumb = d["thumbnails"][-1].get("url")
        items.append({
            "id": d.get("id"),
            "title": d.get("title"),
            "channel": d.get("channel") or d.get("uploader") or info.get("channel") or info.get("uploader"),
            "view_count": d.get("view_count") or 0,
            "duration": d.get("duration"),
            "thumbnail": thumb,
            "upload_date": d.get("upload_date"),
        })
    items.sort(key=lambda x: x["view_count"] or 0, reverse=True)
    return items[:limit]
