import re
import json
import httpx


def extract_video_id(url: str) -> str | None:
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


async def fetch(url: str) -> dict:
    video_id = extract_video_id(url)
    if not video_id:
        return {"error": "Invalid YouTube URL"}

    page_url = f"https://www.youtube.com/watch?v={video_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as c:
        r = await c.get(page_url, headers=headers)
        r.raise_for_status()

    player = None
    match = re.search(r"ytInitialPlayerResponse\s*=\s*({.*?});", r.text, re.DOTALL)
    if match:
        player = json.loads(match.group(1))

    if not player:
        return {"error": "Could not extract player data"}

    details = player.get("videoDetails", {})
    duration = int(details.get("lengthSeconds", 0))

    heatmap = []
    try:
        markers = (
            player["playerOverlays"]["playerOverlayRenderer"]["heatmap"]["heatmapRenderer"]["heatMarkers"]
        )
        for m in markers:
            hm = m.get("heatMarkerRenderer", {})
            start_ms = hm.get("timeRangeStartMillis", 0)
            dur_ms = hm.get("markerDurationMillis", 0)
            intensity = hm.get("heatMarkerIntensityNormalized", 0.0)
            heatmap.append({
                "start": start_ms / 1000.0,
                "end": (start_ms + dur_ms) / 1000.0,
                "intensity": intensity,
            })
    except (KeyError, TypeError):
        pass

    return {
        "video_id": video_id,
        "title": details.get("title", ""),
        "author": details.get("author", ""),
        "channel_id": details.get("channelId", ""),
        "description": details.get("shortDescription", ""),
        "duration": duration,
        "heatmap": heatmap,
    }
