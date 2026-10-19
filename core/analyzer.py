import json
import re
import time
import requests
from typing import List, Dict, Any
from .config import GEMINI_API_KEY, GEMINI_MODEL

def fmt_time(sec: float) -> str:
    m = int(sec // 60)
    s = int(sec % 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{m:02}:{s:02}.{ms:03}"

def analyze_transcript_with_gemini(
    title: str,
    cues: List[Dict[str, Any]],
    clip_count: int,
    max_duration: int,
    video_duration: float
) -> List[Dict[str, Any]]:
    """
    Sends the formatted transcript to Gemini to extract high-virality clips.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured in clipYT .env file.")

    # Build condensed transcript lines
    transcript_lines = [
        f"[{fmt_time(c['start'])} --> {fmt_time(c['end'])}] {c['text']}"
        for c in cues
    ]
    transcript_text = "\n".join(transcript_lines)

    # Subsample if transcript is huge
    max_chars = 95000
    if len(transcript_text) > max_chars:
        step = max(1, len(transcript_text) // max_chars)
        transcript_text = "\n".join(transcript_lines[::step])

    prompt = f"""You are a master short-form viral video editor for YouTube Shorts, TikTok, and Instagram Reels.
Analyze this video transcript and identify the top {clip_count} most compelling, viral clip opportunities.

Selection Criteria:
1. Immediate Hook: The first 3 seconds must create curiosity, surprise, or value.
2. Complete Thought: The clip must make sense standalone without external context.
3. High Engagement: Favor key takeaways, dramatic revelations, funny moments, or counter-intuitive tips.
4. Clip Length: Between 15 and {max_duration} seconds.
5. Non-overlapping: Clips must not overlap in timestamps.

Format your response ONLY as a JSON array of objects with the following schema:
[
  {{
    "start_seconds": 24.5,
    "end_seconds": 58.2,
    "hook": "Concise, punchy hook title under 12 words",
    "caption": "Compelling social post caption with 3-4 trending hashtags",
    "score": 95,
    "reason": "Why this snippet has high retention and shareability"
  }}
]

Video Title: {title}
Total Video Duration: {video_duration:.1f} seconds

Transcript:
{transcript_text}"""

    # Try primary GEMINI_MODEL first, followed by stable fallbacks if unavailable or rate-limited
    models_to_try = [GEMINI_MODEL]
    for fallback in ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]:
        if fallback not in models_to_try:
            models_to_try.append(fallback)

    last_error = None
    clips_raw = None

    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        
        # Up to 2 attempts per model for transient network drops / 503 high demand spikes
        for attempt in range(2):
            try:
                resp = requests.post(
                    url,
                    params={"key": GEMINI_API_KEY},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "responseMimeType": "application/json",
                            "temperature": 0.4
                        }
                    },
                    timeout=180
                )

                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        raise RuntimeError(f"Gemini model {model_name} returned no candidates: {data}")

                    parts = candidates[0].get("content", {}).get("parts", [])
                    # Extract text parts while ignoring internal reasoning/thought parts
                    text_parts = [p["text"] for p in parts if "text" in p and not p.get("thought", False)]
                    if not text_parts:
                        text_parts = [p["text"] for p in parts if "text" in p]

                    raw_text = "\n".join(text_parts).strip()
                    clean_text = raw_text
                    if clean_text.startswith("```"):
                        clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text, flags=re.IGNORECASE)
                        clean_text = re.sub(r"\s*```$", "", clean_text)

                    try:
                        parsed = json.loads(clean_text)
                    except Exception:
                        match = re.search(r"\[\s*\{.*\}\s*\]", clean_text, re.DOTALL)
                        if match:
                            parsed = json.loads(match.group(0))
                        else:
                            raise

                    if isinstance(parsed, list) and len(parsed) > 0:
                        clips_raw = parsed
                        break
                    else:
                        raise RuntimeError(f"Model {model_name} response was not a valid clip array.")

                elif resp.status_code in (503, 429, 500):
                    err_msg = resp.text[:400]
                    last_error = f"Gemini API Error ({model_name} HTTP {resp.status_code}): {err_msg}"
                    time.sleep(1.5 * (attempt + 1))
                    continue
                else:
                    err_msg = resp.text[:400]
                    last_error = f"Gemini API Error ({model_name} HTTP {resp.status_code}): {err_msg}"
                    break

            except requests.RequestException as e:
                last_error = f"Network error connecting to Gemini ({model_name}): {str(e)}"
                time.sleep(1.0)
                continue
            except Exception as e:
                last_error = f"Error processing Gemini response ({model_name}): {str(e)}"
                break

        if clips_raw:
            break

    if not clips_raw:
        raise RuntimeError(last_error or "Failed to extract viral clips with Gemini AI.")

    # Validate and filter
    valid_clips = []
    for item in clips_raw:
        try:
            start = float(item["start_seconds"])
            end = float(item["end_seconds"])
            duration = end - start

            if start < 0 or end <= start or duration < 12 or duration > (max_duration + 5) or end > (video_duration + 2):
                continue

            valid_clips.append({
                "start_seconds": round(start, 2),
                "end_seconds": round(min(end, video_duration), 2),
                "duration_seconds": round(end - start, 2),
                "hook": str(item.get("hook", "Must-Watch Moment"))[:120].strip(),
                "caption": str(item.get("caption", ""))[:280].strip(),
                "score": max(50, min(100, int(float(item.get("score", 85))))),
                "reason": str(item.get("reason", ""))[:200].strip()
            })
        except (KeyError, TypeError, ValueError):
            continue

    # Sort by score descending
    valid_clips.sort(key=lambda x: x["score"], reverse=True)

    # Deduplicate / avoid overlaps
    selected = []
    for candidate in valid_clips:
        c_start, c_end = candidate["start_seconds"], candidate["end_seconds"]
        # Ensure no overlap with already selected
        if all(c_end <= s["start_seconds"] or c_start >= s["end_seconds"] for s in selected):
            selected.append(candidate)
        if len(selected) >= clip_count:
            break

    if not selected:
        raise RuntimeError("Gemini found no clips meeting the duration and quality criteria.")

    return selected
