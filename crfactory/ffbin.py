from __future__ import annotations
import shutil
from functools import cache


@cache
def ffmpeg_bin() -> str:
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"
