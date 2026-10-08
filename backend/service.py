"""Camada de aplicação — CalculadoraService é o único ponto de entrada.

Contrato DTO (dict/JSON puro, sem Decimal, sem classes de domínio):
  entrada calcular = {processo, preset, data_fim(AAAA-MM-DD), verbas[{nome, valor_base, data_base, juros_ini?}], honorarios_perc, custas, multa?}
  saída = {id, base, honorarios, custas, multa, total, verbas[{nome, corrigido, juros, total}]}
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from backend.engine import (
    CalculadoraFacade, D, JurosComposto, JurosSimples, SelicUnica, SqliteRepository, Verba,
)
from backend.presets import PresetRegistry
from backend.storage import CalculoRepository, Database

JUROS_POR_TIPO = {
    "simples": JurosSimples(),
    "composto": JurosComposto(),
    "selic_unica": SelicUnica(),
}


class CalculadoraService:
    """Fachada de aplicação. Dependências via construtor; sem global, sem I/O direto."""

    def __init__(self, db: Database, presets: PresetRegistry | None = None):
        self._db = db
        self._presets = presets or PresetRegistry()

    def init(self, seed: bool = True) -> None:
        self._db.init(seed)

    def get_presets(self) -> dict:
        return {k: {"descricao": self._presets.obter(k).descricao,
                    "indice": self._presets.obter(k).indice,
                    "taxa_am": float(self._presets.obter(k).taxa_am),
                    "tipo_juros": self._presets.obter(k).tipo_juros}
                for k in self._presets.listar()}

    def calcular(self, dto: dict) -> dict:
        """Use-case único: valida DTO, calcula, persiste, retorna DTO puro."""
        self._db.init()
        preset = self._presets.obter(dto.get("preset", "TJSP_CIVEL"))
        data_fim = date.fromisoformat(dto["data_fim"])
        verbas: list[Verba] = []
        for v in dto.get("verbas", []):
            if not v.get("nome") or float(v.get("valor_base", 0)) < 0:
                raise ValueError(f"verba inválida: {v}")
            db0 = date.fromisoformat(v["data_base"])
            ji = date.fromisoformat(v.get("juros_ini", v["data_base"]))
            verbas.append(Verba(v["nome"], D(str(v["valor_base"])), db0,
                                preset.indice, preset.taxa_am, ji, data_fim))
        if not verbas:
            raise ValueError("adicione ao menos 1 verba")
        facade = CalculadoraFacade(SqliteRepository(str(self._db.path)),
                                   juros=JUROS_POR_TIPO[preset.tipo_juros])
        try:
            r = facade.calcular_processo(
                verbas, data_fim, [],
                D(str(dto.get("honorarios_perc", 10))) / D(100),
                D(str(dto.get("custas", 0))), D(str(dto.get("multa", 0))),
            )
        except KeyError as e:
            raise KeyError(f"{e} — rode sync ou confira competência") from e
        vin = [{"valor_base": v.valor_base, "data_base": v.data_base.isoformat()} for v in verbas]
        cid = CalculoRepository(self._db).salvar(
            dto.get("processo", ""), preset.codigo, data_fim.isoformat(), r, vin)
        return {"id": cid, "processo": dto.get("processo", ""), "preset": preset.codigo,
                "base": float(r["base"]), "honorarios": float(r["honorarios"]),
                "custas": float(r["custas"]), "multa": float(r["multa"]), "total": float(r["total"]),
                "verbas": [{"nome": v.verba, "corrigido": float(v.corrigido),
                            "juros": float(v.juros), "total": float(v.total)} for v in r["verbas"]]}

    def listar(self, limit: int = 20) -> list[dict]:
        self._db.init(seed=False)
        return [{"id": r[0], "processo": r[1], "preset": r[2], "data_fim": r[3],
                 "total": r[4], "em": r[5]} for r in CalculoRepository(self._db).listar(limit)]
