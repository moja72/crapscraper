from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    root: Path
    data_dir: Path
    host: str
    port: int


def load_settings() -> Settings:
    root = Path(__file__).resolve().parents[1]
    legacy_data = root.parent / "data"
    return Settings(
        root=root,
        data_dir=Path(os.getenv("SCRAPER_DATA_DIR", legacy_data)).resolve(),
        host=os.getenv("SCRAPER_HOST", "127.0.0.1"),
        port=int(os.getenv("SCRAPER_PORT", "8766")),
    )
