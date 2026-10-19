import os
import io
import re
import wave
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Callable, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import (
    NVIDIA_API_KEY,
    NVIDIA_ASR_MODEL,
    NVIDIA_ASR_FUNCTION_ID,
    NVIDIA_RIVA_URI,
    GEMINI_API_KEY,
    GEMINI_MODEL
)

def extract_audio_for_asr(video_path: Path, output_wav: Path) -> Path:
    """
    Extracts a 16kHz mono 16-bit PCM WAV audio track suitable for ASR models.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(output_wav)
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        err = (p.stderr or p.stdout or "Audio extraction failed")[-1000:]
        raise RuntimeError(f"FFmpeg audio extraction error: {err}")
    return output_wav

def slice_wav_file(wav_path: Path, chunk_seconds: float = 20.0) -> List[Tuple[float, float, bytes]]:
    """
    Slices a 16kHz mono WAV file into RAM-buffered WAV chunks without subprocesses.
    Returns list of (start_sec, end_sec, wav_bytes).
    """
    slices = []
    with wave.open(str(wav_path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        total_duration = n_frames / float(framerate)

        frames_per_chunk = int(framerate * chunk_seconds)
        current_frame = 0

        while current_frame < n_frames:
            read_count = min(frames_per_chunk, n_frames - current_frame)
            wf.setpos(current_frame)
            frames = wf.readframes(read_count)

            start_sec = round(current_frame / float(framerate), 3)
            end_sec = round((current_frame + read_count) / float(framerate), 3)

            # Package into an in-memory WAV file
            buf = io.BytesIO()
            with wave.open(buf, "wb") as out_wf:
                out_wf.setnchannels(n_channels)
                out_wf.setsampwidth(sampwidth)
                out_wf.setframerate(framerate)
                out_wf.writeframes(frames)
            
            slices.append((start_sec, end_sec, buf.getvalue()))
            current_frame += read_count

    return slices

def transcribe_with_nvidia_canary(
    wav_path: Path,
    progress_callback: Optional[Callable[[str, int], None]] = None
) -> List[Dict[str, Any]]:
    """
    Transcribes the audio using NVIDIA Canary-1B-ASR NIM via Riva gRPC client.
    Returns timed subtitle cues: [{'start': float, 'end': float, 'text': str}, ...]
    """
    if not NVIDIA_API_KEY:
        raise RuntimeError("NVIDIA_API_KEY is not configured in .env file.")

    try:
        import riva.client
    except ImportError:
        raise RuntimeError("nvidia-riva-client is not installed. Please install via: pip install nvidia-riva-client")

    auth = riva.client.Auth(
        uri=NVIDIA_RIVA_URI,
        use_ssl=True,
        metadata_args=[
            ["function-id", NVIDIA_ASR_FUNCTION_ID],
            ["authorization", f"Bearer {NVIDIA_API_KEY}"]
        ]
    )

    if progress_callback:
        progress_callback("Extracting and segmenting audio for Canary ASR...", 28)

    slices = slice_wav_file(wav_path, chunk_seconds=20.0)
    total_slices = len(slices)
    if total_slices == 0:
        return []

    if progress_callback:
        progress_callback(f"Transcribing audio with NVIDIA Canary ASR (0/{total_slices} chunks)...", 30)

    def _transcribe_single_slice(start_sec: float, end_sec: float, wav_bytes: bytes) -> Tuple[float, float, str]:
        asr = riva.client.ASRService(auth)
        config = riva.client.RecognitionConfig(
            language_code="en-US",
            max_alternatives=1,
            enable_automatic_punctuation=True
        )
        riva.client.add_audio_file_specs_to_config(config, wav_bytes)
        try:
            res = asr.offline_recognize(wav_bytes, config)
            text = ""
            if res and res.results:
                text = " ".join([r.alternatives[0].transcript for r in res.results if r.alternatives])
            return start_sec, end_sec, text.strip()
        except Exception as e:
            # Return empty on single chunk failure to avoid failing whole job
            return start_sec, end_sec, ""

    results = []
    completed = 0

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {
            executor.submit(_transcribe_single_slice, s, e, b): (s, e)
            for s, e, b in slices
        }
        for future in as_completed(future_map):
            s, e, text = future.result()
            results.append((s, e, text))
            completed += 1
            if progress_callback:
                pct = int(30 + (12 * (completed / total_slices)))
                progress_callback(
                    f"Transcribing audio with NVIDIA Canary ASR ({completed}/{total_slices} chunks)...",
                    pct
                )

    # Sort results chronologically by chunk start
    results.sort(key=lambda x: x[0])

    # Convert chunks into timestamped subtitle cues
    cues = []
    for start_sec, end_sec, text in results:
        if not text:
            continue
        
        # Split chunk text into clean sentences or clauses
        sentences = [s.strip() for s in re.split(r'(?<=[.?!])\s+', text) if s.strip()]
        if not sentences:
            sentences = [text]

        total_words = sum(max(1, len(s.split())) for s in sentences)
        chunk_duration = max(0.5, end_sec - start_sec)
        cur_start = start_sec

        for s in sentences:
            w_count = max(1, len(s.split()))
            dur = (w_count / total_words) * chunk_duration
            cur_end = min(end_sec, cur_start + dur)
            cues.append({
                "start": round(cur_start, 3),
                "end": round(cur_end, 3),
                "text": s
            })
            cur_start = cur_end

    return cues

def generate_vtt_file(cues: List[Dict[str, Any]], vtt_path: Path) -> Path:
    """
    Serializes cue objects into standard WebVTT format on disk.
    """
    def _sec_to_vtt_timestamp(sec: float) -> str:
        sec = max(0.0, sec)
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        ms = int(round((sec - int(sec)) * 1000))
        if ms >= 1000:
            s += 1
            ms = 0
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

    lines = ["WEBVTT", ""]
    for idx, cue in enumerate(cues, 1):
        start_str = _sec_to_vtt_timestamp(cue["start"])
        end_str = _sec_to_vtt_timestamp(cue["end"])
        text = cue["text"].strip()
        if text and cue["end"] > cue["start"]:
            lines.append(f"{idx}")
            lines.append(f"{start_str} --> {end_str}")
            lines.append(text)
            lines.append("")

    vtt_path.parent.mkdir(parents=True, exist_ok=True)
    vtt_path.write_text("\n".join(lines), encoding="utf-8")
    return vtt_path
