from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path

CONFIG_DIR = Path.home() / ".crfactory"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_STORAGE_ROOT = Path.home() / "crfactory-data"


SUPPORTED_BROWSERS = (
    "brave", "chrome", "chromium", "edge", "firefox",
    "opera", "safari", "vivaldi", "whale",
)


@dataclass
class AppConfig:
    storage_root: str = str(DEFAULT_STORAGE_ROOT)
    youtube_cookies_browser: str | None = None

    def storage_path(self) -> Path:
        return Path(self.storage_root).expanduser()

    @classmethod
    def load(cls) -> "AppConfig":
        if not CONFIG_FILE.exists():
            cfg = cls()
            cfg.save()
            return cfg
        data = json.loads(CONFIG_FILE.read_text())
        valid = {f.name for f in __import__("dataclasses").fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2))
        self.storage_path().mkdir(parents=True, exist_ok=True)
