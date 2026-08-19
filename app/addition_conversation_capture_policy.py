from __future__ import annotations

import base64
import hashlib
import re
import time
from html.parser import HTMLParser
from typing import Any, Mapping
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_final_validation_policy as final_validation
import app.addition_one_click_policy as one_click
import app.addition_product_creative_policy as creative
import app.addition_simple_creation_policy as simple
import app.new_product_workflow_policy as additions


_INSTALLED = False
_ORIGINAL_RUN_TWO_CHATS = None
_ORIGINAL_SEND_MESSAGE = None

_DESCRIPTION_EXAMPLE = (
    "Crie páginas profissionais com total liberdade visual O Elementor Pro ajuda a montar páginas, lojas e áreas "
    "do site com visual avançado, melhorando apresentação, conversão e flexibilidade para criar projetos WordPress "
    "mais modernos e profissionais. Ele funciona com edição de arrastar e soltar, widgets premium, templates e "
    "construtores para tema, formulários e pop-ups, deixando a criação mais prática e reduzindo dependência de código no projeto."
)

_EXCLUDED_OFFICIAL_HOSTS = {
    "ultrapackv2.com",
    "www.ultrapackv2.com",
    "cdn.ultrapackv2.com",
    "facebook.com",
    "www.facebook.com",
    "instagram.com",
    "www.instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "www.youtube.com",
    "google.com",
    "www.google.com",
}

_MARKETPLACE_HOSTS = {
    "themeforest.net",
    "www.themeforest.net",
    "codecanyon.net",
    "www.codecanyon.net",
    "elements.envato.com",
    "woocommerce.com",
    "wordpress.org",
}


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        self._href = values.get("href", "").strip()
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(str(data or ""))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._href:
            return
        self.rows.append({"href": self._href, "text": " ".join(self._text).strip()})
        self._href = ""
        self._text = []


def _kind(job: Mapping[str, Any]) -> str:
    return "theme" if str(job.get("kind") or "").strip().lower() == "theme" else "plugin"


def _host(url: str) -> str:
    try:
        return str(urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return ""


def _is_ultrapack(url: str) -> bool:
    host = _host(url)
    return host == "ultrapackv2.com" or host.endswith(".ultrapackv2.com")


def _is_official_candidate(url: str, source_url: str = "") -> bool:
    value = str(url or "").strip()
    if not value.startswith(("http://", "https://")):
        return False
    host = _host(value)
    if not host or host in _EXCLUDED_OFFICIAL_HOSTS:
        return False
    if _is_ultrapack(value):
        return False
    source_host = _host(source_url)
    if source_host and host == source_host:
        return False
    return True


def _official_score(url: str, text: str) -> int:
    host = _host(url)
    path = str(urlparse(url).path or "").lower()
    label = " ".join(str(text or "").lower().split())
    score = 0
    if host in _MARKETPLACE_HOSTS:
        score += 120
    if "/item/" in path:
        score += 40
    if any(marker in label for marker in (
        "página do item", "pagina do item", "página oficial", "pagina oficial",
        "site oficial", "official", "view item", "sale page", "product page",
    )):
        score += 100
    if any(marker in label for marker in ("demo", "preview")):
        score += 15
    if any(marker in path for marker in ("/tag/", "/category/", "/author/", "/blog/")):
        score -= 30
    return score


def _official_from_html(html: str, base_url: str) -> str:
    parser = _AnchorParser()
    try:
        parser.feed(str(html or ""))
    except Exception:
        return ""
    ranked: list[tuple[int, str]] = []
    for row in parser.rows:
        href = urljoin(base_url, str(row.get("href") or "").strip())
        if not _is_official_candidate(href, base_url):
            continue
        ranked.append((_official_score(href, str(row.get("text") or "")), href))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < 60:
        return ""
    return ranked[0][1]


def _fetch_html(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CrapScraper/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=25) as response:
        raw = response.read(2_500_000)
        encoding = response.headers.get_content_charset() or "utf-8"
    return raw.decode(encoding, "replace")


def _ensure_tracking_schema() -> None:
    columns = {
        "description_chat_url": "TEXT NOT NULL DEFAULT ''",
        "image_chat_url": "TEXT NOT NULL DEFAULT ''",
        "description_sha256": "TEXT NOT NULL DEFAULT ''",
        "image_sha256": "TEXT NOT NULL DEFAULT ''",
    }
    with additions._db() as connection:
        existing = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(addition_jobs)").fetchall()
        }
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE addition_jobs ADD COLUMN {name} {definition}")


def _resolve_official_for_job(job_id: str) -> dict[str, Any]:
    _ensure_tracking_schema()
    job = additions._row(job_id)
    source_url = str(job.get("source_product_url") or "").strip()
    current = str(job.get("source_official_url") or "").strip()

    if _is_official_candidate(current, source_url):
        one_click._emit(
            job_id,
            f"Página oficial confirmada para os dois chats: {current}",
            step="official_source",
            progress=5,
        )
        return job

    if not source_url:
        raise RuntimeError("O cadastro não possui URL de origem para localizar a página oficial do produto.")

    one_click._emit(
        job_id,
        "Localizando a página oficial do plugin/tema antes de abrir o ChatGPT…",
        step="official_source",
        progress=4,
    )
    try:
        official = _official_from_html(_fetch_html(source_url), source_url)
    except Exception as error:
        raise RuntimeError(
            f"Não foi possível consultar a página de origem para localizar a página oficial: {type(error).__name__}."
        ) from None

    if not official:
        raise RuntimeError(
            "A página oficial do plugin/tema não pôde ser identificada na fonte. "
            "O ChatGPT não será chamado com a página do Ultrapack no lugar da página oficial."
        )

    job = additions._update(job_id, source_official_url=official, error="")
    one_click._emit(
        job_id,
        f"Página oficial resolvida e persistida: {official}",
        step="official_source",
        progress=6,
    )
    return job


def _description_prompt(job: Mapping[str, Any]) -> str:
    official = str(job.get("source_official_url") or "").strip()
    kind_label = "tema WordPress" if _kind(job) == "theme" else "plugin WordPress"
    return f"""Gere SOMENTE a breve descrição comercial deste produto para o e-commerce PluginTema.

PRODUTO
Nome: {job.get('source_name') or '-'}
Tipo: {kind_label}
Versão de referência: {job.get('source_version') or '-'}
Página oficial do produto: {official or '-'}

PESQUISA OBRIGATÓRIA
Antes de escrever, abra e analise a PÁGINA OFICIAL acima. Use essa página como fonte principal de verdade para entender o produto, marca, finalidade, recursos confirmados, público e posicionamento. Não use sites de redistribuição como fonte editorial e não copie o texto da página oficial.

FORMATO
Escreva um único parágrafo em português do Brasil, com aproximadamente 400 a 500 caracteres e 2 ou 3 frases. Comece com o benefício principal, mencione o produto naturalmente e explique o que ele ajuda a fazer com base no que foi confirmado na página oficial. Finalize indicando para quais projetos ou usuários ele é útil, sem repetir ideias.

QUALIDADE
- Texto comercial, claro, específico, natural e informativo.
- Não invente recursos, compatibilidades, números ou integrações.
- Não inclua a versão no texto final.
- Evite clichês vazios como “solução completa”, “uma opção versátil” e “leve seu projeto para outro nível”.
- Não use título, H1, H2, listas, HTML, Markdown, SEO, tags, categoria, observações ou explicações.
- Não escreva rótulos como “Descrição:” ou “Breve descrição:”.

Use apenas a estrutura, o ritmo e a extensão deste exemplo como referência; não copie o conteúdo:
"{_DESCRIPTION_EXAMPLE}"

Retorne SOMENTE o parágrafo final."""


def _image_prompt(job: Mapping[str, Any]) -> str:
    official = str(job.get("source_official_url") or "").strip()
    title = str(job.get("source_name") or job.get("title") or "produto WordPress").strip()
    kind = _kind(job)

    if kind == "theme":
        composition = """TEMA — RESULTADO ESPERADO
- O arquivo anexado 'exemplo tema.webp' define APENAS o tipo de mockup, proporções e nível de acabamento.
- Gere uma NOVA composição 1:1, com fundo totalmente transparente, mostrando um monitor Apple e um celular inteiros e claramente visíveis.
- Nas telas, use a aparência REAL do tema encontrada na página oficial: screenshots, cores, marca, tipografia e estilo visual identificáveis no produto.
- A posição do celular pode variar, mas as duas telas devem ser legíveis e pertencer claramente ao produto atual.
- Não copie as telas, marca ou textos da imagem de referência."""
    else:
        composition = """PLUGIN — RESULTADO ESPERADO
- O arquivo anexado 'exemplo plugin.webp' define APENAS o tipo de caixa 3D, proporções e nível de acabamento.
- Gere uma NOVA caixa 1:1 com fundo totalmente transparente, profissional e com pelo menos 3 faces visíveis.
- Use nome, cores e identidade REAL do plugin encontrada na página oficial. Use o logotipo real apenas quando estiver confirmado visualmente; não invente logo.
- Use fonte Quicksand nas informações da embalagem e mostre exatamente: “Vitalício | Ilimitado | Atualizado”.
- Não copie marca, cores ou textos da imagem de referência."""

    return f"""Gere SOMENTE a imagem principal deste produto. Não responda com texto fora da geração da imagem.

PRODUTO
Nome: {title}
Tipo: {'tema WordPress' if kind == 'theme' else 'plugin WordPress'}
Página oficial do produto: {official or '-'}

PESQUISA VISUAL OBRIGATÓRIA
Antes de gerar, abra e analise a PÁGINA OFICIAL acima. Ela é a fonte principal para identificar a aparência real do produto: marca, logo quando houver, cores, screenshots, interface e linguagem visual. O arquivo anexado é somente uma referência de MOCKUP/COMPOSIÇÃO.

{composition}

REQUISITOS FINAIS
- Imagem quadrada 1:1.
- Fundo totalmente transparente, inclusive nas bordas e áreas vazias.
- Alta qualidade para capa de produto em e-commerce.
- Não use cenário ou fundo sólido.
- Não corte os dispositivos ou a caixa.
- Não reutilize o arquivo anexado como resultado final.
- Não invente identidade visual diferente da página oficial.
- Aguarde a geração terminar completamente e entregue uma única imagem final."""


def _assistant_text_candidates(page: Any) -> list[str]:
    try:
        result = page.evaluate(
            """
            () => {
              const out = [];
              const seen = new Set();
              const push = node => {
                if (!node) return;
                const text = String(node.innerText || node.textContent || '').trim();
                if (!text || seen.has(text)) return;
                seen.add(text);
                out.push(text);
              };
              document.querySelectorAll('[data-message-author-role="assistant"]').forEach(node => {
                push(node.querySelector('.markdown, [class*="markdown"], [class*="prose"]') || node);
              });
              document.querySelectorAll('main [data-testid*="conversation-turn"], main article').forEach(turn => {
                const roleNode = turn.matches('[data-message-author-role]')
                  ? turn : turn.querySelector('[data-message-author-role]');
                const role = String(roleNode?.getAttribute('data-message-author-role') || '').toLowerCase();
                if (role === 'user') return;
                push(turn.querySelector('.markdown, [class*="markdown"], [class*="prose"]'));
              });
              return out;
            }
            """
        )
    except Exception:
        return []
    return [str(item or "").strip() for item in (result or []) if str(item or "").strip()]


def _wait_plain_answer(
    context: Any,
    page: Any,
    before_count: int,
    job_id: str,
    url: str,
    *,
    timeout_seconds: int = 240,
) -> tuple[Any, str]:
    del before_count
    deadline = time.time() + timeout_seconds
    current = page
    announced = False
    while time.time() < deadline:
        if not reconnect._page_is_alive(current):
            current = reconnect._pick_page(context)
            current = reconnect._ensure_project_page_resilient(context, current, job_id, url, timeout_seconds=60)

        candidates = []
        for raw in _assistant_text_candidates(current):
            value = final_validation._validated_description(raw)
            if value:
                candidates.append(value)
        if candidates:
            candidate = min(candidates, key=lambda value: abs(len(value) - 450))
            if not announced:
                one_click._emit(
                    job_id,
                    f"Descrição final mapeada no Chat 1 ({len(candidate)} caracteres); aguardando apenas o término da resposta…",
                    step="chatgpt_description",
                    progress=30,
                )
                announced = True
            if not simple._assistant_busy(current):
                return current, candidate
        time.sleep(0.8)
    raise RuntimeError("O ChatGPT exibiu a resposta, mas o texto final da descrição não pôde ser mapeado com segurança.")


def _image_candidates(page: Any) -> list[dict[str, Any]]:
    try:
        result = page.evaluate(
            """
            () => [...document.images]
              .filter(img => img.naturalWidth >= 256 && img.naturalHeight >= 256)
              .map((img, index) => {
                const turn = img.closest('[data-testid*="conversation-turn"], article');
                const roleNode = img.closest('[data-message-author-role]') ||
                  (turn && (turn.matches('[data-message-author-role]') ? turn : turn.querySelector('[data-message-author-role]')));
                return {
                  index,
                  src: String(img.currentSrc || img.src || ''),
                  role: String(roleNode?.getAttribute('data-message-author-role') || '').toLowerCase(),
                  text: String(turn?.innerText || '').trim(),
                  width: Number(img.naturalWidth || 0),
                  height: Number(img.naturalHeight || 0),
                  alt: String(img.alt || '')
                };
              })
              .filter(item => item.src && !item.src.includes('avatar') && !item.src.includes('icon'))
            """
        )
    except Exception:
        return []
    return [dict(item) for item in (result or []) if isinstance(item, Mapping)]


def _image_candidate_score(item: Mapping[str, Any]) -> int:
    role = str(item.get("role") or "").lower()
    text = str(item.get("text") or "").lower()
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    if role == "user":
        return -1000
    if "gere somente a imagem principal" in text or "pesquisa visual obrigatória" in text:
        return -1000
    score = 0
    if role == "assistant":
        score += 200
    if "worked for" in text or "pensou por" in text or "editar" in text or "edit" in text:
        score += 80
    if min(width, height) >= 512:
        score += 60
    score += min(40, int(min(width, height) / 32))
    return score


def _decode_data_url(data_url: str) -> bytes:
    match = re.match(r"^data:image/[^;]+;base64,(.+)$", str(data_url or ""), re.I | re.S)
    if not match:
        return b""
    try:
        return base64.b64decode(match.group(1), validate=False)
    except Exception:
        return b""


def _page_image_data_url(page: Any, source: str) -> str:
    try:
        value = page.evaluate(
            """
            async (src) => {
              const images = [...document.images].filter(img =>
                String(img.currentSrc || img.src || '') === String(src || '')
              );
              const img = images.length ? images[images.length - 1] : null;
              if (!img) return '';
              try { await img.decode(); } catch (_) {}
              try {
                const response = await fetch(src, {credentials: 'include'});
                if (response.ok) {
                  const blob = await response.blob();
                  const result = await new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onload = () => resolve(String(reader.result || ''));
                    reader.onerror = reject;
                    reader.readAsDataURL(blob);
                  });
                  if (String(result).startsWith('data:image/')) return result;
                }
              } catch (_) {}
              try {
                const canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth;
                canvas.height = img.naturalHeight;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0);
                return canvas.toDataURL('image/png');
              } catch (_) {
                return '';
              }
            }
            """,
            source,
        )
        return str(value or "")
    except Exception:
        return ""


def _request_image_data_url(page: Any, source: str) -> str:
    if str(source or "").startswith("data:image/"):
        return str(source)
    try:
        request_context = page.context.request
        response = request_context.get(source, timeout=30_000)
        if not response.ok:
            return ""
        raw = response.body()
        if len(raw) < 15_000:
            return ""
        headers = response.headers
        mime = str(headers.get("content-type") or "image/png").split(";", 1)[0].strip()
        if not mime.startswith("image/"):
            mime = "image/png"
        return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
    except Exception:
        return ""


def _extract_image_data_url(page: Any, source: str) -> str:
    direct = _page_image_data_url(page, source)
    if len(_decode_data_url(direct)) >= 15_000:
        return direct
    requested = _request_image_data_url(page, source)
    if len(_decode_data_url(requested)) >= 15_000:
        return requested
    return ""


def _wait_generated_image(
    context: Any,
    page: Any,
    before: set[str],
    job_id: str,
    url: str,
    *,
    timeout_seconds: int,
) -> tuple[Any, str]:
    deadline = time.time() + timeout_seconds
    started = time.time()
    current = page
    reference, reference_sha = final_validation._reference_hash(job_id)
    announced_candidate = False
    announced_read = False
    retry_used = False

    while time.time() < deadline:
        if not reconnect._page_is_alive(current):
            current = reconnect._pick_page(context)
            current = reconnect._ensure_project_page_resilient(context, current, job_id, url, timeout_seconds=60)

        elapsed = time.time() - started
        busy = simple._assistant_busy(current)
        candidates = [
            item for item in _image_candidates(current)
            if str(item.get("src") or "") not in before and _image_candidate_score(item) >= 0
        ]
        candidates.sort(key=_image_candidate_score, reverse=True)

        if candidates and elapsed >= 8:
            if not announced_candidate:
                one_click._emit(
                    job_id,
                    "Imagem do turno do assistente detectada no Chat 2; aguardando o término da geração para capturar os bytes finais…",
                    step="chatgpt_image",
                    progress=68,
                )
                announced_candidate = True

            if not busy:
                for candidate in candidates[:4]:
                    source = str(candidate.get("src") or "")
                    data_url = _extract_image_data_url(current, source)
                    raw = _decode_data_url(data_url)
                    if not raw:
                        continue
                    current_sha = hashlib.sha256(raw).hexdigest()
                    if reference_sha and current_sha == reference_sha:
                        continue
                    if len(raw) < 20_000:
                        continue
                    one_click._emit(
                        job_id,
                        f"Imagem final do Chat 2 capturada e validada em memória ({len(raw):,} bytes).",
                        step="chatgpt_image",
                        progress=74,
                    )
                    return current, data_url

                if not announced_read:
                    one_click._emit(
                        job_id,
                        "A imagem final está visível, mas a URL visual exige leitura autenticada; mantendo as estratégias de captura do navegador ativas…",
                        step="chatgpt_image",
                        progress=70,
                    )
                    announced_read = True

        if (
            not retry_used
            and elapsed >= 20
            and not busy
            and final_validation._is_generation_error_visible(current)
            and final_validation._click_retry(current)
        ):
            retry_used = True
            before.update(str(item.get("src") or "") for item in _image_candidates(current))
            one_click._emit(
                job_id,
                "O ChatGPT exibiu erro de geração; Repetir foi acionado automaticamente e o Chat 2 continua sendo monitorado.",
                step="chatgpt_image",
                progress=66,
            )
            started = time.time()
            announced_candidate = False
            announced_read = False

        time.sleep(1.0)

    raise RuntimeError(
        "A imagem foi solicitada no Chat 2, mas o CrapScraper não conseguiu capturar os bytes da geração final dentro do prazo."
    )


def _conversation_url(page: Any, timeout_seconds: int = 10) -> str:
    deadline = time.time() + timeout_seconds
    latest = ""
    while time.time() < deadline:
        try:
            latest = str(page.url or "")
        except Exception:
            latest = ""
        if "/c/" in latest or re.search(r"/project/.+?/c/", latest):
            return latest
        time.sleep(0.4)
    return latest


def _send_message_tracked(
    context: Any,
    page: Any,
    prompt: str,
    job_id: str,
    url: str,
) -> tuple[Any, int, set[str]]:
    result = _ORIGINAL_SEND_MESSAGE(context, page, prompt, job_id, url)
    current = result[0]
    chat_url = _conversation_url(current)
    lowered = str(prompt or "").lower()
    if "breve descrição comercial" in lowered:
        additions._update(job_id, description_chat_url=chat_url)
        one_click._emit(job_id, "Chat 1 mapeado e vinculado ao job de descrição.", step="chatgpt_description")
    elif "imagem principal" in lowered:
        additions._update(job_id, image_chat_url=chat_url)
        one_click._emit(job_id, "Chat 2 mapeado e vinculado ao job de imagem.", step="chatgpt_image")
    return result


def _save_description_tracked(job_id: str, description: str) -> dict[str, Any]:
    result = final_validation._save_plain_description(job_id, description)
    cleaned = str(result.get("short_description") or "").encode("utf-8")
    if cleaned:
        additions._update(job_id, description_sha256=hashlib.sha256(cleaned).hexdigest())
    return additions._row(job_id)


def _run_two_chats_mapped(job_id: str) -> dict[str, Any]:
    _resolve_official_for_job(job_id)
    return _ORIGINAL_RUN_TWO_CHATS(job_id)


def install_addition_conversation_capture_policy() -> None:
    global _INSTALLED, _ORIGINAL_RUN_TWO_CHATS, _ORIGINAL_SEND_MESSAGE
    if _INSTALLED:
        return

    _ensure_tracking_schema()
    _ORIGINAL_RUN_TWO_CHATS = simple._run_two_chats
    _ORIGINAL_SEND_MESSAGE = reconnect._send_message_resilient

    simple._run_two_chats = _run_two_chats_mapped
    simple._description_prompt = _description_prompt
    simple._wait_plain_answer = _wait_plain_answer
    simple._save_plain_description = _save_description_tracked
    creative._image_only_prompt = _image_prompt
    reconnect._send_message_resilient = _send_message_tracked
    reconnect._wait_new_image_resilient = _wait_generated_image

    _INSTALLED = True
