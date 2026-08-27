from __future__ import annotations

from pathlib import Path
from typing import Any


class ComparisonRepository:
    def __init__(self, data_dir: Path): self.data_dir=data_dir.resolve()
    def catalogs(self) -> list[dict[str, Any]]:
        rows=[]
        for path in self.data_dir.rglob("*.csv"):
            relative=path.relative_to(self.data_dir).as_posix()
            if relative.startswith("update_queues/"): continue
            lowered=relative.lower(); role="site" if "plugintema" in lowered and "plugintheme" not in lowered else "source"
            rows.append({"id":relative,"label":relative,"role":role,"size":path.stat().st_size,"updated_at":path.stat().st_mtime})
        return sorted(rows,key=lambda x:x["updated_at"],reverse=True)
    def resolve(self, catalog_id: str) -> Path:
        path=(self.data_dir/catalog_id).resolve()
        if self.data_dir not in path.parents or path.suffix.lower()!=".csv" or not path.is_file(): raise ValueError("Catálogo inválido.")
        return path
