from app.additions import chatgpt_json_recovery_runtime as runtime


def test_extracts_real_rendered_response_with_newline_inside_url_string():
    text = '''texto antes
{
  "product_name": "Agricola - Agriculture and Organic Farm WordPress Theme",
  "short_description": "Crie uma presença profissional para negócios ligados ao campo e à alimentação orgânica. O Agricola é um tema WordPress desenvolvido para fazendas, produtores, lojas de alimentos naturais e outros projetos do setor agrícola, com uma apresentação adequada ao segmento e uso prático no WordPress.",
  "content": "<p>O Agricola oferece uma base visual voltada a negócios agrícolas e produção orgânica.</p><p>Também permite apresentar produtos, serviços e conteúdos do segmento em páginas organizadas.</p>",
  "categories": ["Tema"],
  "tags": [],
  "developer": "Ultrapack",
  "official_url": "https://themeforest.net/item/agricola-agriculture-and-organic-farm-wordpress-theme/39853177
"
}
texto depois'''
    payload = runtime.extract_json(text)
    assert payload is not None
    assert payload["product_name"].startswith("Agricola")
    assert payload["categories"] == ["Tema"]
    assert payload["official_url"].strip().endswith("39853177")


def test_prefers_last_complete_object_and_ignores_markdown_noise():
    text = '''Exemplo anterior: {"short_description":"antigo","content":"antigo"}

```json
{
  "product_name": "Produto correto",
  "short_description": "Descrição correta suficientemente estruturada",
  "content": "<p>Parágrafo com {chaves} dentro da string.</p><p>Segundo parágrafo.</p>",
  "categories": ["Plugin"],
  "tags": [],
  "developer": "Dev",
  "official_url": "https://example.test/item",
}
```
O ChatGPT pode cometer erros.'''
    payload = runtime.extract_json(text)
    assert payload is not None
    assert payload["product_name"] == "Produto correto"
    assert "{chaves}" in payload["content"]
    assert payload["official_url"] == "https://example.test/item"


def test_incomplete_json_fails_closed():
    text = '{"product_name":"Produto","short_description":"incompleta"'
    assert runtime.extract_json(text) is None
