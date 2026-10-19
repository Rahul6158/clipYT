import re
from pathlib import Path
from typing import List, Dict, Any, Optional

def clean_vtt_text(text: str) -> str:
    """Strip WebVTT tags, timestamps, and entities."""
    # Remove cue tags like <c.color>...</c> or <00:00:01.000>
    cleaned = re.sub(r"<[^>]+>", "", text)
    # Remove HTML entities
    cleaned = cleaned.replace("&amp;", "&").replace("&quot;", '"').replace("&apos;", "'")
    cleaned = cleaned.replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", cleaned).strip()

def parse_vtt(vtt_path: Path) -> List[Dict[str, Any]]:
    """Parse a WebVTT file into start, end, text cues."""
    if not vtt_path.exists():
        return []
    
    content = vtt_path.read_text(encoding="utf-8", errors="replace")
    cues = []
    current_cue = None

    for line in content.splitlines():
        line = line.strip()
        # Match timestamp lines (HH:MM:SS.mmm or MM:SS.mmm)
        m = re.search(
            r"(?:(\d{2,}):)?(\d{2}):(\d{2})[.,](\d{3})\s+-->\s+(?:(\d{2,}):)?(\d{2}):(\d{2})[.,](\d{3})",
            line
        )
        if m:
            g = m.groups()
            start = (int(g[0] or 0) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000)
            end = (int(g[4] or 0) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000)
            current_cue = {"start": round(start, 3), "end": round(end, 3), "text": ""}
            cues.append(current_cue)
        elif current_cue and line:
            if line.startswith(("WEBVTT", "NOTE", "Kind:", "Language:")) or re.fullmatch(r"\d+", line):
                continue
            cleaned = clean_vtt_text(line)
            if cleaned:
                if not current_cue["text"]:
                    current_cue["text"] = cleaned
                elif cleaned != current_cue["text"]:
                    current_cue["text"] += " " + cleaned

    # Filter out empty or zero-duration cues
    valid_cues = []
    for c in cues:
        c["text"] = c["text"].strip()
        if c["text"] and c["end"] > c["start"]:
            valid_cues.append(c)

    # Sort cues chronologically
    valid_cues.sort(key=lambda x: x["start"])
    return valid_cues

def chunk_cue(cue: Dict[str, Any], max_words: int = 4) -> List[Dict[str, Any]]:
    """
    Split a long cue into short, punchy 3-5 word bursts.
    This creates modern TikTok/Reels-style captions that fit vertical aspect ratios
    without overflowing or wrapping into messy 4-line blocks.
    """
    words = cue["text"].split()
    if len(words) <= max_words:
        return [cue]

    total_duration = max(0.5, cue["end"] - cue["start"])
    total_words = len(words)
    chunks = []

    # Segment words into groups of max_words
    word_groups = [words[i:i + max_words] for i in range(0, len(words), max_words)]
    current_time = cue["start"]

    for group in word_groups:
        group_text = " ".join(group)
        group_duration = total_duration * (len(group) / total_words)
        end_time = min(cue["end"], current_time + group_duration)
        chunks.append({
            "start": round(current_time, 3),
            "end": round(end_time, 3),
            "text": group_text
        })
        current_time = end_time

    return chunks

def to_ass_time(sec: float) -> str:
    """Format seconds into ASS timestamp: H:MM:SS.cs"""
    sec = max(0.0, sec)
    cs = int(round((sec - int(sec)) * 100))
    if cs == 100:
        sec += 1
        cs = 0
    total_sec = int(sec)
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"

def generate_ass_subtitles(
    cues: List[Dict[str, Any]],
    clip_start: float,
    clip_end: float,
    output_path: Path,
    hook_text: str = "",
    width: int = 1080,
    height: int = 1920,
    style_theme: str = "viral_yellow"
) -> Path:
    """
    Generate Advanced SubStation Alpha (.ass) subtitles tailored to the aspect ratio.
    Guarantees word-wrap, safe margins, and stylish typography.
    """
    clip_duration = clip_end - clip_start

    # Themes (ASS colors are in &HAABBGGRR format)
    # Bright Yellow text with thick black outline
    if style_theme == "viral_yellow":
        font_size = 54 if height >= 1920 else (36 if height <= 1080 and width > height else 44)
        primary_color = "&H0000E6FF" # Vibrant Gold/Yellow in BGR
        outline_color = "&H00000000" # Black outline
        outline_width = "4.2"
        shadow_depth = "2.0"
    elif style_theme == "clean_white":
        font_size = 50 if height >= 1920 else 36
        primary_color = "&H00FFFFFF" # Pure White
        outline_color = "&H00000000"
        outline_width = "4.0"
        shadow_depth = "2.0"
    else: # Minimal
        font_size = 46 if height >= 1920 else 34
        primary_color = "&H00F0F0F0"
        outline_color = "&H00101010"
        outline_width = "3.0"
        shadow_depth = "1.5"

    # Margins adjusted for vertical vs horizontal video
    if height > width: # 9:16 portrait
        margin_l = 80
        margin_r = 80
        margin_v_bottom = 260 # Above TikTok/Shorts UI
        margin_v_top = 180
    else: # 16:9 landscape
        margin_l = 100
        margin_r = 100
        margin_v_bottom = 60
        margin_v_top = 50

    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CaptionStyle,Arial,{font_size},{primary_color},&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,0.5,0,1,{outline_width},{shadow_depth},2,{margin_l},{margin_r},{margin_v_bottom},1
Style: HookBadge,Arial,40,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0.5,0,1,3.5,1.5,8,{margin_l},{margin_r},{margin_v_top},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []

    # Optional: Display hook badge on top for the first 5 seconds or whole clip
    if hook_text and height > width:
        clean_hook = re.sub(r'["\\]', '', hook_text).strip()
        if clean_hook:
            # Wrap hook if long
            h_start = to_ass_time(0.0)
            h_end = to_ass_time(min(clip_duration, 6.0)) # Show for initial 6 seconds as a hook
            events.append(f"Dialogue: 1,{h_start},{h_end},HookBadge,,0,0,0,,{{\\b1}}🔥 {clean_hook}{{\\b0}}")

    # Extract and chunk relevant subtitle cues
    for cue in cues:
        # Check if cue overlaps with the clip
        if cue["end"] <= clip_start or cue["start"] >= clip_end:
            continue

        # Split long cue into punchy mobile bursts
        chunks = chunk_cue(cue, max_words=4)

        for chunk in chunks:
            c_start = chunk["start"]
            c_end = chunk["end"]

            # Clamp to clip range
            if c_end <= clip_start or c_start >= clip_end:
                continue

            rel_start = max(0.0, c_start - clip_start)
            rel_end = min(clip_duration, c_end - clip_start)

            if rel_end <= rel_start or (rel_end - rel_start) < 0.2:
                continue

            start_str = to_ass_time(rel_start)
            end_str = to_ass_time(rel_end)
            text = chunk["text"].strip()
            # Clean text for ASS
            text = text.replace("{", "(").replace("}", ")")

            events.append(f"Dialogue: 0,{start_str},{end_str},CaptionStyle,,0,0,0,,{text}")

    full_ass_content = ass_header + "\n".join(events) + "\n"
    output_path.write_text(full_ass_content, encoding="utf-8")
    return output_path
