from __future__ import annotations

from app.additions.chatgpt_playwright import _image_magic, parse_content_response


def job():
    return {
        "job_id": "add-test",
        "product_name": "Produto Teste",
        "kind": "plugin",
        "source_version": "1.2.3",
        "source_url": "https://example.com/source",
        "official_url": "https://example.com/official",
        "developer": "Fornecedor",
    }


def test_parse_browser_json_content():
    text = """```json
{"product_name":"Produto Teste","short_description":"Produto Teste oferece uma solução prática e bem estruturada para projetos WordPress, reunindo recursos confirmados pela fonte oficial e facilitando o uso cotidiano em sites profissionais, sem adicionar promessas ou compatibilidades que não tenham sido verificadas previamente pelo processo de cadastro.","content":"<p>Produto Teste é um plugin WordPress cadastrado a partir de dados confirmados pela fonte aprovada.</p><p>O processo preserva a origem do arquivo, a página oficial, o desenvolvedor e os detalhes realmente disponíveis para o produto, evitando incluir recursos ou compatibilidades que não estejam comprovados.</p><p>Antes da publicação, o CrapScraper valida o ZIP, prepara a mídia e confere o resultado no WooCommerce para manter o cadastro consistente.</p>","categories":["Plugins"],"tags":["WordPress"],"developer":"Fornecedor","official_url":"https://example.com/official"}
```"""
    result = parse_content_response(text, job())
    assert result["product_name"] == "Produto Teste"
    assert result["categories"] == ["Plugins"]
    assert result["tags"] == ["WordPress"]


def test_parse_legacy_structured_content_from_old_browser_flow():
    text = """TÍTULO: Produto Teste
BREVE DESCRIÇÃO: Produto Teste oferece uma solução prática e bem estruturada para projetos WordPress, reunindo recursos confirmados pela fonte oficial e facilitando o uso cotidiano em sites profissionais, sem adicionar promessas ou compatibilidades que não tenham sido verificadas previamente pelo processo de cadastro.
DESCRIÇÃO: <p>Produto Teste é um plugin WordPress cadastrado a partir de dados confirmados pela fonte aprovada.</p><p>O processo preserva a origem do arquivo, a página oficial, o desenvolvedor e os detalhes realmente disponíveis para o produto, evitando incluir recursos ou compatibilidades que não estejam comprovados.</p><p>Antes da publicação, o CrapScraper valida o ZIP, prepara a mídia e confere o resultado no WooCommerce para manter o cadastro consistente.</p>
TÍTULO SEO: Produto Teste
META DESCRIPTION: Produto Teste para WordPress.
TAGS: WordPress, Plugin
CATEGORIA: Plugins
"""
    result = parse_content_response(text, job())
    assert result["categories"] == ["Plugins"]
    assert result["tags"] == ["WordPress", "Plugin"]


def test_image_magic_allows_only_expected_formats():
    assert _image_magic(b"\x89PNG\r\n\x1a\n" + b"x" * 32) == "png"
    assert _image_magic(b"\xff\xd8\xff" + b"x" * 32) == "jpeg"
    assert _image_magic(b"RIFF" + b"1234" + b"WEBP" + b"x" * 32) == "webp"
    assert _image_magic(b"<!doctype html><html></html>") == ""
