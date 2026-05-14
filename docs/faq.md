# FAQ

## Can I use Achew without Audiobookshelf?

No, Achew is built specifically around Audiobookshelf. It uses ABS to find books and sources, pull audio, and write chapters back.

## Can I use the AI Cleanup feature for free?

Yes! Three options: Gemini's free tier, GitHub Copilot Free, or a local model via Ollama or LM Studio. See [Free options](getting-started/setup-llm-providers.md#free-options) for more details.

## Can I use Achew behind a reverse proxy?

Yes. Achew does not include built-in authentication, so do not expose it directly to the internet; use your reverse proxy to put an auth layer in front (basic auth, Tailscale, Authelia, etc.). Make sure the proxy forwards WebSocket upgrades. See [Reverse Proxy](installation/reverse-proxy.md).

## How can I improve the consistency of chapter transcripts?

See [Tips for improving transcription](reference/transcription.md#tips-for-improving-transcription).

## Does Achew upload my audio to the cloud?

No. All audio stays on the Achew host. When you use cloud LLMs for AI Cleanup, only chapter *titles* and some metadata are sent, never audio. See [Privacy and Data](reference/privacy-and-data.md#llm-providers-ai-cleanup).

## Which Transcription model should I pick?

See the [Transcription](reference/transcription.md#what-should-i-start-with) page for recommendations.

## Can I run Achew on a low-memory system?

Achew has been tested on as little as [4GB of memory](installation/index.md#system-requirements). By default, Achew auto-detects a safe worker count based on available CPU cores and memory (and respects Docker memory limits). If you still run tight, set `ACHEW_WORKER_COUNT=1` to disable parallelism (slowest but most frugal). You can also raise the value to utilize more of a beefy machine. See [Tuning the worker count](troubleshooting/performance-tuning.md#tuning-the-worker-count).

## Does Achew work on older CPUs?

Yes, it'll just run slower. If your CPU is pre-2013 (Intel) or pre-2015 (AMD) and lacks AVX2 support, use the `legacy-cpu` Docker tag to avoid Whisper crashes. See [Transcription → legacy-cpu](reference/transcription.md#legacy-cpu-docker-image).

## Can I run Achew headless or via CLI?

Achew uses a web UI; there is no pure-CLI mode. You can run it on a headless server and access the UI from another machine on your local network.

## What happens if I close the browser?

Nothing; all data is held server-side. Re-open Achew in the browser and you'll land right back where you were.

## How do I go back or start over with a different book?

Use the [Back Menu](reference/glossary.md#back-menu): click the **Back** button at the top-left of the screen and pick the step you want to return to. To discard your changes without submitting, choose **New Audiobook**.

## Related

- [Common Issues](troubleshooting/common-issues.md)
