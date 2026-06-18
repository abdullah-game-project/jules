import os
import uuid
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from config import settings
from downloader import download_audio, cleanup
from transcriber import transcribe
from heatmap import fetch as fetch_heatmap
from analyzer import analyze as analyze_clips
from captions import generate_srt, generate_ass_styled

app = FastAPI(title="Opus Killer")

jobs: dict = {}  # simple in-memory job store


class AnalyzeRequest(BaseModel):
    url: str


class ClipResult(BaseModel):
    clip: dict
    title: str
    description: str
    tags: list[str]
    keywords: list[str]
    reasoning: str


class AnalyzeResponse(BaseModel):
    job_id: str
    video_id: str
    title: str
    author: str
    channel_id: str
    duration: float
    heatmap_segments: int
    transcript_language: str | None
    clips: list[ClipResult]


@app.get("/")
async def root():
    return {
        "status": "ok",
        "endpoints": {
            "POST /analyze": "Analyze a YouTube URL, returns viral clip candidates",
            "GET /jobs": "List all analyzed jobs",
            "GET /jobs/{id}": "Get specific job details",
        },
    }


@app.get("/jobs")
async def list_jobs():
    return {"jobs": [{"job_id": jid, "title": j.get("title"), "status": j.get("status", "done")}
                     for jid, j in jobs.items()]}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(404)
    return j


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    os.makedirs(settings.temp_dir, exist_ok=True)

    info = await fetch_heatmap(req.url)
    if "error" in info:
        raise HTTPException(400, info["error"])

    vid = info["video_id"]
    audio_path = await download_audio(req.url, vid)

    transcript_words = []
    transcript_lang = None
    if audio_path:
        try:
            tr = transcribe(audio_path)
            transcript_words = tr.get("words", [])
            transcript_lang = tr.get("language")
        except Exception as e:
            print(f"Transcription error: {e}")
        finally:
            cleanup(vid)

    clips = analyze_clips(
        info["title"],
        info["description"],
        info["duration"],
        transcript_words,
        info["heatmap"],
    )

    result_clips = []
    for i, c in enumerate(clips):
        clip_info = c.get("clip", {})
        start = clip_info.get("start_time", 0)
        end = clip_info.get("end_time", 0)

        clip_words = [w for w in transcript_words if w["end"] >= start and w["start"] <= end]

        result_clips.append(ClipResult(
            clip=clip_info,
            title=c.get("title", ""),
            description=c.get("description", ""),
            tags=c.get("tags", []),
            keywords=c.get("keywords", []),
            reasoning=c.get("reasoning", ""),
        ))

    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {
        "job_id": job_id,
        "video_id": vid,
        "title": info["title"],
        "author": info["author"],
        "status": "ready",
    }

    return AnalyzeResponse(
        job_id=job_id,
        video_id=vid,
        title=info["title"],
        author=info["author"],
        channel_id=info["channel_id"],
        duration=info["duration"],
        heatmap_segments=len(info.get("heatmap", [])),
        transcript_language=transcript_lang,
        clips=result_clips,
    )
