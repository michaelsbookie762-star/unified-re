$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
  uv venv .venv --python 3.13
  if ($LASTEXITCODE -ne 0) { throw 'Project Python environment creation failed.' }
}
# Install pinned requirements additively; do not sync/remove existing packages.
uv pip install --python $taskPython --require-hashes -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Pinned Python dependency installation failed.' }
$taskRea = Join-Path $PSScriptRoot 'node_modules\rea-agents\package.json'
if (-not (Test-Path -LiteralPath $taskRea)) {
  if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'node_modules')) {
    throw 'Existing node_modules is not the expected managed REA install; preserve it and use a fresh copy of this project.'
  }
  npm ci --ignore-scripts --no-audit --no-fund
  if ($LASTEXITCODE -ne 0) { throw 'Pinned local REA installation failed.' }
}
if ((Get-Content -LiteralPath $taskRea -Raw | ConvertFrom-Json).version -ne '6.5.0') {
  throw 'REA version differs from the reviewed 6.5.0 contract; no files were replaced.'
}
$taskCloak = Join-Path $PSScriptRoot 'cloakbrowser'
if (-not (Test-Path -LiteralPath (Join-Path $taskCloak 'node_modules'))) {
  npm --prefix $taskCloak ci --ignore-scripts --no-audit --no-fund
  if ($LASTEXITCODE -ne 0) { throw 'Pinned CloakBrowser/MCP dependency installation failed.' }
}
& node (Join-Path $taskCloak 'install.mjs')
if ($LASTEXITCODE -ne 0) { throw 'Pinned public CloakBrowser installation failed.' }
& $taskPython -X utf8 scripts/download_model.py
if ($LASTEXITCODE -ne 0) { throw 'Public pinned model integrity/download failed.' }
if (-not (Test-Path -LiteralPath 'backends.json')) {
  Copy-Item -LiteralPath 'examples/backends.rea-only.json' -Destination 'backends.json'
}
& $taskPython -X utf8 scripts/index.py
if ($LASTEXITCODE -ne 0) { throw 'Local semantic index build failed.' }
Write-Output 'Project runtime ready. Run start.ps1 through an MCP client, or scripts/demo.py for the real protocol smoke test.'
