import os
import json
import uuid
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.config import BASE_DIR, OUTPUT_DIR, GEMINI_API_KEY, GEMINI_MODEL, PORT, HOST, check_system_tools
from core.downloader import get_video_info, download_media_and_subtitles
from core.analyzer import analyze_transcript_with_gemini
from core.subtitle import parse_vtt, generate_ass_subtitles
from core.renderer import render_clip
from core.transcriber import extract_audio_for_asr, transcribe_with_nvidia_canary, generate_vtt_file

app = FastAPI(title="clipYT - AI Viral Video Clipper", version="2.0.0")

# Enable CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store
JOBS: Dict[str, Dict[str, Any]] = {}
executor = ThreadPoolExecutor(max_workers=3)

class ClipRequest(BaseModel):
    video_url: str = Field(..., description="YouTube video URL")
    clip_count: int = Field(default=3, ge=1, le=5)
    max_duration: int = Field(default=45, ge=15, le=90)
    aspect_ratio: str = Field(default="portrait", pattern="^(portrait|landscape|square)$")
    framing_mode: str = Field(default="fit_blur", pattern="^(fit_blur|fill_crop|fit_black)$")
    subtitle_style: str = Field(default="viral_yellow", pattern="^(viral_yellow|clean_white|minimal|none)$")

class VideoInfoRequest(BaseModel):
    video_url: str

def update_job_progress(job_id: str, step: str, progress: int, extra: Optional[Dict[str, Any]] = None):
    if job_id in JOBS:
        JOBS[job_id]["current_step"] = step
        JOBS[job_id]["progress"] = progress
        if extra:
            JOBS[job_id].update(extra)

def execute_clipping_job(job_id: str, req: ClipRequest):
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    start_time = time.time()

    try:
        update_job_progress(job_id, "Downloading video and transcript...", 15)
        media_data = download_media_and_subtitles(
            video_url=req.video_url,
            job_dir=job_dir,
            progress_callback=lambda step, p: update_job_progress(job_id, step, p)
        )

        title = media_data["title"]
        duration = media_data["duration"]
        video_path = media_data["video_path"]
        vtt_path = media_data["vtt_path"]

        update_job_progress(job_id, "Preparing transcript and subtitles...", 30, {
            "title": title,
            "duration": duration,
            "author": media_data["author"],
            "thumbnail": media_data["thumbnail"]
        })

        if not vtt_path or not vtt_path.exists():
            update_job_progress(
                job_id,
                "No native subtitles found. Extracting audio for NVIDIA Canary-1B Speech AI...",
                32
            )
            audio_wav = job_dir / "audio_track.wav"
            extract_audio_for_asr(video_path, audio_wav)

            cues = transcribe_with_nvidia_canary(
                wav_path=audio_wav,
                progress_callback=lambda step, p: update_job_progress(job_id, step, p)
            )

            if not cues or len(cues) < 2:
                raise RuntimeError("Speech-to-text transcription did not detect any spoken dialogue in this video.")

            vtt_path = job_dir / "subs.en.vtt"
            generate_vtt_file(cues, vtt_path)

            if audio_wav.exists():
                try:
                    audio_wav.unlink()
                except Exception:
                    pass
        else:
            cues = parse_vtt(vtt_path)

        if len(cues) < 2:
            raise RuntimeError("Subtitles could not be parsed or video has virtually no spoken dialogue.")

        update_job_progress(job_id, "Gemini AI is finding high-virality clips...", 55)
        clips = analyze_transcript_with_gemini(
            title=title,
            cues=cues,
            clip_count=req.clip_count,
            max_duration=req.max_duration,
            video_duration=duration
        )

        total_clips = len(clips)
        rendered_clips = []

        # Target dimensions for subtitles
        target_w = 1080 if req.aspect_ratio in ("portrait", "square") else 1920
        target_h = 1920 if req.aspect_ratio == "portrait" else 1080

        for idx, clip in enumerate(clips, 1):
            progress_val = int(60 + (35 * (idx / total_clips)))
            update_job_progress(
                job_id,
                f"Rendering Clip {idx}/{total_clips} (FFmpeg {req.framing_mode} + styled subtitles)...",
                progress_val
            )

            clip_filename = f"clip_{idx:02d}.mp4"
            dest_clip_path = job_dir / clip_filename
            ass_path = None

            # Generate ASS Subtitles if requested
            if req.subtitle_style != "none":
                ass_file = job_dir / f"clip_{idx:02d}.ass"
                ass_path = generate_ass_subtitles(
                    cues=cues,
                    clip_start=clip["start_seconds"],
                    clip_end=clip["end_seconds"],
                    output_path=ass_file,
                    hook_text=clip["hook"],
                    width=target_w,
                    height=target_h,
                    style_theme=req.subtitle_style
                )

            # Render with smart framing
            render_clip(
                source_video=video_path,
                output_clip_path=dest_clip_path,
                start_seconds=clip["start_seconds"],
                end_seconds=clip["end_seconds"],
                ass_subtitle_path=ass_path,
                aspect_ratio=req.aspect_ratio,
                framing_mode=req.framing_mode
            )

            file_size_mb = round(dest_clip_path.stat().st_size / (1024 * 1024), 2)
            rendered_clips.append({
                "clip_index": idx,
                "filename": clip_filename,
                "video_url": f"/api/clips/{job_id}/{clip_filename}",
                "download_url": f"/api/clips/{job_id}/{clip_filename}?download=true",
                "start_seconds": clip["start_seconds"],
                "end_seconds": clip["end_seconds"],
                "duration_seconds": clip["duration_seconds"],
                "hook": clip["hook"],
                "caption": clip["caption"],
                "score": clip["score"],
                "reason": clip.get("reason", ""),
                "size_mb": file_size_mb
            })

        elapsed = round(time.time() - start_time, 1)
        manifest = {
            "job_id": job_id,
            "source_url": req.video_url,
            "title": title,
            "author": media_data["author"],
            "thumbnail": media_data["thumbnail"],
            "aspect_ratio": req.aspect_ratio,
            "framing_mode": req.framing_mode,
            "elapsed_seconds": elapsed,
            "clips": rendered_clips
        }
        (job_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        JOBS[job_id]["status"] = "completed"
        JOBS[job_id]["progress"] = 100
        JOBS[job_id]["current_step"] = f"Finished! Created {len(rendered_clips)} viral clips in {elapsed}s."
        JOBS[job_id]["clips"] = rendered_clips
        JOBS[job_id]["manifest"] = manifest

    except Exception as e:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = str(e)
        JOBS[job_id]["current_step"] = f"Failed: {str(e)}"

# ----------------- API ENDPOINTS -----------------

@app.get("/api/health")
def health():
    tools = check_system_tools()
    return {
        "status": "online",
        "app": "clipYT",
        "version": "2.0.0",
        "tools": tools,
        "gemini_model": GEMINI_MODEL
    }

@app.post("/api/info")
def fetch_info(req: VideoInfoRequest):
    """Instant preview of YouTube title, duration, author, and thumbnail."""
    try:
        info = get_video_info(req.video_url)
        return {"ok": True, "info": info}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/clip")
def start_clip_job(req: ClipRequest, background_tasks: BackgroundTasks):
    """Start an asynchronous clipping job."""
    tools = check_system_tools()
    if not tools["ffmpeg"]:
        raise HTTPException(500, "FFmpeg is not installed or not found on system PATH.")
    if not tools["yt_dlp"]:
        raise HTTPException(500, "yt-dlp is not installed or not found on system PATH.")
    if not tools["gemini_api_key_configured"]:
        raise HTTPException(400, "GEMINI_API_KEY is not configured in clipYT .env file.")

    job_id = uuid.uuid4().hex[:10]
    JOBS[job_id] = {
        "job_id": job_id,
        "source_url": req.video_url,
        "status": "processing",
        "progress": 5,
        "current_step": "Starting job initialization...",
        "created_at": time.time(),
        "clips": [],
        "error": None
    }

    # Run in background thread
    executor.submit(execute_clipping_job, job_id, req)
    return {"job_id": job_id, "status": "processing"}

@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    if job_id not in JOBS:
        # Check if exists on disk
        manifest_file = OUTPUT_DIR / job_id / "manifest.json"
        if manifest_file.exists():
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
            return {
                "job_id": job_id,
                "status": "completed",
                "progress": 100,
                "current_step": "Completed",
                "clips": data.get("clips", []),
                "manifest": data
            }
        raise HTTPException(404, "Job ID not found.")
    return JOBS[job_id]

@app.get("/api/jobs/{job_id}/stream")
async def stream_job_progress(job_id: str):
    """Server-Sent Events (SSE) stream for real-time UI updates."""
    async def event_generator():
        while True:
            if job_id not in JOBS:
                yield f"data: {json.dumps({'status': 'not_found'})}\n\n"
                break
            job = JOBS[job_id]
            data = {
                "status": job["status"],
                "progress": job["progress"],
                "step": job["current_step"],
                "clips": job.get("clips", []),
                "error": job.get("error")
            }
            yield f"data: {json.dumps(data)}\n\n"
            if job["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.8)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/clips/{job_id}/{filename}")
def stream_clip_file(job_id: str, filename: str, download: bool = False):
    clip_file = OUTPUT_DIR / job_id / filename
    if not clip_file.exists() or not clip_file.is_file():
        raise HTTPException(404, "Requested video clip was not found.")
    
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return FileResponse(clip_file, media_type="video/mp4", headers=headers)

@app.get("/api/jobs")
def list_jobs():
    """Returns list of recent jobs saved on disk."""
    recent = []
    if OUTPUT_DIR.exists():
        for d in sorted(OUTPUT_DIR.iterdir(), key=os.path.getmtime, reverse=True):
            if d.is_dir() and (d / "manifest.json").exists():
                try:
                    meta = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
                    recent.append(meta)
                except Exception:
                    pass
    return {"jobs": recent[:15]}

# Static Frontend Mount
static_dir = BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
