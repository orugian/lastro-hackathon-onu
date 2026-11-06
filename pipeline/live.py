"""Análise ao vivo de uma autorização (chamada por POST /api/analyze/{autex}).

Reaproveita o pipeline de exportação (pipeline.export.caso.processar_caso). Escopo leve:
regras documentais + S2/GEE + detector LightGBM + volume; sem CBERS.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "data" / "artifacts"

ProgressCb = Optional[Callable[[str, float], None]]


def analisar(autex: str, progress_cb: ProgressCb = None) -> dict:
    def p(etapa: str, frac: float) -> None:
        if progress_cb:
            try:
                progress_cb(etapa, frac)
            except Exception:
                pass

    p("Carregando autorização e árvores declaradas", 0.05)
    from pipeline.export import caso as caso_mod  # import tardio

    kwargs = {}
    try:
        import inspect
        sig = inspect.signature(caso_mod.processar_caso)
        if "cbers" in sig.parameters:
            kwargs["cbers"] = False
        if "progress_cb" in sig.parameters:
            kwargs["progress_cb"] = p
    except Exception:
        pass

    p("Baixando Sentinel-2 e detectando distúrbio", 0.2)
    dossier = caso_mod.processar_caso(autex, **kwargs)
    p("Atualizando índice", 0.95)
    data = dossier.model_dump() if hasattr(dossier, "model_dump") else dict(dossier)
    _upsert_index(data)
    p("Concluído", 1.0)
    return {"autex": autex, "score": data.get("score"), "flags": data.get("flags", [])}


def _upsert_index(d: dict) -> None:
    idx_path = ART / "index.json"
    if not idx_path.exists():
        return
    from contracts.models import CaseSummary, Index

    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    summary = CaseSummary.model_validate({k: d[k] for k in CaseSummary.model_fields if k in d}).model_dump()
    casos = [c for c in idx["casos"] if c["autex"] != summary["autex"]] + [summary]
    casos.sort(key=lambda c: -c["score"])
    idx["casos"] = casos
    Index.model_validate(idx)
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
