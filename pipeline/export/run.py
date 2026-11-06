"""Exporta casos com imagem (top N da pré-triagem) + todas as demais autorizações como só-documentais + index.json.

  uv run python -m pipeline.export.run --top 3
  uv run python -m pipeline.export.run --top 30 --top-asv 10 --cbers-top 5
  uv run python -m pipeline.export.run --so-docs             # só documentais + index (reaproveita casos com imagem existentes)
  uv run python -m pipeline.export.run --autex 20112202446622
"""
from __future__ import annotations

import argparse
import json
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from contracts.models import CaseSummary, Dossier, Index
from pipeline.export.caso import caso_documental, processar_caso
from pipeline.export.dados import ART, POLO, agora, dados

LOG = logging.getLogger("lastro.export")


def _carregar_existente(autex: str):
    p = ART / "cases" / autex / "dossier.json"
    if p.exists():
        try:
            d = Dossier.model_validate_json(p.read_text(encoding="utf-8"))
            return d
        except Exception:
            return None
    return None


def construir_index(dossies: dict[str, Dossier]) -> Index:
    D = dados()
    casos = []
    for autex in D.aut.index:
        d = dossies.get(autex) or _carregar_existente(autex)
        if d is None or (not d.analise_imagem and autex not in dossies):
            d = caso_documental(autex)
        casos.append(d)
    # casos simulados existentes
    for p in (ART / "cases").glob("SIM-*/dossier.json"):
        casos.append(Dossier.model_validate_json(p.read_text(encoding="utf-8")))
    sums = [CaseSummary.model_validate({k: getattr(d, k) for k in CaseSummary.model_fields}) for d in casos]
    sums.sort(key=lambda c: (-c.score, c.autex))
    reais = [c for c in sums if c.source_mode == "real"]
    sl = 0.0
    for d in casos:
        if d.source_mode != "real":
            continue
        for f in d.flags_detalhe:
            if f.codigo == "A" and f.status == "indicio" and f.volume_m3 and f.volume_m3.p50:
                sl += max(f.volume_m3.p50, 0)
    totais = {
        "autorizacoes_avaliadas": len(reais),
        "com_imagem": sum(c.analise_imagem for c in reais),
        "com_indicio": sum(any(f.status == "indicio" for f in c.flags) for c in reais),
        "por_tipo": {t: sum(c.tipo == t for c in reais) for t in ("POA", "ASV", "UAS")},
        "por_flag_indicio": {k: sum(any(f.codigo == k and f.status == "indicio" for f in c.flags) for c in reais) for k in ("A", "B", "C", "D", "E", "F2", "F6")},
        "arvores_if100": D.n_arvores_total,
        "volume_declarado_total_m3": round(D.vol_total, 1),
        "volume_sem_lastro_p50_m3": round(sl, 1),
        "simulados": sum(c.source_mode == "simulado" for c in sums),
    }
    idx = Index(gerado_em=agora(), polo=POLO, totais=totais, casos=sums)
    Index.model_validate(idx.model_dump())
    (ART / "index.json").write_text(json.dumps(idx.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
    return idx


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=3, help="N casos POA da pré-triagem com imagem")
    ap.add_argument("--top-asv", type=int, default=0, help="N casos ASV/UAS com imagem")
    ap.add_argument("--cbers-top", type=int, default=0, help="recorta CBERS nos K casos de maior score (2ª passada)")
    ap.add_argument("--so-docs", action="store_true")
    ap.add_argument("--autex", nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    D = dados()
    alvo = []
    if a.autex:
        alvo = list(a.autex)
    elif not a.so_docs:
        alvo = list(D.pre[D.pre.tipo == "POA"].autex.head(a.top)) + list(D.pre[D.pre.tipo != "POA"].autex.head(a.top_asv))
    feitos, falhas = {}, []
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futs = {pool.submit(processar_caso, x): x for x in alvo}
        for f in as_completed(futs):
            x = futs[f]
            try:
                d = f.result()
                feitos[x] = d
                LOG.info("caso %s score=%.3f flags=%s", x, d.score, [(g.codigo, g.status) for g in d.flags])
            except Exception as exc:
                falhas.append({"autex": x, "erro": repr(exc)[:400]})
                LOG.error("falha %s: %s\n%s", x, exc, traceback.format_exc())
    if a.cbers_top and feitos:
        top = sorted(feitos.values(), key=lambda d: -d.score)[: a.cbers_top]
        for d in top:
            try:
                feitos[d.autex] = processar_caso(d.autex, cbers=True)
                LOG.info("CBERS %s ok", d.autex)
            except Exception as exc:
                LOG.error("CBERS %s falhou: %s", d.autex, exc)
    idx = construir_index(feitos)
    print(json.dumps({"processados": list(feitos), "falhas": falhas, "totais": idx.totais}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
