import json
from config import settings
from google import genai

_client = None


def _get_client():
    global _client
    if _client is None and settings.gemini_api_key:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


CLIP_PROMPT = """You are a viral short-clip expert. I'll give you a video transcript (with timestamps), title, and YouTube heatmap data. Find the BEST {max_clips} segments that would make viral YouTube Shorts.

RULES for clip selection:
- Each clip should be {clip_duration}s long (min {clip_min}s, max {clip_max}s)
- Look for: hooks, surprising facts, emotional peaks, punchlines, strong opinions, questions, story climaxes
- Prioritize segments with high heatmap intensity (most replayed)
- Clips should NOT overlap
- Return them sorted by virality potential (best first)

TRANSCRIPT:
{transcript}

TITLE: {title}
DESCRIPTION: {description}
HEATMAP (top replayed segments): {heatmap}

For each clip, provide:
1. start_time / end_time (in seconds)
2. A clickbait title under 100 chars with #shorts
3. A short engaging description (2-3 lines with emojis + hashtags)
4. 10-15 relevant tags
5. 5-8 keywords for search
6. Reasoning for why this segment is viral

Return ONLY JSON (no markdown):
{{"clips": [
  {{
    "clip": {{"start_time": float, "end_time": float}},
    "title": "str",
    "description": "str",
    "tags": ["str"],
    "keywords": ["str"],
    "reasoning": "str"
  }}
]}}"""


def format_transcript(words: list[dict]) -> str:
    lines = []
    current_line = ""
    current_start = 0

    for w in words:
        if not current_line:
            current_start = w["start"]
            current_line = w["text"]
        elif len(current_line) + len(w["text"]) + 1 > 80:
            lines.append(f"[{current_start:.1f}s] {current_line}")
            current_start = w["start"]
            current_line = w["text"]
        else:
            current_line += " " + w["text"]

    if current_line:
        lines.append(f"[{current_start:.1f}s] {current_line}")

    return "\n".join(lines)


def format_heatmap(heatmap: list[dict]) -> str:
    top = sorted(heatmap, key=lambda s: s["intensity"], reverse=True)[:15]
    return json.dumps(top, indent=2) if top else "No heatmap data available"


def analyze(video_title: str, video_description: str, duration: float,
            transcript_words: list[dict], heatmap: list[dict]) -> list[dict]:
    client = _get_client()
    if not client:
        return _fallback_analysis(video_title, transcript_words, duration)

    transcript = format_transcript(transcript_words)
    heatmap_str = format_heatmap(heatmap)

    prompt = CLIP_PROMPT.format(
        max_clips=settings.max_clips,
        clip_duration=settings.clip_duration,
        clip_min=settings.clip_min_duration,
        clip_max=settings.clip_max_duration,
        transcript=transcript,
        title=video_title,
        description=video_description[:500],
        heatmap=heatmap_str,
    )

    try:
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={"temperature": 0.7, "max_output_tokens": 2048},
        )
        text = resp.text.strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(text)
        return data.get("clips", [])
    except Exception as e:
        print(f"Gemini error: {e}")
        return _fallback_analysis(video_title, transcript_words, duration)


def _fallback_analysis(video_title: str, transcript_words: list[dict], duration: float) -> list[dict]:
    clips = []
    if not transcript_words:
        mid = duration / 2
        half = settings.clip_duration / 2
        clips.append({
            "clip": {"start_time": round(max(0, mid - half), 1), "end_time": round(min(duration, mid + half), 1)},
            "title": f"{video_title[:80]} #shorts",
            "description": f"{video_title}\n\n#shorts #youtubeshorts",
            "tags": ["shorts"],
            "keywords": [],
            "reasoning": "Fallback: no transcript available",
        })
        return clips

    chunks = []
    chunk = {"words": [], "start": 0, "end": 0}
    char_count = 0
    for w in transcript_words:
        if char_count == 0:
            chunk["start"] = w["start"]
        chunk["words"].append(w["text"])
        char_count += len(w["text"]) + 1
        if char_count > 300:
            chunk["end"] = w["end"]
            chunks.append(chunk)
            chunk = {"words": [], "start": 0, "end": 0}
            char_count = 0
    if chunk["words"]:
        chunk["end"] = transcript_words[-1]["end"]
        chunks.append(chunk)

    step = max(1, len(chunks) // settings.max_clips)
    for i in range(0, min(len(chunks), settings.max_clips * step), step):
        c = chunks[i]
        text = " ".join(c["words"])
        clip_dur = settings.clip_duration
        if c["end"] - c["start"] > clip_dur:
            mid = (c["start"] + c["end"]) / 2
            half = clip_dur / 2
            start = max(0, mid - half)
            end = min(duration, mid + half)
        else:
            start = c["start"]
            end = c["end"]

        preview = text[:80].strip()
        clips.append({
            "clip": {"start_time": round(start, 1), "end_time": round(end, 1)},
            "title": f"{preview[:80]} #shorts",
            "description": f"{preview}\n\n#shorts #youtubeshorts",
            "tags": ["shorts"],
            "keywords": [],
            "reasoning": "Fallback: evenly split transcript chunks",
        })

    return clips[:settings.max_clips]
