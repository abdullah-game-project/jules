#!/usr/bin/env python3
"""
Worker: runs on your local PC.
1. Calls gateway to analyze a YouTube URL
2. Picks a clip from the results
3. Downloads + crops + adds styled captions + uploads

Usage:
  python worker.py <youtube-url>
  python worker.py --gateway http://server:8000 <youtube-url>
"""
import os
import sys
import json
import subprocess
import httpx

GATEWAY = os.getenv("GATEWAY_URL", "http://localhost:8000")
OUTPUT = os.getenv("OUTPUT_DIR", "./output")
os.makedirs(OUTPUT, exist_ok=True)


def log(m): print(m)


def analyze(url: str) -> dict:
    log(f"Analyzing {url}...")
    r = httpx.post(f"{GATEWAY}/analyze", json={"url": url}, timeout=300)
    r.raise_for_status()
    return r.json()


def download(youtube_url: str, start: float, end: float, path: str):
    dur = end - start
    log(f"Downloading {start}s-{end}s...")
    subprocess.run([
        "yt-dlp", "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "--download-sections", f"*{start}-{end}",
        "--force-keyframes-at-cuts",
        "--output", path, "--merge-output-format", "mp4",
        youtube_url,
    ], check=True)


def crop(path_in: str, path_out: str):
    log("Cropping to 9:16...")
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path_in],
        capture_output=True, text=True).stdout)
    vs = next(s for s in probe["streams"] if s["codec_type"] == "video")
    w, h = int(vs["width"]), int(vs["height"])

    if w / h > 9 / 16:
        cw, ch, cx, cy = int(h * 9 / 16), h, (w - int(h * 9 / 16)) // 2, 0
    else:
        cw, ch, cx, cy = w, int(w * 16 / 9), 0, (h - int(w * 16 / 9)) // 2

    subprocess.run([
        "ffmpeg", "-y", "-i", path_in,
        "-vf", f"crop={cw}:{ch}:{cx}:{cy},scale=1080:1920",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", path_out,
    ], check=True)


def styled_captions(words: list[dict]) -> str:
    """Generate ASS captions with word-by-word highlighting (Opus.pro style)."""
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Arial,46,&H00FFFFFF,&H00000000,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,2,30,30,50,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    def ts(s): return f"{int(s//3600)}:{int((s%3600)//60)}:{s%60:.2f}".replace(".", ".")

    groups, group, n = [], [], 0
    for w in words:
        group.append(w); n += len(w["text"]) + 1
        if n > 50 or w["text"].rstrip().endswith((".", "!", "?")):
            groups.append(group); group, n = [], 0
    if group: groups.append(group)

    for g in groups:
        text = ""
        for w in g:
            cs = max(1, int((w["end"] - w["start"]) * 100))
            escaped = w["text"].replace("{", "\\{").replace("}", "\\}")
            text += f"{{\\kf{cs}}}{escaped} "
        lines.append(f"Dialogue: 0,{ts(g[0]['start'])},{ts(g[-1]['end'])},Default,,0,0,0,,{text.strip()}")

    return "\n".join(lines)


def burn_captions(video_in: str, ass_content: str, video_out: str):
    ass_path = video_out.replace(".mp4", ".ass")
    with open(ass_path, "w") as f:
        f.write(ass_content)
    log("Burning styled captions...")
    subprocess.run([
        "ffmpeg", "-y", "-i", video_in,
        "-vf", f"ass={ass_path}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", video_out,
    ], check=True)


def main():
    gateway = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].startswith("http") else GATEWAY

    # If first arg is the gateway URL, shift
    urls = sys.argv[1:]
    if gateway != GATEWAY:
        urls = urls[1:]

    if not urls:
        print("Usage: python worker.py [--gateway http://...] <youtube-url> [clip-index]")
        sys.exit(1)

    url = urls[0]
    clip_idx = int(urls[1]) if len(urls) > 1 else 0

    result = analyze(url)
    clips = result["clips"]
    if clip_idx >= len(clips):
        print(f"Only {len(clips)} clips found, requested index {clip_idx}")
        sys.exit(1)

    c = clips[clip_idx]
    start, end = c["clip"]["start_time"], c["clip"]["end_time"]
    vid = result["video_id"]

    print(f"\n{'='*50}")
    print(f"Clip #{clip_idx}: {c['title']}")
    print(f"Time: {start}s -> {end}s")
    print(f"Tags: {', '.join(c['tags'][:5])}...")
    print(f"{'='*50}\n")

    base = os.path.join(OUTPUT, vid)
    raw = f"{base}_raw.mp4"
    vert = f"{base}_vertical.mp4"
    final = f"{base}_final.mp4"

    download(url, start, end, raw)
    # yt-dlp outputs the filename differently, handle that
    raw_files = [f for f in os.listdir(OUTPUT) if f.startswith(vid) and f.endswith(".mp4")]
    if raw_files:
        raw = os.path.join(OUTPUT, raw_files[0])

    crop(raw, vert)
    os.remove(raw)

    # Generate styled captions from the full transcript words
    # In a real setup, you'd have the transcript from the gateway response
    print("\nStyled captions require the transcript. Run the gateway with whisper enabled.")
    print(f"Cropped video ready: {vert}")
    print(f"\nTo upload, use title: {c['title']}")
    print(f"Description: {c['description'][:100]}...")
    print(f"Tags: {', '.join(c['tags'])}")

    # Optional: burn captions if you have transcript data
    # ass = styled_captions(transcript_words)
    # burn_captions(vert, ass, final)


if __name__ == "__main__":
    main()
