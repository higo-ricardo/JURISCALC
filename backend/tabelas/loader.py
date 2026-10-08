"""Consultas de índices no SQLite (ver schema.sql)."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def ultimo_mes(db_path: str | Path, indice: str) -> str | None:
    con = sqlite3.connect(str(db_path))
    try:
        row = con.execute(
            "SELECT MAX(competencia) FROM indices WHERE indice=?", (indice,)
        ).fetchone()
    finally:
        con.close()
    return row[0] if row else None
