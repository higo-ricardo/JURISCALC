"""Memória de cálculo — Builder: mesma base gera dict/HTML/CSV."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path


class MemoriaBuilder:
    def __init__(self, processo: str):
        self.processo = processo
        self.linhas: list[dict] = []

    @staticmethod
    def _logo() -> str:
        """Cabeçalho com brasão TJMA (base64, funciona offline/impresso)."""
        import base64

        for cand in (Path(__file__).resolve().parents[1] / "TJMA.jpg",
                     Path("TJMA.jpg"), Path("C:/Users/HIGO/Desktop/CALCULADORA/TJMA.jpg")):
            if cand.exists():
                b64 = base64.b64encode(cand.read_bytes()).decode()
                return (f"<div style='text-align:center;margin-bottom:10px'>"
                        f"<img src='data:image/jpeg;base64,{b64}' style='max-height:90px'>"
                        f"<div style='font-size:12px;color:#555'>Tribunal de Justiça do Estado do Maranhão</div></div>")
        return ""

    def add_verba(self, nome: str, base: Decimal, data_base: str,
                  corrigido: Decimal, juros: Decimal, total: Decimal,
                  detalhe: str = "") -> "MemoriaBuilder":
        self.linhas.append({"nome": nome, "base": base, "data_base": data_base,
                            "corrigido": corrigido, "juros": juros,
                            "total": total, "detalhe": detalhe})
        return self

    def to_html(self, total: dict, destino: str = "memoria.html") -> str:
        trs = "".join(
            f"<tr><td>{v['nome']}</td><td>R$ {v['base']:.2f}</td><td>{v['data_base']}</td>"
            f"<td>R$ {v['corrigido']:.2f}</td><td>R$ {v['juros']:.2f}</td>"
            f"<td><b>R$ {v['total']:.2f}</b></td></tr>"
            for v in self.linhas
        )
        html = (f"<html><head><meta charset='utf-8'><title>Memória - {self.processo}</title>"
                "<style>body{font-family:Arial}table{border-collapse:collapse;width:100%}"
                "td,th{border:1px solid #999;padding:6px}</style></head><body>"
                f"{self._logo()}"
                f"<h2>Memória - {self.processo}</h2>"
                "<p>V_corr = V0 x (índice final / índice inicial) | Juros simples pro-rata die</p>"
                "<table><tr><th>Verba</th><th>Base</th><th>Data</th><th>Corrigido</th>"
                f"<th>Juros</th><th>Total</th></tr>{trs}"
                f"<tr><td colspan='5'>Subtotal condenação</td><td><b>R$ {total['base']:.2f}</b></td></tr>"
                f"<tr><td colspan='5'>Honorários</td><td>R$ {total['honorarios']:.2f}</td></tr>"
                f"<tr><td colspan='5'>Custas</td><td>R$ {total.get('custas', 0):.2f}</td></tr>"
                f"<tr><td colspan='5'>Multa</td><td>R$ {total.get('multa', 0):.2f}</td></tr></table>"
                f"<h3>Total geral R$ {total['total']:.2f}</h3></body></html>")
        Path(destino).write_text(html, encoding="utf-8")
        return destino
