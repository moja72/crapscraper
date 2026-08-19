from __future__ import annotations

from pathlib import Path

import app.addition_product_creative_policy as policy


def _job(kind: str = "plugin") -> dict[str, str]:
    return {
        "job_id": "add-test",
        "kind": kind,
        "source_name": "Produto Teste",
        "title": "Produto Teste",
        "source_product_url": "https://example.test/source",
        "source_official_url": "https://example.test/official",
    }


def test_content_prompt_is_text_only_and_keeps_short_description_rule(monkeypatch) -> None:
    base = (
        "BASE\n"
        "7. Gere também uma imagem quadrada 1:1, limpa, profissional, sem selos de preço, "
        "sem texto pequeno ilegível e sem copiar identidade visual protegida de terceiros. "
        "A imagem deve funcionar como capa de produto em uma loja de plugins e temas WordPress.\n"
        "EXECUÇÃO AUTOMÁTICA\n"
        "Depois do conteúdo textual, gere também a imagem principal quadrada 1:1 solicitada para o produto."
    )
    monkeypatch.setattr(policy, "_BASE_PROMPT", lambda _job: base)

    prompt = policy._patched_prompt(_job("plugin"))

    assert "entre 400 e 500 caracteres" in prompt
    assert "alvo próximo de 450 caracteres" in prompt
    assert "Crie páginas profissionais com total liberdade visual" in prompt
    assert "ETAPA ATUAL: SOMENTE CONTEÚDO" in prompt
    assert "NÃO gere imagem" in prompt
    assert "Gere também uma imagem quadrada 1:1" not in prompt
    assert "Depois do conteúdo textual, gere também a imagem" not in prompt
    assert "Vitalício | Ilimitado | Atualizado" not in prompt


def test_theme_image_prompt_uses_reference_and_apple_monitor() -> None:
    prompt = policy._image_only_prompt(_job("theme"))

    assert "SOMENTE a imagem principal" in prompt
    assert "exemplo tema.webp" in prompt
    assert "monitor Apple" in prompt
    assert "computador e de um celular" in prompt
    assert "FUNDO TRANSPARENTE" in prompt
    assert "Página da fonte" in prompt


def test_plugin_image_prompt_keeps_box_requirements() -> None:
    prompt = policy._image_only_prompt(_job("plugin"))

    assert "exemplo plugin.webp" in prompt
    assert "Vitalício | Ilimitado | Atualizado" in prompt
    assert "Quicksand" in prompt
    assert "3 lados/faces visíveis" in prompt
    assert "Fundo totalmente transparente" in prompt


def test_reference_file_depends_on_product_kind() -> None:
    assert policy._reference_path(_job("plugin")).name == "exemplo plugin.webp"
    assert policy._reference_path(_job("theme")).name == "exemplo tema.webp"


class _FakeInput:
    def __init__(self, captured: dict[str, str]) -> None:
        self.captured = captured

    def set_input_files(self, path: str) -> None:
        self.captured["path"] = path


class _FakeInputs:
    def __init__(self, captured: dict[str, str]) -> None:
        self.input = _FakeInput(captured)

    def count(self) -> int:
        return 1

    def nth(self, _index: int) -> _FakeInput:
        return self.input


class _FakePage:
    def __init__(self, captured: dict[str, str]) -> None:
        self.captured = captured

    def locator(self, selector: str):
        if selector == "input[type='file']":
            return _FakeInputs(self.captured)
        raise AssertionError(selector)

    def wait_for_timeout(self, _milliseconds: int) -> None:
        return None


def test_attach_reference_uses_existing_file_input(monkeypatch, tmp_path: Path) -> None:
    reference = tmp_path / "exemplo plugin.webp"
    reference.write_bytes(b"fake")
    captured: dict[str, str] = {}

    monkeypatch.setattr(policy.one_click, "_emit", lambda *_args, **_kwargs: None)

    assert policy._attach_reference(_FakePage(captured), reference, "add-test") is True
    assert Path(captured["path"]) == reference


def test_missing_reference_stops_attachment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(policy.one_click, "_emit", lambda *_args, **_kwargs: None)
    missing = tmp_path / "exemplo tema.webp"

    assert policy._attach_reference(object(), missing, "add-test") is False
