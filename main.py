"""Entrypoint — único lugar que conhece o concreto. Comandos via dict, DI via construtor."""
import argparse
import sys
from abc import ABC, abstractmethod
from pathlib import Path

from backend.service import CalculadoraService
from backend.storage import DB_DEFAULT, Database
from backend.tabelas.sync import INDICES, Sincronizador, sync_indice
from frontend.app import WebServer
from frontend.cli import WizardCLI


class Context:
    def __init__(self, db: Path):
        self.service = CalculadoraService(Database(db), sincronizador=Sincronizador(db))


class Command(ABC):
    @abstractmethod
    def run(self, ctx: Context, args: argparse.Namespace) -> int: ...


class InitCommand(Command):
    def run(self, ctx: Context, args: argparse.Namespace) -> int:
        Database(Path(args.db)).init()
        print(f"OK db={args.db}")
        return 0


class WizardCommand(Command):
    def run(self, ctx: Context, args: argparse.Namespace) -> int:
        return WizardCLI(ctx.service).run_interativo()


class ExemploCommand(Command):
    def run(self, ctx: Context, args: argparse.Namespace) -> int:
        r = ctx.service.calcular({"processo": "exemplo", "preset": "TJSP_CIVEL", "data_fim": "2026-10-07",
                                  "verbas": [{"nome": "Dano moral", "valor_base": 20000,
                                              "data_base": "2023-06-15", "juros_ini": "2023-06-15"}],
                                  "honorarios_perc": 10})
        print(f"Total R$ {r['total']} salvo id={r['id']}")
        return 0


class ListarCommand(Command):
    def run(self, ctx: Context, args: argparse.Namespace) -> int:
        WizardCLI(ctx.service).run_listar()
        return 0


class SyncCommand(Command):
    def run(self, ctx: Context, args: argparse.Namespace) -> int:
        if not args.tudo and not args.indice:
            print(f"use --tudo ou --indice ({', '.join(INDICES)})", file=sys.stderr)
            return 2
        Database(Path(args.db)).init(seed=False)
        alvos = INDICES if args.tudo else [args.indice]
        for ind in alvos:
            print(ind, sync_indice(Path(args.db), ind, args.de, args.ate), "OK")
        return 0


class ServeCommand(Command):
    def run(self, ctx: Context, args: argparse.Namespace) -> int:
        WebServer(ctx.service, args.port).run()
        return 0


COMMANDS: dict[str, Command] = {
    "init": InitCommand(),
    "wizard": WizardCommand(),
    "exemplo": ExemploCommand(),
    "listar": ListarCommand(),
    "sync": SyncCommand(),
    "serve": ServeCommand(),
}


def main() -> int:
    ap = argparse.ArgumentParser(prog="calculadora")
    ap.add_argument("--db", default=str(DB_DEFAULT))
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in COMMANDS:
        p = sub.add_parser(name)
        if name == "sync":
            p.add_argument("--tudo", action="store_true")
            p.add_argument("--indice", default=None)
            p.add_argument("--de", default="2020-01")
            p.add_argument("--ate", default="2026-10")
        if name == "serve":
            p.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    return COMMANDS[a.cmd].run(Context(Path(a.db)), a)


if __name__ == "__main__":
    raise SystemExit(main())
