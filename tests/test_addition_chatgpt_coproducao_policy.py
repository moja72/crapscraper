from __future__ import annotations

from pathlib import Path

import app.addition_chatgpt_coproducao_policy as policy


def test_uses_cs_automacao_project(monkeypatch) -> None:
    monkeypatch.delenv("SCRAPER_CHATGPT_PROJECT_URL", raising=False)
    assert policy._PROJECT_SLUG == "g-p-6a85a9a911888191a2cc491671a4056d-cs-automacao"
    assert policy._PROJECT_URL == (
        "https://chatgpt.com/g/"
        "g-p-6a85a9a911888191a2cc491671a4056d-cs-automacao/project"
    )
    assert policy._project_url() == policy._PROJECT_URL


def test_uses_isolated_coproducao_profile(monkeypatch) -> None:
    monkeypatch.delenv("SCRAPER_CHATGPT_COPRODUCAO_DEBUG_PORT", raising=False)
    candidates = policy._profile_candidates()
    assert len(candidates) == 1
    assert isinstance(candidates[0], Path)
    assert candidates[0].name == "chatgpt-coproducaolancamentos"
    assert policy._project_debug_port() == 9444


def test_login_and_project_detection() -> None:
    assert policy._is_login_url("https://auth.openai.com/log-in") is True
    assert policy._is_login_url("https://chatgpt.com/auth/login") is True
    assert policy._is_login_url(policy._PROJECT_URL) is False
    assert policy._has_project_url([policy._PROJECT_URL]) is True
    assert policy._has_project_url(["https://chatgpt.com/"]) is False


def test_prompt_requires_content_and_image(monkeypatch) -> None:
    monkeypatch.setattr(policy, "_BASE_PROMPT", lambda _job: "BASE")
    prompt = policy._patched_prompt({})
    assert "NÃO peça confirmação" in prompt
    assert "BREVE DESCRIÇÃO" in prompt
    assert "CATEGORIA" in prompt
    assert "imagem principal quadrada 1:1" in prompt
