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

## Installation

<details>

<summary>Docker (Recommended)</summary>

## Running with Docker

### 1. Install prerequisites
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)

### 2. Gather Keys
- Create an [Audiobookshelf API Key](https://www.audiobookshelf.org/guides/api-keys/#creating-api-keys)
- **[Optional]** Create API key for OpenAI, Gemini, or Claude, or have access to a machine running Ollama or LM Studio. This is only required if you want to use the AI Cleanup feature.

### 3. Set Up the Compose File
- Download the [docker-compose.yml](docker-compose.yml) file.
- Change the port and volume mappings as necessary.


### 4. Run
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
