$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$node = Join-Path $root 'tools\node'
if (Test-Path $node) {
    $env:PATH = $node + ';' + $env:PATH
}
Set-Location (Join-Path $root 'frontend')
& npm run dev
