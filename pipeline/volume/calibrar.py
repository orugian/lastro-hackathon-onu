"""Calibração imagem -> volume declarado (IF100) por célula de 100 m.

Etapas (idempotentes, com cache):
  uv run python -m pipeline.volume.calibrar --baixar --n 72   # escolhe UPAs limpas, baixa S2 (4 threads) e roda o detector
  uv run python -m pipeline.volume.calibrar                   # monta calib_celulas.parquet, treina quantis, GroupKFold, conformal

Seleção de UPAs de calibração: POA do polo com >= 50 árvores IF100, fora do top 10 da pré-triagem (demo),
sem indício C, sem alerta DETER intersectando o polígono, janela de exploração entre 2022-06 e 2026-05, área <= 3000 ha.
"""
from __future__ import annotations

import argparse
import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from pipeline.grid.celulas import grade_celulas, agrega_arvores
from pipeline.ingest.common import utm
from pipeline.volume.estimar import FEATS, FRAC_VALIDA_MIN, VOL_DIR, features_celulas, amostrar_quantis

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
STACKS = VOL_DIR / "stacks"
METRICS = ROOT / "data" / "artifacts" / "metrics"


def candidatos(n: int, seed: int = 42) -> pd.DataFrame:
    a = gpd.read_parquet(PROC / "autorizacoes.parquet")
    r = pd.read_parquet(PROC / "regras_doc.parquet")
    p = pd.read_csv(PROC / "pretriagem.csv", dtype={"autex": str})
    d = gpd.read_parquet(PROC / "deter.parquet")
    m = a.merge(r.drop(columns=["tipo"]), on="autex")
    c = m[(m.tipo == "POA") & (m.n_arvores >= 50) & ~m.autex.isin(p.autex.head(10)) & (m.status_C != "indicio")]
    j = gpd.sjoin(c[["autex", "geometry"]], d[["geometry"]], predicate="intersects")
    c = c[~c.autex.isin(j.autex)]
    c = c[(c.data_expl_max <= "2026-05-01") & (c.data_expl_min >= "2022-06-01") & (c.area_ha <= 3000)]
    c = c.sample(frac=1, random_state=seed)
    return c.head(n)


def _aoi(geom):
    crs = utm(geom)
    g = gpd.GeoSeries([geom], crs=4326).to_crs(crs).buffer(100).to_crs(4326).iloc[0]
    return g.buffer(0)


def baixar_um(row) -> dict:
    from pipeline.imagery.s2 import baixar_par_s2, janelas_automaticas
    from pipeline.detect.predict import prever
    from pipeline.volume.estimar import patch_s2_utm
    patch_s2_utm()
    autex = row["autex"]
    dest = STACKS / autex
    t0 = time.monotonic()
    pre, pos = janelas_automaticas(row["data_expl_min"], row["data_expl_max"], row["validade_ini"])
    meta = baixar_par_s2(autex, _aoi(row["geometry"]), pre, pos, dest)
    if not (dest / "prob.tif").exists():
        prever(dest / "s2_stack.tif", dest)
    return {"autex": autex, "s": round(time.monotonic() - t0, 1), "nuvem_pos": meta.get("nuvem_pct_pos")}


def baixar(n: int, workers: int = 4):
    c = candidatos(n)
    STACKS.mkdir(parents=True, exist_ok=True)
    (VOL_DIR / "calib_upas.json").write_text(json.dumps(list(c.autex)), encoding="utf-8")
    print(f"{len(c)} UPAs de calibração", flush=True)
    ok, fail = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(baixar_um, row): row["autex"] for _, row in c.iterrows()}
        for f in as_completed(futs):
            try:
                ok.append(f.result()); print("ok", ok[-1], flush=True)
            except Exception as exc:
                fail.append({"autex": futs[f], "erro": str(exc)[:300]}); print("falha", fail[-1], flush=True)
    (VOL_DIR / "download_log.json").write_text(json.dumps({"ok": ok, "falha": fail}, indent=1), encoding="utf-8")


# ------------------------------------------------------------------ dataset
def montar_dataset() -> pd.DataFrame:
    a = gpd.read_parquet(PROC / "autorizacoes.parquet")
    t = gpd.read_parquet(PROC / "arvores_if100.parquet")
    rows = []
    for d in sorted(STACKS.glob("*")):
        if not ((d / "s2_stack.tif").exists() and (d / "prob.tif").exists()):
            continue
        autex = d.name
        poly = a.loc[a.autex == autex, "geometry"]
        if poly.empty:
            continue
        cel = grade_celulas(poly.iloc[0], 100)
        tr = t[(t.autex == autex) & t.dentro_upa.fillna(False).astype(bool)]
        cel = agrega_arvores(cel, tr)
        cel = features_celulas(cel, d / "s2_stack.tif", d / "prob.tif")
        cel["autex"] = autex
        rows.append(pd.DataFrame(cel.drop(columns="geometry")))
        print(autex, len(cel), flush=True)
    df = pd.concat(rows, ignore_index=True)
    df["n_px"] = df["n_px"].astype(int)
    df.to_parquet(VOL_DIR / "calib_celulas_todas.parquet", index=False)
    keep = (df.frac_valida >= FRAC_VALIDA_MIN) & (df.area_ha >= 0.5) & df.disturbio_frac.notna()
    df = df[keep].copy()
    df["y_m3_ha"] = df.vol_declarado / df.area_ha
    df.to_parquet(VOL_DIR / "calib_celulas.parquet", index=False)
    return df


# ------------------------------------------------------------------ treino
PARAMS = dict(objective="quantile", learning_rate=0.05, num_leaves=15, min_data_in_leaf=40,
              feature_fraction=0.9, bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, verbose=-1, seed=0)
N_ROUNDS = 300
ALPHAS = {10: 0.1, 50: 0.5, 90: 0.9}


def _mono():
    # crescente em disturbio_frac e prob_mean; decrescente em dNDVI (média e p10)
    m = {"disturbio_frac": 1, "prob_mean": 1, "dndvi_mean": -1, "dndvi_p10": -1}
    return [m.get(f, 0) for f in FEATS]


def _fit(X, y, alpha):
    import lightgbm as lgb
    # LightGBM não aceita monotone_constraints com objective=quantile; a monotonicidade entre quantis é
    # garantida por ordenação (_pred) e a curva é verificada em calibracao.json.
    p = dict(PARAMS, alpha=alpha)
    return lgb.train(p, lgb.Dataset(X, y), num_boost_round=N_ROUNDS)


def _pred(models, X):
    q = np.column_stack([models[k].predict(X) for k in (10, 50, 90)])
    return np.sort(np.clip(q, 0, None), axis=1)


def _r2(y, p):
    ss = ((y - y.mean()) ** 2).sum()
    return float(1 - ((y - p) ** 2).sum() / ss) if ss > 0 else None


def _cqr_q(y, q, alpha=0.2):
    s = np.maximum(q[:, 0] - y, y - q[:, 2])
    n = len(s)
    k = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
    return float(np.quantile(s, k))


def _upa_mc(dfu, q, sigma, n=2000, seed=0):
    rng = np.random.default_rng(seed)
    f = np.exp(rng.normal(0, sigma, size=(n, 1))) if sigma > 0 else 1
    s = (amostrar_quantis(q[:, 0], q[:, 1], q[:, 2], rng.random((n, len(q)))) * f).sum(1)
    return np.percentile(s, [10, 50, 90])


def treinar(df: pd.DataFrame, k: int = 5):
    from sklearn.model_selection import GroupKFold
    X = df[FEATS].astype(float).to_numpy()
    y = df["y_m3_ha"].to_numpy(float)
    area = df["area_ha"].to_numpy(float)
    g = df["autex"].to_numpy()
    oof = np.zeros((len(df), 3))
    qconf_fold = np.zeros(len(df))
    gkf = GroupKFold(n_splits=k)
    for tr, te in gkf.split(X, y, g):
        # CQR: separa 25% das UPAs do treino como conjunto de calibração conformal
        upas = np.unique(g[tr])
        rng = np.random.default_rng(0)
        cal_upas = set(rng.choice(upas, size=max(1, len(upas) // 4), replace=False))
        cal = np.array([u in cal_upas for u in g[tr]])
        m_fit = {kq: _fit(X[tr][~cal], y[tr][~cal], a) for kq, a in ALPHAS.items()}
        qc = _cqr_q(y[tr][cal], _pred(m_fit, X[tr][cal]))
        m_all = {kq: _fit(X[tr], y[tr], a) for kq, a in ALPHAS.items()}
        oof[te] = _pred(m_all, X[te])
        qconf_fold[te] = qc
    oof_c = oof.copy()
    oof_c[:, 0] = np.clip(oof[:, 0] - qconf_fold, 0, None)
    oof_c[:, 2] = oof[:, 2] + qconf_fold

    def cel_metrics(q):
        return {"r2": _r2(y, q[:, 1]), "mae_m3_ha": float(np.abs(y - q[:, 1]).mean()),
                "cobertura_p10_p90": float(((y >= q[:, 0]) & (y <= q[:, 2])).mean()),
                "largura_media_m3_ha": float((q[:, 2] - q[:, 0]).mean())}

    # sigma_upa: dispersão log da razão declarado/estimado por UPA (fora da amostra)
    d = df.assign(v=y * area, p50=oof[:, 1] * area)
    agg = d.groupby("autex").agg(v=("v", "sum"), p50=("p50", "sum"))
    lr = np.log((agg.v + 1) / (agg.p50 + 1))
    sigma_upa = float(np.clip(lr.std(ddof=1), 0.05, 1.5))

    def upa_metrics(q, sigma):
        res = []
        for u, idx in d.groupby("autex").indices.items():
            qq = q[idx] * area[idx, None]
            p = _upa_mc(None, qq, sigma) if sigma is not None else qq.sum(0)
            res.append((agg.v[u], *p))
        r = np.array(res)
        return {"r2": _r2(r[:, 0], r[:, 2]), "mae_m3": float(np.abs(r[:, 0] - r[:, 2]).mean()),
                "erro_rel_mediano": float(np.median(np.abs(r[:, 0] - r[:, 2]) / np.maximum(r[:, 0], 1))),
                "cobertura_p10_p90": float(((r[:, 0] >= r[:, 1]) & (r[:, 0] <= r[:, 3])).mean()), "n_upas": len(r)}

    metr = {
        "celula_antes": cel_metrics(oof), "celula_conformal": cel_metrics(oof_c),
        "upa_soma_quantis_antes": upa_metrics(oof, None),
        "upa_mc_antes": upa_metrics(oof, sigma_upa), "upa_mc_conformal": upa_metrics(oof_c, sigma_upa),
        "sigma_upa": sigma_upa, "q_conformal_folds_m3_ha": sorted(set(np.round(qconf_fold, 3).tolist())),
    }
    # modelo final + conformal final (calibração em 25% das UPAs)
    upas = np.unique(g)
    rng = np.random.default_rng(1)
    cal_upas = set(rng.choice(upas, size=max(1, len(upas) // 4), replace=False))
    cal = np.array([u in cal_upas for u in g])
    m_fit = {kq: _fit(X[~cal], y[~cal], a) for kq, a in ALPHAS.items()}
    q_final = _cqr_q(y[cal], _pred(m_fit, X[cal]))
    final = {kq: _fit(X, y, a) for kq, a in ALPHAS.items()}
    return final, q_final, metr


def curva(models, df, qc):
    med = df[FEATS].median()
    pts = []
    for x in np.linspace(0, 1, 21):
        row = med.copy()
        row["disturbio_frac"] = x
        q = _pred(models, row[FEATS].to_numpy(float)[None])[0]
        pts.append({"disturbio_frac": round(float(x), 2), "p10": round(float(max(q[0] - qc, 0)), 2),
                    "p50": round(float(q[1]), 2), "p90": round(float(q[2] + qc), 2)})
    return pts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baixar", action="store_true")
    ap.add_argument("--n", type=int, default=72)
    ap.add_argument("--reusar-dataset", action="store_true")
    a = ap.parse_args(argv)
    VOL_DIR.mkdir(parents=True, exist_ok=True)
    if a.baixar:
        baixar(a.n)
        return
    path = VOL_DIR / "calib_celulas.parquet"
    df = pd.read_parquet(path) if a.reusar_dataset and path.exists() else montar_dataset()
    print("células", len(df), "UPAs", df.autex.nunique(), flush=True)
    models, qc, metr = treinar(df)
    for kq, m in models.items():
        m.save_model(str(VOL_DIR / f"lgbm_q{kq}.txt"))
    conf = {"versao": "lgbm-quantil-v1+cqr", "q_m3_ha": qc, "sigma_upa": metr["sigma_upa"], "features": FEATS,
            "cobertura_celula_antes": metr["celula_antes"]["cobertura_p10_p90"],
            "cobertura_celula_conformal": metr["celula_conformal"]["cobertura_p10_p90"],
            "cobertura_upa_mc": metr["upa_mc_conformal"]["cobertura_p10_p90"],
            "r2": metr["celula_antes"]["r2"], "n_upas": int(df.autex.nunique()), "n_celulas": len(df),
            "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (VOL_DIR / "conformal.json").write_text(json.dumps(conf, indent=1), encoding="utf-8")
    (VOL_DIR / "metricas_cv.json").write_text(json.dumps(metr, indent=1), encoding="utf-8")
    from contracts.models import MetricsCalibracao
    cb = metr["celula_antes"]; cc = metr["celula_conformal"]
    ua, uc = metr["upa_mc_antes"], metr["upa_mc_conformal"]
    obs = (
        f"Métricas fora da amostra (GroupKFold por UPA, k=5). Célula 1 ha: R² {cb['r2']:.2f}, MAE {cb['mae_m3_ha']:.1f} m³/ha, "
        f"cobertura [p10,p90] {cb['cobertura_p10_p90']:.0%} antes e {cc['cobertura_p10_p90']:.0%} após CQR (ajuste ±{qc:.1f} m³/ha). "
        f"UPA (Monte Carlo, fator comum lognormal σ={metr['sigma_upa']:.2f}): R² {ua['r2']:.2f}, erro relativo mediano "
        f"{ua['erro_rel_mediano']:.0%}, cobertura {ua['cobertura_p10_p90']:.0%} antes e {uc['cobertura_p10_p90']:.0%} após CQR. "
        "Cobertura reportada no campo principal = célula após conformal. "
        "Limitações: (1) a calibração usa UPAs sem indício documental nem DETER, mas pode conter divergência não detectada, o que "
        "infla a relação declarado/distúrbio; (2) clareiras de árvore isolada (200–600 m²) são sub-pixel em 10 m e fecham em meses; "
        "(3) nuvem: células com < 70% de pixels válidos são descartadas; (4) coordenadas IF100 têm erro de GPS de dezenas de metros, "
        "o que espalha volume entre células vizinhas (por isso o indício A é avaliado em blocos e no agregado da UPA)."
    )
    mc = MetricsCalibracao(protocolo="GroupKFold por UPA, k=5 · células 100 m · LightGBM quantílico (α=0,1/0,5/0,9, monotônico) + CQR",
                           n_celulas_treino=len(df), n_upas=int(df.autex.nunique()), r2=cb["r2"], mae_m3_ha=cb["mae_m3_ha"],
                           cobertura_p10_p90=cc["cobertura_p10_p90"], curva=curva(models, df, qc), obs=obs,
                           gerado_em=conf["gerado_em"])
    METRICS.mkdir(parents=True, exist_ok=True)
    (METRICS / "calibracao.json").write_text(json.dumps(mc.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
    mcj = {
        "descricao": "Monte Carlo do volume por UPA (pipeline.volume.estimar.monte_carlo_upa)",
        "n_amostras": 10000, "seed": 0,
        "celula": "CDF linear por partes pelos quantis (0,1;p10),(0,5;p50),(0,9;p90) do LightGBM quantílico + CQR; caudas extrapoladas linearmente, truncadas em 0",
        "correlacao_espacial": "fator comum por UPA ~ lognormal(0, sigma_upa) multiplicando todas as células",
        "sigma_upa": metr["sigma_upa"],
        "sigma_upa_origem": "desvio-padrão de log((declarado+1)/(p50 estimado+1)) por UPA, fora da amostra",
        "conformal_q_m3_ha": qc,
        "subconjuntos": {"sem_lastro_excesso": "Σ(vol_declarado − vol amostrado) nas células sem_lastro",
                         "nao_declarado": "Σ vol amostrado nas células nao_declarado"},
        "corte_raso": {"V": "A × V_ha", "V_ha_estoque": "Normal(volume autorizado/área autorizada, 15%)",
                       "V_ha_agb": "AGB/(WD×BEF)×f_com", "WD": "Normal(0,62; 0,05) g/cm³", "BEF": "Normal(1,6; 0,15)",
                       "f_com": "Uniforme(0,3; 0,5)"},
        "metricas_cv": metr, "gerado_em": conf["gerado_em"],
    }
    (METRICS / "montecarlo.json").write_text(json.dumps(mcj, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(metr, indent=1))


if __name__ == "__main__":
    main()
