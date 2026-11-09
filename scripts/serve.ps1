$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

foreach ($tool in 'npm', 'uv') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Pré-requisito ausente: $tool. Consulte o README."
    }
}

npm --prefix web ci
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
npm --prefix web run build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv sync --locked
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run --locked uvicorn api.main:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
