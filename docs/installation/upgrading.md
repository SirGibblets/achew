# Upgrading Achew

![Upgrade Available](../img/update-available-dark.webp#only-dark){ width="140" align=left .off-glb }
![Upgrade Available](../img/update-available-light.webp#only-light){ width="140" align=left .off-glb }

When a new version of Achew is available, a small download icon will be displayed next to the currently-installed version in the bottom right. Clicking the icon opens the **Update Achew** dialog, with a link to the release notes and, for native installs, an **Update Now** button. If an install can't update itself from the app, such as when Achew was started with `--debug`, the dialog says why instead.

??? question "Do I need to back up my data?"
    Upgrading to newer releases of Achew is generally safe, but it's always a good idea to back up your data just in case. This is especially true when upgrading from v1.6.1 or earlier: due to a change in how settings are stored beginning with [v1.7.0](https://github.com/SirGibblets/achew/releases/tag/v1.7.0){:target="_blank"}, downgrading to v1.6.1 or earlier will result in all settings becoming unavailable, and they'll need to be restored from a pre-v1.7.0 backup.

    You'll only need to back up the Settings directory. See [Storage and Backup](storage-and-backup.md) for example backup commands.

## Docker

```bash
cd path/to/achew # Directory containing your Docker compose file
docker-compose pull
docker-compose up -d
```

The `latest` tag tracks the most recent release. If you need the `legacy-cpu` image (for CPUs without AVX2: Intel pre-2013, AMD pre-2015), use that tag instead.

Your configuration and model cache persist via the volumes defined in [`docker-compose.yml`](https://github.com/SirGibblets/achew/blob/main/docker-compose.yml){:target="_blank"}, so your Audiobookshelf key, LLM settings, and saved preferences survive upgrades. 

## Native (Linux / macOS)

Click the download icon, then **Update Now**. Achew downloads the update, then restarts itself to install it, which can take a few minutes. The page reloads once the new version is running.

To update from a terminal instead, stop Achew, then run:

```bash
cd path/to/achew
./run.sh --update
```

Running the [install command](installation-linux-macos.md#1-install) again does the same, as long as it points at the same folder (`~/achew`, or the `ACHEW_DIR` you installed with).

??? note "How Achew updates itself"
    Achew always updates to the latest release. An install made with git (by the install script, or by hand) checks out that release's tag, the same as `git checkout v1.14.0` would. If it was on a branch, such as `main`, it switches to the release and leaves the branch as it was. If you've changed any of Achew's files, Achew won't overwrite your changes: commit or discard them first. Any other install downloads the release and replaces Achew's files with it. Your settings aren't part of a release, so they're kept.

    To run unreleased changes from the `main` branch instead, use `git checkout main` and `git pull` rather than the update button.

??? note "Updating from Achew 1.13 or earlier"
    Older versions can't update themselves. Update once with git, and the options above work from then on:

    ```bash
    cd path/to/achew
    git checkout main
    git pull
    ./run.sh
    ```

    If git stops because your local changes to `uv.lock` or `package-lock.json` would be overwritten, discard them with `git checkout -- backend/uv.lock frontend/package-lock.json` and try again. Older versions could rewrite these files on launch.

The run script re-runs `uv sync` on launch, so new Python dependencies install automatically. It also downloads newer versions of its [bundled tools](installation-linux-macos.md#bundled-tools) when an update calls for them.

??? note "No system ffmpeg needed"
    Achew 1.14.0 and higher installs its own build of [ffmpeg](../reference/glossary.md#ffmpeg) along with its other dependencies and doesn't use a system-wide ffmpeg. If you installed ffmpeg for an older version of Achew, you can keep it, or remove it if nothing else on your system needs it.

??? note "No separate uv or Node.js needed"
    Achew 1.14.0 and higher downloads its own copies of uv, Node.js, and Python into the project's `.toolchain` folder and no longer uses the ones installed on your system. The first launch after upgrading takes a few extra minutes while Achew downloads these tools and reinstalls its dependencies. If you installed uv or Node.js only for Achew, you can keep them, or remove them if nothing else on your system needs them. See [Bundled tools](installation-linux-macos.md#bundled-tools) for what these tools need, or to keep using your own.

## Native (Windows)

Click the download icon, then **Update Now**. Achew downloads the update, then restarts itself to install it, which can take a few minutes. The page reloads once the new version is running.

To update from a terminal instead, stop Achew, then run:

```powershell
cd path\to\achew
.\run.bat --update
```

Running the [install command](installation-windows.md#1-install) again does the same, as long as it points at the same folder (`$HOME\achew`, or the `ACHEW_DIR` you installed with).

??? note "How Achew updates itself"
    Achew always updates to the latest release. An install made with git (by the install script, or by hand) checks out that release's tag, the same as `git checkout v1.14.0` would. If it was on a branch, such as `main`, it switches to the release and leaves the branch as it was. If you've changed any of Achew's files, Achew won't overwrite your changes: commit or discard them first. Any other install downloads the release and replaces Achew's files with it. Your settings aren't part of a release, so they're kept.

    To run unreleased changes from the `main` branch instead, use `git checkout main` and `git pull` rather than the update button.

??? note "Updating from Achew 1.13 or earlier"
    Older versions can't update themselves. Update once with git, and the options above work from then on:

    ```powershell
    cd path\to\achew
    git checkout main
    git pull
    .\run.bat
    ```

    If git stops because your local changes to `uv.lock` or `package-lock.json` would be overwritten, discard them with `git checkout -- backend\uv.lock frontend\package-lock.json` and try again. Older versions could rewrite these files on launch.

The run script re-runs `uv sync` on launch, so new Python dependencies install automatically. It also downloads newer versions of its [bundled tools](installation-windows.md#bundled-tools) when an update calls for them.

??? note "No system ffmpeg needed"
    Achew 1.14.0 and higher installs its own build of [ffmpeg](../reference/glossary.md#ffmpeg) along with its other dependencies and doesn't use a system-wide ffmpeg. If you installed ffmpeg for an older version of Achew, you can keep it, or remove it if nothing else on your system needs it.

??? note "No separate uv or Node.js needed"
    Achew 1.14.0 and higher downloads its own copies of uv, Node.js, and Python into the project's `.toolchain` folder and no longer uses the ones installed on your system. The first launch after upgrading takes a few extra minutes while Achew downloads these tools and reinstalls its dependencies. If you installed uv or Node.js only for Achew, you can keep them, or remove them if nothing else on your system needs them. See [Bundled tools](installation-windows.md#bundled-tools) for what these tools need, or to keep using your own.

## After upgrading

New features and breaking changes land in the [GitHub release notes](https://github.com/SirGibblets/achew/releases){:target="_blank"}. Read these, especially if you saw a Migration Failed screen after upgrade.

### Handling a Failed Migration

If Achew's saved config format changes between versions and the automatic migration cannot complete, you will land on a **Settings Migration Failed** screen.

![Migration failed](../img/migration-failed-light.webp#only-light){ width="480"; .center }
![Migration failed](../img/migration-failed-dark.webp#only-dark){ width="480"; .center }

Due to how data was saved prior to v1.7.0, switching to a different python runtime (which can happen during an upgrade) may, in rare cases, cause the data to become inaccessible. Unfortunately, in this situation your only options are to either downgrade to an older version of Achew, or proceed with resetting your settings.

If you choose the latter, you will need to re-enter your Audiobookshelf URL and API key, any LLM settings previously configured, any transcription or editor preferences, any custom AI Cleanup instructions, and any custom chapter search rules. Prior to resetting, it is recommended to back up the Settings directory in case you wish to downgrade at a later time. See [Storage and Backup](storage-and-backup.md) for example backup commands for your platform.

## Downgrading
??? warning "Downgrading to v1.6.1 or earlier"
    Achew version 1.7.0 changed how settings are stored, and the new format will not be recognized by earlier versions. If you have a pre-v1.7.0 backup of your Settings directory, you can restore that when downgrading. Otherwise, you'll need to re-enter all of your settings (Audiobookshelf URL/Key, LLM settings, and other app preferences) after a downgrade.

### Docker
Edit your `docker-compose.yml` file and specify the image tag for the version you want to use, e.g.

```yaml
services:
  achew:
    image: sirgibblets/achew:v1.5.4
```

Then:

```bash
cd path/to/achew # Directory containing your Docker compose file
docker-compose up -d
```

### Native (Linux / macOS)

These steps need an install made with git. Without git, download the version you want from its [GitHub release page](https://github.com/SirGibblets/achew/releases){:target="_blank"}, unpack it into a new folder, and copy your [Settings directory](storage-and-backup.md#settings) into it.

Versions before 1.14.0 don't bundle their own tools, so install uv, Node.js, and ffmpeg first, as described in that version's install guide. To come back to the latest version from one of them, follow [Updating from Achew 1.13 or earlier](#native-linux-macos).

```bash
cd path/to/achew

# Download the git tags used for releases
git fetch --tags

# Check out the desired version
git checkout v1.5.4

./run.sh
```

### Native (Windows)

These steps need an install made with git. Without git, download the version you want from its [GitHub release page](https://github.com/SirGibblets/achew/releases){:target="_blank"}, unpack it into a new folder, and copy your [Settings directory](storage-and-backup.md#settings) into it.

Versions before 1.14.0 don't bundle their own tools, so install uv, Node.js, and ffmpeg first, as described in that version's install guide. To come back to the latest version from one of them, follow [Updating from Achew 1.13 or earlier](#native-windows).

```powershell
cd path\to\achew

# Download the git tags used for releases
git fetch --tags

# Check out the desired version
git checkout v1.5.4

.\run.bat
```