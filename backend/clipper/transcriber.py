import subprocess
from typing import List, Dict, Any, Optional
import numpy as np
from app.config import FFMPEG_PATH
from pulpo import pulpo

_whisper_model = None


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        # base int8 gives much stronger Spanish accuracy than tiny while staying ~200MB RAM
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=4)
    return _whisper_model


def preload_whisper_model():
    """Preloads Whisper model into RAM at startup to eliminate first-render load delay."""
    try:
        get_whisper_model()
        print("[WHISPER] Modelo 'base' (int8) precargado en memoria.")
    except Exception as e:
        print(f"[WHISPER] Warning en precarga: {e}")


def transcribe_clip_words(media_path: str, language: Optional[str] = "es") -> List[Dict[str, Any]]:
    """Extracts normalized audio via FFmpeg and transcribes exact word-level timestamps."""
    cmd = [
        FFMPEG_PATH,
        "-hide_banner",
        "-loglevel", "error",
        "-i", str(media_path),
        "-af", "loudnorm",
        "-ar", "16000",
        "-ac", "1",
        "-f", "f32le",
        "-",
    ]
    raw = subprocess.check_output(cmd, timeout=90)
    if not raw:
        return []

    audio = np.frombuffer(raw, dtype=np.float32)
    if len(audio) < 1600:
        return []

    model = get_whisper_model()
    segs, _ = model.transcribe(
        audio,
        language=language,
        word_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=False,
        beam_size=1,
    )

    words: List[Dict[str, Any]] = []
    for seg in segs:
        if seg.words:
            for w in seg.words:
                txt = w.word.strip()
                if not txt:
                    continue
                # Collapse stutter/hallucination repeats (>2 identical consecutive words)
                if len(words) >= 2 and words[-1]["word"].lower() == txt.lower() and words[-2]["word"].lower() == txt.lower():
                    continue
                words.append({
                    "word": txt,
                    "start_sec": round(float(w.start), 3),
                    "end_sec": round(float(w.end), 3),
                })
        else:
            txt = seg.text.strip()
            if txt:
                tokens = txt.split()
                dur = max(0.2, float(seg.end - seg.start)) / len(tokens)
                for idx, tok in enumerate(tokens):
                    ws = float(seg.start) + idx * dur
                    words.append({
                        "word": tok,
                        "start_sec": round(ws, 3),
                        "end_sec": round(ws + dur, 3),
                    })
    return words


async def polish_words_with_pulpo(words: List[Dict[str, Any]], context: str = "") -> List[Dict[str, Any]]:
    """Polishes misheard slang/names via Gemini while strictly keeping Whisper timestamps."""
    if not words:
        return words
    try:
        res = await pulpo.run("polish_transcript", {"words": words, "context": context}, use_cache=False)
        reps = res.get("replacements", {}) if isinstance(res, dict) else {}
        for idx_str, corrected in reps.items():
            try:
                idx = int(idx_str)
                if 0 <= idx < len(words) and isinstance(corrected, str) and corrected.strip():
                    words[idx]["word"] = corrected.strip()
            except Exception:
                continue
    except Exception as e:
        print(f"[TRANSCRIBER] Polish skipped: {e}")
    return words
