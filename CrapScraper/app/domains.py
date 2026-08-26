from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.persistence import JsonStore


def _files(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    result: list[Path] = []
    for pattern in patterns:
        result.extend(root.rglob(pattern))
    return sorted(set(result), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)


@dataclass
class DomainService:
    data_dir: Path
    runtime: JsonStore

    def collection(self) -> dict[str, Any]:
        slots_root = self.data_dir / "slots"
        slots = [p.name for p in slots_root.iterdir() if p.is_dir()] if slots_root.exists() else []
        catalogs = _files(self.data_dir, ("*.csv",))
        state = self.runtime.read().get("collection", {})
        return {"ok": True, "slots": slots, "catalogs": len(catalogs), "recent": [str(p.relative_to(self.data_dir)) for p in catalogs[:8]], "state": state}

    def collection_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        all_state = self.runtime.read(); state = dict(all_state.get("collection", {}))
        if action == "create-slot":
            name = " ".join(str(payload.get("name", "")).split()).strip()
            if not name: raise ValueError("Informe o nome do slot.")
            (self.data_dir / "slots" / name).mkdir(parents=True, exist_ok=True)
            state["slot"] = name
        elif action == "select-slot": state["slot"] = str(payload.get("name", ""))
        elif action == "start": state.update(status="running", progress=0, started_at=datetime.now().isoformat(), logs=["Coleta iniciada pelo runtime consolidado."])
        elif action == "pause": state["status"] = "paused"
        elif action == "resume": state["status"] = "running"
        elif action == "stop": state["status"] = "stopped"
        else: raise ValueError("Ação de coleta desconhecida.")
        all_state["collection"] = state; self.runtime.write(all_state)
        return self.collection()

    def decisions(self) -> dict[str, Any]:
        dbs = _files(self.data_dir, ("*.db", "*.sqlite", "*.sqlite3"))
        rows: list[dict[str, Any]] = []
        chosen = ""
        for db in dbs:
            try:
                con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
                con.row_factory = sqlite3.Row
                tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
                table = next((t for t in tables if "decision" in t.lower()), None)
                if table:
                    rows = [dict(r) for r in con.execute(f'SELECT * FROM "{table}" ORDER BY rowid DESC LIMIT 200')]
                    chosen = str(db.relative_to(self.data_dir)); con.close(); break
                con.close()
            except sqlite3.Error: continue
        return {"ok": True, "database": chosen, "items": rows, "total": len(rows)}

    def jobs(self, decision: str) -> dict[str, Any]:
        items = self.decisions()["items"]
        selected = [r for r in items if str(r.get("decision", r.get("decision_type", ""))) == decision]
        return {"ok": True, "items": selected, "total": len(selected)}

    def store(self) -> dict[str, Any]:
        catalogs = _files(self.data_dir, ("*.csv",))
        products = 0
        for path in catalogs[:40]:
            try:
                with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
                    products += sum(1 for _ in csv.DictReader(stream))
            except OSError: pass
        return {"ok": True, "catalogs": len(catalogs), "products_sampled": products, "monitor": self.runtime.read().get("store_monitor", {"enabled": False})}

    def monitor(self, enabled: bool) -> dict[str, Any]:
        state = self.runtime.read(); state["store_monitor"] = {"enabled": enabled, "updated_at": datetime.now().isoformat()}; self.runtime.write(state)
        return self.store()
