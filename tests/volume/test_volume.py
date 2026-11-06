import numpy as np
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from pipeline.volume.estimar import (amostrar_quantis, avaliar_blocos, bloco_ids, classificar_celulas, mc_blocos,
                                     monte_carlo_upa, volume_corte_raso)
from pipeline.volume.janelas import janelas_sazonais
from pipeline.volume.calibrar import _cqr_q


def test_cobertura_quantis_sinteticos_proxima_do_nominal():
    rng = np.random.default_rng(0)
    n = 20000
    mu = rng.uniform(5, 50, n)
    y = rng.normal(mu, 5)
    z = 1.2815515655446004
    q = np.column_stack([mu - z * 5, mu, mu + z * 5])
    cov = ((y >= q[:, 0]) & (y <= q[:, 2])).mean()
    assert abs(cov - 0.80) < 0.02
    # amostragem pela CDF linear por partes reproduz os quantis informados
    s = amostrar_quantis(10.0, 20.0, 40.0, rng.random(200000))
    p = np.percentile(s, [10, 50, 90])
    assert np.allclose(p, [10, 20, 40], atol=0.5)


def test_cqr_corrige_intervalo_estreito():
    rng = np.random.default_rng(1)
    y = rng.normal(0, 2, 5000)
    q = np.column_stack([np.full(5000, -1.0), np.zeros(5000), np.full(5000, 1.0)])  # estreito demais
    qc = _cqr_q(y[:2500], q[:2500])
    adj = q[2500:].copy(); adj[:, 0] -= qc; adj[:, 2] += qc
    cov = ((y[2500:] >= adj[:, 0]) & (y[2500:] <= adj[:, 2])).mean()
    assert 0.76 <= cov <= 0.86


def _cel(n=9, vd=None, p=(1.0, 2.0, 4.0), na=None, dist=0.0, fv=1.0):
    ids = [f"EPSG:31980_{i % 3}_{i // 3}" for i in range(n)]
    g = gpd.GeoDataFrame({"id": ids, "vol_declarado": vd if vd is not None else [0.0] * n,
                          "n_arvores": na if na is not None else [0] * n, "disturbio_frac": [dist] * n,
                          "frac_valida": [fv] * n, "vol_p10": [p[0]] * n, "vol_p50": [p[1]] * n, "vol_p90": [p[2]] * n,
                          "dentro_upa": [True] * n, "area_ha": [1.0] * n},
                         geometry=[box(i, 0, i + 1, 1) for i in range(n)], crs=31980)
    return g


def test_monte_carlo_reprodutivel_com_seed():
    g = classificar_celulas(_cel(vd=[3.0] * 9, na=[1] * 9))
    a = monte_carlo_upa(g, n=2000, seed=42, sigma_upa=0.3)
    b = monte_carlo_upa(g, n=2000, seed=42, sigma_upa=0.3)
    c = monte_carlo_upa(g, n=2000, seed=43, sigma_upa=0.3)
    assert a["upa"] == b["upa"]
    assert a["upa"] != c["upa"]
    assert a["upa"]["p10"] < a["upa"]["p50"] < a["upa"]["p90"]


def test_classificar_casos_limite():
    g = _cel(n=6, vd=[10.0, 4.9, 3.0, 0.0, 0.0, 10.0], na=[2, 1, 1, 0, 0, 3], p=(1.0, 2.0, 4.0))
    g.loc[3, "disturbio_frac"] = 0.15   # exatamente no limiar -> nao_declarado
    g.loc[4, "disturbio_frac"] = 0.149  # abaixo -> sem_atividade
    g.loc[5, "frac_valida"] = 0.69      # nuvem -> nao_observavel mesmo com excesso
    c = classificar_celulas(g).classe.tolist()
    assert c[0] == "sem_lastro"        # 10 > p90 4 e >= 5 m³
    assert c[1] == "sem_lastro" or c[1] == "consistente"
    assert c[1] == "consistente"       # 4,9 m³ < mínimo de 5 m³
    assert c[2] == "consistente"
    assert c[3] == "nao_declarado"
    assert c[4] == "sem_atividade"
    assert c[5] == "nao_observavel"


def test_volume_corte_raso_unidades():
    r = volume_corte_raso(100.0, 20.0, None, n=20000)
    assert abs(r["p50"] - 2000) / 2000 < 0.02
    assert r["p10"] < r["p50"] < r["p90"]
    assert any(p["unidade"] == "m³/ha" for p in r["parametros"])
    r2 = volume_corte_raso(100.0, None, 300.0, n=20000)  # AGB -> volume: 300/(0,62*1,6)*0,4 ≈ 121 m³/ha
    assert 8000 < r2["p50"] < 16000
    assert volume_corte_raso(100.0, None, None)["p50"] is None


def test_blocos_3x3_e_regra():
    assert list(bloco_ids(["EPSG:31980_0_0", "EPSG:31980_2_2", "EPSG:31980_3_0", "EPSG:31980_-1_0_f"])) == ["0_0", "0_0", "1_0", "-1_0"]
    g = classificar_celulas(_cel(vd=[30.0] * 9, na=[5] * 9, p=(0.5, 1.0, 2.0)))
    b = avaliar_blocos(g, sigma_bloco=0.3)
    assert len(b) == 1 and bool(b.sem_lastro.iloc[0]) and b.excesso.iloc[0] > 200
    r = mc_blocos(np.array([[1.0, 2.0, 4.0]] * 9), np.array(["a"] * 9), 0.0, n=4000)
    assert 14 < r.p50.iloc[0] < 22


def test_janelas_sazonais_mesma_estacao():
    from datetime import date
    pre, pos, lim = janelas_sazonais("POA", "2024-08-16", "2025-06-30", "2024-06-19", "2025-06-19", hoje=date(2026, 11, 6))
    assert pre == ("2023-06-01", "2023-10-05") and pos == ("2025-06-01", "2025-10-05")
    pre, pos, lim = janelas_sazonais("POA", "2025-11-28", "2026-11-04", "2024-05-28", "2026-04-19", hoje=date(2026, 11, 6))
    assert pos == ("2026-06-01", "2026-10-05") and lim  # pós no futuro -> última seca + limitação
    for w in (pre, pos):
        assert w[0][5:] == "06-01" and w[1][5:] == "10-05"
