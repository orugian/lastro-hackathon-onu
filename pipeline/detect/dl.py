"""Inferência da U-Net siamesa (deep learning, treinada no Colab) via ONNX Runtime.

Mesma interface de pipeline.detect.predict.prever: lê o stack S2 de 16 bandas e grava
prob.tif, mask.tif e poligonos.geojson. Usa as 12 bandas de reflectância (pré+pós), a
mesma normalização do treino e janelas deslizantes 224 px com peso Hann nas bordas.
"""
from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import geometry_mask, shapes
from shapely import transform
from shapely.geometry import mapping, shape

from .common import read_stack

ROOT = Path(__file__).resolve().parents[2]
ONNX = next((p for p in (ROOT / "models/lastro_unet.onnx", ROOT / "data/processed/dl/lastro_unet.onnx") if p.exists()),
            ROOT / "models/lastro_unet.onnx")
# Normalização usada no treino (config.json do Colab: normalization_mean/std)
MEAN = np.array([.108, .137, .151, .226, .240, .186], np.float32)
STD = np.array([.057, .065, .079, .103, .114, .104], np.float32)
SIZE, STEP, LIMIAR = 224, 168, 0.5
METODO = "unet-siamesa"


@lru_cache(maxsize=1)
def _sessao(path: str = str(ONNX)):
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 4
    return ort.InferenceSession(path, opts, providers=["CPUExecutionProvider"])


def _starts(n: int) -> list[int]:
    if n <= SIZE:
        return [0]
    return sorted(set(list(range(0, n - SIZE + 1, STEP)) + [n - SIZE]))


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def prob_unet(x12: np.ndarray, valid: np.ndarray, batch: int = 8) -> np.ndarray:
    """x12: (12,H,W) reflectância 0-1; valid: (H,W). Retorna prob (H,W) float32, -9999 fora do válido."""
    _, h, w = x12.shape
    norm = (x12 - np.tile(MEAN, 2)[:, None, None]) / np.tile(STD, 2)[:, None, None]
    norm[:, ~valid] = 0
    ph, pw = max(h, SIZE), max(w, SIZE)
    if (ph, pw) != (h, w):
        pad = np.zeros((12, ph, pw), np.float32)
        pad[:, :h, :w] = norm
        norm = pad
    acc = np.zeros((ph, pw), np.float32)
    wsum = np.zeros((ph, pw), np.float32)
    wk = np.maximum(np.outer(np.hanning(SIZE), np.hanning(SIZE)), .01).astype(np.float32)
    coords = [(r, c) for r in _starts(ph) for c in _starts(pw)]
    sess = _sessao()
    for i in range(0, len(coords), batch):
        part = coords[i:i + batch]
        xb = np.stack([norm[:, r:r + SIZE, c:c + SIZE] for r, c in part]).astype(np.float32)
        pb = _sigmoid(sess.run(None, {"x": xb})[0])
        for (r, c), p in zip(part, pb):
            acc[r:r + SIZE, c:c + SIZE] += p * wk
            wsum[r:r + SIZE, c:c + SIZE] += wk
    prob = (acc / np.maximum(wsum, 1e-6))[:h, :w]
    out = np.full((h, w), -9999, np.float32)
    out[valid] = prob[valid]
    return out


def prever(stack_path, out_dir, limiar: float = LIMIAR):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    a, valid, profile = read_stack(stack_path)
    if profile["crs"] is None:
        raise ValueError("Stack sem CRS")
    x12 = np.nan_to_num(a[..., :12].transpose(2, 0, 1).astype(np.float32))
    prob = prob_unet(x12, valid)
    mask = np.full(valid.shape, 255, np.uint8)
    mask[valid] = (prob[valid] >= limiar).astype(np.uint8)
    paths = {"prob_tif": str(out / "prob.tif"), "mask_tif": str(out / "mask.tif"),
             "poligonos_geojson": str(out / "poligonos.geojson")}
    for key, arr, dtype, nodata in [("prob_tif", prob, "float32", -9999), ("mask_tif", mask, "uint8", 255)]:
        p = profile.copy()
        p.update(count=1, dtype=dtype, nodata=nodata, compress="deflate")
        with rasterio.open(paths[key], "w", **p) as dst:
            dst.write(arr, 1)
            dst.update_tags(modelo=METODO, limiar=str(limiar))
    to_wgs = Transformer.from_crs(profile["crs"], 4326, always_xy=True).transform
    records = []
    for geom, _ in shapes(mask, mask=(mask == 1), transform=profile["transform"]):
        wgs = transform(shape(geom), to_wgs, interleaved=False)
        epsg = 31980 if wgs.centroid.x < -60 else 31981
        area = transform(wgs, Transformer.from_crs(4326, epsg, always_xy=True).transform, interleaved=False).area / 10000
        if area < .1:
            continue
        inside = geometry_mask([geom], out_shape=valid.shape, transform=profile["transform"], invert=True) & (mask == 1)
        records.append({"type": "Feature", "geometry": mapping(wgs),
                        "properties": {"id": str(len(records) + 1), "area_ha": area,
                                       "prob": float(prob[inside].mean()), "metodo": METODO}})
    Path(paths["poligonos_geojson"]).write_text(json.dumps({"type": "FeatureCollection", "features": records}), encoding="utf-8")
    return paths


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stack")
    ap.add_argument("--out-dir", default="data/processed/dl/prediction")
    a = ap.parse_args()
    print(json.dumps(prever(a.stack, a.out_dir), indent=2))
