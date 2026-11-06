"""Registra a avaliação independente U-Net × LightGBM e a regra operacional em metrics/detector.json e dl.json.

Fonte: data/processed/dl/regra_operacional.json (pipeline/detect/calibrar_dl.py): blocos de 5 km nunca vistos pela
U-Net, divididos em metade A (escolha da regra) e metade B (medição). Todas as entradas [Local 5 km] são da metade B,
nos mesmos pixels, parede a parede. Uso: uv run python scripts/integrar_unet.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contracts.models import MetricsDetector  # noqa: E402

MET = ROOT / "data/artifacts/metrics"
regra = json.loads((ROOT / "data/processed/dl/regra_operacional.json").read_text(encoding="utf-8"))
av = json.loads((ROOT / "data/processed/dl/avaliacao_local.json").read_text(encoding="utf-8"))
tb, nb = regra["teste_B"], len(regra["blocos_B"])
base = (f"Teste em {nb} blocos de 5 km nunca vistos pela U-Net e não usados para escolher a regra (metade B); "
        "todos os pixels rotulados, mesmos pixels para todos os métodos; LightGBM = modelo do fold em que o bloco foi teste. "
        f"Falso alarme = fração da floresta estável marcada como distúrbio. ")
spec = [
    ("and@0.5", "[Local 5 km] LightGBM + U-Net (AND)",
     "Regra operacional: distúrbio se LightGBM ≥ limiar E U-Net ≥ 0,5. Prioriza precisão porque casos acima do limiar geram comunicação ao IBAMA."),
    ("unet@0.5", "[Local 5 km] U-Net siamesa",
     f"Deep learning sozinho: maior IoU, mas falso alarme alto e manchas em dossel intacto de florestas manejadas sem alerta. "
     f"Nos {av['n_blocos']} blocos completos venceu o LightGBM em IoU em {av['blocos_unet_vence']}."),
    ("media@0.55", "[Local 5 km] Média U-Net/LightGBM ≥ 0,55", "Alternativa de maior recall; limiar escolhido na metade A. Não adotada pelo falso alarme."),
    ("lightgbm", "[Local 5 km] LightGBM", "Detector anterior (mesmo modelo/limiar do GroupKFold local)."),
    ("baseline", "[Local 5 km] ΔNDVI + Otsu", "Baseline sem treino."),
]
novos = []
for chave, nome, extra in spec:
    m = tb[chave]
    novos.append({**{k: m[k] for k in ("iou", "f1", "precisao", "recall", "matriz_confusao", "n_pixels_teste")},
                  "nome": nome, "obs": base + f"Falso alarme {m['falso_alarme']:.1%}. " + extra})

det = json.loads((MET / "detector.json").read_text(encoding="utf-8"))
det["modelos"] = [m for m in det["modelos"] if not m["nome"].startswith("[Local 5 km]")]
det["modelos"] = det["modelos"][:2] + novos + det["modelos"][2:]
det["selecionado"] = spec[0][1]
det["protocolo"] = (det["protocolo"].split(" | ")[0]
                    + " | [Local 5 km]: blocos nunca vistos pela U-Net; regra escolhida na metade A e medida na metade B "
                    "(pipeline/detect/avaliar_dl.py, calibrar_dl.py)."
                    + " | [Colab]: segundo protocolo independente (blocos de 25 km)."
                    + " | Operacional: LightGBM confirmado pela U-Net siamesa (AND) na detecção espacial; LightGBM como insumo da calibração de volume.")
MetricsDetector.model_validate(det)
(MET / "detector.json").write_text(json.dumps(det, ensure_ascii=False, indent=2), encoding="utf-8")

dl = json.loads((MET / "dl.json").read_text(encoding="utf-8"))
dl["avaliacao_local"] = {k: av[k] for k in ("protocolo", "n_blocos", "blocos_excluidos_vistos", "blocos_unet_vence", "resultados")}
dl["regra_operacional"] = {"regra": "LightGBM ≥ limiar E U-Net ≥ 0,5", "blocos_B": nb,
                           "teste_B": {k: {m: v[m] for m in ("iou", "f1", "precisao", "recall", "falso_alarme")} for k, v in tb.items()}}
dl["status"] = "em uso: confirma a detecção do LightGBM (regra AND), ONNX Runtime em CPU"
for dest in (MET / "dl.json", ROOT / "web/public/dl/dl.json"):
    dest.write_text(json.dumps(dl, ensure_ascii=False, indent=1), encoding="utf-8")
print("ok", [m["nome"] for m in det["modelos"]])

