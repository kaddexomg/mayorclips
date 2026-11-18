import json
import base64
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from app.config import CACHE_DIR
from pulpo.gemini_pool import gemini_pool
from pulpo.tts import generate_speech_with_timestamps


def _compute_hash(task: str, payload: Any) -> str:
    # Avoid hashing huge raw base64 blobs repeatedly if audio_path is given
    safe_payload = dict(payload) if isinstance(payload, dict) else payload
    raw = f"{task}:{json.dumps(safe_payload, sort_keys=True, default=str)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_cache(h: str) -> Any:
    cache_file = CACHE_DIR / f"{h}.json"
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _set_cache(h: str, data: Any):
    cache_file = CACHE_DIR / f"{h}.json"
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


class PulpoRouter:
    """Central AI orchestrator for MayorClips with multimodal audio/vision & 7-key rotation."""

    async def run(self, task: str, payload: Dict[str, Any], use_cache: bool = True) -> Any:
        h = _compute_hash(task, payload)
        if use_cache and task not in ("analyze_audio_window", "detect_facecam"):
            cached = _get_cache(h)
            if cached is not None:
                return cached

        res = None
        if task == "analyze_audio_window":
            res = await self._analyze_audio_window(payload)
        elif task == "detect_facecam":
            res = await self._detect_facecam(payload)
        elif task == "find_moments":
            res = await self._find_moments(payload)
        elif task == "write_titles":
            res = await self._write_titles(payload)
        elif task == "script":
            res = await self._generate_script(payload)
        elif task == "scene_plan":
            res = await self._generate_scene_plan(payload)
        elif task == "tts":
            text = payload.get("text", "")
            voice = payload.get("voice", "es-MX-DaliaNeural")
            res = await generate_speech_with_timestamps(text, voice)
        else:
            raise ValueError(f"Tarea de Pulpo desconocida: {task}")

        if use_cache and res is not None and task not in ("analyze_audio_window", "detect_facecam"):
            _set_cache(h, res)
        return res

    async def _analyze_audio_window(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Listens directly to a real audio chunk (.m4a) via Gemini Multimodal Audio."""
        audio_path = payload["audio_path"]
        window_start_sec = float(payload.get("window_start_sec", 0.0))
        window_dur_sec = float(payload.get("window_dur_sec", 90.0))
        streamer = payload.get("streamer", "Streamer")
        title = payload.get("stream_title", "")
        chat_sample = payload.get("chat_sample", "")

        with open(audio_path, "rb") as f:
            b64_audio = base64.b64encode(f.read()).decode("utf-8")

        ext = Path(audio_path).suffix.lower()
        mime_type = "audio/aac" if ext in (".m4a", ".aac") else "audio/mp3"

        system_instruction = (
            "Eres un productor experto de clips virales (TikTok, Instagram Reels, YouTube Shorts). "
            "Escuchas fragmentos reales de audio de transmisiones en español e identificas los mejores cortes virales. "
            "Responde SIEMPRE en español y estrictamente en formato JSON válido."
        )

        prompt = f"""
Stream: "{title}" — Creador: {streamer}
Este audio dura {window_dur_sec:.0f} segundos (el segundo 0.0 de este audio corresponde al segundo {window_start_sec:.0f} del stream completo).
Mensajes reales del chat en este momento: {chat_sample}

Escucha con atención el audio completo:
1. Evalúa si hay un momento gracioso, polémico, emotivo, grito, remate o discusión interesante digna de clip.
2. Si lo hay, define el corte exacto dentro de este audio (`start_offset_sec` entre 0 y {window_dur_sec:.0f}, y `end_offset_sec` de 15 a 75 segundos después).
3. Transcribe brevemente las frases clave que realmente se escuchan.

Devuelve un JSON dict exacto con:
- "is_viral_worthy": boolean
- "start_offset_sec": float
- "end_offset_sec": float
- "title": string (título llamativo en español de máximo 60 caracteres)
- "hook": string (texto gancho en pantalla para los primeros 2 segundos, en español y mayúsculas cortas)
- "reason": string (explicación breve de qué ocurre exactamente en el audio)
- "virality_score": int (0 a 99; >=80 solo si de verdad hay acción/emoción/chiste claro)
- "event_comment": string (tarjeta de comentario divertida con 1 emoji, ej: '💀 Se calentó la discusión en vivo')
- "tags": list de strings
- "transcript_summary": string (lo que dicen textualmente)
"""
        media_parts = [{"inlineData": {"mimeType": mime_type, "data": b64_audio}}]
        res = await gemini_pool.generate_json(
            prompt, system_instruction, task_name="analyze_audio_window", media_parts=media_parts
        )
        if isinstance(res, list) and res:
            return res[0]
        return res

    async def _detect_facecam(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Inspects a single video frame JPEG to locate the streamer's webcam rectangle accurately."""
        image_path = payload["image_path"]
        with open(image_path, "rb") as f:
            b64_img = base64.b64encode(f.read()).decode("utf-8")

        system_instruction = "Eres un analizador de composición visual de streams 16:9."
        prompt = """
Analiza este fotograma del stream (resolución normalizada de 0.0 a 1.0 en ancho X y alto Y).
1. ¿Hay un recuadro de cámara web (facecam) superpuesto sobre un gameplay/pantalla, o es una toma de cámara completa (ej: podcast/Just Chatting)?
2. Si hay facecam superpuesta, indica sus coordenadas normalizadas (0.0 a 1.0): x, y (esquina superior izquierda), w (ancho), h (alto).
3. Recomienda el mejor layout vertical 9:16:
   - "split_screen": si hay facecam superpuesta sobre contenido/video/juego
   - "centered_face": si toda la pantalla es la cámara hablando
   - "blur_bg": si es un video/pantalla sin cámara o con personas en todo el encuadre

Devuelve un JSON dict:
{
  "has_facecam": boolean,
  "layout_recommended": "split_screen" | "centered_face" | "blur_bg",
  "webcam_box": {"x": float, "y": float, "w": float, "h": float}
}
"""
        media_parts = [{"inlineData": {"mimeType": "image/jpeg", "data": b64_img}}]
        try:
            res = await gemini_pool.generate_json(
                prompt, system_instruction, task_name="detect_facecam", media_parts=media_parts
            )
            if isinstance(res, list) and res:
                return res[0]
            return res
        except Exception:
            return {
                "has_facecam": False,
                "layout_recommended": "blur_bg",
                "webcam_box": {"x": 0.02, "y": 0.02, "w": 0.30, "h": 0.35},
            }

    async def _find_moments(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        transcript_text = payload.get("transcript", "")
        signals = payload.get("signals", {})
        streamer_name = payload.get("streamer", "Streamer")

        system_instruction = (
            "Eres un editor profesional de clips virales en español para TikTok, Instagram Reels y YouTube Shorts. "
            "Responde ÚNICAMENTE con un JSON array válido."
        )
        prompt = f"""
Streamer: {streamer_name}
Señales detectadas:
{json.dumps(signals, ensure_ascii=False, indent=2)}

Transcripción con marcas de tiempo:
{transcript_text[:25000]}

Extrae entre 4 y 12 momentos virales reales (duración de 15 a 85 segundos) con:
- "start_sec": float
- "end_sec": float
- "hook": string
- "title": string
- "reason": string
- "virality_score": int (60-99)
- "event_comment": string
- "tags": list[str]
"""
        result = await gemini_pool.generate_json(prompt, system_instruction, task_name="find_moments")
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "moments" in result:
            return result["moments"]
        return [result]

    async def _write_titles(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        clip_summary = payload.get("summary", "")
        hook = payload.get("hook", "")
        system_instruction = "Eres un estratega de copy viral en español para TikTok, Instagram Reels y Facebook."
        prompt = f"""
Clip: {clip_summary}
Gancho base: {hook}

Genera un JSON dict con:
- "titles": lista de 3 títulos virales en español
- "caption_instagram": descripción para Instagram Reels con 5 hashtags
- "caption_tiktok": descripción concisa para TikTok con hashtags
- "caption_facebook": descripción para Facebook Reels
- "overlay_sticker": texto corto humorístico para tarjeta flotante
"""
        return await gemini_pool.generate_json(prompt, system_instruction, task_name="write_titles")

    async def _generate_script(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        topic = payload.get("topic", "")
        style = payload.get("style", "curiosities")
        system_instruction = (
            "Eres un guionista de videos virales de alta retención en español en formato vertical 9:16. "
            "Duración objetivo: 30 a 50 segundos."
        )
        prompt = f"""
Tema: {topic}
Estilo: {style}

Devuelve JSON dict con:
- "title": string
- "hook": string (primeros 3s hablados)
- "scenes": lista de escenas con {{scene_id, spoken_text, visual_cue, keyword_highlight, estimated_sec}}
"""
        return await gemini_pool.generate_json(prompt, system_instruction, task_name="script")

    async def _generate_scene_plan(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        script = payload.get("script", {})
        system_instruction = "Eres director técnico de Motion Graphics para HyperFrames / FFmpeg."
        prompt = f"""
Guion:
{json.dumps(script, ensure_ascii=False, indent=2)}

Devuelve un JSON array de escenas con:
- "scene_id": int
- "template": "kinetic_text" | "stat_card" | "split_highlight" | "curiosity_reveal"
- "headline": string
- "subtitle": string
- "accent_color": string (ej. "#2BF0C8")
- "animation_type": "slide_up" | "zoom_in" | "glitch_reveal"
- "duration_sec": float
"""
        res = await gemini_pool.generate_json(prompt, system_instruction, task_name="scene_plan")
        if isinstance(res, list):
            return res
        if isinstance(res, dict) and "scenes" in res:
            return res["scenes"]
        return [res]


pulpo = PulpoRouter()
