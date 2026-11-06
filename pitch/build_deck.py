"""Gera pitch/deck.html (autocontido) a partir de pitch/deck.template.html e dos artefatos reais.

    uv run python pitch/build_deck.py

Números ausentes viram o marcador visível "[a preencher]". AUTEX são mascarados (7 primeiros + ••••• + 2 últimos).
"""
from __future__ import annotations

import base64
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "data" / "artifacts"
SCREENS = ROOT / "tests" / "web" / "screens"
FILL = '<span class="fill">[a preencher]</span>'


def br(x, nd=0):
    s = f"{x:,.{nd}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x, nd=0):
    return br(100 * x, nd) + "%"


def load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def mask(autex: str) -> str:
    a = str(autex)
    if a.upper().startswith("SIM-"):
        return "SIM-" + mask(a[4:])
    if len(a) <= 9:
        return a[:2] + "•••••" + a[-2:]
    return a[:7] + "•••••" + a[-2:]


def img_tag(path: Path, alt: str) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f'<img alt="{alt}" src="data:image/png;base64,{b64}">'


def pick_screens():
    """Prefere screenshots reais (sem prefixo mock-) mais recentes."""
    if not SCREENS.exists():
        return None, None, True
    pngs = sorted(SCREENS.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    real = [p for p in pngs if not p.name.startswith("mock-")]
    pool = real or pngs
    is_mock = not real

    def find(*keys):
        for k in keys:
            for p in pool:
                if k in p.name:
                    return p
        return None

    dossie = find("dossie-a-evidencia", "dossie-a", "dossie")
    triagem = find("triagem")
    return dossie or (pool[0] if pool else None), triagem, is_mock


# ------------------------------------------------------------------ SVGs
def svg_cover():
    import random
    rnd = random.Random(7)
    cell, n = 58, 9
    out = [f'<svg width="{cell*n+40}" height="{cell*n+40}" viewBox="0 0 {cell*n+40} {cell*n+40}" aria-hidden="true">']
    out.append(f'<path d="M30 70 L{cell*n-10} 20 L{cell*n+20} {cell*n-30} L80 {cell*n+20} Z" fill="none" stroke="#c5f67c" stroke-width="4"/>')
    for i in range(n):
        for j in range(n):
            x, y = 20 + i * cell, 20 + j * cell
            r = rnd.random()
            if r < 0.22:
                fill, op = "#c5f67c", 0.85
            elif r < 0.30:
                fill, op = "#ff9a7a", 0.0
            else:
                fill, op = "#2e5443", 0.55
            if op:
                out.append(f'<rect x="{x+3}" y="{y+3}" width="{cell-6}" height="{cell-6}" rx="5" fill="{fill}" opacity="{op}"/>')
            else:
                out.append(f'<rect x="{x+5}" y="{y+5}" width="{cell-10}" height="{cell-10}" rx="5" fill="none" stroke="{fill}" stroke-width="4" stroke-dasharray="9 7"/>')
            if r < 0.30 or rnd.random() < 0.12:
                for _ in range(rnd.randint(1, 3)):
                    out.append(f'<circle cx="{x+rnd.uniform(14,cell-14):.0f}" cy="{y+rnd.uniform(14,cell-14):.0f}" r="5" fill="#f3f4e8"/>')
    out.append("</svg>")
    return "".join(out)


def svg_cells():
    cell, n = 74, 6
    lime = {(1, 1), (2, 1), (1, 2), (4, 4), (4, 3), (3, 4), (0, 4)}
    ghost = {(3, 0), (4, 0), (4, 1), (5, 1), (5, 0)}
    w = cell * n + 8
    out = [f'<svg width="{w}" height="{w}" viewBox="0 0 {w} {w}" aria-hidden="true">']
    for i in range(n):
        for j in range(n):
            x, y = 4 + i * cell, 4 + j * cell
            if (i, j) in lime:
                out.append(f'<rect x="{x+4}" y="{y+4}" width="{cell-8}" height="{cell-8}" rx="6" fill="#c5f67c" opacity=".9"/>')
            elif (i, j) in ghost:
                out.append(f'<rect x="{x+6}" y="{y+6}" width="{cell-12}" height="{cell-12}" rx="6" fill="none" stroke="#ff9a7a" stroke-width="4" stroke-dasharray="10 8"/>')
            else:
                out.append(f'<rect x="{x+4}" y="{y+4}" width="{cell-8}" height="{cell-8}" rx="6" fill="#2e5443" opacity=".6"/>')
    pts = [(1, 1, .3, .4), (1, 1, .7, .6), (2, 1, .5, .5), (1, 2, .4, .6), (4, 4, .5, .4), (4, 3, .3, .7), (3, 4, .6, .5), (0, 4, .5, .5),
           (3, 0, .3, .3), (3, 0, .7, .6), (4, 0, .5, .5), (4, 1, .4, .3), (4, 1, .7, .7), (5, 1, .5, .5), (5, 0, .3, .6), (5, 0, .7, .3)]
    for i, j, a, b in pts:
        out.append(f'<circle cx="{4+i*cell+a*cell:.0f}" cy="{4+j*cell+b*cell:.0f}" r="8" fill="#f3f4e8"/>')
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------------ dados
def detector_vals():
    d = load(ART / "metrics" / "detector.json")
    v = {}
    if not d:
        return v
    m = {x["nome"]: x for x in d["modelos"]}
    lg, bs = m.get("lightgbm"), m.get("baseline-otsu")
    if lg:
        v.update(DET_IOU=br(lg["iou"], 2), DET_F1=br(lg["f1"], 2), DET_IOU_W=f"{100*lg['iou']:.1f}", DET_F1_W=f"{100*lg['f1']:.1f}",
                 DET_NPX=br(lg["n_pixels_teste"]))
        obs = lg.get("obs") or ""
        k0 = obs.find("{", obs.find("Por tipo")) if "Por tipo" in obs else -1
        if k0 >= 0:
            depth = 0
            for k in range(k0, len(obs)):
                depth += obs[k] == "{"
                depth -= obs[k] == "}"
                if depth == 0:
                    s = json.loads(obs[k0:k + 1])
                    v.update(F1_RASO=br(s["corte_raso"]["f1"], 2), F1_SEL=br(s["seletivo_degradacao"]["f1"], 2))
                    break
    if bs:
        v.update(BAS_IOU=br(bs["iou"], 2), BAS_F1=br(bs["f1"], 2), BAS_IOU_W=f"{100*bs['iou']:.1f}", BAS_F1_W=f"{100*bs['f1']:.1f}")
    return v


def calib_vals():
    c = load(ART / "metrics" / "calibracao.json")
    if not c or c.get("cobertura_p10_p90") is None or "MOCK" in str(c.get("obs", "")):
        return {"COB": FILL, "COB_W": "0", "COB_TXT": "Aguardando a calibração de volume (GroupKFold por UPA). O valor nominal é 80%."}
    cov = float(c["cobertura_p10_p90"])
    nom = float(c.get("cobertura_nominal", 0.8))
    antes = re.search(r"cobertura \[p10,p90\] (\d+)% antes", c.get("obs") or "")
    upa = re.search(r"UPA \(Monte Carlo[^)]*\):.*?cobertura (\d+)% antes e (\d+)% após", c.get("obs") or "")
    txt = (f"Em {br(c['n_upas'])} UPAs fora do treino ({br(c['n_celulas_treino'])} células), o volume declarado caiu dentro da faixa "
           f"em {pct(cov)} das células, para {pct(nom)} esperados")
    if antes:
        txt += f" ({antes.group(1)}% antes do ajuste conformal)"
    txt += "."
    if upa:
        txt += f" No total da UPA: {upa.group(2)}%."
    err = re.search(r"erro relativo mediano (\d+)%", c.get("obs") or "")
    if err:
        txt += f" O erro relativo mediano do total da UPA é de {err.group(1)}%, por isso a decisão usa o intervalo e não o ponto."
    return {"COB": pct(cov), "COB_W": f"{100*cov:.1f}", "COB_TXT": txt}


def dl_vals():
    z = ROOT / "lastro_dl_resultados.zip"
    try:
        m = json.loads(zipfile.ZipFile(z).read("metrics_dl.json"))
        return {"DL_IOU": br(m["iou"], 2)}
    except Exception:
        return {"DL_IOU": "[a preencher]"}


MIN_INDEX_TS = "2026-11-06T04:20"  # só usar index regenerado após a correção da flag B (pedido do orquestrador)


def index_vals():
    idx = load(ART / "index.json")
    if idx and str(idx.get("gerado_em", "")) < MIN_INDEX_TS:
        print("index.json", idx.get("gerado_em"), "anterior a", MIN_INDEX_TS, "-> marcadores")
        idx = None
    if not idx:
        return {"K_AVALIADAS": "1.142", "K_IMAGEM": FILL, "K_INDICIO": "1,87 mi m³",
                "K_INDICIO_LBL": "declarados no IF100 (2022+) confrontados com as regras documentais",
                "TOP_TABLE": f'<p class="rule" style="margin-top:40px">Ranking dos casos de maior prioridade: {FILL} (aguardando data/artifacts/index.json)</p>',
                "SRC_RESULTADOS": "Regras documentais: data/processed/regras_doc.parquet · casos com imagem: data/artifacts/index.json (pendente)"}, None
    t = idx.get("totais", {})
    casos = idx.get("casos", [])
    real = [c for c in casos if c.get("source_mode") == "real"]
    n_av = t.get("autorizacoes_avaliadas", len(real))
    n_img = t.get("com_imagem", sum(1 for c in real if c.get("analise_imagem")))
    n_ind = t.get("com_indicio", sum(1 for c in real if any(f["status"] == "indicio" for f in c.get("flags", []))))
    rows = []
    top = sorted(casos, key=lambda c: -c["score"])
    top = [c for c in top if any(f["status"] == "indicio" for f in c.get("flags", []))][:4]
    for c in top:
        fl = "".join(f'<span class="fl">{f["codigo"]}</span>' for f in c["flags"] if f["status"] == "indicio")
        sim = '<span class="sim">SIMULAÇÃO</span>' if c.get("source_mode") == "simulado" else ""
        mun = str(c.get("municipio", "")).title().replace(" Do ", " do ").replace(" De ", " de ")
        img = "imagem" if c.get("analise_imagem") else "documental"
        rows.append(f'<tr><td class="mask">{mask(c["autex"])}{sim}</td><td>{c["tipo"]}</td><td>{mun} / {c["uf"]}</td>'
                    f'<td>{img}</td><td>{fl}</td><td class="sc">{round(100*c["score"])}</td></tr>')
    table = ('<table class="top"><thead><tr><th>Autorização</th><th>Tipo</th><th>Município</th><th>Análise</th><th>Indícios</th>'
             '<th style="text-align:right">Prioridade</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>")
    gen = str(idx.get("gerado_em", ""))[:10]
    a_inc = sum(1 for c in casos for f in c.get("flags", []) if f["codigo"] == "A" and f["status"] == "inconclusivo")
    a_ind = sum(1 for c in casos for f in c.get("flags", []) if f["codigo"] == "A" and f["status"] == "indicio")
    vol = t.get("volume_declarado_total_m3")
    k4 = (br(vol / 1e6, 2) + " mi m³") if vol else FILL
    note = (f'<p class="rule" style="margin-top:20px;font-size:25px;padding:12px 24px">Assinatura A: {a_ind} indício e {a_inc} <b>inconclusivos</b>. '
            f'Há células sem lastro, mas o total da UPA fica dentro do p90 da imagem. É motivo para olhar, não para concluir.</p>') if (a_inc or a_ind) else ""
    return {"K_AVALIADAS": br(n_av), "K_IMAGEM": br(n_img), "K_INDICIO": k4,
            "K_INDICIO_LBL": f"declarados no IF100 (2022+) confrontados; {br(n_ind)} autorizações com ao menos um indício",
            "TOP_TABLE": table + note,
            "SRC_RESULTADOS": f"data/artifacts/index.json (gerado em {gen}) · AUTEX mascarado · prioridade = score de triagem × 100, não é probabilidade"}, idx


def main():
    tpl = (ROOT / "pitch" / "deck.template.html").read_text(encoding="utf-8")
    vals = {"SVG_COVER": svg_cover(), "SVG_CELLS": svg_cells()}
    vals.update(detector_vals())
    vals.update(calib_vals())
    vals.update(dl_vals())
    iv, _ = index_vals()
    vals.update(iv)
    dossie, _, is_mock = pick_screens()
    if dossie:
        vals["IMG_DOSSIE"] = img_tag(dossie, "Dossiê do Lastro")
        vals["CAP_DOSSIE"] = ("Tela do dossiê com dados de demonstração (mock), marcada como SIMULAÇÃO." if is_mock
                              else "Dossiê de um caso real do polo AMACRO.")
    else:
        vals["IMG_DOSSIE"] = f'<div style="padding:200px;text-align:center">{FILL}</div>'
        vals["CAP_DOSSIE"] = "Screenshot do dossiê pendente."
    out = tpl
    for k, v in vals.items():
        out = out.replace("{{" + k + "}}", str(v))
    left = sorted(set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", out)))
    for k in left:
        out = out.replace("{{" + k + "}}", FILL if not k.endswith("_W") else "0")
    (ROOT / "pitch" / "deck.html").write_text(out, encoding="utf-8")
    print("deck.html ok;", "screens:", dossie.name if dossie else None, "mock" if is_mock else "real", "; pendentes:", left or "nenhum")


if __name__ == "__main__":
    main()
