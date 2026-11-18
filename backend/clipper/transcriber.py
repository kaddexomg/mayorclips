import subprocess
from typing import List, Dict, Any, Optional
import numpy as np
from app.config import FFMPEG_PATH

_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        # tiny int8 uses ~147 MB RAM total and transcribes 60s of speech in ~3s on Ryzen 5 CPU
        _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
    return _whisper_model


def transcribe_clip_words(media_path: str, language: Optional[str] = "es") -> List[Dict[str, Any]]:
    """Extracts exact word-level timestamps from any audio or video slice using local faster-whisper."""
    cmd = [
        FFMPEG_PATH,
        "-hide_banner",
        "-loglevel", "error",
        "-i", str(media_path),
        "-ar", "16000",
        "-ac", "1",
        "-f", "f32le",
        "-",
    ]
    raw = subprocess.check_output(cmd, timeout=60)
    if not raw:
        return []

    audio = np.frombuffer(raw, dtype=np.float32)
    if len(audio) < 1600:
        return []

    model = _get_whisper_model()
    segs, _ = model.transcribe(audio, language=language, word_timestamps=True, vad_filter=False, beam_size=1)

    words: List[Dict[str, Any]] = []
    for seg in segs:
        if seg.words:
            for w in seg.words:
                txt = w.word.strip()
                if txt:
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
