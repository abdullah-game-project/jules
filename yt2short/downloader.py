import os
import subprocess
from config import settings


async def download_audio(url: str, video_id: str) -> str | None:
    os.makedirs(settings.temp_dir, exist_ok=True)
    out = os.path.join(settings.temp_dir, f"{video_id}.mp3")

    cmd = [
        "yt-dlp",
        "-x", "--audio-format", "mp3",
        "--audio-quality", "0",
        "--output", out,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"Download error: {result.stderr[:500]}")
        return None
    return out if os.path.exists(out) else None


def cleanup(video_id: str):
    for f in os.listdir(settings.temp_dir):
        if video_id in f:
            try:
                os.remove(os.path.join(settings.temp_dir, f))
            except OSError:
                pass
