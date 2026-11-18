import subprocess
import json
import re
from pathlib import Path
from typing import List, Dict, Any
from app.config import FFMPEG_PATH

def analyze_audio_peaks(audio_path: str, interval_sec: float = 2.0) -> List[Dict[str, Any]]:
    """Analyzes volume and energy spikes via FFmpeg ebur128/astats filter."""
    if not Path(audio_path).exists():
        return []

    # Fast ebur128 audio filter pass
    cmd = [
        FFMPEG_PATH,
        "-hide_banner",
        "-nostats",
        "-i", audio_path,
        "-af", f"ebur128=interval={interval_sec}",
        "-f", "null",
        "-"
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
        output = proc.stderr

        peaks = []
        # Parse lines like: [Parsed_ebur128_0 @ ...] t: 14.000000  TARGET:-23 LUFS    M: -18.2 S: -19.4 ...
        pattern = re.compile(r't:\s*([\d\.]+)\s+.*?M:\s*([-\d\.]+)')
        for match in pattern.finditer(output):
            t_sec = float(match.group(1))
            lufs = float(match.group(2))
            # Louder sounds have higher LUFS (e.g. -12 is louder than -28)
            # Normalize -70..-5 LUFS to 0..100 score
            score = max(0, min(100, int((lufs + 60.0) * 2.0)))
            if score > 60: # Noticeable spike
                peaks.append({
                    "time_sec": round(t_sec, 2),
                    "loudness_lufs": lufs,
                    "intensity": score
                })
        return peaks
    except Exception as e:
        print(f"[SIGNALS ERROR] Audio peak analysis failed: {e}")
        return []

def extract_chat_reactions(chat_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detects message bursts and viral emote spikes (KEKW, LUL, JAJA, etc.) in chat."""
    if not chat_entries:
        return []

    # Emotes indicating high engagement
    VIRAL_EMOTES = {
        "kekw", "lul", "omegalul", "jajaja", "jaja", "lol", "pog", "poggers",
        "clip it", "clipealo", "noooo", "wtffff", "omg", "f", "skull", "💀"
    }

    # Bucket messages by 5-second intervals
    buckets: Dict[int, Dict[str, Any]] = {}
    for entry in chat_entries:
        t = entry.get("time_sec", 0)
        bucket_idx = int(t // 5) * 5
        if bucket_idx not in buckets:
            buckets[bucket_idx] = {"time_sec": bucket_idx, "count": 0, "viral_count": 0}
        buckets[bucket_idx]["count"] += 1
        msg = entry.get("message", "").lower()
        if any(emote in msg for emote in VIRAL_EMOTES):
            buckets[bucket_idx]["viral_count"] += 1

    spikes = []
    for b_time, b in sorted(buckets.items()):
        if b["count"] >= 5 or b["viral_count"] >= 2:
            spikes.append({
                "time_sec": b["time_sec"],
                "message_rate": b["count"],
                "viral_rate": b["viral_count"],
                "intensity": min(100, b["count"] * 10 + b["viral_count"] * 25)
            })
    return spikes
