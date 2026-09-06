from app.store.repository import StoreRepository
from app.store.service import StoreService
from app.store.bundles import StoreBundleService
from app.store.wordpress import FixtureManualQueue
from app.store.woocommerce import FixtureStoreGateway


class Updates:
    def __init__(self):
        self.executed = []
        self.environment_calls = []

    def list(self, payload):
        return {"items": [{"job_id": "job-42", "woo_product_id": 42, "source_name": "UltraPackV2", "current_version": "1.0", "source_version": "2.0"}]}

    def resolve_manual_request(self, product_id):
        return {"state": "update_available", "message": "Atualização encontrada.", "item": self.list({})["items"][0]}

    def execute(self, job_id):
        self.executed.append(job_id)
        return {"ok": True}

    def environment(self):
        self.environment_calls.append("read")
        return {"checks": [{"key": "woocommerce", "label": "WooCommerce", "state": "ok", "value": "VALIDADO", "detail": "Leitura confirmada."}]}

    def verify_environment(self):
        self.environment_calls.append("check")
        return self.environment()


def service(tmp_path, gateway=None, queue=None, updates=None):
    return StoreService(tmp_path, updates or Updates(), repository=StoreRepository(tmp_path), gateway=gateway or FixtureStoreGateway(), queue=queue or FixtureManualQueue())


def test_store_environment_reuses_shared_canonical_check(tmp_path):
    updates = Updates()
    store = service(tmp_path, updates=updates)

    read = store.environment()
    checked = store.environment(check=True)

    assert read["checks"][0]["value"] == "VALIDADO"
    assert checked["checks"][0]["value"] == "VALIDADO"
    assert updates.environment_calls == ["read", "check", "read"]
    assert {item["key"] for item in checked["checks"]} == {"woocommerce", "store_write", "wordpress_monitor"}


def test_monitor_toggle_next_check_and_log_are_persistent(tmp_path):
    store = service(tmp_path)

    enabled = store.monitor_enable(True)["monitor"]
    assert enabled["enabled"] is True and enabled["next_check_at"]
    assert StoreRepository(tmp_path).monitor()["enabled"] is True

    store.monitor_enable(False)
    assert StoreRepository(tmp_path).monitor()["enabled"] is False
    restarted = store.monitor_enable(True)["monitor"]
    assert restarted["enabled"] is True
    assert store.monitor_service.snapshot()["worker_alive"] is True
    store.monitor_enable(False)


def test_monitor_current_request_is_cleared_but_history_is_preserved(tmp_path):
    class Queue(FixtureManualQueue):
        def pending(self):
            return [{"request_id": "req-1", "product_id": 42, "product_name": "Produto monitorado"}]

    updates = Updates()
    store = service(tmp_path, queue=Queue(), updates=updates)

    result = store.monitor_run()
    monitor = result["monitor"]

    assert result["ok"] is True and updates.executed == ["job-42"]
    assert monitor["current_product"] == "" and monitor["woo_product_id"] == 0 and monitor["request_state"] == ""
    assert monitor["history"][0]["product"] == "Produto monitorado"
    assert monitor["history"][0]["woo_product_id"] == 42
    assert monitor["logs"] and all(line.startswith("[") for line in monitor["logs"])


def test_pricing_catalog_loads_real_variations_packs_and_plans(tmp_path):
    gateway = FixtureStoreGateway()
    gateway._products.append({"id": 300, "name": "Plano Ouro", "type": "simple", "status": "publish", "categories": [{"id": 4, "name": "Planos"}], "short_description": "Plano", "images": [{"id": 3}], "meta_data": [], "regular_price": "399.00", "sale_price": "349.00"})
    store = service(tmp_path, gateway=gateway)

    catalog = store.pricing_catalog()

    assert catalog["individual"]["total"] == 24
    assert catalog["individual"]["sampled_products"] == {"plugin": 6, "theme": 6}
    assert catalog["individual"]["available_products"] == {"plugin": 8, "theme": 7}
    assert {item["period"] for item in catalog["individual"]["items"]} == {"annual", "lifetime"}
    assert catalog["packs"]["items"][0]["product_id"] == 200
    assert catalog["plans"]["items"][0]["product_id"] == 300
    assert catalog["plans"]["items"][0]["regular_price"] == "399.00"


def test_plan_price_write_uses_real_group_and_explicit_confirmation():
    gateway = FixtureStoreGateway()
    gateway._products.append({"id": 300, "name": "Plano Ouro", "type": "simple", "status": "publish", "categories": [{"id": 4, "name": "Planos"}], "short_description": "Plano", "images": [{"id": 3}], "meta_data": [], "regular_price": "399.00", "sale_price": "349.00"})
    pricing = StoreBundleService(gateway)
    payload = {"product_id": 300, "price_group": "plan", "regular_price": "409", "sale_price": "359"}

    preview = pricing.preview(payload)
    assert preview["price_group"] == "plan" and preview["status"] == "change"
    try:
        pricing.apply(payload, True)
    except ValueError as error:
        from app.store.pricing import confirmation_token
        assert "ALTERAR PRECO" in confirmation_token(str(error))
    else:
        raise AssertionError("Plano foi escrito sem confirmação explícita")
    result = pricing.apply({**payload, "confirmation": "ALTERAR PRECO"}, True)
    assert result["updated"] is True and gateway.writes[-1][0] == 300


def test_variable_subscription_plan_loads_and_updates_its_variations(tmp_path):
    gateway = FixtureStoreGateway()
    gateway._products.append({"id": 301, "name": "Clube", "type": "variable-subscription", "status": "publish", "categories": [{"id": 4, "name": "Plano"}], "short_description": "Plano", "images": [{"id": 3}], "meta_data": [], "regular_price": "", "sale_price": ""})
    pricing = StoreBundleService(gateway)
    listed = pricing.list(gateway.products(), "plan")
    payload = {"product_id": 301, "price_group": "plan", "variations": [{"id": 3011, "regular_price": "109", "sale_price": "89"}, {"id": 3012, "regular_price": "209", "sale_price": "189"}], "confirmation": "ALTERAR PRECO"}

    assert len(listed) == 1 and len(listed[0]["variations"]) == 2
    try:
        pricing.preview({"product_id": 301, "price_group": "plan", "regular_price": "999", "sale_price": ""})
    except ValueError as error:
        assert "variações" in str(error)
    else:
        raise AssertionError("Plano variável aceitou escrita insegura no preço vazio do parent")
    preview = pricing.preview(payload)
    assert len(preview["variation_changes"]) == 2 and preview["status"] == "change"
    result = pricing.apply(payload, True)
    assert result["changed"] == 2
    assert gateway.writes[-1][0] == 301 and isinstance(gateway.writes[-1][1], list)

    store = service(tmp_path, gateway=gateway)
    assert len(store.product(301)["variations"]) == 2


def test_quality_search_field_category_and_pagination_are_server_side(tmp_path):
    store = service(tmp_path)

    by_id = store.quality_products({"query": "101"})
    missing_description = store.quality_products({"field": "short_description"})
    generic_categories = store.quality_products({"field": "categories"})
    plugins = store.quality_products({"category": "Plugins", "page_size": 3, "page": 2})
    complete = store.quality_products({"status": "complete"})

    assert by_id["total"] == 1 and by_id["items"][0]["product_id"] == 101
    assert {item["product_id"] for item in missing_description["items"]} == {101, 104}
    assert generic_categories["total"] == 15
    assert plugins["total"] == 8 and plugins["page"] == 2 and len(plugins["items"]) == 3
    assert all(not item["problems"] for item in complete["items"])


def test_quality_rows_expose_real_categories_and_audit_fields(tmp_path):
    row = service(tmp_path).quality_products({"query": "102"})["items"][0]

    assert row["categories"] == ["Temas"]
    assert row["version"] == "1.0"
    assert row["developer"] == "E2E"
    assert row["official_url"] == "https://example.test"
    assert "missing_categories" in row["problem_codes"]
