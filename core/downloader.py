import json
import subprocess
import re
from pathlib import Path
from typing import Dict, Any, Callable, Optional
from .config import MAX_VIDEO_BYTES, get_yt_dlp_base_args

def run_cmd(cmd, timeout=3600):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        err = (p.stderr or p.stdout or "Process execution failed")[-2000:]
        raise RuntimeError(err)
    return p.stdout

def get_video_info(video_url: str) -> Dict[str, Any]:
    """Fetch video metadata quickly without downloading media."""
    base_args = get_yt_dlp_base_args()
    stdout = run_cmd([
        "yt-dlp",
        *base_args,
        "--skip-download",
        "--dump-single-json",
        "--no-playlist",
        video_url
    ], timeout=60)
    
    meta = json.loads(stdout)
    return {
        "title": meta.get("title") or "YouTube Video",
        "duration": float(meta.get("duration") or 0),
        "author": meta.get("uploader") or meta.get("channel") or "Unknown Creator",
        "thumbnail": meta.get("thumbnail") or "",
        "view_count": meta.get("view_count") or 0,
        "description": (meta.get("description") or "")[:500]
    }

def download_audio_track(video_url: str, output_wav: Path) -> Path:
    """
    Downloads audio stream from YouTube and encodes as 16kHz mono WAV for ASR.
    """
    base_args = get_yt_dlp_base_args()
    cmd = [
        "yt-dlp",
        *base_args,
        "--no-playlist",
        "-f", "ba/b",
        "-x",
        "--audio-format", "wav",
        "--postprocessor-args", "ffmpeg:-ar 16000 -ac 1",
        "-o", str(output_wav.with_suffix(".%(ext)s")),
        video_url
    ]
    run_cmd(cmd, timeout=600)
    for c in output_wav.parent.glob(f"{output_wav.stem}.*"):
        if c.suffix.lower() == ".wav":
            if c != output_wav:
                c.replace(output_wav)
            return output_wav
    raise RuntimeError("Audio download/conversion failed.")

def download_media_and_subtitles(
    video_url: str,
    job_dir: Path,
    progress_callback: Optional[Callable[[str, int], None]] = None
) -> Dict[str, Any]:
    """
    Downloads source video and English subtitles into job_dir.
    Returns dictionary with paths to video and vtt file.
    """
    if progress_callback:
        progress_callback("Extracting video metadata...", 10)

    info = get_video_info(video_url)
    duration = info["duration"]
    if duration <= 0:
        raise RuntimeError("Could not determine valid video duration.")

    # 1. Download English Subtitles (Automatic + Manual)
    if progress_callback:
        progress_callback("Fetching transcript and subtitles...", 25)

    base_args = get_yt_dlp_base_args()
    sub_pattern = str(job_dir / "subs.%(ext)s")
    try:
        run_cmd([
            "yt-dlp",
            *base_args,
            "--no-playlist",
            "--write-auto-subs",
            "--write-subs",
            "--sub-langs", "en.*,en",
            "--sub-format", "vtt",
            "--skip-download",
            "-o", sub_pattern,
            video_url
        ], timeout=120)
    except Exception as e:
        # Some videos may have alternate naming
        pass

    vtts = sorted(job_dir.glob("subs*.vtt"))
    vtt_path = vtts[0] if vtts else None

    # 2. Download Source Video
    if progress_callback:
        progress_callback("Downloading high-quality source video...", 40)

    video_path = job_dir / "source.mp4"
    run_cmd([
        "yt-dlp",
        *base_args,
        "--no-playlist",
        "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "--merge-output-format", "mp4",
        "-o", str(video_path),
        video_url
    ], timeout=3600)

    if not video_path.exists():
        candidates = list(job_dir.glob("source.*"))
        if candidates:
            video_path = candidates[0]
        else:
            raise RuntimeError("Source video could not be saved.")

    if video_path.stat().st_size > MAX_VIDEO_BYTES:
        raise RuntimeError(f"Video file exceeds max size limit ({MAX_VIDEO_BYTES // (1024*1024)} MB).")

    return {
        "title": info["title"],
        "duration": duration,
        "author": info["author"],
        "thumbnail": info["thumbnail"],
        "video_path": video_path,
        "vtt_path": vtt_path
    }
