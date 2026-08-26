from __future__ import annotations

import threading
from contextlib import suppress
from typing import Any, Callable

from app.app import ScraperApp
import app.web as web


_INSTALLED = False
_BASE_LOAD_INITIAL_SUMMARY: Callable[..., dict[str, Any]] | None = None
_BASE_PREPARE_APP: Callable[..., Any] | None = None
_BASE_CREATE_SERVER: Callable[..., Any] | None = None
_BASE_RENDER: Callable[..., str] | None = None
_STARTUP_PHASE = True
_HYDRATION_LOCK = threading.RLock()
_HYDRATION_STARTED: set[int] = set()

_PROCESS_HISTORY_START = '''  function start() {
    installStyles();
    ensureCreditsNode();
    decorateModal();
    observeUi();
    window.setTimeout(pollCredits, 900);
    window.setInterval(pollCredits, 60000);
    window.setTimeout(pollBackendHistory, 1400);
    window.setInterval(pollBackendHistory, 2600);
    window.setInterval(() => { ensureCreditsNode(); decorateModal(); }, 1200);
  }'''
_PROCESS_HISTORY_START_WITHOUT_OBSERVER = '''  function start() {
    installStyles();
    ensureCreditsNode();
    decorateModal();
    // Sem MutationObserver global: o polling leve abaixo mantém créditos e histórico atualizados.
    window.setTimeout(pollCredits, 900);
    window.setInterval(pollCredits, 60000);
    window.setTimeout(pollBackendHistory, 1400);
    window.setInterval(pollBackendHistory, 2600);
    window.setInterval(() => { ensureCreditsNode(); decorateModal(); }, 1200);
  }'''
_PROCESS_HISTORY_LAZY_START = '''  function processMonitorVisible() {
    const overlay = $("#cs_processes_overlay");
    return !!overlay && !overlay.classList.contains("hidden");
  }

  function activateProcessMonitor() {
    pollCredits();
    pollBackendHistory();
    decorateModal();
  }

  function start() {
    installStyles();
    ensureCreditsNode();
    decorateModal();
    $("#cs_processes_button")?.addEventListener("click", () => {
      window.setTimeout(activateProcessMonitor, 0);
    });
    window.setInterval(() => { if (processMonitorVisible()) pollBackendHistory(); }, 5000);
    window.setInterval(() => { if (processMonitorVisible()) pollCredits(); }, 60000);
    window.setInterval(() => { if (processMonitorVisible()) decorateModal(); }, 1500);
    if (processMonitorVisible()) window.setTimeout(activateProcessMonitor, 0);
  }'''


def _memory_snapshot(app: Any) -> dict[str, Any]:
    """Retorna somente o estado já em memória; nunca varre catálogos/logs."""
    snapshot = getattr(app, "snapshot", None)
    if not callable(snapshot):
        return {}
    try:
        return dict(snapshot(max_logs=0) or {})
    except TypeError:
        try:
            return dict(snapshot() or {})
        except Exception:
            return {}
    except Exception:
        return {}


def _fast_load_initial_summary(self: ScraperApp) -> dict[str, Any]:
    """Durante o boot não bloqueia o socket lendo catálogos grandes do disco."""
    if _STARTUP_PHASE:
        return _memory_snapshot(self)
    if _BASE_LOAD_INITIAL_SUMMARY is None:
        return _memory_snapshot(self)
    return _BASE_LOAD_INITIAL_SUMMARY(self)


def _fast_prepare_app(app: ScraperApp | Any | None = None) -> ScraperApp | Any:
    """Prepara somente o contexto ativo antes de abrir a porta HTTP.

    A implementação anterior percorria todos os runs e executava
    ``load_initial_summary`` em cada um, mesmo depois de o ScraperApp principal já
    ter feito a mesma leitura no construtor. Em catálogos grandes isso repetia
    leitura de CSV/JSON/logs antes de o navegador conseguir conectar.
    """
    if app is not None:
        resolved_target = app
    else:
        resolved_target = web._ensure_manager(None)

    manager = web._ensure_manager(resolved_target)
    with suppress(Exception):
        primary = web._get_primary_app(manager)
        refresh = getattr(primary, "refresh_slots_state", None)
        if callable(refresh):
            refresh()
    return resolved_target


def _hydrate_primary_summary_async(resolved_target: Any) -> bool:
    if _BASE_LOAD_INITIAL_SUMMARY is None:
        return False

    manager = web._ensure_manager(resolved_target)
    key = id(manager)
    with _HYDRATION_LOCK:
        if key in _HYDRATION_STARTED:
            return False
        _HYDRATION_STARTED.add(key)

    def run() -> None:
        # Entrega primeiro o socket/página. A hidratação pesada começa logo depois
        # e atualiza o mesmo RuntimeState que a UI já consulta normalmente.
        threading.Event().wait(0.35)
        try:
            primary = web._get_primary_app(manager)
            _BASE_LOAD_INITIAL_SUMMARY(primary)
        except Exception as error:
            with suppress(Exception):
                web._boot_log(
                    "Resumo inicial em segundo plano não pôde ser carregado: "
                    f"{type(error).__name__}: {error}"
                )

    threading.Thread(
        target=run,
        name="startup-summary-hydration",
        daemon=True,
    ).start()
    return True


def _create_server_fast(*args: Any, **kwargs: Any) -> Any:
    global _STARTUP_PHASE
    if _BASE_CREATE_SERVER is None:
        raise RuntimeError("Criador de servidor base indisponível")

    result = _BASE_CREATE_SERVER(*args, **kwargs)
    _STARTUP_PHASE = False
    try:
        resolved_target = result[0]
    except Exception:
        resolved_target = args[0] if args else kwargs.get("app")
    _hydrate_primary_summary_async(resolved_target)
    return result


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)

    # A consulta de créditos autentica PluginTheme/UltraPack e pode abrir/reler
    # perfis do navegador. Ela não pertence ao caminho de abertura do painel.
    # Aplique a correção como camada FINAL de HTML para não depender da ordem das
    # policies anteriores que também refinam o modal Processos.
    html = html.replace(_PROCESS_HISTORY_START, _PROCESS_HISTORY_LAZY_START)
    html = html.replace(_PROCESS_HISTORY_START_WITHOUT_OBSERVER, _PROCESS_HISTORY_LAZY_START)
    return html


def install_startup_fast_path_policy() -> None:
    global _INSTALLED, _BASE_LOAD_INITIAL_SUMMARY, _BASE_PREPARE_APP
    global _BASE_CREATE_SERVER, _BASE_RENDER
    if _INSTALLED:
        return

    # O primeiro load_initial_summary ocorre dentro de ScraperApp.__init__ antes
    # de web.create_server. Durante esta janela ele deve ser apenas um snapshot em
    # memória. Depois que o socket é criado, chamadas normais voltam ao método base.
    _BASE_LOAD_INITIAL_SUMMARY = ScraperApp.load_initial_summary
    ScraperApp.load_initial_summary = _fast_load_initial_summary

    # Elimina a segunda (e, em multi-run, múltiplas) hidratação síncrona feita por
    # web.prepare_app no caminho crítico de abertura.
    _BASE_PREPARE_APP = web.prepare_app
    web.prepare_app = _fast_prepare_app

    # create_server é resolvido dinamicamente por web.serve; portanto o wrapper
    # funciona mesmo que main.py já tenha importado ``serve`` anteriormente.
    _BASE_CREATE_SERVER = web.create_server
    web.create_server = _create_server_fast

    # Finaliza a proteção também no frontend: nada que dependa de sessão remota
    # deve rodar só porque o painel foi aberto.
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page

    _INSTALLED = True
