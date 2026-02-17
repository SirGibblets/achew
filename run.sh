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
    echo -e "${YELLOW}️ $1${NC}"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Command-line Flags:"
    echo "  --host HOST              Set server host (default: 127.0.0.1)"
    echo "  --port PORT              Set server port (default: 8000)"
    echo "  --listen                 Listen on all interfaces (equivalent to --host 0.0.0.0)"
    echo "  --debug                  Enable debug mode"
    echo "  --help                   Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --host 0.0.0.0 --port 9000"
    echo "  $0 --listen --port 9000"
    echo "  $0 --port 3000"
}

# Default arguments
HOST="127.0.0.1"
PORT="8000"
DEBUG="false"
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
        --debug)
            DEBUG="true"
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

log_info "Server Configuration:"
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

# Build frontend
log_info "Building frontend..."
npm run build

log_success "Frontend build completed"
cd ..

# Install backend dependencies
log_info "Building backend..."
log_info "Installing backend dependencies..."
cd backend
uv sync --frozen

log_success "Backend dependencies installed"

# Start the application
log_info "Starting the application..."

# Add debug flag if enabled
UVICORN_ARGS=""
if [ "$DEBUG" = "true" ]; then
    UVICORN_ARGS="--reload --log-level debug"
    log_warning "Debug mode enabled - using auto-reload"
    export DEBUG="true"
else
    export DEBUG="false"
fi

# Run the backend server
uv run python -m uvicorn app.main:app --host "$HOST" --port "$PORT" $UVICORN_ARGS