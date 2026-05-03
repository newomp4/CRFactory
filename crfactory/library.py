from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id      TEXT PRIMARY KEY,
    channel       TEXT,
    title         TEXT,
    view_count    INTEGER,
    duration      REAL,
    thumbnail_url TEXT,
    upload_date   TEXT,
    scraped_at    TEXT,
    downloaded_at TEXT,
    stitched_at   TEXT,
    raw_path      TEXT,
    output_path   TEXT,
    status        TEXT,
    error         TEXT,
    cta_used      TEXT,
    clip_used     REAL
);
CREATE INDEX IF NOT EXISTS idx_status     ON videos(status);
CREATE INDEX IF NOT EXISTS idx_view_count ON videos(view_count DESC);
"""

EXTRA_COLUMNS: list[tuple[str, str]] = [
    ("cta_used", "TEXT"),
    ("clip_used", "REAL"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Library:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)
            existing = {r[1] for r in c.execute("PRAGMA table_info(videos)").fetchall()}
            for name, decl in EXTRA_COLUMNS:
                if name not in existing:
                    c.execute(f"ALTER TABLE videos ADD COLUMN {name} {decl}")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def has(self, video_id: str) -> bool:
        with self._conn() as c:
            return c.execute(
                "SELECT 1 FROM videos WHERE video_id=?", (video_id,)
            ).fetchone() is not None

    def add_scraped(self, v: dict) -> bool:
        with self._conn() as c:
            cur = c.execute(
                """
                INSERT OR IGNORE INTO videos
                  (video_id, channel, title, view_count, duration,
                   thumbnail_url, upload_date, scraped_at, status)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    v["id"], v.get("channel"), v.get("title"),
                    v.get("view_count"), v.get("duration"),
                    v.get("thumbnail"), v.get("upload_date"),
                    _now(), "scraped",
                ),
            )
            return cur.rowcount > 0

    def update(self, video_id: str, **fields) -> None:
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with self._conn() as c:
            c.execute(
                f"UPDATE videos SET {sets} WHERE video_id=?",
                (*fields.values(), video_id),
            )

    def list(self, status: str | None = None, limit: int = 1000) -> list[dict]:
        q = "SELECT * FROM videos"
        args: tuple = ()
        if status:
            q += " WHERE status=?"
            args = (status,)
        q += " ORDER BY view_count DESC LIMIT ?"
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, (*args, limit)).fetchall()]

    def get(self, video_id: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM videos WHERE video_id=?", (video_id,)).fetchone()
            return dict(r) if r else None

    def stats(self) -> dict:
        with self._conn() as c:
            r = c.execute(
                """
                SELECT
                  COUNT(*) AS total,
                  SUM(CASE WHEN status='scraped'    THEN 1 ELSE 0 END) AS scraped,
                  SUM(CASE WHEN status='downloaded' THEN 1 ELSE 0 END) AS downloaded,
                  SUM(CASE WHEN status='stitched'   THEN 1 ELSE 0 END) AS stitched,
                  SUM(CASE WHEN status='failed'     THEN 1 ELSE 0 END) AS failed
                FROM videos
                """
            ).fetchone()
            return {k: (v or 0) for k, v in dict(r).items()}
