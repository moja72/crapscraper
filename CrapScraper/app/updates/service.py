from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from app.comparison import decisions
from app.plugintheme_profile import open_manual_session, profile_diagnostic
from app.updates.adapters import WooCommerceConnectivityError, normalize_version, version_metadata
from app.updates.batch import UpdateBatchService
from app.updates.executor import UpdateExecutor
from app.updates.logging import safe_message
from app.updates.repository import UpdateRepository
from app.updates.source_auth import (
    clear_source_session,
    get_source_account,
    get_source_diagnostic,
    get_source_session,
    set_source_state,
    source_state,
)


class UpdateExecutionBlocked(RuntimeError):
    def __init__(self, blockers: list[dict[str, str]]):
        self.blockers = blockers
        super().__init__("; ".join(item["message"] for item in blockers))


UPDATE_PROGRESS_STAGES = (
    ("prepared", "Aguardando execucao"),
    ("validating", "Validando WooCommerce"),
    ("authenticating", "Validando autenticacao da fonte"),
    ("downloading", "Baixando arquivo"),
    ("staging", "Validando ZIP"),
    ("backing_up", "Criando backup"),
    ("installing", "Instalando nova versao"),
    ("verifying_artifact", "Validando arquivo instalado"),
    ("updating_woocommerce", "Atualizando pt_versao"),
    ("completed", "Atualizacao concluida"),
)
UPDATE_PROGRESS_INDEX = {stage: index for index, (stage, _label) in enumerate(UPDATE_PROGRESS_STAGES)}
UPDATE_PROGRESS_LABELS = dict(UPDATE_PROGRESS_STAGES)


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
            sort_by=str(payload.get("sort_by") or "date"),
            sort_order=str(payload.get("sort_order") or "desc"),
        )
        result["items"] = [self._with_execution(item) for item in result["items"]]
        return {"ok": True, **result, "batch": self.batch.state(), "database": str(self.repository.path)}

    @staticmethod
    def _source_label(kind: str) -> str:
        return {"ultrapackv2": "UltraPackV2", "plugintheme": "PluginTheme"}.get(kind, kind or "desconhecida")

    @staticmethod
    def _source_summary(sources: dict[str, dict[str, Any]], required: set[str]) -> dict[str, Any]:
        relevant = required or set(sources)
        results = [sources[kind] for kind in sorted(relevant) if kind in sources]
        missing = sorted(relevant - set(sources))
        ok = bool(relevant) and not missing and all(bool(item.get("ok")) for item in results)
        messages = [f"{item['source']}: {item.get('message') or 'sem diagnóstico'}" for item in results]
        messages.extend(f"{kind}: validação não executada" for kind in missing)
        failure = next((item for item in results if not item.get("ok")), None)
        return {
            "ok": ok,
            "status": "validated" if ok else str((failure or {}).get("status") or "not_validated"),
            "message": "; ".join(messages) or "Nenhuma fonte necessária foi validada.",
        }

    def _execution(self, job: dict[str, Any]) -> dict[str, Any]:
        blockers: list[dict[str, str]] = []
        state = str(job.get("state") or "")
        stage = str(job.get("stage") or "")
        action = "retry" if state == "error" else "execute" if state == "ready" else "none"

        if state == "running":
            blockers.append({"code": "job_running", "message": "Job já está em execução."})
        elif state == "success":
            blockers.append({"code": "job_completed", "message": "Atualização já concluída."})
        elif state not in {"ready", "error"}:
            blockers.append({"code": "job_state_invalid", "message": f"Estado {state or 'ausente'} não permite execução."})
        elif state == "ready" and stage != "prepared":
            blockers.append({"code": "job_not_prepared", "message": f"Job ainda não está preparado (etapa: {stage or 'ausente'})."})
        elif state == "error" and (job.get("error") or {}).get("recoverable") is False:
            blockers.append({"code": "job_not_recoverable", "message": "A falha exige intervenção antes de uma nova tentativa."})

        if state not in {"ready", "error"} or blockers:
            return {"allowed": False, "action": action, "blockers": blockers}

        if int(job.get("woo_product_id") or 0) <= 0 or not job.get("source_url") or not job.get("source_version"):
            blockers.append({"code": "job_incomplete", "message": "Job incompleto: produto, URL e versão são obrigatórios."})
        if not self.executor.enabled:
            blockers.append({"code": "execution_disabled", "message": "Execução desabilitada pelo gate de segurança."})
        allowed_ids = self.executor.allowed_product_ids
        if allowed_ids and int(job.get("woo_product_id") or 0) not in allowed_ids:
            blockers.append({
                "code": "product_not_allowed",
                "message": f"Execução bloqueada pelo gate de segurança: produto WooCommerce #{job.get('woo_product_id')} não autorizado.",
            })

        validated = self.environment_validation
        for key, code, label in (
            ("woocommerce", "woocommerce", "WooCommerce"),
            ("storage", "storage", "Armazenamento de destino"),
        ):
            result = validated.get(key)
            if not result:
                blockers.append({"code": f"{code}_not_validated", "message": f"{label} não validado. Execute Verificar pré-requisitos."})
            elif not result.get("ok"):
                detail = str(result.get("message") or "indisponível")
                blockers.append({"code": f"{code}_unavailable", "message": f"{label} não pôde ser validado: {detail}"})

        kind = str(job.get("source_kind") or "")
        source = (validated.get("sources") or {}).get(kind)
        source_label = self._source_label(kind)
        if not source:
            blockers.append({"code": "source_not_validated", "message": f"Fonte {source_label} não validada. Execute Verificar pré-requisitos."})
        elif not source.get("ok"):
            detail = str(source.get("message") or "autenticação indisponível")
            blockers.append({"code": "source_unavailable", "message": f"Fonte {source_label} não autenticada: {detail}"})
        return {"allowed": not blockers, "action": action, "blockers": blockers}

    def _with_execution(self, job: dict[str, Any]) -> dict[str, Any]:
        item = dict(job)
        item["execution"] = self._execution(item)
        item["progress"] = self._progress(item)
        return item

    @staticmethod
    def _progress(job: dict[str, Any]) -> dict[str, Any]:
        stage=str(job.get("stage") or "prepared")
        state=str(job.get("state") or "ready")
        total=len(UPDATE_PROGRESS_STAGES)-1
        if state=="success":step=total
        else:step=UPDATE_PROGRESS_INDEX.get(stage, max(0, total-1 if state=="error" else 0))
        if stage in {"rolling_back","rolled_back","rollback_required"}:
            label={"rolling_back":"Executando rollback","rolled_back":"Rollback concluido","rollback_required":"Rollback requer intervencao"}[stage]
        elif stage=="already_current":label="Destino ja estava atualizado"
        else:label=UPDATE_PROGRESS_LABELS.get(stage, stage.replace("_"," ").strip().capitalize() or "Aguardando")
        return {
            "active": state=="running",
            "complete": state=="success",
            "failed": state=="error",
            "stage": stage,
            "label": label,
            "step": step,
            "total": total,
            "logs": [str(line) for line in list(job.get("logs") or [])[-6:]],
            "updated_at": str(job.get("updated_at") or ""),
        }

    def reconcile_job(self, job_id: str) -> dict[str, Any]:
        job=self.repository.get(job_id)
        if job["state"]=="success":return {"ok":True,"reconciled":False,"reason":"already_success","item":self._with_execution(job)}
        if job["state"]!="error":return {"ok":True,"reconciled":False,"reason":"not_error","item":self._with_execution(job)}
        attempt=self.repository.latest_attempt(job_id)
        artifact_sha=str((attempt or {}).get("artifact_sha256") or "")
        if not artifact_sha:return {"ok":True,"reconciled":False,"reason":"artifact_hash_missing","item":self._with_execution(job)}
        reader=getattr(self.executor.woo,"get_product_fresh",None) or self.executor.woo.get_product
        product=reader(int(job["woo_product_id"]));metadata=version_metadata(product)
        expected=normalize_version(job["source_version"])
        if metadata["status"]!="single" or normalize_version(metadata.get("value"))!=expected:
            return {"ok":True,"reconciled":False,"reason":"version_mismatch","expected":expected,"observed":metadata.get("value") if metadata["status"]=="single" else metadata["status"],"item":self._with_execution(job)}
        prepare=getattr(self.executor.woo,"prepare_job",None)
        if callable(prepare):prepare(job)
        if not self.executor.installer.validate(job,artifact_sha):
            return {"ok":True,"reconciled":False,"reason":"artifact_hash_mismatch","expected_sha256":artifact_sha,"item":self._with_execution(job)}
        message=f"Estado reconciliado: versao alvo {expected} e ZIP SHA-256 {artifact_sha[:12]}... confirmados."
        item=self.repository.reconcile_success(job_id,message)
        return {"ok":True,"reconciled":True,"reason":"target_confirmed","item":self._with_execution(item)}

    def reconcile_errors(self) -> dict[str, Any]:
        first=self.repository.list(group="error",page=1,page_size=100,sort_by="date",sort_order="desc")
        jobs=list(first["items"])
        for page in range(2,first["pages"]+1):jobs.extend(self.repository.list(group="error",page=page,page_size=100,sort_by="date",sort_order="desc")["items"])
        results=[]
        for job in jobs:
            try:results.append({"job_id":job["job_id"],**self.reconcile_job(job["job_id"])})
            except Exception as error:results.append({"job_id":job["job_id"],"ok":False,"reconciled":False,"reason":"verification_failed","message":safe_message(error)})
        return {"ok":all(item.get("ok") for item in results),"checked":len(results),"reconciled":sum(bool(item.get("reconciled")) for item in results),"results":results}

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
            "credit_total_downloads": cached.get("total_downloads"),
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
            attempts = int(result.get("attempts") or 1)
            recovered = bool(result.get("recovered"))
            message = "Leitura autenticada do WooCommerce confirmada."
            if recovered:
                message += f" Conectividade recuperada após {attempts} tentativas limitadas."
            validation["woocommerce"] = {"ok": bool(result.get("ok")), "message": message, "details": result}
        except WooCommerceConnectivityError as error:
            validation["woocommerce"] = {
                "ok": False,
                "message": error.diagnosis,
                "details": {"host": error.host, "error_type": error.error_type, "attempts": error.attempts},
            }
        except Exception as error:
            validation["woocommerce"] = {"ok": False, "message": safe_message(error)}
        try:
            result = self.executor.installer.check()
            validation["storage"] = {"ok": bool(result.get("ok")), "message": str(result.get("message") or "")}
        except Exception as error:
            validation["storage"] = {"ok": False, "message": safe_message(error)}

        source_results: list[dict[str, Any]] = []
        plugin_account = get_source_account("plugintheme")
        public_logs = ["PluginTheme: configuração encontrada.", "Perfil carregado.", "Validando sessão..."]
        if self.credits is None:
            plugin_result = {"ok": False, "authenticated": False, "status": "not_validated", "message": "Serviço canônico de créditos indisponível.", "logs": []}
        else:
            try:
                plugin_result = self.credits.refresh("plugintheme", plugin_account)
            except Exception as error:
                plugin_result = {"ok": False, "authenticated": False, "status": "invalid", "message": safe_message(error), "logs": []}
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
        candidate_kinds = {str(item.get("source_kind") or "") for item in candidates if item.get("source_kind")}
        kinds = set(candidate_kinds)
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
                message = safe_message(error)
                code = str(getattr(getattr(error, "error", None), "code", "") or "")
                missing = code == "authentication_missing" or "não configurada" in message.lower()
                expired = not missing and any(term in message.lower() for term in ("login", "expir", "401", "403"))
                status = "not_configured" if missing else "expired" if expired else "invalid"
                set_source_state(kind, status)
                source_results.append({"source": kind, "ok": False, "status": status, "message": message})

        source_by_kind = {str(item["source"]): item for item in source_results}
        required_sources = candidate_kinds or set(source_by_kind)
        validation["sources"] = source_by_kind
        validation["required_sources"] = sorted(required_sources)
        validation["source"] = self._source_summary(source_by_kind, required_sources)
        self.environment_validation = validation
        result=self.environment()
        if validation.get("woocommerce",{}).get("ok") and validation.get("storage",{}).get("ok"):
            result["reconciliation"]=self.reconcile_errors()
        return result

    def renew_plugintheme(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        account = str((payload or {}).get("account_key") or get_source_account("plugintheme"))
        clear_source_session("plugintheme", account_key=account)
        set_source_state("plugintheme", "not_validated", account)
        result = open_manual_session(account)
        sources = self.environment_validation.setdefault("sources", {})
        sources["plugintheme"] = {"source": "plugintheme", "ok": False, "status": "not_validated", "message": "Renovação PluginTheme aberta; conclua o login e verifique novamente."}
        required = set(self.environment_validation.get("required_sources") or sources)
        self.environment_validation["source"] = self._source_summary(sources, required)
        return result

    def selection(self, payload: dict[str, Any]) -> dict[str, Any]:
        base = {"query": str(payload.get("query") or ""), "group": str(payload.get("group") or ""), "stage": str(payload.get("stage") or ""), "sort_by":str(payload.get("sort_by") or "date"),"sort_order":str(payload.get("sort_order") or "desc")}
        first = self.repository.list(**base, page=1, page_size=100)
        items = list(first["items"])
        for page in range(2, first["pages"] + 1):
            items.extend(self.repository.list(**base, page=page, page_size=100)["items"])
        return {"ok": True, "items": [self._with_execution(item) for item in items], "total": len(items)}

    def job(self, job_id: str) -> dict[str, Any]:
        return {"ok": True, "item": self._with_execution(self.repository.get(job_id)), "history": self.repository.history(job_id)}

    def _require_execution_environment(self) -> None:
        for key, label in (("woocommerce", "WooCommerce"), ("storage", "armazenamento")):
            result = self.environment_validation.get(key)
            if result and result.get("ok") is False:
                detail = safe_message(RuntimeError(str(result.get("message") or "não validado")))
                raise RuntimeError(f"Pré-requisito {label} indisponível: {detail}")

    def _require_job_execution(self, job_id: str) -> dict[str, Any]:
        job = self.repository.get(job_id)
        execution = self._execution(job)
        if not execution["allowed"]:
            raise UpdateExecutionBlocked(execution["blockers"])
        return job

    def execute(self, job_id: str) -> dict[str, Any]:
        self._require_execution_environment()
        self._require_job_execution(job_id)
        return self.executor.execute(job_id)

    def retry(self, job_id: str) -> dict[str, Any]:
        self._require_execution_environment()
        self._require_job_execution(job_id)
        return self.executor.execute(job_id)

    def batch_start(self, job_ids: list[str] | None = None) -> dict[str, Any]:
        self._require_execution_environment()
        ids = job_ids or [item["job_id"] for item in self.repository.list(group="prepared", page_size=100)["items"]]
        if not ids:
            raise ValueError("Nenhum job preparado foi selecionado para execução.")
        blocked: list[dict[str, str]] = []
        for job_id in dict.fromkeys(ids):
            job = self.repository.get(job_id)
            execution = self._execution(job)
            if not execution["allowed"]:
                for item in execution["blockers"]:
                    blocked.append({**item, "message": f"{job['product_name']}: {item['message']}"})
        if blocked:
            raise UpdateExecutionBlocked(blocked)
        return {"ok": True, "batch": self.batch.start(ids)}

    def batch_control(self, action: str) -> dict[str, Any]:
        method = {"pause": self.batch.pause, "resume": self.batch.resume, "cancel": self.batch.cancel}[action]
        return {"ok": True, "batch": method()}
