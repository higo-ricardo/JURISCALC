"""Servidor web stdlib — depende só da porta (protocolo), nunca do service concreto."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from backend.ports import AppPort

STATIC = Path(__file__).with_name("static")
PAGINAS = {
    "/": "index.html",
    "/index.html": "index.html",
    "/tabelas": "tabelas.html",
    "/tabelas.html": "tabelas.html",
}


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

            def _json(self, code: int, obj):
                return self._send(code, json.dumps(obj).encode())

            def _body(self) -> dict:
                n = int(self.headers.get("Content-Length", 0))
                return json.loads(self.rfile.read(n) or b"{}")

            def do_GET(self):
                p = urlparse(self.path).path
                if p in PAGINAS:
                    html = STATIC.joinpath(PAGINAS[p]).read_bytes()
                    return self._send(200, html, "text/html; charset=utf-8")
                if p == "/static/app.css":
                    css = STATIC.joinpath("app.css").read_bytes()
                    return self._send(200, css, "text/css; charset=utf-8")
                if p == "/api/presets":
                    return self._json(200, svc.get_presets())
                if p == "/api/calculos":
                    return self._json(200, svc.listar())
                if p == "/api/indices":
                    return self._json(200, svc.listar_indices())
                if p == "/api/sync":
                    return self._json(200, svc.status_sync())
                return self._send(404, b'{"erro":"rota inexistente"}')

            def do_POST(self):
                p = urlparse(self.path).path
                if p == "/api/sync":
                    try:
                        data = self._body()
                        r = svc.sincronizar(
                            indice=data.get("indice"),
                            tudo=bool(data.get("tudo")),
                            de=data.get("de", "2020-01"),
                            ate=data.get("ate", "2026-10"),
                        )
                        return self._json(202, r)
                    except (KeyError, ValueError) as e:
                        return self._json(400, {"erro": str(e)})
                    except Exception as e:
                        return self._json(500, {"erro": f"interno: {e}"})
                if p != "/api/calcular":
                    return self._send(404, b'{"erro":"rota inexistente"}')
                try:
                    data = self._body()
                    return self._json(200, svc.calcular(data))
                except (KeyError, ValueError) as e:
                    return self._json(400, {"erro": str(e)})
                except Exception as e:
                    return self._json(500, {"erro": f"interno: {e}"})

        return Handler


class WebServer:
    """Servidor HTTP com dependências no construtor."""

    def __init__(self, port: AppPort, http_port: int = 8000):
        self._factory = HandlerFactory(port)
        self._http_port = http_port

    def build(self, host: str = "127.0.0.1") -> ThreadingHTTPServer:
        """ThreadingHTTPServer: o sync de índices leva minutos e não pode
        monopolizar a única thread do servidor."""
        return ThreadingHTTPServer((host, self._http_port), self._factory.handler_class())

    def run(self):
        print(f"Interface em http://localhost:{self._http_port}")
        print(f"Tabelas    em http://localhost:{self._http_port}/tabelas")
        self.build().serve_forever()


if __name__ == "__main__":
    import sys

    from backend.service import CalculadoraService
    from backend.storage import Database

    WebServer(CalculadoraService(Database()), int(sys.argv[1]) if len(sys.argv) > 1 else 8000).run()
