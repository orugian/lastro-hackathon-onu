# Downloads em background para data/raw (fontes IBAMA). Idempotente.
$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent
$raw = Join-Path $root 'data\raw'
New-Item -ItemType Directory -Force $raw | Out-Null
$snd = Join-Path $root '_sondagem'

# Reaproveita o que já foi baixado na sondagem
foreach ($f in 'asv.csv','pmfs.csv','poa.csv','if100.zip','pamgia_amz_attrs.json') {
  $src = Join-Path $snd $f
  if ((Test-Path $src) -and -not (Test-Path (Join-Path $raw $f))) { Copy-Item $src $raw }
}
if (-not (Test-Path (Join-Path $raw 'if100'))) { Expand-Archive (Join-Path $raw 'if100.zip') (Join-Path $raw 'if100') -Force }

$items = @(
  @{ n='dof_autorizacoes_csv.zip'; u='https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/DOF/DOFAutorizacoes/DOFAutorizacoes_csv.zip' },
  @{ n='uas.csv'; u='https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/SINAFLOR/usoAlternativoDoSolo/uso-alternativo-do-solo.csv' },
  @{ n='dof_transportes_csv.zip'; u='https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/DOF/DOFTransportes/DOFTransportes_csv.zip' }
)
foreach ($i in $items) {
  $out = Join-Path $raw $i.n
  Write-Output "[$(Get-Date -Format HH:mm:ss)] baixando $($i.n)"
  curl.exe -s -L -C - -o $out $i.u
  Write-Output "[$(Get-Date -Format HH:mm:ss)] ok $($i.n) $((Get-Item $out).Length) bytes"
}
foreach ($z in 'dof_autorizacoes_csv.zip') {
  Expand-Archive (Join-Path $raw $z) (Join-Path $raw ($z -replace '\.zip$','')) -Force
}
Write-Output "DONE"
