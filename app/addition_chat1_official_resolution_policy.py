from __future__ import annotations

import re
import time
from typing import Any, Mapping

import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_conversation_capture_policy as capture
import app.addition_final_validation_policy as final_validation
import app.addition_official_resolution_fallback_policy as fallback
import app.addition_one_click_policy as one_click
import app.addition_simple_creation_policy as simple
import app.new_product_workflow_policy as additions


_INSTALLED = False
_ORIGINAL_SAVE = None
_DESCRIPTION_EXAMPLE = (
    "Crie páginas profissionais com total liberdade visual O Elementor Pro ajuda a montar páginas, lojas e áreas "
    "do site com visual avançado, melhorando apresentação, conversão e flexibilidade para criar projetos WordPress "
    "mais modernos e profissionais. Ele funciona com edição de arrastar e soltar, widgets premium, templates e "
    "construtores para tema, formulários e pop-ups, deixando a criação mais prática e reduzindo dependência de código no projeto."
)


def _kind(job: Mapping[str, Any]) -> str:
    return "theme" if str(job.get("kind") or "").strip().lower() == "theme" else "plugin"


def _marketplace(job: Mapping[str, Any]) -> str:
    return fallback._marketplace_from_source(str(job.get("source_product_url") or ""))


def _valid_official(job: Mapping[str, Any], url: str) -> bool:
    value = str(url or "").strip().rstrip(".,;)")
    source = str(job.get("source_product_url") or "").strip()
    if not capture._is_official_candidate(value, source):
        return False
    marketplace = _marketplace(job)
    if marketplace:
        if not fallback._marketplace_item_url(value, marketplace):
            return False
        name = str(job.get("source_name") or job.get("title") or "")
        if fallback._name_similarity(name, value) < 0.55:
            return False
    return True


def _description_prompt(job: Mapping[str, Any]) -> str:
    name = str(job.get("source_name") or job.get("title") or "Produto WordPress").strip()
    kind_label = "tema WordPress" if _kind(job) == "theme" else "plugin WordPress"
    marketplace = _marketplace(job)
    marketplace_label = {
        "themeforest": "ThemeForest",
        "codecanyon": "CodeCanyon",
    }.get(marketplace, "site oficial do desenvolvedor ou marketplace oficial")
    current = str(job.get("source_official_url") or "").strip()
    known = current if _valid_official(job, current) else ""
    official_instruction = (
        f"A página oficial já validada é: {known}. Abra essa página e use-a como fonte principal."
        if known
        else (
            f"Localize por pesquisa web a página OFICIAL exata deste produto. O marketplace esperado é {marketplace_label}. "
            "Confirme que o nome corresponde ao produto antes de usar a página. Não use sites de redistribuição como fonte."
        )
    )

    return f"""Pesquise e escreva a breve descrição comercial deste produto para o e-commerce PluginTema.

PRODUTO
Nome: {name}
Tipo: {kind_label}
Versão de referência: {job.get('source_version') or '-'}

PÁGINA OFICIAL
{official_instruction}
Use a página oficial encontrada/validada para entender marca, finalidade, recursos confirmados, público e posicionamento. Não invente recursos e não copie o texto da página.

DESCRIÇÃO
Escreva um único parágrafo em português do Brasil, com aproximadamente 400 a 500 caracteres e 2 ou 3 frases. Comece com o principal benefício, mencione o produto naturalmente, explique o que ele ajuda a fazer e finalize indicando para quais projetos ou usuários ele é útil. Evite clichês vazios e não inclua a versão.

Use apenas estrutura, ritmo e extensão deste exemplo como referência; não copie o conteúdo:
\"{_DESCRIPTION_EXAMPLE}\"

FORMATO DE RESPOSTA OBRIGATÓRIO
Retorne EXATAMENTE duas linhas, sem Markdown, sem explicações e sem qualquer texto adicional:
PAGINA_OFICIAL: https://url-oficial-do-produto
DESCRICAO: parágrafo final da breve descrição"""


def _parse_answer(raw: str, job: Mapping[str, Any]) -> tuple[str, str]:
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:text|markdown|json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    url_match = re.search(r"P[ÁA]GINA[_\s-]*OFICIAL\s*:\s*(https?://\S+)", text, flags=re.I)
    desc_match = re.search(r"DESCRI[CÇ][AÃ]O\s*:\s*(.+)\Z", text, flags=re.I | re.S)
    if not url_match or not desc_match:
        return "", ""
    official = url_match.group(1).strip().rstrip(".,;)")
    description = simple._clean_description(desc_match.group(1))
    if not _valid_official(job, official):
        return "", ""
    validated = final_validation._validated_description(description)
    if not validated:
        return "", ""
    return official, validated


def _resolve_without_blocking(job_id: str) -> dict[str, Any]:
    job = additions._row(job_id)
    current = str(job.get("source_official_url") or "").strip()
    if _valid_official(job, current):
        one_click._emit(
            job_id,
            f"Página oficial já validada: {current}",
            step="official_source",
            progress=6,
        )
        return job

    additions._update(job_id, source_official_url="", error="")
    marketplace = _marketplace(job)
    label = {"themeforest": "ThemeForest", "codecanyon": "CodeCanyon"}.get(marketplace, "fonte oficial")
    one_click._emit(
        job_id,
        f"Página oficial ainda não confirmada localmente; o Chat 1 fará a pesquisa web no {label} e validará o vínculo antes da descrição.",
        step="official_source",
        progress=6,
    )
    return additions._row(job_id)


def _wait_official_and_description(
    context: Any,
    page: Any,
    before_count: int,
    job_id: str,
    url: str,
    *,
    timeout_seconds: int = 300,
) -> tuple[Any, str]:
    del before_count
    deadline = time.time() + timeout_seconds
    current = page
    stable_value = ""
    stable_count = 0
    announced = False

    while time.time() < deadline:
        if not reconnect._page_is_alive(current):
            current = reconnect._pick_page(context)
            current = reconnect._ensure_project_page_resilient(context, current, job_id, url, timeout_seconds=60)

        job = additions._row(job_id)
        found = ""
        for raw in reversed(capture._assistant_text_candidates(current)):
            official, description = _parse_answer(raw, job)
            if official and description:
                found = f"PAGINA_OFICIAL: {official}\nDESCRICAO: {description}"
                break

        if found:
            if found == stable_value:
                stable_count += 1
            else:
                stable_value = found
                stable_count = 0
            if not announced:
                official, description = _parse_answer(found, job)
                one_click._emit(
                    job_id,
                    f"Chat 1 encontrou a página oficial e uma descrição válida ({len(description)} caracteres); validando o término da resposta…",
                    step="chatgpt_description",
                    progress=30,
                )
                announced = True
            if stable_count >= 1 and not simple._assistant_busy(current):
                return current, found
        time.sleep(0.8)

    if stable_value:
        return current, stable_value
    raise RuntimeError(
        "O Chat 1 não retornou uma página oficial válida junto com a descrição. "
        "A automação não seguirá para a imagem sem confirmar a fonte oficial."
    )


def _save_official_and_description(job_id: str, raw: str) -> dict[str, Any]:
    job = additions._row(job_id)
    official, description = _parse_answer(raw, job)
    if not official or not description:
        raise RuntimeError("A resposta do Chat 1 não passou na validação de página oficial + descrição.")
    additions._update(job_id, source_official_url=official, error="")
    one_click._emit(
        job_id,
        f"Página oficial confirmada pelo Chat 1 e persistida: {official}",
        step="official_source",
        progress=34,
    )
    return _ORIGINAL_SAVE(job_id, description)


def install_addition_chat1_official_resolution_policy() -> None:
    global _INSTALLED, _ORIGINAL_SAVE
    if _INSTALLED:
        return
    _ORIGINAL_SAVE = simple._save_plain_description
    capture._resolve_official_for_job = _resolve_without_blocking
    simple._description_prompt = _description_prompt
    simple._wait_plain_answer = _wait_official_and_description
    simple._save_plain_description = _save_official_and_description
    _INSTALLED = True
