"""Camada de aplicação — CalculadoraService é o único ponto de entrada.

Contrato DTO (dict/JSON puro, sem Decimal, sem classes de domínio):
  entrada calcular = {processo, preset, data_fim(AAAA-MM-DD), verbas[{nome, valor_base, data_base, juros_ini?}], honorarios_perc, custas, multa?}
  saída = {id, base, honorarios, custas, multa, total, verbas[{nome, corrigido, juros, total}]}
"""
from __future__ import annotations

import threading
from datetime import date
from pathlib import Path

from backend.engine import (
    CalculadoraFacade, D, JurosComposto, JurosSimples, SelicUnica, SqliteRepository, Verba,
)
from backend.presets import PresetRegistry
from backend.storage import CalculoRepository, Database
from backend.tabelas.sync import INDICES, Sincronizador

JUROS_POR_TIPO = {
    "simples": JurosSimples(),
    "composto": JurosComposto(),
    "selic_unica": SelicUnica(),
}


class CalculadoraService:
    """Fachada de aplicação. Dependências via construtor; sem global, sem I/O direto."""

    def __init__(self, db: Database, presets: PresetRegistry | None = None,
                 sincronizador: Sincronizador | None = None):
        self._db = db
        self._presets = presets or PresetRegistry()
        self._sync = sincronizador or Sincronizador(db.path)
        self._lock = threading.Lock()
        self._st: dict = {
            "rodando": False, "indice": None, "de": "2020-01", "ate": "2026-10",
            "progresso": 0, "erro": None, "erro_indice": None,
            "erro_de": "2020-01", "erro_ate": "2026-10",
        }

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
        try:
            with SqliteRepository(str(self._db.path)) as repo:
                facade = CalculadoraFacade(repo, juros=JUROS_POR_TIPO[preset.tipo_juros])
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

    # ---- atualização de tabelas (wireframe "Atualizar tabelas") ----

    def listar_indices(self) -> list[dict]:
        self._db.init(seed=False)
        return self._sync.listar_indices()

    def sincronizar(self, *, indice: str | None = None, tudo: bool = False,
                    de: str = "2020-01", ate: str = "2026-10") -> dict:
        """Dispara a sincronização em background e devolve na hora (o HTTP responde 202).

        Um sync por vez: o lock recusa chamadas concorrentes, evitando escrita
        simultânea no mesmo SQLite.
        """
        alvos = INDICES if tudo else ([indice] if indice else [])
        if not alvos:
            raise ValueError("informe 'tudo' ou 'indice'")
        if indice is not None and indice not in INDICES:
            raise ValueError(f"indice desconhecido: {indice!r}; use um de {INDICES}")
        with self._lock:
            if self._st["rodando"]:
                raise ValueError("sincronizacao ja em andamento")
            self._st.update(rodando=True, indice=None, de=de, ate=ate,
                            progresso=0, erro=None, erro_indice=None,
                            erro_de=de, erro_ate=ate, concluidos=[])
        alvo = list(alvos)
        t = threading.Thread(target=self._rodar_sync, args=(alvo, de, ate), daemon=True)
        t.start()
        return {"iniciado": True, "alvos": alvos}

    def status_sync(self) -> dict:
        with self._lock:
            st = dict(self._st)
        st["log"] = self._sync.ultimo_log(20)
        st["indices"] = self._sync.listar_indices()
        return st

    def _rodar_sync(self, alvos: list[str], de: str, ate: str) -> None:
        total = len(alvos)
        for i, ind in enumerate(alvos):
            with self._lock:
                self._st["indice"] = ind
                self._st["progresso"] = int(i * 100 / total)
            try:
                self._sync.sync(indice=ind, de=de, ate=ate)
            except Exception as e:  # falha de um índice não derruba os demais
                with self._lock:
                    self._st["erro"] = f"{ind}: {e}"
                    self._st["erro_indice"] = ind
                continue
            finally:
                with self._lock:
                    self._st["progresso"] = int((i + 1) * 100 / total)
        with self._lock:
            self._st["rodando"] = False
            self._st["indice"] = None
