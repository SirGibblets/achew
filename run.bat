@echo off
setlocal enabledelayedexpansion

REM This script's path, folder and name, saved first: the argument parsing below shifts
REM the script's own entry along with the arguments.
set "SELF=%~f0"
set "ROOT=%~dp0"
set "SELF_NAME=%~nx0"

REM Run from the repo root, wherever the script was started from
cd /d "%ROOT%"

echo Starting build...

REM Set default values
set HOST=127.0.0.1
set PORT=8000
set DEBUG=false
set LISTEN_FLAG=
set WORKERS=
set UPDATE=false

REM The arguments to start the app again with, after an update
set "RUN_ARGS=%*"
if defined RUN_ARGS set "RUN_ARGS=!RUN_ARGS:--update=!"

REM Parse command-line arguments
:parse_args
if "%~1"=="" goto :args_done
if "%~1"=="--host" (
    if not "%LISTEN_FLAG%"=="" (
        echo Cannot specify both --host and --listen arguments
        goto :show_usage
    )
    set HOST=%~2
    shift
    shift
    goto :parse_args
)
if "%~1"=="--port" (
    set PORT=%~2
    shift
    shift
    goto :parse_args
)
if "%~1"=="--listen" (
    if not "%HOST%"=="127.0.0.1" (
        echo Cannot specify both --host and --listen arguments
        goto :show_usage
    )
    set HOST=0.0.0.0
    set LISTEN_FLAG=true
    shift
    goto :parse_args
)
if "%~1"=="--workers" (
    set WORKERS=%~2
    shift
    shift
    goto :parse_args
)
if "%~1"=="--debug" (
    set DEBUG=true
    shift
    goto :parse_args
)
if "%~1"=="--update" (
    set UPDATE=true
    shift
    goto :parse_args
)
if "%~1"=="--help" (
    goto :show_usage
)
echo Unknown option: %~1
goto :show_usage

:args_done

echo Server Configuration:
echo   HOST: %HOST%
echo   PORT: %PORT%
echo   DEBUG: %DEBUG%
if "%WORKERS%"=="" (echo   WORKER COUNT: auto) else (echo   WORKER COUNT: %WORKERS%)
echo.

REM Install the pinned uv and Node.js into .toolchain\ and use them for this window only
REM (see scripts\toolchain.ps1). ACHEW_SYSTEM_TOOLS=1 uses your own uv and npm instead.
if "%ACHEW_SYSTEM_TOOLS%"=="1" goto :system_tools
echo Preparing toolchain...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\toolchain.ps1"
if errorlevel 1 (
    echo Install uv and Node.js yourself, then run again with ACHEW_SYSTEM_TOOLS=1.
    exit /b 1
)
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%ROOT%toolchain.env") do set "%%A=%%B"
set "TOOLCHAIN_DIR=%ROOT%.toolchain"
set "PATH=%TOOLCHAIN_DIR%\uv-%UV_VERSION%-x86_64-pc-windows-msvc;%TOOLCHAIN_DIR%\node-v%NODE_VERSION%-win-x64;%PATH%"
REM Keep uv's Python, cache and any tool installs inside the project, and never use
REM (or register) a system Python. x64 Python even on Windows on ARM, to match the
REM x64-only wheels (see scripts\toolchain.ps1).
set "UV_CACHE_DIR=%TOOLCHAIN_DIR%\cache\uv"
set "UV_PYTHON_INSTALL_DIR=%TOOLCHAIN_DIR%\python"
set "UV_TOOL_DIR=%TOOLCHAIN_DIR%\uv-tools"
set "UV_MANAGED_PYTHON=1"
set "UV_PYTHON=cpython-%PYTHON_VERSION%-windows-x86_64-none"
set "UV_PYTHON_INSTALL_BIN=0"
set "UV_PYTHON_INSTALL_REGISTRY=0"
REM npm's cache and logs (otherwise %LOCALAPPDATA%\npm-cache), and no update or funding notices.
set "npm_config_cache=%TOOLCHAIN_DIR%\cache\npm"
set "npm_config_update_notifier=false"
set "npm_config_fund=false"
goto :toolchain_done

:system_tools
where npm >nul 2>&1
if errorlevel 1 (
    echo ACHEW_SYSTEM_TOOLS=1 is set, but npm is not installed. Install Node.js ^(which includes npm^) first.
    echo For installation instructions, visit: https://nodejs.org/en/download/
    exit /b 1
)
where uv >nul 2>&1
if errorlevel 1 (
    echo ACHEW_SYSTEM_TOOLS=1 is set, but uv is not installed. Install uv first.
    echo For installation instructions, visit: https://docs.astral.sh/uv/getting-started/installation/
    exit /b 1
)

:toolchain_done

REM Update, then start over with the updated scripts. The whole block is read before it
REM runs, so the update rewriting this file can't change what runs next.
if "%UPDATE%"=="true" (
    echo Updating Achew...
    REM Runs before the backend's dependencies are installed, so it only needs Python itself
    if defined UV_PYTHON (set "UPDATER_PYTHON=!UV_PYTHON!") else (set "UPDATER_PYTHON=>=3.11")
    uv run --no-project --python "!UPDATER_PYTHON!" python -I backend\app\core\updater.py
    if errorlevel 1 exit /b 1
    call "%SELF%" %RUN_ARGS%
    exit /b
)

REM Install frontend dependencies
echo Installing frontend dependencies...
cd frontend
call npm install
if errorlevel 1 (
    echo Failed to install frontend dependencies
    cd ..
    exit /b 1
)

REM Build frontend
echo Building frontend...
call npm run build
if errorlevel 1 (
    echo Failed to build frontend
    cd ..
    exit /b 1
)

echo Frontend build completed
cd ..

REM Install backend dependencies
echo Installing backend dependencies...
cd backend
uv sync --frozen
if errorlevel 1 (
    echo Failed to install backend dependencies
    cd ..
    exit /b 1
)

REM Achew installs its own ffmpeg on supported platforms; elsewhere it needs one on PATH
REM or in ACHEW_FFMPEG. The check prints instructions when neither works.
uv run --frozen python -m app.core.ffmpeg
if errorlevel 1 (
    echo ffmpeg is required.
    cd ..
    exit /b 1
)

echo Backend dependencies installed

REM Start the application
echo Starting the application...

REM Add debug flag if enabled
set UVICORN_ARGS=
if "%DEBUG%"=="true" (
    set UVICORN_ARGS=--reload --log-level debug
    echo Debug mode enabled - using auto-reload
)

if not "%WORKERS%"=="" set ACHEW_WORKER_COUNT=%WORKERS%

REM Lets an in-app update restart Achew through this script. Not with --reload, whose file
REM watcher would restart the server by itself partway through an update.
set ACHEW_RESTART_FILE=
if "%DEBUG%"=="false" set "ACHEW_RESTART_FILE=%ROOT%.toolchain\restart-requested"
if defined ACHEW_RESTART_FILE if exist "%ACHEW_RESTART_FILE%" del "%ACHEW_RESTART_FILE%"

REM Run the backend server. After an in-app update, start this script over so the new
REM version's dependencies and frontend get installed. In parentheses so cmd reads the whole
REM block before running it, since the update can rewrite this file while the server runs.
(
    uv run --frozen python -m uvicorn app.main:app --host %HOST% --port %PORT% %UVICORN_ARGS%
    if defined ACHEW_RESTART_FILE if exist "!ACHEW_RESTART_FILE!" (
        del "!ACHEW_RESTART_FILE!"
        echo Restarting Achew to finish the update...
        call "%SELF%" %RUN_ARGS%
    )
    exit /b
)

:show_usage
echo Usage: %SELF_NAME% [OPTIONS]
echo.
echo Command-line Flags:
echo   --host HOST              Set server host (default: 127.0.0.1)
echo   --port PORT              Set server port (default: 8000)
echo   --listen                 Listen on all interfaces (equivalent to --host 0.0.0.0)
echo   --workers N              Number of parallel audio workers (default: auto-detect)
echo   --debug                  Enable debug mode
echo   --update                 Update Achew to the latest version, then start it
echo   --help                   Show this help message
echo.
echo Examples:
echo   %SELF_NAME% --host 0.0.0.0 --port 9000
echo   %SELF_NAME% --listen --port 9000
echo   %SELF_NAME% --port 3000
echo   %SELF_NAME% --workers 2
exit /b 0
