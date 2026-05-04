# Install on Windows

!!! info ""
    View the [system requirements](index.md#system-requirements) before you get started.

## 1. Install prerequisites

- [npm](https://nodejs.org/en/download){:target="_blank"} (bundled with the Node.js installer)
- [uv package manager](https://docs.astral.sh/uv/getting-started/installation/){:target="_blank"}
- [ffmpeg](https://ffmpeg.org/download.html){:target="_blank"}: make sure `ffmpeg.exe` is on your `PATH`.
- *(Optional)* [Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170#latest-supported-redistributable-version){:target="_blank"}: only required if using the Parakeet transcription model.

## 2. Clone the project

```powershell
git clone https://github.com/SirGibblets/achew.git
cd achew
```

## 3. Run

```powershell
# Default host/port (localhost:8000)
.\run.bat

# Expose to other machines on your local network
.\run.bat --listen

# Custom host and/or port
.\run.bat --host 0.0.0.0 --port 3000
```

!!! tip "Give it a moment"
    The first launch may take several minutes while dependencies are installed and the app is built.

## 4. Open the app

Visit <http://localhost:8000>{:target="_blank"} once the app is ready and you should see the welcome screen:

![Achew welcome screen](../img/welcome-light.webp#only-light)
![Achew welcome screen](../img/welcome-dark.webp#only-dark)

## Next steps

- [First run walkthrough](first-run.md): Connect Audiobookshelf and (optionally) configure an LLM service.
- [Upgrading](upgrading.md): How to install the latest version of Achew.
- [Storage and backup](storage-and-backup.md): Where your data is stored.
