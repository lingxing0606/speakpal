$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. 后端 Python 环境
$python = 'D:\python\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
$venv = Join-Path $root 'backend\.venv'
if (-not (Test-Path $venv)) {
    & $python -m venv --without-pip $venv
}
$py = Join-Path $venv 'Scripts\python.exe'
$tmp = Join-Path $root '.tmp'
New-Item -ItemType Directory -Force $tmp | Out-Null
$env:TEMP = $tmp
$env:TMP = $tmp
& $py -m ensurepip --upgrade
& $py -m pip install -r (Join-Path $root 'backend\requirements.txt')

# 2. 前端 Node 依赖
$node = Join-Path $root 'tools\node'
if (Test-Path $node) { $env:PATH = $node + ';' + $env:PATH }
Set-Location (Join-Path $root 'frontend')
& npm install

Write-Host '安装完成。' -ForegroundColor Green
