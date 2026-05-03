# CRFactory

Pull a YouTube channel's top shorts, dedupe against what you've already grabbed, trim the first few seconds, and stitch your own CTA on the end. Output is a folder of upload-ready 1080×1920 H.264 mp4s. Runs locally on Mac and Windows.

## What it does

1. **Pick a channel.** Drop in a YouTube handle (e.g. `@somecreator`). It pulls their shorts metadata sorted by view count.
2. **Dedupe.** Each project keeps a SQLite library keyed by YouTube video ID. Re-scraping the same channel later only downloads what's new.
3. **Stitch your CTA.** Trim the first N seconds (default 3s, configurable per project), re-encode both the trimmed clip and your CTA to identical specs (1080×1920, H.264, 30fps), then concat. No glitchy seams, no audio drift.
4. **Per-project.** Each niche gets its own folder, channels list, CTA, library, and output directory.
5. **Local-only.** No cloud, no upload scheduler. Output mp4s land in a folder you can hand to whatever upload tool you use.

## Install

Requires Python 3.10+. ffmpeg ships with the package via `imageio-ffmpeg`.

```bash
git clone https://github.com/newomp4/CRFactory.git
cd CRFactory
python -m pip install -e .
```

## Run

```bash
crfactory
```

Opens `http://127.0.0.1:8765` in your browser.

### Storage on an external drive / SD card

Set the storage root once (also editable in the UI header):

```bash
# Mac
crfactory --storage-root /Volumes/MySD/crfactory-data

# Windows (PowerShell)
crfactory --storage-root E:\crfactory-data
```

Project folders, raw downloads, and output mp4s all live under that path.

## Per-project layout

```
<storage-root>/
  fitness-niche/
    project.json          # channels, trim seconds, output specs
    cta.mp4               # your CTA, swappable any time via UI
    library.db            # dedupe: video_id, status, paths
    raw/<id>.mp4          # original downloads
    output/<id>.mp4       # finished CTA-stitched clips
```

## Hardware encoding

Auto-detected at runtime:

| Platform                | Encoder used        |
|-------------------------|---------------------|
| Apple Silicon Mac       | `h264_videotoolbox` |
| Windows + Nvidia GPU    | `h264_nvenc`        |
| Windows + AMD GPU       | `h264_amf`          |
| Windows + Intel iGPU    | `h264_qsv`          |
| Fallback (any CPU)      | `libx264`           |

On Apple Silicon a 60s short encodes in ~3–5s without spinning the fans.

## Workflow

1. Create a project, add channels, upload a CTA video.
2. Click **Scrape channels** — pulls top N shorts metadata, skips anything already in the library.
3. Click **Download + stitch new** — downloads the new ones, trims, stitches your CTA, drops finished mp4s in `output/`.
4. Re-scrape the same channels weeks later — old videos are skipped automatically.

## License

MIT.
