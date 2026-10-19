param([string]$Url = 'about:blank')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & node.exe open.mjs $Url
    if ($LASTEXITCODE -ne 0) { throw "CloakBrowser exited with code $LASTEXITCODE" }
} finally {
    Pop-Location
}
