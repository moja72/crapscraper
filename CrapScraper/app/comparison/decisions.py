from __future__ import annotations

import sqlite3
import threading
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.collection.legacy_core import settings


DECISION_LABELS = {
    "pending": "Pendente",
    "approve_update": "Aprovar atualização",
    "ignore": "Ignorado",
    "review_later": "Revisar depois",
    "same_product": "Mesmo produto confirmado",
    "different_products": "Produtos diferentes",
    "approve_new_product": "Cadastro novo aprovado",
}

QUEUE_TYPE_BY_DECISION = {
    "pending": "",
    "approve_update": "update",
    "approve_new_product": "new_product",
    "same_product": "match_confirmation",
    "review_later": "review",
    "ignore": "",
    "different_products": "",
}


RELATIONSHIP_LABELS = {
    "safe_auto": "Vínculo automático seguro",
    "candidate": "Candidato",
    "manual_confirmed": "Vínculo confirmado manualmente",
    "manual_rejected": "Vínculo rejeitado manualmente",
    "confirmed_not_in_source": "Confirmado como ausente no Ultrapack",
    "pending_review": "Pendente de revisão",
}


_DB_LOCK = threading.RLock()

SNAPSHOT_COLUMNS = (
    "woo_product_id",
    "site_version",
    "site_product_url",
    "site_official_url",
    "source_version",
    "source_product_url",
    "source_official_url",
    "relationship_state",
    "relationship_label",
)


def normalize_decision(value: Any) -> str:
    decision = str(value or "").strip().lower()

    if decision not in DECISION_LABELS:
        raise ValueError(
            "Decisao invalida: " + (decision or "vazia")
        )

    return decision


def queue_type_for_decision(decision: Any) -> str:
    normalized = normalize_decision(decision)
    return QUEUE_TYPE_BY_DECISION.get(normalized, "")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_database_path() -> Path:
    path = Path(os.getenv("SCRAPER_COMPARISON_DECISIONS_DB_PATH",str(settings.COMPARISON_DECISIONS_DB_PATH))).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def database_connection() -> Iterator[sqlite3.Connection]:
    database_path = get_database_path()

    with _DB_LOCK:
        connection = sqlite3.connect(
            str(database_path),
            timeout=30,
        )
        connection.row_factory = sqlite3.Row

        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA busy_timeout = 30000")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def initialize_database() -> Path:
    with database_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS comparison_decisions (
                comparison_item_id TEXT PRIMARY KEY,
                decision TEXT NOT NULL,
                decision_label TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                operator TEXT NOT NULL DEFAULT '',
                site_id TEXT NOT NULL DEFAULT '',
                site_name TEXT NOT NULL DEFAULT '',
                source_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                recommended_action TEXT NOT NULL DEFAULT '',
                queue_type TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS comparison_decision_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                comparison_item_id TEXT NOT NULL,
                previous_decision TEXT NOT NULL DEFAULT '',
                new_decision TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                operator TEXT NOT NULL DEFAULT '',
                changed_at TEXT NOT NULL,
                FOREIGN KEY (comparison_item_id)
                    REFERENCES comparison_decisions(comparison_item_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_comparison_decisions_decision
                ON comparison_decisions(decision);

            CREATE INDEX IF NOT EXISTS idx_comparison_decisions_queue_type
                ON comparison_decisions(queue_type);

            CREATE INDEX IF NOT EXISTS idx_comparison_history_item
                ON comparison_decision_history(comparison_item_id);


            CREATE TABLE IF NOT EXISTS comparison_relationships (
                relationship_id INTEGER PRIMARY KEY AUTOINCREMENT,

                site_product_key TEXT NOT NULL,
                source_product_key TEXT NOT NULL DEFAULT '',

                relationship_state TEXT NOT NULL,
                relationship_label TEXT NOT NULL DEFAULT '',

                site_id TEXT NOT NULL DEFAULT '',
                site_name TEXT NOT NULL DEFAULT '',
                site_official_url TEXT NOT NULL DEFAULT '',

                source_name TEXT NOT NULL DEFAULT '',
                source_product_url TEXT NOT NULL DEFAULT '',
                source_official_url TEXT NOT NULL DEFAULT '',

                note TEXT NOT NULL DEFAULT '',
                operator TEXT NOT NULL DEFAULT '',

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,

                UNIQUE(site_product_key, source_product_key)
            );


            CREATE INDEX IF NOT EXISTS idx_comparison_relationships_site
                ON comparison_relationships(site_product_key);

            CREATE INDEX IF NOT EXISTS idx_comparison_relationships_source
                ON comparison_relationships(source_product_key);

            CREATE INDEX IF NOT EXISTS idx_comparison_relationships_state
                ON comparison_relationships(relationship_state);
            """        )

        existing_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(comparison_decisions)")
        }
        for column in SNAPSHOT_COLUMNS:
            if column not in existing_columns:
                connection.execute(
                    f"ALTER TABLE comparison_decisions ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                )

    return get_database_path()


def save_decision(
    comparison_item_id: Any,
    decision: Any,
    *,
    note: Any = "",
    operator: Any = "",
    site_id: Any = "",
    site_name: Any = "",
    source_name: Any = "",
    status: Any = "",
    recommended_action: Any = "",
    **snapshot: Any,
) -> dict[str, Any]:
    initialize_database()

    item_id = str(comparison_item_id or "").strip()
    if not item_id:
        raise ValueError("comparison_item_id obrigatorio")

    normalized_decision = normalize_decision(decision)
    decision_label = DECISION_LABELS[normalized_decision]
    queue_type = queue_type_for_decision(normalized_decision)
    now = utc_now_iso()

    values = {
        "comparison_item_id": item_id,
        "decision": normalized_decision,
        "decision_label": decision_label,
        "note": str(note or "").strip(),
        "operator": str(operator or "").strip(),
        "site_id": str(site_id or "").strip(),
        "site_name": str(site_name or "").strip(),
        "source_name": str(source_name or "").strip(),
        "status": str(status or "").strip(),
        "recommended_action": str(recommended_action or "").strip(),
        "queue_type": queue_type,
        **{
            column: str(snapshot.get(column, "") or "").strip()
            for column in SNAPSHOT_COLUMNS
        },
    }
    if not values["woo_product_id"]:
        values["woo_product_id"] = values["site_id"]

    with database_connection() as connection:
        previous = connection.execute(
            "SELECT decision, created_at FROM comparison_decisions "
            "WHERE comparison_item_id = ?",
            (item_id,),
        ).fetchone()

        previous_decision = (
            str(previous["decision"]) if previous else ""
        )
        created_at = (
            str(previous["created_at"]) if previous else now
        )

        connection.execute(
            """
            INSERT INTO comparison_decisions (
                comparison_item_id, decision, decision_label, note,
                operator, site_id, site_name, source_name, status,
                recommended_action, queue_type, created_at, updated_at,
                woo_product_id, site_version, site_product_url,
                site_official_url, source_version, source_product_url,
                source_official_url, relationship_state, relationship_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(comparison_item_id) DO UPDATE SET
                decision = excluded.decision,
                decision_label = excluded.decision_label,
                note = excluded.note,
                operator = excluded.operator,
                site_id = excluded.site_id,
                site_name = excluded.site_name,
                source_name = excluded.source_name,
                status = excluded.status,
                recommended_action = excluded.recommended_action,
                queue_type = excluded.queue_type,
                woo_product_id = excluded.woo_product_id,
                site_version = excluded.site_version,
                site_product_url = excluded.site_product_url,
                site_official_url = excluded.site_official_url,
                source_version = excluded.source_version,
                source_product_url = excluded.source_product_url,
                source_official_url = excluded.source_official_url,
                relationship_state = excluded.relationship_state,
                relationship_label = excluded.relationship_label,
                updated_at = excluded.updated_at
            """,
            (
                item_id, normalized_decision, decision_label,
                values["note"], values["operator"], values["site_id"],
                values["site_name"], values["source_name"],
                values["status"], values["recommended_action"],
                queue_type, created_at, now,
                values["woo_product_id"], values["site_version"],
                values["site_product_url"], values["site_official_url"],
                values["source_version"], values["source_product_url"],
                values["source_official_url"], values["relationship_state"],
                values["relationship_label"],
            ),
        )

        connection.execute(
            """
            INSERT INTO comparison_decision_history (
                comparison_item_id, previous_decision, new_decision,
                note, operator, changed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item_id, previous_decision, normalized_decision,
                values["note"], values["operator"], now,
            ),
        )

        saved = connection.execute(
            "SELECT * FROM comparison_decisions "
            "WHERE comparison_item_id = ?",
            (item_id,),
        ).fetchone()

    return dict(saved)


def save_decisions_bulk(
    items: Any,
    decision: Any,
    *,
    note: Any = "",
    operator: Any = "local",
) -> dict[str, Any]:
    normalized_decision = normalize_decision(decision)
    normalized_items = [
        dict(item)
        for item in (items or [])
        if isinstance(item, dict)
        and str(item.get("comparison_item_id", "")).strip()
    ]

    if not normalized_items:
        raise ValueError("Nenhum item valido foi informado")

    saved_items = []

    for item in normalized_items:
        saved_items.append(
            save_decision(
                item.get("comparison_item_id"),
                normalized_decision,
                note=note,
                operator=operator,
                site_id=item.get("site_id", ""),
                site_name=item.get("site_name", ""),
                source_name=item.get("source_name", ""),
                status=item.get("status", ""),
                recommended_action=item.get(
                    "recommended_action",
                    "",
                ),
                **{column: item.get(column, "") for column in SNAPSHOT_COLUMNS},
            )
        )

    return {
        "decision": normalized_decision,
        "decision_label": DECISION_LABELS[normalized_decision],
        "total_saved": len(saved_items),
        "items": saved_items,
    }


def get_decision(comparison_item_id: Any) -> dict[str, Any] | None:
    initialize_database()
    item_id = str(comparison_item_id or "").strip()
    if not item_id:
        return None

    with database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM comparison_decisions "
            "WHERE comparison_item_id = ?",
            (item_id,),
        ).fetchone()

    return dict(row) if row else None


def get_decision_history(comparison_item_id: Any) -> list[dict[str, Any]]:
    initialize_database()
    item_id = str(comparison_item_id or "").strip()
    if not item_id:
        return []

    with database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM comparison_decision_history "
            "WHERE comparison_item_id = ? "
            "ORDER BY history_id DESC",
            (item_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def list_decisions(
    decision: Any = "",
    queue_type: Any = "",
) -> list[dict[str, Any]]:
    initialize_database()
    filters = []
    values = []

    normalized_decision = str(decision or "").strip().lower()
    normalized_queue = str(queue_type or "").strip().lower()

    if normalized_decision:
        normalized_decision = normalize_decision(normalized_decision)
        filters.append("decision = ?")
        values.append(normalized_decision)

    if normalized_queue:
        filters.append("queue_type = ?")
        values.append(normalized_queue)

    sql = "SELECT * FROM comparison_decisions"
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += " ORDER BY updated_at DESC"

    with database_connection() as connection:
        rows = connection.execute(sql, values).fetchall()

    return [dict(row) for row in rows]


def get_decisions_map(
    comparison_item_ids: Any = None,
) -> dict[str, dict[str, Any]]:
    initialize_database()

    ids = [
        str(value or "").strip()
        for value in (comparison_item_ids or [])
        if str(value or "").strip()
    ]

    with database_connection() as connection:
        if ids:
            placeholders = ",".join("?" for _ in ids)
            rows = connection.execute(
                "SELECT * FROM comparison_decisions "
                "WHERE comparison_item_id IN (" + placeholders + ")",
                ids,
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM comparison_decisions"
            ).fetchall()

    return {
        str(row["comparison_item_id"]): dict(row)
        for row in rows
    }


def reset_decision(
    comparison_item_id: Any,
    *,
    note: Any = "Decisao removida",
    operator: Any = "",
) -> dict[str, Any] | None:
    current = get_decision(comparison_item_id)
    if current is None:
        return None

    return save_decision(
        comparison_item_id,
        "pending",
        note=note,
        operator=operator,
        site_id=current.get("site_id", ""),
        site_name=current.get("site_name", ""),
        source_name=current.get("source_name", ""),
        status=current.get("status", ""),
        recommended_action=current.get("recommended_action", ""),
        **{column: current.get(column, "") for column in SNAPSHOT_COLUMNS},
    )


def list_approved_updates() -> list[dict[str, Any]]:
    return list_decisions(decision="approve_update")


def list_approved_additions() -> list[dict[str, Any]]:
    return list_decisions(decision="approve_new_product")


def get_operational_queues() -> dict[str, Any]:
    updates = list_approved_updates()
    additions = list_approved_additions()

    return {
        "updates": updates,
        "additions": additions,
        "update_total": len(updates),
        "addition_total": len(additions),
        "total": len(updates) + len(additions),
    }


def get_decision_summary() -> dict[str, Any]:
    initialize_database()

    with database_connection() as connection:
        rows = connection.execute(
            "SELECT decision, COUNT(*) AS total "
            "FROM comparison_decisions GROUP BY decision"
        ).fetchall()

    counts = {
        key: 0
        for key in DECISION_LABELS
    }

    for row in rows:
        counts[str(row["decision"])] = int(row["total"])

    approved_total = (
        counts.get("approve_update", 0)
        + counts.get("approve_new_product", 0)
        + counts.get("same_product", 0)
    )

    return {
        "counts": counts,
        "total": sum(counts.values()),
        "approved_total": approved_total,
        "pending_total": counts.get("pending", 0),
        "ignored_total": counts.get("ignore", 0),
        "review_total": counts.get("review_later", 0),
    }


def normalize_relationship_state(value: Any) -> str:
    state = str(value or "").strip().lower()

    if state not in RELATIONSHIP_LABELS:
        raise ValueError(
            "Estado de relacionamento invalido: "
            + (state or "vazio")
        )

    return state


def save_relationship(
    site_product_key: Any,
    source_product_key: Any,
    relationship_state: Any,
    *,
    site_id: Any = "",
    site_name: Any = "",
    site_official_url: Any = "",
    source_name: Any = "",
    source_product_url: Any = "",
    source_official_url: Any = "",
    note: Any = "",
    operator: Any = "local",
) -> dict[str, Any]:
    initialize_database()

    site_key = str(site_product_key or "").strip()
    source_key = str(source_product_key or "").strip()

    if not site_key:
        raise ValueError("site_product_key obrigatorio")

    state = normalize_relationship_state(
        relationship_state
    )

    if (
        state
        not in {
            "confirmed_not_in_source",
            "pending_review",
        }
        and not source_key
    ):
        raise ValueError(
            "source_product_key obrigatorio para este estado"
        )

    now = utc_now_iso()

    with database_connection() as connection:

        if state == "manual_confirmed":

            connection.execute(
                """
                UPDATE comparison_relationships
                SET
                    relationship_state = 'manual_rejected',
                    relationship_label = ?,
                    updated_at = ?
                WHERE site_product_key = ?
                  AND source_product_key <> ?
                  AND relationship_state = 'manual_confirmed'
                """,
                (
                    RELATIONSHIP_LABELS["manual_rejected"],
                    now,
                    site_key,
                    source_key,
                ),
            )

            connection.execute(
                """
                UPDATE comparison_relationships
                SET
                    relationship_state = 'manual_rejected',
                    relationship_label = ?,
                    updated_at = ?
                WHERE source_product_key = ?
                  AND site_product_key <> ?
                  AND relationship_state = 'manual_confirmed'
                """,
                (
                    RELATIONSHIP_LABELS["manual_rejected"],
                    now,
                    source_key,
                    site_key,
                ),
            )

        previous = connection.execute(
            """
            SELECT created_at
            FROM comparison_relationships
            WHERE site_product_key = ?
              AND source_product_key = ?
            """,
            (
                site_key,
                source_key,
            ),
        ).fetchone()

        created_at = (
            str(previous["created_at"])
            if previous
            else now
        )

        connection.execute(
            """
            INSERT INTO comparison_relationships (
                site_product_key,
                source_product_key,
                relationship_state,
                relationship_label,
                site_id,
                site_name,
                site_official_url,
                source_name,
                source_product_url,
                source_official_url,
                note,
                operator,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(
                site_product_key,
                source_product_key
            )
            DO UPDATE SET
                relationship_state =
                    excluded.relationship_state,
                relationship_label =
                    excluded.relationship_label,
                site_id = excluded.site_id,
                site_name = excluded.site_name,
                site_official_url =
                    excluded.site_official_url,
                source_name = excluded.source_name,
                source_product_url =
                    excluded.source_product_url,
                source_official_url =
                    excluded.source_official_url,
                note = excluded.note,
                operator = excluded.operator,
                updated_at = excluded.updated_at
            """,
            (
                site_key,
                source_key,
                state,
                RELATIONSHIP_LABELS[state],
                str(site_id or "").strip(),
                str(site_name or "").strip(),
                str(site_official_url or "").strip(),
                str(source_name or "").strip(),
                str(source_product_url or "").strip(),
                str(source_official_url or "").strip(),
                str(note or "").strip(),
                str(operator or "").strip(),
                created_at,
                now,
            ),
        )

        row = connection.execute(
            """
            SELECT *
            FROM comparison_relationships
            WHERE site_product_key = ?
              AND source_product_key = ?
            """,
            (
                site_key,
                source_key,
            ),
        ).fetchone()

    return dict(row)


def get_relationships_for_site(
    site_product_key: Any,
) -> list[dict[str, Any]]:
    initialize_database()

    site_key = str(site_product_key or "").strip()

    if not site_key:
        return []

    with database_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM comparison_relationships
            WHERE site_product_key = ?
            ORDER BY updated_at DESC
            """,
            (site_key,),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def get_relationships_map() -> dict[str, list[dict[str, Any]]]:
    initialize_database()

    with database_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM comparison_relationships
            ORDER BY updated_at DESC
            """
        ).fetchall()

    result: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        item = dict(row)
        site_key = str(
            item.get("site_product_key", "")
        )

        result.setdefault(
            site_key,
            [],
        ).append(item)

    return result


def get_database_info() -> dict[str, Any]:
    database_path = initialize_database()

    with database_connection() as connection:
        tables = [
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' ORDER BY name"
            ).fetchall()
        ]

        decision_total = int(
            connection.execute(
                "SELECT COUNT(*) FROM comparison_decisions"
            ).fetchone()[0]
        )

        history_total = int(
            connection.execute(
                "SELECT COUNT(*) FROM comparison_decision_history"
            ).fetchone()[0]
        )

        relationship_total = int(
            connection.execute(
                "SELECT COUNT(*) FROM comparison_relationships"
            ).fetchone()[0]
        )

    return {
        "database_path": str(database_path),
        "exists": database_path.exists(),
        "tables": tables,
        "decision_total": decision_total,
        "history_total": history_total,
        "relationship_total": relationship_total,
    }


__all__ = [
    "RELATIONSHIP_LABELS",
    "normalize_relationship_state",
    "save_relationship",
    "get_relationships_for_site",
    "get_relationships_map",
    "get_operational_queues",
    "list_approved_additions",
    "list_approved_updates",
    "database_connection",
    "get_database_info",
    "get_database_path",
    "initialize_database",
    "utc_now_iso",
]
