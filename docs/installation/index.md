<style>
    .md-typeset table:not([class]) th:nth-child(1),
    .md-typeset table:not([class]) td:nth-child(1) {
        min-width: 8rem;
    }
</style>

# Installation

This section covers how to install, set up, and upgrade Achew. Pick the install method that fits your setup, then proceed through first-run configuration.

## Install methods

- [Install with Docker](installation-docker.md)
- [Install on Linux/macOS](installation-linux-macos.md)
- [Install on Windows](installation-windows.md)

## After installation

- [First Run](first-run.md): Connect Audiobookshelf and (optionally) configure an LLM service.
- [Upgrading](upgrading.md): How to install the latest version of Achew.
- [Storage and Backup](storage-and-backup.md): Where Achew keeps its data.
- [Reverse Proxy](reverse-proxy.md): For remote access.

## System requirements

### Minimum

- **10 GB disk space**
- **4 GB RAM**

### Recommended

- **8 GB+ RAM** if you plan to use the larger transcription models.
- **SSD.** Highly recommended since many processes are I/O heavy.
- **Apple Silicon Mac** for faster transcription (enables [MLX services](../reference/transcription.md#services) via the native install).

## Networking Requirements

- Achew must be able to reach your Audiobookshelf server.
- Cloud LLM providers (optional) used for [AI Cleanup](../editor/ai-cleanup.md) require internet access.
- Local [transcription services](../reference/transcription.md) require internet access for initial model downloads.

## Environment variables

A few launch-time knobs can be set as environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `HOST` | `127.0.0.1` | Bind address for the backend. Equivalent to `--host` (or `--listen` for `0.0.0.0`). |
| `PORT` | `8000` | Listen port. Equivalent to `--port`. |
| `DEBUG` | `false` | Enables debug logging and FastAPI auto-reload. Equivalent to `--debug` / `--no-debug`. |
| `ACHEW_WORKER_COUNT` | auto | Overrides the number of parallel workers used for audio analysis. Equivalent to `--workers`. See [Tuning the worker count](../troubleshooting/performance-tuning.md#tuning-the-worker-count). |
