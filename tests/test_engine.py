"""Testes do domínio — só API de classes, sem funções compat."""
from datetime import date
from decimal import Decimal

from backend.engine import (
    Calculadora, CalculadoraFacade, FatorSimples, JurosComposto, JurosSimples,
    MemoriaRepository, Pagamento, SelicAcumulada, Verba, round2,
)
from backend.presets import PresetRegistry


def test_correcao_basica():
    assert FatorSimples().corrigir(Decimal("1000"), Decimal("100.0"), Decimal("145.3")) == Decimal("1453.00")


def test_verba_com_juros():
    repo = MemoriaRepository({("X", "2023-06"): 120.50, ("X", "2026-10"): 145.30})
    calc = Calculadora(repo)
    r = calc.calcular_verba(
        Verba("v", Decimal("20000"), date(2023, 6, 15), "X",
              Decimal("0.01"), date(2023, 6, 15), date(2026, 10, 7)),
        date(2026, 10, 7))
    assert r.corrigido > 20000
    assert r.total == r.corrigido + r.juros


def test_total_com_honorarios():
    repo = MemoriaRepository({("X", "2020-01"): 1.0, ("X", "2020-02"): 1.0})
    facade = CalculadoraFacade(repo)
    r = facade.calcular_processo(
        [Verba("a", Decimal("10000"), date(2020, 1, 1), "X", Decimal("0"),
               date(2020, 1, 1), date(2020, 2, 1)),
         Verba("b", Decimal("5000"), date(2020, 1, 1), "X", Decimal("0"),
               date(2020, 1, 1), date(2020, 2, 1))],
        date(2020, 2, 1), honorarios_perc=Decimal("0.10"))
    assert r["honorarios"] == Decimal("1500.00")
    assert r["total"] == Decimal("16500.00")


def test_strategy_juros_composto_maior_que_simples():
    s, c = JurosSimples(), JurosComposto()
    ini, fim = date(2020, 1, 1), date(2026, 1, 1)
    assert c.calcular(Decimal("10000"), Decimal("0.01"), ini, fim) > s.calcular(Decimal("10000"), Decimal("0.01"), ini, fim)


def test_selic_fase2():
    assert SelicAcumulada().aplicar(Decimal("10000"), Decimal("0.10")) == Decimal("11000.00")


def test_fase_ec113_duas_fases():
    repo = MemoriaRepository({("IPCA-E", "2020-01"): 100.0, ("IPCA-E", "2021-12"): 120.0})
    calc = Calculadora(repo)
    r = calc.calcular_fase_ec113(
        Verba("Dano", Decimal("10000"), date(2020, 1, 10), "IPCA-E",
              Decimal("0.01"), date(2020, 1, 10)), Decimal("0.10"))
    assert r.total == round2(round2(r.corrigido + r.juros) * Decimal("1.10"))


def test_facade_com_repo():
    repo = MemoriaRepository({("IPCA-E", "2020-01"): 100.0, ("IPCA-E", "2026-10"): 145.3})
    calc = Calculadora(repo)
    r = calc.calcular_verba(Verba("Dano", Decimal("8450"), date(2020, 1, 10), "IPCA-E"), date(2026, 10, 7))
    assert r.total > r.corrigido


def test_pagamento_abate_base():
    repo = MemoriaRepository({("X", "2020-01"): 1.0, ("X", "2020-02"): 1.0})
    facade = CalculadoraFacade(repo)
    r = facade.calcular_processo(
        [Verba("a", Decimal("10000"), date(2020, 1, 1), "X", Decimal("0"),
               date(2020, 1, 1), date(2020, 2, 1))],
        date(2020, 2, 1), pagamentos=[Pagamento(date(2020, 2, 1), Decimal("2000"))])
    assert r["base"] == Decimal("8000.00")


def test_presets_validos():
    reg = PresetRegistry()
    assert "TJSP_CIVEL" in reg.listar()
    assert "TJMA_CIVEL" in reg.listar()
    assert reg.obter("FAZENDA_EC113").tipo_juros == "selic_unica"
