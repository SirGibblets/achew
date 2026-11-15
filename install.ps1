# Installs Achew (or updates an existing install), then starts it. In PowerShell:
#
#   irm https://raw.githubusercontent.com/SirGibblets/achew/main/install.ps1 | iex
#
# Installs the latest release into %USERPROFILE%\achew, or into ACHEW_DIR if set: a git clone
# checked out at the release's tag when git is available, otherwise the release's files,
# downloaded. Either way, run.bat then downloads the tools Achew needs (uv, Node.js and Python)
# into that folder, and nothing outside it changes.
#
# ACHEW_GIT_URL, ACHEW_LATEST_RELEASE_URL and ACHEW_RELEASE_ARCHIVE_URL override where Achew
# comes from (for forks, or testing); the last two are shared with backend\app\core\updater.py.
#
# Runs in a script block so nothing leaks into the session that runs it with iex, and returns
# instead of exiting, which would close that session's window.

& {
    $ErrorActionPreference = 'Stop'
    # Windows PowerShell 5.1's progress bar slows Invoke-WebRequest to a crawl.
    $ProgressPreference = 'SilentlyContinue'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    $dir = if ($env:ACHEW_DIR) { $env:ACHEW_DIR } else { Join-Path $HOME 'achew' }
    # A full path, since .NET calls below resolve relative paths differently than PowerShell
    $dir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($dir)
    $gitUrl = if ($env:ACHEW_GIT_URL) { $env:ACHEW_GIT_URL } else { 'https://github.com/SirGibblets/achew.git' }
    $latestReleaseUrl = if ($env:ACHEW_LATEST_RELEASE_URL) { $env:ACHEW_LATEST_RELEASE_URL } else {
        'https://api.github.com/repos/SirGibblets/achew/releases/latest'
    }
    $releaseArchiveUrl = if ($env:ACHEW_RELEASE_ARCHIVE_URL) { $env:ACHEW_RELEASE_ARCHIVE_URL } else {
        'https://github.com/SirGibblets/achew/archive/refs/tags/{tag}.tar.gz'
    }
    $runBat = Join-Path $dir 'run.bat'

    try {
        if (Test-Path $runBat) {
            # Achew 1.13 and earlier have no updater, and their run.bat rejects --update
            if (-not (Test-Path (Join-Path $dir 'backend\app\core\updater.py'))) {
                throw "The Achew in $dir is too old to update itself. Update it once with git: cd `"$dir`"; git checkout main; git pull; .\run.bat"
            }
            Write-Host "Achew is already installed in $dir, so updating it." -ForegroundColor Cyan
            & $runBat --update
            return
        }
        if ((Test-Path $dir) -and (Get-ChildItem -Force $dir | Select-Object -First 1)) {
            throw "$dir already exists and isn't an Achew install. Set ACHEW_DIR to install somewhere else."
        }

        Write-Host 'Looking up the latest Achew release...' -ForegroundColor Cyan
        $tag = (Invoke-RestMethod -Uri $latestReleaseUrl -Headers @{ 'User-Agent' = 'achew-installer' }).tag_name
        if (-not $tag) { throw "Couldn't find the latest Achew release." }

        Write-Host "Downloading Achew $tag into $dir..." -ForegroundColor Cyan
        if (Get-Command git -ErrorAction SilentlyContinue) {
            git -c advice.detachedHead=false clone --quiet --branch $tag $gitUrl $dir
            if ($LASTEXITCODE -ne 0) { throw 'git clone failed.' }
        } else {
            $toolchain = Join-Path $dir '.toolchain'
            New-Item -ItemType Directory -Force -Path $toolchain | Out-Null
            $archive = Join-Path $toolchain 'release.tar.gz'
            Invoke-WebRequest -UseBasicParsing -Uri $releaseArchiveUrl.Replace('{tag}', $tag) -OutFile $archive
            # Windows' own tar.exe (10 1803+), by path: a GNU tar from MSYS2/Cygwin can't take Windows paths
            $tar = Join-Path $env:SystemRoot 'System32\tar.exe'
            & $tar -xzf $archive -C $dir --strip-components 1
            if ($LASTEXITCODE -ne 0) { throw "Couldn't unpack Achew $tag." }
            # Lists the release's files, so updates can remove files that later releases drop
            $files = & $tar -tzf $archive | ForEach-Object { $_ -replace '^[^/]*/', '' } |
                Where-Object { $_ -and -not $_.EndsWith('/') }
            [IO.File]::WriteAllLines((Join-Path $toolchain 'install-manifest.txt'), [string[]]$files)
            Remove-Item $archive
        }

        Write-Host "Installed Achew in $dir. To start it again later, run: $runBat" -ForegroundColor Cyan
        Write-Host "Starting Achew. Open http://localhost:8000 once it's ready." -ForegroundColor Cyan
        & $runBat
    } catch {
        Write-Host $_ -ForegroundColor Red
    }
}
