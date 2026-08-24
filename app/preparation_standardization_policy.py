from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs

import app.addition_operational_ui_policy as addition_ui
import app.web as web


_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_OPERATIONS_PAYLOAD: Callable[[str], dict[str, Any]] | None = None
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_SCRIPT_PATHS = (
    _STATIC_DIR / "preparation_standardization_v12.js",
    _STATIC_DIR / "preparation_standardization_v12_selection_fix.js",
)


def _query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    values = query.get(key) or []
    return addition_ui._clean(values[0]) if values else default


def _filtered_preparation_page(
    *,
    q: str = "",
    state: str = "",
    version: str = "",
    relationship: str = "",
    page: int = 1,
    page_size: int = 5,
) -> dict[str, Any]:
    """Pagina a Preparação de Adicionar com os dois filtros compartilhados da UI."""
    safe_page = max(1, addition_ui._safe_int(page, 1))
    safe_size = max(1, min(100, addition_ui._safe_int(page_size, 5)))
    where, values = addition_ui._where_jobs("preparation", q, state)
    clauses = [where]

    if version == "has_version":
        clauses.append("TRIM(COALESCE(source_version, '')) <> ''")
    elif version == "missing_version":
        clauses.append("TRIM(COALESCE(source_version, '')) = ''")

    if relationship == "new_product":
        clauses.append("COALESCE(woo_product_id, 0) = 0")
    elif relationship == "woo_linked":
        clauses.append("COALESCE(woo_product_id, 0) > 0")

    final_where = " AND ".join(f"({clause})" for clause in clauses if clause)
    with addition_ui.additions._db() as connection:
        total = addition_ui._safe_int(
            connection.execute(
                f"SELECT COUNT(*) AS total FROM addition_jobs WHERE {final_where}", values
            ).fetchone()["total"]
        )
        pages = max(1, (total + safe_size - 1) // safe_size)
        safe_page = min(safe_page, pages)
        rows = connection.execute(
            f"SELECT * FROM addition_jobs WHERE {final_where} "
            "ORDER BY CASE queue_state "
            "WHEN 'executing' THEN 0 WHEN 'preparing' THEN 1 WHEN 'queued' THEN 2 "
            "WHEN 'ready' THEN 3 WHEN 'error' THEN 4 WHEN 'interrupted' THEN 5 "
            "WHEN 'waiting' THEN 6 WHEN 'completed' THEN 7 ELSE 8 END, "
            "CASE WHEN queue_position>0 THEN queue_position ELSE 999999 END, "
            "updated_at DESC LIMIT ? OFFSET ?",
            values + [safe_size, (safe_page - 1) * safe_size],
        ).fetchall()

    return {
        "items": [addition_ui._public_operation_job(dict(row)) for row in rows],
        "total": total,
        "page": safe_page,
        "page_size": safe_size,
        "pages": pages,
    }


def _patched_operations_payload(path_query: str) -> dict[str, Any]:
    base = _BASE_OPERATIONS_PAYLOAD or addition_ui._operations_payload
    query = parse_qs(path_query, keep_blank_values=True)
    scope = _query_value(query, "scope", "overview")
    if scope != "preparation":
        return base(path_query)

    version = _query_value(query, "version")
    relationship = _query_value(query, "relationship")
    if not version and not relationship:
        return base(path_query)

    return {
        "ok": True,
        **_filtered_preparation_page(
            q=_query_value(query, "q"),
            state=_query_value(query, "state"),
            version=version,
            relationship=relationship,
            page=addition_ui._safe_int(_query_value(query, "page", "1"), 1),
            page_size=addition_ui._safe_int(_query_value(query, "page_size", "5"), 5),
        ),
    }


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    blocks: list[str] = []
    for index, path in enumerate(_SCRIPT_PATHS, start=1):
        try:
            script = path.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
        except OSError:
            continue
        blocks.append(
            f"\n<script data-preparation-standardization-v12=\"{index}\">\n{script}\n</script>\n"
        )
    if not blocks:
        return html
    block = "".join(blocks)
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_preparation_standardization_policy() -> None:
    """Instala a camada final da seção Preparação nas abas Atualizar e Adicionar."""
    global _INSTALLED, _BASE_RENDER, _BASE_OPERATIONS_PAYLOAD
    if _INSTALLED:
        return

    _BASE_OPERATIONS_PAYLOAD = addition_ui._operations_payload
    addition_ui._operations_payload = _patched_operations_payload

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
