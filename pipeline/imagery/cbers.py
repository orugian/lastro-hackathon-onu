"""Window-only CBERS WPM COG access; brightness is a heuristic, not cloud truth."""
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path

import numpy as np
from pyproj import Transformer
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds
import requests
from shapely.geometry import mapping, shape
from shapely.ops import transform as geom_transform

from .render import render_rgb

STAC = "https://data.inpe.br/bdc/stac/v1/"
LOG = logging.getLogger(__name__)


def _search(aoi, target, days):
    body = {"collections": ["CB4A-WPM-PCA-FUSED-1"], "intersects": mapping(aoi),
            "datetime": f"{(target-timedelta(days=days)).strftime('%Y-%m-%dT00:00:00Z')}/{(target+timedelta(days=days)).strftime('%Y-%m-%dT23:59:59Z')}",
            "limit": 100}
    url, method, items = STAC + "search", "POST", []
    while url:
        response = requests.request(method, url, json=body if method == "POST" else None, timeout=90)
        response.raise_for_status()
        page = response.json()
        items.extend(page.get("features", []))
        next_link = next((link for link in page.get("links", []) if link["rel"] == "next"), None)
        if next_link is None:
            break
        url, method = next_link["href"], next_link.get("method", "GET")
        body = {**body, **next_link.get("body", {})} if next_link.get("merge") else next_link.get("body", body)
    return sorted(items, key=lambda i: abs((_item_date(i)-target).total_seconds()))


def _item_date(item):
    return datetime.fromisoformat(item["properties"]["datetime"].replace("Z", "+00:00"))


def _read_crop(item, aoi, max_px):
    assets = item["assets"]
    asset = assets.get("tci") or assets.get("rgb")
    if not asset:
        raise ValueError("CBERS item lacks tci/rgb asset")
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff",
                      GDAL_HTTP_TIMEOUT="60", GDAL_HTTP_MAX_RETRY="2"):
        with rasterio.open("/vsicurl/" + asset["href"]) as src:
            projected = geom_transform(Transformer.from_crs(4326, src.crs, always_xy=True).transform, aoi)
            window = from_bounds(*projected.bounds, transform=src.transform).round_offsets().round_lengths()
            factor = min(1, max_px/max(window.width, window.height))
            w, h = max(1, round(window.width*factor)), max(1, round(window.height*factor))
            data = src.read([1, 2, 3], window=window, out_shape=(3, h, w),
                            boundless=True, fill_value=0, resampling=Resampling.nearest)
            transform = src.window_transform(window) * src.transform.scale(window.width/w, window.height/h)
            inside = geometry_mask([mapping(projected)], out_shape=(h, w), transform=transform, invert=True)
            valid = np.any(data != 0, axis=0) & inside
            coverage = float(valid.sum()/max(1, inside.sum()))
            bright = float((data.mean(axis=0)[valid] > 200).mean()) if valid.any() else 1.0
            data = data.astype("float32")
            data[:, ~valid] = np.nan
            return data, transform, src.crs, coverage, bright


def recorte_cbers(aoi_4326, data_alvo: str, out_png: Path, janela_dias=120, max_px=1600) -> dict | None:
    if aoi_4326.is_empty or not aoi_4326.is_valid:
        raise ValueError("Invalid AOI")
    if janela_dias < 0 or max_px < 1:
        raise ValueError("Invalid window or pixel limit")
    target = datetime.fromisoformat(data_alvo).replace(tzinfo=timezone.utc)
    out_png = Path(out_png)
    sidecar = out_png.with_suffix(".json")
    inputs = {"aoi_wkb": aoi_4326.wkb_hex, "data_alvo": data_alvo, "janela_dias": janela_dias, "max_px": max_px}
    if out_png.exists() and sidecar.exists():
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        if meta.get("inputs") == inputs:
            return meta
    items = _search(aoi_4326, target, janela_dias)
    best, failures = None, []
    # Prefer low brightness contamination; temporal proximity breaks ties.
    for item in items:
        if item.get("geometry") and not shape(item["geometry"]).intersects(aoi_4326):
            continue
        try:
            result = _read_crop(item, aoi_4326, max_px)
        except Exception as exc:
            failures.append(f"{item['id']}: {exc}")
            LOG.warning("CBERS crop failed %s: %s", item["id"], exc)
            continue
        data, transform, crs, coverage, bright = result
        if coverage <= 0.90:
            continue
        score = (round(bright, 2), abs((_item_date(item)-target).total_seconds()))
        if best is None or score < best[0]:
            best = (score, item, result)
        # Nearest scene with <1% bright contamination is already sufficient.
        if bright < 0.01:
            break
    if best is None:
        if failures and len(failures) == len(items):
            raise RuntimeError("All CBERS COG reads failed: " + "; ".join(failures[:3]))
        return None
    _, item, (data, transform, crs, coverage, bright) = best
    meta = render_rgb(data, transform, crs, out_png, max_px)
    meta.update({"data": _item_date(item).date().isoformat(), "item_id": item["id"],
                 "cobertura_pct": 100*coverage, "brilho_nuvem_pct": 100*bright,
                 "resolucao_nativa_m": 2, "inputs": inputs,
                 "selecao": "menor fracao RGB medio >200; desempate por proximidade temporal; interrompe ao encontrar <1%",
                 "source_mode": "real"})
    sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta
