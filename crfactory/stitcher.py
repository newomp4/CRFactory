from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Callable

from .encoder import detect_video_encoder
from .ffbin import ffmpeg_bin


def stitch_with_cta(
    input_path: Path,
    cta_path: Path,
    output_path: Path,
    width: int = 1080,
    height: int = 1920,
    framerate: int = 30,
    video_bitrate: str = "4M",
    audio_bitrate: str = "128k",
    clip_seconds: float | None = None,
    proc_callback: Callable[[subprocess.Popen], None] | None = None,
) -> None:
    encoder = detect_video_encoder()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    scale_pad = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1,fps={framerate},format=yuv420p"
    )

    if clip_seconds and clip_seconds > 0:
        v0 = f"[0:v]trim=duration={clip_seconds},setpts=PTS-STARTPTS,{scale_pad}[v0]"
        a0 = (
            f"[0:a]atrim=duration={clip_seconds},asetpts=PTS-STARTPTS,"
            f"aresample=async=1:first_pts=0,"
            f"aformat=sample_rates=44100:channel_layouts=stereo[a0]"
        )
    else:
        v0 = f"[0:v]{scale_pad}[v0]"
        a0 = (
            f"[0:a]aresample=async=1:first_pts=0,"
            f"aformat=sample_rates=44100:channel_layouts=stereo[a0]"
        )

    filter_complex = (
        f"{v0};"
        f"{a0};"
        f"[1:v]{scale_pad}[v1];"
        f"[1:a]aresample=async=1:first_pts=0,aformat=sample_rates=44100:channel_layouts=stereo[a1];"
        f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
    )

    cmd = [
        ffmpeg_bin(), "-y",
        "-i", str(input_path),
        "-i", str(cta_path),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-c:v", encoder,
        "-b:v", video_bitrate,
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-movflags", "+faststart",
        str(output_path),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc_callback:
        proc_callback(proc)
    _, stderr = proc.communicate()
    if proc.returncode != 0:
        if proc.returncode < 0:
            raise CancelledError(f"ffmpeg terminated (signal {-proc.returncode})")
        raise RuntimeError(f"ffmpeg failed: {stderr[-2000:]}")


class CancelledError(RuntimeError):
    pass
