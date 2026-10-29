param(
  [int]$FrontendPort = 5500,
  [int]$BackendPort = 8000
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command python -ErrorAction Stop).Source
$backendPython = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"
$venvConfig = Join-Path $projectRoot "backend\.venv\pyvenv.cfg"
$venvHome = $null
if (Test-Path -LiteralPath $venvConfig) {
  $homeSetting = Get-Content -LiteralPath $venvConfig | Where-Object { $_ -match "^home\s*=" } | Select-Object -First 1
  if ($homeSetting) {
    $venvHome = ($homeSetting -split "=", 2)[1].Trim()
  }
}
$backendPythonReady = (Test-Path -LiteralPath $backendPython) -and $venvHome -and (Test-Path -LiteralPath (Join-Path $venvHome "python.exe"))
$useUv = $false

if (-not $backendPythonReady) {
  $backendPython = $python
  $uv = Get-Command uv -ErrorAction SilentlyContinue
  if ($uv) {
    $useUv = $true
  }
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
  if ($useUv) {
    $backend = Start-Process -FilePath $uv.Source `
      -ArgumentList @(
        "run", "--no-project", "--python", "3.14",
        "--with-requirements", (Join-Path $projectRoot "backend\requirements.txt"),
        "--directory", (Join-Path $projectRoot "backend"),
        "python", "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0", "--port", "$BackendPort"
      ) `
      -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
  } else {
    $backend = Start-Process -FilePath $backendPython `
      -ArgumentList @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "$BackendPort") `
      -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
  }
  Write-Host "Started backend PID $($backend.Id)."
} else {
  Write-Host "Backend port $BackendPort is already in use (PID $($backendListener.OwningProcess)); leaving it running."
}

Write-Host "Frontend: http://localhost:$FrontendPort/"
Write-Host "Backend docs: http://localhost:$BackendPort/docs"
