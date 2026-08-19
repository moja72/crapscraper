from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from app import settings
import app.new_product_workflow_policy as additions

_CONFIG_PATH = Path(settings.DATA_DIR) / "chatgpt_browser_assist.json"
_PROFILE_DIR = Path(settings.DATA_DIR) / "browser_profiles" / "chatgpt"
_DEFAULT_URL = "https://chatgpt.com/"
_ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _load_config() -> dict[str, Any]:
    try:
        payload = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _save_config(payload: Mapping[str, Any]) -> dict[str, Any]:
    current = _load_config()
    current.update(dict(payload))
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def public_config() -> dict[str, Any]:
    config = _load_config()
    return {
        "ok": True,
        "conversation_url": str(config.get("conversation_url") or ""),
        "profile_dir": str(_PROFILE_DIR),
        "mode": "browser_assisted",
        "automatic_extraction": False,
    }


def save_conversation_url(url: str) -> dict[str, Any]:
    normalized = str(url or "").strip()
    if normalized and not re.match(r"^https://(chatgpt\.com|chat\.openai\.com)(/|$)", normalized, re.I):
        raise ValueError("Use uma URL de conversa do ChatGPT em https://chatgpt.com/.")
    _save_config({"conversation_url": normalized})
    return {"ok": True, "message": "Conversa do ChatGPT salva.", **public_config()}


def _copy_to_clipboard(text: str) -> None:
    if sys.platform == "win32":
        try:
            subprocess.run(["clip.exe"], input=text, text=True, check=True, timeout=10)
            return
        except Exception:
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
                    input=text,
                    text=True,
                    check=True,
                    timeout=15,
                )
                return
            except Exception as error:
                raise ValueError(f"Não foi possível copiar o prompt para a área de transferência: {error}") from None
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
    except Exception as error:
        raise ValueError(f"Não foi possível copiar o prompt para a área de transferência: {error}") from None


def _chrome_candidates() -> list[str]:
    values: list[str] = []
    explicit = os.getenv("SCRAPER_CHATGPT_BROWSER_PATH", "").strip()
    if explicit:
        values.append(explicit)
    if sys.platform == "win32":
        local = os.getenv("LOCALAPPDATA", "")
        program_files = os.getenv("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)")
        values.extend([
            str(Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe"),
            str(Path(program_files_x86) / "Google" / "Chrome" / "Application" / "chrome.exe"),
            str(Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe") if local else "",
            str(Path(program_files) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
            str(Path(program_files_x86) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
        ])
    for name in ("google-chrome", "chrome", "chromium", "chromium-browser", "msedge"):
        found = shutil.which(name)
        if found:
            values.append(found)
    return [value for value in values if value]


def _find_browser() -> str:
    for candidate in _chrome_candidates():
        if Path(candidate).exists() or shutil.which(candidate):
            return candidate
    raise ValueError(
        "Chrome/Edge não encontrado. Defina SCRAPER_CHATGPT_BROWSER_PATH com o caminho do navegador."
    )


def open_for_job(job_id: str) -> dict[str, Any]:
    job = additions._row(additions._normalize(job_id))
    prompt = str(additions._public_job(job).get("prompt") or "").strip()
    if not prompt:
        raise ValueError("Não foi possível gerar o prompt deste produto.")
    _copy_to_clipboard(prompt)
    config = _load_config()
    url = str(config.get("conversation_url") or _DEFAULT_URL).strip() or _DEFAULT_URL
    browser = _find_browser()
    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        browser,
        f"--user-data-dir={_PROFILE_DIR}",
        "--profile-directory=Default",
        "--new-window",
        url,
    ]
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    _save_config({"last_opened_at": int(time.time()), "last_job_id": str(job.get("job_id") or job_id)})
    return {
        "ok": True,
        "message": (
            "ChatGPT aberto em um perfil dedicado e o prompt foi copiado. "
            "No primeiro uso, faça login manualmente nessa janela; a sessão ficará nesse perfil para os próximos usos."
        ),
        "conversation_url": url,
        "profile_dir": str(_PROFILE_DIR),
    }


def _section(text: str, label: str, next_labels: list[str]) -> str:
    escaped = re.escape(label)
    tail = "|".join(re.escape(item) for item in next_labels)
    pattern = rf"(?ims)^\s*{escaped}\s*:\s*(.*?)(?=^\s*(?:{tail})\s*:|\Z)" if tail else rf"(?ims)^\s*{escaped}\s*:\s*(.*)\Z"
    match = re.search(pattern, text)
    return str(match.group(1) if match else "").strip()


def parse_chatgpt_text(text: str) -> dict[str, str]:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("Cole ou copie primeiro a resposta textual do ChatGPT.")
    labels = [
        "TÍTULO",
        "BREVE DESCRIÇÃO",
        "DESCRIÇÃO",
        "TÍTULO SEO",
        "META DESCRIPTION",
        "TAGS",
        "CATEGORIA",
    ]
    values: dict[str, str] = {}
    for index, label in enumerate(labels):
        values[label] = _section(raw, label, labels[index + 1 :])
    if not values["TÍTULO"] or not values["BREVE DESCRIÇÃO"] or not values["DESCRIÇÃO"]:
        raise ValueError(
            "A resposta não contém os campos obrigatórios TÍTULO, BREVE DESCRIÇÃO e DESCRIÇÃO. "
            "Use o prompt gerado pelo CrapScraper e copie o bloco final estruturado."
        )
    return {
        "title": values["TÍTULO"],
        "short_description": values["BREVE DESCRIÇÃO"],
        "description": values["DESCRIÇÃO"],
        "seo_title": values["TÍTULO SEO"],
        "meta_description": values["META DESCRIPTION"],
        "tags": values["TAGS"],
        "category_name": values["CATEGORIA"],
    }


def import_text(job_id: str, text: str) -> dict[str, Any]:
    job = additions._row(additions._normalize(job_id))
    parsed = parse_chatgpt_text(text)
    payload = {
        "job_id": job["job_id"],
        "kind": job.get("kind") or "plugin",
        **parsed,
        "annual_regular": job.get("annual_regular") or "",
        "annual_sale": job.get("annual_sale") or "",
        "lifetime_regular": job.get("lifetime_regular") or "",
        "lifetime_sale": job.get("lifetime_sale") or "",
    }
    result = additions._save_content(payload)
    result["message"] = "Texto do ChatGPT importado e estruturado no cadastro."
    return result


def _downloads_dir() -> Path:
    configured = os.getenv("SCRAPER_CHATGPT_DOWNLOADS_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / "Downloads"


def _latest_image() -> Path:
    root = _downloads_dir()
    if not root.exists():
        raise ValueError(f"Pasta de Downloads não encontrada: {root}")
    config = _load_config()
    opened_at = int(config.get("last_opened_at") or 0)
    minimum_mtime = max(opened_at - 60, int(time.time()) - 3 * 60 * 60)
    candidates = [
        path for path in root.iterdir()
        if path.is_file()
        and path.suffix.lower() in _ALLOWED_IMAGE_SUFFIXES
        and int(path.stat().st_mtime) >= minimum_mtime
        and path.stat().st_size <= 12 * 1024 * 1024
    ]
    if not candidates:
        raise ValueError(
            "Nenhuma imagem recente foi encontrada em Downloads. No ChatGPT, baixe a imagem gerada e tente novamente."
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def import_latest_image(job_id: str) -> dict[str, Any]:
    job_id = additions._normalize(job_id)
    additions._row(job_id)
    source = _latest_image()
    additions._IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()
    target = additions._IMAGE_ROOT / f"{additions._safe_job_id(job_id)}{suffix}"
    shutil.copy2(source, target)
    additions._update(job_id, image_path=str(target), error="")
    job = additions._recalculate_state(job_id)
    return {
        "ok": True,
        "message": f"Imagem importada de Downloads: {source.name}",
        "source_name": source.name,
        "image_path": str(target),
        "job": additions._public_job(job),
    }
