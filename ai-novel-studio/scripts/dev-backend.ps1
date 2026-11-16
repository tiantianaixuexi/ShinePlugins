<#
.SYNOPSIS
    Start the Python backend for browser-based frontend development.

.DESCRIPTION
    `pnpm dev` proxies /api to http://127.0.0.1:8765 and the web client sends
    the token from VITE_API_TOKEN. This script starts the backend with a fixed
    development token and port so that proxy actually works, and puts the novel
    library in a separate "dev" profile instead of the real one.

    The Tauri shell does NOT use this: it picks its own free port, generates a
    one-shot token and injects both into the backend itself.

.EXAMPLE
    pwsh -File scripts/dev-backend.ps1
#>

[CmdletBinding()]
param(
    [string]$Port = "8765",
    [string]$Token = "dev-token",
    [string]$DataDir = (Join-Path $env:LOCALAPPDATA "AI Novel Studio/dev")
)

$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "..\backend"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "Backend virtualenv not found at $python. Run: uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt"
    exit 1
}

New-Item -ItemType Directory -Path $DataDir -Force | Out-Null

$env:NOVEL_STUDIO_DATA_DIR = $DataDir
$env:NOVEL_STUDIO_AUTH_TOKEN = $Token
$env:NOVEL_STUDIO_PORT = $Port
$env:NOVEL_STUDIO_LOG_LEVEL = if ($env:NOVEL_STUDIO_LOG_LEVEL) { $env:NOVEL_STUDIO_LOG_LEVEL } else { "INFO" }
$env:PYTHONUTF8 = "1"

Write-Host "AI Novel Studio backend" -ForegroundColor Cyan
Write-Host "  URL     : http://127.0.0.1:$Port"
Write-Host "  Token   : $Token"
Write-Host "  Data dir: $DataDir"
Write-Host ""
Write-Host "Frontend: cd desktop; copy .env.example to .env; pnpm dev" -ForegroundColor DarkGray
Write-Host ""

Push-Location $backend
try {
    & $python -m app
}
finally {
    Pop-Location
}