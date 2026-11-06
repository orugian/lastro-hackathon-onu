"""Janelas Sentinel-2 sazonalmente comparáveis (sempre estação seca: 01/jun a 05/out, 127 dias).

A janela tem > 120 dias de propósito: pipeline.imagery.s2.baixar_par_s2 só estende a janela pós para 180 dias
(entrando na estação chuvosa) quando ela tem ≤ 120 dias. Assim pré e pós ficam sempre na mesma estação.

POA: pré = estação seca anterior à primeira exploração; pós = estação seca logo após a última exploração
(a do mesmo ano, se a exploração terminou até julho). ASV/UAS: pré = estação seca anterior ao início da
validade; pós = estação seca do fim da validade (ou a mais recente disponível).
Se a pós cair no futuro, usa a estação seca mais recente disponível e devolve uma limitação.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

INI, FIM = "06-01", "10-05"


def _w(y: int) -> tuple[str, str]:
    return (f"{y}-{INI}", f"{y}-{FIM}")


def ultima_estacao(hoje: Optional[date] = None) -> int:
    hoje = hoje or date.today()
    return hoje.year if hoje >= date(hoje.year, 10, 5) else hoje.year - 1


def janelas_sazonais(tipo: str, data_min: Optional[str], data_max: Optional[str], val_ini: Optional[str],
                     val_fim: Optional[str], hoje: Optional[date] = None) -> tuple[tuple[str, str], tuple[str, str], list[str]]:
    lim = []
    ult = ultima_estacao(hoje)
    if tipo == "POA" and (data_min or val_ini):
        s = date.fromisoformat((data_min or val_ini)[:10])
        e = date.fromisoformat((data_max or data_min or val_ini)[:10])
    else:
        s = date.fromisoformat(val_ini[:10])
        e = date.fromisoformat((val_fim or val_ini)[:10])
    y_pre = s.year if s >= date(s.year, 10, 5) else s.year - 1
    y_pos = e.year if e.month <= 7 else e.year + 1
    if y_pos > ult:
        lim.append(f"A estação seca posterior ao período de interesse ({y_pos}) ainda não está disponível; usada a mais recente ({ult}).")
        y_pos = ult
    if y_pos <= y_pre:
        lim.append(f"Janelas pré e pós na mesma estação ({y_pre}): comparação temporal limitada.")
        y_pos = max(y_pos, min(y_pre + 1, ult))
    if tipo == "POA" and data_min and data_max:
        if e.month in (6, 7, 8, 9) and y_pos == e.year:
            lim.append("A janela pós sobrepõe o fim da exploração declarada; parte da mudança pode não estar visível.")
        if s.month in (6, 7, 8, 9) and y_pre == s.year:
            lim.append("A janela pré sobrepõe o início da exploração declarada.")
    return _w(y_pre), _w(y_pos), lim
