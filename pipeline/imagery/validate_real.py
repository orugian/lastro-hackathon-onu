"""Reproducible real-data smoke test. Optional --autex uses its polygon + 2 km."""
import argparse
import json
from pathlib import Path
import time

import geopandas as gpd
import numpy as np
from PIL import Image
from pyproj import Transformer
import rasterio
from shapely.ops import transform

from .cbers import recorte_cbers
from .run_batch import demo_aoi
from .s2 import baixar_par_s2, utm_crs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--autex")
    parser.add_argument("--cbers", action="store_true")
    args = parser.parse_args()
    name = args.autex or "demo_amacro"
    aoi = demo_aoi()
    if args.autex:
        polygons = gpd.read_parquet("data/processed/autorizacoes.parquet").to_crs(4326)
        selected = polygons[polygons.autex.astype(str) == args.autex]
        if selected.empty:
            raise ValueError(f"Unknown AUTEX {args.autex}")
        geometry = selected.geometry.union_all()
        crs = utm_crs(geometry)
        aoi = transform(Transformer.from_crs(crs, 4326, always_xy=True).transform,
                        transform(Transformer.from_crs(4326, crs, always_xy=True).transform, geometry).buffer(2000))
    folder = Path("data/processed/imagery") / name
    started = time.monotonic()
    cached = (folder / "s2_stack.tif").exists()
    meta = baixar_par_s2(name, aoi, ("2023-06-01", "2023-09-30"), ("2024-06-01", "2024-09-30"), folder)
    report = {"s2_tempo_s": round(time.monotonic()-started, 2), "s2_cache": cached, "s2": meta}
    with rasterio.open(meta["stack"]) as src:
        delta, valid = src.read(13), src.read(16) == 1
        report.update({"bytes": Path(meta["stack"]).stat().st_size, "shape": src.shape,
                       "valid_pixels": int(valid.sum()), "valid_area_ha": float(valid.sum()*src.res[0]*src.res[1]/10000),
                       "dndvi_quantiles": dict(zip(["min", "p01", "p05", "p50", "p95", "p99", "max"],
                                                  np.quantile(delta[valid], [0, .01, .05, .5, .95, .99, 1]).tolist())),
                       "decline_below_minus_0_1_pct": float(100*np.mean(delta[valid] < -0.1))})
        assert src.count == 16 and src.crs.to_epsg() in (31980, 31981)
        assert src.res == (10, 10) and valid.any()
        assert np.isfinite(delta[valid]).all()
        assert np.all(np.abs(delta[valid]) <= 2)
    for period, target in (("pre", "2023-08-01"), ("pos", "2024-08-01")):
        if args.cbers:
            t = time.monotonic()
            report[f"cbers_{period}"] = recorte_cbers(aoi, target, folder / f"cbers_{period}.png")
            report[f"cbers_{period}_tempo_s"] = round(time.monotonic()-t, 2)
    report["pngs"] = {}
    for png in folder.glob("*.png"):
        with Image.open(png) as image:
            assert max(image.size) <= 1600 and image.mode == "RGBA"
            report["pngs"][png.name] = {"size": image.size, "bytes": png.stat().st_size}
    report["interpretacao"] = "Quedas de indice sao variacao espectral, nao atribuicao causal a exploracao. Areas agricolas, sazonalidade e mistura temporal requerem verificacao."
    (folder / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # Explicit seasonal validation windows, not automatically inferred IF100 windows.
    meta.update({key: value for key, value in report.items() if key.startswith("cbers_")})
    meta["validacao_janelas_fixas"] = True
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
