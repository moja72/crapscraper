from __future__ import annotations

import app.addition_server_integration_fix as policy


def test_unknown_addition_route_delegates_without_consuming_body(monkeypatch):
    class BaseHandler:
        def __init__(self):
            self.read_count = 0
            self.delegated = False

        def _request_path(self):
            return "/adicoes/automatico"

        def _read_json_body(self):
            self.read_count += 1
            return {"job_id": "x"}

        def do_POST(self):
            self.delegated = True

    monkeypatch.setattr(policy.additions, "_manager_from_handler", lambda _handler: None)
    monkeypatch.setattr(
        policy,
        "_BASE_SERVER",
        lambda _address, handler_class, *_args, **_kwargs: handler_class,
    )

    WrappedHandler = policy._server_factory(("127.0.0.1", 0), BaseHandler)
    handler = WrappedHandler()
    handler.do_POST()

    assert handler.delegated is True
    assert handler.read_count == 0


def test_automatic_route_is_reserved_for_next_policy_layer():
    assert "/adicoes/automatico" not in policy._POST_ROUTES
