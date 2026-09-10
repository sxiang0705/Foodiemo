param([switch]$Test)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot/..
if ($Test) { & ./.venv/Scripts/python.exe scripts/run.py --test }
else { & ./.venv/Scripts/python.exe scripts/run.py }
exit $LASTEXITCODE

