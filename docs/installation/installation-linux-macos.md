# Install on Linux or macOS

!!! info ""
    View the [system requirements](index.md#system-requirements) before you get started.

## 1. Install prerequisites

- [npm](https://nodejs.org/en/download){:target="_blank"} (bundled with the Node.js installer)
- [uv package manager](https://docs.astral.sh/uv/getting-started/installation/){:target="_blank"}
- [ffmpeg](https://ffmpeg.org/download.html){:target="_blank"}

=== "macOS (Homebrew)"

    ```bash
    brew install node ffmpeg
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

=== "Debian / Ubuntu"

    ```bash
    sudo apt update
    sudo apt install -y npm ffmpeg
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

=== "Fedora / RHEL"

    ```bash
    sudo dnf install -y npm ffmpeg
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

## 2. Clone the project

```bash
git clone https://github.com/SirGibblets/achew.git
cd achew
chmod +x ./run.sh
```

## 3. Run

```bash
# Default host/port (localhost:8000)
./run.sh

# Expose to other machines on your local network
./run.sh --listen

# Custom host and/or port
./run.sh --host 0.0.0.0 --port 3000
```

!!! tip "Give it a moment"
    The first launch may take several minutes while dependencies are installed and the app is built.

## 4. Open the app

Visit <http://localhost:8000>{:target="_blank"} once the app is ready and you should see the welcome screen:

![Achew welcome screen](../img/welcome-light.webp#only-light)
![Achew welcome screen](../img/welcome-dark.webp#only-dark)

## Apple Silicon: MLX models

If you are on an M-series Mac, the **Parakeet MLX** and **Whisper MLX** models will be available in [Transcription Settings](../reference/transcription.md#services). These use hardware acceleration on Apple Silicon and run noticeably faster than the CPU variants.

## Next steps

- [First run walkthrough](first-run.md): Connect Audiobookshelf and (optionally) configure an LLM service.
- [Upgrading](upgrading.md): How to install the latest version of Achew.
- [Storage and backup](storage-and-backup.md): Where your data is stored.
