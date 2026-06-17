# Shortify — AI-Powered YouTube Shorts Generator

A free, self-hosted alternative to Opus.pro. Paste a YouTube URL, get viral short clips with transcripts, styled captions, and metadata — powered by Whisper + Gemini AI.

## How It Works

1. **Heatmap Analysis** — Scrapes YouTube's "most replayed" segments to find naturally viral moments
2. **Whisper Transcription** — Transcribes the full video with word-level timestamps using Faster-Whisper
3. **Gemini AI Analysis** — Sends transcript + heatmap to Gemini to pick the best viral clips
4. **Styled Captions** — Generates Opus-style ASS karaoke subtitles with word-by-word highlighting
5. **Export** — Returns clip timestamps, clickbait titles, descriptions, tags, and keywords

## Quick Start

### Prerequisites

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) installed and in your PATH
- A [Google Gemini API key](https://aistudio.google.com/apikey) (free tier works)

### Installation

```bash
git clone https://github.com/YOUR_USERNAME/shortify.git
cd shortify
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add your Gemini API key:

```
GEMINI_API_KEY=your-key-here
```

### Run the API Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Analyze a Video

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

Response:

```json
{
  "job_id": "a1b2c3d4e5f6",
  "video_id": "dQw4w9WgXcQ",
  "title": "Rick Astley - Never Gonna Give You Up",
  "duration": 212.0,
  "clips": [
    {
      "clip": {"start_time": 45.0, "end_time": 75.0},
      "title": "Rick Astley's most iconic moment #shorts",
      "description": "This part hits different every time...\n\n#shorts #viral",
      "tags": ["shorts", "viral", "music", "rickroll"],
      "keywords": ["rick astley", "never gonna give you up"],
      "reasoning": "High heatmap intensity, recognizable hook"
    }
  ]
}
```

### Worker (Local PC)

The worker downloads, crops to 9:16, and generates styled captions:

```bash
python worker.py <youtube-url> [clip-index]
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/analyze` | Analyze a YouTube URL, returns viral clip candidates |
| `GET` | `/jobs` | List all analyzed jobs |
| `GET` | `/jobs/{job_id}` | Get job details |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | **Required.** Your Google Gemini API key |
| `WHISPER_MODEL` | `base` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large-v3` |
| `WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` (GPU) |
| `CLIP_DURATION` | `30` | Target clip length in seconds |
| `MAX_CLIPS` | `5` | Max clips to return per analysis |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8000` | Server port |

## Project Structure

```
shortify/
├── main.py           # FastAPI server
├── config.py         # Settings from .env
├── heatmap.py        # YouTube heatmap scraper
├── transcriber.py    # Faster-Whisper transcription
├── analyzer.py       # Gemini AI clip selection + metadata
├── captions.py       # SRT & ASS subtitle generation
├── downloader.py     # yt-dlp audio download
├── worker.py         # Local PC: download + crop + captions
├── requirements.txt
└── .env.example
```

## Features vs Opus.pro

| Feature | Shortify | Opus.pro |
|---------|----------|----------|
| Price | Free (self-hosted) | $19+/mo |
| Transcript source | Whisper (local) | Their servers |
| AI analysis | Gemini (free tier) | Proprietary |
| YouTube heatmap | Yes | No |
| Styled captions | Yes (ASS karaoke) | Yes |
| Multiple clips per video | Yes | Yes |
| Customizable | 100% | No |
| Privacy | Fully local option | Cloud |

## License

MIT
