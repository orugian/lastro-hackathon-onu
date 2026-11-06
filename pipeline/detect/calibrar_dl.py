"""Escolhe a regra operacional da U-Net (limiar / ensemble) sem vazamento:
seleção em metade dos blocos de avaliação local (A), relatório na outra metade (B).

Estratégias: U-Net com limiar t; ensemble AND (U-Net ≥ t E LightGBM); média das probabilidades.
Critério de seleção em A: maior IoU sujeito a taxa de falso alarme ≤ a do LightGBM em A.
Uso: uv run python -m pipeline.detect.calibrar_dl
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .avaliar_dl import DL, ML, N, baixar, blocos_vistos_pela_unet, modelos_por_fold, rotulos
from .common import features
from .dataset import exclude_demo_rows
from .dl import prob_unet


def _m(y, p):
    tp = int((y & p).sum()); fp = int((~y & p).sum()); fn = int((y & ~p).sum()); tn = int((~y & ~p).sum())
    return dict(iou=tp / max(tp + fp + fn, 1), f1=2 * tp / max(2 * tp + fp + fn, 1), precisao=tp / max(tp + fp, 1),
                recall=tp / max(tp + fn, 1), falso_alarme=fp / max(fp + tn, 1), matriz_confusao=[[tn, fp], [fn, tp]], n_pixels_teste=tp + fp + fn + tn)


def main():
    df, _ = exclude_demo_rows(pd.read_parquet(ML / "dataset.parquet"))
    df = df.reset_index(drop=True)
    anos = df.groupby("bloco").year.first().to_dict()
    alvo = sorted(b for b in anos if b not in blocos_vistos_pela_unet())
    folds = modelos_por_fold(df)
    dados = []
    for b in alvo:
        a, valid = baixar(b, anos[b])
        if valid.mean() < .3:
            continue
        y = rotulos(b, anos[b], a, valid)
        lab = y >= 0
        if not (y == 0).any() or not (y > 0).any():
            continue
        pu = prob_unet(np.nan_to_num(a[:12]), valid)
        booster, thr = folds[b]
        flat = a.reshape(16, -1).T
        pl = np.zeros(N * N, np.float32)
        vv = valid.ravel()
        pl[vv] = booster.predict(features(flat[vv]), num_threads=4)
        pl = pl.reshape(N, N)
        from .avaliar_dl import baseline as _base
        dados.append(dict(b=b, y=(y > 0)[lab], pu=pu[lab], pl=pl[lab], thr=thr, base=_base(a, valid)[lab]))
    rng = np.random.default_rng(7)
    ordem = rng.permutation(len(dados))
    A = [dados[i] for i in ordem[: len(dados) // 2]]
    B = [dados[i] for i in ordem[len(dados) // 2:]]

    def avalia(grupo, regra):
        y = np.concatenate([d["y"] for d in grupo])
        p = np.concatenate([regra(d) for d in grupo])
        return _m(y, p)

    regras = {"lightgbm": lambda d: d["pl"] >= d["thr"]}
    for t in np.round(np.arange(.5, .96, .05), 2):
        regras[f"unet@{t}"] = (lambda t: lambda d: d["pu"] >= t)(t)
        regras[f"and@{t}"] = (lambda t: lambda d: (d["pu"] >= t) & (d["pl"] >= d["thr"]))(t)
        regras[f"media@{t}"] = (lambda t: lambda d: (d["pu"] + d["pl"]) / 2 >= t)(t)
    resA = {k: avalia(A, r) for k, r in regras.items()}
    fa_lgbm = resA["lightgbm"]["falso_alarme"]
    elegiveis = {k: v for k, v in resA.items() if k != "lightgbm" and v["falso_alarme"] <= fa_lgbm}
    escolhida = max(elegiveis, key=lambda k: elegiveis[k]["iou"]) if elegiveis else "lightgbm"
    resB = {k: avalia(B, regras[k]) for k in dict.fromkeys(("lightgbm", "unet@0.5", "media@0.55", "and@0.5", escolhida))}
    import numpy as _np
    from scipy.ndimage import binary_opening as _bo
    resB["baseline"] = avalia(B, lambda d: d["base"])
    out = dict(protocolo=f"Seleção em {len(A)} blocos (A), relatório em {len(B)} blocos (B); blocos de 5 km nunca vistos pela U-Net; parede a parede. "
                         "Critério: maior IoU em A com falso alarme ≤ LightGBM em A.",
               escolhida=escolhida, blocos_A=[d["b"] for d in A], blocos_B=[d["b"] for d in B],
               selecao_A={k: {m: round(v[m], 4) for m in ("iou", "f1", "precisao", "recall", "falso_alarme")} for k, v in resA.items()},
               teste_B=resB)
    (DL / "regra_operacional.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("escolhida:", escolhida)
    for k, v in resB.items():
        print(f"B {k:12s} IoU {v['iou']:.3f} F1 {v['f1']:.3f} P {v['precisao']:.3f} R {v['recall']:.3f} falso_alarme {v['falso_alarme']:.3f}")


if __name__ == "__main__":
    main()



