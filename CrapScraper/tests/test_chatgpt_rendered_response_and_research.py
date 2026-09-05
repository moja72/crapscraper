from __future__ import annotations

from app.additions.chatgpt_content_response_runtime import (
    _extract_json,
    _rendered_text,
    parse_content_response,
)
from app.additions.source import ProductResearchService, clean_developer


def _job(**overrides):
    value = {
        "job_id": "agribusiness-test",
        "product_name": "Agribusiness - Agriculture Business Consulting WordPress Theme",
        "kind": "theme",
        "source_version": "1.0.3",
        "source_url": "https://www.ultrapackv2.com/item/agribusiness/",
        "official_url": "https://themeforest.net/item/agribusiness/58281385",
        "developer": "cmsmasters",
    }
    value.update(overrides)
    return value


def test_rendered_markdown_unescapes_keys_and_markers():
    text = r'<<\<CRAPSCRAPER\_JSON\_BEGIN>>> {"product\_name":"Produto"} <<\<CRAPSCRAPER\_JSON\_END>>>'
    normalized = _rendered_text(text)
    assert "CRAPSCRAPER_JSON_BEGIN" in normalized
    assert '"product_name"' in normalized


def test_extract_json_accepts_escaped_underscores_from_ui():
    text = r'''```json
{"product\_name":"Produto Teste","short\_description":"Descrição suficiente para o teste","content":"<p>Conteúdo</p>","categories":[],"tags":[],"developer":"cmsmasters","official\_url":"https://themeforest.net/item/test/1"}
```'''
    payload = _extract_json(text)
    assert payload is not None
    assert payload["product_name"] == "Produto Teste"
    assert payload["official_url"].startswith("https://themeforest.net/")


def test_parse_content_preserves_confirmed_metadata_and_htmlizes_plain_content():
    short = (
        "Crie uma presença profissional para negócios ligados ao agronegócio com um tema WordPress voltado a "
        "consultorias e empresas do setor agrícola. O Agribusiness ajuda a apresentar serviços, especialistas, "
        "projetos e conteúdo institucional de forma organizada, oferecendo uma base visual coerente para marcas "
        "que precisam comunicar atuação e experiência no mercado agrícola."
    )
    content = (
        "O Agribusiness é um tema WordPress voltado a negócios relacionados à agricultura e ao agronegócio. "
        "Ele oferece uma base visual direcionada ao segmento para apresentar serviços e conteúdo institucional. "
        "A estrutura pode ser usada por consultorias e empresas do setor agrícola sem adicionar recursos não confirmados. "
        "O cadastro preserva apenas informações verificadas pelas páginas de origem e oficial do produto."
    )
    text = (
        '{"product_name":"Agribusiness - Agriculture Business Consulting WordPress Theme",'
        f'"short_description":"{short}","content":"{content}",'
        '"categories":["Temas WordPress"],"tags":["Agronegócio"],'
        '"developer":"after{border-top-color:#f6f6f6;}",'
        '"official_url":"[https://themeforest.net/item/wrong](https://themeforest.net/item/wrong)"}'
    )
    result = parse_content_response(text, _job())
    assert result["developer"] == "cmsmasters"
    assert result["official_url"] == "https://themeforest.net/item/agribusiness/58281385"
    assert result["content"].startswith("<p>")


def test_clean_developer_rejects_css_fragment():
    assert clean_developer("after{border-top-color:#f6f6f6;}.post-content blockquote") == ""
    assert clean_developer("cmsmasters") == "cmsmasters"


class _Response:
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")


class _Session:
    def get(self, url, **_kwargs):
        if "themeforest.net" in url:
            return _Response('<a href="https://themeforest.net/user/cmsmasters">cmsmasters</a>')
        return _Response('<html><style>author: after{border-top-color:#f6f6f6;}</style><a href="https://themeforest.net/item/agribusiness/58281385">Official</a></html>')


def test_research_replaces_stale_css_developer_from_official_page():
    service = ProductResearchService(session=_Session())
    result = service.resolve(
        _job(
            developer="after{border-top-color:#f6f6f6;}.post-content blockquote",
            official_url="https://themeforest.net/item/agribusiness/58281385",
        )
    )
    assert result["developer"] == "cmsmasters"
    assert result["official_url"].startswith("https://themeforest.net/item/agribusiness/")
