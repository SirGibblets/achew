<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/c2df8623-21e7-4c06-9918-5adb55e48bbe">
    <source media="(prefers-color-scheme: light)" srcset="https://github.com/user-attachments/assets/04864a8e-9dfa-4d6d-b669-6cb23ec5ffe6">
    <img width="600" alt="achew" src="https://github.com/user-attachments/assets/c2df8623-21e7-4c06-9918-5adb55e48bbe">
  </picture>
</div>

## About

#### **achew** is an Audiobook Chapter Extraction Wizard.
Designed to work with [Audiobookshelf](https://www.audiobookshelf.org/), **achew** helps you analyze your audiobook files to find chapters and generate titles.

### Features

- **Search**: Quickly find audiobooks in your Audiobookshelf libraries.
- **Smart Chapter Detection**: Automatically analyzes audio files to efficiently detect potential chapter cues.
- **Uses Existing Chapters**: Uses existing chapter information from Audiobookshelf, Audnexus, or embedded chapters to compare against detected chapters, guide the AI Cleanup process, or simply generate new chapter titles for existing timestamps.
- **Title Transcription**: Uses the Parakeet and Whisper ASR models to transcribe chapter titles. Apple Silicon devices can access the hardware-accelerated MLX versions of these models.
- **Interactive Chapter Editor**: Allows you to edit titles, play chapter audio, and delete unwanted chapters.
- **AI Cleanup**: Uses one of several LLM providers to intelligently clean up your chapter titles. Supports OpenAI, Google Gemini, Anthropic's Claude, Ollama, and LM Studio.
- **Export**: Save updated chapter data right back to Audiobookshelf, or export to a variety of formats.
- **Supports Multiple Formats**: Works with both single-file and multi-file audiobooks (mp3, m4b, etc).
- **Multilingual Support**: Title Transcription and AI Cleanup support dozens of languages, while Smart Detection works for *all* languages.
- **Cross-Platform**: Builds and runs on Windows, Linux, and macOS. There's also a Docker image!
- **It's Fast!** On modern hardware, **achew** can generate chapters for most audiobooks in only a few minutes. 

### Demo Video

https://github.com/user-attachments/assets/cde5b668-2849-4fe5-88b7-db0f97d73019

## System Requirements

- 10GB disk space (SSD recommended)
- 8GB RAM

## Installation

<details>

<summary>Docker</summary>

## Running with Docker

#### Note: The Docker image uses the CPU for transcription. Hardware-accelerated models are only available via the native installation method on Apple Silicon devices.

### 1. Install prerequisites
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)

### 2. Gather Keys
- Create an [Audiobookshelf API Key](https://www.audiobookshelf.org/guides/api-keys/#creating-api-keys)
- **[Optional]** Create API key for OpenAI, Gemini, or Claude, or have access to a machine running Ollama or LM Studio. This is only required if you want to use the AI Cleanup feature.

### 3. Set Up the Compose File
- Download the [docker-compose.yml](docker-compose.yml) file. This can go anywhere (e.g. inside a new directory named `achew` in your home directory).
- Change the port and volume mappings if desired.


### 4. Run
In a terminal, cd into the directory where you downloaded the docker-compose.yml file, and run the following command:
```bash
docker-compose up -d
```

### 5. Access
Access the running application in a browser at http://localhost:8000.

</details>

<details>

<summary>Linux and macOS</summary>

## Installation on Linux and macOS

### 1. Install Prerequisites
- Install [Node.js](https://nodejs.org/en/download) with npm
- Install [uv package manager](https://docs.astral.sh/uv/getting-started/installation/)
- Install [ffmpeg](https://ffmpeg.org/download.html)

### 2. Gather Keys
- Create an [Audiobookshelf API Key](https://www.audiobookshelf.org/guides/api-keys/#creating-api-keys)
- **[Optional]** Create an API key for OpenAI, Gemini, or Claude, or have access to a machine running Ollama or LM Studio. This is only required if you want to use the AI Cleanup feature.

### 3. Clone the Project
```bash
# Clone the repository
git clone https://github.com/SirGibblets/achew.git
cd achew

# Make run script executable
chmod +x ./run.sh
```

### 4. Run
```bash
# Run the app with default host/port:
./run.sh

# To allow access from another machine on the network:
./run.sh --listen

# Or specify a different host and/or port:
./run.sh --host 0.0.0.0 --port 3000
```

### 5. Access
Access the running application in a browser at http://localhost:8000. It may take several minutes before the web interface becomes available on the first run.
</details>

<details>

<summary>Windows</summary>

## Installation on Windows

### 1. Install Prerequisites:
- Install [Node.js](https://nodejs.org/en/download) with npm
- Install [uv package manager](https://docs.astral.sh/uv/getting-started/installation/)
- Install [ffmpeg](https://ffmpeg.org/download.html)
- **[Optional]** Install the [Visual C++ Redistributable](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist) if not already installed. This is only required if you want to use the Parakeet ASR model on Windows.

### 2. Gather Keys
- Create an [Audiobookshelf API Key](https://www.audiobookshelf.org/guides/api-keys/#creating-api-keys)
- **[Optional]** Create an API key for OpenAI, Gemini, or Claude, or have access to a machine running Ollama or LM Studio. This is only required if you want to use the AI Cleanup feature.


### 3. Clone
```powershell
git clone https://github.com/SirGibblets/achew.git
cd achew
```

### 4. Run
```powershell
# Run the app with default host/port:
.\run.bat

# To allow access from another machine on the network:
.\run.bat --listen

# Or specify a different host and/or port:
.\run.bat --host 0.0.0.0 --port 3000
```

### 5. Access
Access the running application in a browser at http://localhost:8000. It may take several minutes before the web interface becomes available on the first run.

</details>


## FAQ

<details>

<summary>Can I use the AI Cleanup feature without a paid OpenAI/Anthropic/Gemini account?</summary>

Yes! You have two options:
1. If you have a Google account, the easiest way is to use Gemini's free tier. Just go [here](https://aistudio.google.com/apikey), create a free API Key, and then copy/paste it into the Gemini section in achew's LLM Configuration page. Be aware that the free tier has usage limits, but it should be good enough for the occasional chapter cleanup.
2. If you have powerful hardware, you can install Ollama or LM Studio and run any LLM of your choice. This option is free, unlimited, and respects your privacy. Just be aware that small and even medium-size models may produce unusable results.

</details>

<details>

<summary>Can I use achew behind a reverse proxy?</summary>

As achew does not include built-in authentication, it is *not* recommended to expose it directly to the internet.  
With that being said, yes, achew should work behind a reverse proxy so long as you enable websocket support. If you choose to go this route, it is *highly* recommended to add some form of authentication at the proxy level.

</details>

<details>

<summary>How can I improve the consistency of chapter transcriptions?</summary>

You may find that chapter transcriptions are frequently inconsistent: chapter numbers may be a mix of words, digits, and Roman numerals; words may be in all caps or not capitalized at all; punctuation and separators may vary from chapter to chapter. Part of this is simply the nature of the ASR models and short audio segments used for transcription, and the overall recommendation is to use AI Cleanup when possible to standardize your chapter titles.

If AI Cleanup isn’t an option for you, try using one of the Whisper models with the “Use Bias Words” option enabled. Bias words act as a sort of custom vocabulary for the model and help guide the output toward specific spelling, terminology, and conventions. It’s far from perfect, but it can go a long way toward reducing the manual cleanup required.

</details>

<details>

<summary>I frequently get too many or too few cues when using Smart Detect</summary>

You can fine-tune this by adjusting the Minimum Chapter Gap value, found in the Detection Settings before starting the Smart Detect workflow. If you are getting too few cue options, drop this down to 1.75s or 1.5s. Conversely, if you're getting too many cues, try raising it up to 2.5 or 3s.
</details>
