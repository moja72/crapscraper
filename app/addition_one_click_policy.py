from __future__ import annotations

import base64
import mimetypes
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import app.web as web
import app.new_product_workflow_policy as additions
import app.chatgpt_browser_assist as chatgpt
from app.integrations.wordpress import sanitize_text

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_SERVER: Any = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "addition_one_click.js"
_TASK_LOCK = threading.RLock()
_TASKS: dict[str, dict[str, Any]] = {}
_MAX_LOGS = 80


def _now_text() -> str:
    return datetime.now().astimezone().strftime("%H:%M:%S")


def _task(job_id: str) -> dict[str, Any]:
    with _TASK_LOCK:
        task = _TASKS.get(job_id)
        if task is None:
            task = {
                "job_id": job_id,
                "running": False,
                "done": False,
                "error": "",
                "step": "idle",
                "progress": 0,
                "logs": [],
                "started_at": "",
                "finished_at": "",
            }
            _TASKS[job_id] = task
        return task


def _emit(job_id: str, message: str, *, step: str = "", progress: int | None = None) -> None:
    line = f"[{_now_text()}] {str(message or '').strip()}"
    with _TASK_LOCK:
        task = _task(job_id)
        if step:
            task["step"] = step
        if progress is not None:
            task["progress"] = max(0, min(100, int(progress)))
        logs = list(task.get("logs") or [])
        logs.append(line)
        task["logs"] = logs[-_MAX_LOGS:]


def _public_task(job_id: str) -> dict[str, Any]:
    with _TASK_LOCK:
        task = dict(_task(job_id))
        task["logs"] = list(task.get("logs") or [])
    try:
        task["job"] = additions._public_job(additions._row(job_id))
    except Exception:
        task["job"] = None
    return task


def _composer(page: Any) -> Any:
    selectors = (
        "#prompt-textarea",
        "[data-testid='composer-text-input']",
        "div[contenteditable='true'][role='textbox']",
        "textarea[placeholder*='Message' i]",
        "textarea[placeholder*='mensagem' i]",
    )
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() and locator.is_visible():
                return locator
        except Exception:
            continue
    return None


def _wait_composer(page: Any, job_id: str, timeout_seconds: int = 300) -> Any:
    deadline = time.time() + timeout_seconds
    warned = False
    while time.time() < deadline:
        composer = _composer(page)
        if composer is not None:
            return composer
        if not warned:
            _emit(
                job_id,
                "Aguardando o ChatGPT ficar disponível. Se esta for a primeira execução, faça login na janela aberta.",
                step="chatgpt_login",
                progress=12,
            )
            warned = True
        page.wait_for_timeout(1000)
    raise RuntimeError("Tempo esgotado aguardando o login/caixa de mensagem do ChatGPT.")


def _assistant_messages(page: Any) -> Any:
    return page.locator("[data-message-author-role='assistant']")


def _send_message(page: Any, prompt: str, job_id: str) -> tuple[int, set[str]]:
    messages = _assistant_messages(page)
    before_count = messages.count()
    before_images = set(_large_image_sources(page))
    composer = _wait_composer(page, job_id)
    composer.click()
    try:
        composer.fill(prompt)
    except Exception:
        page.keyboard.press("Control+A")
        page.keyboard.insert_text(prompt)
    page.wait_for_timeout(250)

    sent = False
    for selector in (
        "button[data-testid='send-button']",
        "button[aria-label*='Send' i]",
        "button[aria-label*='Enviar' i]",
    ):
        button = page.locator(selector).first
        try:
            if button.count() and button.is_visible() and button.is_enabled():
                button.click()
                sent = True
                break
        except Exception:
            continue
    if not sent:
        page.keyboard.press("Enter")
    return before_count, before_images


def _wait_structured_answer(page: Any, before_count: int, job_id: str, timeout_seconds: int = 360) -> str:
    deadline = time.time() + timeout_seconds
    latest = ""
    while time.time() < deadline:
        messages = _assistant_messages(page)
        try:
            count = messages.count()
        except Exception:
            count = 0
        if count > before_count:
            try:
                latest = str(messages.nth(count - 1).inner_text() or "").strip()
            except Exception:
                latest = ""
            normalized = latest.upper()
            if (
                "TÍTULO" in normalized
                and "BREVE DESCRIÇÃO" in normalized
                and "DESCRIÇÃO" in normalized
                and "TAGS" in normalized
            ):
                try:
                    chatgpt.parse_chatgpt_text(latest)
                    return latest
                except Exception:
                    pass
        page.wait_for_timeout(1500)
    if latest:
        raise RuntimeError("O ChatGPT respondeu, mas o bloco estruturado ainda não ficou válido.")
    raise RuntimeError("Tempo esgotado aguardando a resposta do ChatGPT.")


def _large_image_sources(page: Any) -> list[str]:
    try:
        result = page.evaluate(
            """
            () => [...document.images]
              .filter(img => img.naturalWidth >= 256 && img.naturalHeight >= 256)
              .map(img => img.currentSrc || img.src || '')
              .filter(src => src && !src.includes('avatar') && !src.includes('icon'))
            """
        )
        return [str(item) for item in (result or []) if str(item or "").strip()]
    except Exception:
        return []


def _wait_new_image(page: Any, before: set[str], timeout_seconds: int = 240) -> str:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        sources = _large_image_sources(page)
        for source in reversed(sources):
            if source not in before:
                return source
        page.wait_for_timeout(1500)
    return ""


def _image_data_url(page: Any, source: str) -> str:
    if source.startswith("data:image/"):
        return source
    return str(
        page.evaluate(
            """
            async (src) => {
              const response = await fetch(src, {credentials: 'include'});
              if (!response.ok) throw new Error(`HTTP ${response.status}`);
              const blob = await response.blob();
              return await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(String(reader.result || ''));
                reader.onerror = reject;
                reader.readAsDataURL(blob);
              });
            }
            """,
            source,
        )
        or ""
    )


def _persist_image(job_id: str, data_url: str) -> str:
    match = re.match(r"^data:(image/(?:png|jpeg|webp));base64,(.+)$", data_url, re.I | re.S)
    if not match:
        raise RuntimeError("A imagem gerada pelo ChatGPT não pôde ser lida.")
    mime = match.group(1).lower()
    suffix = ".jpg" if mime == "image/jpeg" else mimetypes.guess_extension(mime) or ".png"
    raw = base64.b64decode(match.group(2), validate=False)
    if len(raw) < 8_000:
        raise RuntimeError("A imagem retornada pelo ChatGPT parece inválida ou pequena demais.")
    additions._IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
    target = additions._IMAGE_ROOT / f"{additions._safe_job_id(job_id)}{suffix}"
    target.write_bytes(raw)
    additions._update(job_id, image_path=str(target), error="")
    additions._recalculate_state(job_id)
    return str(target)


def _save_text(job_id: str, answer: str) -> None:
    job = additions._row(job_id)
    parsed = chatgpt.parse_chatgpt_text(answer)
    additions._save_content(
        {
            "job_id": job_id,
            "kind": job.get("kind") or "plugin",
            **parsed,
            "annual_regular": job.get("annual_regular") or "",
            "annual_sale": job.get("annual_sale") or "",
            "lifetime_regular": job.get("lifetime_regular") or "",
            "lifetime_sale": job.get("lifetime_sale") or "",
        }
    )


def _automatic_chatgpt(job_id: str) -> None:
    job = additions._row(job_id)
    if additions._content_complete(job) and str(job.get("image_path") or "").strip():
        _emit(job_id, "Conteúdo e imagem já estão prontos; etapa de IA reaproveitada.", step="content_ready", progress=42)
        return

    prompt = str(additions._public_job(job).get("prompt") or "").strip()
    if not prompt:
        raise RuntimeError("Não foi possível montar o prompt do produto.")

    _emit(job_id, "Abrindo o ChatGPT no perfil persistente…", step="chatgpt", progress=8)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as error:
        raise RuntimeError(f"Playwright indisponível para automação do ChatGPT: {type(error).__name__}") from None

    browser_path = chatgpt._find_browser()
    profile_dir = Path(chatgpt._PROFILE_DIR)
    profile_dir.mkdir(parents=True, exist_ok=True)
    config = chatgpt._load_config()
    url = str(config.get("conversation_url") or chatgpt._DEFAULT_URL).strip() or chatgpt._DEFAULT_URL

    with sync_playwright() as playwright:
        context = None
        try:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                executable_path=browser_path,
                headless=False,
                viewport=None,
                args=["--start-maximized"],
            )
            pages = list(context.pages)
            page = pages[0] if pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            _wait_composer(page, job_id)

            _emit(job_id, "Enviando instruções de conteúdo ao ChatGPT…", step="chatgpt_content", progress=16)
            before_count, before_images = _send_message(page, prompt, job_id)
            answer = _wait_structured_answer(page, before_count, job_id)
            _save_text(job_id, answer)
            _emit(job_id, "Texto, SEO, tags e categoria recebidos.", step="chatgpt_content", progress=30)

            image_source = _wait_new_image(page, before_images, timeout_seconds=35)
            if not image_source:
                current = additions._row(job_id)
                title = str(current.get("title") or current.get("source_name") or "produto WordPress")
                image_prompt = (
                    f"Agora gere SOMENTE uma imagem de capa quadrada 1:1 para o produto {title}. "
                    "Visual profissional para e-commerce de plugins/temas WordPress, composição limpa, "
                    "sem preço, sem marca d'água, sem texto pequeno e sem copiar identidade visual protegida."
                )
                _emit(job_id, "Gerando a imagem 1:1…", step="chatgpt_image", progress=34)
                _count, before_second = _send_message(page, image_prompt, job_id)
                image_source = _wait_new_image(page, before_second, timeout_seconds=300)
            if not image_source:
                raise RuntimeError("O ChatGPT concluiu o texto, mas não retornou uma imagem utilizável.")
            data_url = _image_data_url(page, image_source)
            _persist_image(job_id, data_url)
            _emit(job_id, "Imagem recebida e salva localmente.", step="content_ready", progress=42)
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass


def _read_clipboard() -> str:
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard -Raw"],
                capture_output=True,
                text=True,
                timeout=12,
                check=True,
            )
            return str(result.stdout or "").strip()
        except Exception:
            return ""
    return ""


def _assisted_chatgpt_fallback(job_id: str) -> None:
    _emit(
        job_id,
        "Automação direta do navegador indisponível. Abrindo o modo assistido; o fluxo continuará sozinho após você copiar a resposta e baixar a imagem.",
        step="chatgpt_assisted",
        progress=10,
    )
    chatgpt.open_for_job(job_id)
    prompt = str(additions._public_job(additions._row(job_id)).get("prompt") or "").strip()
    deadline = time.time() + 15 * 60
    imported_text = False
    imported_image = False
    while time.time() < deadline:
        if not imported_text:
            clipboard = _read_clipboard()
            if clipboard and clipboard != prompt:
                try:
                    chatgpt.import_text(job_id, clipboard)
                    imported_text = True
                    _emit(job_id, "Resposta copiada detectada e importada.", progress=30)
                except Exception:
                    pass
        if not imported_image:
            try:
                chatgpt.import_latest_image(job_id)
                imported_image = True
                _emit(job_id, "Imagem baixada detectada e importada.", progress=42)
            except Exception:
                pass
        if imported_text and imported_image:
            return
        time.sleep(2)
    raise RuntimeError("Tempo esgotado aguardando conteúdo/imagem no modo assistido do ChatGPT.")


def _ensure_content(job_id: str) -> None:
    try:
        _automatic_chatgpt(job_id)
    except Exception as automatic_error:
        _emit(job_id, f"Automação do ChatGPT não concluiu: {sanitize_text(automatic_error)}")
        _assisted_chatgpt_fallback(job_id)


def _run(job_id: str, manager: Any) -> None:
    with _TASK_LOCK:
        task = _task(job_id)
        task.update(
            running=True,
            done=False,
            error="",
            step="starting",
            progress=1,
            logs=[],
            started_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            finished_at="",
        )
    try:
        additions._row(job_id)
        _emit(job_id, "Iniciando cadastro automático.", step="starting", progress=2)

        job = additions._row(job_id)
        if not additions._content_complete(job) or not str(job.get("image_path") or "").strip():
            _ensure_content(job_id)
        else:
            _emit(job_id, "Conteúdo e imagem já existentes; reaproveitando.", progress=42)

        job = additions._row(job_id)
        zip_ready = bool(str(job.get("zip_path") or "").strip() and Path(str(job.get("zip_path"))).exists())
        if not zip_ready:
            _emit(job_id, "Baixando e validando o ZIP da fonte…", step="zip", progress=48)
            additions._download_source(job_id, manager)
            _emit(job_id, "ZIP preparado e validado.", step="zip_ready", progress=62)
        else:
            _emit(job_id, "ZIP já preparado; reaproveitando arquivo existente.", progress=62)

        job = additions._recalculate_state(job_id)
        if str(job.get("state")) not in {"ready_to_create", "draft_created", "published", "completed"}:
            raise RuntimeError(f"Produto ainda não está pronto para criar. Estado atual: {job.get('state_label') or job.get('state')}")

        if not int(job.get("woo_product_id") or 0):
            _emit(job_id, "Criando rascunho no WooCommerce…", step="draft", progress=70)
            additions._create_or_resume_draft(job_id, "CRIAR RASCUNHO")
            _emit(job_id, "Rascunho criado e validado.", step="draft_ready", progress=82)

        job = additions._row(job_id)
        if str(job.get("state")) not in {"published", "completed"}:
            woo_id = int(job.get("woo_product_id") or 0)
            if not woo_id:
                raise RuntimeError("O WooCommerce não retornou o ID do rascunho.")
            _emit(job_id, f"Publicando WooCommerce #{woo_id}…", step="publish", progress=88)
            additions._publish(job_id, f"PUBLICAR {woo_id}")

        _emit(job_id, "Produto adicionado e validado com sucesso.", step="completed", progress=100)
        with _TASK_LOCK:
            task = _task(job_id)
            task["running"] = False
            task["done"] = True
            task["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception as error:
        message = sanitize_text(error)
        try:
            additions._update(job_id, error=message)
        except Exception:
            pass
        _emit(job_id, f"ERRO: {message}", step="error")
        with _TASK_LOCK:
            task = _task(job_id)
            task["running"] = False
            task["done"] = False
            task["error"] = message
            task["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")


def _start(job_id: str, manager: Any) -> dict[str, Any]:
    job_id = additions._normalize(job_id)
    additions._row(job_id)
    with _TASK_LOCK:
        task = _task(job_id)
        if task.get("running"):
            return {"ok": True, "message": "O cadastro já está em execução.", "task": _public_task(job_id)}
        task["running"] = True
        task["done"] = False
        task["error"] = ""
    thread = threading.Thread(target=_run, args=(job_id, manager), daemon=True, name=f"addition-{job_id[:20]}")
    thread.start()
    return {"ok": True, "message": "Cadastro iniciado.", "task": _public_task(job_id)}


def _script_block() -> str:
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return ""
    return f"\n<script data-addition-one-click>\n{script}\n</script>\n"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    block = _script_block()
    if not block:
        return html
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def _manager_from_handler(handler_class: type) -> Any:
    try:
        return additions._manager_from_handler(handler_class)
    except Exception:
        return None


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    manager = _manager_from_handler(handler_class)

    class OneClickAdditionHandler(handler_class):
        def do_GET(self) -> None:
            path = self._request_path()
            if path == "/adicoes/automatico/status":
                with _TASK_LOCK:
                    tasks = [_public_task(job_id) for job_id in list(_TASKS.keys())]
                self._send_json({"ok": True, "tasks": tasks})
                return
            return super().do_GET()

        def do_POST(self) -> None:
            path = self._request_path()
            if path == "/adicoes/automatico":
                try:
                    payload = self._read_json_body()
                    result = _start(str(payload.get("job_id") or ""), manager)
                    self._send_json(result)
                except ValueError as error:
                    self._send_json({"ok": False, "message": str(error)}, code=400)
                except Exception as error:
                    self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)
                return
            return super().do_POST()

    return _BASE_SERVER(server_address, OneClickAdditionHandler, *args, **kwargs)


def install_addition_one_click_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_SERVER
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory
    _INSTALLED = True
