import json
import base64
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from app.config import CACHE_DIR
from pulpo.gemini_pool import gemini_pool
from pulpo.tts import generate_speech_with_timestamps


def _compute_hash(task: str, payload: Any) -> str:
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
        if use_cache and task not in ("analyze_audio_window", "detect_facecam", "polish_transcript"):
            cached = _get_cache(h)
            if cached is not None:
                return cached

        res = None
        if task == "analyze_audio_window":
            res = await self._analyze_audio_window(payload)
        elif task == "detect_facecam":
            res = await self._detect_facecam(payload)
        elif task == "polish_transcript":
            res = await self._polish_transcript(payload)
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

        if use_cache and res is not None and task not in ("analyze_audio_window", "detect_facecam", "polish_transcript"):
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
            "Eres un editor profesional de clips cortos en español para redes (TikTok, Instagram Reels, Shorts). "
            "Escribes títulos limpios, naturales y atractivos, sin gritar todo en mayúsculas ni usar clickbait sucio. "
            "Solo usas 1 emoji ocasionalmente si aporta emoción natural; muchos títulos funcionan mejor sin emoji. "
            "Responde SIEMPRE en español y estrictamente en formato JSON válido."
        )

        prompt = f"""
Stream: "{title}" — Creador: {streamer}
Este fragmento dura {window_dur_sec:.0f} segundos (el segundo 0.0 del audio corresponde al segundo {window_start_sec:.0f} del stream completo).
Mensajes del chat en este tramo: {chat_sample}

Escucha el audio real con atención:
1. Identifica el momento de mayor interés o gracia y define el corte exacto en una pausa o inicio claro de frase (`start_offset_sec` y `end_offset_sec`, duración entre 20 y 65 segundos).
2. Redacta un título editorial limpio (sin todo en mayúsculas ni signos repetidos como `!!!`, y con máximo 1 emoji SOLO si realmente encaja; déjalo sin emoji si se lee más elegante).
3. Redacta un gancho corto de pantalla (`hook`, máximo 5 palabras claras).
4. En `reason`, explica en 2 frases claras y con sentido **quién habla, qué está pasando y por qué vale la pena el clip** para alguien que no vio el directo.
5. En `event_comment`, escribe un apunte breve y natural de contexto (sin corchetes ni barras raras).

Devuelve un JSON dict exacto con:
- "is_viral_worthy": boolean
- "start_offset_sec": float
- "end_offset_sec": float
- "title": string (máximo 52 caracteres, ortografía natural en español)
- "hook": string (3 a 5 palabras claras para el encabezado en pantalla)
- "reason": string (explicación coherente y completa del contexto del clip)
- "virality_score": int (60 a 99)
- "event_comment": string (comentario corto de contexto sin corchetes, opcionalmente 1 emoji si aporta)
- "tags": list de strings
- "transcript_summary": string (resumen fiel de lo que se escucha)
"""
        media_parts = [{"inlineData": {"mimeType": mime_type, "data": b64_audio}}]
        res = await gemini_pool.generate_json(
            prompt, system_instruction, task_name="analyze_audio_window", media_parts=media_parts
        )
        if isinstance(res, list) and res:
            return res[0]
        return res

    async def _polish_transcript(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Fixes proper nouns and LATAM/gaming slang in Whisper word tokens while preserving exact timestamps."""
        words = payload.get("words", [])
        context_hint = payload.get("context", "")
        if not words:
            return {"replacements": {}}

        indexed = [{"i": idx, "w": w["word"]} for idx, w in enumerate(words[:180])]
        system_instruction = (
            "Eres corrector ortográfico de subtítulos en español rioplatense/latinoamericano. "
            "Corrige únicamente palabras mal transcritas fonéticamente (nombres propios, jerga de fútbol/streaming, palabras repetidas sin sentido). "
            "No inventes frases nuevas ni cambies los índices."
        )
        prompt = f"""
Contexto del stream: {context_hint}
Palabras detectadas con índice:
{json.dumps(indexed, ensure_ascii=False)}

Devuelve un JSON dict con la clave "replacements", donde cada entrada sea el índice en string y la palabra corregida:
Ejemplo: {{"14": "estadísticas", "15": "Luzu", "28": "Davoo"}}
Si una palabra ya está bien escrita, NO la incluyas.
"""
        try:
            res = await gemini_pool.generate_json(prompt, system_instruction, task_name="polish_transcript")
            return res if isinstance(res, dict) else {"replacements": {}}
        except Exception:
            return {"replacements": {}}

    async def _detect_facecam(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Inspects a single video frame JPEG to classify scene layout and locate facecam if present."""
        image_path = payload["image_path"]
        with open(image_path, "rb") as f:
            b64_img = base64.b64encode(f.read()).decode("utf-8")

        system_instruction = "Eres un director de fotografía que analiza encuadres de streams 16:9."
        prompt = """
Analiza este fotograma del video (coordenadas normalizadas 0.0 a 1.0 en X y Y).
Clasifica el tipo de escena:
- "two_person_split": hay 2 personas principales hablando lado a lado (podcast/entrevista/debate de 2 cámaras)
- "multi_panel": hay 3 o más recuadros de personas hablando (mesa de debate/show) y/o pizarra abajo
- "facecam_gameplay": 1 recuadro pequeño de cámara del streamer superpuesto sobre un videojuego/pantalla
- "single_speaker": 1 persona ocupando toda la toma hablando a cámara
- "blur_bg": pantalla completa con gráficas, partido o texto donde no conviene recortar

Devuelve un JSON dict exacto:
{
  "scene_type": "two_person_split" | "multi_panel" | "facecam_gameplay" | "single_speaker" | "blur_bg",
  "has_facecam": boolean,
  "has_important_bottom_graphic": boolean,
  "layout_recommended": "duo_split" | "speaker_focus" | "split_screen" | "centered_face" | "blur_bg",
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
                "scene_type": "blur_bg",
                "has_facecam": False,
                "has_important_bottom_graphic": False,
                "layout_recommended": "blur_bg",
                "webcam_box": {"x": 0.02, "y": 0.02, "w": 0.30, "h": 0.35},
            }

    async def _find_moments(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        transcript_text = payload.get("transcript", "")
        signals = payload.get("signals", {})
        streamer_name = payload.get("streamer", "Streamer")

        system_instruction = (
            "Eres un editor profesional de clips en español. Títulos naturales sin exceso de mayúsculas, "
            "explicación clara del contexto y emojis solo de vez en cuando cuando sumen. Responde en JSON array."
        )
        prompt = f"""
Streamer: {streamer_name}
Señales detectadas:
{json.dumps(signals, ensure_ascii=False, indent=2)}

Transcripción con marcas de tiempo:
{transcript_text[:25000]}

Extrae entre 4 y 10 momentos reales (18 a 75 segundos) con:
- "start_sec": float
- "end_sec": float
- "hook": string (3 a 5 palabras claras)
- "title": string (título natural <=52 caracteres, máx 1 emoji opcional)
- "reason": string (explicación de 2 frases claras de lo que ocurre)
- "virality_score": int (60-99)
- "event_comment": string (nota breve sin corchetes)
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
        system_instruction = "Eres estratega editorial en español. Redactas copys limpios, humanos y atractivos, usando emojis con moderación."
        prompt = f"""
Clip: {clip_summary}
Gancho base: {hook}

Genera un JSON dict con:
- "titles": lista de 3 títulos naturales (sin abuso de mayúsculas; máximo 1 emoji opcional en uno o dos de ellos)
- "caption_instagram": descripción natural para Instagram Reels con 4–5 hashtags relevantes
- "caption_tiktok": descripción ágil para TikTok con hashtags
- "caption_facebook": descripción para Facebook Reels
- "overlay_sticker": texto corto de contexto sin corchetes
"""
        return await gemini_pool.generate_json(prompt, system_instruction, task_name="write_titles")

    async def _generate_script(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        topic = payload.get("topic", "")
        style = payload.get("style", "curiosities")
        system_instruction = (
            "Eres un guionista de videos cortos en español con ritmo ágil (30 a 50 segundos)."
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
        system_instruction = "Eres director técnico de Motion Graphics."
        prompt = f"""
Guion:
{json.dumps(script, ensure_ascii=False, indent=2)}

Devuelve un JSON array de escenas con:
- "scene_id": int
- "template": "kinetic_text" | "stat_card" | "split_highlight" | "curiosity_reveal"
- "headline": string
- "subtitle": string
- "accent_color": string
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
