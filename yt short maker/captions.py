import os
from config import settings


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,46,&H00FFFFFF,&H00000000,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,2,30,30,50,1
Style: Highlight,Arial,46,&H00FFD700,&H00000000,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,2,30,30,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m}:{s:.2f}".replace(".", ".")


def generate_srt(words: list[dict], video_id: str) -> str:
    path = os.path.join(settings.temp_dir, f"{video_id}.srt")
    lines = []
    idx = 1

    groups = []
    group = []
    group_chars = 0
    for w in words:
        group.append(w)
        group_chars += len(w["text"]) + 1
        if group_chars > 50 or w["text"].rstrip().endswith((".", "!", "?")):
            groups.append(group)
            group = []
            group_chars = 0
    if group:
        groups.append(group)

    for g in groups:
        start = g[0]["start"]
        end = g[-1]["end"]
        text = " ".join(w["text"] for w in g)
        lines.append(f"{idx}")
        lines.append(f"{_srt_time(start)} --> {_srt_time(end)}")
        lines.append(text)
        lines.append("")
        idx += 1

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


def generate_ass_styled(words: list[dict], video_id: str) -> str:
    """Generate ASS subtitles with word-by-word karaoke highlighting (Opus.pro style)."""
    path = os.path.join(settings.temp_dir, f"{video_id}.ass")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    events = []
    groups = []
    group = []
    group_chars = 0

    for w in words:
        group.append(w)
        group_chars += len(w["text"]) + 1
        if group_chars > 50 or w["text"].rstrip().endswith((".", "!", "?")):
            groups.append(group)
            group = []
            group_chars = 0
    if group:
        groups.append(group)

    for g in groups:
        start = _ass_time(g[0]["start"])
        end = _ass_time(g[-1]["end"])
        total_duration = g[-1]["end"] - g[0]["start"]
        if total_duration <= 0:
            continue

        ass_text = ""
        for w in g:
            word_duration = w["end"] - w["start"]
            cs = max(1, int(word_duration * 100))
            escaped = w["text"].replace("{", "\\{").replace("}", "\\}")
            if " " in escaped:
                ass_text += f"{{\\k{cs}}}{escaped} "
            else:
                ass_text += f"{{\\kf{cs}}}{escaped} "

        ass_text = ass_text.rstrip()
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{ass_text}")

    content = ASS_HEADER + "\n".join(events)
    with open(path, "w") as f:
        f.write(content)
    return path
