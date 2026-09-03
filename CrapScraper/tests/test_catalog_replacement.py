import time

from app.catalogs import CatalogService


class FakeGateway:
    def __init__(self):
        self.rows = [
            {"id": 1, "name": "Plugin A", "slug": "plugin-a", "permalink": "https://x/1", "status": "publish", "type": "simple", "categories": [{"id": 10, "name": "Plugins"}], "meta_data": [{"key": "pt_versao", "value": "1.0"}]},
            {"id": 2, "name": "Tema B", "slug": "tema-b", "permalink": "https://x/2", "status": "publish", "type": "simple", "categories": [{"id": 20, "name": "Temas"}], "meta_data": []},
        ]

    def products(self, **filters):
        rows = list(self.rows)
        status = filters.get("status")
        if status:
            rows = [row for row in rows if row["status"] == status]
        return rows

    def product(self, product_id):
        return next(row for row in self.rows if row["id"] == int(product_id))

    def categories(self):
        return [
            {"id": 10, "name": "Plugins", "count": 1},
            {"id": 20, "name": "Temas", "count": 1},
        ]


def wait(service):
    for _ in range(300):
        state = service.generation_status()
        if state["status"] != "running":
            return state
        time.sleep(0.01)
    raise AssertionError("generation did not finish")


def plugin_tema_rows(service):
    return [
        row
        for row in service.list({"page_size": 100})["rows"]
        if "plugintema" in row["id"].lower() and "plugintheme" not in row["id"].lower()
    ]


def test_catalog_with_same_name_replaces_previous_file(tmp_path):
    service = CatalogService(tmp_path, FakeGateway())
    service.generate_plugintema({"mode": "preset", "name": "Tudo", "kinds": ["plugin"]})
    first = wait(service)
    first_id = first["result"]["catalog_id"]
    assert (tmp_path / first_id).is_file()

    time.sleep(1.05)
    service.generate_plugintema({"mode": "preset", "name": "Tudo", "kinds": ["plugin", "theme"]})
    second = wait(service)
    second_id = second["result"]["catalog_id"]

    assert second["status"] == "completed"
    assert second_id != first_id
    assert not (tmp_path / first_id).exists()
    assert (tmp_path / second_id).is_file()
    assert second["result"]["replaced_catalog_ids"] == [first_id]
    assert len(plugin_tema_rows(service)) == 1


def test_catalog_list_exposes_generation_config_for_update_button(tmp_path):
    service = CatalogService(tmp_path, FakeGateway())
    service.generate_plugintema({"mode": "preset", "name": "Plugins", "kinds": ["plugin"]})
    wait(service)
    row = plugin_tema_rows(service)[0]

    assert row["display_name"] == "Plugins"
    assert row["generation_config"]["mode"] == "preset"
    assert row["generation_config"]["kinds"] == ["plugin"]
    assert row["generation_config"]["name"] == "Plugins"
    assert row["generation_config"]["inferred"] is False


def test_rename_to_existing_name_keeps_only_renamed_catalog(tmp_path):
    service = CatalogService(tmp_path, FakeGateway())
    service.generate_plugintema({"mode": "preset", "name": "Plugins", "kinds": ["plugin"]})
    first = wait(service)
    time.sleep(1.05)
    service.generate_plugintema({"mode": "preset", "name": "Temas", "kinds": ["theme"]})
    second = wait(service)

    response = service.set_name({"catalog_id": second["result"]["catalog_id"], "name": "Plugins"})
    rows = plugin_tema_rows(service)

    assert len(rows) == 1
    assert rows[0]["id"] == second["result"]["catalog_id"]
    assert rows[0]["display_name"] == "Plugins"
    assert first["result"]["catalog_id"] in response["replaced_catalog_ids"]
