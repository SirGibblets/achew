<style>
  .md-typeset h1 {
    display: none;
  }
</style>

# Introduction { display:none }

![Achew overview](img/hero-light.webp#only-light){ width="600"; .center .off-glb }
![Achew overview](img/hero-dark.webp#only-dark){ width="600"; .center .off-glb }

**Achew** is an Audiobook Chapter Extraction Wizard. It pairs with [Audiobookshelf](https://www.audiobookshelf.org/){:target="_blank"} to help you find chapters, align them to the audio, transcribe titles, and clean up the results. Changes can then be saved back to your library or exported for use elsewhere.

??? tip "Securing your Achew instance"
    Much like a desktop application, Achew does not include native authentication. Direct access should be limited to the hosting computer or a trusted local network. For remote access, it is recommended to use a VPN or place Achew behind a reverse proxy that enforces its own authentication layer.
    
    See [Reverse Proxy](installation/reverse-proxy.md) and [Privacy and Data](reference/privacy-and-data.md).

## Start here

<div class="grid cards" markdown>

- :material-download:{ .lg .middle } **Install Achew**

    ---

    Pick the installation method that best fits your setup.

    [:octicons-arrow-right-24: Docker](installation/installation-docker.md) ·
    [Linux/macOS](installation/installation-linux-macos.md) ·
    [Windows](installation/installation-windows.md)

- :material-rocket-launch-outline:{ .lg .middle } **First run**

    ---

    Connect Achew to Audiobookshelf and configure your LLM settings.

    [:octicons-arrow-right-24: First run walkthrough](installation/first-run.md)

- :material-book-open-outline:{ .lg .middle } **Achew Basics**

    ---

    Learn the core concepts behind how Achew works.

    [:octicons-arrow-right-24: Achew Basics](getting-started/achew-basics.md)

- :material-lightbulb-on-outline:{ .lg .middle } **Common scenarios**

    ---

    Step-by-step walkthroughs for the most frequent tasks.

    [:octicons-arrow-right-24: Examples](examples/index.md)

</div>

## What can Achew do?

Chapter metadata for audiobooks is often missing, wrong, or inconsistent. Achew gives you a focused toolkit for fixing it without needing to manually scrub through audio.

**Find chapter boundaries.** Detect them from the audio itself when nothing reliable exists, or pull them in from Audiobookshelf, Audnexus, embedded metadata, or a variety of other sources.

**Fix existing chapters.** Realign timestamps that are slightly off, regenerate titles that were never set properly, or drop straight into the chapter editor for quick changes.

**Transcribe chapter titles.** Use speech recognition to extract text from the start of each chapter. Supports all the multilingual and English-only models of both Whisper and Parakeet, with hardware acceleration on Apple Silicon.

**Clean up with AI.** Normalize capitalization, numbers, punctuation, and wording in one pass, using an LLM service of your choice: OpenAI, Claude, Gemini, OpenRouter, GitHub Copilot, or a local model via Ollama or LM Studio.

**Save the results.** Save chapters back to Audiobookshelf, or export to a variety of formats.

Achew runs anywhere you want it to (Docker, Linux, macOS, or Windows) and works on single- and multi-file audiobooks in a variety of formats.

## Demo Video

<video controls width="100%" src="img/demo-video-light.mp4#only-light"></video>
<video controls width="100%" src="img/demo-video-dark.mp4#only-dark"></video>
