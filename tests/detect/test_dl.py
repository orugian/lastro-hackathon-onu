import numpy as np
import pytest

from pipeline.detect import dl, selecao


@pytest.mark.skipif(not dl.ONNX.exists(), reason="pesos ONNX ausentes")
def test_prob_unet_shape_nodata_e_faixa():
    rng = np.random.default_rng(0)
    x = rng.uniform(0.01, 0.4, (12, 250, 300)).astype(np.float32)
    valid = np.ones((250, 300), bool)
    valid[:10] = False
    p = dl.prob_unet(x, valid)
    assert p.shape == (250, 300)
    assert (p[:10] == -9999).all()
    assert ((p[10:] >= 0) & (p[10:] <= 1)).all()


@pytest.mark.skipif(not dl.ONNX.exists(), reason="pesos ONNX ausentes")
def test_janela_menor_que_chip():
    x = np.full((12, 100, 120), 0.1, np.float32)
    assert dl.prob_unet(x, np.ones((100, 120), bool)).shape == (100, 120)


def test_selecao_volume_usa_lightgbm_sempre(monkeypatch):
    monkeypatch.setenv("LASTRO_DETECTOR", "unet")
    assert selecao.metodo() == "lightgbm"
    assert selecao.limiar() == selecao.limiar_lgbm()


def test_selecao_fallback_lightgbm(monkeypatch):
    monkeypatch.setenv("LASTRO_DETECTOR", "lightgbm")
    assert selecao.nome() == "lightgbm"
    assert selecao.metodo_espacial() == "lightgbm"
