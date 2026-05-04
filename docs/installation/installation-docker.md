# Install with Docker

The Docker image is the easiest way to get Achew running on any platform that supports Docker.

!!! info ""
    View the [system requirements](index.md#system-requirements) before you get started.

## 1. Install prerequisites

- [Docker](https://docs.docker.com/get-docker/){:target="_blank"}
- [Docker Compose](https://docs.docker.com/compose/install/){:target="_blank"}

## 2. Download the Compose file

Download [`docker-compose.yml`](https://github.com/SirGibblets/achew/blob/main/docker-compose.yml){:target="_blank"} and save it anywhere you like; a new `achew/` directory in your home folder works well.

Adjust the port and volume mappings if needed. The default exposes Achew on port `8000`.

??? info "Using an older CPU?"
    If your CPU lacks AVX2 support (Intel pre-2013, AMD pre-2015) the Whisper transcription model can crash. Switch to the `legacy-cpu` image tag to avoid this. See comments in `docker-compose.yml`.

## 3. Start Achew

```bash
cd path/to/achew # Directory containing your Docker compose file
docker-compose up -d
```

## 4. Open the app

Visit <http://localhost:8000>{:target="_blank"} and you should see the welcome screen:

![Achew welcome screen](../img/welcome-light.webp#only-light)
![Achew welcome screen](../img/welcome-dark.webp#only-dark)

## Next steps

- [First run walkthrough](first-run.md): Connect Audiobookshelf and (optionally) configure an LLM service.
- [Upgrading](upgrading.md): How to install the latest version of Achew.
- [Storage and backup](storage-and-backup.md): Where your data is stored.
- [Reverse proxy](reverse-proxy.md): If you need remote access.
