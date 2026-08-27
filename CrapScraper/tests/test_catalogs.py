from __future__ import annotations

import csv
from pathlib import Path

import pytest
import time

from app.catalogs import CatalogService


def write_csv(path: Path, count: int = 5) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=["nome","versao"]);writer.writeheader();writer.writerows({"nome":f"Produto {index}","versao":str(index)} for index in range(count))


def test_catalog_list_search_pagination_context_preview_and_download(tmp_path: Path):
    context=tmp_path/"slots/default/ultrapackv2/plugin/account/catalog.csv";write_csv(context,5);write_csv(tmp_path/"imports/plugintema-products.csv",2)
    service=CatalogService(tmp_path);first=service.list({"page":1,"page_size":1})
    assert first["pagination"]=={"page":1,"page_size":1,"total_rows":2,"total_pages":2}
    found=service.list({"query":"ultrapackv2","page_size":20})["rows"][0]
    assert found["kind"]=="context" and found["items_count"]==5 and found["slot_name"]=="default"
    preview=service.preview({"catalog_id":found["id"],"query":"Produto 3","page":1,"page_size":2})
    assert preview["headers"]==["nome","versao"] and preview["rows"][0]["nome"]=="Produto 3"
    filename,content=service.download(found["id"]);assert filename=="catalog.csv" and b"Produto 4" in content


def test_catalog_path_cannot_escape_data_directory(tmp_path: Path):
    service=CatalogService(tmp_path)
    with pytest.raises(ValueError):service.download("../outside.csv")


def test_plugintema_generation_is_async_observable_and_read_only(tmp_path: Path):
    class Gateway:
        def __init__(self):self.calls=[]
        def products(self,**filters):
            self.calls.append(filters);return [{"id":10,"name":"Alpha","slug":"alpha","permalink":"https://shop.test/alpha","status":"publish","type":"variable","categories":[{"name":"Plugins"}],"meta_data":[{"key":"pt_versao","value":"2.0"}]}]
    gateway=Gateway();service=CatalogService(tmp_path,gateway);started=service.generate_plugintema({"kinds":["plugin"]});assert started["status"]=="running"
    for _ in range(100):
        state=service.generation_status()
        if state["status"]!="running":break
        time.sleep(.01)
    assert state["status"]=="completed" and state["result"]["items_count"]==1
    assert gateway.calls==[{"status":"publish","_fields":"id,name,slug,permalink,status,type,categories,meta_data"}]
    preview=service.preview({"catalog_id":state["result"]["catalog_id"]});assert preview["rows"][0]["Nome"]=="Alpha"
