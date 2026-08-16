from __future__ import annotations

import unittest
from pathlib import Path


class UpdateQueueUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = Path("app/static/panel.js").read_text(encoding="utf-8")
        cls.web = Path("app/web.py").read_text(encoding="utf-8")

    def test_filters_search_and_relationships_exist(self):
        for token in ("updates_status_filter", "updates_type_filter", "updates_search_filter",
                      "updates_version_filter", "updates_relationship_filter", "updates_clear_filters"):
            self.assertIn(token, self.js + self.web)

    def test_selection_all_filtered_and_counter_exist(self):
        for token in ("updates_select_page", "updates_select_filtered", "updates_clear_selection",
                      "updates_selected_count", "UPDATE_QUEUE.selected"):
            self.assertIn(token, self.js + self.web)

    def test_real_frontend_pagination_drives_visible_rows_and_page_selection(self):
        for token in ("updates_page_size", "updates_prev_page", "updates_next_page",
                      "UPDATE_QUEUE.pageSize", "UPDATE_QUEUE.workingFiltered.slice(start,start+UPDATE_QUEUE.pageSize)"):
            self.assertIn(token, self.js + self.web)
        self.assertNotIn("filtered.slice(0,100)", self.js)
        page_size = self.web.split('id="updates_page_size"', 1)[1][:180]
        self.assertIn('type="number"', page_size)
        self.assertIn('min="1"', page_size)
        self.assertIn('value="25"', page_size)
        self.assertIn("Math.min(parsed, LISTING_MAX_PAGE_SIZE)", self.js)

    def test_batch_is_sequential_and_failure_does_not_abort_loop(self):
        start = self.js.index("async function runUpdateBatch")
        body = self.js[start:start + 1800]
        self.assertIn("for(const id of ids)", body)
        self.assertIn("catch(error)", body)
        self.assertIn("stats.errors", body)
        self.assertNotIn("Promise.all", body)
        self.assertIn('postJson("/atualizacoes/preparar"', body)
        self.assertIn('postJson("/atualizacoes/plano"', body)

    def test_preparation_and_plan_are_one_user_action(self):
        combined = self.js + self.web
        self.assertIn("Preparar e gerar planos", self.web)
        self.assertIn("Preparar e gerar plano", self.js)
        self.assertNotIn('id="updates_plan_selected"', self.web)
        self.assertNotIn('<button class="btn-secondary update-plan"', self.js)

    def test_no_batch_execution_action(self):
        self.assertNotIn("Executar selecionados", self.js + self.web)
        self.assertNotIn("Executar todos", self.js + self.web)

    def test_execution_banner_uses_backend_whitelist_without_hardcoded_product(self):
        self.assertIn("execution_allowed_product_ids", self.js)
        self.assertIn("produtos permitidos:", self.js)
        self.assertNotIn("restrita ao WooCommerce #94567", self.js)
        self.assertNotIn('allowedIds = [94567]', self.js)

    def test_details_are_collapsed_and_lazy(self):
        self.assertIn('update-preview-slot hidden', self.js)
        self.assertIn('aria-expanded="false"', self.js)
        self.assertIn("if(!open && !slot.dataset.rendered)", self.js)

    def test_individual_modal_requires_exact_product_confirmation(self):
        self.assertIn("EXECUTAR ${job.woo_product_id}", self.js)
        self.assertIn("update_execute_modal", self.web)
        self.assertIn("Esta ação alterará o ZIP de produção e pt_versao", self.web)
        for label in ("Arquivo de produção", "SHA atual", "SHA novo", "Backup planejado"):
            self.assertIn(label, self.js)

    def test_execution_polling_is_scoped_to_job_log(self):
        self.assertIn("/atualizacoes/logs?job_id=", self.js)
        self.assertNotIn('getJson("/atualizacoes/logs")', self.js)

    def test_completed_card_is_terminal_and_has_audit_details(self):
        self.assertIn('const completed = job.state === "completed"', self.js)
        self.assertIn('const cycleActions = completed ? ""', self.js)
        self.assertIn("Resultado concluído", self.js)
        self.assertIn("Logs finais", self.js)
        self.assertIn('const bulkSelectable=j=>!["queued","executing","completed"', self.js)
        self.assertIn("Ciclo concluído não pode ser preparado novamente", self.web)
        self.assertIn("Ciclo concluído não pode gerar outro plano", self.web)
        for label in ("Versão anterior", "Versão instalada", "Versão da comparação",
                      "SHA anterior", "SHA novo", "Backup", "Identificador do plano"):
            self.assertIn(label, self.js)

    def test_history_is_collapsed_searchable_and_paginated(self):
        self.assertIn('updates-history-accordion" id="updates_history_accordion"', self.web)
        self.assertNotIn('id="updates_history_accordion" open', self.web)
        for token in ("updates_history_search", "updates_history_prev", "updates_history_next",
                      "UPDATE_QUEUE.historyPage", "historyPageSize:LISTING_DEFAULT_PAGE_SIZE"):
            self.assertIn(token, self.js + self.web)

    def test_update_lists_are_split_into_titled_cards_with_conditional_controls(self):
        combined = self.js + self.web
        for token in (
            "updates-overview-card", "updates-environment-card", "updates-working-card",
            "updates-queue-section", "updates-card-section", "updates_working_controls",
            "updates_queue_list_controls", "updates_history_controls", "updates_queue_search",
            "updates_queue_status_filter", "updates_queue_prev", "updates_queue_next",
            "updates_history_status_filter", "workingFiltered", "queuePage",
        ):
            self.assertIn(token, combined)
        self.assertIn('classList.toggle("hidden",baseWorking.length===0)', self.js)
        self.assertIn('classList.toggle("hidden",allItems.length===0)', self.js)

    def test_history_has_classic_tabs_download_and_persistent_delete(self):
        combined = self.js + self.web
        for token in ("updates-history-tabs", "role=\"tablist\"", "updates_history_download",
                      "updates_history_delete", "/atualizacoes/historico/baixar",
                      "/atualizacoes/historico/apagar"):
            self.assertIn(token, combined)
        runtime = Path("app/operations/runtime.py").read_text(encoding="utf-8")
        self.assertIn("clear_update_history", runtime)
        self.assertIn("dismissed_history", runtime)
        self.assertIn("updates-disclosure-chevron", self.js + self.web)
        self.assertIn("▸", self.web)
        self.assertEqual(self.web.count('class="updates-disclosure-chevron"'), 3)

    def test_preparation_has_loading_and_blocked_items_remain_retryable(self):
        combined = self.js + self.web
        for token in ('button.setAttribute("aria-busy", "true")', "Preparando e gerando plano",
                      "updates-batch-progress", "updateBlockedReason", "Concluídos (${completedCount})",
                      "Erros (${errorCount})"):
            self.assertIn(token, combined)
        excluded = self.js.split("const excludedStates=", 1)[1].split(";", 1)[0]
        self.assertNotIn('"blocked"', excluded)
        batch = self.js.split("async function runUpdateBatch", 1)[1].split("function openUpdateExecuteModal", 1)[0]
        self.assertIn('progress.textContent=', batch)
        self.assertIn('progress.classList.add("is-complete")', batch)

    def test_plan_ready_actions_follow_backend_eligibility(self):
        for token in ("selectedEligible", "enqueueSelected.disabled", 'job.state === "plan_ready"',
                      "job.execution_eligible === true", "update-enqueue-one", "update-execute"):
            self.assertIn(token, self.js)
        css = Path("app/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".main-tabs-nav{border-bottom:none!important}", css)
        self.assertIn(".main-tabs-nav .tab-btn.is-active::after{content:none!important", css)

    def test_plugintheme_session_action_lives_inside_diagnostic_and_reports_cookies(self):
        environment = self.web.split('class="card updates-card-section updates-environment-card', 1)[1].split('id="updates_filters_title"', 1)[0]
        details = environment.split('id="updates_environment_details"', 1)[1]
        self.assertIn('id="plugintheme_session_renew"', details)
        self.assertIn('id="plugintheme_cookie_status"', details)
        self.assertIn('data-update-accordion-kind="environment"', environment)
        self.assertIn('aria-expanded="false"', environment)
        self.assertIn('standard-update-accordion-card is-collapsed', environment)
        self.assertIn("plugintheme_cookies", self.js)
        manual = Path("app/integrations/plugintheme_manual_session.py").read_text(encoding="utf-8")
        self.assertIn("def plugintheme_cookie_diagnostic", manual)
        self.assertIn("nunca expõe nomes ou valores", manual)

    def test_async_modals_and_collect_queue_use_spinner_feedback(self):
        for token in ("modal-loading-overlay", "Carregando catálogos e produtos",
                      "Carregando dados da lista", "Pesquisando produtos", "Carregando fila"):
            self.assertIn(token, self.js + self.web)

    def test_summary_cards_have_accessible_help(self):
        self.assertIn('summaryCard=(key,label,value)', self.js)
        self.assertIn('aria-label="Ajuda sobre ${label}"', self.js)
        self.assertIn('data-tooltip="${escapeHtml(help[key])}"', self.js)
        css = Path("app/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".updates-operations-center{overflow:visible}", css)
        self.assertIn(".updates-summary>div:first-child .comparison-help::after", css)

    def test_named_update_queues_are_selectable_and_persisted_as_csv(self):
        for token in ("updates_queue_select", "open_update_lists_modal", "update_lists_modal",
                      "update_lists_new_name", "update_lists_create", "data-update-list-action",
                      "/atualizacoes/filas/criar", "/atualizacoes/filas/selecionar",
                      "/atualizacoes/filas/renomear", "/atualizacoes/filas/apagar",
                      "/atualizacoes/filas/limpar", "Limpar itens", "Padrão"):
            self.assertIn(token, self.js + self.web)
        runtime = Path("app/operations/runtime.py").read_text(encoding="utf-8")
        self.assertIn("_persist_queue_spreadsheets", runtime)
        self.assertIn('encoding="utf-8-sig"', runtime)
        self.assertIn("last_completed_at", runtime)
        self.assertIn("rename_update_queue", runtime)
        self.assertIn("delete_update_queue", runtime)
        self.assertIn("clear_update_queue", runtime)

    def test_active_queue_switch_clears_stale_state_and_loads_real_items(self):
        self.assertIn("async function selectAndRefreshUpdateQueue", self.js)
        body = self.js.split("async function selectAndRefreshUpdateQueue", 1)[1].split("function startUpdateQueuePolling", 1)[0]
        self.assertIn("UPDATE_QUEUE.jobs = []", body)
        self.assertIn("UPDATE_QUEUE.queuePage = 1", body)
        self.assertIn('getJson("/atualizacoes/jobs")', body)
        self.assertIn("selected?.details?.items", body)
        render = self.js.split("function renderOperationalQueue", 1)[1].split("function renderUpdateListsManager", 1)[0]
        self.assertIn('normalizeText(job.queue_name,"default")===queueName', render)
        self.assertNotIn('job.state==="queued"&&', render)

    def test_manual_history_refreshes_and_shows_wordpress_audit(self):
        self.assertIn("async function refreshUpdateRuntime", self.js)
        self.assertIn("Manual pelo WordPress", self.js)
        self.assertIn("manual_requested_at", self.js)
        self.assertIn('tab_panel_atualizacoes', self.js)

    def test_update_lists_use_rename_and_preview_modals(self):
        combined = self.js + self.web
        for token in ("update_list_rename_modal", "update_list_rename_confirm",
                      "update_list_preview_modal", "update_list_preview_rows",
                      "data-update-list-action=\"preview\"", "/atualizacoes/filas/detalhes"):
            self.assertIn(token, combined)
        runtime = Path("app/operations/runtime.py").read_text(encoding="utf-8")
        self.assertIn("def update_queue_details", runtime)

    def test_header_uses_image_after_clean_title(self):
        self.assertIn('class="page-brand-mascot"', self.web)
        self.assertIn('src="/mascote.webp"', self.web)
        self.assertIn('<h1>__HEADER_TITLE__</h1><img class="page-brand-title-image" src="/emoji.webp"', self.web)
        self.assertIn('return "CrapScraper"', self.web)
        self.assertNotIn('return "💩 CrapScraper"', self.web)


if __name__ == "__main__": unittest.main()
