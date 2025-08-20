#!/bin/bash

set -e  # Exit on any error

echo "Starting build..."

# Colors for output
GREEN='\033[0;32m'
CYAN='\033[0;96m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions to print colored output
log_info() {
    echo -e "${CYAN} $1${NC}"
}

log_success() {
    echo -e "${GREEN} $1${NC}"
}

log_error() {
    echo -e "${RED} $1${NC}"
}

log_warning() {
    echo -e "${YELLOW} $1${NC}"
}

# Function to cleanup background processes on exit
cleanup() {
    log_info "Shutting down development servers..."
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    exit 0
}

# Set up cleanup trap
trap cleanup SIGINT SIGTERM

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Command-line Flags:"
    echo "  --host HOST              Set backend server host (default: 127.0.0.1)"
    echo "  --port PORT              Set backend server port (default: 8000)"
    echo "  --listen                 Listen on all interfaces (equivalent to --host 0.0.0.0)"
    echo "  --no-debug               Disable debug mode"
    echo "  --help                   Show this help message"
    echo ""
    echo "Development servers:"
    echo "  - Frontend (Vite): http://localhost:5173"
    echo "  - Backend (FastAPI): http://localhost:8000 (or configured port)"
    echo ""
    echo "Examples:"
    echo "  $0 --host 0.0.0.0 --port 9000"
    echo "  $0 --listen --port 9000"
    echo "  $0 --port 3000"
}

# Default arguments
HOST="127.0.0.1"
PORT="8000"
DEBUG="true"
LISTEN_FLAG=""

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            if [ -n "$LISTEN_FLAG" ]; then
                log_error "Cannot specify both --host and --listen arguments"
                show_usage
                exit 1
            fi
            HOST="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --listen)
            if [ "$HOST" != "127.0.0.1" ]; then
                log_error "Cannot specify both --host and --listen arguments"
                show_usage
                exit 1
            fi
            HOST="0.0.0.0"
            LISTEN_FLAG="true"
            shift
            ;;
        --no-debug)
            DEBUG="false"
            shift
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

log_info "Development Server Configuration:"
log_info "  HOST: $HOST"
log_info "  PORT: $PORT"
log_info "  DEBUG: $DEBUG"
log_info ""

# Check if required dependencies are installed
log_info "Checking dependencies..."

# Check Node.js
if ! command -v node &> /dev/null; then
    log_error "Node.js is not installed. Please install Node.js first."
    log_error "For installation instructions, visit: https://nodejs.org/en/download/"
    exit 1
fi

# Check npm
if ! command -v npm &> /dev/null; then
    log_error "npm is not installed. Please install npm first."
    log_error "For installation instructions, visit: https://nodejs.org/en/download/"
    exit 1
fi

# Check ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    log_error "ffmpeg is not installed. Please install ffmpeg first."
    log_error "For installation instructions, visit: https://ffmpeg.org/download.html"
    exit 1
fi

# Check uv
if ! command -v uv &> /dev/null; then
    log_error "uv is not installed. Please install uv first."
    log_error "For installation instructions, visit: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# Install frontend dependencies
log_info "Installing frontend dependencies..."
cd frontend
npm install
cd ..

# Install backend dependencies (including dev dependencies)
log_info "Installing backend dependencies (including dev tools)..."
cd backend
uv sync --all-extras
cd ..

log_success "Dependencies installed"

# Start frontend development server in background
log_info "Starting frontend development server (Vite)..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

# Give frontend server time to start
sleep 3

# Start backend development server in background
log_info "Starting backend development server (FastAPI with auto-reload)..."
cd backend

# Build uvicorn command with debug settings
UVICORN_ARGS="--reload --host $HOST --port $PORT"
if [ "$DEBUG" = "true" ]; then
    UVICORN_ARGS="$UVICORN_ARGS --log-level debug"
fi

uv run python -m uvicorn app.main:app $UVICORN_ARGS &
BACKEND_PID=$!
cd ..

# Give backend server time to start
sleep 5

log_success "Development servers started!"
log_info "Frontend (Vite): http://localhost:5173"
log_info "Backend (FastAPI): http://$HOST:$PORT"
log_warning "Use Ctrl+C to stop both servers"

# Wait for user to stop the servers
wait $FRONTEND_PID $BACKEND_PID