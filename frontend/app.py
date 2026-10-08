"""Servidor web stdlib — depende só da porta (protocolo), nunca do service concreto."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from backend.ports import AppPort

STATIC = Path(__file__).with_name("static")


class HandlerFactory:
    """Cria Handlers com a porta amarrada no construtor. Zero global."""

    def __init__(self, port: AppPort):
        self._port = port

    def handler_class(self) -> type[BaseHTTPRequestHandler]:
        svc = self._port

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code: int, body: bytes, ctype: str = "application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                p = urlparse(self.path).path
                if p in ("/", "/index.html"):
                    html = STATIC.joinpath("index.html").read_bytes()
                    return self._send(200, html, "text/html; charset=utf-8")
                if p == "/api/presets":
                    return self._send(200, json.dumps(svc.get_presets()).encode())
                if p == "/api/calculos":
                    return self._send(200, json.dumps(svc.listar()).encode())
                return self._send(404, b'{"erro":"rota inexistente"}')

            def do_POST(self):
                if urlparse(self.path).path != "/api/calcular":
                    return self._send(404, b'{"erro":"rota inexistente"}')
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    data = json.loads(self.rfile.read(n) or b"{}")
                    return self._send(200, json.dumps(svc.calcular(data)).encode())
                except (KeyError, ValueError) as e:
                    return self._send(400, json.dumps({"erro": str(e)}).encode())
                except Exception as e:
                    return self._send(500, json.dumps({"erro": f"interno: {e}"}).encode())

        return Handler


class WebServer:
    """Servidor HTTP com dependências no construtor."""

    def __init__(self, port: AppPort, http_port: int = 8000):
        self._factory = HandlerFactory(port)
        self._http_port = http_port

    def build(self, host: str = "127.0.0.1") -> HTTPServer:
        return HTTPServer((host, self._http_port), self._factory.handler_class())

    def run(self):
        print(f"Interface em http://localhost:{self._http_port}")
        self.build().serve_forever()


if __name__ == "__main__":
    import sys

    from backend.service import CalculadoraService
    from backend.storage import Database

    WebServer(CalculadoraService(Database()), int(sys.argv[1]) if len(sys.argv) > 1 else 8000).run()
