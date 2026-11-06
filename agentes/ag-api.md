# AG-API: backend FastAPI

**Suas pastas:** `api/`, `tests/api/`.

## Objetivo
API local que serve os artefatos do contrato v1 (`contracts/models.py`) para o front e oferece a análise ao vivo de uma autorização.

## Requisitos
- `api/main.py` com app FastAPI. Rodar com `uv run uvicorn api.main:app --port 8000`.
- Raiz de artefatos configurável: env `LASTRO_ARTIFACTS`. O padrão é `data/artifacts` se `data/artifacts/index.json` existir; caso contrário, `data/artifacts-mock`. Exponha qual está em uso em `/api/health`.
- Endpoints (todos GET, salvo indicação):
  - `/api/health` → `{status, versao, artifacts_root, modo: "real"|"mock", gerado_em}`
  - `/api/index` → `index.json` (validado com `Index`). Aceite filtros por query: `uf`, `tipo`, `flag` (código), `min_score`, `so_imagem`.
  - `/api/cases/{autex}` → `dossier.json`
  - `/api/cases/{autex}/layers/{nome}` → GeoJSON (nome em `camadas` do dossier; valide o nome com regex `^[a-z0-9_]+$`, para evitar path traversal)
  - `/api/cases/{autex}/img/{arquivo}` → PNG (mesma validação; só `.png`)
  - `/api/metrics/{nome}` → `detector` | `calibracao` | `montecarlo`
  - `/api/cases/{autex}/dossier.html` → versão imprimível simples do dossiê (HTML server-side com escape), com o aviso "Resultado experimental de triagem. Não constitui prova nem auto de infração." em destaque.
  - `POST /api/analyze/{autex}` → análise ao vivo, assíncrona:
    - Cria um job e retorna `{job_id}`. `GET /api/jobs/{job_id}` → `{status: queued|running|done|error, etapa, progresso, resultado?}`.
    - Se `{autex}` já tiver artefato, retorna `done` imediatamente com `cached: true`.
    - Caso contrário, chama `pipeline.live.analisar(autex, progress_cb)`. Esse módulo ainda NÃO existe; o orquestrador vai implementá-lo depois. Importe-o de forma tardia dentro de try/except. Se não existir ou falhar, devolva `status: error` com mensagem amigável ("Análise ao vivo indisponível; exibindo dados em cache").
    - Timeout de 90 s.
- Servir o front buildado: se `web/dist` existir, monte em `/` com fallback SPA para `index.html`, para a demo rodar numa porta só (`:8000`).
- CORS liberado para `http://localhost:5173` (dev do Vite).
- Bind em `127.0.0.1`.
- Cache leve em memória dos JSON (invalida por mtime).

## Entregas
1. `api/main.py` (+ módulos, se quiser).
2. `tests/api/test_api.py` com `fastapi.testclient`, contra `data/artifacts-mock`: health, index com filtros, dossier, layers, img, path traversal bloqueado (`../`), 404 para autex inexistente, analyze com autex mock (cached) e analyze com autex desconhecida (error amigável).
3. `scripts/serve.ps1`: builda o front (se `web/package.json` existir: `npm --prefix web run build`) e sobe o uvicorn. Esse arquivo é seu, mesmo estando fora de `api/`.

## Critério de pronto
`uv run pytest tests/api` passa. `uv run uvicorn api.main:app --port 8000` responde `/api/index` com o mock.
