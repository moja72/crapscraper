from __future__ import annotations

from typing import Any


class CollectionRepository:
    @property
    def storage(self):
        from app.collection.legacy_core import storage
        return storage

    def slots(self) -> list[dict[str, Any]]: return self.storage.build_slots_public_list()
    def create_slot(self, name: str) -> str: return self.storage.create_slot(name)
    def select_slot(self, name: str) -> str: return self.storage.set_active_slot(name)
    def default_slot(self, name: str) -> str: return self.storage.set_default_slot(name)
    def delete_slot(self, name: str) -> tuple[bool, str]: return self.storage.delete_slot(name)
    def clear_slot(self, name: str) -> tuple[bool, str]: return self.storage.clear_slot_contents(name)
    def categories(self, context: Any) -> list[dict[str, Any]]: return self.storage.load_available_categories(context)
    def catalog(self, context: Any) -> list[dict[str, Any]]: return self.storage.load_catalog_items(context)
    def config(self, context: Any) -> dict[str, Any]: return self.storage.load_context_config(context)
    def progress(self, context: Any) -> dict[str, Any]: return self.storage.load_progress_data(context)
    def contexts(self, slot_name: str) -> list[dict[str, Any]]:
        root=self.storage.get_slot_dir(slot_name);rows=[]
        if not root.is_dir():return rows
        for site in root.iterdir():
            if not site.is_dir():continue
            for item_type in site.iterdir():
                if not item_type.is_dir():continue
                for account in item_type.iterdir():
                    if not account.is_dir():continue
                    context={"slot_name":slot_name,"site_key":site.name,"item_type_key":item_type.name,"account_key":account.name};catalog=self.storage.load_catalog_items(context);progress=self.storage.load_progress_data(context);paths=self.storage.build_context_paths(context,ensure=False);catalog_file=paths.output_csv_path
                    rows.append({**context,"items_count":len(catalog),"updated_at":catalog_file.stat().st_mtime if catalog_file.exists() else 0,"status":str(progress.get("status") or progress.get("meta",{}).get("status") or ""),"catalog_available":catalog_file.is_file(),"state_available":paths.status_txt_path.is_file(),"log_available":paths.last_logs_txt_path.is_file() or paths.runtime_log_path.is_file(),"catalog_id":catalog_file.relative_to(self.storage.get_data_dir()).as_posix() if catalog_file.is_file() else ""})
        return sorted(rows,key=lambda x:(x["site_key"],x["item_type_key"],x["account_key"]))

    def catalog_management(self) -> dict[str, Any]:
        slots=[];all_contexts=[]
        for slot in self.slots():
            rows=self.contexts(str(slot["name"]));all_contexts.extend(rows)
            slots.append({**slot,"label":"Padrão" if slot["name"]=="default" else slot["name"],"items_count":sum(int(row["items_count"]) for row in rows),"contexts_count":len(rows),"updated_at":max((float(row["updated_at"]) for row in rows),default=0)})
        return {"slots":slots,"contexts":all_contexts}

    def context_file(self, context: dict[str, str], kind: str) -> str:
        if kind == "state": return self.storage.load_status_text(context)
        if kind == "log": return self.storage.load_full_logs_text(context)
        raise ValueError("Tipo de prévia inválido.")
