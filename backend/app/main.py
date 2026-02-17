import os
import asyncio
import logging

# Configure logging before any other imports
# noinspection SpellCheckingInspection
debug_mode = os.getenv("DEBUG", "false").lower() == "true"
logging.basicConfig(
    level=logging.DEBUG if debug_mode else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import core, chapters, audio, config, audiobookshelf, pipeline
from .core.config import get_settings
from .models.websocket import WSMessage, WSMessageType
from .app import get_app_state

logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()


# noinspection PyUnusedLocal
@asynccontextmanager
async def lifespan(achew_app: FastAPI):
    """Application lifespan context manager"""
    # Startup
    logger.info("Starting achew")
    logger.info(f"CORS origins: {settings.cors_origins_list}")

    # Check API configuration
    from .core.config import is_abs_configured

    if is_abs_configured():
        logger.info("ABS configuration found and loaded")
    else:
        logger.warning("ABS configuration missing - configuration required via web UI")

    if static_dir:
        logger.info(f"Frontend found at {static_dir}")
    else:
        logger.warning(
            "Frontend not built - API only mode. Run 'npm run build' in frontend directory or use './run.sh' from project root."
        )

    # Initialize app state
    get_app_state()
    logger.info("App state initialized")

    yield

    # Shutdown
    logger.info("Shutting down achew")

    # Cleanup app state
    app_state = get_app_state()

    try:
        app_state.delete_pipeline()
    except Exception as e:
        logger.error(f"Error cleaning up app state: {e}")

    logger.info("Cleanup completed")


def get_static_directory() -> Path | None:
    """Get the static directory path for serving frontend files"""
    # Frontend build directory (created by 'npm run build')
    frontend_dist_dir = Path(__file__).parent.parent.parent / "frontend" / "dist"

    if frontend_dist_dir.exists():
        return frontend_dist_dir
    else:
        return None


# Create FastAPI app
app = FastAPI(
    title="achew",
    description="Audiobook Chapter Extraction Wizard for Audiobookshelf",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS for API endpoints only
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(core.router, prefix="/api", tags=["core"])
app.include_router(pipeline.router, prefix="/api", tags=["pipeline"])
app.include_router(config.router, prefix="/api", tags=["config"])
app.include_router(chapters.router, prefix="/api", tags=["chapters"])
app.include_router(audio.router, prefix="/api", tags=["audio"])
app.include_router(audiobookshelf.router, prefix="/api/audiobookshelf", tags=["audiobookshelf"])

# Setup static file serving
static_dir = get_static_directory()

if static_dir:
    # Mount static files (CSS, JS, assets)
    # Vite puts assets in an 'assets' subdirectory
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # Mount any other static files
    app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")

    logger.info(f"Serving static files from {static_dir}")
else:
    logger.warning(
        "Frontend files not found. Run 'npm run build' in frontend directory or use './run.sh' from project root."
    )


@app.get("/")
async def serve_index():
    """Serve the main frontend application"""
    # static_dir = get_static_directory()

    if static_dir:
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file, media_type="text/html")

    # Fallback API response if no frontend built
    return {
        "message": "achew API",
        "version": "1.0.0",
        "status": "running",
        "note": "Frontend not built. Run 'npm run build' in frontend directory or use './run.sh' from project root.",
    }


@app.get("/api")
async def api_root():
    """API root endpoint"""
    return {
        "message": "achew API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "docs": "/docs",
            "redoc": "/redoc",
            "health": "/health",
            "session": "/api/session",
            "chapters": "/api/chapters",
            "audio": "/api/audio",
            "audiobookshelf": "/api/audiobookshelf",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Basic health check
        app_state = get_app_state()
        has_active_pipeline = app_state.pipeline is not None
        return {
            "status": "healthy",
            "has_active_pipeline": has_active_pipeline,
            "version": "1.0.0",
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)},
        )


# Catch-all route for frontend routing (SPA support)
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve SPA for any non-API routes"""

    # Don't intercept API routes
    if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("redoc"):
        return JSONResponse(
            status_code=404,
            content={"detail": "API endpoint not found"},
        )

    # Don't intercept WebSocket routes
    if full_path.startswith("ws/"):
        return JSONResponse(
            status_code=404,
            content={"detail": "WebSocket endpoint not found"},
        )

    # Check if it's a static file request
    # static_dir = get_static_directory()

    if static_dir:
        # Try to serve the requested file directly
        requested_file = static_dir / full_path
        if requested_file.exists() and requested_file.is_file():
            return FileResponse(requested_file)

        # For SPA routing, serve index.html
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file, media_type="text/html")

    # Frontend not found
    return JSONResponse(
        status_code=404,
        content={
            "detail": "Frontend not found",
            "note": "Run 'npm run build' in frontend directory or use './run.sh' from project root.",
        },
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    app_state = get_app_state()

    try:
        # Accept connection
        await websocket.accept()

        # Add connection to app state
        app_state.add_websocket_connection(websocket)

        if app_state.pipeline:
            logger.info(f"WebSocket connected with active pipeline")
            # Send initial status with pipeline info
            welcome_message = WSMessage(
                type=WSMessageType.STATUS,
                data={"message": "Connected to app", "step": app_state.step.value},
            )
        else:
            logger.info(f"WebSocket connected without active pipeline (configuration mode)")
            # Send initial status for configuration mode
            welcome_message = WSMessage(
                type=WSMessageType.STATUS,
                data={"message": "Connected for configuration", "step": "idle"},
            )

        await websocket.send_text(welcome_message.model_dump_json())

        # Keep connection alive and handle incoming messages
        try:
            while True:
                # Wait for messages (can be used for heartbeat or commands)
                message = await websocket.receive_text()

                # Handle incoming message if needed
                try:
                    # Parse message and handle commands if any
                    logger.debug(f"Received WebSocket message: {message}")

                    # Get current app state (might have changed since connection)
                    step = app_state.step.value

                    # Echo back simple status
                    response = WSMessage(
                        type=WSMessageType.STATUS,
                        data={
                            "message": "Message received",
                            "echo": message,
                            "step": step,
                        },
                    )
                    await websocket.send_text(response.model_dump_json())
                except Exception as e:
                    logger.warning(f"Failed to handle WebSocket message: {e}")

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected")

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        # noinspection PyBroadException
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except:
            pass

    finally:
        # Remove connection from app state
        app_state.remove_websocket_connection(websocket)


@app.exception_handler(Exception)
async def global_exception_handler(exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Add middleware for request logging
@app.middleware("http")
async def log_requests(request, call_next):
    """Log HTTP requests"""
    start_time = asyncio.get_event_loop().time()

    # Skip logging for health checks and static files
    if request.url.path not in ["/health", "/favicon.ico"] and not request.url.path.startswith("/assets/"):
        logger.info(f"{request.method} {request.url.path}")

    response = await call_next(request)

    process_time = asyncio.get_event_loop().time() - start_time

    # Log response time for API calls
    if request.url.path.startswith("/api/") and process_time > 1.0:
        logger.warning(f"Slow request: {request.method} {request.url.path} took {process_time:.2f}s")

    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
    )
