# Project-local toolchain for run.bat (the Windows counterpart of toolchain.sh).
#
# Downloads the uv and Node.js versions pinned in toolchain.env into .toolchain\ and
# verifies them against the pinned SHA-256. run.bat then puts them on PATH for its own
# process only; nothing is installed system-wide and no user settings are changed.

$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1's progress bar slows Invoke-WebRequest to a crawl.
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

trap {
    Write-Host $_ -ForegroundColor Red
    exit 1
}

$Root = Split-Path -Parent $PSScriptRoot
$ToolchainDir = Join-Path $Root '.toolchain'

$Pins = @{}
foreach ($line in Get-Content (Join-Path $Root 'toolchain.env')) {
    if ($line -match '^\s*([A-Za-z0-9_]+)=(.*)$') { $Pins[$Matches[1]] = $Matches[2].Trim() }
}

# x64 tools on every Windows machine: the bundled ffmpeg and several Python wheels only
# ship for win_amd64, and Windows on ARM runs x64 binaries under emulation.
$UvTarget = 'x86_64-pc-windows-msvc'
$NodeTarget = 'win-x64'

function Install-Tool($Name, $Url, $Sha256, $Dest) {
    if (-not $Sha256) { throw "No pinned checksum for $Name." }
    New-Item -ItemType Directory -Force -Path $ToolchainDir | Out-Null
    $tmp = Join-Path $ToolchainDir (".download." + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        Write-Host "Downloading $Name..."
        $zip = Join-Path $tmp 'archive.zip'
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $zip
        $actual = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower()
        if ($actual -ne $Sha256) { throw "Checksum mismatch for $Name (expected $Sha256, got $actual)." }
        $out = Join-Path $tmp 'x'
        New-Item -ItemType Directory -Path $out | Out-Null
        # Windows' own tar.exe (10 1803+) is much faster than Expand-Archive on Node's many
        # files. Named by path, since a GNU tar from MSYS2/Cygwin on PATH can't read zips.
        $tar = Join-Path $env:SystemRoot 'System32\tar.exe'
        if (Test-Path $tar) {
            & $tar -xf $zip -C $out
            if ($LASTEXITCODE -ne 0) { throw "Failed to extract $Name." }
        } else {
            Expand-Archive -Path $zip -DestinationPath $out
        }
        if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
        # Node's zip has one top-level folder; uv's zip holds the executables directly.
        $entries = @(Get-ChildItem $out)
        $src = if ($entries.Count -eq 1 -and $entries[0].PSIsContainer) { $entries[0].FullName } else { $out }
        Move-Item $src $Dest
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

function Remove-OtherVersions($Keep, $NameRegex) {
    Get-ChildItem -Path $ToolchainDir -Directory |
        Where-Object { $_.Name -match $NameRegex -and $_.FullName -ne $Keep } |
        Remove-Item -Recurse -Force
}

$uvVersion = $Pins['UV_VERSION']
$uvHome = Join-Path $ToolchainDir "uv-$uvVersion-$UvTarget"
if (-not (Test-Path (Join-Path $uvHome 'uv.exe'))) {
    Install-Tool "uv $uvVersion" `
        "https://github.com/astral-sh/uv/releases/download/$uvVersion/uv-$UvTarget.zip" `
        $Pins["UV_SHA256_$($UvTarget -replace '-', '_')"] $uvHome
    Remove-OtherVersions $uvHome "^uv-\d.*-$UvTarget`$"
}

$nodeVersion = $Pins['NODE_VERSION']
$nodeHome = Join-Path $ToolchainDir "node-v$nodeVersion-$NodeTarget"
if (-not (Test-Path (Join-Path $nodeHome 'node.exe'))) {
    Install-Tool "Node.js $nodeVersion" `
        "https://nodejs.org/dist/v$nodeVersion/node-v$nodeVersion-$NodeTarget.zip" `
        $Pins["NODE_SHA256_$($NodeTarget -replace '-', '_')"] $nodeHome
    Remove-OtherVersions $nodeHome "^node-v\d.*-$NodeTarget`$"
}
