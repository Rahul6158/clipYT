import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

def render_clip(
    source_video: Path,
    output_clip_path: Path,
    start_seconds: float,
    end_seconds: float,
    ass_subtitle_path: Optional[Path] = None,
    aspect_ratio: str = "portrait",       # portrait (9:16), landscape (16:9), square (1:1)
    framing_mode: str = "fit_blur",        # fit_blur (Recommended), fill_crop, fit_black
    timeout: int = 1800
) -> Path:
    """
    Renders an individual clip with smart aspect ratio framing and burn-in ASS subtitles.
    Solves both framing issues (no lost content) and subtitle styling/margins.
    """
    duration = end_seconds - start_seconds
    job_dir = source_video.parent

    # Determine canvas target dimensions
    if aspect_ratio == "portrait":
        target_w, target_h = 1080, 1920
    elif aspect_ratio == "square":
        target_w, target_h = 1080, 1080
    else: # landscape
        target_w, target_h = 1920, 1080

    # Build Video Filter Graph
    # -------------------------------------------------------------
    # 1. Framing Layouts
    # -------------------------------------------------------------
    if aspect_ratio == "landscape":
        # Native widescreen: simple scale to 1920:1080
        vf_base = f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    elif framing_mode == "fit_blur":
        # Professional Blurred Backdrop:
        # Background: Zoomed, cropped, heavily blurred
        # Foreground: Full uncropped original video centered with crisp edges
        vf_base = (
            f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h},"
            f"boxblur=26:6[bg];"
            f"[0:v]scale={target_w}:-2:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    elif framing_mode == "fill_crop":
        # Full Fill: Crops sides to fill 9:16 completely
        vf_base = (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h}:(in_w-{target_w})/2:(in_h-{target_h})/2,setsar=1"
        )
    else: # fit_black / letterbox
        vf_base = (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=0x0a0b10,setsar=1"
        )

    # -------------------------------------------------------------
    # 2. Add Styled Subtitles
    # -------------------------------------------------------------
    filter_complex = vf_base
    if ass_subtitle_path and ass_subtitle_path.exists():
        # Using filename directly with cwd=job_dir avoids Windows path colon escaping issues
        sub_name = ass_subtitle_path.name
        if "[bg]" in vf_base: # Filtergraph with named streams
            filter_complex = f"{vf_base}[vmid];[vmid]ass='{sub_name}'[outv]"
            map_args = ["-map", "[outv]", "-map", "0:a?"]
        else:
            filter_complex = f"{vf_base},ass='{sub_name}'"
            map_args = []
    else:
        if "[bg]" in vf_base:
            filter_complex = f"{vf_base}[outv]"
            map_args = ["-map", "[outv]", "-map", "0:a?"]
        else:
            map_args = []

    # Build FFmpeg command
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-ss", f"{start_seconds:.3f}",
        "-i", source_video.name,
        "-t", f"{duration:.3f}",
        "-filter_complex" if "[bg]" in vf_base else "-vf",
        filter_complex,
        *map_args,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "21",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_clip_path.name
    ]

    p = subprocess.run(
        cmd,
        cwd=str(job_dir),
        capture_output=True,
        text=True,
        timeout=timeout
    )

    if p.returncode != 0:
        err = (p.stderr or p.stdout or "FFmpeg encoding failed")[-2000:]
        raise RuntimeError(f"FFmpeg error: {err}")

    if not output_clip_path.exists() or output_clip_path.stat().st_size == 0:
        raise RuntimeError("FFmpeg completed but output clip was not generated.")

    return output_clip_path
