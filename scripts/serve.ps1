$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (Test-Path -LiteralPath 'web/package.json') {
    npm --prefix web run build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
