import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
from PIL import Image
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from pipeline.imagery import cbers, s2
from pipeline.imagery.render import render_rgb, render_probability, render_dndvi
from pipeline.imagery.run_batch import demo_aoi, main


def test_windows():
    assert s2.janelas_automaticas("2024-07-01", "2024-09-01", "2022-01-01") == (
        ("2023-06-01", "2023-09-30"), ("2024-09-01", "2024-12-30"))
    assert s2.janelas_automaticas(None, None, "2024-01-01")[1] == ("2024-01-01", "2024-04-30")
    with pytest.raises(ValueError):
        s2.janelas_automaticas("2024-08-01", "2024-07-01", None)


def test_indices_sign_and_nodata():
    pre = np.array([0.1, 0.1, 0.1, 0.6, 0.2, 0.2], dtype="float32")[:, None, None]
    pos = np.array([0.1, 0.1, 0.2, 0.3, 0.3, 0.3], dtype="float32")[:, None, None]
    assert np.all(s2.indices(pos)-s2.indices(pre) < 0)
    assert np.isnan(s2.indices(np.zeros_like(pre))).all()
    assert s2.utm_crs(box(-63, -8, -62, -7)) == "EPSG:31980"
    assert s2.utm_crs(box(-60, -8, -59, -7)) == "EPSG:31981"


def test_geographic_render_and_alpha(tmp_path):
    t = from_origin(490000, 9160000, 10, 10)
    rgb = np.ones((3, 20, 30), dtype="float32")
    rgb[:, :5] = np.nan
    meta = render_rgb(rgb, t, "EPSG:31980", tmp_path / "rgb.png", max_px=16)
    with Image.open(meta["png"]) as image:
        assert max(image.size) <= 16
        assert image.mode == "RGBA"
        assert np.any(np.array(image)[..., 3] == 0)
    west, south, east, north = meta["bounds_4326"]
    assert -66 < west < east < -60 and -10 < south < north < 0
    transform = from_origin(-63, -7, 0.001, 0.001)
    changes = np.array([[-0.3, 0.3], [np.nan, 0]], dtype="float32")
    render_dndvi(changes, transform, "EPSG:4326", tmp_path / "d.png")
    alpha = np.array(Image.open(tmp_path / "d.png"))[..., 3]
    assert alpha[0, 0] > 0
    assert alpha[0, 1] == alpha[1, 0] == alpha[1, 1] == 0
    render_probability(np.array([[1, 0], [np.nan, 0.5]]), transform, 4326, tmp_path / "p.png", categorical=True)
    alpha = np.array(Image.open(tmp_path / "p.png"))[..., 3]
    assert alpha[0, 0] > alpha[1, 1] > 0
    assert alpha[0, 1] == alpha[1, 0] == 0


def test_download_tiles_mocked(monkeypatch):
    calls = []
    def compute(request):
        calls.append(request)
        grid = request["grid"]
        w, h = grid["dimensions"]["width"], grid["dimensions"]["height"]
        with rasterio.io.MemoryFile() as mem:
            with mem.open(driver="GTiff", width=w, height=h, count=12, dtype="float32",
                          crs=grid["crsCode"], transform=from_origin(0, 100, 10, 10)) as ds:
                ds.write(np.ones((12, h, w), dtype="float32"))
            return mem.read()
    monkeypatch.setattr(s2.ee.data, "computePixels", compute)
    tiles = list(s2._download(None, "EPSG:31980", from_origin(0, 100, 10, 10), 7, 5, tile_px=4))
    assert len(tiles) == 4
    assert sum(a.shape[1]*a.shape[2] for _, a in tiles) == 35
    assert calls[-1]["grid"]["affineTransform"]["translateX"] == 40
    assert calls[-1]["grid"]["affineTransform"]["translateY"] == 60


def test_stack_and_cache_without_network(monkeypatch, tmp_path):
    monkeypatch.setattr(s2, "initialize", lambda: None)
    monkeypatch.setattr(s2.ee, "Geometry", lambda value: value)
    prepared = []
    def prepare(region, window):
        prepared.append(window)
        return MagicMock(), {"n": 5, "clean": 1 if len(prepared) == 2 else 4, "mean_clear": 0.9}
    monkeypatch.setattr(s2, "_prepare", prepare)
    def download(image, crs, transform, width, height):
        data = np.ones((12, height, width), dtype="float32") * 0.2
        data[3] = 0.6
        data[9] = 0.3
        data[:6, 1, 1] = -9999
        yield rasterio.windows.Window(0, 0, width, height), data
    monkeypatch.setattr(s2, "_download", download)
    aoi = box(-63.001, -7.001, -63, -7)
    pre, pos = ("2023-06-01", "2023-09-30"), ("2024-07-01", "2024-08-01")
    meta = s2.baixar_par_s2("test", aoi, pre, pos, tmp_path)
    assert meta["pos"][1] == "2024-12-28"
    assert len(prepared) == 3
    with rasterio.open(meta["stack"]) as ds:
        assert ds.count == 16 and ds.res == (10, 10)
        assert ds.descriptions == tuple(s2.STACK_BANDS)
        mask = ds.read(16)
        assert set(np.unique(mask)) <= {0, 1}
        assert mask[1, 1] == 0
        assert np.all(ds.read(13)[mask == 1] < 0)
    # Cache and regeneration of a missing PNG require no EE access.
    monkeypatch.setattr(s2, "initialize", lambda: pytest.fail("Cache tried network"))
    (tmp_path / "dndvi.png").unlink()
    assert s2.baixar_par_s2("test", aoi, pre, pos, tmp_path)["cache_key"] == meta["cache_key"]
    assert (tmp_path / "dndvi.png").exists()
    with pytest.raises(ValueError, match="different inputs"):
        s2.baixar_par_s2("test", aoi, pre, pos, tmp_path, escala_m=20)


def test_cbers_quality_selection_and_coverage(monkeypatch, tmp_path):
    items = [{"id": str(i), "properties": {"datetime": f"2024-07-0{i+1}T00:00:00Z"}} for i in range(3)]
    monkeypatch.setattr(cbers, "_search", lambda *args: items)
    def crop(item, *args):
        coverage, bright = [(0.89, 0), (1, 0.6), (0.99, 0.02)][int(item["id"])]
        return np.ones((3, 5, 5)), from_origin(-63, -7, 0.001, 0.001), "EPSG:4326", coverage, bright
    monkeypatch.setattr(cbers, "_read_crop", crop)
    result = cbers.recorte_cbers(demo_aoi(), "2024-07-01", tmp_path / "c.png")
    assert result["item_id"] == "2" and result["cobertura_pct"] == 99
    monkeypatch.setattr(cbers, "_search", lambda *args: pytest.fail("Cache tried network"))
    assert cbers.recorte_cbers(demo_aoi(), "2024-07-01", tmp_path / "c.png")["item_id"] == "2"


def test_cbers_no_scenes(monkeypatch, tmp_path):
    monkeypatch.setattr(cbers, "_search", lambda *args: [])
    assert cbers.recorte_cbers(demo_aoi(), "2024-07-01", tmp_path / "none.png") is None


def test_cbers_network_failure_not_no_coverage(monkeypatch, tmp_path):
    monkeypatch.setattr(cbers, "_search", lambda *args: [{"id": "broken"}])
    monkeypatch.setattr(cbers, "_read_crop", lambda *args: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(RuntimeError, match="COG reads failed"):
        cbers.recorte_cbers(demo_aoi(), "2024-07-01", tmp_path / "none.png")


def test_batch_reads_ranking_buffers_utm_and_dates(monkeypatch, tmp_path):
    import geopandas as gpd
    import pandas as pd
    from pipeline.imagery import run_batch
    ranking = tmp_path / "ranking.csv"
    polygons = tmp_path / "autorizacoes.parquet"
    pd.DataFrame([{"autex": "001", "data_expl_min": "2024-07-01", "data_expl_max": "2024-08-01"}]).to_csv(ranking, index=False)
    gpd.GeoDataFrame({"autex": ["001"], "validade_ini": ["2023-01-01"]},
                     geometry=[box(-63.001, -7.001, -63, -7)], crs=4326).to_parquet(polygons)
    calls = []
    def run(job, output, cbers):
        calls.append(job)
        return {"ok": True}
    monkeypatch.setattr(run_batch, "_run", run)
    main(["--pretriagem", str(ranking), "--autorizacoes", str(polygons), "--out-dir", str(tmp_path), "--top", "1"])
    autex, aoi, pre, pos = calls[0]
    assert autex == "001"
    projected = gpd.GeoSeries([aoi], crs=4326).to_crs(31980).iloc[0]
    assert 4200 > projected.bounds[2] - projected.bounds[0] > 4100
    assert pre == ("2023-06-01", "2023-09-30")
    assert pos == ("2024-08-01", "2024-11-29")


def test_search_pagination(monkeypatch):
    from datetime import datetime, timezone
    calls = []
    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        response = MagicMock()
        i = len(calls)
        response.json.return_value = {
            "features": [{"id": str(i), "properties": {"datetime": f"2024-07-0{i}T00:00:00Z"}}],
            "links": [{"rel": "next", "href": "https://example.test/next", "method": "POST", "body": {"token": "next"}, "merge": True}] if i == 1 else []}
        return response
    monkeypatch.setattr(cbers.requests, "request", request)
    found = cbers._search(demo_aoi(), datetime(2024, 7, 1, tzinfo=timezone.utc), 120)
    assert len(found) == 2
    assert calls[1][2]["json"]["token"] == "next"
    assert calls[1][2]["json"]["collections"] == ["CB4A-WPM-PCA-FUSED-1"]
