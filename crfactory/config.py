from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path

CONFIG_DIR = Path.home() / ".crfactory"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_STORAGE_ROOT = Path.home() / "crfactory-data"


@dataclass
class AppConfig:
    storage_root: str = str(DEFAULT_STORAGE_ROOT)

    def storage_path(self) -> Path:
        return Path(self.storage_root).expanduser()

    @classmethod
    def load(cls) -> "AppConfig":
        if not CONFIG_FILE.exists():
            cfg = cls()
            cfg.save()
            return cfg
        return cls(**json.loads(CONFIG_FILE.read_text()))

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2))
        self.storage_path().mkdir(parents=True, exist_ok=True)
