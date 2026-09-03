from __future__ import annotations

import csv
import json
import os
import threading
from pathlib import Path
from typing import Any

from app.catalogs.service import CatalogService as BaseCatalogService


class ManagedCatalogService(BaseCatalogService):
    """Complementa o serviço canônico com identidade lógica e atualização de catálogos PluginTema."""

    def __init__(self, data_dir: Path, gateway: Any = None):
        super().__init__(data_dir, gateway)
        self._finalizer: threading.Thread | None = None
        self._finalizer_source: threading.Thread | None = None

    @property
    def _definitions_path(self) -> Path:
        return self.data_dir / "catalog_definitions.json"

    def _load_definitions(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self._definitions_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): dict(value) for key, value in payload.items() if isinstance(value, dict)}

    def _save_definitions(self, definitions: dict[str, dict[str, Any]]) -> None:
        self._definitions_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._definitions_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(definitions, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self._definitions_path)

    @staticmethod
    def _is_plugintema_id(catalog_id: str) -> bool:
        lowered = str(catalog_id or "").casefold()
        return lowered.startswith("imports/") and "plugintema" in lowered and "plugintheme" not in lowered

    @classmethod
    def _name_key(cls, value: Any) -> str:
        return cls._fold(" ".join(str(value or "").split()))

    def _remove_catalog_ids(
        self,
        catalog_ids: set[str],
        *,
        names: dict[str, str] | None = None,
        definitions: dict[str, dict[str, Any]] | None = None,
    ) -> list[str]:
        names = names if names is not None else self._load_names()
        definitions = definitions if definitions is not None else self._load_definitions()
        removed: list[str] = []
        for catalog_id in sorted(catalog_ids):
            if not self._is_plugintema_id(catalog_id):
                continue
            path = (self.data_dir / catalog_id).resolve()
            try:
                if self.data_dir in path.parents and path.is_file():
                    path.unlink()
            except OSError:
                raise RuntimeError(f"Não foi possível substituir o catálogo anterior: {catalog_id}")
            names.pop(catalog_id, None)
            definitions.pop(catalog_id, None)
            removed.append(catalog_id)
        self._save_names(names)
        self._save_definitions(definitions)
        return removed

    def _collapse_duplicate_names(self) -> list[str]:
        if self._worker and self._worker.is_alive():
            return []
        with self._lock:
            names = self._load_names()
            definitions = self._load_definitions()
            groups: dict[str, list[str]] = {}
            for catalog_id, name in names.items():
                if self._is_plugintema_id(catalog_id) and self._name_key(name):
                    groups.setdefault(self._name_key(name), []).append(catalog_id)
            remove: set[str] = set()
            for catalog_ids in groups.values():
                if len(catalog_ids) < 2:
                    continue
                existing = []
                for catalog_id in catalog_ids:
                    path = self.data_dir / catalog_id
                    if path.is_file():
                        existing.append((path.stat().st_mtime, catalog_id))
                if len(existing) < 2:
                    continue
                existing.sort(reverse=True)
                remove.update(catalog_id for _, catalog_id in existing[1:])
            return self._remove_catalog_ids(remove, names=names, definitions=definitions) if remove else []

    def _catalog_ids_from_csv(self, catalog_id: str) -> list[int]:
        path = self.data_dir / catalog_id
        if not path.is_file():
            return []
        result: list[int] = []
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    try:
                        result.append(int(str(row.get("ID") or "").strip()))
                    except (TypeError, ValueError):
                        continue
        except OSError:
            return []
        return sorted(set(result))

    def _infer_kinds_from_csv(self, catalog_id: str) -> list[str]:
        path = self.data_dir / catalog_id
        if not path.is_file():
            return []
        kinds: set[str] = set()
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    categories = [
                        {"name": item.strip()}
                        for item in str(row.get("Categorias") or "").split(",")
                        if item.strip()
                    ]
                    kind = self._catalog_kind({"type": row.get("Tipo", ""), "categories": categories})
                    if kind in self.KIND_ORDER:
                        kinds.add(kind)
        except OSError:
            return []
        return [kind for kind in self.KIND_ORDER if kind in kinds]

    def _infer_definition(self, row: dict[str, Any]) -> dict[str, Any]:
        catalog_id = str(row.get("id") or "")
        display_name = str(row.get("display_name") or row.get("label") or "").strip()
        filename = Path(catalog_id).name.casefold()
        if "personalizado" in filename or "custom" in filename:
            ids = self._catalog_ids_from_csv(catalog_id)
            return {
                "mode": "custom",
                "name": display_name,
                "kinds": [],
                "custom": {
                    "type": "all",
                    "status": "any",
                    "category_ids": [],
                    "query": "",
                    "specific_ids": ", ".join(str(item) for item in ids),
                    "version": "all",
                    "include_ids": ids,
                },
                "inferred": True,
            }
        kinds = self._infer_kinds_from_csv(catalog_id)
        if not kinds:
            kinds = [kind for kind in self.KIND_ORDER if f"-{kind}-" in f"-{filename}-"]
        return {
            "mode": "preset",
            "name": display_name,
            "kinds": kinds or ["plugin"],
            "custom": {
                "type": "all",
                "status": "publish",
                "category_ids": [],
                "query": "",
                "specific_ids": "",
                "version": "all",
                "include_ids": [],
            },
            "inferred": True,
        }

    def _definition_from_payload(self, payload: dict[str, Any], display_name: str) -> dict[str, Any]:
        mode = "custom" if str(payload.get("mode") or "").casefold() == "custom" else "preset"
        kinds = [kind for kind in self.KIND_ORDER if kind in {str(item) for item in payload.get("kinds", [])}]
        raw_custom = payload.get("custom") if isinstance(payload.get("custom"), dict) else {}
        include_ids = sorted(self._ids(raw_custom.get("include_ids")))
        category_ids = [str(item) for item in raw_custom.get("category_ids", []) if str(item)]
        return {
            "mode": mode,
            "name": display_name,
            "kinds": kinds,
            "custom": {
                "type": str(raw_custom.get("type") or "all"),
                "status": str(raw_custom.get("status") or "publish"),
                "category_ids": category_ids,
                "query": str(raw_custom.get("query") or ""),
                "specific_ids": str(raw_custom.get("specific_ids") or ""),
                "version": str(raw_custom.get("version") or "all"),
                "include_ids": include_ids,
            },
            "inferred": False,
        }

    def list(self, query: dict[str, Any] | None = None) -> dict[str, Any]:
        self._collapse_duplicate_names()
        data = super().list(query)
        definitions = self._load_definitions()
        for row in data.get("rows", []):
            catalog_id = str(row.get("id") or "")
            if self._is_plugintema_id(catalog_id):
                row["generation_config"] = definitions.get(catalog_id) or self._infer_definition(row)
        return data

    def set_name(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = super().set_name(payload)
        catalog = response.get("catalog") or {}
        catalog_id = str(catalog.get("id") or payload.get("catalog_id") or "")
        name = str(catalog.get("display_name") or payload.get("name") or "").strip()
        with self._lock:
            definitions = self._load_definitions()
            definition = definitions.get(catalog_id) or self._infer_definition(catalog)
            definition["name"] = name
            definitions[catalog_id] = definition
            self._save_definitions(definitions)
            names = self._load_names()
            duplicate_ids = {
                other_id
                for other_id, other_name in names.items()
                if other_id != catalog_id
                and self._is_plugintema_id(other_id)
                and self._name_key(other_name) == self._name_key(name)
            }
            removed = self._remove_catalog_ids(duplicate_ids, names=names, definitions=definitions) if duplicate_ids else []
        response["replaced_catalog_ids"] = removed
        response["catalog"] = self._metadata_with_name(self.data_dir / catalog_id)
        return response

    def delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        catalog_id = str(payload.get("catalog_id") or "")
        response = super().delete(payload)
        with self._lock:
            definitions = self._load_definitions()
            if catalog_id in definitions:
                definitions.pop(catalog_id, None)
                self._save_definitions(definitions)
        return response

    def _finalize_generation(self, source_worker: threading.Thread, payload: dict[str, Any]) -> None:
        source_worker.join()
        try:
            with self._lock:
                if self._generation.get("status") != "completed":
                    return
                result = dict(self._generation.get("result") or {})
                catalog_id = str(result.get("catalog_id") or "")
                display_name = str(result.get("display_name") or "").strip()
                if not catalog_id or not display_name:
                    return

                names = self._load_names()
                definitions = self._load_definitions()
                definition = self._definition_from_payload(payload, display_name)
                duplicate_ids = {
                    other_id
                    for other_id, other_name in names.items()
                    if other_id != catalog_id
                    and self._is_plugintema_id(other_id)
                    and self._name_key(other_name) == self._name_key(display_name)
                }
                replace_id = str(payload.get("replace_catalog_id") or "").strip()
                if replace_id and replace_id != catalog_id and self._is_plugintema_id(replace_id):
                    duplicate_ids.add(replace_id)

                definitions[catalog_id] = definition
                names[catalog_id] = display_name
                removed = self._remove_catalog_ids(duplicate_ids, names=names, definitions=definitions) if duplicate_ids else []
                if not duplicate_ids:
                    self._save_names(names)
                    self._save_definitions(definitions)

                result["replaced_catalog_ids"] = removed
                result["generation_config"] = definition
                logs = list(self._generation.get("logs") or [])
                if removed:
                    logs.append(f"{len(removed)} catálogo(s) anterior(es) com o mesmo nome substituído(s).")
                self._generation = {
                    **self._generation,
                    "status": "completed",
                    "progress": 100,
                    "logs": logs,
                    "result": result,
                }
        except Exception as error:
            with self._lock:
                self._generation = {
                    **self._generation,
                    "status": "error",
                    "logs": [*self._generation.get("logs", []), f"Falha ao substituir catálogo anterior: {error}"],
                }

    def generate_plugintema(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(payload or {})
        response = super().generate_plugintema(payload)
        source_worker = self._worker
        if source_worker and source_worker.is_alive() and source_worker is not self._finalizer_source:
            self._finalizer_source = source_worker
            self._finalizer = threading.Thread(
                target=self._finalize_generation,
                args=(source_worker, payload),
                name="plugintema-catalog-finalizer",
                daemon=True,
            )
            self._finalizer.start()
        return response

    def generation_status(self) -> dict[str, Any]:
        state = super().generation_status()
        finalizer = self._finalizer
        if finalizer and finalizer.is_alive() and state.get("status") == "completed":
            return {
                **state,
                "status": "running",
                "progress": 99,
                "logs": [*state.get("logs", []), "Finalizando substituição e identidade do catálogo…"],
            }
        return state
