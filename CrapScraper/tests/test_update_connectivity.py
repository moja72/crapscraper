from __future__ import annotations

import requests
import pytest

from app.updates.adapters import WooCommerceConnectivityError, WooCommerceGateway
from app.updates.executor import UpdateExecutor
from app.updates.logging import safe_message
from app.updates.repository import UpdateRepository
from app.updates.service import UpdateService
from tests.update_fakes import FakeInstaller, FakeSource, approval


class Response:
    status_code = 200
    url = "https://example.test/wp-json/wc/v3/products"
    history: list = []
    headers = {"Content-Type": "application/json"}
    content = b"[]"
    text = "[]"

    def json(self):
        return []


def configured_gateway(monkeypatch, *, network_delays=(0.0, 0.0)) -> WooCommerceGateway:
    monkeypatch.setenv("SCRAPER_WP_BASE_URL", "https://example.test")
    monkeypatch.setenv("SCRAPER_WC_CONSUMER_KEY", "ck_test_public")
    monkeypatch.setenv("SCRAPER_WC_CONSUMER_SECRET", "cs_test_private")
    return WooCommerceGateway(network_delays=network_delays, sleeper=lambda _delay: None)


def dns_error(*, include_secret: bool = False) -> requests.ConnectionError:
    suffix = "?consumer_secret=cs_test_private" if include_secret else ""
    return requests.ConnectionError(
        "HTTPSConnectionPool(host='example.test', port=443): Max retries exceeded "
        f"with url: /wp-json/wc/v3/products{suffix} (Caused by NameResolutionError("
        "Failed to resolve 'example.test' ([Errno 11001] getaddrinfo failed)))"
    )


def test_gateway_retries_one_transient_dns_failure_and_recovers(monkeypatch) -> None:
    woo = configured_gateway(monkeypatch)
    calls = []
    responses = iter((dns_error(), Response()))

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        value = next(responses)
        if isinstance(value, Exception):
            raise value
        return value

    woo.session.request = request
    result = woo.check_connection()

    assert result["ok"] is True and result["recovered"] is True and result["attempts"] == 2
    assert len(calls) == 2
    assert calls[0][2]["auth"] == ("ck_test_public", "cs_test_private")
    assert calls[0][2]["params"] == {"per_page": 1, "page": 1}


def test_gateway_persistent_dns_failure_is_structured_and_sanitized(monkeypatch) -> None:
    woo = configured_gateway(monkeypatch)
    calls = 0

    def request(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise dns_error(include_secret=True)

    woo.session.request = request
    with pytest.raises(WooCommerceConnectivityError) as raised:
        woo.check_connection()

    error = raised.value
    assert calls == 2 and error.error_type == "dns_resolution" and error.attempts == 2
    assert error.host == "example.test" and error.diagnosis == "Não foi possível resolver example.test."
    assert "cs_test_private" not in error.original_exception
    assert "cs_test_private" not in safe_message(error)


def test_non_dns_put_connection_failure_is_not_retried(monkeypatch) -> None:
    woo = configured_gateway(monkeypatch, network_delays=(0.0, 0.0, 0.0))
    calls = 0

    def request(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise requests.ConnectionError("connection reset before response")

    woo.session.request = request
    with pytest.raises(WooCommerceConnectivityError) as raised:
        woo._request("PUT", "/products/89824", json={"meta_data": []})
    assert calls == 1 and raised.value.error_type == "connection"


def test_executor_persists_short_dns_error_with_technical_details(tmp_path) -> None:
    class Woo:
        def get_product(self, _product_id):
            raise WooCommerceConnectivityError(
                method="GET",
                endpoint="/products/89824",
                host="plugintema.com.br",
                error_type="dns_resolution",
                attempts=3,
                original_exception=dns_error(include_secret=True),
            )

    repo = UpdateRepository(tmp_path)
    item = approval("dns", kind="UltraPackV2", woo=89824)
    repo.materialize([item])
    job = repo.list(page_size=5)["items"][0]
    result = UpdateExecutor(
        repo,
        woo=Woo(),
        installer=FakeInstaller(),
        enabled=True,
        allowed_product_ids=frozenset(),
    ).execute(job["job_id"])

    error = result["error"]
    assert error["message"] == "Falha de conexão com WooCommerce."
    assert error["diagnosis"] == "Não foi possível resolver plugintema.com.br."
    assert error["code"] == "dns_resolution" and error["details"]["attempts"] == 3
    assert "cs_test_private" not in str(error)


def test_failed_woo_preflight_disables_write_and_blocks_new_attempt(tmp_path, monkeypatch) -> None:
    class Woo:
        recovered = False
        base = "https://plugintema.com.br/wp-json/wc/v3"
        auth = ("configured-key", "configured-secret")

        def check_connection(self):
            if not self.recovered:
                raise WooCommerceConnectivityError(
                    method="GET",
                    endpoint="/products",
                    host="plugintema.com.br",
                    error_type="dns_resolution",
                    attempts=3,
                    original_exception=dns_error(),
                )
            return {"ok": True, "attempts": 1, "recovered": False}

    class Installer(FakeInstaller):
        def check(self):
            return {"ok": True, "message": "storage testado"}

    class Credits:
        def refresh(self, _site, _account):
            return {"ok": True, "authenticated": True, "credits": 50, "status": "success", "logs": []}

        def cached(self, _site, _account):
            return {"ok": True, "authenticated": True, "credits": 50, "status": "success", "logs": []}

    monkeypatch.setattr("app.updates.service.decisions.list_approved_updates", lambda: [])
    monkeypatch.setattr("app.updates.service.profile_diagnostic", lambda _account: {"configured": True})
    woo = Woo()
    repo = UpdateRepository(tmp_path)
    executor = UpdateExecutor(repo, woo=woo, installer=Installer(), enabled=True, allowed_product_ids=frozenset())
    service = UpdateService(tmp_path, repository=repo, executor=executor, credits=Credits())

    failed = service.verify_environment()
    checks = {item["key"]: item for item in failed["checks"]}
    assert checks["woocommerce"]["value"] == "CONFIGURADO / NÃO VALIDADO"
    assert checks["woocommerce"]["detail"] == "Não foi possível resolver plugintema.com.br."
    assert checks["woo_write"]["value"] == "DESABILITADA"
    with pytest.raises(RuntimeError, match="Pré-requisito WooCommerce indisponível"):
        service.execute("job-that-must-not-start")

    woo.recovered = True
    recovered = service.verify_environment()
    recovered_checks = {item["key"]: item for item in recovered["checks"]}
    assert recovered_checks["woocommerce"]["value"] == "VALIDADO"
    assert recovered_checks["woo_write"]["value"] == "HABILITADA"
