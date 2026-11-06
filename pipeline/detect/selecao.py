"""Seleção de detectores (arquitetura híbrida, decidida por avaliação fora da amostra).

Detecção espacial (polígonos de distúrbio, áreas dentro/fora, indícios B/F2, camada de mudança no mapa):
  REGRA AND = pixel é distúrbio se LightGBM ≥ limiar E U-Net siamesa (deep learning) ≥ 0,5.
  Avaliação em 21 blocos de 5 km nunca vistos pela U-Net (pipeline/detect/avaliar_dl.py, calibrar_dl.py):
    - U-Net sozinha: IoU 0,729 (LightGBM 0,452), mas falso alarme 37,7% (LightGBM 16,1%) e, em florestas
      manejadas sem alerta, manchas de ~2 km em dossel intacto (mudança de domínio: treino com ≥ 50% de chips positivos).
    - Regra escolhida em metade dos blocos (A) e reportada na outra metade (B): AND tem IoU 0,455 (≈ LightGBM 0,451),
      precisão 0,88 (0,81) e falso alarme 9,2% (16,1%), ou seja, 43% menos falso alarme. Como casos acima do limiar
      geram comunicação ao IBAMA, a operação prioriza precisão. A média (U-Net+LightGBM)/2 ≥ 0,55 teve IoU 0,723,
      mas reintroduz as manchas; fica documentada como alternativa de maior recall.
Conversão imagem → volume (indício A, p10/p50/p90): features do LightGBM; recalibrar sobre a U-Net piorou
  (UPA R² 0,21 × 0,33; disparo de A em UPAs limpas 9,7% × 6,9%).

Env LASTRO_DETECTOR = unet (padrão, regra AND) | lightgbm.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ONNX = next((p for p in (ROOT / "models/lastro_unet.onnx", ROOT / "data/processed/dl/lastro_unet.onnx") if p.exists()),
            ROOT / "models/lastro_unet.onnx")
LIMIAR_UNET = 0.5


def nome() -> str:
    escolhido = os.environ.get("LASTRO_DETECTOR", "unet").lower()
    return "unet" if escolhido == "unet" and ONNX.exists() else "lightgbm"


def limiar_lgbm() -> float:
    try:
        return float(json.loads((ROOT / "data/processed/ml/threshold.json").read_text())["threshold"])
    except Exception:
        return 0.5


def prever_volume(stack_path, out_dir):
    """Probabilidade usada pela calibração de volume (sempre LightGBM) -> prob.tif."""
    from .predict import prever
    return prever(stack_path, out_dir)


def prever_espacial(stack_path, out_dir):
    """Probabilidade da detecção espacial -> prob_dl.tif = LightGBM confirmado pela U-Net (AND), ou prob.tif.
    Requer prob.tif (LightGBM) já calculado no mesmo grid."""
    import numpy as np
    import rasterio
    out_dir = Path(out_dir)
    if nome() != "unet":
        return {"prob_tif": str(out_dir / "prob.tif")}
    from .common import read_stack
    from .dl import prob_unet
    a, valid, profile = read_stack(stack_path)
    pu = prob_unet(np.nan_to_num(a[..., :12].transpose(2, 0, 1).astype(np.float32)), valid)
    with rasterio.open(out_dir / "prob.tif") as src:
        pl = src.read(1)
    # mantém a probabilidade do LightGBM só onde a U-Net também vê distúrbio; com o limiar do LightGBM
    # equivale a (LightGBM ≥ limiar) E (U-Net ≥ 0,5)
    ens = np.full(valid.shape, -9999, np.float32)
    ok = valid & (pl != -9999) & (pu != -9999)
    ens[ok] = np.where(pu[ok] >= LIMIAR_UNET, pl[ok], 0.0)
    dest = out_dir / "prob_dl.tif"
    p = profile.copy()
    p.update(count=1, dtype="float32", nodata=-9999, compress="deflate")
    with rasterio.open(dest, "w", **p) as dst:
        dst.write(ens, 1)
        dst.update_tags(modelo="LightGBM confirmado pela U-Net siamesa (AND)", limiar=str(limiar_lgbm()))
    return {"prob_tif": str(dest)}


# compatibilidade: calibrar.py chama prever()/metodo()/limiar() para o insumo do volume
prever = prever_volume


def metodo() -> str:
    return "lightgbm"


def limiar() -> float:
    return limiar_lgbm()


def limiar_espacial() -> float:
    return limiar_lgbm()


def rotulo_espacial() -> str:
    return "LightGBM confirmado pela U-Net" if nome() == "unet" else "LightGBM"


def metodo_espacial() -> str:
    return "lightgbm-and-unet" if nome() == "unet" else "lightgbm"


rotulo = rotulo_espacial
