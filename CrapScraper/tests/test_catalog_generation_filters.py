import csv
import time

from app.catalogs.service import CatalogService


class FakeGateway:
    def __init__(self):
        self.rows = [
            {"id": 1, "name": "Plugin A", "slug": "plugin-a", "permalink": "https://x/1", "status": "publish", "type": "simple", "categories": [{"id": 10, "name": "Plugins"}], "meta_data": [{"key": "pt_versao", "value": "1.0"}]},
            {"id": 2, "name": "Tema B", "slug": "tema-b", "permalink": "https://x/2", "status": "publish", "type": "simple", "categories": [{"id": 20, "name": "Temas"}], "meta_data": []},
            {"id": 3, "name": "Template C", "slug": "template-c", "permalink": "https://x/3", "status": "publish", "type": "simple", "categories": [{"id": 30, "name": "Templates"}], "meta_data": []},
            {"id": 4, "name": "Pack D", "slug": "pack-d", "permalink": "https://x/4", "status": "publish", "type": "bundle", "categories": [{"id": 40, "name": "Packs"}], "meta_data": []},
            {"id": 5, "name": "Assinatura E", "slug": "assinatura-e", "permalink": "https://x/5", "status": "publish", "type": "subscription", "categories": [{"id": 50, "name": "Assinaturas"}], "meta_data": [{"key": "pt_versao", "value": "5.0"}]},
            {"id": 6, "name": "Plugin Rascunho", "slug": "plugin-draft", "permalink": "https://x/6", "status": "draft", "type": "simple", "categories": [{"id": 10, "name": "Plugins"}], "meta_data": []},
        ]

    def products(self, **filters):
        rows = list(self.rows)
        status = filters.get("status")
        if status:
            rows = [row for row in rows if row["status"] == status]
        search = str(filters.get("search") or "").casefold()
        if search:
            rows = [row for row in rows if search in f"{row['id']} {row['name']} {row['slug']}".casefold()]
        return rows

    def product(self, product_id):
        return next(row for row in self.rows if row["id"] == int(product_id))

    def categories(self):
        return [
            {"id": 10, "name": "Plugins", "count": 2},
            {"id": 20, "name": "Temas", "count": 1},
            {"id": 30, "name": "Templates", "count": 1},
            {"id": 40, "name": "Packs", "count": 1},
            {"id": 50, "name": "Assinaturas", "count": 1},
        ]


def wait(service):
    for _ in range(100):
        state = service.generation_status()
        if state["status"] != "running":
            return state
        time.sleep(0.01)
    raise AssertionError("generation did not finish")


def read_ids(tmp_path, catalog_id):
    with (tmp_path / catalog_id).open("r", encoding="utf-8-sig", newline="") as handle:
        return [int(row["ID"]) for row in csv.DictReader(handle)]


def test_preset_supports_all_catalog_types(tmp_path):
    service = CatalogService(tmp_path, FakeGateway())
    service.generate_plugintema({"mode": "preset", "kinds": ["template", "pack", "plan"]})
    state = wait(service)
    assert state["status"] == "completed"
    assert read_ids(tmp_path, state["result"]["catalog_id"]) == [3, 4, 5]
    assert "Templates" in state["result"]["display_name"]
    assert "Packs" in state["result"]["display_name"]
    assert "Assinatura" in state["result"]["display_name"]


def test_custom_filters_and_manual_includes(tmp_path):
    service = CatalogService(tmp_path, FakeGateway())
    service.generate_plugintema({
        "mode": "custom",
        "name": "Meu catálogo customizado",
        "custom": {
            "type": "plugin",
            "status": "publish",
            "category_ids": [10],
            "query": "Plugin",
            "specific_ids": "1",
            "version": "with",
            "include_ids": [3],
        },
    })
    state = wait(service)
    assert state["status"] == "completed"
    assert state["result"]["display_name"] == "Meu catálogo customizado"
    assert read_ids(tmp_path, state["result"]["catalog_id"]) == [1, 3]
    assert state["progress"] == 100
    assert any("Filtros aplicados" in line for line in state["logs"])


def test_generation_options_and_search(tmp_path):
    service = CatalogService(tmp_path, FakeGateway())
    options = service.generation_options()
    assert [item["id"] for item in options["kinds"]] == ["plugin", "theme", "template", "pack", "plan"]
    found = service.search_products({"query": "Template", "status": "publish", "type": "template"})
    assert [item["id"] for item in found["items"]] == [3]
