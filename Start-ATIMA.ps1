# Safe, local-only Windows launcher for the ATIMA-FL experiment designer.
# It never changes Git branches, removes an environment or kills another process.
[CmdletBinding()]
param(
    [switch]$Doctor,
    [switch]$NoInstall,
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [string]$Workspace = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvDir = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$manifest = Join-Path $projectRoot "pyproject.toml"
$stamp = Join-Path $venvDir ".atima-install-state"

function Run-Checked {
    param([string]$Exe, [string[]]$Arguments, [string]$Description)
    Write-Host "[ATIMA] $Description"
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed (exit code $LASTEXITCODE)."
    }
}

function Find-CompatiblePython {
    $candidates = @(
        @{ Executable = "py"; Prefix = @("-3.12") },
        @{ Executable = "py"; Prefix = @("-3.11") },
        @{ Executable = "python"; Prefix = @() }
    )
    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Executable -ErrorAction SilentlyContinue)) {
            continue
        }
        $prefix = [string[]]$candidate.Prefix
        $previous = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $version = & $candidate.Executable @prefix -c "import sys; print('%s.%s' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $version -in @("3.11", "3.12")) {
                return @{ Executable = $candidate.Executable; Prefix = $prefix }
            }
        } catch {
            # Try the next Python on PATH rather than using an unsupported interpreter.
        } finally {
            $ErrorActionPreference = $previous
        }
    }
    throw "Python 3.11 or 3.12 is required. Install Python 3.12 from python.org, with the Python launcher enabled."
}

try {
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
        throw "pyproject.toml not found next to launcher. Run this from the ATIMA-FL repository."
    }
    Write-Host "[ATIMA] Project: $projectRoot"

    if (Get-Command git -ErrorAction SilentlyContinue) {
        $branchName = & git -C $projectRoot branch --show-current 2>$null
        $revision = & git -C $projectRoot rev-parse --short HEAD 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[ATIMA] Git: $branchName @ $revision (no automatic Git changes)"
        }
    }

    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        if (Test-Path -LiteralPath $venvDir) {
            throw "An incomplete .venv exists. Rename it manually after backing up anything important, then rerun the launcher."
        }
        if ($NoInstall) {
            throw "Local .venv is missing. Retry without -NoInstall to create it automatically."
        }
        $systemPython = Find-CompatiblePython
        $args = [string[]]($systemPython.Prefix + @("-m", "venv", $venvDir))
        Run-Checked -Exe $systemPython.Executable -Arguments $args -Description "Creating isolated Python environment"
    }

    # Existing environments are never silently replaced or repaired.
    Run-Checked -Exe $venvPython -Arguments @(
        "-c", "import sys; assert sys.version_info[:2] in ((3,11),(3,12)), 'ATIMA requires Python 3.11 or 3.12'; print('Python:', sys.version.split()[0])"
    ) -Description "Checking local Python"

    $digest = (Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash
    $expectedStamp = "$projectRoot|$digest"
    $needsInstall = -not (Test-Path -LiteralPath $stamp -PathType Leaf)
    if (-not $needsInstall) {
        $needsInstall = (Get-Content -LiteralPath $stamp -Raw).Trim() -ne $expectedStamp
    }
    if (-not $needsInstall) {
        & $venvPython -c "import atima_fl, importlib.metadata; importlib.metadata.version('atima-fl')" 2>$null
        $needsInstall = $LASTEXITCODE -ne 0
    }
    if ($needsInstall) {
        if ($NoInstall) {
            throw "The local installation is absent or stale. Retry without -NoInstall."
        }
        Run-Checked -Exe $venvPython -Arguments @("-m", "pip", "install", "-e", $projectRoot) -Description "Installing/updating editable ATIMA-FL dependencies"
        # Only mark a successful installation as current.
        Set-Content -LiteralPath $stamp -Value $expectedStamp -Encoding Ascii
    } else {
        Write-Host "[ATIMA] Local installation already up to date."
    }

    Run-Checked -Exe $venvPython -Arguments @(
        "-c", "from atima_fl.core.configuration import ExperimentConfig; ExperimentConfig().validate(); print('ATIMA component registry: OK')"
    ) -Description "Checking package and component registry"

    if ([string]::IsNullOrWhiteSpace($Workspace)) {
        $Workspace = Join-Path (Split-Path -Parent $projectRoot) "ATIMA-workspace"
    }
    Write-Host "[ATIMA] Workspace: $Workspace"
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -gt 0) {
        $owners = ($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
        Write-Warning "Port $Port is in use by PID(s): $owners. The launcher will not stop these processes."
        if (-not $Doctor) { throw "Stop the existing service or start with -Port <another-port>." }
    } else {
        Write-Host "[ATIMA] Port $Port available."
    }

    if ($Doctor) {
        Write-Host "[ATIMA] Doctor checks completed. No server launched."
        exit 0
    }

    Write-Host "[ATIMA] Opening loopback-only webapp: http://127.0.0.1:$Port/"
    Run-Checked -Exe $venvPython -Arguments @(
        "-m", "atima_fl.cli", "ui", "--workspace", $Workspace, "--port", "$Port"
    ) -Description "Starting ATIMA-FL"
} catch {
    Write-Error "[ATIMA] $($_.Exception.Message)"
    exit 1
}
