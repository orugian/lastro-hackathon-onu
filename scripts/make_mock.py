"""Gera data/artifacts-mock com 2 casos fictícios (POA e ASV) válidos pelo contrato v1.
Uso: uv run python scripts/make_mock.py
"""
from __future__ import annotations

import json
import math
import random
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contracts.models import (  # noqa: E402
    CaseSummary, CelulaProps, Dossier, Index, MetricsCalibracao, MetricsDetector,
)

OUT = ROOT / "data" / "artifacts-mock"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
rng = random.Random(7)
nrng = np.random.default_rng(7)

DEG_M = 111_320.0


def rect(lon0, lat0, w_m, h_m):
    dx = w_m / (DEG_M * math.cos(math.radians(lat0)))
    dy = h_m / DEG_M
    return [[lon0, lat0], [lon0 + dx, lat0], [lon0 + dx, lat0 + dy], [lon0, lat0 + dy], [lon0, lat0]], (lon0, lat0, lon0 + dx, lat0 + dy)


def fc(features):
    return {"type": "FeatureCollection", "features": features}


def feat(geom, props):
    return {"type": "Feature", "geometry": geom, "properties": props}


def write_json(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def forest_png(path: Path, size, clearings, cloud=False, roads=()):
    """RGB sintético: floresta texturizada + clareiras (solo) + estradas."""
    h, w = size
    g = nrng.normal(0, 1, (h, w))
    base = np.stack([30 + 8 * g, 70 + 14 * g, 35 + 8 * g], -1)
    yy, xx = np.mgrid[0:h, 0:w]
    for (cx, cy, r) in clearings:
        m = (xx - cx) ** 2 + (yy - cy) ** 2 < r ** 2
        base[m] = [150, 120, 85]
    for (x0, y0, x1, y1) in roads:
        n = int(max(abs(x1 - x0), abs(y1 - y0)))
        for t in np.linspace(0, 1, n):
            x, y = int(x0 + t * (x1 - x0)), int(y0 + t * (y1 - y0))
            base[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = [170, 140, 100]
    if cloud:
        m = ((xx - w * 0.8) ** 2 + (yy - h * 0.2) ** 2) < (w * 0.12) ** 2
        base[m] = [235, 235, 235]
    Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).save(path)


def diff_png(path: Path, size, clearings):
    h, w = size
    a = np.zeros((h, w, 4), np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]
    for (cx, cy, r) in clearings:
        m = (xx - cx) ** 2 + (yy - cy) ** 2 < r ** 2
        a[m] = [220, 40, 40, 200]
    Image.fromarray(a, "RGBA").save(path)


def prov():
    return [
        {"id": "pamgia", "fonte": "IBAMA PAMGIA - Polígonos Sinaflor", "url": "https://pamgia.ibama.gov.br/server/rest/services/SINAFLORGEO/sinaflor_proj_externo_merge_a/FeatureServer/6", "consultado_em": NOW, "versao": None, "licenca": "Dados abertos"},
        {"id": "if100", "fonte": "IBAMA - Volumes Explorados IF100", "url": "https://dadosabertos.ibama.gov.br/dataset/volumes-explorados-if-100", "consultado_em": NOW, "versao": "2026-10-08", "licenca": "Dados abertos"},
        {"id": "s2", "fonte": "Copernicus Sentinel-2 L2A via Google Earth Engine", "url": "https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED", "consultado_em": NOW, "versao": None, "licenca": "Copernicus open"},
        {"id": "deter", "fonte": "INPE DETER (TerraBrasilis)", "url": "https://terrabrasilis.dpi.inpe.br/geoserver/ows", "consultado_em": NOW, "versao": None, "licenca": "CC-BY-SA"},
    ]


def make_poa():
    autex = "MOCK-POA-0001"
    d = OUT / "cases" / autex
    (d / "img").mkdir(parents=True, exist_ok=True)
    lon0, lat0 = -63.10, -7.62
    upa_ring, upa_bbox = rect(lon0, lat0, 3000, 2000)  # 600 ha
    buf_ring, buf_bbox = rect(lon0 - 0.018, lat0 - 0.018, 7000, 6000)
    write_json(d / "upa.geojson", fc([feat({"type": "Polygon", "coordinates": [upa_ring]}, {"autex": autex, "area_ha": 600.0})]))
    write_json(d / "buffer.geojson", fc([feat({"type": "Polygon", "coordinates": [buf_ring]}, {"buffer_m": 2000})]))

    # células 100 m sobre a UPA (30 x 20) + uma faixa fora
    cells, trees = [], []
    dxc = 100 / (DEG_M * math.cos(math.radians(lat0)))
    dyc = 100 / DEG_M
    k = 0
    for i in range(-5, 35):
        for j in range(-4, 24):
            inside = 0 <= i < 30 and 0 <= j < 20
            x, y = lon0 + i * dxc, lat0 + j * dyc
            ring = [[x, y], [x + dxc, y], [x + dxc, y + dyc], [x, y + dyc], [x, y]]
            n = 0
            vol = 0.0
            dist = None
            classe = "sem_atividade"
            if inside:
                n = nrng.poisson(1.2)
                if 20 <= i < 26 and 5 <= j < 12:  # bloco "sem lastro": muito declarado, sem distúrbio
                    n = nrng.poisson(6)
                vol = float(sum(rng.uniform(3, 9) for _ in range(n)))
                dist = float(np.clip(0.012 * n + nrng.normal(0, 0.01), 0, 1)) if not (20 <= i < 26 and 5 <= j < 12) else float(abs(nrng.normal(0.004, 0.003)))
                classe = "consistente" if n > 0 else "sem_atividade"
                if 20 <= i < 26 and 5 <= j < 12:
                    classe = "sem_lastro"
            else:
                dist = 0.0
                if -4 <= i < -1 and 3 <= j < 9:  # distúrbio fora da UPA
                    dist = float(rng.uniform(0.15, 0.4))
                    classe = "nao_declarado"
            if inside and i < 3 and j > 16:
                classe, dist = "nao_observavel", None
            if classe == "sem_atividade" and not inside and dist == 0.0:
                continue
            p50 = None if dist is None else round(dist * 160, 2)
            props = CelulaProps(
                id=f"c{k}", vol_declarado=round(vol, 2), n_arvores=int(n), disturbio_frac=None if dist is None else round(dist, 4),
                vol_p10=None if p50 is None else round(p50 * 0.55, 2), vol_p50=p50, vol_p90=None if p50 is None else round(p50 * 1.7, 2),
                classe=classe, dentro_upa=inside,
            )
            cells.append(feat({"type": "Polygon", "coordinates": [ring]}, props.model_dump()))
            for t in range(n):
                trees.append(feat({"type": "Point", "coordinates": [x + rng.random() * dxc, y + rng.random() * dyc]}, {
                    "id": f"t{len(trees)}", "especie": rng.choice(["Dipteryx odorata", "Hymenaea courbaril", "Manilkara elata", "Goupia glabra"]),
                    "vol_autorizado": round(rng.uniform(3, 9), 2), "vol_explorado": round(rng.uniform(3, 9), 2),
                    "data_exploracao": f"2024-{rng.randint(7, 10):02d}-{rng.randint(1, 28):02d}", "dentro_upa": True}))
            k += 1
    # 2 árvores fora (flag C)
    for t in range(2):
        trees.append(feat({"type": "Point", "coordinates": [lon0 - 0.006 - t * 0.001, lat0 + 0.004]}, {
            "id": f"tf{t}", "especie": "Dipteryx odorata", "vol_autorizado": 6.1, "vol_explorado": 7.9, "data_exploracao": "2024-08-12", "dentro_upa": False}))
    write_json(d / "celulas.geojson", fc(cells))
    write_json(d / "arvores.geojson", fc(trees))

    mud_ring, _ = rect(lon0 - 4 * dxc, lat0 + 3 * dyc, 300, 600)
    write_json(d / "mudanca.geojson", fc([feat({"type": "Polygon", "coordinates": [mud_ring]}, {"id": "m0", "area_ha": 5.4, "prob": 0.86, "dentro_upa": False, "dist_limite_m": 180.0, "data_inicio": "2024-06-01", "data_fim": "2024-09-30", "metodo": "lightgbm"})]))
    write_json(d / "deter.geojson", fc([feat({"type": "Polygon", "coordinates": [mud_ring]}, {"classe": "CS_DESORDENADO", "data": "2024-08-21", "area_ha": 4.9})]))
    write_json(d / "prodes.geojson", fc([]))

    b = buf_bbox
    size = (300, 350)
    clear = [(nrng.integers(80, 300), nrng.integers(60, 240), nrng.integers(2, 5)) for _ in range(60)]
    forest_png(d / "img" / "s2_pre.png", size, [])
    forest_png(d / "img" / "s2_pos.png", size, clear + [(55, 130, 14)], roads=[(60, 150, 300, 150)])
    diff_png(d / "img" / "dndvi.png", size, clear + [(55, 130, 14)])
    forest_png(d / "img" / "cbers_pre.png", size, [])
    forest_png(d / "img" / "cbers_pos.png", size, clear + [(55, 130, 14)], roads=[(60, 150, 300, 150)])

    vol_aut = 13850.0
    vol_dec = round(sum(f["properties"]["vol_explorado"] for f in trees), 1)
    summary = dict(
        autex=autex, tipo="POA", uf="AM", municipio="HUMAITA (MOCK)",
        centroide=((upa_bbox[0] + upa_bbox[2]) / 2, (upa_bbox[1] + upa_bbox[3]) / 2), bbox=b,
        area_autorizada_ha=600.0, validade={"inicio": "2024-05-10", "fim": "2025-05-10"}, situacao="Autorização Emitida",
        volume_autorizado_m3=vol_aut, volume_declarado_explorado_m3=vol_dec,
        volume_estimado_m3={"p10": 2100.0, "p50": 3150.0, "p90": 4600.0},
        area_disturbio_ha=48.2, area_disturbio_fora_ha=5.4, n_arvores_declaradas=len(trees),
        flags=[
            {"codigo": "A", "titulo": "Volume declarado sem lastro observável", "status": "indicio", "severidade": "alta", "confianca": 0.72},
            {"codigo": "B", "titulo": "Distúrbio fora da UPA sem declaração", "status": "indicio", "severidade": "alta", "confianca": 0.81},
            {"codigo": "C", "titulo": "Árvores declaradas fora do polígono", "status": "indicio", "severidade": "media", "confianca": 0.95},
            {"codigo": "D", "titulo": "Volume explorado acima do autorizado", "status": "sem_indicio", "severidade": "info", "confianca": 0.9},
            {"codigo": "E", "titulo": "Exploração fora da validade", "status": "sem_indicio", "severidade": "info", "confianca": 0.95},
        ],
        score=0.83, source_mode="simulado", analise_imagem=True, processado_em=NOW,
    )
    CaseSummary(**summary)
    dossier = dict(summary,
        flags_detalhe=[
            {**summary["flags"][0], "regra": "Σ volume declarado nas células > p90 do volume compatível com o distúrbio observado (calibração IF100), em ≥ 10 células contíguas",
             "evidencias": [
                 {"tipo": "metrica", "descricao": "Volume declarado no bloco sem distúrbio compatível", "valor": 1240.0, "unidade": "m³", "camada": "celulas", "filtro": {"classe": "sem_lastro"}, "fonte": "if100"},
                 {"tipo": "metrica", "descricao": "Volume compatível com a imagem no mesmo bloco (p90)", "valor": 310.0, "unidade": "m³", "fonte": "s2"},
                 {"tipo": "imagem", "descricao": "Dossel intacto entre as datas pré e pós no bloco destacado", "camada": "cbers_pos"}],
             "volume_m3": {"p10": 780.0, "p50": 930.0, "p90": 1060.0}},
            {**summary["flags"][1], "regra": "Polígono de distúrbio (prob ≥ 0,5) fora da UPA, a mais de 20 m do limite, sem autorização vizinha",
             "evidencias": [{"tipo": "geometria", "descricao": "5,4 ha de distúrbio a 180 m do limite, coincidente com alerta DETER CS_DESORDENADO de 21/08/2024", "valor": 5.4, "unidade": "ha", "camada": "mudanca", "fonte": "deter"}],
             "volume_m3": {"p10": 60.0, "p50": 105.0, "p90": 170.0}, "area_ha": 5.4},
            {**summary["flags"][2], "regra": "Coordenada IF100 a mais de 20 m fora do polígono autorizado",
             "evidencias": [{"tipo": "geometria", "descricao": "2 árvores declaradas como exploradas fora da UPA (14,0 m³)", "valor": 2, "unidade": "árvores", "camada": "arvores", "filtro": {"dentro_upa": False}, "fonte": "if100"}]},
            {**summary["flags"][3], "regra": "Σ explorado ≤ autorizado e intensidade ≤ 30 m³/ha", "evidencias": [{"tipo": "metrica", "descricao": "Intensidade declarada", "valor": round(vol_dec / 600, 1), "unidade": "m³/ha", "fonte": "if100"}]},
            {**summary["flags"][4], "regra": "Todas as datas de exploração dentro de [início, fim] da validade", "evidencias": []},
        ],
        imagens=[
            {"id": "s2_pre", "sensor": "Sentinel-2", "rotulo": "Sentinel-2 · mediana jun–set 2023", "data": "2023-06-01/2023-09-30", "png": "img/s2_pre.png", "bounds": b, "resolucao_m": 10, "nuvem_pct": 2.1, "par": "pre"},
            {"id": "s2_pos", "sensor": "Sentinel-2", "rotulo": "Sentinel-2 · mediana out–dez 2024", "data": "2024-10-01/2024-12-31", "png": "img/s2_pos.png", "bounds": b, "resolucao_m": 10, "nuvem_pct": 8.4, "par": "pos"},
            {"id": "dndvi", "sensor": "Derivado", "rotulo": "Distúrbio detectado (LightGBM)", "data": None, "png": "img/dndvi.png", "bounds": b, "resolucao_m": 10, "nuvem_pct": None, "par": None},
            {"id": "cbers_pre", "sensor": "CBERS-4A WPM", "rotulo": "CBERS-4A WPM 2 m · 2023-08-17", "data": "2023-08-17", "png": "img/cbers_pre.png", "bounds": b, "resolucao_m": 2, "nuvem_pct": 0.0, "par": "pre"},
            {"id": "cbers_pos", "sensor": "CBERS-4A WPM", "rotulo": "CBERS-4A WPM 2 m · 2024-11-11", "data": "2024-11-11", "png": "img/cbers_pos.png", "bounds": b, "resolucao_m": 2, "nuvem_pct": 3.0, "par": "pos"},
        ],
        camadas=["upa", "buffer", "arvores", "celulas", "mudanca", "deter", "prodes"],
        especies=[
            {"nome_cientifico": "Dipteryx odorata", "nome_popular": "Cumaru", "volume_autorizado_m3": 4200.0, "volume_explorado_m3": 1210.0, "n_arvores": 190},
            {"nome_cientifico": "Hymenaea courbaril", "nome_popular": "Jatobá", "volume_autorizado_m3": 3900.0, "volume_explorado_m3": 1100.0, "n_arvores": 180},
            {"nome_cientifico": "Manilkara elata", "nome_popular": "Maçaranduba", "volume_autorizado_m3": 3150.0, "volume_explorado_m3": 1050.0, "n_arvores": 170},
            {"nome_cientifico": "Goupia glabra", "nome_popular": "Cupiúba", "volume_autorizado_m3": 2600.0, "volume_explorado_m3": 990.0, "n_arvores": 160},
        ],
        parametros_volume=[
            {"nome": "m³ por fração de distúrbio (célula 1 ha)", "distribuicao": "quantis LightGBM q10/q50/q90", "valor": 160.0, "unidade": "m³/ha", "origem": "calibração IF100 · 412 UPAs sem indício"},
            {"nome": "Tolerância de borda", "distribuicao": "fixo", "valor": 20.0, "unidade": "m", "origem": "2 pixels Sentinel-2"},
        ],
        modelo={"detector": "lightgbm-v1 (mock)", "calibracao": "lgbm-quantil-v1 (mock)"},
        proveniencia=prov(),
        limitacoes=[
            "Clareiras de árvore isolada (200–600 m²) são parcialmente visíveis em 10 m e fecham em meses; o indício A é agregado por célula, nunca por árvore.",
            "Nuvem: 3% da AOI não observável (classe nao_observavel).",
            "Dados MOCK para desenvolvimento - não representam autorização real.",
        ],
        linha_do_tempo=[
            {"data": "2024-05-10", "evento": "Início da validade do POA", "fonte": "pamgia"},
            {"data": "2024-07-03", "evento": "Primeira árvore declarada como explorada", "fonte": "if100"},
            {"data": "2024-08-21", "evento": "Alerta DETER CS_DESORDENADO fora da UPA", "fonte": "deter"},
            {"data": "2024-10-28", "evento": "Última árvore declarada como explorada", "fonte": "if100"},
            {"data": "2025-05-10", "evento": "Fim da validade", "fonte": "pamgia"},
        ],
    )
    Dossier(**dossier)
    write_json(d / "dossier.json", dossier)
    return summary


def make_asv():
    autex = "MOCK-ASV-0001"
    d = OUT / "cases" / autex
    (d / "img").mkdir(parents=True, exist_ok=True)
    lon0, lat0 = -63.85, -8.95
    upa_ring, upa_bbox = rect(lon0, lat0, 1500, 1000)  # 150 ha
    buf_ring, buf_bbox = rect(lon0 - 0.018, lat0 - 0.018, 5500, 5000)
    write_json(d / "upa.geojson", fc([feat({"type": "Polygon", "coordinates": [upa_ring]}, {"autex": autex, "area_ha": 150.0})]))
    write_json(d / "buffer.geojson", fc([feat({"type": "Polygon", "coordinates": [buf_ring]}, {"buffer_m": 2000})]))
    in_ring, _ = rect(lon0, lat0, 1500, 1000)
    out_ring, _ = rect(lon0 + 1500 / (DEG_M * math.cos(math.radians(lat0))), lat0 + 0.002, 600, 700)
    write_json(d / "mudanca.geojson", fc([
        feat({"type": "Polygon", "coordinates": [in_ring]}, {"id": "m0", "area_ha": 148.0, "prob": 0.97, "dentro_upa": True, "dist_limite_m": 0.0, "data_inicio": "2024-06-01", "data_fim": "2024-09-30", "metodo": "lightgbm"}),
        feat({"type": "Polygon", "coordinates": [out_ring]}, {"id": "m1", "area_ha": 42.0, "prob": 0.93, "dentro_upa": False, "dist_limite_m": 310.0, "data_inicio": "2024-06-01", "data_fim": "2024-09-30", "metodo": "lightgbm"}),
    ]))
    for n in ("celulas", "arvores", "deter"):
        write_json(d / f"{n}.geojson", fc([]))
    write_json(d / "prodes.geojson", fc([feat({"type": "Polygon", "coordinates": [out_ring]}, {"classe": "d2024", "area_ha": 40.1})]))
    b = buf_bbox
    size = (300, 330)
    forest_png(d / "img" / "s2_pre.png", size, [])
    big = [(150 + dx, 150 + dy, 9) for dx in range(-40, 41, 12) for dy in range(-25, 26, 12)] + [(235 + dx, 135 + dy, 9) for dx in range(-10, 11, 10) for dy in range(-15, 16, 10)]
    forest_png(d / "img" / "s2_pos.png", size, big)
    diff_png(d / "img" / "dndvi.png", size, big)
    summary = dict(
        autex=autex, tipo="ASV", uf="RO", municipio="PORTO VELHO (MOCK)",
        centroide=((upa_bbox[0] + upa_bbox[2]) / 2, (upa_bbox[1] + upa_bbox[3]) / 2), bbox=b,
        area_autorizada_ha=150.0, validade={"inicio": "2024-03-01", "fim": "2025-03-01"}, situacao="Autorização Emitida",
        volume_autorizado_m3=3300.0, volume_declarado_explorado_m3=3280.0,
        volume_estimado_m3={"p10": 3600.0, "p50": 4180.0, "p90": 4900.0},
        area_disturbio_ha=190.0, area_disturbio_fora_ha=42.0, n_arvores_declaradas=None,
        flags=[
            {"codigo": "B", "titulo": "Corte raso fora do polígono autorizado", "status": "indicio", "severidade": "alta", "confianca": 0.93},
            {"codigo": "F2", "titulo": "Área desmatada acima da autorizada", "status": "indicio", "severidade": "alta", "confianca": 0.88},
            {"codigo": "D", "titulo": "Volume estimado acima do autorizado", "status": "indicio", "severidade": "media", "confianca": 0.7},
            {"codigo": "E", "titulo": "Desmatamento fora da validade", "status": "sem_indicio", "severidade": "info", "confianca": 0.8},
        ],
        score=0.77, source_mode="simulado", analise_imagem=True, processado_em=NOW,
    )
    CaseSummary(**summary)
    dossier = dict(summary,
        flags_detalhe=[
            {**summary["flags"][0], "regra": "Polígono de mudança fora da ASV a > 20 m do limite", "evidencias": [{"tipo": "geometria", "descricao": "42 ha de corte raso contíguos à ASV, confirmados por PRODES 2024", "valor": 42.0, "unidade": "ha", "camada": "mudanca", "filtro": {"dentro_upa": False}, "fonte": "s2"}], "area_ha": 42.0, "volume_m3": {"p10": 790.0, "p50": 925.0, "p90": 1090.0}},
            {**summary["flags"][1], "regra": "Σ área desmatada (dentro+fora) > área autorizada + tolerância", "evidencias": [{"tipo": "metrica", "descricao": "190 ha desmatados para 150 ha autorizados", "valor": 190.0, "unidade": "ha"}]},
            {**summary["flags"][2], "regra": "p10 do volume estimado (área × estoque/ha) > volume autorizado", "evidencias": [{"tipo": "metrica", "descricao": "Estoque declarado 22 m³/ha (AUTEX); GEDI L4A indica 180 Mg/ha", "valor": 22.0, "unidade": "m³/ha"}], "volume_m3": {"p10": 3600.0, "p50": 4180.0, "p90": 4900.0}},
            {**summary["flags"][3], "regra": "Intervalo da mudança dentro da validade", "evidencias": []},
        ],
        imagens=[
            {"id": "s2_pre", "sensor": "Sentinel-2", "rotulo": "Sentinel-2 · mediana jun–set 2023", "data": "2023-06-01/2023-09-30", "png": "img/s2_pre.png", "bounds": b, "resolucao_m": 10, "nuvem_pct": 1.0, "par": "pre"},
            {"id": "s2_pos", "sensor": "Sentinel-2", "rotulo": "Sentinel-2 · mediana jun–set 2024", "data": "2024-06-01/2024-09-30", "png": "img/s2_pos.png", "bounds": b, "resolucao_m": 10, "nuvem_pct": 4.0, "par": "pos"},
            {"id": "dndvi", "sensor": "Derivado", "rotulo": "Corte raso detectado (LightGBM)", "data": None, "png": "img/dndvi.png", "bounds": b, "resolucao_m": 10, "nuvem_pct": None, "par": None},
        ],
        camadas=["upa", "buffer", "mudanca", "prodes"],
        especies=[],
        parametros_volume=[
            {"nome": "Estoque comercial por ha", "distribuicao": "normal(22, 3)", "valor": 22.0, "unidade": "m³/ha", "origem": "volume AUTEX / área autorizada"},
            {"nome": "AGB pré-evento (checagem)", "distribuicao": "GEDI L4A média ± se", "valor": 180.0, "unidade": "Mg/ha", "origem": "GEDI L4A"},
        ],
        modelo={"detector": "lightgbm-v1 (mock)"},
        proveniencia=prov(),
        limitacoes=["Dados MOCK para desenvolvimento - não representam autorização real."],
        linha_do_tempo=[{"data": "2024-03-01", "evento": "Início da validade da ASV", "fonte": "pamgia"}, {"data": "2024-08-30", "evento": "PRODES 2024 registra corte raso adjacente", "fonte": "deter"}],
    )
    Dossier(**dossier)
    write_json(d / "dossier.json", dossier)
    return summary


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "metrics").mkdir(parents=True)
    casos = [make_poa(), make_asv()]
    # casos extras só-documentais para popular a triagem
    for i in range(8):
        lon, lat = -63.0 - rng.random() * 1.5, -7.2 - rng.random() * 2.0
        casos.append(dict(
            autex=f"MOCK-POA-{i + 2:04d}", tipo="POA", uf=rng.choice(["AM", "RO"]), municipio=rng.choice(["LABREA (MOCK)", "CANUTAMA (MOCK)", "PORTO VELHO (MOCK)"]),
            centroide=(lon, lat), bbox=(lon - 0.02, lat - 0.02, lon + 0.02, lat + 0.02), area_autorizada_ha=round(rng.uniform(200, 1500), 1),
            validade={"inicio": "2024-04-01", "fim": "2025-04-01"}, situacao="Autorização Emitida",
            volume_autorizado_m3=round(rng.uniform(4000, 30000)), volume_declarado_explorado_m3=round(rng.uniform(3000, 30000)),
            volume_estimado_m3={"p10": None, "p50": None, "p90": None}, area_disturbio_ha=None, area_disturbio_fora_ha=None,
            n_arvores_declaradas=rng.randint(300, 4000),
            flags=[{"codigo": "D", "titulo": "Intensidade acima de 30 m³/ha", "status": rng.choice(["indicio", "sem_indicio"]), "severidade": "media", "confianca": 0.9}],
            score=round(rng.uniform(0.05, 0.5), 2), source_mode="simulado", analise_imagem=False, processado_em=NOW))
    casos.sort(key=lambda c: -c["score"])
    idx = dict(gerado_em=NOW, polo="AMACRO - Sul do AM + Porto Velho/RO (MOCK)",
               totais={"autorizacoes_avaliadas": len(casos), "com_imagem": 2, "com_indicio": 4, "arvores_if100": 1820}, casos=casos)
    Index(**idx)
    write_json(OUT / "index.json", idx)
    md = dict(protocolo="GroupKFold espacial (blocos 5 km), k=5", rotulos="PRODES (corte raso) + DETER (CS_*, degradação) · negativos em floresta estável",
              modelos=[
                  {"nome": "baseline-otsu", "iou": 0.48, "f1": 0.65, "precisao": 0.58, "recall": 0.74, "matriz_confusao": [[90210, 6650], [2600, 7400]], "n_pixels_teste": 106860, "obs": "MOCK"},
                  {"nome": "lightgbm", "iou": 0.61, "f1": 0.76, "precisao": 0.79, "recall": 0.73, "matriz_confusao": [[94900, 1960], [2710, 7290]], "n_pixels_teste": 106860, "obs": "MOCK"},
              ], selecionado="lightgbm", gerado_em=NOW)
    MetricsDetector(**md)
    write_json(OUT / "metrics" / "detector.json", md)
    curva = [{"disturbio_frac": x / 20, "p10": round(x / 20 * 90, 1), "p50": round(x / 20 * 160, 1), "p90": round(x / 20 * 260, 1)} for x in range(0, 21)]
    mc = dict(protocolo="GroupKFold por UPA, k=5 · células 100 m", n_celulas_treino=184220, n_upas=412, r2=0.41, mae_m3_ha=6.8,
              cobertura_p10_p90=0.77, cobertura_nominal=0.80, curva=curva, obs="MOCK", gerado_em=NOW)
    MetricsCalibracao(**mc)
    write_json(OUT / "metrics" / "calibracao.json", mc)
    write_json(OUT / "metrics" / "montecarlo.json", {"n_amostras": 10000, "obs": "MOCK"})
    print("mock ok:", OUT)


if __name__ == "__main__":
    main()
