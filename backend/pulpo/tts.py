import os
import re
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Tuple
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

_FALLBACK_VOICE_ORDER = [
    "es-CO-GonzaloNeural",
    "es-MX-JorgeNeural",
    "es-MX-DaliaNeural",
    "es-ES-AlvaroNeural",
]


def sanitize_tts_text(text: str) -> str:
    """Strips stage tags/markdown and returns speakable text, or '' if no alphanumeric content remains."""
    cleaned = str(text or "")
    cleaned = re.sub(r"\[[^\]]*\]", " ", cleaned)  # [pausa], [ríe], [FX]
    cleaned = re.sub(r"[*_`#~<>]+", " ", cleaned)
    cleaned = re.sub(r"\.{2,}|…", ", ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\r\n-|•·")
    if not re.search(r"[0-9A-Za-zÁÉÍÓÚáéíóúÜüÑñ]", cleaned):
        return ""
    return cleaned


async def _synthesize_edge_tts(text: str, voice: str) -> Tuple[bytes, List[Dict[str, Any]]]:
    communicate = edge_tts.Communicate(text, voice)
    audio_buf = bytearray()
    word_boundaries: List[Dict[str, Any]] = []

    async for chunk in communicate.stream():
        ctype = chunk.get("type")
        if ctype == "audio":
            audio_buf.extend(chunk["data"])
        elif ctype == "WordBoundary":
            start_ms = int(chunk["offset"] / 10000)
            dur_ms = int(chunk["duration"] / 10000)
            word_boundaries.append({
                "word": chunk["text"],
                "start_ms": start_ms,
                "end_ms": start_ms + dur_ms,
                "start_sec": round(start_ms / 1000.0, 3),
                "end_sec": round((start_ms + dur_ms) / 1000.0, 3)
            })
        elif ctype == "SentenceBoundary":
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

    if len(audio_buf) < 256:
        raise ValueError(f"Edge-TTS devolvió audio vacío para voz {voice}")
    return bytes(audio_buf), word_boundaries


async def generate_speech_with_timestamps(
    text: str,
    voice: str = "es-MX-DaliaNeural",
    output_filename: str = None
) -> Dict[str, Any]:
    """Generates audio file and extracts word-level timing boundaries with sanitization, retries, and fallback voices."""
    if not output_filename:
        import uuid
        output_filename = f"tts_{uuid.uuid4().hex[:10]}.mp3"

    audio_path = MEDIA_DIR / output_filename
    sub_path = CACHE_DIR / f"{Path(output_filename).stem}_words.json"

    spoken_text = sanitize_tts_text(text) or "Siguiente escena."
    primary_voice = str(voice or "").strip() or "es-MX-DaliaNeural"

    attempts: List[str] = [primary_voice, primary_voice]
    for fv in _FALLBACK_VOICE_ORDER:
        if fv not in attempts:
            attempts.append(fv)

    audio_bytes: bytes = b""
    word_boundaries: List[Dict[str, Any]] = []
    last_err: Exception | None = None

    for idx, candidate_voice in enumerate(attempts):
        try:
            audio_bytes, word_boundaries = await _synthesize_edge_tts(spoken_text, candidate_voice)
            break
        except Exception as exc:
            last_err = exc
            print(f"[TTS WARN] Intento {idx + 1}/{len(attempts)} falló con {candidate_voice} ({type(exc).__name__}: {exc})")
            if idx < len(attempts) - 1:
                await asyncio.sleep(0.45 * (idx + 1))
    else:
        raise RuntimeError(f"No audio was received después de {len(attempts)} intentos TTS: {last_err}") from last_err

    with open(audio_path, "wb") as f_out:
        f_out.write(audio_bytes)

    if not word_boundaries:
        words = spoken_text.split()
        step = 0.36
        for i, w in enumerate(words):
            st = round(i * step, 3)
            en = round((i + 1) * step, 3)
            word_boundaries.append({
                "word": w,
                "start_ms": int(st * 1000),
                "end_ms": int(en * 1000),
                "start_sec": st,
                "end_sec": en,
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
