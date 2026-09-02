# ============================================================
# UmamusumeAutoTrainer - one-click install (Windows)
# Requires: 64-bit Python 3.10 / 3.11 (3.11 preferred)
#   - paddlepaddle==2.6.2 has no cp313 wheel -> do NOT use Python 3.12+/3.13
# Behavior:
#   1. locate a suitable python (3.11 first, fallback 3.10)
#   2. create project-local venv
#   3. install requirements.txt (top-level pins)
#   4. freeze full dependency snapshot into requirements.lock.txt
#      (committed, used on later installs for reproducibility)
# Mirror: default tsinghua (China). Switch PYPI_MIRROR below to use pypi.org.
# ============================================================

$ErrorActionPreference = "Stop"
$Env:PIP_DISABLE_PIP_VERSION_CHECK = 1
$Env:PIP_NO_CACHE_DIR = 1

# Set to $null to use the official PyPI index
$PYPI_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple/"
$PYTHON = $null
$MIN_VER = [version]"3.10.0"
$MAX_VER = [version]"3.13.0"

function Find-Python {
    param([string]$Name)
    try {
        $cmd = Get-Command $Name -ErrorAction Stop
        $raw = & $cmd.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
        $ver = [version]$raw.Trim()
        if ($ver -ge $MIN_VER -and $ver -lt $MAX_VER) {
            return $cmd.Source
        }
    } catch { }
    return $null
}

# 1. locate python: prefer python3.11, then python, then py -3.11 / -3.10
foreach ($name in @("python3.11", "python")) {
    $found = Find-Python $name
    if ($found) { $PYTHON = $found; break }
}
if (-not $PYTHON) {
    try {
        $py = Get-Command "py" -ErrorAction Stop
        foreach ($tag in @("3.11", "3.10")) {
            $raw = & $py.Source "-$tag" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $ver = [version]$raw.Trim()
                if ($ver -ge $MIN_VER -and $ver -lt $MAX_VER) {
                    $PYTHON = "$($py.Source) -$tag"
                    break
                }
            }
        }
    } catch { }
}
if (-not $PYTHON) {
    Write-Host "ERROR: No suitable Python found." -ForegroundColor Red
    Write-Host "Required: 64-bit Python 3.10 or 3.11 (3.11 preferred)." -ForegroundColor Yellow
    Write-Host "Python 3.12+/3.13 is NOT supported (paddlepaddle==2.6.2 provides no wheel for it)." -ForegroundColor Yellow
    Write-Host "Install Python 3.11 from https://www.python.org/downloads/ and add it to PATH, then rerun."
    Read-Host "Press Enter to exit" | Out-Null
    exit 1
}
Write-Host "Using Python: $PYTHON"
& $PYTHON -c "import struct; assert struct.calcsize('P') == 8, 'not 64-bit'" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Python must be 64-bit." -ForegroundColor Red
    Read-Host "Press Enter to exit" | Out-Null
    exit 1
}

# 2. create venv
if (-not (Test-Path -Path "venv")) {
    Write-Host "Creating venv ..."
    & $PYTHON -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: failed to create venv with $PYTHON" -ForegroundColor Red
        Read-Host "Press Enter to exit" | Out-Null
        exit 1
    }
}

$VenvPython = Join-Path (Get-Location) "venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "ERROR: venv\Scripts\python.exe missing after venv creation" -ForegroundColor Red
    Read-Host "Press Enter to exit" | Out-Null
    exit 1
}

# 3. upgrade pip then install pinned deps
$upgradeArgs = @($VenvPython, "-m", "pip", "install", "--upgrade", "pip")
if ($PYPI_MIRROR) {
    $upgradeArgs += @("-i", $PYPI_MIRROR)
}
& $upgradeArgs 2>$null

$reqFile = "requirements.txt"
$installArgs = @($VenvPython, "-m", "pip", "install", "-r", $reqFile)
if ($PYPI_MIRROR) {
    $installArgs += @("-i", $PYPI_MIRROR)
}
& $installArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install failed. If the mirror lacks a wheel (e.g. paddlepaddle), rerun after setting" -ForegroundColor Yellow
    Write-Host "  `$PYPI_MIRROR = `$null  (line ~25 of install.ps1) to use the official PyPI index." -ForegroundColor Yellow
    Read-Host "Press Enter to exit" | Out-Null
    exit 1
}

# 4. freeze reproducible snapshot (commit it alongside requirements.txt)
$lockFile = "requirements.lock.txt"
if (Test-Path $lockFile) {
    Remove-Item $lockFile -Force
}
& $VenvPython -m pip freeze > $lockFile
Write-Host "Dependency snapshot written to $lockFile (commit it alongside requirements.txt)" -ForegroundColor Green
Write-Host "Install complete. Run .\run.ps1 to start."
Read-Host "Press Enter to exit" | Out-Null
