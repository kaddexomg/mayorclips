from typing import List, Dict, Any

# Note: ASS colors are in BGR hex (&H00BBGGRR)
STYLE_PRESETS = {
    "hormozi": {
        "Fontname": "Impact",
        "Fontsize": "72",
        "PrimaryColour": "&H00FFFFFF",
        "ActiveColour": "&H0000E5FF", # Bright Gold Yellow (BGR)
        "OutlineColour": "&H00000000",
        "BackColour": "&H80000000",
        "Bold": "-1",
        "Outline": "6",
        "Shadow": "3",
        "MarginV": "440",
    },
    "neon": {
        "Fontname": "Arial Black",
        "Fontsize": "66",
        "PrimaryColour": "&H00F2F6E8", # #E8F6F2
        "ActiveColour": "&H00C8F02B",  # #2BF0C8 Quanty Turquoise (BGR)
        "OutlineColour": "&H00100B06", # #060B10 Abyss border
        "BackColour": "&H00000000",
        "Bold": "-1",
        "Outline": "6",
        "Shadow": "2",
        "MarginV": "440",
    },
    "karaoke": {
        "Fontname": "Segoe UI",
        "Fontsize": "64",
        "PrimaryColour": "&H00FFFFFF",
        "ActiveColour": "&H00C8F02B",
        "OutlineColour": "&H00000000",
        "BackColour": "&H60000000",
        "Bold": "-1",
        "Outline": "5",
        "Shadow": "2",
        "MarginV": "440",
    },
    "minimal": {
        "Fontname": "Segoe UI",
        "Fontsize": "58",
        "PrimaryColour": "&H00E5E7EB",
        "ActiveColour": "&H00FFFFFF",
        "OutlineColour": "&H00000000",
        "BackColour": "&H00000000",
        "Bold": "-1",
        "Outline": "3",
        "Shadow": "2",
        "MarginV": "420",
    },
    "mrbeast": {
        "Fontname": "Impact",
        "Fontsize": "76",
        "PrimaryColour": "&H00FFFFFF",
        "ActiveColour": "&H0000D7FF", # Gold
        "OutlineColour": "&H00000000",
        "BackColour": "&H90000000",
        "Bold": "-1",
        "Outline": "7",
        "Shadow": "4",
        "MarginV": "450",
    },
}


def format_ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 99
    return f"{hrs:d}:{mins:02d}:{secs:02d}.{cs:02d}"


def _esc_ass(txt: str) -> str:
    return txt.replace("{", "(").replace("}", ")").replace("\n", " ")


def generate_ass_file(
    words: List[Dict[str, Any]],
    output_path: str,
    style_name: str = "hormozi",
    title_hook: str = "",
    event_comment: str = "",
    margin_v_override: int = None,
) -> str:
    """Generates active-word highlighted ASS subtitles centered cleanly in the 9:16 safe zone."""
    preset = STYLE_PRESETS.get(style_name, STYLE_PRESETS["hormozi"])
    mv = str(margin_v_override) if margin_v_override is not None else preset["MarginV"]

    style_line = (
        f"Style: Default,{preset['Fontname']},{preset['Fontsize']},{preset['PrimaryColour']},"
        f"{preset['ActiveColour']},{preset['OutlineColour']},{preset['BackColour']},"
        f"{preset['Bold']},0,0,0,100,100,0,0,1,{preset['Outline']},"
        f"{preset['Shadow']},2,50,50,{mv},1"
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

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    active_bgr = preset["ActiveColour"]
    base_bgr = preset["PrimaryColour"]

    if words:
        # Group into natural 2-3 word rhythmic chunks
        chunks = []
        cur = []
        cur_chars = 0
        for w in words:
            wt = (w.get("word") or "").strip()
            if not wt:
                continue
            if cur and (len(cur) >= 3 or cur_chars + len(wt) > 20):
                chunks.append(cur)
                cur = []
                cur_chars = 0
            cur.append(w)
            cur_chars += len(wt) + 1
        if cur:
            chunks.append(cur)

        # Emit word-by-word highlight inside each chunk
        for c_idx, chunk in enumerate(chunks):
            for w_idx, active_w in enumerate(chunk):
                w_start = float(active_w["start_sec"])
                # Extend smoothly to next word or next chunk to prevent flickering gaps
                if w_idx + 1 < len(chunk):
                    w_end = float(chunk[w_idx + 1]["start_sec"])
                elif c_idx + 1 < len(chunks):
                    next_s = float(chunks[c_idx + 1][0]["start_sec"])
                    w_end = min(float(active_w["end_sec"]) + 0.25, next_s)
                else:
                    w_end = float(active_w["end_sec"]) + 0.15

                if w_end <= w_start:
                    w_end = w_start + 0.12

                styled_tokens = []
                for j, item in enumerate(chunk):
                    txt = _esc_ass(item["word"].upper())
                    if j == w_idx:
                        styled_tokens.append(f"{{\\c{active_bgr}&\\fscx108\\fscy108}}{txt}{{\\c{base_bgr}&\\fscx100\\fscy100}}")
                    else:
                        styled_tokens.append(txt)

                line_str = " ".join(styled_tokens)
                events.append(f"Dialogue: 0,{format_ass_time(w_start)},{format_ass_time(w_end)},Default,,0,0,0,,{line_str}")

    full_content = header + "\n".join(events) + "\n"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_content)

    return output_path
