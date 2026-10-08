"""Persistência de cálculos + init geral do SQLite."""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_DEFAULT = ROOT / "data" / "indices.db"
SCHEMA = Path(__file__).with_name("tabelas") / "schema.sql"
CSV_SEED = Path(__file__).with_name("tabelas") / "indices_exemplo.csv"


class Database:
    """Dono da conexão/transação. Ninguém fora daqui abre sqlite3 diretamente."""

    def __init__(self, path: Path | str = DB_DEFAULT):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.path))

    def init(self, seed: bool = True) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = self.connect()
        try:
            con.executescript(SCHEMA.read_text(encoding="utf-8"))
            con.commit()
        finally:
            con.close()
        if seed and CSV_SEED.exists():
            self.seed_csv()
        return self.path

    def seed_csv(self) -> int:
        con = self.connect()
        try:
            n = 0
            with open(CSV_SEED, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    con.execute(
                        "INSERT OR IGNORE INTO indices(indice, competencia, valor, fonte) VALUES (?,?,?,?)",
                        (row["indice"].strip(), row["competencia"].strip(),
                         float(row["valor"]), row.get("fonte", "csv").strip()),
                    )
                    n += 1
            con.commit()
            return n
        finally:
            con.close()


class CalculoRepository:
    """Persiste e lista cálculos. Recebe o Database por DI."""

    def __init__(self, db: Database):
        self._db = db

    def salvar(self, processo: str, preset: str, data_fim: str,
               resultado: dict, verbas_input: list[dict]) -> int:
        con = self._db.connect()
        try:
            cur = con.execute(
                "INSERT INTO calculos(processo, preset, data_fim, base, honorarios, custas, multa, total)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (processo, preset, data_fim, float(resultado["base"]), float(resultado["honorarios"]),
                 float(resultado["custas"]), float(resultado["multa"]), float(resultado["total"])),
            )
            cid = cur.lastrowid
            for r, vin in zip(resultado["verbas"], verbas_input):
                con.execute(
                    "INSERT INTO calculo_itens(calculo_id, verba, valor_base, data_base, corrigido, juros, total)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (cid, r.verba, float(vin["valor_base"]), vin["data_base"],
                     float(r.corrigido), float(r.juros), float(r.total)),
                )
            con.commit()
            return cid
        finally:
            con.close()

    def listar(self, limit: int = 20) -> list[tuple]:
        con = self._db.connect()
        try:
            return con.execute(
                "SELECT id, processo, preset, data_fim, total, criado_em FROM calculos ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            con.close()
