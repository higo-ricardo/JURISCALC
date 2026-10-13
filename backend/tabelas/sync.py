"""Sync IBGE/BACEN -> SQLite. Idempotente, com log e validação.

Uso:
  python -m backend.tabelas.sync --init
  python -m backend.tabelas.sync --tudo --de 2020-01 --ate 2026-10
  python -m backend.tabelas.sync --indice IPCA-E --de 2024-01 --ate 2026-10
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.request
from datetime import datetime
from pathlib import Path

DB_DEFAULT = Path(__file__).resolve().parents[2] / "data" / "indices.db"
SCHEMA = Path(__file__).with_name("schema.sql")

BACEN_SGS = {"SELIC": 11, "TR": 226}
# SIDRA: IPCA=1419 IPCA-E=1419+? INPC=1420 — confirmar agregados; fallback usa série mensal
IBGE_SIDRA = {"IPCA": "1419", "IPCA-E": "1436", "INPC": "1420"}
INDICES = ["IPCA-E", "IPCA", "INPC", "SELIC", "TR"]


def init_db(db_path: Path = DB_DEFAULT) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.commit()
    con.close()


def _get(url: str, retries: int = 3) -> object:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "calculadora-judicial/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"GET falhou {url}: {last}")


def fetch_bcb(indice: str, de: str, ate: str) -> list[tuple[str, float]]:
    """Retorna [(AAAA-MM, valor_mensal)]. SELIC diária é agregada por mês (soma simples)."""
    codigo = BACEN_SGS[indice]
    di = de.replace("-", "") + "01"
    # ate: último dia aproximado
    df = ate.replace("-", "") + "28"
    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
           f"?formato=json&dataInicial={di}&dataFinal={df}")
    raw = _get(url)
    agg: dict[str, float] = {}
    for row in raw:
        # row: {"data": "dd/mm/aaaa", "valor": "0,01"}
        dt = datetime.strptime(row["data"], "%d/%m/%Y")
        comp = f"{dt.year:04d}-{dt.month:02d}"
        agg[comp] = agg.get(comp, 0.0) + float(str(row["valor"]).replace(",", "."))
    return sorted(agg.items())


def fetch_ibge(indice: str, de: str, ate: str) -> list[tuple[str, float]]:
    """SIDRA mensal. Retorna [(AAAA-MM, índice número-índice)]."""
    tabela = IBGE_SIDRA[indice]
    # categoria 2266 = número-índice; período em AAAAMM
    url = (f"https://apisidra.ibge.gov.br/values/t/{tabela}/n1/all/v/2266"
           f"/p/{de.replace('-', '')}-{ate.replace('-', '')}/c315/all")
    raw = _get(url)
    out = []
    for row in raw[1:]:  # pula cabeçalho
        # colunas variam; tenta extrair mês e valor
        mes = str(row.get("Mês (Código)", row.get("Mês", "")))
        if len(mes) == 6 and mes.isdigit():
            out.append((f"{mes[:4]}-{mes[4:]}", float(str(row.get("Valor", 0)).replace(",", "."))))
    return sorted(out)


def upsert(db_path: Path, indice: str, competencia: str, valor: float, fonte: str) -> None:
    if abs(valor) > 1e9:
        raise ValueError(f"valor absurdo {indice} {competencia}={valor}, bloqueado")
    con = sqlite3.connect(str(db_path))
    con.execute(
        "INSERT OR REPLACE INTO indices(indice, competencia, valor, fonte) VALUES (?,?,?,?)",
        (indice, competencia, valor, fonte),
    )
    con.commit()
    con.close()


def log(con: sqlite3.Connection, fonte: str, indice: str, periodo: str, status: str, msg: str = ""):
    con.execute(
        "INSERT INTO sync_log(fonte, indice, periodo, status, mensagem) VALUES (?,?,?,?,?)",
        (fonte, indice, periodo, status, msg),
    )
    con.commit()


def sync_indice(db_path: Path, indice: str, de: str, ate: str, dry: bool = False) -> int:
    if indice not in IBGE_SIDRA and indice not in BACEN_SGS:
        raise ValueError(f"indice desconhecido: {indice!r}; use um de {INDICES}")
    fonte = "BACEN" if indice in BACEN_SGS else "IBGE"
    _fetch = fetch_bcb if indice in BACEN_SGS else fetch_ibge
    periodo = f"{de}..{ate}"
    con = sqlite3.connect(str(db_path))
    try:
        dados = _fetch(indice, de, ate)
        if not dry:
            for comp, val in dados:
                upsert(db_path, indice, comp, val, fonte)
        log(con, fonte, indice, periodo, "OK", f"{len(dados)} competências")
        return len(dados)
    except Exception as e:
        log(con, fonte, indice, periodo, "ERRO", str(e))
        raise
    finally:
        con.close()


class Sincronizador:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)

    def listar_indices(self) -> list[dict]:
        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.execute(
                "SELECT indice, fonte, MAX(competencia), COUNT(*) FROM indices GROUP BY indice ORDER BY indice"
            ).fetchall()
        finally:
            con.close()
        res = []
        for ind, fonte, ultima, n in cur:
            res.append(
                {
                    "indice": ind,
                    "fonte": fonte or ("IBGE" if ind in IBGE_SIDRA else ("BACEN" if ind in BACEN_SGS else "—")),
                    "ultima": ultima,
                    "n": int(n) if n else 0,
                }
            )
        order = {"IPCA-E": 0, "IPCA": 1, "INPC": 2, "SELIC": 3, "TR": 4, "IGP-M": 5}
        return sorted(res, key=lambda x: order.get(x["indice"], 99))

    def sync(self, *, indice: str | None = None, tudo: bool = False, de: str = "2020-01", ate: str = "2026-10") -> int:
        alvos = INDICES if tudo else ([indice] if indice else [])
        if not alvos:
            raise ValueError("use 'tudo' ou 'indice'")
        total = 0
        for ind in alvos:
            total += sync_indice(self.db_path, ind, de, ate, dry=False)
        return total

    def ultimo_log(self, limit: int = 20) -> list[dict]:
        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.execute(
                "SELECT executado_em, fonte, indice, periodo, status, mensagem FROM sync_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            con.close()
        return [
            {
                "executado_em": r[0],
                "fonte": r[1],
                "indice": r[2],
                "periodo": r[3],
                "status": r[4],
                "mensagem": r[5] or "",
            }
            for r in cur
        ]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--tudo", action="store_true")
    ap.add_argument("--indice", default=None)
    ap.add_argument("--de", default="2020-01")
    ap.add_argument("--ate", default="2026-10")
    ap.add_argument("--db", default=str(DB_DEFAULT))
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    db = Path(a.db)
    if a.init:
        init_db(db)
        print(f"DB pronto em {db}")
    alvos = INDICES if a.tudo else ([a.indice] if a.indice else [])
    for ind in alvos:
        n = sync_indice(db, ind, a.de, a.ate, dry=a.dry)
        print(f"{ind}: {n} competências {'(dry)' if a.dry else 'gravadas'}")
