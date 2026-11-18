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
        window_dur_sec = float(payload.get("window_dur_sec", 120.0))
        streamer = payload.get("streamer", "Streamer")
        title = payload.get("stream_title", "")
        chat_sample = payload.get("chat_sample", "")
        chapter_title = payload.get("chapter_title", "")
        user_context = payload.get("user_context", "")

        with open(audio_path, "rb") as f:
            b64_audio = base64.b64encode(f.read()).decode("utf-8")

        ext = Path(audio_path).suffix.lower()
        mime_type = "audio/aac" if ext in (".m4a", ".aac") else "audio/mp3"

        system_instruction = (
            "Eres un editor profesional de clips cortos en español para redes (TikTok, Instagram Reels, Shorts). "
            "Priorizas comprensión del contexto real: nunca cortas un chiste o debate a mitad sin su planteamiento previo. "
            "Escribes títulos limpios y atractivos, y explicas claramente qué ocurre en el clip para quien no vio el directo. "
            "Responde SIEMPRE en español y estrictamente en formato JSON válido."
        )

        context_lines = [f'Stream: "{title}" — Creador: {streamer}']
        if chapter_title:
            context_lines.append(f"Capítulo / Juego / Sección en este instante: {chapter_title}")
        if user_context:
            context_lines.append(f"Enfoque pedido por el editor: {user_context}")
        context_block = "\n".join(context_lines)

        prompt = f"""
{context_block}
Este audio dura {window_dur_sec:.0f} segundos (el segundo 0.0 corresponde al segundo {window_start_sec:.0f} del stream; los primeros ~20s sirven para entender el contexto previo).
Referencia de chat / radar: {chat_sample}

Escucha el audio real con atención:
1. Localiza el momento con mayor punch, gracia, anécdota o clímax completo (incluyendo el planteamiento previo necesario para que se entienda solo) entre 22 y 65 segundos (`start_offset_sec` y `end_offset_sec`). Si es puro silencio o relleno sin interés, marca `"is_viral_worthy": false`.
2. Redacta un título limpio (<=52 caracteres, sin gritar todo en mayúsculas ni spam de signos, máximo 1 emoji opcional solo si aporta).
3. Redacta un gancho breve para pantalla (`hook`, 3 a 6 palabras que den contexto o intriga real).
4. En `reason`, explica en **2 a 3 frases claras y autosuficientes**: (a) qué estaba pasando o de qué hablaban antes, (b) qué dice o sucede exactamente en el clip, y (c) por qué atrapa al espectador.
5. En `event_comment`, escribe una nota breve de contexto en pantalla (sin corchetes).

Devuelve un JSON dict exacto con:
- "is_viral_worthy": boolean
- "start_offset_sec": float
- "end_offset_sec": float
- "title": string
- "hook": string
- "reason": string
- "virality_score": int (55 a 99)
- "event_comment": string
- "tags": list de strings
- "transcript_summary": string (resumen fiel de lo escuchado)
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

        system_instruction = "Eres un director de fotografía que analiza encuadres de streams 16:9 (podcasts, gameplay tipo GTA 6, reacciones y tutoriales)."
        prompt = """
Analiza este fotograma del video (coordenadas normalizadas 0.0 a 1.0 en X y Y).
Clasifica el tipo de escena:
- "two_person_split": hay 2 personas principales hablando lado a lado (podcast/entrevista/debate de 2 cámaras)
- "multi_panel": hay 3 o más recuadros de personas hablando (mesa de debate/show) y/o pizarra abajo
- "facecam_gameplay": 1 recuadro pequeño de cámara del streamer superpuesto sobre un videojuego/pantalla
- "gaming_action": pantalla completa de videojuego (ej. GTA 6, meme en escena, NPC, accidente o detalle visual clave) sin facecam o donde la acción del juego es lo más importante
- "single_speaker": 1 persona ocupando toda la toma hablando a cámara
- "blur_bg": pantalla completa con gráficas, partido o código donde no conviene recortar

Devuelve un JSON dict exacto:
{
  "scene_type": "two_person_split" | "multi_panel" | "facecam_gameplay" | "gaming_action" | "single_speaker" | "blur_bg",
  "has_facecam": boolean,
  "has_important_bottom_graphic": boolean,
  "layout_recommended": "duo_split" | "speaker_focus" | "split_screen" | "gaming_zoom" | "centered_face" | "blur_bg",
  "webcam_box": {"x": float, "y": float, "w": float, "h": float},
  "roi_box": {"x": float, "y": float, "w": float, "h": float}
}
Notas:
- `roi_box` marca la zona de interés principal dentro del video/gameplay (ej. el personaje, vehículo, texto de meme o suceso gracioso en GTA 6). Si todo el cuadro importa, usa {"x": 0.15, "y": 0.1, "w": 0.7, "h": 0.8}.
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
        user_context = payload.get("user_context", "")

        system_instruction = (
            "Eres un editor profesional de clips en español. Priorizas contexto completo, "
            "explicación clara de qué ocurre y títulos naturales sin abuso de mayúsculas. Responde en JSON array."
        )
        prompt = f"""
Streamer: {streamer_name}
Contexto editorial adicional: {user_context or "Ninguno"}
Señales detectadas:
{json.dumps(signals, ensure_ascii=False, indent=2)}

Transcripción con marcas de tiempo:
{transcript_text[:25000]}

Extrae entre 4 y 10 momentos reales (22 a 75 segundos, incluyendo planteamiento previo completo) con:
- "start_sec": float
- "end_sec": float
- "hook": string (3 a 6 palabras claras de gancho)
- "title": string (título natural <=52 caracteres, máx 1 emoji opcional)
- "reason": string (explicación de 2 a 3 frases claras sobre qué precedió al momento, qué se dice/hace y por qué engancha)
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
        style_notes = {
            "explainer": "Estilo explicativo técnico / motion graphics estilo código y arquitectura: directo, pasos claros, cifras concretas o bloques lógicos.",
            "gaming_lore": "Estilo GTA 6 / lore & memes gaming: narración inmersiva, datos ocultos, detalles curiosos y remate épico.",
            "curiosities": "Estilo curiosidades virales rápidas con datos sorprendentes.",
            "top5": "Formato Top dinámico con ritmo ascendente y datos claros.",
            "history": "Narrativa de historia / misterio con giro final atrapante.",
            "data_charts": "Enfoque en estadísticas, porcentajes y métricas impactantes.",
        }.get(style, "Ritmo ágil con gancho fuerte en los primeros 3 segundos.")

        system_instruction = (
            "Eres un guionista y director creativo de videos cortos verticales en español (28 a 42 segundos, 3 a 4 escenas claras)."
        )
        prompt = f"""
Tema: {topic}
Estilo: {style} ({style_notes})

Devuelve JSON dict exacto con:
- "title": string corto (puede llevar 1 emoji al final si aporta valor)
- "hook": string (primeros 3s hablados de alto impacto)
- "scenes": lista de 3 a 4 escenas con {{scene_id, spoken_text, visual_cue, keyword_highlight, estimated_sec}}
"""
        return await gemini_pool.generate_json(prompt, system_instruction, task_name="script")

    async def _generate_scene_plan(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        script = payload.get("script", {})
        system_instruction = "Eres director técnico de Motion Graphics (estilo Apple Keynote / código moderno / HUD gaming)."
        prompt = f"""
Guion:
{json.dumps(script, ensure_ascii=False, indent=2)}

Devuelve un JSON array de escenas (una por cada escena del guion) con:
- "scene_id": int
- "template": "kinetic_text" | "stat_card" | "split_highlight" | "curiosity_reveal"
- "badge": string corto tipo etiqueta HUD (ej. "PUNTO 01", "DATO CLAVE", "GTA VI // LORE", "CÓDIGO / PIPELINE")
- "headline": string impactante (máximo 7 palabras, puede llevar 1 emoji si aporta)
- "subtitle": string breve (máximo 14 palabras explicativas)
- "stat_value": string corto numérico o métrico opcional (ej. "4.2x", "1080p", "2026", "$2B") o ""
- "stat_label": string corto que acompaña a stat_value (ej. "RENDIMIENTO", "PRECISIÓN") o ""
- "progress_pct": int entre 15 y 98 (barra visual animada en tarjeta o diagrama)
- "bullets": lista de 0 a 3 líneas muy cortas (ideal para bloques de código, pasos o comparación)
- "accent_color": hex color brillante acorde al tema (ej. "#00E5FF", "#38BDF8", "#A855F7", "#F59E0B", "#10B981")
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
