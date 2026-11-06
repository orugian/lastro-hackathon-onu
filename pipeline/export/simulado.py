"""Cenário SIMULAÇÃO: copia um caso POA real processado e injeta, sobre a mesma geografia e imagem,
  (1) "árvores fantasma": registros IF100 sintéticos num bloco de células observáveis SEM distúrbio;
  (2) 3 árvores fora da UPA (200–600 m do limite).
Reavalia A e C com o mesmo motor de regras e grava cases/SIM-{autex} com source_mode="simulado".

  uv run python -m pipeline.export.simulado --autex 20112202586315
"""
from __future__ import annotations

import argparse
import json
import shutil

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from contracts.models import Dossier
from pipeline.export.caso import arvores_fc, escrever_fc
from pipeline.export.dados import ART, IMG, agora, dados, nn
from pipeline.ingest.common import utm
from pipeline.rules import flags as F
from pipeline.rules.score import score
from pipeline.volume.estimar import avaliar_blocos, bloco_ids, classificar_celulas, modelo_info, monte_carlo_upa

AVISO = ("SIMULAÇÃO: cenário sintético para demonstração. Sobre a geografia e a imagem reais da autorização {autex}, foram injetados "
         "{n_f} registros IF100 fictícios ({v_f:.0f} m³) num bloco de {n_c} células sem distúrbio e 3 árvores fictícias fora da UPA. "
         "Não representa declaração real do detentor.")


def escolher_bloco(cel: gpd.GeoDataFrame, n: int = 12) -> list:
    """Bloco compacto de n células dentro da UPA, observáveis, sem distúrbio e sem árvores declaradas."""
    c = cel[cel.dentro_upa & (cel.classe != "nao_observavel") & (cel.disturbio_frac.fillna(1) < 0.02) & (cel.n_arvores == 0) & (cel.area_ha > 0.95)]
    if len(c) < n:
        c = cel[cel.dentro_upa & (cel.classe != "nao_observavel") & (cel.disturbio_frac.fillna(1) < 0.05) & (cel.area_ha > 0.9)]
    xy = np.array([[int(s.split("_")[-2]), int(s.split("_")[-1])] for s in c["id"]])
    best, best_idx = None, None
    for i in range(len(c)):
        d = np.abs(xy - xy[i]).max(1)
        idx = np.argsort(d, kind="stable")[:n]
        r = d[idx].max()
        if best is None or r < best:
            best, best_idx = r, idx
            if r <= 2:
                break
    return list(c.index[best_idx])


def gerar(autex: str, n_celulas: int = 12, arv_por_celula: int = 6, seed: int = 7) -> Dossier:
    rng = np.random.default_rng(seed)
    D = dados()
    src = ART / "cases" / autex
    base = Dossier.model_validate_json((src / "dossier.json").read_text(encoding="utf-8"))
    if base.tipo != "POA" or not base.analise_imagem:
        raise ValueError("Simulação requer um caso POA com imagem processado")
    cel = gpd.read_file(src / "celulas.geojson").to_crs(4326)
    cp = pd.read_parquet(IMG / autex / "celulas.parquet")
    cel = cel.drop(columns=[c for c in cel.columns if c not in ("id", "geometry")]).merge(cp, on="id")
    cel = gpd.GeoDataFrame(cel, geometry="geometry", crs=4326)
    a = D.aut.loc[autex]
    crs = utm(a.geometry)
    upa_u = gpd.GeoSeries([a.geometry], crs=4326).to_crs(crs).iloc[0]

    # 1. árvores fantasma
    idx = escolher_bloco(cel, n_celulas)
    arv_real = D.arvores(autex)
    vols = arv_real["vol_explorado"].dropna().to_numpy()
    esp = arv_real[["especie", "nome_popular"]].dropna().drop_duplicates().to_numpy()
    fant = []
    data_ref = base.validade.inicio or "2025-01-01"
    for i in idx:
        g = gpd.GeoSeries([cel.loc[i, "geometry"]], crs=4326).to_crs(crs).iloc[0]
        minx, miny, maxx, maxy = g.bounds
        k = 0
        while k < arv_por_celula:
            p = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
            if g.contains(p):
                v = float(rng.choice(vols)) if len(vols) else 4.0
                e = esp[rng.integers(len(esp))] if len(esp) else ("Especie sp.", None)
                fant.append(dict(geometry=p, vol_explorado=v, vol_autorizado=v, especie=e[0], nome_popular=e[1], dentro_upa=True, dist_upa_m=0.0))
                k += 1
        cel.loc[i, "vol_declarado"] = cel.loc[i, "vol_declarado"] + sum(f["vol_explorado"] for f in fant[-arv_por_celula:])
        cel.loc[i, "n_arvores"] = cel.loc[i, "n_arvores"] + arv_por_celula
    v_f = sum(f["vol_explorado"] for f in fant)
    # 2. três árvores fora da UPA
    fora = []
    ring = upa_u.buffer(600).difference(upa_u.buffer(200))
    minx, miny, maxx, maxy = ring.bounds
    while len(fora) < 3:
        p = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
        if ring.contains(p):
            v = float(rng.choice(vols)) if len(vols) else 4.0
            fora.append(dict(geometry=p, vol_explorado=v, vol_autorizado=v, especie=esp[0][0] if len(esp) else "Especie sp.",
                             nome_popular=esp[0][1] if len(esp) else None, dentro_upa=False, dist_upa_m=round(float(p.distance(upa_u)), 1)))
    sint = gpd.GeoDataFrame(fant + fora, geometry="geometry", crs=crs).to_crs(4326)
    sint["id"] = [f"SIM-{i+1}" for i in range(len(sint))]
    sint["data_exploracao"] = data_ref

    # reavaliação
    cel = classificar_celulas(cel)
    mc = monte_carlo_upa(cel, n=10000, seed=0)
    blocos = avaliar_blocos(cel)
    bl_sl = set(blocos.loc[blocos.sem_lastro, "bloco"])
    cb = pd.Series(bloco_ids(cel["id"]), index=cel.index)
    cel.loc[(cel.classe == "sem_lastro") & ~cb.isin(bl_sl), "classe"] = "consistente"
    cel.loc[(cel.classe != "nao_observavel") & cel.dentro_upa & cb.isin(bl_sl) & (cel.n_arvores > 0) & (cel.vol_declarado > cel.vol_p50), "classe"] = "sem_lastro"
    info = modelo_info()
    n_arv = (base.n_arvores_declaradas or 0) + len(sint)
    fa = F.flag_A(cel, mc, info.get("cobertura_bloco") or info.get("cobertura_celula"), n_arv, blocos=blocos,
                  frac_min=info.get("a_frac_excesso_min", F.A_FRAC_MIN))
    doc = {k: nn(v) for k, v in D.regras.loc[autex].to_dict().items()}
    doc["n_arvores"] = n_arv
    doc["c_n_fora"] = int(doc.get("c_n_fora") or 0) + 3
    doc["c_volume_fora_m3"] = float(doc.get("c_volume_fora_m3") or 0) + sum(f["vol_explorado"] for f in fora)
    doc["status_C"] = "indicio"
    fc = F.flag_C(doc)
    outras = [f for f in base.flags_detalhe if f.codigo not in ("A", "C")]
    fl = [fa, fc] + outras
    fl.sort(key=lambda f: "ABCDEF".index(f.codigo[0]))

    sid = f"SIM-{autex}"
    dst = ART / "cases" / sid
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    cc = cel.copy()
    for k in ("vol_declarado", "vol_p10", "vol_p50", "vol_p90"):
        cc[k] = cc[k].astype(float).round(2)
    cc.loc[cc.classe == "nao_observavel", "disturbio_frac"] = np.nan
    escrever_fc(dst / "celulas.geojson", cc, ["id", "vol_declarado", "n_arvores", "disturbio_frac", "vol_p10", "vol_p50", "vol_p90", "classe", "dentro_upa", "frac_valida"], None)
    arv_all = pd.concat([arv_real.assign(id=arv_real["id"].astype(str)), sint], ignore_index=True)
    arv_all = gpd.GeoDataFrame(arv_all, geometry="geometry", crs=4326)
    arvores_fc(dst / "arvores.geojson", arv_all, cel[cel.classe == "sem_lastro"])
    aviso = AVISO.format(autex=autex, n_f=len(fant), v_f=v_f, n_c=len(idx))
    d = base.model_copy(deep=True)
    d.autex = sid
    d.source_mode = "simulado"
    d.flags_detalhe = fl
    d.flags = [F.Flag.model_validate(f.model_dump()) for f in fl]
    d.score = score(fl)
    d.n_arvores_declaradas = n_arv
    d.volume_declarado_explorado_m3 = round((base.volume_declarado_explorado_m3 or 0) + float(sint.vol_explorado.sum()), 2)
    d.volume_estimado_m3 = {k: round(v, 1) for k, v in mc["upa"].items()}
    d.limitacoes = [aviso] + list(base.limitacoes)
    d.aviso = "SIMULAÇÃO — " + d.aviso
    d.processado_em = agora()
    d.modelo = dict(base.modelo, simulacao={"base": autex, "arvores_fantasma": len(fant), "volume_fantasma_m3": round(v_f, 1),
                                            "celulas_bloco": len(idx), "arvores_fora": 3, "seed": seed},
                    monte_carlo_upa={k: mc[k] for k in ("upa", "sem_lastro_excesso", "declarado_upa_m3")})
    d = Dossier.model_validate(d.model_dump())
    (dst / "dossier.json").write_text(json.dumps(d.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--autex", required=True)
    ap.add_argument("--celulas", type=int, default=12)
    ap.add_argument("--por-celula", type=int, default=6)
    a = ap.parse_args(argv)
    d = gerar(a.autex, a.celulas, a.por_celula)
    print(d.autex, d.score, [(f.codigo, f.status, f.severidade) for f in d.flags])
    from pipeline.export.run import construir_index
    construir_index({})


if __name__ == "__main__":
    main()
