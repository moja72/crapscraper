from __future__ import annotations

from pathlib import Path

import app.addition_product_creative_policy as policy


def _job(kind: str = "plugin") -> dict[str, str]:
    return {
        "job_id": "add-test",
        "kind": kind,
        "source_name": "Produto Teste",
        "title": "Produto Teste",
    }


def test_prompt_prioritizes_short_description_shape(monkeypatch) -> None:
    monkeypatch.setattr(policy, "_BASE_PROMPT", lambda _job: "PROMPT BASE")

    prompt = policy._patched_prompt(_job("plugin"))

    assert "entre 400 e 500 caracteres" in prompt
    assert "alvo próximo de 450 caracteres" in prompt
    assert "Crie páginas profissionais com total liberdade visual" in prompt
    assert "Vitalício | Ilimitado | Atualizado" in prompt
    assert "Quicksand" in prompt
    assert "FUNDO TRANSPARENTE" in prompt
    assert "3 lados/faces visíveis" in prompt


def test_theme_prompt_uses_theme_reference_and_apple_monitor(monkeypatch) -> None:
    monkeypatch.setattr(policy, "_BASE_PROMPT", lambda _job: "PROMPT BASE")

    prompt = policy._patched_prompt(_job("theme"))

    assert "exemplo tema.webp" in prompt
    assert "monitor Apple" in prompt
    assert "computador e de um celular" in prompt
    assert "FUNDO TRANSPARENTE" in prompt


def test_reference_file_depends_on_product_kind() -> None:
    assert policy._reference_path(_job("plugin")).name == "exemplo plugin.webp"
    assert policy._reference_path(_job("theme")).name == "exemplo tema.webp"


def test_fallback_image_prompt_keeps_plugin_requirements() -> None:
    prompt = policy._image_only_prompt(_job("plugin"))

    assert "SOMENTE a imagem final" in prompt
    assert "exemplo plugin.webp" in prompt
    assert "Vitalício | Ilimitado | Atualizado" in prompt
    assert "Quicksand" in prompt
    assert "Fundo totalmente transparente" in prompt


def test_send_message_attaches_reference_and_rewrites_image_prompt(monkeypatch, tmp_path: Path) -> None:
    reference = tmp_path / "exemplo plugin.webp"
    reference.write_bytes(b"fake")
    captured: dict[str, object] = {}

    monkeypatch.setattr(policy.additions, "_row", lambda _job_id: _job("plugin"))
    monkeypatch.setattr(policy, "_reference_path", lambda _job: reference)
    monkeypatch.setattr(
        policy,
        "_attach_reference",
        lambda _page, path, _job_id: captured.setdefault("attached", path) is not None,
    )

    def fake_send(_page, prompt: str, job_id: str):
        captured["prompt"] = prompt
        captured["job_id"] = job_id
        return 2, {"before"}

    monkeypatch.setattr(policy, "_BASE_SEND_MESSAGE", fake_send)

    result = policy._patched_send_message(
        object(),
        "Agora gere SOMENTE uma imagem de capa quadrada 1:1 para o produto Produto Teste.",
        "add-test",
    )

    assert result == (2, {"before"})
    assert captured["attached"] == reference
    assert "Vitalício | Ilimitado | Atualizado" in str(captured["prompt"])
    assert captured["job_id"] == "add-test"
