"""Imagem -> volume (m³) por célula de 100 m, com intervalo calibrado, e Monte Carlo por UPA.

API usada pelo motor de regras (pipeline/export/caso.py):
  features_celulas(celulas, stack_path, prob_path)   -> features da imagem por célula
  estimar_celulas(celulas, stack_path, prob_path)    -> + disturbio_frac, frac_valida, vol_p10/p50/p90 (m³/célula)
  classificar_celulas(gdf)                           -> + classe
  monte_carlo_upa(gdf, n, seed)                      -> faixas da UPA e dos subconjuntos
  volume_corte_raso(area_ha_faixa, estoque, agb, n)  -> ASV/UAS

Modelos: data/processed/volume/lgbm_q{10,50,90}.txt + conformal.json (pipeline.volume.calibrar).
Sem modelo treinado, usa uma calibração-prior explícita (CALIB_PRIOR) e registra isso em `modelo_info()`.
Todos os volumes de célula são m³ na célula (já multiplicados pela área da célula em ha).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize

ROOT = Path(__file__).resolve().parents[2]
VOL_DIR = ROOT / "data" / "processed" / "volume"
ML_DIR = ROOT / "data" / "processed" / "ml"

FEATS = ["disturbio_frac", "prob_mean", "dndvi_mean", "dndvi_p10", "dndvi_std", "dnbr_mean", "dndmi_mean"]
FRAC_VALIDA_MIN = 0.7
LIMIAR_NAO_DECLARADO = 0.15
VOL_MIN_SEM_LASTRO = 5.0

# Prior usado apenas se não houver modelo calibrado (m³/ha por fração de distúrbio).
CALIB_PRIOR = {"m3_ha_por_frac": 120.0, "p10_fator": 0.3, "p90_fator": 2.5, "p90_aditivo_m3_ha": 5.0}


def patch_s2_utm():
    """Polígonos a oeste de -66° (Porto Velho/Lábrea) fazem s2.utm_crs falhar; usa a mesma convenção de
    pipeline.ingest.common.utm (31980 a oeste de -60°, 31981 a leste) sem alterar o módulo de imagem."""
    import pipeline.imagery.s2 as s2
    if getattr(s2.utm_crs, "_lastro_patch", False):
        return
    orig = s2.utm_crs

    def utm_crs(aoi):
        try:
            return orig(aoi)
        except ValueError:
            return "EPSG:31980" if aoi.centroid.x < -60 else "EPSG:31981"
    utm_crs._lastro_patch = True
    s2.utm_crs = utm_crs


def limiar_detector() -> float:
    try:
        return float(json.loads((ML_DIR / "threshold.json").read_text())["threshold"])
    except Exception:
        return 0.5


# ---------------------------------------------------------------- máscara de floresta
NDVI_FLORESTA_MIN = 0.7


def prob_floresta(stack_path, prob_path, out_path, prodes_gdf=None, ano_pre: int | None = None,
                  ndvi_min: float = NDVI_FLORESTA_MIN) -> dict:
    """Zera a probabilidade de distúrbio em pixels que NÃO eram floresta no pré:
    NDVI pré < ndvi_min, ou dentro de PRODES com ano <= ano_pre (desmatamento já mapeado até a janela pré).
    Pixels sem dado permanecem nodata. Grava out_path (GeoTIFF float32) e retorna estatísticas."""
    from rasterio.features import geometry_mask
    with rasterio.open(stack_path) as src:
        red, nir = src.read(3).astype("float32"), src.read(4).astype("float32")
        nod = src.nodata
        crs, tr, shape = src.crs, src.transform, (src.height, src.width)
    with rasterio.open(prob_path) as src:
        prob = src.read(1).astype("float32")
        prof = src.profile.copy()
        pnod = src.nodata
    valid = (prob != pnod) & np.isfinite(prob) & (red != nod) & (nir != nod)
    ndvi = np.where(valid, (nir - red) / np.maximum(nir + red, 1e-6), np.nan)
    floresta = valid & (ndvi >= ndvi_min)
    n_prodes = 0
    if prodes_gdf is not None and len(prodes_gdf) and ano_pre is not None:
        pr = prodes_gdf[prodes_gdf["ano"] <= ano_pre]
        if len(pr):
            geoms = [g for g in pr.to_crs(crs).geometry if g is not None and not g.is_empty]
            if geoms:
                desm = geometry_mask(geoms, out_shape=shape, transform=tr, invert=True)
                n_prodes = int((floresta & desm).sum())
                floresta &= ~desm
    out = np.where(valid, np.where(floresta, prob, 0.0), pnod).astype("float32")
    prof.update(count=1, dtype="float32", nodata=pnod, compress="deflate")
    with rasterio.open(out_path, "w", **prof) as dst:
        dst.write(out, 1)
    nv = max(int(valid.sum()), 1)
    return {"frac_floresta_pre": float(floresta.sum() / nv), "frac_nao_floresta_ndvi": float((valid & (ndvi < ndvi_min)).sum() / nv),
            "px_excluidos_prodes": n_prodes, "ndvi_min": ndvi_min, "ano_pre": ano_pre}


# ---------------------------------------------------------------- features
def features_celulas(celulas_gdf: gpd.GeoDataFrame, stack_path, prob_path, limiar: float | None = None) -> gpd.GeoDataFrame:
    """Agrega por célula: disturbio_frac (prob >= limiar), prob média, dNDVI média/p10/desvio, dNBR, dNDMI, frac_valida."""
    limiar = limiar_detector() if limiar is None else limiar
    out = celulas_gdf.copy()
    n = len(out)
    with rasterio.open(stack_path) as src:
        crs, tr, shape = src.crs, src.transform, (src.height, src.width)
        d = src.read([13, 14, 15]).astype("float32")
        vmask = src.read(16)
        nod = src.nodata
    with rasterio.open(prob_path) as src:
        prob = src.read(1).astype("float32")
        pnod = src.nodata
    valid = (vmask > 0) & np.all(np.isfinite(d), axis=0) & np.all(d != nod, axis=0) & np.isfinite(prob) & (prob != pnod)
    cel = out.to_crs(crs)
    ids = np.zeros(shape, dtype="int32")
    if n:
        ids = rasterize(((g, i + 1) for i, g in enumerate(cel.geometry) if g is not None and not g.is_empty),
                        out_shape=shape, transform=tr, fill=0, dtype="int32")
    tot = np.bincount(ids.ravel(), minlength=n + 1)[1:]
    sel = (ids > 0) & valid
    idv = ids[sel] - 1
    nv = np.bincount(idv, minlength=n).astype(float)

    def mean(arr):
        s = np.bincount(idv, weights=arr[sel].astype("float64"), minlength=n)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(nv > 0, s / np.maximum(nv, 1), np.nan)

    dndvi = d[0]
    out["frac_valida"] = np.where(tot > 0, nv / np.maximum(tot, 1), 0.0)
    out["n_px"] = tot
    out["disturbio_frac"] = mean((prob >= limiar).astype("float32"))
    out["prob_mean"] = mean(prob)
    out["dndvi_mean"] = mean(dndvi)
    sq = mean(dndvi.astype("float64") ** 2)
    out["dndvi_std"] = np.sqrt(np.clip(sq - out["dndvi_mean"].to_numpy() ** 2, 0, None))
    out["dnbr_mean"] = mean(d[1])
    out["dndmi_mean"] = mean(d[2])
    p10 = np.full(n, np.nan)
    if idv.size:
        s = pd.Series(dndvi[sel]).groupby(idv).quantile(0.1)
        p10[s.index.to_numpy()] = s.to_numpy()
    out["dndvi_p10"] = p10
    return out


# ---------------------------------------------------------------- modelo
@lru_cache(maxsize=1)
def _modelos():
    import lightgbm as lgb
    paths = {q: VOL_DIR / f"lgbm_q{q}.txt" for q in (10, 50, 90)}
    if not all(p.exists() for p in paths.values()):
        return None
    conf_path = VOL_DIR / "conformal.json"
    conf = json.loads(conf_path.read_text(encoding="utf-8")) if conf_path.exists() else {}
    return {q: lgb.Booster(model_file=str(p)) for q, p in paths.items()}, conf


def modelo_info() -> dict:
    m = _modelos()
    if m is None:
        return {"calibracao": "prior-linear-v0 (sem modelo calibrado)", "conformal_q_m3_ha": 0.0,
                "sigma_upa": 0.35, "prior": CALIB_PRIOR, "cobertura_celula": None, "r2": None}
    conf = m[1]
    return {"calibracao": conf.get("versao", "lgbm-quantil-v1"), "conformal_q_m3_ha": conf.get("q_m3_ha", 0.0),
            "sigma_upa": conf.get("sigma_upa", 0.35), "cobertura_celula": conf.get("cobertura_celula_conformal"),
            "sigma_bloco": conf.get("sigma_bloco", 0.3), "cobertura_bloco": conf.get("cobertura_bloco"),
            "a_frac_excesso_min": conf.get("a_frac_excesso_min", 0.10), "a_fpr": conf.get("a_fpr"),
            "a_frac_vol_sl_min": conf.get("a_frac_vol_sl_min", 0.30),
            "cobertura_upa": conf.get("cobertura_upa_mc"), "r2": conf.get("r2"), "n_upas": conf.get("n_upas"),
            "features": conf.get("features", FEATS)}


def prever_m3_ha(X: pd.DataFrame) -> np.ndarray:
    """Retorna array (n,3) de quantis p10,p50,p90 em m³/ha, monotônicos e >= 0, com ajuste conformal."""
    m = _modelos()
    n = len(X)
    if n == 0:
        return np.zeros((0, 3))
    if m is None:
        f = X["disturbio_frac"].fillna(0).to_numpy()
        p50 = CALIB_PRIOR["m3_ha_por_frac"] * f
        q = np.column_stack([p50 * CALIB_PRIOR["p10_fator"], p50, p50 * CALIB_PRIOR["p90_fator"] + CALIB_PRIOR["p90_aditivo_m3_ha"] * (f > 0)])
    else:
        boosters, conf = m
        feats = conf.get("features", FEATS)
        Xa = X[feats].astype(float).to_numpy()
        q = np.column_stack([boosters[k].predict(Xa) for k in (10, 50, 90)])
        qc = float(conf.get("q_m3_ha", 0.0))
        q[:, 0] -= qc
        q[:, 2] += qc
    q = np.sort(np.clip(q, 0, None), axis=1)
    return q


def estimar_celulas(celulas_gdf, stack_path, prob_path) -> gpd.GeoDataFrame:
    """Adiciona disturbio_frac, frac_valida, vol_p10, vol_p50, vol_p90 (m³/célula). Nulos onde não observável."""
    out = features_celulas(celulas_gdf, stack_path, prob_path)
    if "area_ha" not in out:
        out["area_ha"] = out.to_crs(_utm_epsg(out)).area / 10000
    obs = (out["frac_valida"] >= FRAC_VALIDA_MIN) & out["disturbio_frac"].notna()
    for c in ("vol_p10", "vol_p50", "vol_p90"):
        out[c] = np.nan
    if obs.any():
        q = prever_m3_ha(out.loc[obs, FEATS]) * out.loc[obs, "area_ha"].to_numpy()[:, None]
        out.loc[obs, "vol_p10"], out.loc[obs, "vol_p50"], out.loc[obs, "vol_p90"] = q[:, 0], q[:, 1], q[:, 2]
    return out


def _utm_epsg(gdf):
    x = gdf.to_crs(4326).geometry.union_all().centroid.x
    return 31980 if x < -60 else 31981


# ---------------------------------------------------------------- classes
def classificar_celulas(gdf, limiar: float = LIMIAR_NAO_DECLARADO) -> gpd.GeoDataFrame:
    """classe ∈ {consistente, sem_lastro, nao_declarado, sem_atividade, nao_observavel}."""
    out = gdf.copy()
    fv = out.get("frac_valida", pd.Series(np.nan, index=out.index)).astype(float)
    dist = out["disturbio_frac"].astype(float)
    vd = out["vol_declarado"].fillna(0).astype(float)
    na = out["n_arvores"].fillna(0).astype(int)
    p10, p90 = out["vol_p10"].astype(float), out["vol_p90"].astype(float)
    nao_obs = ~(fv >= FRAC_VALIDA_MIN) | dist.isna() | p90.isna()
    classe = np.where(na > 0, "consistente", "sem_atividade").astype(object)
    nd = (na == 0) & (dist >= limiar) & (p10 > 0)
    classe[nd.to_numpy()] = "nao_declarado"
    sl = (vd > p90) & (vd >= VOL_MIN_SEM_LASTRO)
    classe[sl.to_numpy()] = "sem_lastro"
    classe[nao_obs.to_numpy()] = "nao_observavel"
    out["classe"] = classe
    return out


# ---------------------------------------------------------------- Monte Carlo
def amostrar_quantis(p10, p50, p90, u):
    """Inversa da CDF linear por partes passando por (0,1;p10), (0,5;p50), (0,9;p90).
    Caudas: extrapolação linear com a inclinação do segmento adjacente; truncada em 0."""
    p10, p50, p90 = (np.asarray(a, dtype=float) for a in (p10, p50, p90))
    lo = p50 + (u - 0.5) * (p50 - p10) / 0.4
    hi = p50 + (u - 0.5) * (p90 - p50) / 0.4
    return np.clip(np.where(u < 0.5, lo, hi), 0, None)


def monte_carlo_upa(gdf, n: int = 10000, seed: int = 0, sigma_upa: float | None = None, chunk: int = 500) -> dict:
    """Soma o volume das células observáveis dentro da UPA amostrando de cada célula a CDF ajustada aos quantis,
    com um fator comum de escala por UPA ~ lognormal(0, sigma_upa) (correlação espacial simplificada).
    Retorna {upa, sem_lastro_excesso, nao_declarado, nao_declarado_fora} cada um com p10/p50/p90 (m³)."""
    rng = np.random.default_rng(seed)
    sigma = modelo_info()["sigma_upa"] if sigma_upa is None else sigma_upa
    g = gdf[gdf["vol_p50"].notna()]
    dentro = g["dentro_upa"].astype(bool).to_numpy() if "dentro_upa" in g else np.ones(len(g), bool)
    classe = g["classe"].to_numpy() if "classe" in g else np.array(["consistente"] * len(g))
    q = g[["vol_p10", "vol_p50", "vol_p90"]].to_numpy(float)
    vd = g["vol_declarado"].fillna(0).to_numpy(float) if "vol_declarado" in g else np.zeros(len(g))
    m_upa = dentro
    m_sl = dentro & (classe == "sem_lastro")
    m_nd = dentro & (classe == "nao_declarado")
    m_ndf = (~dentro) & (classe == "nao_declarado")
    res = {k: [] for k in ("upa", "sem_lastro_excesso", "nao_declarado", "nao_declarado_fora")}
    done = 0
    while done < n:
        k = min(chunk, n - done)
        fator = np.exp(rng.normal(0, sigma, size=(k, 1))) if sigma > 0 else np.ones((k, 1))
        u = rng.random((k, len(g)))
        s = amostrar_quantis(q[:, 0], q[:, 1], q[:, 2], u) * fator
        res["upa"].append(s[:, m_upa].sum(1))
        res["sem_lastro_excesso"].append((vd[m_sl] - s[:, m_sl]).sum(1))
        res["nao_declarado"].append(s[:, m_nd].sum(1))
        res["nao_declarado_fora"].append(s[:, m_ndf].sum(1))
        done += k
    out = {}
    for key, arrs in res.items():
        a = np.concatenate(arrs)
        p = np.percentile(a, [10, 50, 90])
        out[key] = {"p10": float(p[0]), "p50": float(p[1]), "p90": float(p[2])}
    out["n"] = n
    out["seed"] = seed
    out["sigma_upa"] = sigma
    out["n_celulas"] = int(m_upa.sum())
    out["declarado_upa_m3"] = float(vd[m_upa].sum())
    out["prob_declarado_acima_estimado"] = float(np.mean(np.concatenate(res["upa"]) < vd[m_upa].sum())) if len(g) else None
    return out


# ---------------------------------------------------------------- blocos 3x3
BLOCO_K = 3


def bloco_ids(ids, k: int = BLOCO_K) -> np.ndarray:
    """'{crs}_{ix}_{iy}[_f]' -> '{ix//k}_{iy//k}' (bloco de k×k células de 100 m = k² ha)."""
    out = []
    for i in ids:
        parts = str(i).split("_")
        if parts[-1] == "f":
            parts = parts[:-1]
        out.append(f"{int(parts[-2]) // k}_{int(parts[-1]) // k}")
    return np.array(out)


def mc_blocos(q: np.ndarray, blocos: np.ndarray, sigma_bloco: float, n: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Quantis (p10,p50,p90) da soma por bloco. q: (ncel,3) m³ por célula; fator comum por bloco ~ lognormal(0, sigma_bloco)."""
    rng = np.random.default_rng(seed)
    if len(q) == 0:
        return pd.DataFrame(columns=["bloco", "p10", "p50", "p90"])
    uniq, inv = np.unique(blocos, return_inverse=True)
    order = np.argsort(inv, kind="stable")
    starts = np.r_[0, np.flatnonzero(np.diff(inv[order])) + 1]
    qs = q[order]
    res = []
    for c0 in range(0, n, 500):
        k = min(500, n - c0)
        s = amostrar_quantis(qs[:, 0], qs[:, 1], qs[:, 2], rng.random((k, len(qs))))
        b = np.add.reduceat(s, starts, axis=1)
        if sigma_bloco > 0:
            b = b * np.exp(rng.normal(0, sigma_bloco, size=b.shape))
        res.append(b)
    p = np.percentile(np.concatenate(res), [10, 50, 90], axis=0)
    return pd.DataFrame({"bloco": uniq, "p10": p[0], "p50": p[1], "p90": p[2]})


def avaliar_blocos(gdf, sigma_bloco: float | None = None, k: int = BLOCO_K, vol_min: float = 20.0, seed: int = 0) -> pd.DataFrame:
    """Agrega células observáveis dentro da UPA em blocos k×k; classifica bloco sem_lastro se Σ declarado > p90 do bloco e ≥ vol_min m³."""
    sigma_bloco = modelo_info().get("sigma_bloco", 0.3) if sigma_bloco is None else sigma_bloco
    g = gdf[gdf["vol_p50"].notna()]
    if "dentro_upa" in g:
        g = g[g["dentro_upa"].astype(bool)]
    if not len(g):
        return pd.DataFrame(columns=["bloco", "p10", "p50", "p90", "vol_declarado", "n_celulas", "n_arvores", "sem_lastro", "excesso"])
    bl = bloco_ids(g["id"], k)
    r = mc_blocos(g[["vol_p10", "vol_p50", "vol_p90"]].to_numpy(float), bl, sigma_bloco, seed=seed)
    agg = pd.DataFrame({"bloco": bl, "vd": g["vol_declarado"].fillna(0).to_numpy(float), "na": g["n_arvores"].fillna(0).to_numpy(int)}).groupby("bloco").agg(
        vol_declarado=("vd", "sum"), n_celulas=("vd", "size"), n_arvores=("na", "sum")).reset_index()
    r = r.merge(agg, on="bloco")
    r["sem_lastro"] = (r["vol_declarado"] > r["p90"]) & (r["vol_declarado"] >= vol_min)
    r["excesso"] = np.where(r["sem_lastro"], r["vol_declarado"] - r["p90"], 0.0)
    return r


# ---------------------------------------------------------------- corte raso
def volume_corte_raso(area_ha_faixa, estoque_m3_ha: float | None, agb_mg_ha: float | None, n: int = 10000, seed: int = 0) -> dict:
    """ASV/UAS: V = A × V_ha. area_ha_faixa: número ou (p10,p50,p90)/dict. V_ha ~ Normal(estoque, 15%) se houver;
    senão AGB (GEDI) -> V_ha = AGB/(WD×BEF)×f_com. Retorna p10/p50/p90 (m³) + parametros (ParametroVolume)."""
    rng = np.random.default_rng(seed)
    if isinstance(area_ha_faixa, dict):
        a = (area_ha_faixa.get("p10"), area_ha_faixa.get("p50"), area_ha_faixa.get("p90"))
    elif isinstance(area_ha_faixa, (tuple, list)):
        a = tuple(area_ha_faixa)
    else:
        a = (area_ha_faixa,) * 3
    if a[1] is None or not np.isfinite(a[1]):
        return {"p10": None, "p50": None, "p90": None, "parametros": [], "metodo": None}
    area = amostrar_quantis(a[0], a[1], a[2], rng.random(n)) if a[0] != a[2] else np.full(n, float(a[1]))
    params = [{"nome": "Área desmatada", "distribuicao": "fixa" if a[0] == a[2] else "CDF linear por partes (p10,p50,p90)",
               "valor": float(a[1]), "unidade": "ha", "origem": "detector LightGBM sobre Sentinel-2"}]
    if estoque_m3_ha is not None and np.isfinite(estoque_m3_ha) and estoque_m3_ha > 0:
        vha = np.clip(rng.normal(estoque_m3_ha, 0.15 * estoque_m3_ha, n), 0, None)
        params.append({"nome": "Estoque comercial por ha", "distribuicao": f"normal({estoque_m3_ha:.1f}, {0.15*estoque_m3_ha:.1f})",
                       "valor": float(estoque_m3_ha), "unidade": "m³/ha", "origem": "volume autorizado / área autorizada (AUTEX)"})
        metodo = "estoque_declarado"
    elif agb_mg_ha is not None and np.isfinite(agb_mg_ha) and agb_mg_ha > 0:
        wd = np.clip(rng.normal(0.62, 0.05, n), 0.3, None)
        bef = np.clip(rng.normal(1.6, 0.15, n), 1.0, None)
        fcom = rng.uniform(0.3, 0.5, n)
        vha = agb_mg_ha / (wd * bef) * fcom
        params += [
            {"nome": "AGB pré-evento", "distribuicao": "fixo", "valor": float(agb_mg_ha), "unidade": "Mg/ha", "origem": "GEDI L4A"},
            {"nome": "Densidade da madeira (WD)", "distribuicao": "normal(0.62, 0.05)", "valor": 0.62, "unidade": "g/cm³", "origem": "literatura (média Amazônia)"},
            {"nome": "Fator de expansão de biomassa (BEF)", "distribuicao": "normal(1.6, 0.15)", "valor": 1.6, "unidade": None, "origem": "literatura"},
            {"nome": "Fração comercial", "distribuicao": "uniforme(0.3, 0.5)", "valor": 0.4, "unidade": None, "origem": "literatura"},
        ]
        metodo = "agb_gedi"
    else:
        return {"p10": None, "p50": None, "p90": None, "parametros": params, "metodo": None}
    v = area * vha
    p = np.percentile(v, [10, 50, 90])
    return {"p10": float(p[0]), "p50": float(p[1]), "p90": float(p[2]), "parametros": params, "metodo": metodo}
