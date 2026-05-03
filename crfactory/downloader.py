from __future__ import annotations
from pathlib import Path

from yt_dlp import YoutubeDL


def download_video(video_id: str, dest_dir: Path, cookies_browser: str | None = None) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(dest_dir / "%(id)s.%(ext)s")
    opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": out_template,
        "quiet": True,
        "noprogress": True,
        "overwrites": True,
        "restrictfilenames": True,
        "remote_components": ["ejs:github"],
    }
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
    url = f"https://www.youtube.com/watch?v={video_id}"
    with YoutubeDL(opts) as ydl:
        ydl.extract_info(url, download=True)

    final = dest_dir / f"{video_id}.mp4"
    if final.exists():
        return final
    for ext in ("mkv", "webm", "mov"):
        cand = dest_dir / f"{video_id}.{ext}"
        if cand.exists():
            return cand
    matches = list(dest_dir.glob(f"{video_id}.*"))
    if matches:
        return matches[0]
    raise FileNotFoundError(f"download for {video_id} not found in {dest_dir}")
