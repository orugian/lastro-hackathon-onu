import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from contracts.models import Dossier, Index
from pipeline.rules import flags as F
from pipeline.rules.score import score


def _mud(rows):
    return gpd.GeoDataFrame(rows, geometry=[box(0, 0, 100, 100)] * len(rows), crs=31980)


def test_C_tolerancia_e_ausencia():
    base = dict(n_arvores=100, c_n_fora=0, c_volume_fora_m3=0.0, c_n_coord_incoerente=0, n_sem_coordenada=0, status_C="sem_indicio")
    assert F.flag_C(base).status == "sem_indicio"
    f = F.flag_C(dict(base, c_n_fora=2, c_volume_fora_m3=14.0, status_C="indicio"))
    assert f.status == "indicio" and f.evidencias[0].filtro == {"dentro_upa": False}
    # coordenada incoerente (> 5 km) é limitação, não indício
    f = F.flag_C(dict(base, c_n_coord_incoerente=5))
    assert f.status == "sem_indicio" and "qualidade cadastral" in f.evidencias[0].descricao
    assert F.flag_C(dict(base, n_arvores=0, status_C="nao_avaliado")).status == "nao_avaliado"
    assert F.flag_C(dict(base, n_sem_coordenada=3)).status == "inconclusivo"


def test_B_tolerancia_20m_prob_e_area():
    def row(**k):
        r = dict(area_ha=2.0, prob=0.8, dentro_upa=False, dist_limite_m=25.0, coberto_outra=False); r.update(k); return r
    assert F.flag_B(_mud([row()]), None, None, None, area_upa_ha=100, area_buffer_ha=2000).status == "indicio"
    assert F.flag_B(_mud([row(dist_limite_m=20.0)]), None, None, None, area_upa_ha=100, area_buffer_ha=2000).status == "sem_indicio"
    assert F.flag_B(_mud([row(prob=0.55)]), None, None, None, area_upa_ha=100, area_buffer_ha=2000).status == "sem_indicio"
    assert F.flag_B(_mud([row(area_ha=0.4)]), None, None, None, area_upa_ha=100, area_buffer_ha=2000).status == "sem_indicio"
    assert F.flag_B(_mud([row(coberto_outra=True)]), None, None, None, area_upa_ha=100, area_buffer_ha=2000).status == "sem_indicio"
    assert F.flag_B(None, None, None, None).status == "nao_avaliado"


def test_B_sanidade_area_implausivel_vira_inconclusivo():
    f = F.flag_B(_mud([dict(area_ha=400.0, prob=0.9, dentro_upa=False, dist_limite_m=500.0, coberto_outra=False)]),
                 None, None, None, area_upa_ha=100, area_buffer_ha=5000)
    assert f.status == "inconclusivo" and any("artefato" in e.descricao for e in f.evidencias)


def test_D_e_E_dados_ausentes_nao_avaliado():
    assert F.flag_D_poa(dict(n_arvores=0), 100).status == "nao_avaliado"
    assert F.flag_E_poa(dict(n_arvores=0)).status == "nao_avaliado"
    assert F.flag_D_asv(None, 1000).status == "nao_avaliado"
    assert F.flag_D_asv({"p10": 1200, "p50": 1500, "p90": 1800}, 1000).status == "indicio"
    assert F.flag_D_asv({"p10": 900, "p50": 1500, "p90": 1800}, 1000).status == "sem_indicio"
    assert F.flag_F2(None, 100).status == "nao_avaliado"
    assert F.flag_F6(None, False).status == "nao_avaliado"


def test_F2_limiar_5pct():
    assert F.flag_F2(105.0, 100.0).status == "sem_indicio"
    assert F.flag_F2(106.0, 100.0).status == "indicio"


def test_E_janela_cruzando_validade_inconclusivo():
    v = ("2024-03-01", "2025-03-01")
    assert F.janela_vs_validade(("2024-06-01", "2024-09-30"), v) == "dentro"
    assert F.janela_vs_validade(("2025-06-01", "2025-09-30"), v) == "fora"
    assert F.janela_vs_validade(("2024-10-01", "2025-10-05"), v) == "cruza"
    assert F.janela_vs_validade(("2024-10-01", "2025-10-05"), (None, "2025-01-01")) == "desconhecido"
    f = F.flag_E_imagem(50.0, ("2023-06-01", "2023-10-05"), ("2025-06-01", "2025-10-05"), v)
    assert f.status == "inconclusivo"
    f = F.flag_E_imagem(50.0, ("2025-06-01", "2025-10-05"), ("2026-06-01", "2026-10-05"), v)
    assert f.status == "indicio"
    assert F.flag_E_imagem(None, ("a", "b"), ("c", "d"), v).status == "nao_avaliado"


def test_A_blocos_dispara_e_nao_dispara():
    cel = gpd.GeoDataFrame({"id": [f"X_{i}_0" for i in range(9)], "dentro_upa": [True] * 9, "n_arvores": [3] * 9,
                            "classe": ["consistente"] * 9, "vol_declarado": [30.0] * 9, "disturbio_frac": [0.0] * 9, "area_ha": [1.0] * 9},
                           geometry=[box(i, 0, i + 1, 1) for i in range(9)])
    mc = {"upa": {"p10": 50.0, "p50": 100.0, "p90": 200.0}, "declarado_upa_m3": 270.0}
    bl = pd.DataFrame({"bloco": ["0_0", "1_0", "2_0"], "p10": [5, 5, 5], "p50": [10, 10, 10], "p90": [20, 20, 20],
                       "vol_declarado": [90.0, 90.0, 90.0], "n_celulas": [3, 3, 3], "n_arvores": [9, 9, 9],
                       "sem_lastro": [True, True, True], "excesso": [70.0, 70.0, 70.0]})
    f = F.flag_A(cel, mc, 0.8, 27, blocos=bl)
    assert f.status == "indicio" and f.volume_m3.p50 > 0
    assert f.evidencias[0].filtro == {"classe": "sem_lastro"}
    ok = bl.assign(sem_lastro=False, excesso=0.0)
    f = F.flag_A(cel, {"upa": {"p10": 200, "p50": 300, "p90": 400}, "declarado_upa_m3": 270.0}, 0.8, 27, blocos=ok)
    assert f.status == "sem_indicio"
    assert F.flag_A(cel, mc, 0.8, 0, blocos=bl).status == "nao_avaliado"
    assert F.flag_A(None, None, 0.8, 27, blocos=bl).status == "nao_avaliado"


def test_score_monotonico():
    def fl(cod, st="indicio", sev="alta", conf=0.9):
        return F._flag(cod, st, sev, conf, "r")
    s1 = score([fl("C")])
    s2 = score([fl("C"), fl("A")])
    s3 = score([fl("C"), fl("A"), fl("B")])
    assert 0 < s1 < s2 < s3 < 1
    assert score([fl("C", conf=0.5)]) < s1
    assert score([fl("C", sev="media")]) < s1
    assert score([fl("C", st="inconclusivo"), fl("A", st="nao_avaliado")]) == 0
    assert score([]) == 0


ART = Path(__file__).resolve().parents[2] / "data" / "artifacts"


@pytest.mark.skipif(not (ART / "index.json").exists(), reason="artefatos não gerados")
def test_schema_index_e_caso_exportado():
    idx = Index.model_validate_json((ART / "index.json").read_text(encoding="utf-8"))
    assert idx.totais["autorizacoes_avaliadas"] >= 1142
    com_img = [c for c in idx.casos if c.analise_imagem and c.source_mode == "real"]
    assert com_img
    d = Dossier.model_validate_json((ART / "cases" / com_img[0].autex / "dossier.json").read_text(encoding="utf-8"))
    for cam in d.camadas:
        assert (ART / "cases" / d.autex / f"{cam}.geojson").exists()
    for im in d.imagens:
        assert (ART / "cases" / d.autex / im.png).exists()
    txt = json.dumps(d.model_dump(), ensure_ascii=False).lower()
    for proibido in ("fraude", "ilegal", "crime", "cpf", "cnpj", "nm_detentor"):
        assert proibido not in txt
    # dados ausentes nunca viram sem_indicio
    for c in idx.casos:
        if c.n_arvores_declaradas == 0 and c.tipo == "POA":
            assert all(f.status != "sem_indicio" for f in c.flags if f.codigo in ("C", "D", "E"))
