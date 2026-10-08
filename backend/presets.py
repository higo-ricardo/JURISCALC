"""Presets por tribunal — Factory + dataclass frozen com validação."""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

PRESETS_JSON = Path(__file__).with_name("presets.json")

INDICES_SUPORTADOS = ["IPCA-E", "IPCA", "INPC", "IGP-M", "SELIC", "TR", "TABELA_TJSP", "TABELA_CJF"]


@dataclass(frozen=True)
class Preset:
    codigo: str
    descricao: str
    indice: str
    taxa_am: Decimal
    tipo_juros: str  # simples | composto | selic_unica
    termo_inicial_padrao: str  # citacao | evento_danoso | arbitramento
    corte_ec113: str | None = None
    observacao: str = ""

    def validar(self) -> list[str]:
        erros = []
        if self.indice not in INDICES_SUPORTADOS:
            erros.append(f"indice {self.indice} inválido")
        if self.tipo_juros not in ("simples", "composto", "selic_unica"):
            erros.append(f"tipo_juros {self.tipo_juros} inválido")
        if not (Decimal("0") <= self.taxa_am <= Decimal("0.2")):
            erros.append("taxa_am fora de 0-20% a.m.")
        return erros


_DEFAULTS = {
    "TJSP_CIVEL": Preset("TJSP_CIVEL", "TJSP Cível padrão", "IPCA-E", Decimal("0.01"),
                         "simples", "citacao", None,
                         "Súm.54 juros desde evento danoso; Súm.362 correção dano moral desde arbitramento"),
    "TJRJ_CIVEL": Preset("TJRJ_CIVEL", "TJRJ Cível padrão", "IPCA-E", Decimal("0.01"),
                         "simples", "citacao", None, "Mesma regra STJ Súm.43/54/362"),
    "JF_MANUAL_CJF": Preset("JF_MANUAL_CJF", "JF Manual CJF", "IPCA-E", Decimal("0.005"),
                            "simples", "citacao", None, "Previdenciário usa INPC"),
    "FAZENDA_EC113": Preset("FAZENDA_EC113", "Fazenda pós EC113", "SELIC", Decimal("0"),
                            "selic_unica", "citacao", "2021-12-09",
                            "Até 08/12/2021 IPCA-E+juros; após só SELIC"),
    "TJMA_CIVEL": Preset("TJMA_CIVEL", "TJMA Cível padrão (CGJ-MA)", "INPC", Decimal("0.01"),
                         "simples", "citacao", None,
                         "Tabela TJMA/CGJ-MA (INPC) + 1% a.m.; Súm.43/54/362"),
}

class PresetRegistry:
    """Factory: centraliza criação por tribunal, permite override via presets.json."""

    def __init__(self):
        self._reg = dict(_DEFAULTS)
        if PRESETS_JSON.exists():
            try:
                data = json.loads(PRESETS_JSON.read_text(encoding="utf-8"))
                for codigo, d in data.items():
                    self._reg[codigo] = Preset(
                        codigo, d["descricao"], d["indice"], Decimal(str(d["taxa_am"])),
                        d["tipo_juros"], d.get("termo_inicial_padrao", "citacao"),
                        d.get("corte_ec113"), d.get("observacao", ""),
                    )
            except Exception as e:
                raise ValueError(f"presets.json inválido: {e}")

    def listar(self) -> list[str]:
        return sorted(self._reg)

    def obter(self, codigo: str) -> Preset:
        try:
            p = self._reg[codigo]
        except KeyError:
            raise KeyError(f"Preset {codigo} não existe. Opções: {self.listar()}")
        if (erros := p.validar()):
            raise ValueError(f"Preset {codigo} inválido: {erros}")
        return p
