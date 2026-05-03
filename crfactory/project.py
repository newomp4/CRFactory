from __future__ import annotations
import json
import re
from dataclasses import dataclass, asdict, field, fields
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Project:
    name: str
    slug: str
    channels: list[str] = field(default_factory=list)
    output_width: int = 1080
    output_height: int = 1920
    framerate: int = 30
    video_bitrate: str = "4M"
    audio_bitrate: str = "128k"
    cta_filename: str = "cta.mp4"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @staticmethod
    def slugify(name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
        return slug or "project"

    def dir(self, root: Path) -> Path:
        return root / self.slug

    def cta_path(self, root: Path) -> Path:
        return self.dir(root) / self.cta_filename

    def raw_dir(self, root: Path) -> Path:
        return self.dir(root) / "raw"

    def output_dir(self, root: Path) -> Path:
        return self.dir(root) / "output"

    def db_path(self, root: Path) -> Path:
        return self.dir(root) / "library.db"

    def project_file(self, root: Path) -> Path:
        return self.dir(root) / "project.json"

    def ensure_dirs(self, root: Path) -> None:
        for d in (self.dir(root), self.raw_dir(root), self.output_dir(root)):
            d.mkdir(parents=True, exist_ok=True)

    def output_filename(self, video_id: str, title: str | None = None) -> str:
        base = sanitize_for_filename(title or "") or "video"
        return f"{base[:80]}_{video_id}.mp4"

    def save(self, root: Path) -> None:
        self.ensure_dirs(root)
        self.project_file(root).write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, root: Path, slug: str) -> "Project":
        path = root / slug / "project.json"
        return cls.from_dict(json.loads(path.read_text()))

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})


def sanitize_for_filename(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE).strip()
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-")


def list_projects(root: Path) -> list[Project]:
    root.mkdir(parents=True, exist_ok=True)
    out: list[Project] = []
    for d in sorted(root.iterdir()):
        pf = d / "project.json"
        if pf.exists():
            try:
                out.append(Project.from_dict(json.loads(pf.read_text())))
            except Exception:
                continue
    return out
