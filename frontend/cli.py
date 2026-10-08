"""CLI interativo — depende só da porta (protocolo) + IO injetável. Sem input() direto."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.ports import AppPort
from reports.memoria_pdf import MemoriaBuilder


class ConsoleIO:
    """Borda de IO real. FakeIO nos testes herda daqui."""

    def ask(self, prompt: str, default: str = "") -> str:
        s = input(f"{prompt}" + (f" [{default}]" if default else "") + ": ").strip()
        return s or default

    def show(self, msg: str = "") -> None:
        print(msg)

    def ask_date(self, prompt: str, default: str) -> date:
        while True:
            try:
                return date.fromisoformat(self.ask(prompt, default))
            except ValueError:
                self.show("Use AAAA-MM-DD.")


class WizardCLI:
    """Orquestra as 5 etapas. Porta e IO via construtor; testável sem stdin."""

    def __init__(self, port: AppPort, io: ConsoleIO | None = None):
        self._port = port
        self._io = io or ConsoleIO()

    def run_interativo(self) -> int:
        presets = self._port.get_presets()
        self._io.show(f"Presets: {', '.join(sorted(presets))}")
        processo = self._io.ask("Nº processo", "0001234-56.2020.8.26.0100")
        preset_cod = self._io.ask("Preset", "TJSP_CIVEL")
        p = presets.get(preset_cod, {})
        self._io.show(f"\nPreset: {p.get('descricao', preset_cod)} | índice {p.get('indice')} | juros {p.get('taxa_am')}/mês")
        data_fim = self._io.ask_date("Data final", date.today().isoformat())

        verbas: list[dict] = []
        while True:
            nome = self._io.ask("Verba nome (ENTER termina)", "" if verbas else "Dano moral")
            if not nome and verbas:
                break
            if not nome:
                self._io.show("Informe ao menos 1 verba.")
                continue
            vb = self._io.ask("  valor base", "20000")
            db0 = self._io.ask_date("  data base", "2023-06-15")
            ji = self._io.ask_date("  juros desde", db0.isoformat())
            verbas.append({"nome": nome, "valor_base": float(vb),
                           "data_base": db0.isoformat(), "juros_ini": ji.isoformat()})

        dto = {"processo": processo, "preset": preset_cod, "data_fim": data_fim.isoformat(),
               "verbas": verbas, "honorarios_perc": float(self._io.ask("Honorários % (ex 10)", "10")),
               "custas": float(self._io.ask("Custas", "0")), "multa": float(self._io.ask("Multa", "0"))}
        try:
            r = self._port.calcular(dto)
        except (KeyError, ValueError) as e:
            self._io.show(f"\nERRO: {e}\nDica: rode 'python main.py sync --tudo' ou confira competência na tabela.")
            return 1

        self._io.show(f"\nTotal: R$ {r['total']} (base {r['base']} + honor {r['honorarios']})")
        for v in r["verbas"]:
            self._io.show(f" - {v['nome']}: {v['corrigido']} + {v['juros']} = {v['total']}")
        self._io.show(f"Salvo cálculo id={r['id']}")

        b = MemoriaBuilder(processo)
        for v, vin in zip(r["verbas"], verbas):
            b.add_verba(v["nome"], Decimal(str(vin["valor_base"])), vin["data_base"],
                        Decimal(str(v["corrigido"])), Decimal(str(v["juros"])), Decimal(str(v["total"])))
        out = b.to_html({k: Decimal(str(r[k])) for k in ("base", "honorarios", "custas", "multa", "total")},
                        str(Path(f"memoria_{r['id']}.html")))
        self._io.show(f"Memória: {out}")
        return 0

    def run_listar(self) -> None:
        for row in self._port.listar():
            self._io.show(str(row))


if __name__ == "__main__":
    from backend.service import CalculadoraService
    from backend.storage import Database

    raise SystemExit(WizardCLI(CalculadoraService(Database())).run_interativo())
