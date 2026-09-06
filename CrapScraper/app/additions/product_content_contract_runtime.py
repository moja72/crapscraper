from __future__ import annotations

import re
from typing import Any

from app.additions import chatgpt_content_response_runtime as content_runtime
from app.additions import chatgpt_playwright as legacy
from app.additions.catalog_content_contract_v3 import apply as apply_catalog_contract
from app.additions.catalog_content_contract_v3 import has_forbidden_list_markup
from app.additions.content import valid_content

_INSTALLED = False
_CONTENT_CONTRACT_VERSION = 4

ELEMENTOR_PRO_MODEL = (
    "Crie páginas profissionais com total liberdade visual O Elementor Pro ajuda a montar páginas, "
    "lojas e áreas do site com visual avançado, melhorando apresentação, conversão e flexibilidade "
    "para criar projetos WordPress mais modernos e profissionais. Ele funciona com edição de arrastar "
    "e soltar, widgets premium, templates e construtores para tema, formulários e pop-ups, deixando a "
    "criação mais prática e reduzindo dependência de código no projeto."
)

_ORIGINAL_PARSE = content_runtime.parse_content_response
_ORIGINAL_QUALITY = content_runtime._quality_ok
_ORIGINAL_CONTENT_FINGERPRINT = legacy._content_fingerprint


def canonical_category(job: dict[str, Any]) -> str:
    return "Plugin" if str(job.get("kind") or "").strip().casefold() == "plugin" else "Tema"


def normalize_catalog_result(job: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return apply_catalog_contract(job, result)


def strict_prompt(job: dict[str, Any], correction: bool = False) -> str:
    prefix = (
        "A resposta anterior não seguiu o padrão comercial da PluginTema. Gere novamente sem explicar o erro.\n\n"
        if correction
        else ""
    )
    kind_label = "plugin" if str(job.get("kind") or "").strip().casefold() == "plugin" else "tema"
    category = canonical_category(job)
    category_id = 504 if category == "Plugin" else 525
    developer = str(job.get("developer") or "não confirmado").strip()
    official = str(job.get("official_url") or "não confirmada").strip()
    source = str(job.get("source_url") or "").strip()

    return f"""{prefix}Você está cadastrando um {kind_label} WordPress na loja PluginTema, dentro do projeto {legacy.project_name()}.
Produto: {job.get('product_name') or ''}
Versão: {job.get('source_version') or ''}
Fonte aprovada: {source}
Página oficial confirmada: {official}
Desenvolvedor confirmado: {developer}

Use somente fatos confirmados pelas fontes fornecidas. Não invente recursos, compatibilidades, desenvolvedor, URL ou benefícios específicos não comprovados.

PADRÃO OBRIGATÓRIO DA DESCRIÇÃO
Use como referência de estrutura, ritmo, tamanho e tom comercial este modelo do Elementor Pro, sem copiar recursos do Elementor para outro produto:
"{ELEMENTOR_PRO_MODEL}"

Para short_description:
- escreva entre 330 e 540 caracteres;
- texto corrido, natural, comercial e informativo;
- comece com uma frase curta de benefício/posicionamento diretamente ligada ao produto;
- depois explique em 2 ou 3 frases o que o produto faz, para quem serve e como ajuda no uso real;
- sem versão, sem HTML, sem listas, sem bullets, sem títulos e sem inventar recursos;
- NÃO faça enumeração de recursos.

Para content:
- use SOMENTE parágrafos <p>...</p>;
- escreva em texto corrido, no mesmo estilo comercial do modelo acima, com 2 a 4 parágrafos curtos;
- NÃO use listas, bullets, enumerações, títulos, subtítulos, <ul>, <ol>, <li>, <h1>, <h2>, <h3> ou qualquer seção de "Principais recursos";
- não transforme a descrição em uma lista de funcionalidades;
- não repita a breve descrição palavra por palavra.

TAXONOMIA OBRIGATÓRIA
- este produto é {category}, categoria WooCommerce já existente ID {category_id};
- categories deve ser EXATAMENTE ["{category}"];
- tags deve ser EXATAMENTE [];
- NÃO crie, sugira ou retorne nenhuma outra categoria;
- NÃO retorne tags;
- nunca retorne Plugin e Tema ao mesmo tempo.

METADADOS
- developer e official_url devem preservar os valores confirmados acima;
- official_url deve ser URL pura, sem Markdown.

Responda SOMENTE JSON válido, sem explicações antes ou depois, usando exatamente as chaves:
product_name, short_description, content, categories, tags, developer, official_url.
"""


def parse_content_response(text: str, job: dict[str, Any]) -> dict[str, Any]:
    return normalize_catalog_result(job, _ORIGINAL_PARSE(text, job))


def quality_ok(result: dict[str, Any]) -> bool:
    short = " ".join(str(result.get("short_description") or "").split())
    long_content = str(result.get("content") or "")
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", short) if part.strip()]
    paragraph_count = len(re.findall(r"<p\b[^>]*>.*?</p>", long_content, re.I | re.S))
    return bool(
        _ORIGINAL_QUALITY(result)
        and valid_content(result)
        and 330 <= len(short) <= 540
        and len(sentences) >= 2
        and "<" not in short
        and 2 <= paragraph_count <= 6
        and not has_forbidden_list_markup(long_content)
        and list(result.get("categories") or []) in (["Plugin"], ["Tema"])
        and not list(result.get("tags") or [])
    )


def content_fingerprint(job: dict[str, Any]) -> str:
    return f"content-contract-v{_CONTENT_CONTRACT_VERSION}|{_ORIGINAL_CONTENT_FINGERPRINT(job)}"


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    content_runtime._strict_prompt = strict_prompt
    content_runtime.parse_content_response = parse_content_response
    content_runtime._quality_ok = quality_ok
    legacy.parse_content_response = parse_content_response
    legacy._content_fingerprint = content_fingerprint
    _INSTALLED = True


__all__ = [
    "ELEMENTOR_PRO_MODEL",
    "canonical_category",
    "content_fingerprint",
    "install",
    "normalize_catalog_result",
    "parse_content_response",
    "quality_ok",
    "strict_prompt",
]
