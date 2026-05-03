from __future__ import annotations
import platform
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import AppConfig
from .downloader import download_video
from .encoder import detect_video_encoder
from .library import Library
from .project import Project, list_projects
from .scraper import list_channel_shorts
from .stitcher import trim_and_stitch

app = FastAPI(title="CRFactory")

STATIC_DIR = Path(__file__).parent / "static"
JOBS: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root() -> Path:
    cfg = AppConfig.load()
    p = cfg.storage_path()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _log(job_id: str, msg: str) -> None:
    JOBS[job_id]["log"].append(msg)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------- config ----------

@app.get("/api/config")
def api_get_config() -> dict:
    cfg = AppConfig.load()
    return {
        "storage_root": cfg.storage_root,
        "video_encoder": detect_video_encoder(),
        "platform": platform.system(),
    }


class ConfigUpdate(BaseModel):
    storage_root: str


@app.post("/api/config")
def api_set_config(body: ConfigUpdate) -> dict:
    cfg = AppConfig(storage_root=body.storage_root)
    cfg.save()
    return {"storage_root": cfg.storage_root}


# ---------- projects ----------

@app.get("/api/projects")
def api_list_projects() -> list[dict]:
    return [p.__dict__ for p in list_projects(_root())]


class ProjectCreate(BaseModel):
    name: str
    channels: list[str] = []
    trim_seconds: float = 3.0


@app.post("/api/projects")
def api_create_project(body: ProjectCreate) -> dict:
    root = _root()
    slug = Project.slugify(body.name)
    if (root / slug / "project.json").exists():
        raise HTTPException(400, f"project '{slug}' already exists")
    p = Project(
        name=body.name,
        slug=slug,
        channels=body.channels,
        trim_seconds=body.trim_seconds,
    )
    p.save(root)
    return p.__dict__


@app.get("/api/projects/{slug}")
def api_get_project(slug: str) -> dict:
    root = _root()
    try:
        p = Project.load(root, slug)
    except FileNotFoundError:
        raise HTTPException(404, "project not found")
    lib = Library(p.db_path(root))
    return {
        "project": p.__dict__,
        "stats": lib.stats(),
        "has_cta": p.cta_path(root).exists(),
        "output_dir": str(p.output_dir(root)),
    }


class ProjectUpdate(BaseModel):
    channels: list[str] | None = None
    trim_seconds: float | None = None
    output_width: int | None = None
    output_height: int | None = None
    framerate: int | None = None
    video_bitrate: str | None = None
    audio_bitrate: str | None = None


@app.put("/api/projects/{slug}")
def api_update_project(slug: str, body: ProjectUpdate) -> dict:
    root = _root()
    p = Project.load(root, slug)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    p.save(root)
    return p.__dict__


@app.delete("/api/projects/{slug}")
def api_delete_project(slug: str, purge: bool = False) -> dict:
    root = _root()
    pdir = root / slug
    if not pdir.exists():
        raise HTTPException(404, "project not found")
    if purge:
        shutil.rmtree(pdir)
    else:
        (pdir / "project.json").unlink(missing_ok=True)
    return {"ok": True, "purged": purge}


@app.post("/api/projects/{slug}/cta")
async def api_upload_cta(slug: str, file: UploadFile) -> dict:
    root = _root()
    p = Project.load(root, slug)
    p.ensure_dirs(root)
    target = p.cta_path(root)
    with target.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"ok": True, "path": str(target)}


@app.get("/api/projects/{slug}/library")
def api_library(slug: str, status: str | None = None, limit: int = 1000) -> list[dict]:
    root = _root()
    p = Project.load(root, slug)
    lib = Library(p.db_path(root))
    return lib.list(status=status, limit=limit)


@app.post("/api/projects/{slug}/reveal")
def api_reveal_output(slug: str) -> dict:
    root = _root()
    p = Project.load(root, slug)
    out = p.output_dir(root)
    out.mkdir(parents=True, exist_ok=True)
    sysname = platform.system()
    try:
        if sysname == "Darwin":
            subprocess.Popen(["open", str(out)])
        elif sysname == "Windows":
            subprocess.Popen(["explorer", str(out)])
        else:
            subprocess.Popen(["xdg-open", str(out)])
    except Exception as e:
        return {"ok": False, "path": str(out), "error": str(e)}
    return {"ok": True, "path": str(out)}


# ---------- jobs ----------

class ScrapeRequest(BaseModel):
    channels: list[str] | None = None
    limit: int = 50


@app.post("/api/projects/{slug}/scrape")
def api_scrape(slug: str, body: ScrapeRequest, bt: BackgroundTasks) -> dict:
    root = _root()
    p = Project.load(root, slug)
    channels = body.channels or p.channels
    if not channels:
        raise HTTPException(400, "no channels configured")
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "id": job_id, "slug": slug, "type": "scrape",
        "status": "pending", "log": [], "started_at": _now(),
    }
    bt.add_task(_run_scrape, job_id, slug, channels, body.limit)
    return {"job_id": job_id}


def _run_scrape(job_id: str, slug: str, channels: list[str], limit: int) -> None:
    JOBS[job_id]["status"] = "running"
    try:
        root = _root()
        p = Project.load(root, slug)
        lib = Library(p.db_path(root))
        for ch in channels:
            _log(job_id, f"Scraping {ch} (top {limit} by views)...")
            try:
                items = list_channel_shorts(ch, limit=limit)
            except Exception as e:
                _log(job_id, f"  ERROR scraping {ch}: {e}")
                continue
            new = 0
            for item in items:
                if item["id"] and lib.add_scraped(item):
                    new += 1
            dup = len(items) - new
            _log(job_id, f"  {ch}: {len(items)} fetched, {new} new, {dup} already in library")
        JOBS[job_id]["status"] = "done"
    except Exception as e:
        JOBS[job_id]["status"] = "error"
        _log(job_id, f"FATAL: {e}")
    finally:
        JOBS[job_id]["finished_at"] = _now()


@app.post("/api/projects/{slug}/process")
def api_process(slug: str, bt: BackgroundTasks) -> dict:
    root = _root()
    p = Project.load(root, slug)
    if not p.cta_path(root).exists():
        raise HTTPException(400, "upload a CTA video before processing")
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "id": job_id, "slug": slug, "type": "process",
        "status": "pending", "log": [], "started_at": _now(),
    }
    bt.add_task(_run_process, job_id, slug)
    return {"job_id": job_id}


def _run_process(job_id: str, slug: str) -> None:
    JOBS[job_id]["status"] = "running"
    try:
        root = _root()
        p = Project.load(root, slug)
        lib = Library(p.db_path(root))
        cta = p.cta_path(root)

        pending = lib.list(status="scraped") + lib.list(status="downloaded") + lib.list(status="failed")
        seen: set[str] = set()
        queue: list[dict] = []
        for v in pending:
            if v["video_id"] in seen:
                continue
            seen.add(v["video_id"])
            queue.append(v)

        _log(job_id, f"{len(queue)} videos to process")
        for v in queue:
            vid = v["video_id"]
            title = (v.get("title") or "")[:60]
            try:
                raw_path = Path(v["raw_path"]) if v.get("raw_path") else None
                if not raw_path or not raw_path.exists():
                    _log(job_id, f"  download {vid}  {title}")
                    raw_path = download_video(vid, p.raw_dir(root))
                    lib.update(
                        vid,
                        raw_path=str(raw_path),
                        status="downloaded",
                        downloaded_at=_now(),
                    )
                out = p.output_dir(root) / f"{vid}.mp4"
                _log(job_id, f"  stitch   {vid} -> {out.name}")
                trim_and_stitch(
                    raw_path, cta, out,
                    trim_seconds=p.trim_seconds,
                    width=p.output_width, height=p.output_height,
                    framerate=p.framerate,
                    video_bitrate=p.video_bitrate,
                    audio_bitrate=p.audio_bitrate,
                )
                lib.update(
                    vid,
                    output_path=str(out),
                    status="stitched",
                    stitched_at=_now(),
                    error=None,
                )
            except Exception as e:
                lib.update(vid, status="failed", error=str(e)[:500])
                _log(job_id, f"  FAILED {vid}: {e}")
        JOBS[job_id]["status"] = "done"
    except Exception as e:
        JOBS[job_id]["status"] = "error"
        _log(job_id, f"FATAL: {e}")
    finally:
        JOBS[job_id]["finished_at"] = _now()


@app.get("/api/jobs")
def api_jobs() -> list[dict]:
    return list(JOBS.values())[-50:]


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str) -> dict:
    if job_id not in JOBS:
        raise HTTPException(404, "no such job")
    return JOBS[job_id]


@app.get("/api/health")
def api_health() -> dict:
    return {
        "ok": True,
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "encoder": detect_video_encoder(),
    }
