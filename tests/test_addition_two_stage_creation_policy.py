from __future__ import annotations

from pathlib import Path

import app.addition_two_stage_creation_policy as policy


def _job(**changes):
    base = {
        "job_id": "add-test",
        "kind": "theme",
        "title": "Produto Teste",
        "source_name": "Produto Teste",
        "annual_regular": "",
        "annual_sale": "",
        "lifetime_regular": "",
        "lifetime_sale": "",
        "zip_path": "",
        "woo_product_id": 0,
        "image_path": "",
        "media_id": 0,
        "state": "content_ready",
    }
    base.update(changes)
    return base


def test_default_prices_follow_product_kind(monkeypatch) -> None:
    current = _job()
    captured = {}

    monkeypatch.setattr(policy.additions, "_row", lambda _job_id: dict(current))

    def fake_update(_job_id, **values):
        captured.update(values)
        current.update(values)
        return dict(current)

    monkeypatch.setattr(policy.additions, "_update", fake_update)
    monkeypatch.setattr(
        policy,
        "_price_defaults_for_kind",
        lambda kind: (
            {
                "annual_regular": "39.90",
                "annual_sale": "29.90",
                "lifetime_regular": "99.90",
                "lifetime_sale": "79.90",
            },
            {"id": 123, "name": "Tema Referência"},
        ),
    )
    monkeypatch.setattr(policy.one_click, "_emit", lambda *_args, **_kwargs: None)

    result = policy._ensure_default_prices("add-test")

    assert result["annual_regular"] == "39.90"
    assert result["lifetime_regular"] == "99.90"
    assert captured["annual_sale"] == "29.90"


def test_create_draft_bypasses_old_image_requirement(monkeypatch) -> None:
    current = _job(woo_product_id=0)
    calls = []

    monkeypatch.setattr(policy.additions, "_row", lambda _job_id: dict(current))
    monkeypatch.setattr(policy.one_click, "_emit", lambda *_args, **_kwargs: None)

    def fake_create(job_id: str, confirmation: str):
        calls.append((job_id, confirmation))
        return {"job": _job(woo_product_id=456, state="draft_created")}

    monkeypatch.setattr(policy.cdp, "_ORIGINAL_CREATE_DRAFT", fake_create)

    result = policy._create_draft_without_image("add-test")

    assert result["woo_product_id"] == 456
    assert calls == [("add-test", "CRIAR RASCUNHO")]


def test_missing_reference_builds_attachment_free_image_prompt(monkeypatch, tmp_path: Path) -> None:
    current = _job(woo_product_id=456)
    missing = tmp_path / "exemplo tema.webp"

    monkeypatch.setattr(policy.creative, "_reference_path", lambda _job: missing)
    monkeypatch.setattr(policy.creative, "_attach_reference", lambda *_args, **_kwargs: False)

    reference, attached, prompt = policy._prepare_image_request(object(), current, "add-test")

    assert reference == missing
    assert attached is False
    assert "não há mockup local anexado" in prompt.lower()
    assert "referência visual obrigatória" not in prompt.lower()
    assert "use o arquivo anexado" not in prompt.lower()


def test_two_stage_run_orders_store_before_image(monkeypatch) -> None:
    current = _job()
    order = []

    monkeypatch.setattr(policy.additions, "_row", lambda _job_id: dict(current))
    monkeypatch.setattr(
        policy.additions,
        "_update",
        lambda _job_id, **values: current.update(values) or dict(current),
    )
    monkeypatch.setattr(policy.one_click, "_emit", lambda *_args, **_kwargs: None)

    monkeypatch.setattr(policy, "_ensure_text_content", lambda _job_id: order.append("content"))
    monkeypatch.setattr(policy, "_ensure_default_prices", lambda _job_id: order.append("prices") or dict(current))
    monkeypatch.setattr(policy, "_ensure_zip", lambda _job_id, _manager: order.append("zip") or dict(current))
    monkeypatch.setattr(policy, "_create_draft_without_image", lambda _job_id: order.append("draft") or dict(current))
    monkeypatch.setattr(policy, "_run_image_automation", lambda _job_id: order.append("image"))
    monkeypatch.setattr(policy, "_publish_product", lambda _job_id: order.append("publish") or dict(current))

    policy._run_two_stage("add-test", object())

    assert order == ["content", "prices", "zip", "draft", "image", "publish"]
    assert order.index("draft") < order.index("image")
