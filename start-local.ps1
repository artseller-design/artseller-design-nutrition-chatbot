param(
  [int]$FrontendPort = 5500,
  [int]$BackendPort = 8000
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command python -ErrorAction Stop).Source
$backendPython = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $backendPython)) {
  $backendPython = $python
}

$frontendListener = Get-NetTCPConnection -LocalPort $FrontendPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $frontendListener) {
  $frontend = Start-Process -FilePath $python `
    -ArgumentList @("-m", "http.server", "$FrontendPort", "--bind", "0.0.0.0", "--directory", (Join-Path $projectRoot "frontend")) `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
  Write-Host "Started frontend PID $($frontend.Id)."
} else {
  Write-Host "Frontend port $FrontendPort is already in use (PID $($frontendListener.OwningProcess)); leaving it running."
}

$backendListener = Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $backendListener) {
  $backend = Start-Process -FilePath $backendPython `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "$BackendPort") `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
  Write-Host "Started backend PID $($backend.Id)."
} else {
  Write-Host "Backend port $BackendPort is already in use (PID $($backendListener.OwningProcess)); leaving it running."
}

Write-Host "Frontend: http://localhost:$FrontendPort/"
Write-Host "Backend docs: http://localhost:$BackendPort/docs"
