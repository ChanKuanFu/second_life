$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$HealthUrl = 'http://127.0.0.1:5000/api/health'
$PageUrl = 'http://127.0.0.1:5000/'
$StdoutLog = Join-Path $ProjectRoot 'server.stdout.log'
$StderrLog = Join-Path $ProjectRoot 'server.stderr.log'
$PidFile = Join-Path $ProjectRoot 'secondlife.pid'

if (-not (Test-Path -LiteralPath $PythonPath)) {
    $Launcher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $Launcher) { throw 'Python 3 is missing. Install Python 3, then run this launcher again.' }
    & $Launcher.Source -3 -m venv (Join-Path $ProjectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the project Python environment.' }
}

$HasFlask = $false
& $PythonPath -c 'import flask, flask_cors' 2>$null
$HasFlask = ($LASTEXITCODE -eq 0)
if (-not $HasFlask) {
    & $PythonPath -m pip install -r (Join-Path $ProjectRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your internet connection and try again.' }
}

$Ready = $false
try { $Ready = [bool](Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 1).ok } catch { }

if (-not $Ready) {
    $Server = Start-Process -FilePath $PythonPath `
        -ArgumentList 'backend/app.py' `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StdoutLog `
        -RedirectStandardError $StderrLog `
        -PassThru
    Set-Content -LiteralPath $PidFile -Value $Server.Id -Encoding ascii

    for ($Try = 0; $Try -lt 30 -and -not $Ready; $Try++) {
        Start-Sleep -Milliseconds 500
        try { $Ready = [bool](Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 1).ok } catch { }
    }
}

if (-not $Ready) {
    $Details = if (Test-Path -LiteralPath $StderrLog) { Get-Content -LiteralPath $StderrLog -Tail 12 } else { 'No server log was created.' }
    throw "SecondLife did not start. Server details:`n$Details"
}

Start-Process $PageUrl
Write-Host "SecondLife is running at $PageUrl"
Write-Host 'Use stop_secondlife.ps1 when you want to stop the local server.'
