"""Avaliação justa U-Net × LightGBM × baseline no protocolo LOCAL (blocos de 5 km, parede a parede).

Para cada bloco de 5 km do dataset local que a U-Net NÃO viu em treino/validação (split_manifest do Colab):
  - baixa o stack S2 (mesma composição jun–set do detector local) via GEE, 500×500 px a 10 m;
  - rasteriza rótulos INPE em cache (PRODES do ano + DETER corte raso/seletivo/degradação) e
    negativos estáveis (NDVI pré > 0,75 e fora de qualquer DETER/PRODES 2008+), como no dataset local;
  - U-Net: inferência ONNX; LightGBM: modelo do fold em que o bloco foi TESTE (GroupKFold idêntico ao
    train.py, sem vazamento); baseline: ΔNDVI/ΔNBR + Otsu do tile + abertura 3×3.
Métricas em todos os pixels rotulados (parede a parede) e numa amostra balanceada 1000/500/500 por bloco
(mesmo desenho do dataset local).
Uso: uv run python -m pipeline.detect.avaliar_dl
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import ee
import lightgbm as lgb
import numpy as np
import pandas as pd
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy.ndimage import binary_opening
from shapely.geometry import shape
from shapely.ops import transform as stransform
from skimage.filters import threshold_otsu
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

from contracts.models import MetricsDetector
from .common import BANDS, FEATURES, features
from .dataset import exclude_demo_rows, stack as stack_local
from .dl import LIMIAR, prob_unet
from .train import best_threshold, metrics, model

ROOT = Path(__file__).resolve().parents[2]
ML, DL = ROOT / "data/processed/ml", ROOT / "data/processed/dl"
CACHE = DL / "eval_tiles"
N, RES = 500, 10


def blocos_vistos_pela_unet() -> set[str]:
    m = pd.DataFrame(json.loads((DL / "split_manifest.json").read_text(encoding="utf-8")))
    m = m[m.split.isin(["train", "val"])]
    t = Transformer.from_crs(31981, 31980, always_xy=True)
    out = set()
    for r in m.itertuples():
        for dx in (0, 2240):
            for dy in (0, -2240):
                x, y = r.x + dx, r.y + dy
                if r.epsg != 31980:
                    x, y = t.transform(x, y)
                out.add(f"{int(x // 5000)}_{int(y // 5000)}")
    return out


def baixar(bloco: str, ano: int):
    f = CACHE / f"{bloco}_{ano}.npz"
    if f.exists():
        z = np.load(f)
        return z["a"], z["valid"]
    ix, iy = map(int, bloco.split("_"))
    inv = Transformer.from_crs(31980, 4326, always_xy=True)
    b = (*inv.transform(ix * 5000 - 200, iy * 5000 - 200), *inv.transform((ix + 1) * 5000 + 200, (iy + 1) * 5000 + 200))
    img = stack_local(ano, ee.Geometry.Rectangle(list(b), geodesic=False)).unmask(-9999)
    res = ee.data.computePixels(dict(
        expression=img, fileFormat="NUMPY_NDARRAY",
        grid=dict(dimensions=dict(width=N, height=N),
                  affineTransform=dict(scaleX=RES, shearX=0, translateX=ix * 5000, shearY=0, scaleY=-RES, translateY=(iy + 1) * 5000),
                  crsCode="EPSG:31980")))
    a = np.stack([res[n] for n in BANDS]).astype(np.float32)  # 16,N,N
    valid = (a[15] > 0) & (a[:15] != -9999).all(0) & np.isfinite(a).all(0)
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, a=a, valid=valid)
    return a, valid


def rotulos(bloco: str, ano: int, a: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """-1 = ignorado; 0 = estável; 1 = corte raso; 2 = seletivo/degradação (mesma lógica do dataset local)."""
    lab = json.loads((ML / f"labels_{bloco}.json").read_text())
    to_utm = Transformer.from_crs(4326, 31980, always_xy=True).transform
    ix, iy = map(int, bloco.split("_"))
    tf = from_origin(ix * 5000, (iy + 1) * 5000, RES, RES)

    def ras(feats):
        geoms = [stransform(to_utm, shape(f["geometry"])) for f in feats]
        return rasterize(geoms, out_shape=(N, N), transform=tf, fill=0, dtype="uint8") if geoms else np.zeros((N, N), np.uint8)

    cr = [f for f in lab["prodes"] if int(f["properties"].get("year") or 0) == ano]
    sel = []
    for f in lab["deter"]:
        p = f["properties"]
        d = str(p.get("view_date", ""))[:10]
        if f"{ano - 1}-10-01" <= d < f"{ano}-10-01":
            if p.get("classname") in ("CS_DESORDENADO", "CS_GEOMETRICO", "DEGRADACAO"):
                sel.append(f)
            elif p.get("classname") == "DESMATAMENTO_CR":
                cr.append(f)
    excl = ras(lab["deter"] + [f for f in lab["prodes"] if int(f["properties"].get("year") or 0) >= 2008])
    nir, red = a[3], a[2]
    ndvi_pre = (nir - red) / np.maximum(nir + red, 1e-6)
    y = np.full((N, N), -1, np.int8)
    y[(ndvi_pre > .75) & (excl == 0)] = 0
    y[ras(cr) == 1] = 1
    y[ras(sel) == 1] = 2
    y[~valid] = -1
    return y


def baseline(a: np.ndarray, valid: np.ndarray) -> np.ndarray:
    score = np.clip(-.5 * (a[12] + a[13]), 0, 1)
    t = threshold_otsu(score[valid]) if valid.sum() > 10 else 1.0
    return binary_opening(score > t, structure=np.ones((3, 3))) & valid


def modelos_por_fold(df: pd.DataFrame) -> dict[str, tuple]:
    """Reproduz o GroupKFold do train.py e devolve, por bloco de teste, (modelo, limiar) do fold."""
    x = features(df[BANDS].to_numpy())
    y = (df.label.to_numpy() > 0).astype(int)
    g = df.bloco.to_numpy()
    out = {}
    for fold, (tr, te) in enumerate(GroupKFold(5).split(np.zeros(len(g)), groups=g)):
        itr, iva = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=42 + fold).split(x[tr], y[tr], g[tr]))
        inner = model().fit(x[tr[itr]], y[tr[itr]], feature_name=FEATURES)
        thr = best_threshold(y[tr[iva]], inner.booster_.predict(x[tr[iva]], num_threads=4))
        fitted = model().fit(x[tr], y[tr], feature_name=FEATURES)
        for b in set(g[te]):
            out[b] = (fitted.booster_, thr)
    return out


def main():
    ee.Initialize(project="project-f5ab0bff-aa9b-4cb2-97d")
    df, _ = exclude_demo_rows(pd.read_parquet(ML / "dataset.parquet"))
    df = df.reset_index(drop=True)
    anos = df.groupby("bloco").year.first().to_dict()
    vistos = blocos_vistos_pela_unet()
    alvo = sorted(b for b in anos if b not in vistos)
    print(f"blocos locais {len(anos)} | vistos pela U-Net (treino/val) {len(set(anos) & vistos)} | avaliados {len(alvo)}", flush=True)
    folds = modelos_por_fold(df)

    with ThreadPoolExecutor(max_workers=4) as pool:
        stacks = dict(zip(alvo, pool.map(lambda b: baixar(b, anos[b]), alvo)))

    rng = np.random.default_rng(42)
    full = {k: ([], []) for k in ("unet", "lightgbm", "baseline")}
    bal = {k: ([], []) for k in full}
    por_bloco = []
    for b in alvo:
        a, valid = stacks[b]
        if valid.mean() < .3:
            continue
        y = rotulos(b, anos[b], a, valid)
        lab = y >= 0
        if not (y == 0).any() or not (y > 0).any():
            continue
        pu = prob_unet(np.nan_to_num(a[:12]), valid) >= LIMIAR
        booster, thr = folds[b]
        flat = a.reshape(16, -1).T
        pl = np.zeros(N * N, bool)
        vv = valid.ravel()
        pl[vv] = booster.predict(features(flat[vv]), num_threads=4) >= thr
        pl = pl.reshape(N, N)
        pb = baseline(a, valid)
        yt = (y > 0)
        idx = {c: np.flatnonzero((y == c).ravel()) for c in (0, 1, 2)}
        pick = np.concatenate([rng.choice(v, min(len(v), n), replace=False) for c, n in ((0, 1000), (1, 500), (2, 500)) for v in [idx[c]] if len(v)])
        for k, p in (("unet", pu), ("lightgbm", pl), ("baseline", pb)):
            full[k][0].append(yt[lab]); full[k][1].append(p[lab])
            bal[k][0].append(yt.ravel()[pick]); bal[k][1].append(p.ravel()[pick])
        por_bloco.append(dict(bloco=b, ano=int(anos[b]), px_rotulados=int(lab.sum()), positivos=int(yt[lab].sum()),
                              iou_unet=metrics(yt[lab], pu[lab])["iou"], iou_lgbm=metrics(yt[lab], pl[lab])["iou"]))
        print(b, por_bloco[-1], flush=True)

    res = {}
    for nome, d in (("parede_a_parede", full), ("amostra_balanceada", bal)):
        res[nome] = {k: metrics(np.concatenate(v[0]).astype(int), np.concatenate(v[1]).astype(int)) for k, v in d.items()}
    ganhos = sum(r["iou_unet"] > r["iou_lgbm"] for r in por_bloco)
    out = dict(protocolo="Protocolo local: blocos de 5 km (EPSG:31980) do dataset do detector, excluídos os blocos com chips de treino/validação da U-Net; "
                         "LightGBM = modelo do fold em que o bloco foi teste (GroupKFold k=5 idêntico ao train.py); mesmos pixels para os 3 métodos.",
               n_blocos=len(por_bloco), blocos_excluidos_vistos=len(set(anos) & vistos), blocos_unet_vence=ganhos,
               resultados=res, por_bloco=por_bloco, gerado_em=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    (DL / "avaliacao_local.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for nome, r in res.items():
        print(nome, {k: (round(v["iou"], 3), round(v["f1"], 3)) for k, v in r.items()})
    print(f"U-Net vence em {ganhos}/{len(por_bloco)} blocos")


if __name__ == "__main__":
    main()
