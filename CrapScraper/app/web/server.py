from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from app.configuration import Settings
from app.web.api import ApplicationServices
from app.web.routes import get_route, post_route


class Application:
    def __init__(self, settings: Settings, services: ApplicationServices): self.settings, self.services = settings, services

    def serve(self) -> None:
        settings, services = self.settings, self.services
        template = settings.root / "app" / "web" / "templates" / "panel.html"
        static = settings.root / "app" / "static"

        class Handler(BaseHTTPRequestHandler):
            def send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
                self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            def send_json(self, value: object, status: int = 200) -> None: self.send_bytes(json.dumps(value, ensure_ascii=False, default=str).encode(), "application/json; charset=utf-8", status)
            def do_GET(self) -> None:
                path = urlparse(self.path).path
                try:
                    if path == "/": return self.send_bytes(template.read_bytes(), "text/html; charset=utf-8")
                    if path.startswith("/static/"):
                        target = (static / path.removeprefix("/static/")).resolve()
                        if static.resolve() not in target.parents: raise FileNotFoundError
                        return self.send_bytes(target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream")
                    return self.send_json(get_route(services, path))
                except (KeyError, FileNotFoundError): self.send_json({"ok": False, "message": "Não encontrado"}, 404)
                except Exception as error: self.send_json({"ok": False, "message": str(error)}, 500)
            def do_POST(self) -> None:
                try:
                    size = int(self.headers.get("Content-Length", "0")); payload = json.loads(self.rfile.read(size) or b"{}")
                    self.send_json(post_route(services, urlparse(self.path).path, payload))
                except KeyError: self.send_json({"ok": False, "message": "Não encontrado"}, 404)
                except Exception as error: self.send_json({"ok": False, "message": str(error)}, 400)
            def log_message(self, format: str, *args: object) -> None: pass

        server = ThreadingHTTPServer((settings.host, settings.port), Handler)
        print(f"CrapScraper consolidado em http://{settings.host}:{settings.port}", flush=True)
        server.serve_forever()
