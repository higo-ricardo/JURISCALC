from pathlib import Path
import sqlite3
import tempfile
from backend.tabelas.sync import init_db, upsert
from backend.tabelas.loader import ultimo_mes
from backend.engine import SqliteRepository


def test_upsert_e_repo_sqlite():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        init_db(db)
        upsert(db, "IPCA-E", "2026-10", 145.30, "TESTE")
        assert ultimo_mes(str(db), "IPCA-E") == "2026-10"
        assert float(SqliteRepository(str(db)).buscar("IPCA-E", "2026-10")) == 145.30
