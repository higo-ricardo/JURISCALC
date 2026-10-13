"""Reuso de conexão no SqliteRepository — uma conexão por bloco `with`."""
import sqlite3
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

from backend.engine import CalculadoraFacade, JurosSimples, SqliteRepository, Verba
from backend.storage import Database


class TestSqliteRepositoryConexao(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.db = Path(self.td.name) / "repo.db"
        Database(self.db).init()

    def tearDown(self):
        self.td.cleanup()

    def _contar_connects(self):
        return mock.patch("sqlite3.connect", wraps=sqlite3.connect)

    def test_01_uma_conexao_por_bloco(self):
        with self._contar_connects() as spy:
            with SqliteRepository(str(self.db)) as repo:
                for c in ("2020-01", "2020-02", "2020-03", "2026-10"):
                    repo.buscar("IPCA-E", c)
        self.assertEqual(spy.call_count, 1,
                         "4 buscas deveriam abrir 1 conexão, não 4")

    def test_02_mesma_conexao_durante_o_bloco(self):
        with SqliteRepository(str(self.db)) as repo:
            primeiro = repo._con
            repo.buscar("IPCA-E", "2020-01")
            self.assertIs(repo._con, primeiro)

    def test_03_conexao_fechada_ao_sair(self):
        with SqliteRepository(str(self.db)) as repo:
            con = repo._con
        with self.assertRaises(sqlite3.ProgrammingError):
            con.execute("SELECT 1")
        self.assertIsNone(repo._con)

    def test_04_fecha_mesmo_com_excecao(self):
        repo = SqliteRepository(str(self.db))
        try:
            with repo:
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        self.assertIsNone(repo._con)

    def test_05_modo_avulso_preservado(self):
        """Chamar buscar() sem `with` continua funcionando (compatibilidade)."""
        repo = SqliteRepository(str(self.db))
        self.assertIsNone(repo._con)
        v = repo.buscar("IPCA-E", "2026-10")
        self.assertIsInstance(v, Decimal)
        self.assertIsNone(repo._con, "modo avulso não deve guardar conexão")

    def test_06_close_idempotente(self):
        repo = SqliteRepository(str(self.db))
        repo.close()
        with repo:
            pass
        repo.close()

    def test_07_erro_de_indice_continua_sendo_keyerror(self):
        with SqliteRepository(str(self.db)) as repo:
            with self.assertRaises(KeyError):
                repo.buscar("IPCA-E", "1999-01")

    def test_08_calculo_com_10_verbas_usa_uma_conexao(self):
        """O caso real: 10 verbas x 2 buscas = 20 buscas, 1 conexão."""
        verbas = [Verba(f"v{i}", Decimal("1000"), date(2023, 6, 15),
                        "IPCA-E", Decimal("0.01")) for i in range(10)]
        with self._contar_connects() as spy:
            with SqliteRepository(str(self.db)) as repo:
                facade = CalculadoraFacade(repo, juros=JurosSimples())
                r = facade.calcular_processo(verbas, date(2026, 10, 7))
        self.assertEqual(len(r["verbas"]), 10)
        self.assertEqual(spy.call_count, 1)
        self.assertGreater(r["total"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
