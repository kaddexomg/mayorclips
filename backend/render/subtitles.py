import os
from pathlib import Path
from typing import List, Dict, Any

STYLE_PRESETS = {
    "hormozi": {
        "Fontname": "Impact",
        "Fontsize": "64",
        "PrimaryColour": "&H002BF0C8", # Cyan / brand #2BF0C8 in BGR
        "SecondaryColour": "&H00FFFFFF",
        "OutlineColour": "&H00000000",
        "BackColour": "&H80000000",
        "Bold": "-1",
        "Italic": "0",
        "Outline": "4",
        "Shadow": "2",
        "Alignment": "2", # Bottom-center
        "MarginV": "180"
    },
    "neon": {
        "Fontname": "Arial Black",
        "Fontsize": "58",
        "PrimaryColour": "&H00C8F02B", # Neon Cyan BGR
        "SecondaryColour": "&H0000FFFF",
        "OutlineColour": "&H0014242B", # Abyss dark border
        "BackColour": "&H00000000",
        "Bold": "-1",
        "Italic": "0",
        "Outline": "5",
        "Shadow": "0",
        "Alignment": "2",
        "MarginV": "190"
    },
    "karaoke": {
        "Fontname": "Trebuchet MS",
        "Fontsize": "56",
        "PrimaryColour": "&H0000FFFF", # Yellow BGR
        "SecondaryColour": "&H00FFFFFF",
        "OutlineColour": "&H00000000",
        "BackColour": "&H40000000",
        "Bold": "-1",
        "Italic": "0",
        "Outline": "3",
        "Shadow": "1",
        "Alignment": "2",
        "MarginV": "180"
    },
    "minimal": {
        "Fontname": "Segoe UI",
        "Fontsize": "52",
        "PrimaryColour": "&H00FFFFFF",
        "SecondaryColour": "&H00FFFFFF",
        "OutlineColour": "&H00000000",
        "BackColour": "&H00000000",
        "Bold": "-1",
        "Italic": "0",
        "Outline": "2",
        "Shadow": "1",
        "Alignment": "2",
        "MarginV": "160"
    },
    "mrbeast": {
        "Fontname": "Komika Axis",
        "Fontsize": "66",
        "PrimaryColour": "&H0000D7FF", # Gold / Bright Yellow
        "SecondaryColour": "&H00FFFFFF",
        "OutlineColour": "&H00000000",
        "BackColour": "&H80000000",
        "Bold": "-1",
        "Italic": "0",
        "Outline": "6",
        "Shadow": "3",
        "Alignment": "2",
        "MarginV": "200"
    }
}

def format_ass_time(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    return f"{hrs:d}:{mins:02d}:{secs:02d}.{cs:02d}"

def generate_ass_file(words: List[Dict[str, Any]], output_path: str, style_name: str = "hormozi", title_hook: str = "", event_comment: str = "") -> str:
    """Generates an Advanced SubStation Alpha (.ass) subtitle file with word-level highlight and hook animations."""
    preset = STYLE_PRESETS.get(style_name, STYLE_PRESETS["hormozi"])

    style_line = (
        f"Style: Default,{preset['Fontname']},{preset['Fontsize']},{preset['PrimaryColour']},"
        f"{preset['SecondaryColour']},{preset['OutlineColour']},{preset['BackColour']},"
        f"{preset['Bold']},{preset['Italic']},0,0,100,100,0,0,1,{preset['Outline']},"
        f"{preset['Shadow']},{preset['Alignment']},20,20,{preset['MarginV']},1"
    )

    header = f"""[Script Info]
Title: MayorClips Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style_line}
Style: Hook,Impact,74,&H002BF0C8,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,3,8,30,30,220,1
Style: EventCard,Arial Black,42,&H00E8F6F2,&H00FFFFFF,&H0014242B,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,8,40,40,340,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []

    # 1. Title hook in first 2.5 seconds at top
    if title_hook:
        t_end = min(2.8, words[-1]["end_sec"] if words else 2.8)
        events.append(f"Dialogue: 1,0:00:00.00,{format_ass_time(t_end)},Hook,,0,0,0,,{{\\fad(200,200)}}{title_hook.upper()}")

    # 2. Event comment card if present (e.g. at 3s..8s)
    if event_comment:
        events.append(f"Dialogue: 1,0:00:03.00,0:00:08.50,EventCard,,0,0,0,,{{\\fad(300,300)}}[ {event_comment} ]")

    # 3. Dynamic 2-3 words chunks with highlight
    # Group words into short rhythmic phrases (max 3 words per phrase)
    if words:
        chunk_size = 3
        for i in range(0, len(words), chunk_size):
            chunk = words[i:i + chunk_size]
            c_start = chunk[0]["start_sec"]
            c_end = chunk[-1]["end_sec"]
            phrase_text = " ".join([w.get("word", "") for w in chunk]).upper()
            events.append(f"Dialogue: 0,{format_ass_time(c_start)},{format_ass_time(c_end)},Default,,0,0,0,,{phrase_text}")

    full_content = header + "\n".join(events) + "\n"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_content)

    return output_path
