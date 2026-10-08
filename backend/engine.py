"""Motor de cálculo judicial — design aprovado em docs/DESIGN.md.

Strategy (correção/juros) + Repository (índices) + Facade (processo).
Puro, sem I/O. Usa Decimal. Arredonda só no final (2 casas).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, getcontext

getcontext().prec = 28

EC113_CUTOFF = date(2021, 12, 9)


def D(x) -> Decimal:
    return Decimal(str(x))


def round2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------- Value Objects ----------
@dataclass(frozen=True)
class Verba:
    nome: str
    valor_base: Decimal
    data_base: date
    indice_nome: str
    taxa_am: Decimal = D("0.01")
    juros_ini: date | None = None
    juros_fim: date | None = None

    def __post_init__(self):
        if self.valor_base < 0:
            raise ValueError("valor_base negativo")


@dataclass(frozen=True)
class Pagamento:
    data: date
    valor_atualizado: Decimal


@dataclass
class ResultadoVerba:
    verba: str
    corrigido: Decimal
    juros: Decimal
    total: Decimal
    memoria: list[str] = field(default_factory=list)


# ---------- Strategies ----------
class CorrecaoStrategy(ABC):
    @abstractmethod
    def fator(self, ind_ini: Decimal, ind_fim: Decimal) -> Decimal: ...

    def corrigir(self, valor_base: Decimal, ind_ini: Decimal, ind_fim: Decimal) -> Decimal:
        return round2(D(valor_base) * self.fator(D(ind_ini), D(ind_fim)))


class FatorSimples(CorrecaoStrategy):
    def fator(self, ind_ini: Decimal, ind_fim: Decimal) -> Decimal:
        if ind_ini <= 0:
            raise ValueError("indice_inicial deve ser > 0")
        return D(ind_fim) / D(ind_ini)


class SelicAcumulada(CorrecaoStrategy):
    """Fase 2 EC113: aplica SELIC acumulada sobre total da fase 1."""

    def fator(self, ind_ini: Decimal, ind_fim: Decimal) -> Decimal:
        return D(ind_fim)  # aqui ind_fim = 1 + selic_acumulada

    def aplicar(self, total_fase1: Decimal, selic_acumulada: Decimal) -> Decimal:
        return round2(D(total_fase1) * (Decimal("1") + D(selic_acumulada)))


class JurosStrategy(ABC):
    @abstractmethod
    def calcular(self, valor_corrigido: Decimal, taxa_am: Decimal, ini: date, fim: date) -> Decimal: ...


def meses_pro_rata(inicio: date, fim: date) -> Decimal:
    if fim < inicio:
        raise ValueError("termo final anterior ao inicial")
    dias = (fim - inicio).days
    return D(dias) / D(30)


class JurosSimples(JurosStrategy):
    def calcular(self, valor_corrigido: Decimal, taxa_am: Decimal, ini: date, fim: date) -> Decimal:
        if taxa_am == 0:
            return D("0.00")
        return round2(D(valor_corrigido) * D(taxa_am) * meses_pro_rata(ini, fim))


class JurosComposto(JurosStrategy):
    def calcular(self, valor_corrigido: Decimal, taxa_am: Decimal, ini: date, fim: date) -> Decimal:
        n = meses_pro_rata(ini, fim)
        return round2(D(valor_corrigido) * ((Decimal("1") + D(taxa_am)) ** n - Decimal("1")))


class SelicUnica(JurosStrategy):
    def calcular(self, valor_corrigido: Decimal, taxa_am: Decimal, ini: date, fim: date) -> Decimal:
        return D("0.00")  # juros já embutidos na SELIC


# ---------- Repository ----------
class IndiceRepository(ABC):
    @abstractmethod
    def buscar(self, indice: str, competencia: str) -> Decimal: ...


class MemoriaRepository(IndiceRepository):
    def __init__(self, tabela: dict[tuple[str, str], float | Decimal]):
        self._t = {(k[0], k[1]): D(v) for k, v in tabela.items()}

    def buscar(self, indice: str, competencia: str) -> Decimal:
        try:
            return self._t[(indice, competencia)]
        except KeyError:
            raise KeyError(f"Índice {indice} {competencia} não encontrado")


class SqliteRepository(IndiceRepository):
    def __init__(self, db_path: str):
        self.db_path = db_path

    def buscar(self, indice: str, competencia: str) -> Decimal:
        import sqlite3

        con = sqlite3.connect(self.db_path)
        try:
            row = con.execute(
                "SELECT valor FROM indices WHERE indice=? AND competencia=?",
                (indice, competencia),
            ).fetchone()
        finally:
            con.close()
        if not row:
            raise KeyError(f"Índice {indice} {competencia} não encontrado em {self.db_path}")
        return D(row[0])


# ---------- Calculadora ----------
class Calculadora:
    def __init__(self, repo: IndiceRepository,
                 correcao: CorrecaoStrategy | None = None,
                 juros: JurosStrategy | None = None):
        self.repo = repo
        self.correcao = correcao or FatorSimples()
        self.juros = juros or JurosSimples()

    def _comp(self, d: date) -> str:
        return f"{d.year:04d}-{d.month:02d}"

    def calcular_verba(self, verba: Verba, data_fim: date) -> ResultadoVerba:
        ind_ini = self.repo.buscar(verba.indice_nome, self._comp(verba.data_base))
        ind_fim = self.repo.buscar(verba.indice_nome, self._comp(data_fim))
        vc = self.correcao.corrigir(verba.valor_base, ind_ini, ind_fim)
        j_ini = verba.juros_ini or verba.data_base
        j_fim = verba.juros_fim or data_fim
        j = self.juros.calcular(vc, verba.taxa_am, j_ini, j_fim)
        mem = [
            f"{verba.nome}: base R$ {verba.valor_base} em {verba.data_base} [{verba.indice_nome} {ind_ini} -> {ind_fim}]",
            f"V_corr = {verba.valor_base} x ({ind_fim}/{ind_ini}) = R$ {vc}",
            f"Juros {verba.taxa_am * 100}% a.m. {j_ini} -> {j_fim} = R$ {j}",
        ]
        return ResultadoVerba(verba.nome, vc, j, round2(vc + j), mem)

    def calcular_fase_ec113(self, verba: Verba, selic_acumulada_fase2: Decimal,
                            data_corte_comp: str = "2021-12") -> ResultadoVerba:
        """Fase1 até véspera do EC113 com correção+juros, fase2 só SELIC."""
        corte = EC113_CUTOFF - timedelta(days=1)
        ind_ini = self.repo.buscar(verba.indice_nome, self._comp(verba.data_base))
        ind_corte = self.repo.buscar(verba.indice_nome, data_corte_comp)
        vc = self.correcao.corrigir(verba.valor_base, ind_ini, ind_corte)
        j = self.juros.calcular(vc, verba.taxa_am, verba.juros_ini or verba.data_base, corte)
        fase1 = round2(vc + j)
        total = SelicAcumulada().aplicar(fase1, selic_acumulada_fase2)
        return ResultadoVerba(
            verba.nome, vc, j, total,
            [f"Fase1 até {corte}: R$ {fase1} (corr R$ {vc} + juros R$ {j})",
             f"Fase2 SELIC {selic_acumulada_fase2 * 100}%: R$ {fase1} -> R$ {total}"],
        )


class CalculadoraFacade:
    """Fachada: recebe repo + strategies, expõe um método por caso de uso."""

    def __init__(self, repo: IndiceRepository,
                 correcao: CorrecaoStrategy | None = None,
                 juros: JurosStrategy | None = None):
        self.calc = Calculadora(repo, correcao, juros)

    def calcular_processo(self, verbas: list[Verba], data_fim: date,
                          pagamentos: list[Pagamento] | None = None,
                          honorarios_perc: Decimal = D(0),
                          custas: Decimal = D(0), multa: Decimal = D(0)) -> dict:
        pagamentos = pagamentos or []
        resultados = [self.calc.calcular_verba(v, data_fim) for v in verbas]
        base = round2(sum((r.total for r in resultados), D(0)) - sum((p.valor_atualizado for p in pagamentos), D(0)))
        honor = round2(base * D(honorarios_perc))
        total = round2(base + honor + D(custas) + D(multa))
        return {"verbas": resultados, "base": base, "honorarios": honor,
                "custas": round2(D(custas)), "multa": round2(D(multa)), "total": total}
