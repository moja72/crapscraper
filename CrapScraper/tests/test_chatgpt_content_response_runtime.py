from __future__ import annotations

from app.additions.chatgpt_content_response_runtime import (
    _BEGIN,
    _END,
    _extract_last_marked,
    _htmlize,
    _strict_prompt,
    parse_content_response,
)


def job():
    return {
        "job_id": "add-content-runtime",
        "product_name": "Agribusiness - Agriculture Business Consulting WordPress Theme",
        "kind": "theme",
        "source_version": "1.0.3",
        "source_url": "https://example.com/source",
        "official_url": "https://themeforest.net/item/example/123",
        "developer": "cmsmasters",
    }


def test_extracts_last_marked_response_not_prompt_copy():
    body = f"prompt {_BEGIN} modelo {_END}\nassistant {_BEGIN} {{\"ok\": true}} {_END}"
    assert _extract_last_marked(body) == '{"ok": true}'


def test_repairs_markdown_escaped_underscores_and_markdown_url():
    text = r'''{
      "product\_name": "Agribusiness - Agriculture Business Consulting WordPress Theme",
      "short\_description": "Crie uma presença profissional para empresas do agronegócio com um tema voltado a consultorias agrícolas, empresas AgriTech, fornecedores e negócios sustentáveis. O Agribusiness ajuda a apresentar serviços, especialistas, projetos e produtos em uma estrutura visual adequada ao setor, preservando apenas os recursos confirmados pela fonte oficial durante o cadastro.",
      "content": "O Agribusiness atende empresas e consultorias ligadas ao agronegócio. Ele oferece uma estrutura para apresentar serviços e especialistas. Recursos confirmados podem ser organizados de maneira clara para o visitante. A página também pode reunir informações institucionais e comerciais sem inventar compatibilidades não verificadas. O cadastro preserva a origem e os dados confirmados pela fonte aprovada.",
      "categories": ["Temas WordPress"],
      "tags": ["Agronegócio", "WordPress"],
      "developer": "cmsmasters",
      "official\_url": "[https://themeforest.net/item/example/123](https://themeforest.net/item/example/123)"
    }'''
    result = parse_content_response(text, job())
    assert result["product_name"].startswith("Agribusiness")
    assert result["official_url"] == "https://themeforest.net/item/example/123"
    assert result["content"].startswith("<p>")
    assert "</p>" in result["content"]


def test_htmlize_never_leaves_plain_wall_of_text():
    raw = "Primeiro parágrafo com contexto suficiente. Segundo ponto confirmado. Terceiro ponto confirmado. Quarto ponto de encerramento."
    html = _htmlize(raw)
    assert html.startswith("<p>")
    assert html.count("<p>") >= 2


def test_strict_prompt_requires_envelope_html_and_unescaped_keys():
    prompt = _strict_prompt(job())
    assert _BEGIN in prompt and _END in prompt
    assert "product_name" in prompt
    assert "nunca product\\_name" in prompt
    assert "<h2>Principais recursos</h2>" in prompt
    assert "URL pura" in prompt
