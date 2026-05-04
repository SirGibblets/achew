# Logs and Support

## Where logs go

=== "Docker"

    Logs stream to stdout/stderr from the container.

    ```bash
    docker-compose logs -f achew
    ```

    Use `--tail=200` to cap the output size.

=== "Native (Linux/macOS)"

    When you run `./run.sh` directly, logs print to the terminal. Redirect to a file if you need a copy:

    ```bash
    ./run.sh 2>&1 | tee achew.log
    ```

=== "Native (Windows)"

    `run.bat` prints to the console window that starts it. Redirect to a file if needed:

    ```powershell
    .\run.bat > achew.log 2>&1
    ```

## What to capture before asking for help

- The exact Achew version you are running (visible in the bottom-right corner of the app).
- The install method (Docker image tag, or native OS and version).
- General system info (CPU, RAM, HDD vs SSD, etc.)
- The part of the app you were in when the problem occurred.
- The full, exact text of any error message.
- Any relevant logs.

## Filing a bug report

Check [existing issues](https://github.com/SirGibblets/achew/issues){:target="_blank"} first to see if it has already been reported. If not, open a new issue and include the details above and, if relevant, a redacted screenshot.

!!! warning "Redact before posting"
    Screenshots and logs may contain sensitive information. Crop, blur, or remove anything you don't want to share before posting.

## Requesting a feature

Post in the [Ideas category on GitHub Discussions](https://github.com/SirGibblets/achew/discussions/categories/ideas){:target="_blank"} and describe what you'd like Achew to do and the problem it would solve. Check existing discussions first to avoid duplicates.

## Asking questions

For open-ended questions (not bugs or feature requests), use the [GitHub Discussions](https://github.com/SirGibblets/achew/discussions){:target="_blank"} page.

## Related

- [Common Issues](common-issues.md)
