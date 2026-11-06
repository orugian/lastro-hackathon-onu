import json
from pathlib import Path
import sys
import time
from types import ModuleType

from fastapi.testclient import TestClient
import pytest

from api.main import create_app, UNAVAILABLE

MOCK = Path(__file__).resolve().parents[2] / "data/artifacts-mock"
AUTEX = "MOCK-POA-0001"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LASTRO_ARTIFACTS", str(MOCK))
    with TestClient(create_app()) as client:
        yield client


def test_health(client):
    data = client.get("/api/health").json()
    assert data["status"] == "ok"
    assert data["modo"] == "mock"
    assert data["versao"] == "1.0"
    assert Path(data["artifacts_root"]) == MOCK
    assert data["gerado_em"]


@pytest.mark.parametrize("params", [
    {"uf": "AM"}, {"tipo": "ASV"}, {"flag": "A"},
    {"min_score": .6}, {"so_imagem": True},
    {"uf": "AM", "tipo": "POA", "flag": "A", "min_score": .5, "so_imagem": True},
])
def test_filters(client, params):
    original = client.get("/api/index").json()
    response = client.get("/api/index", params=params)
    assert response.status_code == 200
    expected = [c for c in original["casos"] if
                ("uf" not in params or c["uf"] == params["uf"]) and
                ("tipo" not in params or c["tipo"] == params["tipo"]) and
                ("flag" not in params or any(f["codigo"] == params["flag"] for f in c["flags"])) and
                ("min_score" not in params or c["score"] >= params["min_score"]) and
                (not params.get("so_imagem") or c["analise_imagem"])]
    assert response.json()["casos"] == expected
    assert client.get("/api/index").json() == original


def test_case_assets_and_html(client):
    response = client.get(f"/api/cases/{AUTEX}")
    assert response.status_code == 200
    case = response.json()
    assert case["legal_conclusion"] is False
    for layer in case["camadas"]:
        response = client.get(f"/api/cases/{AUTEX}/layers/{layer}")
        assert response.status_code == 200
        assert response.json()["type"] == "FeatureCollection"
    for image in case["imagens"]:
        response = client.get(f"/api/cases/{AUTEX}/{image['png']}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content.startswith(b"\x89PNG")
    response = client.get(f"/api/cases/{AUTEX}/dossier.html")
    assert response.status_code == 200
    assert "Não constitui prova nem auto de infração." in response.text


@pytest.mark.parametrize("path", [
    "/api/cases/INEXISTENTE", "/api/jobs/inexistente", "/api/metrics/outro",
    f"/api/cases/{AUTEX}/layers/inexistente", f"/api/cases/{AUTEX}/img/inexistente.png",
    f"/api/cases/{AUTEX}/layers/../dossier.json",
    f"/api/cases/{AUTEX}/layers/%2e%2e%2fdossier",
    f"/api/cases/{AUTEX}/img/%2e%2e%5cdossier.png",
    "/api/cases/%2e%2e%5cmetrics", f"/api/cases/{AUTEX}/img/s2_pre.jpg",
])
def test_missing_and_traversal(client, path):
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("name", ["detector", "calibracao", "montecarlo"])
def test_metrics(client, name):
    assert client.get(f"/api/metrics/{name}").status_code == 200


def poll(client, job_id):
    for _ in range(200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(.01)
    pytest.fail("Job não terminou")


def test_cached_analysis(client):
    result = client.post(f"/api/analyze/{AUTEX}").json()
    assert result["status"] == "done"
    job = poll(client, result["job_id"])
    assert job["cached"] is True
    assert job["resultado"]["autex"] == AUTEX


def test_unavailable_analysis(client, monkeypatch):
    monkeypatch.setitem(sys.modules, "pipeline.live", None)
    result = client.post("/api/analyze/DESCONHECIDA").json()
    job = poll(client, result["job_id"])
    assert job["status"] == "error"
    assert job["mensagem"] == UNAVAILABLE


@pytest.mark.parametrize("behavior", ["success", "failure", "timeout"])
def test_live_pipeline(client, monkeypatch, behavior):
    module = ModuleType("pipeline.live")
    def analisar(autex, progress_cb):
        progress_cb("Lendo imagens", .5)
        if behavior == "timeout":
            time.sleep(.15)
        if behavior == "failure":
            raise RuntimeError("internal detail")
        return {"autex": autex}
    module.analisar = analisar
    monkeypatch.setitem(sys.modules, "pipeline.live", module)
    if behavior == "timeout":
        monkeypatch.setattr("api.main.LIVE_TIMEOUT", .02)
    result = client.post("/api/analyze/NOVA").json()
    job = poll(client, result["job_id"])
    assert job["status"] == ("done" if behavior == "success" else "error")
    if behavior == "success":
        assert job["resultado"] == {"autex": "NOVA"}
        assert job["progresso"] == 1
    else:
        assert job["mensagem"] == UNAVAILABLE


def test_cache_invalidation_and_html_escape(tmp_path):
    folder = tmp_path / "cases" / AUTEX
    folder.mkdir(parents=True)
    data = json.loads((MOCK / "cases" / AUTEX / "dossier.json").read_text(encoding="utf-8"))
    target = folder / "dossier.json"
    target.write_text(json.dumps(data), encoding="utf-8")
    with TestClient(create_app(tmp_path)) as client:
        assert client.get(f"/api/cases/{AUTEX}").json()["municipio"] == data["municipio"]
        data["municipio"] = "<script>alert('xss')</script>"
        target.write_text(json.dumps(data), encoding="utf-8")
        assert client.get(f"/api/cases/{AUTEX}").json()["municipio"] == data["municipio"]
        html = client.get(f"/api/cases/{AUTEX}/dossier.html").text
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


def test_spa_and_cors(tmp_path):
    (tmp_path / "index.html").write_text("<h1>Lastro</h1>", encoding="utf-8")
    with TestClient(create_app(MOCK, tmp_path)) as client:
        assert client.get("/mapa/caso").text == "<h1>Lastro</h1>"
        assert client.get("/api/inexistente").status_code == 404
        assert client.get("/missing.js").status_code == 404
        assert client.get("/api/index").status_code == 200
        response = client.options("/api/analyze/NOVA", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
