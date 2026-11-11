$ProjectRoot = $PSScriptRoot
$PidFile = Join-Path $ProjectRoot 'secondlife.pid'
$PythonPath = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host 'No SecondLife server PID file was found.'
    exit 0
}

$ServerId = 0
if (-not [int]::TryParse((Get-Content -LiteralPath $PidFile -Raw).Trim(), [ref]$ServerId)) {
    Remove-Item -LiteralPath $PidFile -Force
    throw 'The saved server process ID was invalid.'
}

$Process = Get-CimInstance Win32_Process -Filter "ProcessId=$ServerId" -ErrorAction SilentlyContinue
if ($Process -and $Process.ExecutablePath -eq $PythonPath -and $Process.CommandLine -like '*backend/app.py*') {
    Stop-Process -Id $ServerId -Force
    Write-Host 'SecondLife server stopped.'
} else {
    Write-Host 'The saved server process is no longer running.'
}
Remove-Item -LiteralPath $PidFile -Force
