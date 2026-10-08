"""E2E stdlib (unittest): CalculadoraService -> sqlite -> HTTP API. Sem pytest."""
import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import HTTPServer
from pathlib import Path

from backend.service import CalculadoraService
from backend.storage import Database
from frontend.app import HandlerFactory


class TestE2E(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.svc = CalculadoraService(Database(Path(self.td.name) / "e2e.db"))
        self.svc.init()

    def tearDown(self):
        self.td.cleanup()

    def test_01_presets(self):
        p = self.svc.get_presets()
        self.assertIn("TJSP_CIVEL", p)
        self.assertIn("FAZENDA_EC113", p)
        self.assertIn("TJMA_CIVEL", p)

    def test_02_calcular_e_persistir(self):
        r = self.svc.calcular({
            "processo": "e2e-001", "preset": "TJSP_CIVEL", "data_fim": "2026-10-07",
            "verbas": [{"nome": "Dano moral", "valor_base": 20000,
                        "data_base": "2023-06-15", "juros_ini": "2023-06-15"}],
            "honorarios_perc": 10, "custas": 0})
        self.assertEqual(r["processo"], "e2e-001")
        self.assertGreater(r["total"], 20000)
        self.assertEqual(r["total"], round(r["base"] + r["honorarios"], 2))
        rows = self.svc.listar()
        self.assertTrue(any(x["processo"] == "e2e-001" for x in rows))

    def test_03_validacao(self):
        with self.assertRaises(ValueError):
            self.svc.calcular({"processo": "x", "preset": "TJSP_CIVEL",
                               "data_fim": "2026-10-07", "verbas": []})
        with self.assertRaises(KeyError):
            self.svc.calcular({"processo": "x", "preset": "INEXISTENTE",
                               "data_fim": "2026-10-07",
                               "verbas": [{"nome": "D", "valor_base": 1,
                                           "data_base": "2023-06-15"}]})

    def test_04_http_api(self):
        srv = HTTPServer(("127.0.0.1", 0), HandlerFactory(self.svc).handler_class())
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            base = f"http://127.0.0.1:{port}"
            pres = json.loads(urllib.request.urlopen(base + "/api/presets").read())
            self.assertIn("TJSP_CIVEL", pres)
            dto = {"processo": "e2e-http", "preset": "TJSP_CIVEL", "data_fim": "2026-10-07",
                   "verbas": [{"nome": "D", "valor_base": 100,
                               "data_base": "2023-06-15"}]}
            req = urllib.request.Request(base + "/api/calcular", data=json.dumps(dto).encode(),
                                         headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req).read())
            self.assertEqual(r["processo"], "e2e-http")
            self.assertGreater(r["total"], 100)
            calcs = json.loads(urllib.request.urlopen(base + "/api/calculos").read())
            self.assertTrue(any(c["processo"] == "e2e-http" for c in calcs))
            # erro 400 em DTO inválido
            bad = urllib.request.Request(base + "/api/calcular",
                                         data=json.dumps({"processo": "x"}).encode(),
                                         headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(bad)
                self.fail("esperava 400")
            except Exception as e:
                self.assertIn("400", str(e))
        finally:
            srv.shutdown()
            t.join(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
