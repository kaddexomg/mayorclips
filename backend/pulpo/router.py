import json
import base64
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import CACHE_DIR
from pulpo.gemini_pool import gemini_pool
from pulpo.tts import generate_speech_with_timestamps

_UNCACHED_TASKS = ("analyze_audio_window", "detect_facecam", "analyze_clip_beats", "polish_transcript")
_DEFAULT_WEBCAM_BOX: Dict[str, float] = {"x": 0.02, "y": 0.02, "w": 0.30, "h": 0.35}
_DEFAULT_ROI_BOX: Dict[str, float] = {"x": 0.15, "y": 0.10, "w": 0.70, "h": 0.80}

_VISION_SCENE_SPEC = """Clasifica el tipo de escena (coordenadas normalizadas 0.0 a 1.0 en X y Y):
- "two_person_split": hay 2 personas principales hablando lado a lado (podcast/entrevista/debate de 2 cámaras)
- "multi_panel": hay 3 o más recuadros de personas hablando (mesa de debate/show) y/o pizarra abajo
- "facecam_gameplay": 1 recuadro pequeño de cámara del streamer superpuesto sobre un videojuego/pantalla
- "gaming_action": pantalla completa de videojuego (ej. GTA 6, meme en escena, NPC, accidente o detalle visual clave) sin facecam o donde la acción del juego es lo más importante
- "single_speaker": 1 persona ocupando toda la toma hablando a cámara
- "blur_bg": pantalla completa con gráficas, partido o código donde no conviene recortar"""

_EDITORIAL_CLIP_CRITERIA = """Criterios editoriales (QUÉ CLIPEAR en cualquier streamer del mundo del stream — AuronPlay, ElRubius, IlloJuan, RDjavi, Davoo, etc.):
- Prioriza siempre: mejores momentos de los streams, reacciones sorprendentes, momentos graciosos y situaciones inesperadas.
- En videojuegos y GTA: carros, persecuciones, accidentes, troleos y CUALQUIER conversación o comentario viral relacionado con GTA 6 (si alguien habla de GTA 6 -> prioridad máxima, se clipea).
- Elige fragmentos que despierten intriga y generen ganas reales de ver sus directos completos; descarta relleno o silencios largos."""


def _safe_float(val: Any, default: float) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _encode_jpeg_parts(paths: Any) -> List[Dict[str, Any]]:
    """Encodes existing image files into Gemini inlineData parts."""
    if not paths:
        return []
    path_list = [paths] if isinstance(paths, (str, Path)) else list(paths)
    parts: List[Dict[str, Any]] = []
    for raw_path in path_list:
        if not raw_path:
            continue
        p = Path(raw_path)
        if not p.exists() or not p.is_file():
            continue
        try:
            data = p.read_bytes()
            if not data:
                continue
            mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
            parts.append({"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode("utf-8")}})
        except OSError:
            continue
    return parts


def _clamp_norm_box(box: Any, default: Dict[str, float]) -> Dict[str, float]:
    b = box if isinstance(box, dict) else default
    x = max(0.0, min(0.95, _safe_float(b.get("x"), default["x"])))
    y = max(0.0, min(0.95, _safe_float(b.get("y"), default["y"])))
    w = max(0.05, min(1.0 - x, _safe_float(b.get("w"), default["w"])))
    h = max(0.05, min(1.0 - y, _safe_float(b.get("h"), default["h"])))
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


def _sanitize_vision_dict(raw: Any) -> Dict[str, Any]:
    item = raw[0] if isinstance(raw, list) and raw else raw
    data = item if isinstance(item, dict) else {}
    roi_box = _clamp_norm_box(data.get("roi_box"), _DEFAULT_ROI_BOX)
    webcam_box = _clamp_norm_box(data.get("webcam_box"), _DEFAULT_WEBCAM_BOX)
    return {
        "scene_type": str(data.get("scene_type") or "blur_bg"),
        "has_facecam": bool(data.get("has_facecam", False)),
        "has_important_bottom_graphic": bool(data.get("has_important_bottom_graphic", False)),
        "layout_recommended": str(data.get("layout_recommended") or "blur_bg"),
        "webcam_box": webcam_box,
        "roi_box": roi_box,
    }


def _build_climax_beat(raw_beat: Any, default_at: float, default_box: Dict[str, float]) -> Dict[str, Any]:
    beat = raw_beat if isinstance(raw_beat, dict) else {}
    return {
        "at_sec": round(max(0.0, _safe_float(beat.get("at_sec"), default_at)), 2),
        "duration_sec": round(max(3.5, min(6.0, _safe_float(beat.get("duration_sec"), 4.5))), 2),
        "focus_box": _clamp_norm_box(beat.get("focus_box"), default_box),
        "zoom_factor": round(max(1.15, min(1.45, _safe_float(beat.get("zoom_factor"), 1.28))), 2),
        "label": str(beat.get("label") or "Momento clave").strip()[:60],
    }


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
        if use_cache and task not in _UNCACHED_TASKS:
            cached = _get_cache(h)
            if cached is not None:
                return cached

        res = None
        if task == "analyze_audio_window":
            res = await self._analyze_audio_window(payload)
        elif task == "detect_facecam":
            res = await self._detect_facecam(payload)
        elif task == "analyze_clip_beats":
            res = await self._analyze_clip_beats(payload)
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

        if use_cache and res is not None and task not in _UNCACHED_TASKS:
            _set_cache(h, res)
        return res

    async def _analyze_audio_window(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Listens to an audio chunk (.m4a) plus optional keyframes via Gemini Multimodal."""
        audio_path = payload["audio_path"]
        window_start_sec = float(payload.get("window_start_sec", 0.0))
        window_dur_sec = float(payload.get("window_dur_sec", 120.0))
        streamer = payload.get("streamer", "Streamer")
        title = payload.get("stream_title", "")
        chat_sample = payload.get("chat_sample", "")
        chapter_title = payload.get("chapter_title", "")
        user_context = payload.get("user_context", "")
        frame_paths = payload.get("frame_paths") or []
        frame_times = payload.get("frame_times") or []

        with open(audio_path, "rb") as f:
            b64_audio = base64.b64encode(f.read()).decode("utf-8")

        ext = Path(audio_path).suffix.lower()
        mime_type = "audio/aac" if ext in (".m4a", ".aac") else "audio/mp3"
        image_parts = _encode_jpeg_parts(frame_paths)

        system_instruction = (
            "Eres un editor profesional de clips cortos en español para redes (TikTok, Instagram Reels, Shorts). "
            "Priorizas comprensión del contexto real: nunca cortas un chiste o debate a mitad sin su planteamiento previo. "
            "Combinas audio, imagen y reacciones del chat para detectar el momento visual o verbal exacto del clímax. "
            "Responde SIEMPRE en español y estrictamente en formato JSON válido."
        )

        context_lines = [f'Stream: "{title}" — Creador: {streamer}']
        if chapter_title:
            context_lines.append(f"Capítulo / Juego / Sección en este instante: {chapter_title}")
        if user_context:
            context_lines.append(f"Enfoque pedido por el editor: {user_context}")
        context_block = "\n".join(context_lines)

        visual_note = ""
        if image_parts:
            if frame_times:
                times_str = ", ".join(f"{_safe_float(t, 0.0):.1f}s" for t in frame_times[:len(image_parts)])
                visual_note = f"\nSe adjuntan {len(image_parts)} fotogramas clave dentro de esta ventana (en {times_str})."
            else:
                visual_note = f"\nSe adjuntan {len(image_parts)} fotogramas clave distribuidos en esta ventana."
            visual_note += (
                " Combina lo que SE VE en los fotogramas (gameplay, accidentes, memes en pantalla, gestos) "
                "+ lo que SE ESCUCHA en el audio + las reacciones del chat."
            )

        prompt = f"""
{context_block}
Este audio dura {window_dur_sec:.0f} segundos (el segundo 0.0 corresponde al segundo {window_start_sec:.0f} del stream; los primeros ~20s sirven para entender el contexto previo).
Referencia de chat / radar: {chat_sample}{visual_note}

{_EDITORIAL_CLIP_CRITERIA}

Analiza con atención lo que SE VE en los fotogramas (si hay imágenes) + lo que SE ESCUCHA en el audio + el chat:
1. Localiza el momento con mayor punch, evento visual gracioso/dramático, remate o clímax completo (incluyendo el planteamiento previo necesario para que se entienda solo) entre 22 y 65 segundos (`start_offset_sec` y `end_offset_sec`), centrado justo alrededor del suceso visual o remate principal. Si es puro silencio o relleno sin interés, marca `"is_viral_worthy": false`.
2. Indica `"climax_offset_sec"`: segundo exacto dentro de esta ventana (entre `start_offset_sec` y `end_offset_sec`) donde ocurre el pico, choque, sorpresa o remate principal.
3. Redacta un título limpio (<=52 caracteres, sin gritar todo en mayúsculas ni spam de signos, máximo 1 emoji opcional solo si aporta).
4. Redacta un gancho breve para pantalla (`hook`, 3 a 6 palabras que den contexto o intriga real).
5. En `meme_caption`, escribe opcionalmente un remate/reacción breve estilo meme (2 a 5 palabras) si el momento es gracioso o absurdo (si no aplica, deja `""`).
6. En `reason`, explica en **2 a 3 frases claras y autosuficientes**: (a) qué estaba pasando o de qué hablaban antes, (b) qué se ve o sucede exactamente en el clip, y (c) por qué atrapa al espectador.
7. En `event_comment`, escribe una nota breve de contexto en pantalla (sin corchetes).

Devuelve un JSON dict exacto con:
- "is_viral_worthy": boolean
- "start_offset_sec": float
- "end_offset_sec": float
- "climax_offset_sec": float
- "title": string
- "hook": string
- "meme_caption": string
- "reason": string
- "virality_score": int (55 a 99)
- "event_comment": string
- "tags": list de strings
- "transcript_summary": string (resumen fiel de lo escuchado y visto)
"""
        media_parts = image_parts + [{"inlineData": {"mimeType": mime_type, "data": b64_audio}}]
        res = await gemini_pool.generate_json(
            prompt, system_instruction, task_name="analyze_audio_window", media_parts=media_parts
        )
        item = res[0] if isinstance(res, list) and res else res
        if isinstance(item, dict):
            s_off = max(0.0, _safe_float(item.get("start_offset_sec"), 12.0))
            e_off = max(s_off + 1.0, _safe_float(item.get("end_offset_sec"), s_off + 35.0))
            raw_climax = item.get("climax_offset_sec")
            climax_off = _safe_float(raw_climax, (s_off + e_off) * 0.5) if raw_climax is not None else (s_off + e_off) * 0.5
            item["climax_offset_sec"] = round(max(s_off, min(e_off, climax_off)), 2)
            item["meme_caption"] = str(item.get("meme_caption") or "").strip()
        return item

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
        media_parts = _encode_jpeg_parts(payload.get("image_path"))
        if not media_parts:
            return _sanitize_vision_dict({})

        system_instruction = "Eres un director de fotografía que analiza encuadres de streams 16:9 (podcasts, gameplay tipo GTA 6, reacciones y tutoriales)."
        prompt = f"""
Analiza este fotograma del video.
{_VISION_SCENE_SPEC}

Devuelve un JSON dict exacto:
{{
  "scene_type": "two_person_split" | "multi_panel" | "facecam_gameplay" | "gaming_action" | "single_speaker" | "blur_bg",
  "has_facecam": boolean,
  "has_important_bottom_graphic": boolean,
  "layout_recommended": "duo_split" | "speaker_focus" | "split_screen" | "gaming_zoom" | "centered_face" | "blur_bg",
  "webcam_box": {{"x": float, "y": float, "w": float, "h": float}},
  "roi_box": {{"x": float, "y": float, "w": float, "h": float}}
}}
Notas:
- `roi_box` marca la zona de interés principal dentro del video/gameplay (ej. el personaje, vehículo, texto de meme o suceso gracioso en GTA 6). Si todo el cuadro importa, usa {{"x": 0.15, "y": 0.1, "w": 0.7, "h": 0.8}}.
"""
        try:
            res = await gemini_pool.generate_json(
                prompt, system_instruction, task_name="detect_facecam", media_parts=media_parts
            )
            return _sanitize_vision_dict(res)
        except Exception:
            return _sanitize_vision_dict({})

    async def _analyze_clip_beats(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Inspects 3 keyframes of a clip slice to locate layout, facecam, ROI and visual climax beat."""
        image_paths = payload.get("image_paths") or payload.get("image_path") or []
        frame_times = payload.get("frame_times") or []
        clip_context = str(payload.get("clip_context") or "").strip()
        default_at = (
            _safe_float(frame_times[len(frame_times) // 2], 5.0)
            if frame_times
            else _safe_float(payload.get("duration_sec"), 30.0) * 0.5
        )

        media_parts = _encode_jpeg_parts(image_paths)
        if not media_parts:
            fallback = _sanitize_vision_dict({})
            fallback["climax_beat"] = _build_climax_beat({}, default_at, fallback["roi_box"])
            return fallback

        if frame_times:
            labels = [f"Fotograma {i + 1} (en { _safe_float(t, 0.0):.2f}s)" for i, t in enumerate(frame_times[:len(media_parts)])]
        else:
            default_pcts = ["15%", "50%", "82%"]
            labels = [
                f"Fotograma {i + 1} ({default_pcts[i] if i < len(default_pcts) else 'secuencia'} del clip)"
                for i in range(len(media_parts))
            ]

        context_line = f"\nContexto del clip: {clip_context}" if clip_context else ""
        system_instruction = (
            "Eres un director de fotografía y editor viral que analiza secuencia de fotogramas de clips 16:9 "
            "(gameplay tipo GTA 6, reacciones, streams, podcasts) para dirigir el encuadre vertical 9:16 y zoom dramático."
        )
        prompt = f"""
Analiza esta secuencia de {len(media_parts)} fotogramas del recorte: {", ".join(labels)}.{context_line}
{_VISION_SCENE_SPEC}

Además de clasificar la escena y cajas principales (`webcam_box`, `roi_box`), identifica `climax_beat`: el evento visual más gracioso, impactante o importante (choque, meme, NPC, gesto, jugada, texto en pantalla) donde conviene hacer zoom/enfoque.

Devuelve un JSON dict exacto:
{{
  "scene_type": "two_person_split" | "multi_panel" | "facecam_gameplay" | "gaming_action" | "single_speaker" | "blur_bg",
  "has_facecam": boolean,
  "has_important_bottom_graphic": boolean,
  "layout_recommended": "duo_split" | "speaker_focus" | "split_screen" | "gaming_zoom" | "centered_face" | "blur_bg",
  "webcam_box": {{"x": float, "y": float, "w": float, "h": float}},
  "roi_box": {{"x": float, "y": float, "w": float, "h": float}},
  "climax_beat": {{
    "at_sec": float,
    "duration_sec": float,
    "focus_box": {{"x": float, "y": float, "w": float, "h": float}},
    "zoom_factor": float,
    "label": string
  }}
}}
Reglas para `climax_beat`:
- `at_sec`: segundo dentro del clip donde inicia/ocurre el evento visual principal (coherente con los fotogramas).
- `duration_sec`: duración del enfoque/zoom entre 3.5 y 6.0 segundos.
- `focus_box`: caja normalizada 0.0-1.0 apuntando con precisión al suceso visual/meme/choque/personaje protagonista.
- `zoom_factor`: entre 1.15 y 1.45.
- `label`: etiqueta breve en español (2 a 6 palabras) describiendo el evento visual.
"""
        try:
            res = await gemini_pool.generate_json(
                prompt, system_instruction, task_name="analyze_clip_beats", media_parts=media_parts
            )
            item = res[0] if isinstance(res, list) and res else res
            sanitized = _sanitize_vision_dict(item)
            raw_beat = item.get("climax_beat") if isinstance(item, dict) else {}
            sanitized["climax_beat"] = _build_climax_beat(raw_beat, default_at, sanitized["roi_box"])
            return sanitized
        except Exception:
            fallback = _sanitize_vision_dict({})
            fallback["climax_beat"] = _build_climax_beat({}, default_at, fallback["roi_box"])
            return fallback

    async def _find_moments(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        transcript_text = payload.get("transcript", "")
        signals = payload.get("signals", {})
        streamer_name = payload.get("streamer", "Streamer")
        user_context = payload.get("user_context", "")
        media_parts = _encode_jpeg_parts(payload.get("frame_paths")) or None

        system_instruction = (
            "Eres un editor profesional de clips en español. Priorizas contexto completo, "
            "sincronía con picos de chat/audio/retención, explicación clara de qué ocurre y títulos naturales sin abuso de mayúsculas. "
            "Responde en JSON array."
        )
        prompt = f"""
Streamer: {streamer_name}
Contexto editorial adicional: {user_context or "Ninguno"}
Señales detectadas (picos de chat, audio, retención o capítulos):
{json.dumps(signals, ensure_ascii=False, indent=2)}

{_EDITORIAL_CLIP_CRITERIA}

Transcripción con marcas de tiempo:
{transcript_text[:25000]}

Extrae entre 4 y 10 momentos reales (22 a 75 segundos, incluyendo planteamiento previo completo y centrando el corte alrededor del evento gracioso/dramático o remate) con:
- "start_sec": float
- "end_sec": float
- "climax_sec": float (segundo exacto del pico o remate dentro de [start_sec, end_sec])
- "hook": string (3 a 6 palabras claras de gancho)
- "title": string (título natural <=52 caracteres, máx 1 emoji opcional)
- "meme_caption": string (texto breve de 2 a 5 palabras estilo meme/reacción si es gracioso, o "")
- "reason": string (explicación de 2 a 3 frases claras sobre qué precedió al momento, qué se dice/hace y por qué engancha)
- "virality_score": int (60-99)
- "event_comment": string (nota breve sin corchetes)
- "tags": list[str]
"""
        result = await gemini_pool.generate_json(
            prompt, system_instruction, task_name="find_moments", media_parts=media_parts
        )
        moments: List[Dict[str, Any]]
        if isinstance(result, list):
            moments = result
        elif isinstance(result, dict) and "moments" in result and isinstance(result["moments"], list):
            moments = result["moments"]
        else:
            moments = [result] if isinstance(result, dict) else []

        for m in moments:
            if isinstance(m, dict):
                s_sec = max(0.0, _safe_float(m.get("start_sec"), 0.0))
                e_sec = max(s_sec + 1.0, _safe_float(m.get("end_sec"), s_sec + 35.0))
                c_raw = m.get("climax_sec")
                c_sec = _safe_float(c_raw, (s_sec + e_sec) * 0.5) if c_raw is not None else (s_sec + e_sec) * 0.5
                m["climax_sec"] = round(max(s_sec, min(e_sec, c_sec)), 2)
                m["meme_caption"] = str(m.get("meme_caption") or "").strip()
        return moments

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
        style = payload.get("style", "drama")
        style_notes = {
            "drama": "Dramatización visual con diálogo dinámico entre 2 o 3 personajes contrastados que actúan la situación paso a paso, con emoción, conflicto y remate claro.",
            "explainer": "Explicación visual con diálogo entre Curioso y Experto mostrando mecanismos reales, acciones en pantalla, objetos y pasos concretos.",
            "gaming_lore": "Estilo GTA 6 / gaming dramatizado: personajes actuando la escena (Jugador, NPC/Relator) con acción en la calle, objetos y giro final.",
            "curiosities": "Historia dramatizada con personajes descubriendo el secreto detrás del tema mediante diálogos ágiles.",
            "top5": "Conteo visual animado con presentador y réplicas breves mostrando objetos y escenas por cada puesto.",
            "history": "Narrativa histórica o de misterio dramatizada con voces contrastadas, tensión visual creciente y desenlace.",
            "data_charts": "Debate visual donde personajes comparan cifras reales con objetos y balanzas moviéndose en escena.",
        }.get(style, "Dramatización visual con personajes actuando y dialogando con ritmo ágil.")

        system_instruction = (
            "Eres guionista y director de cortometrajes animados verticales en español (30 a 45 segundos, 3 a 4 escenas visuales). "
            "NUNCA hagas presentaciones aburridas de tarjetas de texto: escribe diálogos vivos entre personajes para que ocurra una situación real en escena."
        )
        prompt = f"""
Tema: {topic}
Estilo: {style} ({style_notes})

Devuelve un JSON dict EXACTO con:
- "title": string corto y natural (máx 1 emoji opcional si suma)
- "hook": string (primera frase hablada de alto impacto que atrapa en 3s)
- "characters": lista de 2 a 3 personajes que actúan en la historia, cada uno con:
  {{
    "id": "c1" | "c2" | "c3",
    "name": string corto (ej. "Ciudadano", "Analista", "Poder", "Jugador", "Dev"),
    "archetype": "citizen" | "analyst" | "authority" | "gamer" | "reporter" | "developer",
    "voice": uno distinto por personaje entre ["es-CO-GonzaloNeural", "es-MX-JorgeNeural", "es-MX-DaliaNeural", "es-ES-AlvaroNeural", "es-ES-ElviraNeural", "es-AR-TomasNeural"],
    "accent_color": hex vibrante (ej. "#38BDF8", "#2BF0C8", "#EF4444", "#F59E0B", "#A855F7")
  }}
- "scenes": lista de 3 a 4 escenas secuenciales con:
  {{
    "scene_id": int,
    "setting": "city_plaza_night" | "surveillance_state" | "podcast_desk" | "street_action" | "code_lab" | "court_chamber" | "stadium",
    "action_type": "crowd_vs_power" | "debate_faceoff" | "surveillance_control" | "balance_shift" | "domino_cascade" | "chase_escape" | "system_flow",
    "emotion": "tense" | "curious" | "fearful" | "shocked" | "angry" | "confident" | "triumphant",
    "crowd_count": int (0 a 22; usa 10-22 cuando haya pueblo, público, usuarios o multitud),
    "visual_objects": lista de 1 a 3 objetos concretos de ["spotlight", "camera", "megaphone", "chains", "scale", "shield", "money", "car", "police_lights", "microphone", "laptop", "rocket", "lock", "chart_rising"],
    "visual_cue": string describiendo qué están haciendo físicamente los personajes y objetos en esta escena,
    "dialogues": lista de 2 a 3 turnos cortos alternando personajes {{ "speaker_id": "c1"|"c2"|"c3", "text": string hablado natural }},
    "estimated_sec": float (8.0 a 14.0)
  }}
Reglas:
- Cada turno de diálogo debe sonar como habla humana real (preguntas directas, réplicas, tensión), nunca como diapositiva leída.
- La primera línea del diálogo de la escena 1 debe coincidir con o arrancar desde "hook".
"""
        return await gemini_pool.generate_json(prompt, system_instruction, task_name="script")

    async def _generate_scene_plan(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        script = payload.get("script", {})
        system_instruction = (
            "Eres director de animación SVG y puesta en escena 2D vertical (1080x1920). "
            "Creas coreografías visuales donde las cosas acontecen con personajes, multitudes, cámaras y objetos vectoriales."
        )
        prompt = f"""
Guion dramatizado:
{json.dumps(script, ensure_ascii=False, indent=2)}

Devuelve un JSON array (una entrada por cada escena del guion) con:
- "scene_id": int
- "setting": string (mismo del guion)
- "action_type": string (mismo del guion)
- "emotion": string
- "crowd_count": int (0 a 22)
- "visual_objects": lista de 1 a 3 objetos de ["spotlight", "camera", "megaphone", "chains", "scale", "shield", "money", "car", "police_lights", "microphone", "laptop", "rocket", "lock", "chart_rising"]
- "active_characters": lista de ids (ej. ["c1", "c2"] o ["c1", "c3"]) presentes en pantalla
- "camera_motion": "zoom_in" | "pan_left" | "pan_right" | "handheld_tension" | "dolly_focus"
- "stage_caption": string muy corto de 2 a 4 palabras para esquina superior (ej. "LA PLAZA // SILENCIO", "QUIEBRE DEL MIEDO")
- "headline": string corto de 3 a 6 palabras (para vista previa)
- "subtitle": string breve describiendo la acción visual de la escena
- "accent_color": hex vibrante acorde al tono de la escena
- "bespoke_svg": string con elementos vectoriales SVG puros (<path>, <rect>, <circle>, <polygon>, <line>) dentro de un bloque <g> para ilustrar edificios, monumentos, barreras u objetos específicos del tema en coordenadas x=80..1000, y=320..920 (OPACIDAD suave 0.28-0.75, PROHIBIDO poner etiquetas <text> o <script> dentro).
- "duration_sec": float
"""
        res = await gemini_pool.generate_json(prompt, system_instruction, task_name="scene_plan")
        if isinstance(res, list):
            return res
        if isinstance(res, dict) and "scenes" in res:
            return res["scenes"]
        return [res]


pulpo = PulpoRouter()
