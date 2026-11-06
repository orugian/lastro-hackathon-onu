"""Integra os resultados do Colab (DL) em data/artifacts/metrics.

- metrics/dl.json: cópia fiel do metrics_dl.json do Colab + config resumida.
- metrics/detector.json: acrescenta 3 entradas comparáveis entre si (mesmos chips de teste do Colab,
  blocos de 25 km), com prefixo "[Colab]". O modelo operacional selecionado continua o LightGBM local,
  porque os pesos da U-Net não foram exportados para inferência local.
Uso: uv run python scripts/integrar_dl.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contracts.models import MetricsDetector  # noqa: E402

DL = ROOT / "data" / "processed" / "dl"
MET = ROOT / "data" / "artifacts" / "metrics"


def entrada(nome: str, m: dict, obs: str) -> dict:
    return {k: m.get(k) for k in ("iou", "f1", "precisao", "recall", "matriz_confusao", "n_pixels_teste")} | {"nome": nome, "obs": obs}


def main() -> None:
    dl = json.loads((DL / "metrics_dl.json").read_text(encoding="utf-8"))
    cfg = json.loads((DL / "config.json").read_text(encoding="utf-8"))
    resumo = {
        "modelo": cfg.get("modelo"), "gpu": cfg.get("gpu"), "epocas_executadas": cfg.get("epocas_executadas"),
        "n_chips": cfg.get("n_chips"), "chip_px": cfg.get("chip_px"), "bloco_m": cfg.get("bloco_m"),
        "fallbacks": cfg.get("fallbacks"), "treino": cfg.get("treino"),
    }
    (MET / "dl.json").write_text(json.dumps({"metricas": dl, "config": resumo}, ensure_ascii=False, indent=1), encoding="utf-8")

    det_path = MET / "detector.json"
    det = json.loads(det_path.read_text(encoding="utf-8"))
    det["modelos"] = [m for m in det["modelos"] if not m["nome"].startswith("[Colab]")]
    base = ("Teste espacial do Colab: blocos de 25 km (70/15/15), "
            f"{dl['n_pixels_teste']:,} px, {cfg.get('n_chips')} chips 224x224, GPU {cfg.get('gpu')}. "
            "Comparável apenas às outras entradas [Colab] (mesmos pixels), não às métricas locais de 5 folds/5 km. ").replace(",", ".")
    fb = "; ".join(f"{f['model']}: {f['error'][:90]}" for f in cfg.get("fallbacks") or [])
    det["modelos"] += [
        entrada("[Colab] U-Net siamesa (ResNet34)", dl,
                base + f"Deep learning, limiar 0,5, {cfg.get('epocas_executadas')} épocas com early stopping. "
                + (f"Prithvi-EO-2.0 tentado e substituído pelo fallback ({fb}). " if fb else "")
                + "Pesos não exportados: experimento de pesquisa, ainda não usado no pipeline operacional."),
        entrada("[Colab] LightGBM", dl["lightgbm_mesmos_chips"], base + "Mesmo algoritmo do detector local, retreinado nos chips do Colab."),
        entrada("[Colab] ΔNDVI + Otsu", dl["baseline_mesmos_chips"], base + "Baseline sem treino nos mesmos chips."),
    ]
    det["protocolo"] = det["protocolo"].split(" | ")[0] + (
        " | Entradas [Colab]: segundo protocolo independente (blocos de 25 km), usado para comparar deep learning com LightGBM e baseline nos mesmos pixels.")
    MetricsDetector.model_validate(det)
    det_path.write_text(json.dumps(det, ensure_ascii=False, indent=2), encoding="utf-8")

    img = ROOT / "docs" / "img"
    img.mkdir(parents=True, exist_ok=True)
    for p in sorted(DL.glob("exemplo_*.png")):
        shutil.copy(p, img / f"dl_{p.name}")
    print("ok: dl.json + detector.json atualizados;", len(det["modelos"]), "modelos")


if __name__ == "__main__":
    main()
