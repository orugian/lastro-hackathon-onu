"""API local dos artefatos Lastro v1."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
from copy import deepcopy
from html import escape
import importlib
import inspect
import json
import logging
import os
from pathlib import Path
import re
import threading
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import ValidationError
from starlette.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from contracts.models import Dossier, Index, MetricsCalibracao, MetricsDetector, SCHEMA_VERSION
from api.dossier_html import render as render_dossier_html

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIVE_TIMEOUT = float(os.environ.get("LASTRO_LIVE_TIMEOUT", "240"))
UNAVAILABLE = "Análise ao vivo indisponível; exibindo dados em cache"
NOTICE = "Resultado experimental de triagem. Não constitui prova nem auto de infração."
NOT_IN_POLO = "Autorização não encontrada no polo processado"
AUTORIZACOES = PROJECT_ROOT / "data/processed/autorizacoes.parquet"
logger = logging.getLogger(__name__)


class Artifacts:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def path(self, *parts):
        path = self.root.joinpath(*parts).resolve()
        if not path.is_relative_to(self.root):
            raise HTTPException(404, "Arquivo não encontrado")
        return path

    def read(self, *parts, model=None):
        path = self.path(*parts)
        try:
            stat = path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
            with self.lock:
                cached = self.cache.get(path)
                if cached and cached[0] == stamp:
                    value = deepcopy(cached[1])
                else:
                    value = json.loads(path.read_text(encoding="utf-8"))
                    self.cache[path] = (stamp, deepcopy(value))
                    self.cache.move_to_end(path)
                    if len(self.cache) > 128:
                        self.cache.popitem(last=False)
            return model.model_validate(value) if model else value
        except (FileNotFoundError, NotADirectoryError):
            raise HTTPException(404, "Artefato não encontrado") from None
        except (ValueError, ValidationError, OSError):
            raise HTTPException(503, "Artefato indisponível ou inválido") from None


def safe_name(value, pattern=r"[A-Za-z0-9_-]+"):
    if not re.fullmatch(pattern, value):
        raise HTTPException(404, "Nome inválido")
    return value


class SPAFiles(StaticFiles):
    async def get_response(self, path, scope):
        path = path.replace("\\", "/")
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Endpoint não encontrado")
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
        if Path(path).suffix or ".." in Path(path).parts:
            raise HTTPException(404, "Arquivo não encontrado")
        return await super().get_response("index.html", scope)


def create_app(artifacts_root=None, dist_root=None):
    configured = artifacts_root or os.environ.get("LASTRO_ARTIFACTS")
    default = PROJECT_ROOT / "data/artifacts"
    root = Path(configured) if configured else (
        default if (default / "index.json").is_file() else PROJECT_ROOT / "data/artifacts-mock"
    )
    artifacts = Artifacts(root)
    jobs = {}
    tasks = set()

    @asynccontextmanager
    async def lifespan(app):
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="Lastro", version=SCHEMA_VERSION, lifespan=lifespan)
    app.state.artifacts = artifacts
    app.state.jobs = jobs
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                       allow_methods=["GET", "POST"], allow_headers=["*"])

    polo_cache = {}

    def autex_no_polo(autex):
        """None se a verificação não se aplica (mock/sem parquet); senão True/False."""
        if artifacts.root.name == "artifacts-mock" or not AUTORIZACOES.is_file():
            return None
        if "ids" not in polo_cache:
            try:
                import pyarrow.parquet as pq
                polo_cache["ids"] = set(map(str, pq.read_table(AUTORIZACOES, columns=["autex"]).column("autex").to_pylist()))
            except Exception:
                polo_cache["ids"] = None
        ids = polo_cache["ids"]
        return None if ids is None else (autex in ids or autex.startswith("SIM-"))

    def dossier(autex):
        try:
            return artifacts.read("cases", safe_name(autex), "dossier.json", model=Dossier)
        except HTTPException as exc:
            if exc.status_code == 404 and autex_no_polo(autex) is False:
                raise HTTPException(404, NOT_IN_POLO) from None
            raise

    @app.get("/api/health")
    def health():
        index = artifacts.read("index.json", model=Index)
        mock = artifacts.root.name == "artifacts-mock" or (
            bool(index.casos) and all(case.source_mode == "simulado" for case in index.casos)
        )
        return dict(status="ok", versao=SCHEMA_VERSION, artifacts_root=str(artifacts.root),
                    modo="mock" if mock else "real", gerado_em=index.gerado_em)

    @app.get("/api/index", response_model=Index)
    def index(uf: str | None = None, tipo: str | None = None, flag: str | None = None,
              min_score: float | None = Query(None, ge=0, le=1), so_imagem: bool = False):
        result = artifacts.read("index.json", model=Index)
        result.casos = [c for c in result.casos if
                        (not uf or c.uf.upper() == uf.upper()) and
                        (not tipo or c.tipo == tipo.upper()) and
                        (not flag or any(f.codigo == flag.upper() for f in c.flags)) and
                        (min_score is None or c.score >= min_score) and
                        (not so_imagem or c.analise_imagem)]
        # totais describes the complete dataset, independent of list filters.
        return result

    @app.get("/api/cases/{autex}", response_model=Dossier)
    def case(autex: str):
        return dossier(autex)

    @app.get("/api/cases/{autex}/layers/{nome}")
    def layer(autex: str, nome: str):
        safe_name(nome, r"[a-z0-9_]+")
        if nome not in dossier(autex).camadas:
            raise HTTPException(404, "Camada não encontrada")
        return artifacts.read("cases", autex, nome + ".geojson")

    @app.get("/api/cases/{autex}/img/{arquivo}")
    def image(autex: str, arquivo: str):
        safe_name(arquivo, r"[a-z0-9_]+\.png")
        case = dossier(autex)
        if "img/" + arquivo not in [i.png for i in case.imagens]:
            raise HTTPException(404, "Imagem não encontrada")
        path = artifacts.path("cases", autex, "img", arquivo)
        if not path.is_file():
            raise HTTPException(404, "Imagem não encontrada")
        return FileResponse(path, media_type="image/png")

    @app.get("/api/metrics/{nome}")
    def metrics(nome: str):
        models = {"detector": MetricsDetector, "calibracao": MetricsCalibracao, "montecarlo": None, "dl": None}
        if nome not in models:
            raise HTTPException(404, "Métrica não encontrada")
        return artifacts.read("metrics", nome + ".json", model=models[nome])

    @app.get("/api/cases/{autex}/dossier.html", response_class=HTMLResponse)
    def printable(autex: str):
        return render_dossier_html(dossier(autex))

    async def run_job(job_id, autex):
        job = jobs[job_id]
        job.update(status="running", etapa="Iniciando análise", progresso=0)
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def progress(etapa, progresso):
            def update():
                if job["status"] == "running":
                    job.update(etapa=str(etapa), progresso=max(0, min(1, float(progresso))))
            if not loop.is_closed():
                loop.call_soon_threadsafe(update)

        def finish(value=None, error=None):
            if not future.done():
                if error is not None:
                    future.set_exception(error)
                else:
                    future.set_result(value)

        def worker():
            try:
                analyze = importlib.import_module("pipeline.live").analisar
                result = analyze(autex, progress)
                if inspect.isawaitable(result):
                    result = asyncio.run(result)
                result = jsonable_encoder(result)
                loop.call_soon_threadsafe(finish, result)
            except Exception as exc:
                if not loop.is_closed():
                    loop.call_soon_threadsafe(finish, None, exc)

        threading.Thread(target=worker, daemon=True, name=f"lastro-{job_id}").start()
        try:
            result = await asyncio.wait_for(future, LIVE_TIMEOUT)
            job.update(status="done", etapa="Concluído", progresso=1, resultado=result, cached=False)
        except Exception:
            logger.exception("Análise ao vivo indisponível para %s", autex)
            job.update(status="error", etapa=UNAVAILABLE, mensagem=UNAVAILABLE)

    @app.post("/api/analyze/{autex}")
    async def analyze(autex: str):
        safe_name(autex)
        job_id = uuid4().hex
        job = dict(status="queued", etapa="Na fila", progresso=0)
        if autex_no_polo(autex) is False:
            job.update(status="error", etapa=NOT_IN_POLO, mensagem=NOT_IN_POLO)
            jobs[job_id] = job
            return {"job_id": job_id, **deepcopy(job)}
        try:
            cached = dossier(autex)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
        else:
            # Só é cache "completo" se a imagem já foi analisada; dossiê documental dispara análise ao vivo.
            if getattr(cached, "analise_imagem", True) or artifacts.root.name == "artifacts-mock":
                job.update(status="done", etapa="Dados em cache", progresso=1,
                           resultado=jsonable_encoder(cached), cached=True)
        jobs[job_id] = job
        if job["status"] == "queued":
            task = asyncio.create_task(run_job(job_id, autex))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
        return {"job_id": job_id, **deepcopy(job)}

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str):
        if job_id not in jobs:
            raise HTTPException(404, "Job não encontrado")
        return deepcopy(jobs[job_id])

    # ---- Comunicações ao IBAMA (score ≥ limiar → protocolo automático; envio com confirmação humana) ----
    from pipeline import comunicacao as com_mod

    def _sync_comunicacoes():
        idx = artifacts.read("index.json", model=Index)
        casos = [c.model_dump() for c in idx.casos]
        return com_mod.gerar_automaticamente(casos, lambda a: dossier(a).model_dump())

    @app.get("/api/comunicacoes")
    def comunicacoes():
        resumo = _sync_comunicacoes()
        estado = com_mod.carregar()
        estado["comunicacoes"] = sorted(estado["comunicacoes"], key=lambda c: -c["score"])
        return {**estado, "ultima_varredura": resumo, "aviso": com_mod.AVISO, "destino": com_mod.DESTINO}

    @app.get("/api/comunicacoes/{protocolo}/texto", response_class=HTMLResponse)
    def comunicacao_texto(protocolo: str):
        safe_name(protocolo)
        p = com_mod.BASE / "pacotes" / f"{protocolo}.txt"
        if not p.is_file():
            raise HTTPException(404, "Protocolo não encontrado")
        return HTMLResponse(f"<pre style='white-space:pre-wrap;font:14px/1.5 ui-monospace,monospace;padding:24px'>{escape(p.read_text(encoding='utf-8'))}</pre>")

    @app.post("/api/comunicacoes/{protocolo}/{acao}")
    def comunicacao_acao(protocolo: str, acao: str, body: dict):
        safe_name(protocolo)
        servidor = str(body.get("servidor", "")).strip()
        justificativa = str(body.get("justificativa", "")).strip()
        if not servidor or len(justificativa) < 10:
            raise HTTPException(422, "Informe o servidor responsável e uma justificativa (mín. 10 caracteres).")
        try:
            if acao == "confirmar":
                return com_mod.confirmar(protocolo, servidor, justificativa)
            if acao == "descartar":
                return com_mod.descartar(protocolo, servidor, justificativa)
        except KeyError:
            raise HTTPException(404, "Protocolo não encontrado") from None
        raise HTTPException(404, "Ação inválida")

    dist = Path(dist_root) if dist_root else PROJECT_ROOT / "web/dist"
    if dist.is_dir():
        app.mount("/", SPAFiles(directory=dist, html=True), name="web")
    return app


app = create_app()
