import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from app.config import CACHE_DIR
from pulpo.gemini_pool import gemini_pool
from pulpo.tts import generate_speech_with_timestamps

def _compute_hash(task: str, payload: Any) -> str:
    raw = f"{task}:{json.dumps(payload, sort_keys=True)}"
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
    """Central AI orchestrator for MayorClips with smart multi-key rotation and zero-token caching."""

    async def run(self, task: str, payload: Dict[str, Any], use_cache: bool = True) -> Any:
        h = _compute_hash(task, payload)
        if use_cache:
            cached = _get_cache(h)
            if cached is not None:
                return cached

        res = None
        if task == "find_moments":
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
        elif task == "vision_check":
            res = await self._vision_check(payload)
        else:
            raise ValueError(f"Tarea de Pulpo desconocida: {task}")

        if use_cache and res is not None:
            _set_cache(h, res)
        return res

    async def _find_moments(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        transcript_text = payload.get("transcript", "")
        signals = payload.get("signals", {}) # chat peaks, audio peaks
        streamer_name = payload.get("streamer", "Streamer")

        system_instruction = (
            "Eres un editor profesional de clips virales para TikTok, Instagram Reels y YouTube Shorts (estilo Quanty Clips / Opus Clip). "
            "Tu objetivo es analizar la transcripción y las señales de reacción (chat, risas, picos de audio) para encontrar los momentos de mayor impacto, "
            "tensión, humor o revelación que retendrán la atención los primeros 3 segundos. "
            "Debes responder ÚNICAMENTE con un JSON válido estructurado como una lista de momentos."
        )

        prompt = f"""
Streamer: {streamer_name}
Señales de interacción (picos de chat o audio):
{json.dumps(signals, ensure_ascii=False, indent=2)}

Transcripción con tiempos aproximados:
{transcript_text[:12000]}

Encuentra entre 4 y 12 momentos virales candidatos (duración entre 15 y 85 segundos).
Cada candidato debe tener:
- "start_sec": float (segundo de inicio, ajustado al inicio de una frase o risa)
- "end_sec": float (segundo de fin, donde concluye la idea o el remate)
- "hook": string (el gancho que debe aparecer en pantalla en los primeros 2 segundos)
- "title": string (título viral de alto CTR)
- "reason": string (por qué se eligió este momento: remate gracioso, fail, jugada épica, discusión, etc.)
- "virality_score": int (entre 60 y 99 según potencial de retención)
- "event_comment": string (un sticker/tarjeta de evento divertido, ej: '💀 Se creía inmortal y le cayó un rayo')
- "tags": list of strings (ej: ['fail', 'humor', 'reaccion'])

Responde estrictamente con el JSON array.
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
        system_instruction = "Eres un estratega de copy viral para clips de formato corto en TikTok, Instagram y Shorts."
        prompt = f"""
Clip: {clip_summary}
Gancho base: {hook}

Genera:
1. "titles": 3 títulos altamente adictivos (sin clickbait engañoso pero con máxima curiosidad).
2. "caption_instagram": Texto para Instagram Reels con 5 hashtags estratégicos.
3. "caption_tiktok": Texto conciso para TikTok con hashtags de tendencia.
4. "caption_facebook": Texto para Facebook Reels.
5. "overlay_sticker": Texto corto y humorístico para tarjeta flotante durante el video.

Responde solo con el JSON dict.
"""
        return await gemini_pool.generate_json(prompt, system_instruction, task_name="write_titles")

    async def _generate_script(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        topic = payload.get("topic", "")
        style = payload.get("style", "curiosities")
        system_instruction = (
            "Eres un guionista de videos virales de alta retención para historias y curiosidades en formato vertical 9:16. "
            "El guion debe tener un gancho contundente en los primeros 3 segundos, datos dinámicos cada 5 segundos y una duración total de 30 a 55 segundos."
        )
        prompt = f"""
Tema: {topic}
Estilo: {style}

Genera un guion dividido en escenas:
- "title": Título del video
- "hook": Los primeros 3 segundos de texto hablado
- "scenes": Lista de escenas, cada una con:
    - "scene_id": 1, 2, ...
    - "spoken_text": Lo que dice la voz en off
    - "visual_cue": Descripción de lo que se debe mostrar en pantalla (gráfico, texto cinético, icono, etc.)
    - "keyword_highlight": Palabra clave para animar en grande
    - "estimated_sec": Duración aproximada en segundos (ej: 6)

Responde en formato JSON dict.
"""
        return await gemini_pool.generate_json(prompt, system_instruction, task_name="script")

    async def _generate_scene_plan(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        script = payload.get("script", {})
        system_instruction = "Eres un director técnico de HyperFrames (HTML/CSS/GSAP rendered to video)."
        prompt = f"""
A partir de este guion:
{json.dumps(script, ensure_ascii=False, indent=2)}

Convierte cada escena en un plan de composición para HyperFrames:
Para cada escena especifica:
- "scene_id": int
- "template": "kinetic_text" | "stat_card" | "split_highlight" | "curiosity_reveal"
- "headline": Texto principal
- "subtitle": Texto secundario
- "accent_color": Código hexadecimal (usa paleta Quanty: #2BF0C8, #E8F6F2, #14242B)
- "animation_type": "slide_up" | "zoom_in" | "glitch_reveal"
- "duration_sec": float

Responde solo con el JSON array.
"""
        res = await gemini_pool.generate_json(prompt, system_instruction, task_name="scene_plan")
        if isinstance(res, list):
            return res
        if isinstance(res, dict) and "scenes" in res:
            return res["scenes"]
        return [res]

    async def _vision_check(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Fallback bounding box for streamer webcam if not detected
        return {
            "webcam_box": {"x": 0.02, "y": 0.02, "width": 0.30, "height": 0.35},
            "gameplay_box": {"x": 0.0, "y": 0.35, "width": 1.0, "height": 0.65}
        }

pulpo = PulpoRouter()
