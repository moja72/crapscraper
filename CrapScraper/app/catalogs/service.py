from __future__ import annotations

import csv
import io
import json
import os
import threading
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any


class CatalogService:
    """Leitura administrativa dos CSVs canônicos e geração de catálogos PluginTema."""

    KIND_LABELS = {
        "plugin": "Plugins",
        "theme": "Temas",
        "template": "Templates",
        "pack": "Packs",
        "plan": "Assinatura",
        "other": "Outros",
    }
    KIND_ORDER = ("plugin", "theme", "template", "pack", "plan")
    STATUSES = (
        ("publish", "Publicado"),
        ("draft", "Rascunho"),
        ("pending", "Pendente"),
        ("private", "Privado"),
        ("any", "Todos"),
    )

    def __init__(self, data_dir: Path, gateway: Any = None):
        self.data_dir = data_dir.resolve()
        self.gateway = gateway
        self._generation = {"status": "idle", "progress": 0, "logs": [], "result": None}
        self._lock = threading.RLock()
        self._worker = None

    @property
    def _names_path(self) -> Path:
        return self.data_dir / "catalog_names.json"

    def _load_names(self) -> dict[str, str]:
        try:
            payload = json.loads(self._names_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(value).strip() for key, value in payload.items() if str(value).strip()}

    def _save_names(self, names: dict[str, str]) -> None:
        self._names_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._names_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(names, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self._names_path)

    def _resolve(self, catalog_id: str) -> Path:
        path = (self.data_dir / str(catalog_id or "")).resolve()
        if self.data_dir not in path.parents or path.suffix.lower() != ".csv" or not path.is_file():
            raise ValueError("Catálogo inválido.")
        return path

    def _editable_plugintema(self, catalog_id: str) -> tuple[Path, str]:
        path = self._resolve(catalog_id)
        relative = path.relative_to(self.data_dir).as_posix()
        lowered = relative.casefold()
        if not relative.startswith("imports/") or "plugintema" not in lowered or "plugintheme" in lowered:
            raise ValueError("Apenas catálogos exportados da PluginTema podem ser renomeados ou excluídos.")
        return path, relative

    @staticmethod
    def _metadata(path: Path, root: Path) -> dict[str, Any]:
        relative = path.relative_to(root).as_posix()
        parts = relative.split("/")
        context = parts[:5] if len(parts) >= 6 and parts[0] == "slots" and parts[-1] == "catalog.csv" else []
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            count = max(0, sum(1 for _ in stream) - 1)
        return {
            "id": relative,
            "name": path.name,
            "label": relative,
            "items_count": count,
            "size": path.stat().st_size,
            "updated_at": path.stat().st_mtime,
            "available": True,
            "kind": "context" if context else "import",
            "slot_name": context[1] if context else "",
            "site_key": context[2] if context else "",
            "item_type_key": context[3] if context else "",
            "account_key": context[4] if context else "",
        }

    def _metadata_with_name(self, path: Path, names: dict[str, str] | None = None) -> dict[str, Any]:
        row = self._metadata(path, self.data_dir)
        names = names if names is not None else self._load_names()
        display_name = str(names.get(row["id"]) or "").strip()
        row["display_name"] = display_name
        if display_name:
            row["label"] = display_name
        return row

    def list(self, query: dict[str, Any] | None = None) -> dict[str, Any]:
        query = query or {}
        needle = str(query.get("query") or "").strip().casefold()
        page = max(1, int(query.get("page") or 1))
        page_size = min(100, max(1, int(query.get("page_size") or 20)))
        names = self._load_names()
        rows = [
            self._metadata_with_name(path, names)
            for path in self.data_dir.rglob("*.csv")
            if "update_queues" not in path.relative_to(self.data_dir).parts
        ]
        if needle:
            rows = [row for row in rows if needle in " ".join(str(v) for v in row.values()).casefold()]
        rows.sort(key=lambda row: row["updated_at"], reverse=True)
        total = len(rows)
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        start = (page - 1) * page_size
        return {
            "ok": True,
            "rows": rows[start : start + page_size],
            "pagination": {"page": page, "page_size": page_size, "total_rows": total, "total_pages": pages},
        }

    def preview(self, query: dict[str, Any]) -> dict[str, Any]:
        path = self._resolve(str(query.get("catalog_id") or ""))
        needle = str(query.get("query") or "").strip().casefold()
        page = max(1, int(query.get("page") or 1))
        page_size = min(100, max(1, int(query.get("page_size") or 30)))
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            headers = list(reader.fieldnames or [])
            rows = [dict(row) for row in reader]
        if needle:
            rows = [row for row in rows if needle in " ".join(str(v) for v in row.values()).casefold()]
        total = len(rows)
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        start = (page - 1) * page_size
        return {
            "ok": True,
            "catalog": self._metadata_with_name(path),
            "headers": headers,
            "rows": rows[start : start + page_size],
            "pagination": {"page": page, "page_size": page_size, "total_rows": total, "total_pages": pages},
        }

    def download(self, catalog_id: str) -> tuple[str, bytes]:
        path = self._resolve(catalog_id)
        return path.name, path.read_bytes()

    def set_name(self, payload: dict[str, Any]) -> dict[str, Any]:
        path, catalog_id = self._editable_plugintema(str(payload.get("catalog_id") or ""))
        name = " ".join(str(payload.get("name") or "").split())
        if not name:
            raise ValueError("Informe um nome para o catálogo.")
        if len(name) > 100:
            raise ValueError("O nome do catálogo deve ter no máximo 100 caracteres.")
        with self._lock:
            names = self._load_names()
            names[catalog_id] = name
            self._save_names(names)
        return {"ok": True, "catalog": self._metadata_with_name(path, names)}

    def delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        path, catalog_id = self._editable_plugintema(str(payload.get("catalog_id") or ""))
        with self._lock:
            path.unlink()
            names = self._load_names()
            if catalog_id in names:
                names.pop(catalog_id, None)
                self._save_names(names)
        return {"ok": True, "deleted": True, "catalog_id": catalog_id}

    @staticmethod
    def _meta(product: dict[str, Any], key: str) -> str:
        return next(
            (str(item.get("value") or "") for item in product.get("meta_data", []) if item.get("key") == key),
            "",
        )

    @staticmethod
    def _fold(value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().casefold()
        return " ".join(text.split())

    @classmethod
    def _catalog_kind(cls, product: dict[str, Any]) -> str:
        categories = {cls._fold(item.get("name")) for item in product.get("categories", []) or []}
        product_type = cls._fold(product.get("type"))
        if product_type == "bundle" or categories & {"pack", "packs", "pacote", "pacotes"}:
            return "pack"
        if "subscription" in product_type or categories & {
            "plano",
            "planos",
            "assinatura",
            "assinaturas",
            "subscription",
            "subscriptions",
            "membership",
            "memberships",
        }:
            return "plan"
        if categories & {"template", "templates"} or any("template" in item for item in categories):
            return "template"
        if categories & {"tema", "temas", "theme", "themes"} or any("theme" in item for item in categories):
            return "theme"
        if categories & {"plugin", "plugins"} or any("plugin" in item for item in categories):
            return "plugin"
        return "other"

    @staticmethod
    def _ids(value: Any) -> set[int]:
        if isinstance(value, (list, tuple, set)):
            raw = value
        else:
            raw = str(value or "").replace(";", ",").replace(" ", ",").split(",")
        result = set()
        for item in raw:
            try:
                if str(item).strip():
                    result.add(int(str(item).strip()))
            except (TypeError, ValueError):
                continue
        return result

    def generation_options(self) -> dict[str, Any]:
        if self.gateway is None:
            raise RuntimeError("WooCommerce não configurado para geração.")
        categories = list(self.gateway.categories())
        categories.sort(key=lambda item: self._fold(item.get("name")))
        return {
            "ok": True,
            "kinds": [{"id": key, "label": self.KIND_LABELS[key]} for key in self.KIND_ORDER],
            "statuses": [{"id": key, "label": label} for key, label in self.STATUSES],
            "categories": [
                {"id": int(item.get("id") or 0), "name": str(item.get("name") or ""), "count": int(item.get("count") or 0)}
                for item in categories
                if item.get("id")
            ],
        }

    def search_products(self, query: dict[str, Any]) -> dict[str, Any]:
        if self.gateway is None:
            raise RuntimeError("WooCommerce não configurado para geração.")
        needle = str(query.get("query") or "").strip()
        if not needle:
            return {"ok": True, "items": []}
        status = str(query.get("status") or "publish")
        requested_kind = str(query.get("type") or "").strip()
        fields = "id,name,slug,status,type,categories,meta_data"
        products: list[dict[str, Any]] = []
        if needle.isdigit():
            try:
                products = [self.gateway.product(int(needle))]
            except Exception:
                products = []
        else:
            filters: dict[str, Any] = {"search": needle, "_fields": fields}
            if status and status != "any":
                filters["status"] = status
            products = list(self.gateway.products(**filters))
        folded_needle = self._fold(needle)
        rows = []
        for product in products:
            haystack = self._fold(f"{product.get('id', '')} {product.get('name', '')} {product.get('slug', '')}")
            kind = self._catalog_kind(product)
            if folded_needle and folded_needle not in haystack:
                continue
            if requested_kind and requested_kind != "all" and kind != requested_kind:
                continue
            rows.append(
                {
                    "id": int(product.get("id") or 0),
                    "name": str(product.get("name") or ""),
                    "kind": kind,
                    "kind_label": self.KIND_LABELS.get(kind, "Outro"),
                    "status": str(product.get("status") or ""),
                    "version": self._meta(product, "pt_versao"),
                    "categories": [str(item.get("name") or "") for item in product.get("categories", []) or []],
                }
            )
        rows.sort(key=lambda item: (self._fold(item["name"]), item["id"]))
        return {"ok": True, "items": rows[:20]}

    def generation_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                **self._generation,
                "logs": list(self._generation.get("logs") or []),
                "result": dict(self._generation["result"]) if isinstance(self._generation.get("result"), dict) else self._generation.get("result"),
            }

    def _generation_update(self, *, progress: int | None = None, log: str | None = None) -> None:
        with self._lock:
            if progress is not None:
                self._generation["progress"] = max(0, min(100, int(progress)))
            if log:
                self._generation.setdefault("logs", []).append(str(log))

    def _automatic_name(self, mode: str, kinds: set[str]) -> str:
        when = datetime.now().strftime("%d/%m/%Y %H:%M")
        if mode == "custom":
            return f"PluginTema · Personalizado · {when}"
        labels = [self.KIND_LABELS[key] for key in self.KIND_ORDER if key in kinds]
        scope = " + ".join(labels) if labels else "Produtos"
        return f"PluginTema · {scope} · {when}"

    def generate_plugintema(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        with self._lock:
            if self._worker and self._worker.is_alive():
                return {"ok": True, **self._generation}
            self._generation = {
                "status": "running",
                "progress": 2,
                "logs": ["Iniciando leitura do WooCommerce em modo somente leitura."],
                "result": None,
            }

            def work() -> None:
                try:
                    if self.gateway is None:
                        raise RuntimeError("WooCommerce não configurado para geração.")

                    mode = "custom" if str(payload.get("mode") or "").lower() == "custom" else "preset"
                    requested_kinds = {str(item) for item in payload.get("kinds", ["plugin", "theme"])}
                    requested_kinds &= set(self.KIND_ORDER)
                    if mode == "preset" and not requested_kinds:
                        raise ValueError("Selecione pelo menos um tipo de produto.")

                    custom = payload.get("custom") if isinstance(payload.get("custom"), dict) else {}
                    status = str(custom.get("status") or "publish") if mode == "custom" else "publish"
                    filters: dict[str, Any] = {
                        "_fields": "id,name,slug,permalink,status,type,categories,meta_data"
                    }
                    if status and status != "any":
                        filters["status"] = status

                    self._generation_update(progress=8, log="Consultando produtos no WooCommerce…")
                    products = list(self.gateway.products(**filters))
                    self._generation_update(progress=24, log=f"{len(products)} produto(s) recebido(s) do WooCommerce.")

                    include_ids = self._ids(custom.get("include_ids")) if mode == "custom" else set()
                    known_ids = {int(item.get("id") or 0) for item in products}
                    missing_includes = sorted(include_ids - known_ids)
                    for product_id in missing_includes:
                        try:
                            products.append(self.gateway.product(product_id))
                        except Exception as error:
                            self._generation_update(log=f"ID {product_id} não pôde ser carregado: {error}")

                    custom_type = str(custom.get("type") or "all")
                    categories = {str(item) for item in custom.get("category_ids", []) if str(item)}
                    query = self._fold(custom.get("query"))
                    specific_ids = self._ids(custom.get("specific_ids"))
                    version_filter = str(custom.get("version") or "all")

                    selected: list[dict[str, Any]] = []
                    total = max(1, len(products))
                    for index, product in enumerate(products, start=1):
                        product_id = int(product.get("id") or 0)
                        kind = self._catalog_kind(product)
                        manually_included = product_id in include_ids
                        accepted = manually_included

                        if not manually_included:
                            if mode == "preset":
                                accepted = kind in requested_kinds
                            else:
                                accepted = True
                                if custom_type and custom_type != "all" and kind != custom_type:
                                    accepted = False
                                if accepted and query:
                                    haystack = self._fold(f"{product_id} {product.get('name', '')} {product.get('slug', '')}")
                                    accepted = query in haystack
                                if accepted and categories:
                                    product_categories = {str(item.get("id") or "") for item in product.get("categories", []) or []}
                                    accepted = bool(categories & product_categories)
                                if accepted and specific_ids:
                                    accepted = product_id in specific_ids
                                if accepted and version_filter in {"with", "without"}:
                                    has_version = bool(self._meta(product, "pt_versao").strip())
                                    accepted = has_version if version_filter == "with" else not has_version

                        if accepted:
                            selected.append(product)

                        if index == total or index % max(1, total // 12) == 0:
                            progress = 25 + int((index / total) * 60)
                            self._generation_update(progress=progress)

                    selected_by_id = {int(item.get("id") or 0): item for item in selected}
                    selected = [selected_by_id[key] for key in sorted(selected_by_id)]
                    self._generation_update(progress=88, log=f"Filtros aplicados: {len(selected)} produto(s) selecionado(s).")

                    headers = [
                        "ID",
                        "Tipo",
                        "Nome",
                        "Slug",
                        "URL",
                        "Status",
                        "Metadado: pt_versao",
                        "Metadado: site_oficial",
                        "Categorias",
                    ]
                    rows = []
                    for product in selected:
                        names = [str(item.get("name") or "") for item in product.get("categories", []) or []]
                        rows.append(
                            {
                                "ID": product.get("id", ""),
                                "Tipo": product.get("type", ""),
                                "Nome": product.get("name", ""),
                                "Slug": product.get("slug", ""),
                                "URL": product.get("permalink", ""),
                                "Status": product.get("status", ""),
                                "Metadado: pt_versao": self._meta(product, "pt_versao"),
                                "Metadado: site_oficial": self._meta(product, "site_oficial"),
                                "Categorias": ", ".join(names),
                            }
                        )

                    buffer = io.StringIO(newline="")
                    writer = csv.DictWriter(buffer, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(rows)

                    if mode == "custom":
                        scope = "personalizado"
                    else:
                        scope = "-".join(key for key in self.KIND_ORDER if key in requested_kinds) or "produtos"
                    target = self.data_dir / "imports" / f"plugintema-{scope}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_suffix(".csv.tmp")
                    temporary.write_text(buffer.getvalue(), encoding="utf-8-sig")
                    os.replace(temporary, target)

                    catalog_id = target.relative_to(self.data_dir).as_posix()
                    requested_name = " ".join(str(payload.get("name") or "").split())
                    display_name = requested_name[:100] if requested_name else self._automatic_name(mode, requested_kinds)
                    names = self._load_names()
                    names[catalog_id] = display_name
                    self._save_names(names)

                    result = {
                        "catalog_id": catalog_id,
                        "display_name": display_name,
                        "items_count": len(rows),
                        "mode": mode,
                        "kinds": [key for key in self.KIND_ORDER if key in requested_kinds],
                    }
                    with self._lock:
                        self._generation = {
                            "status": "completed",
                            "progress": 100,
                            "logs": [
                                *self._generation.get("logs", []),
                                "Arquivo CSV gravado com sucesso.",
                                f"Catálogo: {display_name}",
                                f"{len(rows)} produto(s) exportado(s).",
                                f"Arquivo: {target.name}",
                            ],
                            "result": result,
                        }
                except Exception as error:
                    with self._lock:
                        self._generation = {
                            "status": "error",
                            "progress": int(self._generation.get("progress") or 0),
                            "logs": [*self._generation.get("logs", []), f"Falha: {error}"],
                            "result": None,
                        }

            self._worker = threading.Thread(target=work, name="plugintema-catalog-generation", daemon=True)
            self._worker.start()
            return {"ok": True, **self._generation}
