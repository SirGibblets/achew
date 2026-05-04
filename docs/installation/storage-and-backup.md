# Storage and Backup

## Storage Locations

Achew writes to three locations: **Settings**, **Transcription Model Cache**, and **Temporary Data**.

### Settings

!!! quote ""
    **Directory location**

    - Windows/Linux/macOS: `path/to/achew/backend/app/config/`
    - Docker: `/achew/app/config`

Contains user config/settings data:

- Audiobookshelf URL and key
- LLM provider settings
- Transcription preferences
- Editor settings
- Custom Instructions for AI Cleanup
- Chapter Search rules and cached library data

!!! warning "API keys are stored in plain text"
    `app_config.json` contains your Audiobookshelf and LLM API keys. Treat backups of it accordingly: encrypt off-site copies and do not commit to public repositories.

### Transcription Model Cache

!!! quote ""
    Directory location
    
    - Linux/macOS: `~/.cache/huggingface/hub`
    - Windows: `C:\Users\<Username>\.cache\huggingface\hub`
    - Docker: `/root/.cache/huggingface/hub`

Contains the models used for transcription (Whisper/Parakeet). These are downloaded on first use and cached for subsequent runs. This directory is safe to delete; Achew will re-download anything it needs.

### Temporary Data

!!! quote ""
    Directory location
    
    - Linux/Docker: `/tmp/achew`
    - Windows: Typically `C:\Users\<Username>\AppData\Local\Temp\achew`, but can vary.
    - macOS: `/var/folders/xx/xxx.../T/achew`

Contains transient data for the current session:

- Book audio files
- Chapter source files
- Audio segments used for detection and transcription

## Back up

A backup of the **Settings** directory is enough to restore Achew settings on a new install.

!!! info "Docker users"
    The Docker examples in this page assume the default `./config:/achew/app/config` mapping from `docker-compose.yml`. If you've changed the host-side path, substitute it for `config/` in the commands below.

=== "Docker"

    ```bash
    cd path/to/achew # Directory containing your Docker compose file
    tar czf ~/achew-backup.tgz config/
    ```

=== "Native (Linux/macOS)"

    ```bash
    cd path/to/achew
    tar czf ~/achew-backup.tgz -C backend/app config
    ```

=== "Native (Windows)"

    ```powershell
    cd path\to\achew\backend\app
    Compress-Archive -Path config -DestinationPath "$HOME\achew-backup.zip"
    ```

## Restore

Stop Achew, replace the current `config/` with the backup, and start Achew again.

=== "Docker"

    ```bash
    cd path/to/achew # Directory containing your Docker compose file
    docker-compose down
    mv config config.old
    tar xzf ~/achew-backup.tgz
    docker-compose up -d
    ```

=== "Native (Linux/macOS)"

    Stop the running `./run.sh` first (Ctrl+C in its terminal), then:

    ```bash
    cd path/to/achew/backend/app
    mv config config.old
    tar xzf ~/achew-backup.tgz
    cd ../..
    ./run.sh
    ```

=== "Native (Windows)"

    Stop the running `run.bat` first (Ctrl+C in its terminal), then:

    ```powershell
    cd path\to\achew\backend\app
    Move-Item config config.old
    Expand-Archive -Path "$HOME\achew-backup.zip" -DestinationPath .
    cd ..\..
    .\run.bat
    ```

## Reset all data

Stop Achew, delete `config/`, and restart. You will land on first-run setup and need to re-enter your API keys and preferences.

=== "Docker"

    ```bash
    cd path/to/achew # Directory containing your Docker compose file
    docker-compose down
    rm -rf config/
    docker-compose up -d
    ```

=== "Native (Linux/macOS)"

    Stop the running `./run.sh` first (Ctrl+C in its terminal), then:

    ```bash
    rm -rf path/to/achew/backend/app/config
    cd path/to/achew && ./run.sh
    ```

=== "Native (Windows)"

    Stop the running `run.bat` first (Ctrl+C in its terminal), then:

    ```powershell
    Remove-Item -Recurse -Force path\to\achew\backend\app\config
    cd path\to\achew; .\run.bat
    ```
