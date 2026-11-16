<#
.SYNOPSIS
    Start the Python backend and the Vite dev server together.

.DESCRIPTION
    Browser development needs two processes: the FastAPI sidecar on :8765 and
    Vite on :1420 (which proxies /api to the sidecar). This script starts both,
    creates `desktop/.env` with the matching dev token on first run, and stops
    the backend when the frontend exits.

    The Tauri shell (`pnpm tauri dev`) does NOT need this: Rust allocates a free
    port, generates a one-shot token and manages the backend lifecycle itself.

.EXAMPLE
    pwsh -File scripts/dev.ps1
#>

[CmdletBinding()]
param(
    [string]$Port = "8765",
    [string]$Token = "dev-token"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$desktop = Join-Path $root "desktop"
$backendScript = Join-Path $PSScriptRoot "dev-backend.ps1"

# ---------------------------------------------------------------------------
# The web client reads its token from `desktop/.env` (Vite injects it).
# ---------------------------------------------------------------------------
$envFile = Join-Path $desktop ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $desktop ".env.example") $envFile
    Write-Host "已创建 desktop/.env（开发用 token: $Token）" -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------
$listening = Get-NetTCPConnection -State Listen -LocalPort ([int]$Port) -ErrorAction SilentlyContinue
$backend = $null

if ($listening) {
    Write-Host "端口 $Port 已在监听，跳过启动后端（复用现有进程）" -ForegroundColor Yellow
}
else {
    $ps = (Get-Process -Id $PID).Path
    $backend = Start-Process -FilePath $ps `
        -ArgumentList @('-NoProfile', '-File', $backendScript, '-Port', $Port, '-Token', $Token) `
        -PassThru -WindowStyle Minimized
    Write-Host "后端已启动 (pid $($backend.Id))  -> http://127.0.0.1:$Port" -ForegroundColor Cyan
}

Write-Host "前端启动中            -> http://127.0.0.1:1420" -ForegroundColor Cyan
Write-Host ""

try {
    Push-Location $desktop
    try {
        & pnpm dev
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "pnpm dev 退出码 $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($backend -and -not $backend.HasExited) {
        Write-Host ""
        Write-Host "正在停止后端 (pid $($backend.Id))…" -ForegroundColor DarkGray
        & taskkill /PID $backend.Id /T /F 2>&1 | Out-Null
    }
}