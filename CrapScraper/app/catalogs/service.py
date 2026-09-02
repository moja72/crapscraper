from __future__ import annotations

import csv
import io
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class CatalogService:
    """Leitura administrativa dos CSVs canônicos, sem I/O remoto."""

    def __init__(self, data_dir: Path, gateway: Any = None):
        self.data_dir = data_dir.resolve();self.gateway=gateway;self._generation={"status":"idle","progress":0,"logs":[],"result":None};self._lock=threading.RLock();self._worker=None

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
        relative = path.relative_to(root).as_posix();parts = relative.split("/")
        context = parts[:5] if len(parts) >= 6 and parts[0] == "slots" and parts[-1] == "catalog.csv" else []
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            count = max(0, sum(1 for _ in stream) - 1)
        return {"id":relative,"name":path.name,"label":relative,"items_count":count,"size":path.stat().st_size,"updated_at":path.stat().st_mtime,"available":True,"kind":"context" if context else "import","slot_name":context[1] if context else "","site_key":context[2] if context else "","item_type_key":context[3] if context else "","account_key":context[4] if context else ""}

    def _metadata_with_name(self, path: Path, names: dict[str, str] | None = None) -> dict[str, Any]:
        row = self._metadata(path, self.data_dir)
        names = names if names is not None else self._load_names()
        display_name = str(names.get(row["id"]) or "").strip()
        row["display_name"] = display_name
        if display_name:
            row["label"] = display_name
        return row

    def list(self, query: dict[str, Any] | None = None) -> dict[str, Any]:
        query=query or {};needle=str(query.get("query") or "").strip().casefold();page=max(1,int(query.get("page") or 1));page_size=min(100,max(1,int(query.get("page_size") or 20)));names=self._load_names()
        rows=[self._metadata_with_name(path,names) for path in self.data_dir.rglob("*.csv") if "update_queues" not in path.relative_to(self.data_dir).parts]
        if needle:rows=[row for row in rows if needle in " ".join(str(v) for v in row.values()).casefold()]
        rows.sort(key=lambda row:row["updated_at"],reverse=True);total=len(rows);pages=max(1,(total+page_size-1)//page_size);page=min(page,pages);start=(page-1)*page_size
        return {"ok":True,"rows":rows[start:start+page_size],"pagination":{"page":page,"page_size":page_size,"total_rows":total,"total_pages":pages}}

    def preview(self, query: dict[str, Any]) -> dict[str, Any]:
        path=self._resolve(str(query.get("catalog_id") or ""));needle=str(query.get("query") or "").strip().casefold();page=max(1,int(query.get("page") or 1));page_size=min(100,max(1,int(query.get("page_size") or 30)))
        with path.open("r",encoding="utf-8-sig",newline="") as stream:
            reader=csv.DictReader(stream);headers=list(reader.fieldnames or []);rows=[dict(row) for row in reader]
        if needle:rows=[row for row in rows if needle in " ".join(str(v) for v in row.values()).casefold()]
        total=len(rows);pages=max(1,(total+page_size-1)//page_size);page=min(page,pages);start=(page-1)*page_size
        return {"ok":True,"catalog":self._metadata_with_name(path),"headers":headers,"rows":rows[start:start+page_size],"pagination":{"page":page,"page_size":page_size,"total_rows":total,"total_pages":pages}}

    def download(self, catalog_id: str) -> tuple[str, bytes]:
        path=self._resolve(catalog_id);return path.name,path.read_bytes()

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
    def _meta(product: dict[str,Any], key: str) -> str:
        return next((str(item.get("value") or "") for item in product.get("meta_data",[]) if item.get("key")==key),"")

    def generation_status(self) -> dict[str,Any]:
        with self._lock:return {"ok":True,**self._generation}

    def generate_plugintema(self, payload: dict[str,Any] | None = None) -> dict[str,Any]:
        payload=payload or {}
        with self._lock:
            if self._worker and self._worker.is_alive():return {"ok":True,**self._generation}
            self._generation={"status":"running","progress":0,"logs":["Iniciando leitura WooCommerce somente leitura."],"result":None}
            def work():
                try:
                    if self.gateway is None:raise RuntimeError("WooCommerce não configurado para geração.")
                    products=list(self.gateway.products(status="publish",_fields="id,name,slug,permalink,status,type,categories,meta_data"));kinds={str(x) for x in payload.get("kinds",["plugin","theme"])};rows=[]
                    for product in products:
                        names=[str(x.get("name") or "") for x in product.get("categories",[])];folded=" ".join(names).casefold();kind="theme" if "tema" in folded or "theme" in folded else "plugin" if "plugin" in folded else "other"
                        if kind not in kinds:continue
                        rows.append({"ID":product.get("id",""),"Tipo":product.get("type",""),"Nome":product.get("name",""),"Slug":product.get("slug",""),"URL":product.get("permalink",""),"Status":product.get("status",""),"Metadado: pt_versao":self._meta(product,"pt_versao"),"Metadado: site_oficial":self._meta(product,"site_oficial"),"Categorias":", ".join(names)})
                    headers=["ID","Tipo","Nome","Slug","URL","Status","Metadado: pt_versao","Metadado: site_oficial","Categorias"];buffer=io.StringIO(newline="");writer=csv.DictWriter(buffer,fieldnames=headers);writer.writeheader();writer.writerows(rows);target=self.data_dir/"imports"/f"plugintema-products-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv";target.parent.mkdir(parents=True,exist_ok=True);temporary=target.with_suffix(".csv.tmp");temporary.write_text(buffer.getvalue(),encoding="utf-8-sig");os.replace(temporary,target)
                    with self._lock:self._generation={"status":"completed","progress":100,"logs":["Leitura WooCommerce concluída.",f"{len(rows)} produto(s) exportado(s).",f"Arquivo: {target.name}"],"result":{"catalog_id":target.relative_to(self.data_dir).as_posix(),"items_count":len(rows)}}
                except Exception as error:
                    with self._lock:self._generation={"status":"error","progress":0,"logs":[*self._generation["logs"],str(error)],"result":None}
            self._worker=threading.Thread(target=work,name="plugintema-catalog-generation",daemon=True);self._worker.start();return {"ok":True,**self._generation}
