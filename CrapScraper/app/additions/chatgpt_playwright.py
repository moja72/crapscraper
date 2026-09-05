from __future__ import annotations

import base64
import io
import json
import os
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from app.additions.content import content_prompt, normalize_list, valid_content
from app.additions.creative import image_prompt

_DEFAULT_CHATGPT_URL = "https://chatgpt.com/"
_DEFAULT_PROJECT = "[CS] Automação"
_LOCK = threading.RLock()

_COMPOSER_SELECTORS = (
    "#prompt-textarea",
    "textarea[data-testid='prompt-textarea']",
    "div[data-testid='prompt-textarea'][contenteditable='true']",
    "div[contenteditable='true'][role='textbox']",
)

_ASSISTANT_SELECTOR = "[data-message-author-role='assistant']"
_IMAGE_SELECTOR = "[data-message-author-role='assistant'] img"


class ChatGPTPlaywrightError(RuntimeError):
    pass


def _truthy(value: str | None, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on", "sim"}


def _data_dir() -> Path:
    configured = os.getenv("SCRAPER_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(__file__).resolve().parents[3] / "data").resolve()


def profile_dir() -> Path:
    configured = os.getenv("SCRAPER_CHATGPT_PROFILE_DIR", "").strip()
    root = Path(configured).expanduser() if configured else _data_dir() / "browser_profiles" / "chatgpt_automation"
    return root.resolve()


def state_path() -> Path:
    return _data_dir() / "chatgpt_playwright_state.json"


def project_name() -> str:
    return os.getenv("SCRAPER_CHATGPT_PROJECT_NAME", _DEFAULT_PROJECT).strip() or _DEFAULT_PROJECT


def _timeout_seconds() -> int:
    try:
        return max(60, min(600, int(os.getenv("SCRAPER_CHATGPT_TIMEOUT_SECONDS", "300"))))
    except ValueError:
        return 300


def _read_state() -> dict[str, Any]:
    try:
        payload = json.loads(state_path().read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_state(payload: dict[str, Any]) -> None:
    target = state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(target)


def _update_state(**values: Any) -> dict[str, Any]:
    state = _read_state()
    state.update(values)
    _write_state(state)
    return state


def _job_state(job_id: str) -> dict[str, Any]:
    state = _read_state()
    jobs = state.get("jobs") if isinstance(state.get("jobs"), dict) else {}
    item = jobs.get(str(job_id)) if isinstance(jobs, dict) else None
    return dict(item) if isinstance(item, dict) else {}


def _update_job_state(job_id: str, **values: Any) -> dict[str, Any]:
    state = _read_state()
    jobs = state.get("jobs") if isinstance(state.get("jobs"), dict) else {}
    jobs = dict(jobs)
    current = jobs.get(str(job_id)) if isinstance(jobs.get(str(job_id)), dict) else {}
    current = dict(current)
    current.update(values)
    current["updated_at"] = int(time.time())
    jobs[str(job_id)] = current
    state["jobs"] = jobs
    _write_state(state)
    return current


def _load_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ChatGPTPlaywrightError(
            "Playwright Python não instalado. Execute: py -m pip install playwright pillow && py -m playwright install chromium"
        ) from exc
    return sync_playwright


@contextmanager
def _browser(headless: bool | None = None):
    sync_playwright = _load_playwright()
    profile = profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    use_headless = _truthy(os.getenv("SCRAPER_CHATGPT_HEADLESS"), True) if headless is None else bool(headless)
    playwright = sync_playwright().start()
    context = None
    try:
        kwargs: dict[str, Any] = {
            "user_data_dir": str(profile),
            "headless": use_headless,
            "viewport": {"width": 1600, "height": 1000},
            "device_scale_factor": 2,
            "locale": "pt-BR",
            "timezone_id": "America/Sao_Paulo",
            "accept_downloads": True,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        executable = os.getenv("SCRAPER_CHATGPT_BROWSER_PATH", "").strip()
        channel = os.getenv("SCRAPER_CHATGPT_BROWSER_CHANNEL", "").strip()
        if executable:
            kwargs["executable_path"] = executable
        elif channel:
            kwargs["channel"] = channel
        context = playwright.chromium.launch_persistent_context(**kwargs)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(15000)
        yield page
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        try:
            playwright.stop()
        except Exception:
            pass


def _composer(page, timeout_ms: int = 4000):
    deadline = time.monotonic() + max(0.5, timeout_ms / 1000)
    while time.monotonic() < deadline:
        for selector in _COMPOSER_SELECTORS:
            locator = page.locator(selector).first
            try:
                if locator.count() and locator.is_visible():
                    return locator
            except Exception:
                continue
        time.sleep(0.2)
    return None


def _looks_like_auth_wall(page) -> bool:
    try:
        text = (page.locator("body").inner_text(timeout=3000) or "").casefold()
    except Exception:
        text = ""
    tokens = ("log in", "sign up", "entrar", "criar conta", "verifying you are human", "just a moment")
    return any(token in text for token in tokens)


def _ensure_authenticated(page) -> None:
    if _composer(page, 7000) is not None:
        return
    if _looks_like_auth_wall(page):
        raise ChatGPTPlaywrightError(
            "Sessão ChatGPT não autenticada. Execute uma vez: python -m app.additions.chatgpt_playwright bootstrap"
        )
    raise ChatGPTPlaywrightError(
        "Não foi possível localizar o campo de mensagem do ChatGPT. Faça o bootstrap da sessão e confirme o projeto [CS] Automação."
    )


def _open_sidebar(page) -> None:
    candidates = (
        "button[aria-label*='sidebar' i]",
        "button[aria-label*='barra lateral' i]",
        "button[data-testid*='sidebar']",
    )
    for selector in candidates:
        locator = page.locator(selector).first
        try:
            if locator.count() and locator.is_visible():
                locator.click()
                time.sleep(0.8)
                return
        except Exception:
            continue


def _find_project_locator(page):
    name = project_name()
    candidates = [
        page.get_by_text(name, exact=True),
        page.locator("a").filter(has_text=name),
        page.locator("button").filter(has_text=name),
    ]
    for candidate in candidates:
        try:
            count = candidate.count()
        except Exception:
            continue
        for index in range(min(count, 8)):
            item = candidate.nth(index)
            try:
                if item.is_visible():
                    return item
            except Exception:
                continue
    return None


def _open_project(page) -> None:
    state = _read_state()
    saved = str(state.get("project_url") or "").strip()
    if saved.startswith("https://chatgpt.com/"):
        page.goto(saved, wait_until="domcontentloaded", timeout=60000)
        if _composer(page, 7000) is not None:
            return

    page.goto(_DEFAULT_CHATGPT_URL, wait_until="domcontentloaded", timeout=60000)
    _ensure_authenticated(page)
    locator = _find_project_locator(page)
    if locator is None:
        _open_sidebar(page)
        locator = _find_project_locator(page)
    if locator is None:
        raise ChatGPTPlaywrightError(
            f"Projeto {project_name()} não encontrado no ChatGPT. Execute o bootstrap e abra esse projeto uma vez."
        )
    locator.click()
    page.wait_for_timeout(1200)
    if _composer(page, 7000) is None:
        # Algumas versões da UI abrem a página do projeto sem o compositor; tente Novo chat.
        for pattern in (re.compile(r"novo chat", re.I), re.compile(r"new chat", re.I)):
            try:
                control = page.get_by_role("button", name=pattern).first
                if control.count() and control.is_visible():
                    control.click()
                    page.wait_for_timeout(800)
                    break
            except Exception:
                pass
    if _composer(page, 7000) is None:
        raise ChatGPTPlaywrightError(f"Projeto {project_name()} foi localizado, mas o compositor de mensagens não abriu.")
    if page.url.startswith("https://chatgpt.com/"):
        _update_state(project_url=page.url, project_name=project_name(), profile_dir=str(profile_dir()))


def _open_job_conversation(page, job_id: str) -> None:
    item = _job_state(job_id)
    conversation = str(item.get("conversation_url") or "").strip()
    if conversation.startswith("https://chatgpt.com/"):
        try:
            page.goto(conversation, wait_until="domcontentloaded", timeout=60000)
            if _composer(page, 7000) is not None:
                return
        except Exception:
            pass
    _open_project(page)


def _stop_visible(page) -> bool:
    selectors = (
        "button[data-testid*='stop']",
        "button[aria-label*='Stop' i]",
        "button[aria-label*='Parar' i]",
    )
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible():
                return True
        except Exception:
            continue
    return False


def _send_prompt(page, prompt: str, timeout_seconds: int | None = None) -> tuple[str, Any]:
    composer = _composer(page, 7000)
    if composer is None:
        _ensure_authenticated(page)
        composer = _composer(page, 3000)
    if composer is None:
        raise ChatGPTPlaywrightError("Campo de mensagem do ChatGPT não encontrado.")

    messages = page.locator(_ASSISTANT_SELECTOR)
    before = messages.count()
    composer.click()
    composer.fill(prompt)
    try:
        composer.press("Enter")
    except Exception:
        send = page.locator("button[data-testid='send-button'], button[aria-label*='Enviar' i], button[aria-label*='Send' i]").first
        if not send.count():
            raise
        send.click()

    deadline = time.monotonic() + (timeout_seconds or _timeout_seconds())
    last_text = ""
    stable = 0
    last_message = None
    while time.monotonic() < deadline:
        if _looks_like_auth_wall(page) and _composer(page, 1000) is None:
            raise ChatGPTPlaywrightError("Sessão ChatGPT expirou durante a automação. Execute o bootstrap novamente.")
        count = messages.count()
        if count > before:
            last_message = messages.nth(count - 1)
            try:
                text = (last_message.inner_text(timeout=3000) or "").strip()
            except Exception:
                text = ""
            if text and text == last_text and not _stop_visible(page):
                stable += 1
            else:
                stable = 0
                last_text = text
            if text and stable >= 2:
                return text, last_message
        time.sleep(0.8)
    raise ChatGPTPlaywrightError("ChatGPT não concluiu a resposta dentro do tempo limite.")


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.I | re.S)
    candidates = [fenced.group(1)] if fenced else []
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _legacy_section(text: str, label: str, next_labels: list[str]) -> str:
    tail = "|".join(re.escape(item) for item in next_labels)
    pattern = rf"(?ims)^\s*{re.escape(label)}\s*:\s*(.*?)(?=^\s*(?:{tail})\s*:|\Z)" if tail else rf"(?ims)^\s*{re.escape(label)}\s*:\s*(.*)\Z"
    match = re.search(pattern, text)
    return str(match.group(1) if match else "").strip().strip("`")


def parse_content_response(text: str, job: dict[str, Any]) -> dict[str, Any]:
    payload = _extract_json(text)
    if payload is None:
        labels = ["TÍTULO", "BREVE DESCRIÇÃO", "DESCRIÇÃO", "TÍTULO SEO", "META DESCRIPTION", "TAGS", "CATEGORIA"]
        values = {label: _legacy_section(text, label, labels[index + 1 :]) for index, label in enumerate(labels)}
        if values["BREVE DESCRIÇÃO"] and values["DESCRIÇÃO"]:
            payload = {
                "product_name": values["TÍTULO"] or job.get("product_name"),
                "short_description": values["BREVE DESCRIÇÃO"],
                "content": values["DESCRIÇÃO"],
                "categories": normalize_list(values["CATEGORIA"]),
                "tags": normalize_list(values["TAGS"]),
                "developer": job.get("developer") or "",
                "official_url": job.get("official_url") or "",
            }
    if not isinstance(payload, dict):
        raise ChatGPTPlaywrightError("Resposta do ChatGPT não contém JSON nem o bloco estruturado esperado.")

    result = {
        "product_name": str(payload.get("product_name") or payload.get("title") or job.get("product_name") or "").strip(),
        "short_description": str(payload.get("short_description") or "").strip(),
        "content": str(payload.get("content") or payload.get("description") or "").strip(),
        "categories": normalize_list(payload.get("categories") or payload.get("category") or []),
        "tags": normalize_list(payload.get("tags") or []),
        "developer": str(payload.get("developer") or job.get("developer") or "").strip(),
        "official_url": str(payload.get("official_url") or job.get("official_url") or "").strip(),
    }
    if not valid_content(result):
        raise ChatGPTPlaywrightError("ChatGPT retornou conteúdo incompleto ou curto demais para o cadastro.")
    return result


def _content_fingerprint(job: dict[str, Any]) -> str:
    return "|".join(
        str(job.get(key) or "").strip()
        for key in ("product_name", "source_version", "source_url", "official_url", "developer")
    )


def content_reusable(job: dict[str, Any]) -> bool:
    if not valid_content(job):
        return False
    item = _job_state(str(job.get("job_id") or ""))
    return bool(item.get("content_ready")) and str(item.get("content_fingerprint") or "") == _content_fingerprint(job)


def _image_magic(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    return ""


def _normalize_image_bytes(raw: bytes, root: Path, job_id: str) -> Path:
    if len(raw) <= 1024:
        raise ChatGPTPlaywrightError("Imagem gerada pelo ChatGPT está vazia ou pequena demais.")
    prefix = raw[:256].lstrip().lower()
    if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html") or prefix.startswith(b"{") or prefix.startswith(b"["):
        raise ChatGPTPlaywrightError("Imagem gerada pelo ChatGPT não pôde ser baixada: a resposta recebida não é uma imagem.")

    detected = _image_magic(raw)
    root.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(job_id or "job"))[:120]
    for old in root.glob(f"chatgpt-{safe_id}.*"):
        try:
            old.unlink()
        except OSError:
            pass

    if detected:
        suffix = ".jpg" if detected == "jpeg" else f".{detected}"
        target = root / f"chatgpt-{safe_id}{suffix}"
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_bytes(raw)
        try:
            from PIL import Image
            with Image.open(temp) as image:
                image.verify()
        except ImportError:
            pass
        except Exception as exc:
            temp.unlink(missing_ok=True)
            raise ChatGPTPlaywrightError("Arquivo salvo não é PNG/JPEG/WebP válido.") from exc
        temp.replace(target)
        return target

    try:
        from PIL import Image
    except ImportError as exc:
        raise ChatGPTPlaywrightError(
            "Formato da imagem gerada não é PNG/JPEG/WebP e Pillow não está instalado para converter. Execute: py -m pip install pillow"
        ) from exc

    try:
        with Image.open(io.BytesIO(raw)) as image:
            converted = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            target = root / f"chatgpt-{safe_id}.png"
            temp = target.with_suffix(".png.tmp")
            converted.save(temp, format="PNG")
            temp.replace(target)
            return target
    except Exception as exc:
        raise ChatGPTPlaywrightError("Formato AVIF/SVG ou imagem não suportada; conversão para PNG falhou.") from exc


def image_valid(path: str) -> bool:
    if not path:
        return False
    file = Path(path)
    if not file.is_file() or not file.name.startswith("chatgpt-") or file.stat().st_size <= 1024:
        return False
    try:
        raw = file.read_bytes()[:32]
    except OSError:
        return False
    return bool(_image_magic(raw))


def _candidate_images(page) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    locator = page.locator(_IMAGE_SELECTOR)
    for index in range(locator.count()):
        image = locator.nth(index)
        try:
            info = image.evaluate(
                """img => ({src: img.currentSrc || img.src || '', width: img.naturalWidth || img.width || 0, height: img.naturalHeight || img.height || 0, alt: img.alt || ''})"""
            )
        except Exception:
            continue
        if not isinstance(info, dict):
            continue
        if int(info.get("width") or 0) < 256 or int(info.get("height") or 0) < 256:
            continue
        src = str(info.get("src") or "").strip()
        if not src or src.startswith("data:image/svg"):
            continue
        info["locator"] = image
        items.append(info)
    return items


def _read_image_from_locator(page, item: dict[str, Any]) -> bytes:
    src = str(item.get("src") or "").strip()
    locator = item.get("locator")
    if src.startswith("data:"):
        match = re.match(r"^data:[^;]+;base64,(.+)$", src, re.S)
        if match:
            return base64.b64decode(match.group(1))
    if src.startswith("blob:"):
        try:
            encoded = page.evaluate(
                """async src => { const response = await fetch(src); const buffer = await response.arrayBuffer(); let binary=''; const bytes=new Uint8Array(buffer); const chunk=0x8000; for(let i=0;i<bytes.length;i+=chunk){binary += String.fromCharCode(...bytes.subarray(i,i+chunk));} return btoa(binary); }""",
                src,
            )
            return base64.b64decode(encoded)
        except Exception:
            pass
    if src:
        absolute = urljoin(page.url, src)
        try:
            response = page.context.request.get(absolute, headers={"Referer": page.url}, timeout=90000)
            if response.ok:
                raw = response.body()
                if raw:
                    return raw
        except Exception:
            pass
    if locator is not None:
        try:
            # Último recurso: captura o elemento já renderizado. device_scale_factor=2 preserva boa resolução.
            return locator.screenshot(type="png", timeout=30000)
        except Exception as exc:
            raise ChatGPTPlaywrightError("Imagem gerada pelo ChatGPT não pôde ser baixada nem capturada.") from exc
    raise ChatGPTPlaywrightError("Imagem gerada pelo ChatGPT não pôde ser baixada.")


def generate_content(job: dict[str, Any]) -> dict[str, Any]:
    with _LOCK, _browser() as page:
        _open_job_conversation(page, str(job["job_id"]))
        prompt = (
            f"Você está trabalhando no projeto {project_name()}.\n\n"
            + content_prompt(job)
            + "\n\nNão use Markdown fora do JSON. Não crie dados que não estejam confirmados nas informações fornecidas."
        )
        text, _message = _send_prompt(page, prompt)
        result = parse_content_response(text, job)
        _update_job_state(
            str(job["job_id"]),
            conversation_url=page.url,
            content_ready=True,
            content_fingerprint=_content_fingerprint({**job, **result}),
            content_generated_at=int(time.time()),
        )
        return result


def generate_image(job: dict[str, Any], root: Path) -> Path:
    with _LOCK, _browser() as page:
        _open_job_conversation(page, str(job["job_id"]))
        before = {str(item.get("src") or "") for item in _candidate_images(page)}
        prompt = (
            f"Continuando o cadastro de {job['product_name']} no projeto {project_name()}, gere AGORA a imagem principal.\n\n"
            + image_prompt(job)
            + "\n\nUse a ferramenta de geração de imagens do ChatGPT. Não responda apenas com uma descrição da imagem; produza a imagem de fato."
        )
        _send_prompt(page, prompt, timeout_seconds=_timeout_seconds())

        deadline = time.monotonic() + _timeout_seconds()
        selected = None
        while time.monotonic() < deadline:
            candidates = _candidate_images(page)
            fresh = [item for item in candidates if str(item.get("src") or "") not in before]
            if fresh:
                selected = fresh[-1]
                break
            time.sleep(1.0)
        if selected is None:
            raise ChatGPTPlaywrightError("ChatGPT respondeu, mas nenhuma imagem gerada apareceu na conversa.")

        raw = _read_image_from_locator(page, selected)
        target = _normalize_image_bytes(raw, Path(root), str(job["job_id"]))
        _update_job_state(
            str(job["job_id"]),
            conversation_url=page.url,
            image_ready=True,
            image_path=str(target),
            image_generated_at=int(time.time()),
        )
        return target


def bootstrap() -> dict[str, Any]:
    with _LOCK, _browser(headless=False) as page:
        page.goto(_DEFAULT_CHATGPT_URL, wait_until="domcontentloaded", timeout=60000)
        print("\nUma janela do ChatGPT foi aberta com o perfil persistente do CrapScraper.")
        print("Faça login nessa janela, se necessário. Depois volte a este CMD e pressione ENTER.\n")
        input()
        if _composer(page, 7000) is None:
            raise ChatGPTPlaywrightError("Sessão ChatGPT não autenticada após o bootstrap.")
        try:
            _open_project(page)
        except ChatGPTPlaywrightError:
            print(f"Abra manualmente o projeto {project_name()} na janela do ChatGPT e pressione ENTER aqui.")
            input()
            if _composer(page, 5000) is None:
                raise
            if not page.url.startswith("https://chatgpt.com/"):
                raise ChatGPTPlaywrightError("O navegador não está em uma página válida do ChatGPT.")
            _update_state(project_url=page.url, project_name=project_name(), profile_dir=str(profile_dir()))
        result = {
            "ok": True,
            "project": project_name(),
            "project_url": page.url,
            "profile_dir": str(profile_dir()),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result


def status() -> dict[str, Any]:
    state = _read_state()
    return {
        "project": project_name(),
        "project_url": str(state.get("project_url") or ""),
        "profile_dir": str(profile_dir()),
        "headless_default": _truthy(os.getenv("SCRAPER_CHATGPT_HEADLESS"), True),
        "jobs": len(state.get("jobs") or {}) if isinstance(state.get("jobs"), dict) else 0,
    }


def main() -> None:
    import sys
    command = (sys.argv[1] if len(sys.argv) > 1 else "status").strip().lower()
    if command == "bootstrap":
        bootstrap()
        return
    if command == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=2))
        return
    raise SystemExit("Use: python -m app.additions.chatgpt_playwright [bootstrap|status]")


if __name__ == "__main__":
    main()
