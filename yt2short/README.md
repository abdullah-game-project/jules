# yt2short — Free, AI-Powered YouTube Shorts Generator

A professional, self-hosted, and free alternative to **Opus.pro**. Effortlessly convert long-form YouTube videos into viral, high-engagement Shorts with styled captions and cinematic cropping—all from your command line.

## 🚀 Key Features

- **Free & Open Source**: No subscriptions or hidden fees. Self-hosted on your own machine.
- **AI-Driven Virality**: Uses **Google Gemini AI** to analyze transcripts and identify the most viral-worthy moments.
- **Smart Heatmap Analysis**: Scrapes YouTube's "most replayed" data to find segments viewers naturally love.
- **Local AI Transcription**: Powered by **Faster-Whisper** for fast, local audio-to-text conversion (no API cost).
- **Cinematic 9:16 Cropping**: Automatically crops horizontal videos to vertical 9:16 format with blurred background overlays.
- **Styled Captions**: Generates Opus-style animated ASS captions with word-level highlighting (available via worker/API).
- **Antibot Detection**: Robust support for YouTube cookies (`c.json`) to bypass bot detection and rate limits.

## 🛠️ Prerequisites

- **Python 3.10+**
- **FFmpeg & FFprobe**: Installed and in your system PATH.
- **Node.js**: Recommended for `yt-dlp` signature solving.
- **Google Gemini API Key**: [Get a free key here](https://aistudio.google.com/apikey).

## 📥 Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/yt2short.git
   cd yt2short
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install the CLI tool**:
   ```bash
   pip install -e .
   ```
   Now you can use the `yt2short` command anywhere!

## 🎬 Quick Start

### 1. Launch the Tool
Simply type:
```bash
yt2short
```
This opens the interactive menu where you can configure your API keys and cookies.

### 2. Create Shorts (Express Mode)
Generate viral clips in one command:
```bash
yt2short --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --auto --clips 3
```

### 3. Handle Antibot Detection
Drop your exported YouTube cookies into a file named `c.json` in the working directory. `yt2short` will automatically detect and import them to ensure smooth downloads.

## 📖 Command Line Options

| Flag | Description |
|------|-------------|
| `--url URL` | The YouTube video URL to convert. |
| `--clips N` | Number of Shorts to generate (default: 5). |
| `--auto` | Non-interactive mode; uses defaults for all prompts. |
| `--output DIR`| Custom output directory. |
| `--check` | Verify your system dependencies. |

## 🌟 How It Works

1. **Extraction**: `yt2short` fetches video metadata and engagement heatmaps using `yt-dlp` and `httpx`.
2. **Transcription**: If no captions exist, it downloads the audio and uses `faster-whisper` for local transcription.
3. **Analysis**: The transcript and heatmap are sent to Gemini AI to pick the top moments.
4. **Processing**: `FFmpeg` crops the video, applies blurring, and renders the final 9:16 Shorts.

---
*Created as a free alternative for creators to regain control over their short-form content workflow.*
