"""Run with --demo for the fixed 4 x 4 km AMACRO AOI; --cbers adds WPM crops."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import time

import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point, box
from shapely.ops import transform

from .s2 import baixar_par_s2, janelas_automaticas, utm_crs
from .cbers import recorte_cbers


def demo_aoi():
    forward = Transformer.from_crs(4326, 31980, always_xy=True).transform
    back = Transformer.from_crs(31980, 4326, always_xy=True).transform
    x, y = forward(-63.10, -7.62)
    return transform(back, box(x-2000, y-2000, x+2000, y+2000))


def _value(row, *names):
    for name in names:
        value = row.get(name)
        if value is not None and not pd.isna(value) and str(value).strip():
            return str(value)[:10]
    return None


def _run(job, output, cbers):
    autex, aoi, pre, pos = job
    if not autex or any(ch not in "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-" for ch in autex):
        raise ValueError("Unsafe AUTEX directory name")
    dest = output / autex
    started = time.monotonic()
    meta = baixar_par_s2(autex, aoi, pre, pos, dest)
    if cbers:
        for period, window in (("pre", pre), ("pos", pos)):
            midpoint = (pd.Timestamp(window[0]) + (pd.Timestamp(window[1])-pd.Timestamp(window[0]))/2).date().isoformat()
            try:
                meta[f"cbers_{period}"] = recorte_cbers(aoi, midpoint, dest / f"cbers_{period}.png")
            except Exception as exc:
                meta[f"cbers_{period}_erro"] = str(exc)
    meta["tempo_s"] = round(time.monotonic()-started, 2)
    (dest / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretriagem", type=Path, default=Path("data/processed/pretriagem.csv"))
    parser.add_argument("--autorizacoes", type=Path, default=Path("data/processed/autorizacoes.parquet"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/processed/imagery"))
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--cbers", action="store_true")
    args = parser.parse_args(argv)
    if args.top < 1:
        parser.error("--top must be positive")
    if args.demo or not (args.pretriagem.exists() and args.autorizacoes.exists()):
        print("Using explicit fixed AMACRO demo AOI (not an authorization polygon).", flush=True)
        jobs = [("demo_amacro", demo_aoi(), ("2023-06-01", "2023-09-30"), ("2024-06-01", "2024-09-30"))]
    else:
        ranking = pd.read_csv(args.pretriagem, dtype={"autex": str})
        polygons = gpd.read_parquet(args.autorizacoes).to_crs(4326)
        polygons["autex"] = polygons["autex"].astype(str)
        jobs = []
        for _, row in ranking.head(args.top).iterrows():
            autex = str(row["autex"])
            matched = polygons[polygons.autex == autex]
            if matched.empty:
                raise ValueError(f"No polygon for AUTEX {autex}")
            geometry = matched.geometry.union_all()
            crs = utm_crs(geometry)
            buffered = transform(Transformer.from_crs(4326, crs, always_xy=True).transform, geometry).buffer(2000)
            aoi = transform(Transformer.from_crs(crs, 4326, always_xy=True).transform, buffered)
            merged = {**matched.iloc[0].to_dict(), **row.to_dict()}
            pre, pos = janelas_automaticas(_value(merged, "data_expl_min", "data_exploracao_min"),
                                          _value(merged, "data_expl_max", "data_exploracao_max"),
                                          _value(merged, "validade_ini", "validade_inicio"))
            jobs.append((autex, aoi, pre, pos))
    failed = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_run, job, args.out_dir, args.cbers): job[0] for job in jobs}
        for future in as_completed(futures):
            try:
                print(json.dumps(future.result(), ensure_ascii=False), flush=True)
            except Exception as exc:
                failed.append({"autex": futures[future], "erro": str(exc)})
                print(json.dumps(failed[-1], ensure_ascii=False), flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
