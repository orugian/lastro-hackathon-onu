"""Score de prioridade de fiscalização: 1 − exp(−Σ peso × severidade × confiança) sobre flags com status 'indicio'."""
from __future__ import annotations

import math

PESOS = {"A": 1.0, "B": 1.0, "D": 0.8, "F2": 0.9, "C": 0.6, "E": 0.6, "F6": 1.0}
SEVERIDADE = {"alta": 1.0, "media": 0.6, "baixa": 0.3, "info": 0.0}


def score(flags) -> float:
    x = 0.0
    for f in flags:
        g = f if isinstance(f, dict) else f.model_dump()
        if g["status"] != "indicio":
            continue
        x += PESOS.get(g["codigo"], 0.5) * SEVERIDADE.get(g["severidade"], 0.0) * float(g["confianca"])
    return round(1 - math.exp(-x), 4)


def parametros_score() -> list[dict]:
    return [{"nome": f"Peso da flag {k}", "distribuicao": "fixo", "valor": v, "unidade": None,
             "origem": "pipeline/rules/score.py · score = 1 − exp(−Σ peso × severidade × confiança); severidade alta=1, média=0,6, baixa=0,3"}
            for k, v in PESOS.items()]
