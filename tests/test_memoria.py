"""Testes do MemoriaBuilder — incluindo o cache do brasão."""
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from reports.memoria_pdf import MemoriaBuilder

TOTAL = {
    "base": Decimal("20000.00"),
    "honorarios": Decimal("2000.00"),
    "custas": Decimal("0.00"),
    "multa": Decimal("0.00"),
    "total": Decimal("22000.00"),
}


class TestMemoriaBuilder(unittest.TestCase):
    def test_01_gera_html_com_totais(self):
        b = MemoriaBuilder("proc-1")
        b.add_verba("Dano moral", Decimal("20000"), "2023-06-15",
                    Decimal("21000"), Decimal("1000"), Decimal("22000"))
        with tempfile.TemporaryDirectory() as td:
            out = b.to_html(TOTAL, str(Path(td) / "m.html"))
            html = Path(out).read_text(encoding="utf-8")
        self.assertIn("proc-1", html)
        self.assertIn("Dano moral", html)
        self.assertIn("22000.00", html)

    def test_02_logo_eh_cacheado_uma_vez(self):
        """A segunda geração não pode ler o disco de novo."""
        MemoriaBuilder._logo.cache_clear()
        with mock.patch.object(Path, "exists", return_value=True), \
             mock.patch.object(Path, "read_bytes", return_value=b"\xff\xd8\xff") as read:
            MemoriaBuilder._logo()
            self.assertEqual(read.call_count, 1)
            MemoriaBuilder._logo()
            MemoriaBuilder._logo()
            self.assertEqual(read.call_count, 1, "logo deveria ter vindo do cache")
        self.assertEqual(MemoriaBuilder._logo.cache_info().hits, 2)

    def test_03_logo_retorna_string_sempre(self):
        MemoriaBuilder._logo.cache_clear()
        with mock.patch.object(Path, "exists", return_value=False):
            v = MemoriaBuilder._logo()
        self.assertIsInstance(v, str)

    def test_04_logo_real_resolve_pelo_caminho_do_modulo(self):
        """Trava contra a remoção do fallback: o brasão tem que ser achado de verdade."""
        MemoriaBuilder._logo.cache_clear()
        self.assertTrue((Path(__file__).resolve().parents[1] / "TJMA.jpg").exists(),
                        "TJMA.jpg deveria estar na raiz do projeto")
        html = MemoriaBuilder._logo()
        self.assertIn("data:image/jpeg;base64,", html)
        self.assertGreater(len(html), 1000)

    def test_05_sem_caminho_absoluto_com_usuario(self):
        """Nenhum caminho hardcoded de máquina deve sobrar no fonte."""
        fonte = Path(__file__).resolve().parents[1] / "reports" / "memoria_pdf.py"
        texto = fonte.read_text(encoding="utf-8")
        for suspeito in ("C:/Users/", "C:\\Users\\", "Desktop/CALCULADORA"):
            self.assertNotIn(suspeito, texto, f"caminho absoluto encontrado: {suspeito}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
