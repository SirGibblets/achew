# Install on Windows

!!! info ""
    View the [system requirements](index.md#system-requirements) before you get started.

## 1. Install

Run this in PowerShell:

```powershell
irm https://raw.githubusercontent.com/SirGibblets/achew/main/install.ps1 | iex
```

This installs Achew into an `achew` folder in your user folder (`C:\Users\<Username>\achew`), then starts it. Achew downloads everything else it needs the first time it runs. See [Bundled tools](#bundled-tools) for details.

To install somewhere else, set `ACHEW_DIR` first:

```powershell
$env:ACHEW_DIR = "D:\Apps\achew"
irm https://raw.githubusercontent.com/SirGibblets/achew/main/install.ps1 | iex
```

!!! tip "Give it a moment"
    The first launch may take several minutes while dependencies are installed and the app is built.

!!! info "Parakeet transcription"
    The Parakeet transcription model needs the [Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170#latest-supported-redistributable-version){:target="_blank"}. Install it if you plan to use Parakeet.

??? note "Installing with git"
    If [Git](https://git-scm.com/downloads/win){:target="_blank"} is installed, the install script clones the project and checks out the latest release. Without git, it downloads the latest release instead. Either way, Achew updates from one release to the next. A clone made by hand starts on the `main` branch, and moves to a release the next time Achew updates itself. To clone the project by hand:

    ```powershell
    git clone https://github.com/SirGibblets/achew.git
    cd achew
    .\run.bat
    ```

## 2. Open the app

Visit <http://localhost:8000>{:target="_blank"} once the app is ready and you should see the welcome screen:

![Achew welcome screen](../img/welcome-light.webp#only-light)
![Achew welcome screen](../img/welcome-dark.webp#only-dark)

## Starting Achew again

To start Achew again later, run `run.bat` from its folder:

```powershell
# Default host/port (localhost:8000)
& "$HOME\achew\run.bat"

# Expose to other machines on your local network
& "$HOME\achew\run.bat" --listen

# Custom host and/or port
& "$HOME\achew\run.bat" --host 0.0.0.0 --port 3000
```

You can also double-click `run.bat` in File Explorer. To update Achew, see [Upgrading](upgrading.md).

## Bundled tools

On first launch, `run.bat` downloads its own copies of [uv](https://docs.astral.sh/uv/){:target="_blank"}, [Node.js](https://nodejs.org/){:target="_blank"}, and Python into the `.toolchain` folder inside the project, and verifies each download against a checksum stored in the project. Achew only uses these copies while it runs. They aren't added to your `PATH` or registered with Windows, and any uv, Node.js, or Python you already have installed is left untouched. Deleting the `.toolchain` folder removes them, and the next launch downloads them again.

On Windows 11 on ARM, Achew uses the x64 versions of these tools, which Windows runs through its built-in emulation.

??? note "Using your own uv and Node.js"
    If you would rather manage these tools yourself, install [Node.js](https://nodejs.org/en/download){:target="_blank"} 22.12 or newer (which includes npm; 20.19 also works) and [uv](https://docs.astral.sh/uv/getting-started/installation/){:target="_blank"}, then start Achew with `ACHEW_SYSTEM_TOOLS` set to `1`. Achew then uses the `uv` and `npm` found on your `PATH`.

    ```powershell
    $env:ACHEW_SYSTEM_TOOLS = "1"
    .\run.bat
    ```

## Next steps

- [First run walkthrough](first-run.md): Connect Audiobookshelf and (optionally) configure an LLM service.
- [Upgrading](upgrading.md): How to install the latest version of Achew.
- [Storage and backup](storage-and-backup.md): Where your data is stored.
