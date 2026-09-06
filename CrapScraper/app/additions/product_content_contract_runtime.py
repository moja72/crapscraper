from __future__ import annotations

import re
from typing import Any

from app.additions import chatgpt_content_response_runtime as content_runtime
from app.additions import chatgpt_playwright as legacy
from app.additions.content import valid_content

_INSTALLED = False
_CONTENT_CONTRACT_VERSION = 2

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
    clean = dict(result)
    clean["product_name"] = str(job.get("product_name") or clean.get("product_name") or "").strip()
    clean["short_description"] = " ".join(str(clean.get("short_description") or "").split())
    clean["categories"] = [canonical_category(job)]
    clean["tags"] = []
    return clean


def strict_prompt(job: dict[str, Any], correction: bool = False) -> str:
    prefix = (
        "A resposta anterior não seguiu o padrão comercial da PluginTema. Gere novamente sem explicar o erro.\n\n"
        if correction
        else ""
    )
    kind_label = "plugin" if str(job.get("kind") or "").strip().casefold() == "plugin" else "tema"
    category = canonical_category(job)
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

PADRÃO OBRIGATÓRIO DA BREVE DESCRIÇÃO
Use como referência de estrutura, ritmo, tamanho e tom comercial este modelo do Elementor Pro, SEM copiar recursos do Elementor para outro produto:
"{ELEMENTOR_PRO_MODEL}"

Para short_description:
- escreva entre 330 e 540 caracteres;
- comece com uma frase curta de benefício/posicionamento diretamente ligada ao produto;
- em seguida use 2 frases objetivas explicando o que o produto faz e como ajuda no uso real;
- texto corrido, natural, comercial e informativo;
- sem versão, sem HTML, sem listas, sem promessas genéricas e sem inventar recursos.

Para content:
- use HTML simples e legível;
- use pelo menos 2 parágrafos <p>;
- se houver recursos realmente confirmados, pode usar <h2>Principais recursos</h2> e <ul><li>...</li></ul>;
- não repita a breve descrição palavra por palavra.

TAXONOMIA OBRIGATÓRIA
- categories deve ser EXATAMENTE ["{category}"];
- tags deve ser EXATAMENTE [];
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
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", short) if part.strip()]
    return bool(
        _ORIGINAL_QUALITY(result)
        and valid_content(result)
        and 330 <= len(short) <= 540
        and len(sentences) >= 2
        and "<" not in short
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
