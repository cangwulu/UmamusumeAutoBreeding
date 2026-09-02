# ============================================================
# UmamusumeAutoTrainer - one-click install (Windows)
# Runtime interpreter resolution order:
#   1. conda env (default name: uat)  <- what the author uses locally
#   2. system 64-bit Python 3.10/3.11 (3.11 preferred), project-local venv created
# Version gate: 3.10 <= v < 3.13  (paddlepaddle==2.6.2 has no wheel for 3.12+/3.13)
#
# Behavior:
#   - install pinned deps from requirements.txt into the chosen interpreter
#   - freeze full snapshot into requirements.lock.txt (commit it)
#   - write the chosen interpreter path to .runtime_python (used by run.ps1)
# Mirror: default tsinghua (China). Set $PYPI_MIRROR to $null for official PyPI.
#
# Usage:  .\install.ps1                 (use conda env "uat" if present)
#         .\install.ps1 -CondaEnv myenv (use another conda env)
#         .\install.ps1 -CondaEnv ""    (force venv + system python path)
# ============================================================

param([string]$CondaEnv = "uat", [switch]$NoPause)

$ErrorActionPreference = "Stop"
$Env:PIP_DISABLE_PIP_VERSION_CHECK = 1
$Env:PIP_NO_CACHE_DIR = 1

$PYPI_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple/"
$MIN_VER = [version]"3.10.0"
$MAX_VER = [version]"3.13.0"
$PYTHON = $null

function Test-SuitablePython {
    param([string]$PyPath)
    try {
        $raw = & $PyPath -c "import struct,sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}|{struct.calcsize(chr(80))*8}')"
        if ($LASTEXITCODE -ne 0) { return $false }
        $parts = $raw.Trim() -split "\|"
        $ver = [version]$parts[0]
        return ($ver -ge $MIN_VER -and $ver -lt $MAX_VER -and $parts[1] -eq "64")
    } catch {
        return $false
    }
}

# ---------- 1. prefer conda env ----------
if ($CondaEnv) {
    $candidates = @()
    if ($env:CONDA_PREFIX) { $candidates += (Join-Path $env:CONDA_PREFIX "python.exe") }
    try {
        $base = (& conda info --base 2>$null).Trim()
        if ($base) {
            $candidates += (Join-Path $base "envs\$CondaEnv\python.exe")
            $candidates += (Join-Path $base "python.exe")
        }
    } catch { }
    foreach ($cand in @("E:\MINICONDA", "$env:USERPROFILE\miniconda3", "$env:USERPROFILE\anaconda3", "C:\ProgramData\miniconda3", "C:\ProgramData\Anaconda3")) {
        if ($cand -and (Test-Path $cand)) {
            $candidates += (Join-Path $cand "envs\$CondaEnv\python.exe")
        }
    }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c) -and (Test-SuitablePython $c)) {
            $PYTHON = $c
            Write-Host "Using conda env '$CondaEnv': $PYTHON"
            break
        }
    }
    if (-not $PYTHON) {
        Write-Host "conda env '$CondaEnv' not found or unsuitable (need 64-bit Python 3.10-3.12). Falling back to system Python + venv." -ForegroundColor Yellow
    }
}

# ---------- 2. fallback: system python + venv ----------
$NeedVenv = $false
if (-not $PYTHON) {
    foreach ($name in @("python3.11", "python")) {
        try {
            $cmd = Get-Command $name -ErrorAction Stop
            if (Test-SuitablePython $cmd.Source) { $PYTHON = $cmd.Source; break }
        } catch { }
    }
    if (-not $PYTHON) {
        Write-Host "ERROR: No suitable Python found." -ForegroundColor Red
        Write-Host "Needed: conda env '$CondaEnv' with 64-bit Python 3.10-3.12, or a system 64-bit Python 3.10/3.11." -ForegroundColor Yellow
        if (-not $NoPause) { Read-Host "Press Enter to exit" | Out-Null }
        exit 1
    }
    $NeedVenv = $true
}

$RunPy = $null
if ($NeedVenv) {
    # create project-local venv from the system python
    if (-not (Test-Path "venv")) {
        Write-Host "Creating venv ..."
        & $PYTHON -m venv venv
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: failed to create venv with $PYTHON" -ForegroundColor Red
            if (-not $NoPause) { Read-Host "Press Enter to exit" | Out-Null }
            exit 1
        }
    }
    $RunPy = Join-Path (Get-Location) "venv\Scripts\python.exe"
} else {
    # conda env python used directly (no nested venv)
    $RunPy = $PYTHON
}
if (-not (Test-Path $RunPy)) {
    Write-Host "ERROR: python not found at $RunPy" -ForegroundColor Red
    if (-not $NoPause) { Read-Host "Press Enter to exit" | Out-Null }
    exit 1
}
Write-Host "Install target: $RunPy"

# ---------- 3. install pinned deps ----------
if ($PYPI_MIRROR) {
    & $RunPy -m pip install --upgrade pip -i $PYPI_MIRROR 2>$null
    & $RunPy -m pip install -r requirements.txt -i $PYPI_MIRROR
} else {
    & $RunPy -m pip install --upgrade pip 2>$null
    & $RunPy -m pip install -r requirements.txt
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install failed. If the mirror lacks a wheel (e.g. paddlepaddle), rerun after setting" -ForegroundColor Yellow
    Write-Host "  `$PYPI_MIRROR = `$null  (near top of install.ps1) to use official PyPI." -ForegroundColor Yellow
    if (-not $NoPause) { Read-Host "Press Enter to exit" | Out-Null }
    exit 1
}

# ---------- 4. freeze reproducible snapshot ----------
$lockFile = "requirements.lock.txt"
if (Test-Path $lockFile) { Remove-Item $lockFile -Force }
& $RunPy -m pip freeze > $lockFile

# ---------- 5. record runtime interpreter for run.ps1 ----------
$RunPy | Out-File -FilePath ".runtime_python" -Encoding ascii

Write-Host "Dependency snapshot written to $lockFile (commit it alongside requirements.txt)" -ForegroundColor Green
Write-Host "Interpreter path recorded in .runtime_python" -ForegroundColor Green
Write-Host "Install complete. Run .\run.ps1 to start."
if (-not $NoPause) { Read-Host "Press Enter to exit" | Out-Null }
