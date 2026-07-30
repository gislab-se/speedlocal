param(
    [int]$Port = 8502,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
    Where-Object { $_.Port -eq $Port }
if ($listeners) {
    $endpoints = ($listeners | ForEach-Object { $_.ToString() }) -join ", "
    throw "Port $Port already has an active listener ($endpoints). Stop the existing server before starting another V2 Final instance."
}

if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $repoRoot ".venv\Scripts\python.exe"
}
$pythonExecutable = (Get-Command -Name $Python -CommandType Application -ErrorAction Stop).Source

& $pythonExecutable -m streamlit run app.py --server.address 127.0.0.1 --server.port $Port
exit $LASTEXITCODE
