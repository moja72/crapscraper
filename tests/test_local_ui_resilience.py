from pathlib import Path

import app.local_ui_resilience_policy as resilience


def test_disconnect_errors_are_classified_as_normal_client_disconnects():
    assert resilience._is_client_disconnect(ConnectionAbortedError(10053, "aborted"))
    assert resilience._is_client_disconnect(ConnectionResetError(10054, "reset"))
    assert resilience._is_client_disconnect(BrokenPipeError(32, "broken pipe"))
    assert not resilience._is_client_disconnect(RuntimeError("application failure"))


def test_server_guard_prevents_route_error_handler_from_writing_twice(monkeypatch):
    writes = {"count": 0}

    class BaseHandler:
        def __init__(self, *_args, **_kwargs):
            self.close_connection = False

        def _send_bytes(self, *_args, **_kwargs):
            writes["count"] += 1
            raise ConnectionAbortedError(10053, "aborted")

        def _send_empty(self, *_args, **_kwargs):
            raise BrokenPipeError(32, "broken pipe")

        def _send_json(self, payload, code=200):
            return self._send_bytes((str(payload) * 1000).encode("utf-8"), code=code)

        def do_GET(self):
            try:
                self._send_json({"ok": True, "products": ["item"] * 1000})
            except Exception:
                # Reproduz o padrão antigo de web.py: o erro do primeiro write
                # entrava no except e tentava enviar um JSON 500 no mesmo socket.
                self._send_json({"ok": False, "message": "erro"}, code=500)

        def do_POST(self):
            return self.do_GET()

        def do_OPTIONS(self):
            return self._send_empty()

        def finish(self):
            return None

    class FakeServer:
        def __init__(self, _address, handler_class, *_args, **_kwargs):
            self.handler_class = handler_class

    monkeypatch.setattr(resilience, "_BASE_SERVER", FakeServer)
    server = resilience._server_factory(("127.0.0.1", 0), BaseHandler)
    handler = server.handler_class()

    assert handler.do_GET() is None
    assert handler.close_connection is True
    assert writes["count"] == 1


def test_pack_reads_are_short_cached_and_invalidated_after_write(monkeypatch):
    calls = {"reads": 0, "writes": 0}

    def fake_list(_woo):
        calls["reads"] += 1
        return [{"product_id": 10, "product_name": "Pack"}]

    def fake_update(_woo, payload):
        calls["writes"] += 1
        return {"ok": True, "product": {"product_id": payload["product_id"]}}

    monkeypatch.setattr(resilience, "_BASE_PACK_LIST", fake_list)
    monkeypatch.setattr(resilience, "_BASE_PACK_UPDATE", fake_update)
    resilience._invalidate_pack_cache()

    first = resilience._cached_pack_list(object())
    second = resilience._cached_pack_list(object())

    assert first == second
    assert calls["reads"] == 1

    resilience._cached_pack_update(object(), {"product_id": 10})
    resilience._cached_pack_list(object())

    assert calls == {"reads": 2, "writes": 1}


def test_frontend_guard_defers_hidden_store_and_coalesces_pack_gets():
    source = Path("app/static/frontend_request_resilience.js").read_text(encoding="utf-8")

    assert 'PACK_PATH = "/loja/pacotes/precos"' in source
    assert "if (!storeVisible())" in source
    assert "deferred: true" in source
    assert "if (!packRequest)" in source
    assert "AbortController" in source
    assert "PACK_TIMEOUT_MS" in source
    assert ".finally(() =>" in source
    assert 'setAttribute("aria-busy", "false")' in source


def test_resilience_policy_is_installed_after_addition_diagnostics():
    source = Path("app/addition_operational_legacy_suppression_policy.py").read_text(encoding="utf-8")

    assert "install_addition_tab_diagnostics_policy()" in source
    assert "install_local_ui_resilience_policy()" in source
    assert source.index("install_addition_tab_diagnostics_policy()") < source.rindex("install_local_ui_resilience_policy()")
