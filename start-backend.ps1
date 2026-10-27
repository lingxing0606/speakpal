$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    Write-Host '未找到虚拟环境，请先运行 setup.ps1' -ForegroundColor Red
    exit 1
}
Set-Location (Join-Path $root 'backend')
& $py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
