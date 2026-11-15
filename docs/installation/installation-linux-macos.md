# Install on Linux or macOS

!!! info ""
    View the [system requirements](index.md#system-requirements) before you get started.

## 1. Install

Run this in a terminal:

```bash
curl -LsSf https://raw.githubusercontent.com/SirGibblets/achew/main/install.sh | sh
```

This installs Achew into an `achew` folder in your home directory, then starts it. Achew downloads everything else it needs the first time it runs. See [Bundled tools](#bundled-tools) for details.

```bash
# Install somewhere else
curl -LsSf https://raw.githubusercontent.com/SirGibblets/achew/main/install.sh | ACHEW_DIR=~/apps/achew sh

# Expose to other machines on your local network
curl -LsSf https://raw.githubusercontent.com/SirGibblets/achew/main/install.sh | sh -s -- --listen
```

!!! tip "Give it a moment"
    The first launch may take several minutes while dependencies are installed and the app is built.

??? note "Installing with git"
    If [Git](https://git-scm.com/downloads){:target="_blank"} is installed, the install script clones the project and checks out the latest release. Without git, it downloads the latest release instead. Either way, Achew updates from one release to the next. A clone made by hand starts on the `main` branch, and moves to a release the next time Achew updates itself. To clone the project by hand:

    ```bash
    git clone https://github.com/SirGibblets/achew.git
    cd achew
    ./run.sh
    ```

## 2. Open the app

Visit <http://localhost:8000>{:target="_blank"} once the app is ready and you should see the welcome screen:

![Achew welcome screen](../img/welcome-light.webp#only-light)
![Achew welcome screen](../img/welcome-dark.webp#only-dark)

## Starting Achew again

To start Achew again later, run `run.sh` from its folder:

```bash
# Default host/port (localhost:8000)
~/achew/run.sh

# Expose to other machines on your local network
~/achew/run.sh --listen

# Custom host and/or port
~/achew/run.sh --host 0.0.0.0 --port 3000
```

To update Achew, see [Upgrading](upgrading.md).

## Apple Silicon: MLX models

If you are on an M-series Mac, the **Parakeet MLX** and **Whisper MLX** models will be available in [Transcription Settings](../reference/transcription.md#services). These use hardware acceleration on Apple Silicon and run noticeably faster than the CPU variants.

## Bundled tools

On first launch, `run.sh` downloads its own copies of [uv](https://docs.astral.sh/uv/){:target="_blank"}, [Node.js](https://nodejs.org/){:target="_blank"}, and Python into the `.toolchain` folder inside the project, and verifies each download against a checksum stored in the project. Achew only uses these copies while it runs. They aren't added to your `PATH`, and any uv, Node.js, or Python you already have installed is left untouched. Deleting the `.toolchain` folder removes them, and the next launch downloads them again.

On macOS, the bundled tools need macOS 13.5 (Ventura) or newer.

On Linux, the bundled tools need a 64-bit x86 or ARM CPU, `curl` or `wget`, and glibc 2.28 or newer, which covers nearly every distribution released since 2019. They are not available for 32-bit systems (such as 32-bit Raspberry Pi OS), or for Alpine and other musl-based distributions.

??? note "Using your own uv and Node.js"
    If the bundled tools can't run on your system, or you would rather manage these tools yourself, install them and start Achew with `ACHEW_SYSTEM_TOOLS=1`. Achew then uses the `uv` and `npm` found on your `PATH`.

    Achew needs Node.js 22.12 or newer (20.19 also works). Some distributions package older versions, such as Ubuntu 24.04's Node.js 18, so check with `node --version`, and install a current version from [nodejs.org](https://nodejs.org/en/download){:target="_blank"} if yours is older.

    === "macOS (Homebrew)"

        ```bash
        brew install node
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Debian / Ubuntu"

        ```bash
        sudo apt update
        sudo apt install -y npm
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Fedora / RHEL"

        ```bash
        sudo dnf install -y npm
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    ```bash
    ACHEW_SYSTEM_TOOLS=1 ./run.sh
    ```

## Next steps

- [First run walkthrough](first-run.md): Connect Audiobookshelf and (optionally) configure an LLM service.
- [Upgrading](upgrading.md): How to install the latest version of Achew.
- [Storage and backup](storage-and-backup.md): Where your data is stored.
