from __future__ import annotations

from pathlib import Path

import pytest

from app.chatgpt_browser_assist import parse_chatgpt_text, save_conversation_url


def test_parse_chatgpt_structured_markdown_response() -> None:
    payload = parse_chatgpt_text(
        """
### **TÍTULO:** 123 Medicine WordPress Theme

**BREVE DESCRIÇÃO:** Tema WordPress para sites de saúde e clínicas.

**DESCRIÇÃO:**
```html
<p>Crie páginas para serviços médicos e hospitais.</p>
```

**TÍTULO SEO:** 123 Medicine WordPress Theme
**META DESCRIPTION:** Tema WordPress para sites médicos e de saúde.
**TAGS:** wordpress, saúde, clínica, hospital
**CATEGORIA:** Temas
"""
    )

    assert payload["title"] == "123 Medicine WordPress Theme"
    assert "<p>Crie páginas" in payload["description"]
    assert payload["category_name"] == "Temas"
    assert "saúde" in payload["tags"]


def test_parse_requires_core_fields() -> None:
    with pytest.raises(ValueError):
        parse_chatgpt_text("TÍTULO: Produto sem descrição")


def test_conversation_url_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.chatgpt_browser_assist as assist

    monkeypatch.setattr(assist, "_CONFIG_PATH", tmp_path / "config.json")
    result = save_conversation_url("https://chatgpt.com/c/abc123")
    assert result["conversation_url"] == "https://chatgpt.com/c/abc123"
    with pytest.raises(ValueError):
        save_conversation_url("https://example.com/conversa")
