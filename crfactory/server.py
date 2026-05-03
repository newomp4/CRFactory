from __future__ import annotations
import platform
import random
import re
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
from .scraper import fetch_video_metadata, list_channel_shorts
from .stitcher import stitch_with_cta

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


def _project_or_404(slug: str) -> tuple[Project, Path]:
    root = _root()
    try:
        return Project.load(root, slug), root
    except FileNotFoundError:
        raise HTTPException(404, "project not found")


def _dir_size(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    files = [f for f in path.glob("*") if f.is_file()]
    return sum(f.stat().st_size for f in files), len(files)


_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str, default: str = "cta.mp4") -> str:
    base = Path(name).name
    base = _FILENAME_SAFE.sub("_", base).strip("._")
    return base or default


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
    root = _root()
    out = []
    for p in list_projects(root):
        lib = Library(p.db_path(root))
        ctas = p.list_cta_files(root)
        out.append({
            **p.__dict__,
            "stats": lib.stats(),
            "cta_count": len(ctas),
            "has_cta": len(ctas) > 0,
        })
    return out


class ProjectCreate(BaseModel):
    name: str
    channels: list[str] = []


@app.post("/api/projects")
def api_create_project(body: ProjectCreate) -> dict:
    root = _root()
    slug = Project.slugify(body.name)
    if (root / slug / "project.json").exists():
        raise HTTPException(400, f"project '{slug}' already exists")
    p = Project(name=body.name, slug=slug, channels=body.channels)
    p.save(root)
    return p.__dict__


@app.get("/api/projects/{slug}")
def api_get_project(slug: str) -> dict:
    p, root = _project_or_404(slug)
    lib = Library(p.db_path(root))
    raw_bytes, raw_files = _dir_size(p.raw_dir(root))
    out_bytes, out_files = _dir_size(p.output_dir(root))
    ctas = p.list_cta_files(root)
    return {
        "project": p.__dict__,
        "stats": lib.stats(),
        "has_cta": len(ctas) > 0,
        "cta_count": len(ctas),
        "output_dir": str(p.output_dir(root)),
        "disk": {
            "raw_bytes": raw_bytes, "raw_files": raw_files,
            "output_bytes": out_bytes, "output_files": out_files,
            "total_bytes": raw_bytes + out_bytes,
        },
    }


class ProjectUpdate(BaseModel):
    channels: list[str] | None = None
    output_width: int | None = None
    output_height: int | None = None
    framerate: int | None = None
    video_bitrate: str | None = None
    audio_bitrate: str | None = None


@app.put("/api/projects/{slug}")
def api_update_project(slug: str, body: ProjectUpdate) -> dict:
    p, root = _project_or_404(slug)
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


@app.get("/api/projects/{slug}/ctas")
def api_list_ctas(slug: str) -> list[dict]:
    p, root = _project_or_404(slug)
    return [
        {
            "name": f.name,
            "size": f.stat().st_size,
            "url": f"/api/projects/{slug}/ctas/{f.name}",
        }
        for f in p.list_cta_files(root)
    ]


@app.post("/api/projects/{slug}/ctas")
async def api_upload_cta(slug: str, file: UploadFile) -> dict:
    p, root = _project_or_404(slug)
    p.ensure_dirs(root)
    name = _safe_filename(file.filename or "cta.mp4")
    target = p.ctas_dir(root) / name
    with target.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"ok": True, "name": name, "size": target.stat().st_size}


@app.get("/api/projects/{slug}/ctas/{name}")
def api_get_cta(slug: str, name: str) -> FileResponse:
    p, root = _project_or_404(slug)
    safe = _safe_filename(name)
    target = p.ctas_dir(root) / safe
    if not target.exists():
        raise HTTPException(404, "cta not found")
    return FileResponse(target, media_type="video/mp4")


@app.delete("/api/projects/{slug}/ctas/{name}")
def api_delete_cta(slug: str, name: str) -> dict:
    p, root = _project_or_404(slug)
    safe = _safe_filename(name)
    target = p.ctas_dir(root) / safe
    if not target.exists():
        raise HTTPException(404, "cta not found")
    target.unlink()
    return {"ok": True}


# ---------- library ----------

@app.get("/api/projects/{slug}/library")
def api_library(slug: str, status: str | None = None, limit: int = 1000) -> list[dict]:
    p, root = _project_or_404(slug)
    lib = Library(p.db_path(root))
    return lib.list(status=status, limit=limit)


class AddByUrlRequest(BaseModel):
    url: str


@app.post("/api/projects/{slug}/library/add")
def api_library_add(slug: str, body: AddByUrlRequest) -> dict:
    p, root = _project_or_404(slug)
    lib = Library(p.db_path(root))
    try:
        meta = fetch_video_metadata(body.url)
    except Exception as e:
        raise HTTPException(400, f"could not fetch metadata: {e}")
    if not meta.get("id"):
        raise HTTPException(400, "could not parse video id")
    if lib.has(meta["id"]):
        return {"added": False, "reason": "already in library", "video_id": meta["id"]}
    lib.add_scraped(meta)
    return {"added": True, "video_id": meta["id"]}


@app.post("/api/projects/{slug}/library/{video_id}/retry")
def api_library_retry(slug: str, video_id: str) -> dict:
    p, root = _project_or_404(slug)
    lib = Library(p.db_path(root))
    if not lib.get(video_id):
        raise HTTPException(404, "video not in library")
    lib.update(video_id, status="scraped", error=None)
    return {"ok": True}


@app.delete("/api/projects/{slug}/library/{video_id}")
def api_library_delete(slug: str, video_id: str, delete_files: bool = True) -> dict:
    p, root = _project_or_404(slug)
    lib = Library(p.db_path(root))
    row = lib.get(video_id)
    if not row:
        raise HTTPException(404, "video not in library")
    if delete_files:
        for key in ("raw_path", "output_path"):
            if row.get(key):
                Path(row[key]).unlink(missing_ok=True)
    import sqlite3
    with sqlite3.connect(lib.db_path) as c:
        c.execute("DELETE FROM videos WHERE video_id=?", (video_id,))
        c.commit()
    return {"ok": True}


@app.get("/api/projects/{slug}/library/{video_id}/output")
def api_library_output(slug: str, video_id: str) -> FileResponse:
    p, root = _project_or_404(slug)
    lib = Library(p.db_path(root))
    row = lib.get(video_id)
    if not row or not row.get("output_path"):
        raise HTTPException(404, "no output")
    path = Path(row["output_path"])
    if not path.exists():
        raise HTTPException(404, "output file missing")
    return FileResponse(path, media_type="video/mp4")


@app.post("/api/projects/{slug}/reveal")
def api_reveal_output(slug: str) -> dict:
    p, root = _project_or_404(slug)
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
    p, root = _project_or_404(slug)
    channels = body.channels or p.channels
    if not channels:
        raise HTTPException(400, "no channels configured")
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "id": job_id, "slug": slug, "type": "scrape",
        "status": "pending", "log": [], "progress": None,
        "started_at": _now(),
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
    p, root = _project_or_404(slug)
    if not p.list_cta_files(root):
        raise HTTPException(400, "upload at least one CTA video before processing")
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "id": job_id, "slug": slug, "type": "process",
        "status": "pending", "log": [], "progress": None,
        "started_at": _now(),
    }
    bt.add_task(_run_process, job_id, slug)
    return {"job_id": job_id}


def _run_process(job_id: str, slug: str) -> None:
    JOBS[job_id]["status"] = "running"
    try:
        root = _root()
        p = Project.load(root, slug)
        lib = Library(p.db_path(root))

        ctas = p.list_cta_files(root)
        if not ctas:
            raise RuntimeError("no CTA videos uploaded")
        deck = ctas[:]
        random.shuffle(deck)
        if len(ctas) == 1:
            _log(job_id, f"Using CTA: {ctas[0].name}")
        else:
            _log(job_id, f"Pool of {len(ctas)} CTAs (round-robin, shuffled): {', '.join(c.name for c in ctas)}")

        pending = lib.list(status="scraped") + lib.list(status="downloaded") + lib.list(status="failed")
        seen: set[str] = set()
        queue: list[dict] = []
        for v in pending:
            if v["video_id"] in seen:
                continue
            seen.add(v["video_id"])
            queue.append(v)

        total = len(queue)
        JOBS[job_id]["progress"] = {"done": 0, "total": total}
        _log(job_id, f"{total} videos to process")

        for idx, v in enumerate(queue, start=1):
            vid = v["video_id"]
            title = (v.get("title") or "")[:60]
            cta = deck[(idx - 1) % len(deck)]
            try:
                raw_path = Path(v["raw_path"]) if v.get("raw_path") else None
                if not raw_path or not raw_path.exists():
                    _log(job_id, f"[{idx}/{total}] download {vid}  {title}")
                    raw_path = download_video(vid, p.raw_dir(root))
                    lib.update(
                        vid,
                        raw_path=str(raw_path),
                        status="downloaded",
                        downloaded_at=_now(),
                    )
                out_name = p.output_filename(vid, v.get("title"))
                out = p.output_dir(root) / out_name
                _log(job_id, f"[{idx}/{total}] stitch   {vid} + {cta.name} -> {out.name}")
                stitch_with_cta(
                    raw_path, cta, out,
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
                    cta_used=cta.name,
                    error=None,
                )
            except Exception as e:
                lib.update(vid, status="failed", error=str(e)[:500])
                _log(job_id, f"[{idx}/{total}] FAILED {vid}: {e}")
            finally:
                JOBS[job_id]["progress"] = {"done": idx, "total": total}
        JOBS[job_id]["status"] = "done"
    except Exception as e:
        JOBS[job_id]["status"] = "error"
        _log(job_id, f"FATAL: {e}")
    finally:
        JOBS[job_id]["finished_at"] = _now()


@app.get("/api/jobs")
def api_jobs(slug: str | None = None) -> list[dict]:
    items = list(JOBS.values())
    if slug:
        items = [j for j in items if j.get("slug") == slug]
    return items[-50:]


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
