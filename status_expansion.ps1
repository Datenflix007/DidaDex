$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Virtuelle Umgebung nicht vorhanden. Zuerst start_expansion_72h.ps1 ausfuehren.' }
& $python '.\crawler\expansion\crawler.py' status
