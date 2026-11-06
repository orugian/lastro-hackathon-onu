import importlib

import pytest
from fastapi.testclient import TestClient

from api.main import PROJECT_ROOT, create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LASTRO_COMUNICACOES", str(tmp_path))
    from pipeline import comunicacao
    importlib.reload(comunicacao)
    return TestClient(create_app(PROJECT_ROOT / "data/artifacts-mock"))


def test_gera_protocolos_acima_do_limiar(client):
    r = client.get("/api/comunicacoes").json()
    autex = {c["autex"] for c in r["comunicacoes"]}
    assert r["limiar"] == 0.70
    assert autex == {"MOCK-POA-0001", "MOCK-ASV-0001"}  # scores 0,83 e 0,77; demais < 0,70
    assert all(c["status"] == "aguardando_confirmacao" for c in r["comunicacoes"])
    assert all(len(c["sha256"]) == 64 for c in r["comunicacoes"])
    # idempotente
    assert client.get("/api/comunicacoes").json()["ultima_varredura"]["novos"] == 0


def test_confirmacao_exige_servidor_e_justificativa(client):
    p = client.get("/api/comunicacoes").json()["comunicacoes"][0]["protocolo"]
    assert client.post(f"/api/comunicacoes/{p}/confirmar", json={"servidor": "", "justificativa": "x"}).status_code == 422


def test_simulado_nunca_e_enviado(client):
    p = client.get("/api/comunicacoes").json()["comunicacoes"][0]["protocolo"]
    r = client.post(f"/api/comunicacoes/{p}/confirmar", json={"servidor": "Fiscal Teste", "justificativa": "Revisado e procedente para envio"}).json()
    assert r["status"] == "bloqueado_simulacao"  # mock = source_mode simulado
    assert [e["acao"] for e in r["trilha"]] == ["gerado_automaticamente", "confirmado", "envio_bloqueado"]


def test_texto_manifestacao(client):
    p = client.get("/api/comunicacoes").json()["comunicacoes"][0]["protocolo"]
    t = client.get(f"/api/comunicacoes/{p}/texto").text
    assert "NÃO constituem prova" in t and "SHA-256" in t and "CENÁRIO SIMULADO" in t
