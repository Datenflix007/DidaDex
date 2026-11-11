$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { py -3 -m venv .venv; if ($LASTEXITCODE -ne 0) { throw 'venv fehlt' } }
& $python -m pip install -r '.\crawler\expansion\requirements_expansion.txt'
if ($LASTEXITCODE -ne 0) { throw 'Abhaengigkeiten konnten nicht installiert werden.' }
& $python '.\crawler\expansion\crawler.py' run --hours 72 --target-mib 500 --workers 20 --per-host 1 --host-delay 2.5 --bpb-sitemap
if ($LASTEXITCODE -ne 0) { throw 'Expansion fehlgeschlagen.' }
