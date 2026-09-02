# UmamusumeAutoTrainer launcher
# Uses the interpreter recorded by install.ps1 (.runtime_python), then falls
# back to venv\Scripts\python.exe, then conda env "uat", then `python`.
$ErrorActionPreference = "Stop"
$py = $null

if (Test-Path ".runtime_python") {
    $cand = (Get-Content ".runtime_python" | Select-Object -First 1).Trim()
    if ($cand -and (Test-Path $cand)) { $py = $cand }
}
if (-not $py -and (Test-Path "venv\Scripts\python.exe")) {
    $py = Join-Path (Get-Location) "venv\Scripts\python.exe"
}
if (-not $py) {
    foreach ($cand in @("E:\MINICONDA\envs\uat\python.exe", "$env:USERPROFILE\miniconda3\envs\uat\python.exe")) {
        if ($cand -and (Test-Path $cand)) { $py = $cand; break }
    }
}
if (-not $py) { $py = "python" }

Write-Host "Using python: $py"
& $py ".\main.py"
