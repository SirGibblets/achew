@echo off
setlocal enabledelayedexpansion

echo Starting build...

REM Set default values
set HOST=127.0.0.1
set PORT=8000
set DEBUG=false
set LISTEN_FLAG=

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
if "%~1"=="--debug" (
    set DEBUG=true
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
echo.

REM Check if required dependencies are installed
echo Checking dependencies...

REM Check Node.js
where node >nul 2>&1
if errorlevel 1 (
    echo Node.js is not installed. Please install Node.js first.
    echo For installation instructions, visit: https://nodejs.org/en/download/
    exit /b 1
)

REM Check npm
where npm >nul 2>&1
if errorlevel 1 (
    echo npm is not installed. Please install npm first.
    echo For installation instructions, visit: https://nodejs.org/en/download/
    exit /b 1
)

REM Check ffmpeg
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo ffmpeg is not installed. Please install ffmpeg first.
    echo For installation instructions, visit: https://ffmpeg.org/download.html
    exit /b 1
)

REM Check uv
where uv >nul 2>&1
if errorlevel 1 (
    echo uv is not installed. Please install uv first: visit https://docs.astral.sh/uv/getting-started/installation/
    echo For installation instructions, visit: https://docs.astral.sh/uv/getting-started/installation/
    exit /b 1
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

echo Backend dependencies installed

REM Start the application
echo Starting the application...

REM Add debug flag if enabled
set UVICORN_ARGS=
if "%DEBUG%"=="true" (
    set UVICORN_ARGS=--reload --log-level debug
    echo Debug mode enabled - using auto-reload
)

REM Run the backend server
uv run python -m uvicorn app.main:app --host %HOST% --port %PORT% %UVICORN_ARGS%

:show_usage
echo Usage: %~nx0 [OPTIONS]
echo.
echo Command-line Flags:
echo   --host HOST              Set server host (default: 127.0.0.1)
echo   --port PORT              Set server port (default: 8000)
echo   --listen                 Listen on all interfaces (equivalent to --host 0.0.0.0)
echo   --debug                  Enable debug mode
echo   --help                   Show this help message
echo.
echo Examples:
echo   %~nx0 --host 0.0.0.0 --port 9000
echo   %~nx0 --listen --port 9000
echo   %~nx0 --port 3000
exit /b 0
