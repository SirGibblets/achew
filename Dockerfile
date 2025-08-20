# Stage 1: Frontend build
FROM node:22.18.0-bookworm-slim AS frontend-builder

WORKDIR /app/frontend

# Copy frontend package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci

# Copy frontend source code
COPY frontend/ ./

# Build the frontend
RUN npm run build

# Stage 2: Backend and final image
FROM mwader/static-ffmpeg:7.1.1 AS ffmpeg
FROM astral/uv:0.8.11-python3.11-trixie-slim

# Build arguments for image metadata
ARG VERSION="UNKNOWN"
ARG REVISION=""
ARG BUILD_DATE=""

# Container image metadata
LABEL org.opencontainers.image.authors="Sir Gibblets <gibbletssir@gmail.com>" \
    org.opencontainers.image.title="achew" \
    org.opencontainers.image.description="Audiobook Chapter Extraction Wizard for Audiobookshelf" \
    org.opencontainers.image.version="${VERSION}" \
    org.opencontainers.image.revision="${REVISION}" \
    org.opencontainers.image.created="${BUILD_DATE}" \
    org.opencontainers.image.source="https://github.com/SirGibblets/achew" \
    org.opencontainers.image.documentation="https://hub.docker.com/r/sirgibblets/achew" \
    org.opencontainers.image.vendor="sirgibblets.com" \
    org.opencontainers.image.license="MIT"

# Install libgomp1 for VAD
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy in ffmpeg
COPY --from=ffmpeg /ffmpeg /usr/local/bin/

WORKDIR /achew

# Copy backend files
COPY backend/ ./

# Install Python dependencies using uv
RUN uv sync

# Copy in built frontend
COPY --from=frontend-builder /app/frontend/dist ../frontend/dist

# Expose port 8000
EXPOSE 8000

# Run the application
CMD ["uv", "run", "python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0"]