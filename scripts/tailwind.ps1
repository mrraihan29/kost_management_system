param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$TailwindArgs
)

$ErrorActionPreference = "Stop"
$Version = "v4.3.5"
$ExpectedSha256 = "2803583268c53f4713e89943e211081fddb186c0a4a7d07b5c342c6ae853ec95"
$Root = Split-Path -Parent $PSScriptRoot
$BinDir = Join-Path $Root ".bin"
$BinPath = Join-Path $BinDir "tailwindcss-$Version.exe"
$Url = "https://github.com/tailwindlabs/tailwindcss/releases/download/$Version/tailwindcss-windows-x64.exe"

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
if (-not (Test-Path $BinPath)) {
    Write-Host "Downloading Tailwind CSS $Version..."
    $TmpPath = "$BinPath.tmp"
    curl.exe -fsSL $Url -o $TmpPath
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -Force $TmpPath -ErrorAction SilentlyContinue
        exit $LASTEXITCODE
    }
    Move-Item -Force $TmpPath $BinPath
}

$ActualSha256 = (Get-FileHash -Path $BinPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualSha256 -ne $ExpectedSha256) {
    Remove-Item -Force $BinPath -ErrorAction SilentlyContinue
    throw "SHA-256 mismatch for $BinPath (expected $ExpectedSha256, got $ActualSha256)"
}

& $BinPath -i (Join-Path $Root "static/css/input.css") -o (Join-Path $Root "static/css/app.css") --minify @TailwindArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
