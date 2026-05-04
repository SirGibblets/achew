# Performance Tuning

## Transcription performance

Achew is designed around minimizing the amount of audio that needs to be transcribed, but if you're working with hundreds of chapters then transcription can certainly take a while. Here are some suggestions for speeding things up:

- On Apple Silicon, switch to the **Parakeet MLX** or **Whisper MLX** service. These use hardware acceleration and are dramatically faster.
- Use a smaller Whisper variant (`tiny` or `small` instead of `medium` / `large`).
- Enable the **Trim Segments** option to cut out unwanted audio.
- Reduce the **Transcription length** under advanced settings.

## Smart Detect performance

- Audio analysis is generally CPU-bound, but can become I/O-bound if Achew is running from a spinning disk. If that is the case, consider switching to an SSD. If you're running Achew via Docker and have plenty of system memory to spare (4GB+ free), you can also consider mapping the `/tmp/achew` Docker directory to `/dev/shm/achew` on your system so temporary files are stored in RAM instead of on disk. See [`docker-compose.yml`](https://github.com/SirGibblets/achew/blob/main/docker-compose.yml#L30){:target="_blank"} and [Storage and Backup](../installation/storage-and-backup.md).
- Running Smart Detect with the **Dramatized** option enabled takes roughly *5-10x longer* than standard detection. If your book does not have music or sound effects, it is recommended to keep this option disabled.

    If you know your book only has music/sfx in a few places, and you know where those places are (e.g. music only plays during the intro and outro), you can start by using standard detection for the initial pass and then later, in the editor, run dramatized detection for those specific sections using the [Add Chapter Dialog](../editor/add-chapter-dialog.md#detected-cues).

- Long books simply take longer. For a 20-hour book on a mid-range laptop, expect Smart Detect to take several minutes. Enable the [completion chime](../workflows/index.md#completion-chime), then stand up, get some air, and make a sandwich or something.

## Tuning the worker count

Achew runs part of its audio processing in parallel using multiple workers. By default it picks a worker count based on available CPU cores and memory. This should work well for most hosts, but in some cases you may wish to set this count manually.

To use a specific worker count:

=== "Docker (Compose)"

    Uncomment/add the `environment` block in `docker-compose.yml` and set:

    ```yaml
    environment:
      ACHEW_WORKER_COUNT=4
    ```

=== "Docker"

    ```bash
    docker run -e ACHEW_WORKER_COUNT=4 ...
    ```

=== "Native install"

    ```bash
    ./run.sh --workers 4
    # Windows:
    run.bat --workers 4
    ```

Setting the worker count to 1 disables parallelism entirely, which is the slowest but safest option for memory-constrained devices. On the other hand, feel free to raise the value if you feel your system is being underutilized.

## Related

- [Transcription](../reference/transcription.md)
- [System Requirements](../installation/index.md#system-requirements)
