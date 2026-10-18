$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
& (Join-Path $taskRoot '.venv\Scripts\python.exe') -X utf8 (Join-Path $taskRoot 'scripts\serve.py')
exit $LASTEXITCODE
