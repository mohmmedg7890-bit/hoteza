$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12, then try again.' }
}
$hotezaPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $hotezaPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
$env:DEBUG = '1'
$env:DATABASE_URL = ''
& $hotezaPython manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
if (-not (Test-Path '.local-initialized')) {
    & $hotezaPython manage.py seed_demo
    if ($LASTEXITCODE -eq 0) { New-Item '.local-initialized' -ItemType File | Out-Null }
    else { Write-Host 'Existing database retained. Sign in with your existing account.' }
}
Write-Host 'Open http://127.0.0.1:8000 in your browser. Ctrl+C stops the server.'
& $hotezaPython manage.py runserver 127.0.0.1:8000
