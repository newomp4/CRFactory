from __future__ import annotations
import subprocess
from pathlib import Path

from .encoder import detect_video_encoder
from .ffbin import ffmpeg_bin


def trim_and_stitch(
    input_path: Path,
    cta_path: Path,
    output_path: Path,
    trim_seconds: float = 3.0,
    width: int = 1080,
    height: int = 1920,
    framerate: int = 30,
    video_bitrate: str = "4M",
    audio_bitrate: str = "128k",
) -> None:
    encoder = detect_video_encoder()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    scale_pad = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1,fps={framerate},format=yuv420p"
    )

    filter_complex = (
        f"[0:v]trim=start={trim_seconds},setpts=PTS-STARTPTS,{scale_pad}[v0];"
        f"[0:a]atrim=start={trim_seconds},asetpts=PTS-STARTPTS,aresample=async=1:first_pts=0,aformat=sample_rates=44100:channel_layouts=stereo[a0];"
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
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-2000:]}")
