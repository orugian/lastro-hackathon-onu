"""Sentinel-2 medians and signed post-minus-pre indices (surface reflectance)."""
from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time

import ee
import numpy as np
from pyproj import Transformer
import rasterio
from rasterio.features import geometry_mask
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.windows import Window, transform as window_transform
from shapely.geometry import mapping
from shapely.ops import transform as geom_transform

from .render import render_rgb, render_dndvi

BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]
STACK_BANDS = [f"{period}_{b}" for period in ("pre", "pos") for b in BANDS] + ["dNDVI", "dNBR", "dNDMI", "valid_mask"]
_EE_LOCK = threading.Lock()


def initialize():
    with _EE_LOCK:
        if not ee.data.is_initialized():
            project = os.environ.get("LASTRO_EE_PROJECT", "").strip()
            if not project:
                raise RuntimeError("Defina LASTRO_EE_PROJECT com seu projeto Google Earth Engine antes de reprocessar imagens.")
            ee.Initialize(project=project)


def utm_crs(aoi):
    lon = aoi.centroid.x
    if -66 <= lon < -60:
        return "EPSG:31980"
    if -60 <= lon <= -54:
        return "EPSG:31981"
    raise ValueError("AOI outside supported SIRGAS UTM zones (-66 to -54)")


def janelas_automaticas(data_expl_min: str, data_expl_max: str, validade_ini: str):
    """Inclusive ISO windows. Acquisition expands post to 180 days if needed."""
    start = date.fromisoformat(data_expl_min or validade_ini)
    end = date.fromisoformat(data_expl_max or data_expl_min or validade_ini)
    if end < start:
        raise ValueError("Exploration end precedes start")
    return ((f"{start.year - 1}-06-01", f"{start.year - 1}-09-30"),
            (end.isoformat(), (end + timedelta(days=120)).isoformat()))


def indices(bands):
    """Return NDVI, NBR, NDMI; zero denominators are unobservable (NaN)."""
    nir = bands[3]
    results = []
    for other in (bands[2], bands[5], bands[4]):
        den = nir + other
        result = np.full_like(den, np.nan, dtype="float32")
        np.divide(nir - other, den, out=result, where=np.abs(den) > 1e-8)
        results.append(result)
    return np.stack(results)


def _collection(region, window):
    start, end = window
    end_exclusive = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    sr = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region).filterDate(start, end_exclusive)
    cp = ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY").filterBounds(region).filterDate(start, end_exclusive)
    joined = ee.ImageCollection(ee.Join.saveFirst("clouds").apply(
        sr, cp, ee.Filter.equals(leftField="system:index", rightField="system:index")))

    def mask(image):
        scl = image.select("SCL")
        good = ee.Image(image.get("clouds")).select("probability").lt(40)
        for code in (0, 1, 3, 8, 9, 10, 11):
            good = good.And(scl.neq(code))
        good = good.And(image.select(BANDS).mask().reduce(ee.Reducer.min()))
        clear_fraction = good.rename("clear").unmask(0).reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=60, maxPixels=10000000).get("clear")
        return image.select(BANDS).multiply(0.0001).updateMask(good).set("clear_fraction", clear_fraction)

    return joined.map(mask)


def _prepare(region, window):
    coll = _collection(region, window)
    stats = ee.Dictionary({"n": coll.size(), "clean": coll.filter(ee.Filter.gte("clear_fraction", 0.9)).size(),
                           "mean_clear": coll.aggregate_mean("clear_fraction")}).getInfo()
    return coll.median(), stats


def _download(image, crs, transform, width, height, tile_px=512):
    """512² x 12 float32 = 12 MiB per request, safely under EE limits."""
    for row in range(0, height, tile_px):
        for col in range(0, width, tile_px):
            w, h = min(tile_px, width-col), min(tile_px, height-row)
            window = Window(col, row, w, h)
            t = window_transform(window, transform)
            request = {"expression": image, "fileFormat": "GEO_TIFF", "grid": {
                "dimensions": {"width": w, "height": h}, "crsCode": crs,
                "affineTransform": {"scaleX": t.a, "shearX": 0, "translateX": t.c,
                                    "shearY": 0, "scaleY": t.e, "translateY": t.f}}}
            for attempt in range(3):
                try:
                    raw = ee.data.computePixels(request)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(2 ** attempt)
            with MemoryFile(raw) as mem, mem.open() as src:
                yield window, src.read().astype("float32")


def _render_stack(stack, out_dir):
    with rasterio.open(stack) as src:
        pre = src.read([3, 2, 1])
        pos = src.read([9, 8, 7])
        delta = src.read(13)
        pre[pre == src.nodata] = np.nan
        pos[pos == src.nodata] = np.nan
        delta[delta == src.nodata] = np.nan
        meta = render_rgb(pre, src.transform, src.crs, out_dir / "s2_pre.png")
        render_rgb(pos, src.transform, src.crs, out_dir / "s2_pos.png")
        render_dndvi(delta, src.transform, src.crs, out_dir / "dndvi.png")
    return meta["bounds_4326"]


def baixar_par_s2(autex: str, aoi_4326, pre: tuple[str, str], pos: tuple[str, str],
                  out_dir: Path, escala_m: int = 10) -> dict:
    if aoi_4326.is_empty or not aoi_4326.is_valid or aoi_4326.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("AOI must be a valid nonempty polygon in EPSG:4326")
    if escala_m <= 0:
        raise ValueError("Scale must be positive")
    for window in (pre, pos):
        if date.fromisoformat(window[0]) > date.fromisoformat(window[1]):
            raise ValueError("Window end precedes start")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stack = out_dir / "s2_stack.tif"
    metadata = out_dir / "s2_meta.json"
    key = hashlib.sha256(json.dumps([autex, mapping(aoi_4326), pre, pos, escala_m], sort_keys=True).encode()).hexdigest()
    if stack.exists():
        if metadata.exists():
            cached = json.loads(metadata.read_text(encoding="utf-8"))
        else:
            with rasterio.open(stack) as src:
                cached = json.loads(src.tags()["imagery_metadata"])
        if cached.get("cache_key") != key:
            raise ValueError("Existing stack has different inputs; use a different output directory")
        if not all((out_dir / name).exists() for name in ("s2_pre.png", "s2_pos.png", "dndvi.png")):
            cached["bounds_4326"] = _render_stack(stack, out_dir)
        return cached
    initialize()
    crs = utm_crs(aoi_4326)
    projected = geom_transform(Transformer.from_crs(4326, crs, always_xy=True).transform, aoi_4326)
    left, bottom, right, top = projected.bounds
    left, top = math.floor(left / escala_m) * escala_m, math.ceil(top / escala_m) * escala_m
    width, height = math.ceil((right-left)/escala_m), math.ceil((top-bottom)/escala_m)
    transform = from_origin(left, top, escala_m, escala_m)
    region = ee.Geometry(mapping(aoi_4326))
    before, stats_pre = _prepare(region, pre)
    if not stats_pre["n"]:
        raise ValueError(f"No joined Sentinel-2 scenes for {pre}")
    after, stats_pos = _prepare(region, pos)
    actual_pos = pos
    if stats_pos["clean"] < 3 and (date.fromisoformat(pos[1])-date.fromisoformat(pos[0])).days <= 120:
        actual_pos = (pos[0], (date.fromisoformat(pos[0])+timedelta(days=180)).isoformat())
        after, stats_pos = _prepare(region, actual_pos)
    if not stats_pos["n"]:
        raise ValueError(f"No joined Sentinel-2 scenes for {actual_pos}")
    image = before.rename(STACK_BANDS[:6]).addBands(after.rename(STACK_BANDS[6:12])).clip(region).unmask(-9999).toFloat()
    profile = dict(driver="GTiff", width=width, height=height, count=16, dtype="float32",
                   crs=crs, transform=transform, nodata=-9999, compress="deflate", predictor=3,
                   tiled=True, blockxsize=256, blockysize=256, BIGTIFF="IF_SAFER")
    counts = np.zeros(3, dtype="int64")
    temporary = out_dir / "s2_stack.partial.tif"
    try:
        with rasterio.open(temporary, "w", **profile) as dst:
            dst.descriptions = tuple(STACK_BANDS)
            for window, data in _download(image, crs, transform, width, height):
                inside = geometry_mask([mapping(projected)], out_shape=data.shape[1:],
                                       transform=window_transform(window, transform), invert=True)
                data[(data == -9999) | ~np.isfinite(data)] = np.nan
                data[:, ~inside] = np.nan
                valid_pre = np.all(np.isfinite(data[:6]), axis=0)
                valid_pos = np.all(np.isfinite(data[6:]), axis=0)
                delta = indices(data[6:]) - indices(data[:6])
                valid = valid_pre & valid_pos & np.all(np.isfinite(delta), axis=0)
                delta[:, ~valid] = np.nan
                result = np.concatenate([data, delta, valid[None].astype("float32")])
                dst.write(np.nan_to_num(result, nan=-9999), window=window)
                counts += (inside.sum(), (inside & ~valid_pre).sum(), (inside & ~valid_pos).sum())
            meta = {"stack": str(stack), "crs": crs, "cache_key": key, "autex": autex,
                    "bounds_4326": list(aoi_4326.bounds), "pre": list(pre), "pos": list(actual_pos),
                    "nuvem_pct_pre": float(100*counts[1]/max(counts[0], 1)),
                    "nuvem_pct_pos": float(100*counts[2]/max(counts[0], 1)),
                    "n_cenas_pre": stats_pre["n"], "n_cenas_pos": stats_pos["n"],
                    "n_cenas_limpas_pre": stats_pre["clean"], "n_cenas_limpas_pos": stats_pos["clean"],
                    "nuvem_media_cenas_pct_pre": 100*(1-stats_pre["mean_clear"]),
                    "nuvem_media_cenas_pct_pos": 100*(1-stats_pos["mean_clear"]),
                    "rotulo_pre": f"Sentinel-2 · mediana {pre[0]}/{pre[1]}",
                    "rotulo_pos": f"Sentinel-2 · mediana {actual_pos[0]}/{actual_pos[1]}",
                    "qualidade": "nuvem_pct = pixels sem observacao limpa no composto, incluindo NoData; cena limpa >=90% AOI valida",
                    "reflectancia": "0–1; B11/B12 nativos 20 m reamostrados para grade 10 m",
                    "bandas": STACK_BANDS, "source_mode": "real"}
            dst.update_tags(imagery_metadata=json.dumps(meta, ensure_ascii=False), delta="pos - pre")
        temporary.replace(stack)
    finally:
        if temporary.exists():
            temporary.unlink()
    meta["bounds_4326"] = _render_stack(stack, out_dir)
    with rasterio.open(stack, "r+") as dst:
        dst.update_tags(imagery_metadata=json.dumps(meta, ensure_ascii=False))
    metadata.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta
