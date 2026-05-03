from __future__ import annotations
import platform
import subprocess
from functools import cache

from .ffbin import ffmpeg_bin


@cache
def detect_video_encoder() -> str:
    try:
        out = subprocess.run(
            [ffmpeg_bin(), "-hide_banner", "-encoders"],
            capture_output=True, text=True, check=True,
        ).stdout
    except Exception:
        return "libx264"

    sysname = platform.system()
    if sysname == "Darwin":
        candidates = ["h264_videotoolbox"]
    elif sysname == "Windows":
        candidates = ["h264_nvenc", "h264_amf", "h264_qsv"]
    else:
        candidates = ["h264_nvenc", "h264_vaapi", "h264_qsv"]

    for c in candidates:
        if c in out:
            return c
    return "libx264"
