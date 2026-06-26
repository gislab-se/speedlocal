param(
    [int]$Port = 8502,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

& $Python -m streamlit run app.py --server.address 127.0.0.1 --server.port $Port
exit $LASTEXITCODE
