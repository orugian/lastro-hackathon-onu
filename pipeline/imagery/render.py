"""PNG overlays in EPSG:4326. Bounds are [west, south, east, north]."""
from pathlib import Path

import numpy as np
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import array_bounds
from rasterio.warp import calculate_default_transform, reproject


def geographic(data, transform, crs, max_px=1600, categorical=False):
    """Reproject band-first data, preserving NaN and limiting both dimensions."""
    data = np.asarray(data, dtype="float32")
    if data.ndim == 2:
        data = data[None]
    if max_px < 1:
        raise ValueError("max_px must be positive")
    _, height, width = data.shape
    dst_transform, w, h = calculate_default_transform(
        crs, "EPSG:4326", width, height, *array_bounds(height, width, transform)
    )
    factor = min(1, max_px / max(w, h))
    nw, nh = max(1, round(w * factor)), max(1, round(h * factor))
    dst_transform = dst_transform * dst_transform.scale(w / nw, h / nh)
    dest = np.full((data.shape[0], nh, nw), np.nan, dtype="float32")
    reproject(data, dest, src_transform=transform, src_crs=crs,
              dst_transform=dst_transform, dst_crs="EPSG:4326",
              src_nodata=np.nan, dst_nodata=np.nan,
              resampling=Resampling.nearest if categorical else Resampling.bilinear)
    return dest, list(array_bounds(nh, nw, dst_transform))


def stretch_rgb(rgb, valid=None):
    """Independent 2–98 percentile stretch, with transparent invalid pixels."""
    rgb = np.asarray(rgb, dtype="float32")
    valid = np.all(np.isfinite(rgb), axis=0) if valid is None else valid & np.all(np.isfinite(rgb), axis=0)
    out = np.zeros((*rgb.shape[1:], 4), dtype="uint8")
    for i in range(3):
        if valid.any():
            low, high = np.percentile(rgb[i][valid], [2, 98])
            if high <= low:
                high = low + 1
            out[..., i] = (np.nan_to_num(np.clip((rgb[i] - low) / (high - low), 0, 1)) * 255).astype("uint8")
    out[..., 3] = valid.astype("uint8") * 255
    return out


def render_rgb(rgb, transform, crs, out_png: Path, max_px=1600):
    data, bounds = geographic(rgb, transform, crs, max_px)
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(stretch_rgb(data)).save(out_png)
    return {"png": str(out_png), "bounds_4326": bounds, "crs": "EPSG:4326"}


def render_probability(data, transform, crs, out_png: Path, max_px=1600,
                       threshold=0.0, color=(230, 65, 35), categorical=False):
    """Render mask/probability in [0,1]; NaN and values <= threshold transparent."""
    warped, bounds = geographic(data, transform, crs, max_px, categorical)
    values = warped[0]
    valid = np.isfinite(values) & (values > threshold)
    rgba = np.zeros((*values.shape, 4), dtype="uint8")
    rgba[..., :3] = color
    rgba[..., 3] = np.where(valid, np.nan_to_num(np.clip(values, 0, 1)) * 230, 0).astype("uint8")
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba).save(out_png)
    return {"png": str(out_png), "bounds_4326": bounds, "crs": "EPSG:4326"}


def render_dndvi(data, transform, crs, out_png: Path, max_px=1600):
    # Warp signed changes before selecting declines to avoid bleeding positives.
    warped, bounds = geographic(data, transform, crs, max_px)
    values = warped[0]
    rgba = np.zeros((*values.shape, 4), dtype="uint8")
    rgba[..., :3] = (230, 55, 25)
    rgba[..., 3] = (np.nan_to_num(np.clip(-values / 0.4, 0, 1)) * 230).astype("uint8")
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba).save(out_png)
    return {"png": str(out_png), "bounds_4326": bounds, "crs": "EPSG:4326"}
