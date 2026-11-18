import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List
import edge_tts
from app.config import MEDIA_DIR, CACHE_DIR

VOICES = {
    "es-MX-DaliaNeural": "Dalia (México - Femenina, Dinámica)",
    "es-MX-JorgeNeural": "Jorge (México - Masculino, Profundo)",
    "es-ES-AlvaroNeural": "Álvaro (España - Masculino, Enérgico)",
    "es-ES-ElviraNeural": "Elvira (España - Femenina, Narradora)",
    "es-CO-GonzaloNeural": "Gonzalo (Colombia - Masculino, Neutro)",
    "es-AR-TomasNeural": "Tomás (Argentina - Masculino, Moderno)"
}

async def generate_speech_with_timestamps(
    text: str,
    voice: str = "es-MX-DaliaNeural",
    output_filename: str = None
) -> Dict[str, Any]:
    """Generates audio file and extracts word-level timing boundaries for subtitle synchronization."""
    if not output_filename:
        import uuid
        output_filename = f"tts_{uuid.uuid4().hex[:10]}.mp3"

    audio_path = MEDIA_DIR / output_filename
    sub_path = CACHE_DIR / f"{Path(output_filename).stem}_words.json"

    communicate = edge_tts.Communicate(text, voice)
    word_boundaries: List[Dict[str, Any]] = []

    # Edge TTS communicate stream yields chunks of bytes and word boundaries
    with open(audio_path, "wb") as f_out:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f_out.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start_ms = int(chunk["offset"] / 10000)
                dur_ms = int(chunk["duration"] / 10000)
                word_boundaries.append({
                    "word": chunk["text"],
                    "start_ms": start_ms,
                    "end_ms": start_ms + dur_ms,
                    "start_sec": round(start_ms / 1000.0, 3),
                    "end_sec": round((start_ms + dur_ms) / 1000.0, 3)
                })
            elif chunk["type"] == "SentenceBoundary":
                # Divide sentence into proportional word boundaries
                s_start_ms = int(chunk["offset"] / 10000)
                s_dur_ms = int(chunk["duration"] / 10000)
                words = chunk["text"].strip().split()
                if words:
                    w_dur = s_dur_ms / len(words)
                    for i, w in enumerate(words):
                        w_start = int(s_start_ms + i * w_dur)
                        w_end = int(w_start + w_dur)
                        word_boundaries.append({
                            "word": w,
                            "start_ms": w_start,
                            "end_ms": w_end,
                            "start_sec": round(w_start / 1000.0, 3),
                            "end_sec": round(w_end / 1000.0, 3)
                        })

    with open(sub_path, "w", encoding="utf-8") as f_sub:
        json.dump(word_boundaries, f_sub, ensure_ascii=False, indent=2)

    return {
        "audio_path": str(audio_path),
        "words_path": str(sub_path),
        "word_count": len(word_boundaries),
        "word_boundaries": word_boundaries,
        "duration_sec": word_boundaries[-1]["end_sec"] if word_boundaries else 0.0
    }
