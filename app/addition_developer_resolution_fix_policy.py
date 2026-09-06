from __future__ import annotations

import re
from typing import Any, Callable, Mapping

import app.addition_custom_fields_policy as fields
import app.addition_fresh_project_chat_policy as fresh_chat
import app.addition_operational_ui_policy as operational
import app.addition_one_click_policy as one_click
import app.addition_real_chat_url_policy as real_chat
import app.new_product_workflow_policy as additions


_INSTALLED = False
_BASE_DEVELOPER_OK: Callable[[str], bool] | None = None
_BASE_DEVELOPER: Callable[[Mapping[str, Any], str], str] | None = None

_RESELLER_KEYS = {
    "plugintheme",
    "pluginthenet",
    "plugintema",
    "plugintemacombr",
    "ultrapack",
    "ultrapackv2",
    "ultrapackv2com",
}
_AGGREGATE_CODECANYON_LABEL = "CodeCanyon / Envato Market"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean(value).lower())


def _is_reseller_developer(value: Any) -> bool:
    key = _key(value)
    if not key:
        return False
    return key in _RESELLER_KEYS or any(
        key.startswith(prefix)
        for prefix in ("plugintheme", "ultrapackv2", "plugintema")
    )


def _is_codecanyon_aggregate(job: Mapping[str, Any]) -> bool:
    name = _clean(job.get("source_name") or job.get("title")).lower()
    if "codecanyon" not in name:
        return False
    aggregate_markers = (
        "bundle",
        "pack",
        "collection",
        "plugins",
        "plugin bundle",
    )
    if any(marker in name for marker in aggregate_markers):
        return True
    return bool(re.match(r"^\s*\d{2,}\s+codecanyon\b", name))


def _developer_ok(value: str) -> bool:
    if _is_reseller_developer(value):
        return False
    if _BASE_DEVELOPER_OK is None:
        return bool(_clean(value))
    return bool(_BASE_DEVELOPER_OK(value))


def _developer(job: Mapping[str, Any], official_url: str) -> str:
    # Bundles CodeCanyon agregam itens de vários autores. O campo operacional usa
    # a marca/marketplace responsável pela coleção em vez de atribuir autoria ao
    # site redistribuidor PluginTheme.
    if _is_codecanyon_aggregate(job):
        return _AGGREGATE_CODECANYON_LABEL

    if _BASE_DEVELOPER is None:
        return ""
    value = _clean(_BASE_DEVELOPER(job, official_url))
    return "" if _is_reseller_developer(value) else value


def _resolve_developer_fields(job_id: str) -> None:
    job = additions._row(job_id)
    official = _clean(job.get("source_official_url") or job.get("site_oficial"))
    previous = _clean(job.get("desenvolvedor"))

    try:
        developer = _clean(fields._normalize_developer_display(fields._developer(job, official)))
    except Exception:
        developer = ""

    values: dict[str, Any] = {}
    if official:
        values["site_oficial"] = official

    if developer:
        values["desenvolvedor"] = developer
    elif _is_reseller_developer(previous):
        # Nunca mantenha PluginTheme/UltraPack como se fossem o autor do produto.
        values["desenvolvedor"] = ""

    if values:
        operational._update_operation(job_id, **values)

    if developer:
        if previous and previous != developer:
            one_click._emit(
                job_id,
                f"Desenvolvedor revalidado: {previous} → {developer}.",
                step="official_source",
                progress=77,
            )
        else:
            one_click._emit(
                job_id,
                f"Desenvolvedor resolvido: {developer}.",
                step="official_source",
                progress=77,
            )
        return

    one_click._emit(
        job_id,
        "Página oficial resolvida; desenvolvedor não foi atribuído ao site redistribuidor e seguirá pendente até existir uma fonte segura.",
        step="official_source",
        progress=77,
    )


def install_addition_developer_resolution_fix_policy() -> None:
    global _INSTALLED, _BASE_DEVELOPER_OK, _BASE_DEVELOPER
    if _INSTALLED:
        return

    _BASE_DEVELOPER_OK = fields._developer_ok
    _BASE_DEVELOPER = fields._developer

    # A própria função base consulta _developer_ok em tempo de execução, então
    # substituir o símbolo no módulo também impede que JSON-LD do redistribuidor
    # volte a ser aceito como autor em cadastros futuros.
    fields._developer_ok = _developer_ok
    fields._developer = _developer

    # A UI antiga só resolvia quando o campo estava vazio; revalidar sempre é
    # necessário para corrigir jobs já persistidos com PluginTheme.net.
    operational._resolve_developer_fields = _resolve_developer_fields

    # Este instalador roda depois de addition_conversation_capture_policy e antes
    # do runner resiliente final. É o ponto tardio seguro para ativar duas proteções
    # que já existem/foram isoladas em policies próprias: nunca persistir /project
    # como conversa e nunca aceitar o Chat 2 sem provar um chat novo e vazio.
    real_chat.install_addition_real_chat_url_policy()
    fresh_chat.install_addition_fresh_project_chat_policy()

    _INSTALLED = True
