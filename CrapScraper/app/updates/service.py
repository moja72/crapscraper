from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from app.comparison import decisions
from app.plugintheme_profile import open_manual_session, profile_diagnostic
from app.updates.batch import UpdateBatchService
from app.updates.executor import UpdateExecutor
from app.updates.repository import UpdateRepository
from app.updates.source_auth import (
    clear_source_session,
    get_source_account,
    get_source_diagnostic,
    get_source_session,
    set_source_state,
    source_state,
)


class UpdateService:
    def __init__(
        self,
        data_dir: Path,
        *,
        repository: UpdateRepository | None = None,
        executor: UpdateExecutor | None = None,
        credits: Any | None = None,
    ):
        self.repository = repository or UpdateRepository(data_dir)
        self.executor = executor or UpdateExecutor(self.repository)
        self.batch = UpdateBatchService(self.executor)
        self.lock = threading.RLock()
        self.environment_validation: dict[str, Any] = {}
        self.credits = credits
        if os.getenv("SCRAPER_UPDATE_IMPORT_LEGACY", "1").strip().lower() not in {"0", "false", "no", "off"}:
            self.repository.migrate_legacy_runtime(data_dir / "update_runtime.json")
        self.materialize()
        self.repository.backfill_history_events()
        history = getattr(self.executor, "history", None)
        if history is not None and getattr(history.client, "configured", False):
            threading.Thread(target=history.sync_pending, name="update-history-outbox", daemon=True).start()

    def materialize(self) -> dict[str, Any]:
        with self.lock:
            return {"ok": True, **self.repository.materialize(decisions.list_approved_updates())}

    def materialize_manual(self, approval: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            self.repository.materialize([approval])
            job_id = self.repository._job_id(str(approval["comparison_item_id"]))
            return {"ok": True, "item": self.repository.get(job_id)}

    def list(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        self.materialize()
        result = self.repository.list(
            query=str(payload.get("query") or ""),
            group=str(payload.get("group") or ""),
            stage=str(payload.get("stage") or ""),
            page=int(payload.get("page") or 1),
            page_size=int(payload.get("page_size") or 5),
        )
        return {"ok": True, **result, "batch": self.batch.state(), "database": str(self.repository.path)}

    def _plugintheme_environment(self) -> dict[str, Any]:
        account = get_source_account("plugintheme")
        persisted = profile_diagnostic(account)
        runtime = get_source_diagnostic("plugintheme", account)
        evidence = {**persisted, **runtime}
        cached = self.credits.cached("plugintheme", account) if self.credits is not None else {}
        state = source_state("plugintheme", account)
        authenticated = state == "validated" and bool(evidence.get("authenticated", cached.get("authenticated", False)))
        configured = bool(persisted.get("configured"))
        status = "VALIDADA" if authenticated else "CONFIGURADA / SESSÃO NÃO VALIDADA" if configured else "NÃO CONFIGURADA"
        return {
            "configured": configured,
            "account_key": account,
            "profile_path": evidence.get("profile_path", ""),
            "profile_exists": bool(evidence.get("profile_exists")),
            "persistence_mode": evidence.get("persistence_mode", "persistent_browser_context"),
            "storage_state_exists": bool(evidence.get("storage_state_exists")),
            "browser_storage_exists": bool(evidence.get("browser_storage_exists")),
            "cookie_count": int(evidence.get("cookie_count") or 0),
            "httponly_cookie_count": int(evidence.get("httponly_cookie_count") or 0),
            "storage_entry_count": int(evidence.get("storage_entry_count") or 0),
            "current_url": str(evidence.get("current_url") or ""),
            "login_redirect": bool(evidence.get("login_redirect")),
            "authenticated_indicator": bool(evidence.get("authenticated_indicator")),
            "authenticated": authenticated,
            "status": status,
            "renewal_available": True,
            "credits": cached.get("credits"),
            "credit_limit": cached.get("limit"),
            "credit_used": cached.get("used"),
            "credit_status": cached.get("status", "unavailable"),
            "credit_stale": bool(cached.get("stale")),
            "credit_updated_at": cached.get("last_confirmed_at") or cached.get("updated_at"),
            "credit_source": cached.get("source", ""),
            "last_error": cached.get("last_error") or cached.get("message", ""),
            "logs": list(cached.get("logs") or []),
        }

    def environment(self) -> dict[str, Any]:
        executor, woo, installer = self.executor, self.executor.woo, self.executor.installer
        woo_configured = bool(getattr(woo, "base", "") and all(getattr(woo, "auth", ("", ""))))
        ssh = bool(getattr(installer, "host", "") and getattr(installer, "user", "") and getattr(installer, "root", ""))
        local = bool(getattr(installer, "root", None)) if not hasattr(installer, "host") else False
        plugin = self._plugintheme_environment()
        source_configured = bool(
            get_source_session("ultrapackv2") is not None
            or plugin["configured"]
            or os.getenv("SCRAPER_ULTRAPACK_COOKIES_JSON", "").strip()
            or os.getenv("SCRAPER_ULTRAPACK_HEADERS_JSON", "").strip()
        )
        validated = self.environment_validation
        woo_valid = bool(validated.get("woocommerce", {}).get("ok"))
        storage_valid = bool(validated.get("storage", {}).get("ok"))
        source_valid = bool(validated.get("source", {}).get("ok"))
        checks = [
            {"key": "woocommerce", "label": "WooCommerce", "state": "ok" if woo_valid else "attention", "value": "VALIDADO" if woo_valid else "CONFIGURADO / NÃO VALIDADO" if woo_configured else "NÃO CONFIGURADO", "detail": validated.get("woocommerce", {}).get("message", "")},
            {"key": "source", "label": "Fonte autenticada", "state": "ok" if source_valid else "attention", "value": "VALIDADA" if source_valid else "CONFIGURADA / SESSÃO NÃO VALIDADA" if source_configured else "NÃO CONFIGURADA", "detail": validated.get("source", {}).get("message", "")},
            {"key": "storage", "label": "Armazenamento de destino", "state": "ok" if storage_valid else "blocked", "value": "VALIDADO" if storage_valid else "CONFIGURADO / NÃO VALIDADO" if ssh or local else "NÃO CONFIGURADO", "detail": validated.get("storage", {}).get("message", "")},
            {"key": "individual", "label": "Execução individual", "state": "ok" if executor.enabled else "blocked", "value": "HABILITADA" if executor.enabled else "DESABILITADA"},
            {"key": "woo_write", "label": "WooCommerce escrita", "state": "ok" if woo_valid and storage_valid and executor.enabled else "blocked", "value": "HABILITADA" if woo_valid and storage_valid and executor.enabled else "DESABILITADA"},
        ]
        return {"ok": True, "checks": checks, "attention_count": sum(item["state"] != "ok" for item in checks), "plugintheme": plugin, "allowed_product_count": len(executor.allowed_product_ids)}

    def verify_environment(self) -> dict[str, Any]:
        validation: dict[str, Any] = {}
        try:
            result = self.executor.woo.check_connection()
            validation["woocommerce"] = {"ok": bool(result.get("ok")), "message": "Leitura autenticada do WooCommerce confirmada."}
        except Exception as error:
            validation["woocommerce"] = {"ok": False, "message": str(error)}
        try:
            result = self.executor.installer.check()
            validation["storage"] = {"ok": bool(result.get("ok")), "message": str(result.get("message") or "")}
        except Exception as error:
            validation["storage"] = {"ok": False, "message": str(error)}

        source_results: list[dict[str, Any]] = []
        plugin_account = get_source_account("plugintheme")
        public_logs = ["PluginTheme: configuração encontrada.", "Perfil carregado.", "Validando sessão..."]
        if self.credits is None:
            plugin_result = {"ok": False, "authenticated": False, "status": "not_validated", "message": "Serviço canônico de créditos indisponível.", "logs": []}
        else:
            try:
                plugin_result = self.credits.refresh("plugintheme", plugin_account)
            except Exception as error:
                plugin_result = {"ok": False, "authenticated": False, "status": "invalid", "message": str(error), "logs": []}
        authenticated = bool(plugin_result.get("authenticated"))
        if authenticated:
            set_source_state("plugintheme", "validated", plugin_account)
            public_logs.extend(["Sessão autenticada confirmada.", "Consultando créditos..."])
            if plugin_result.get("credits") is not None:
                public_logs.append(f"Créditos disponíveis: {int(plugin_result['credits'])}.")
            else:
                public_logs.append("Autenticação confirmada, mas o saldo não foi localizado.")
        else:
            set_source_state("plugintheme", "expired" if plugin_result.get("status") == "expired" else "not_validated", plugin_account)
            public_logs.append("Sessão inválida. Login necessário.")
        validation["plugintheme"] = {**plugin_result, "account_key": plugin_account, "authenticated": authenticated, "logs": public_logs + list(plugin_result.get("logs") or [])}
        if self.credits is not None:
            source_results.append({"source": "plugintheme", "ok": authenticated, "status": "validated" if authenticated else plugin_result.get("status", "not_validated"), "message": "Sessão PluginTheme autenticada confirmada." if authenticated else plugin_result.get("message", "Sessão PluginTheme não validada.")})

        candidates = self.repository.list(group="prepared", page=1, page_size=100)["items"]
        kinds = {str(item.get("source_kind") or "") for item in candidates if item.get("source_kind")}
        if self.credits is not None:
            kinds.discard("plugintheme")
        for kind in sorted(kinds):
            job = next(item for item in candidates if item.get("source_kind") == kind)
            try:
                source = self.executor.sources.get(kind)
                probe = getattr(source, "validate_access", None)
                if not callable(probe):
                    source.validate_authentication()
                    raise RuntimeError("A fonte não oferece preflight autenticado de leitura")
                details = probe(job)
                set_source_state(kind, "validated")
                source_results.append({"source": kind, "ok": True, "version": details.get("version"), "message": "Acesso autenticado confirmado."})
            except Exception as error:
                message = str(error)
                code = str(getattr(getattr(error, "error", None), "code", "") or "")
                missing = code == "authentication_missing" or "não configurada" in message.lower()
                expired = not missing and any(term in message.lower() for term in ("login", "expir", "401", "403"))
                status = "not_configured" if missing else "expired" if expired else "invalid"
                set_source_state(kind, status)
                source_results.append({"source": kind, "ok": False, "status": status, "message": message})

        source_ok = all(item["ok"] for item in source_results)
        validation["source"] = {"ok": source_ok, "status": "validated" if source_ok else next((item.get("status") for item in source_results if not item["ok"]), "invalid"), "message": "; ".join(f"{item['source']}: {item['message']}" for item in source_results)}
        self.environment_validation = validation
        return self.environment()

    def renew_plugintheme(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        account = str((payload or {}).get("account_key") or get_source_account("plugintheme"))
        clear_source_session("plugintheme", account_key=account)
        set_source_state("plugintheme", "not_validated", account)
        result = open_manual_session(account)
        self.environment_validation["source"] = {"ok": False, "status": "not_validated", "message": "Renovação PluginTheme aberta; conclua o login e verifique novamente."}
        return result

    def selection(self, payload: dict[str, Any]) -> dict[str, Any]:
        base = {"query": str(payload.get("query") or ""), "group": str(payload.get("group") or ""), "stage": str(payload.get("stage") or "")}
        first = self.repository.list(**base, page=1, page_size=100)
        items = list(first["items"])
        for page in range(2, first["pages"] + 1):
            items.extend(self.repository.list(**base, page=page, page_size=100)["items"])
        return {"ok": True, "items": items, "total": len(items)}

    def job(self, job_id: str) -> dict[str, Any]:
        return {"ok": True, "item": self.repository.get(job_id), "history": self.repository.history(job_id)}

    def execute(self, job_id: str) -> dict[str, Any]:
        return self.executor.execute(job_id)

    def retry(self, job_id: str) -> dict[str, Any]:
        return self.executor.execute(job_id)

    def batch_start(self, job_ids: list[str] | None = None) -> dict[str, Any]:
        ids = job_ids or [item["job_id"] for item in self.repository.list(group="prepared", page_size=100)["items"]]
        return {"ok": True, "batch": self.batch.start(ids)}

    def batch_control(self, action: str) -> dict[str, Any]:
        method = {"pause": self.batch.pause, "resume": self.batch.resume, "cancel": self.batch.cancel}[action]
        return {"ok": True, "batch": method()}
