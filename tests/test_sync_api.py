"""Testes da rota de atualização de tabelas. Sem rede: Sincronizador falso injetado."""
import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from backend.service import CalculadoraService
from backend.storage import Database
from frontend.app import HandlerFactory


class SincronizadorFake:
    """Substitui a rede. Guardado por lock porque roda em thread de fundo."""

    def __init__(self, falhar_em=None):
        self.falhar_em = falhar_em
        self.chamadas = []
        self._lib = threading.Event()
        self._lib.set()

    def listar_indices(self):
        return [{"indice": "IPCA-E", "fonte": "IBGE", "ultima": "2026-10", "n": 82},
                {"indice": "IGP-M", "fonte": "—", "ultima": "2026-10", "n": 82}]

    def sync(self, *, indice=None, tudo=False, de="2020-01", ate="2026-10"):
        self.chamadas.append(indice)
        self._lib.wait(timeout=5)
        if indice == self.falhar_em:
            raise RuntimeError("timeout simulado")
        return 82

    def ultimo_log(self, limit=20):
        return [{"executado_em": "2026-10-09 14:22:00", "fonte": "IBGE", "indice": "IPCA-E",
                 "periodo": "2020-01..2026-10", "status": "OK", "mensagem": "82 competências"}]


class TestSyncAPI(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        db = Path(self.td.name) / "sync.db"
        self.sync = SincronizadorFake()
        self.svc = CalculadoraService(Database(db), sincronizador=self.sync)
        self.svc.init()

    def tearDown(self):
        self.sync._lib.set()
        self.td.cleanup()

    def _servidor(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), HandlerFactory(self.svc).handler_class())
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()

        def fechar():
            srv.shutdown()
            t.join(5)
            srv.server_close()

        self.addCleanup(fechar)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    def test_01_listar_indices(self):
        r = self.svc.listar_indices()
        self.assertEqual(r[0]["indice"], "IPCA-E")
        self.assertEqual(r[0]["n"], 82)

    def test_02_status_inicial(self):
        st = self.svc.status_sync()
        self.assertFalse(st["rodando"])
        self.assertEqual(st["progresso"], 0)
        self.assertIsNone(st["erro"])
        self.assertEqual(len(st["log"]), 1)

    def test_03_sync_dispara_e_responde_na_hora(self):
        self.sync._lib.clear()
        try:
            r = self.svc.sincronizar(tudo=True, de="2024-01", ate="2026-10")
            self.assertTrue(r["iniciado"])
            self.assertEqual(len(r["alvos"]), 5)
            # devolveu enquanto o sync ainda rodava — o request não bloqueou
            self.assertTrue(self.svc.status_sync()["rodando"])
        finally:
            self.sync._lib.set()
        self._espera_fim()
        self.assertEqual(self.sync.chamadas,
                         ["IPCA-E", "IPCA", "INPC", "SELIC", "TR"])

    def test_04_recusa_sync_concorrente(self):
        self.sync._lib.clear()
        try:
            self.svc.sincronizar(tudo=True)
            with self.assertRaises(ValueError):
                self.svc.sincronizar(tudo=True)
        finally:
            self.sync._lib.set()
        self._espera_fim()

    def test_05_indice_invalido(self):
        with self.assertRaises(ValueError):
            self.svc.sincronizar(indice="XPTO")
        with self.assertRaises(ValueError):
            self.svc.sincronizar()

    def test_06_falha_de_um_indice_nao_derruba_os_outros(self):
        self.sync.falhar_em = "INPC"
        self.svc.sincronizar(tudo=True)
        self._espera_fim()
        st = self.svc.status_sync()
        self.assertFalse(st["rodando"])
        self.assertIn("INPC", st["erro"])
        self.assertEqual(len(self.sync.chamadas), 5)

    def test_07_rota_post_devolve_202(self):
        base = self._servidor()
        req = urllib.request.Request(base + "/api/sync", data=json.dumps(
            {"tudo": True, "de": "2024-01", "ate": "2026-10"}).encode(),
            headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req)
        self.assertEqual(resp.status, 202)
        self.assertTrue(json.loads(resp.read())["iniciado"])
        self._espera_fim()

    def test_08_rota_post_400_em_payload_invalido(self):
        base = self._servidor()
        req = urllib.request.Request(base + "/api/sync", data=json.dumps(
            {"indice": "XPTO"}).encode(), headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            self.fail("esperava 400")
        except Exception as e:
            self.assertIn("400", str(e))

    def test_09_rotas_get_e_paginas(self):
        base = self._servidor()
        for rota, tipo in (("/", "text/html"), ("/tabelas", "text/html"),
                          ("/static/app.css", "text/css"), ("/api/indices", "application/json"),
                          ("/api/sync", "application/json")):
            r = urllib.request.urlopen(base + rota)
            self.assertIn(tipo, r.headers["Content-Type"], rota)
        self.assertTrue(json.loads(urllib.request.urlopen(base + "/api/indices").read()))

    def _espera_fim(self, timeout=10):
        for _ in range(int(timeout / 0.05)):
            if not self.svc.status_sync()["rodando"]:
                return
            threading.Event().wait(0.05)
        self.fail("sync nao terminou em %ss" % timeout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
