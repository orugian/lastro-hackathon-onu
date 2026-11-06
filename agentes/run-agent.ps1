# Executa um agente Codex não-interativo a partir de uma spec Markdown.
# Uso: powershell -File agentes\run-agent.ps1 -Spec agentes\ag-dados.md [-Extra "instrução adicional"]
param(
  [Parameter(Mandatory = $true)][string]$Spec,
  [string]$Extra = ""
)
$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent
$name = [IO.Path]::GetFileNameWithoutExtension($Spec)
$logDir = Join-Path $root 'agentes\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$ts = Get-Date -Format 'HHmmss'
$log = Join-Path $logDir "$name-$ts.log"
$last = Join-Path $logDir "$name-$ts.final.md"

$common = Get-Content (Join-Path $root 'agentes\_COMUM.md') -Raw -Encoding UTF8
$body = Get-Content (Join-Path $root $Spec) -Raw -Encoding UTF8
$prompt = "$common`n`n---`n`n$body`n`n$Extra"

"[$(Get-Date -Format HH:mm:ss)] start $name" | Out-File $log -Encoding utf8
$prompt | codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check -C $root -o $last - *>> $log
"[$(Get-Date -Format HH:mm:ss)] end $name exit=$LASTEXITCODE" | Out-File $log -Append -Encoding utf8
Write-Output "FINAL: $last"
if (Test-Path $last) { Get-Content $last -Encoding UTF8 }
