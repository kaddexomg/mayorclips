import json
import re
from typing import Any, Dict, List, Optional

from pulpo.gemini_pool import gemini_pool
from pulpo.tts import VOICES, sanitize_tts_text

VALID_VOICES = list(VOICES.keys())

VALID_BEAT_TYPES = {
    "broll_drama",
    "broll_surveillance",
    "chat_reveal",
    "news_alert",
    "data_chart",
    "code_diff",
    "terminal_run",
    "flow_diagram",
    "kinetic_stat",
    "lottie_callout",
}

VALID_CAMERAS = {
    "zoom_in",
    "pan_left",
    "pan_right",
    "camera_shake",
    "dolly_zoom",
    "editorial_flash",
}

VALID_TRANSITIONS = {
    "whip_left",
    "flash_white",
    "iris",
    "crossfade",
    "glitch_cut",
    "slide_up",
}

VALID_GRADINGS = {
    "noir_teal",
    "warm_amber",
    "alert_crimson",
    "cyber_dark",
    "documentary",
}

VALID_LOTTI_BADGES = {
    "none",
    "fire",
    "rocket",
    "warning",
    "chart_up",
    "chart_down",
    "eyes",
    "brain",
    "lightning",
    "check_mark",
    "globe",
    "money_wings",
    "lock",
    "police_light",
    "trophy",
    "sparkles",
    "100",
    "clapper",
    "gear",
    "laptop",
    "megaphone",
    "mascot_walk",
}

EXPLAINER_STYLES = {"explainer", "data_charts"}


def _pick_default_visual_query(topic: str, style: str, beat_idx: int) -> str:
    t_low = (topic or "").lower()
    if "venezuela" in t_low or "caracas" in t_low:
        pool = [
            "Caracas Venezuela night street city",
            "security camera cctv surveillance night",
            "crowd people plaza protest city",
            "government palace monument architecture",
            "Caracas skyline sunset aerial",
            "dark alley street lamp night",
        ]
        return pool[beat_idx % len(pool)]
    if "gta" in t_low or "ffmpeg" in t_low or style in EXPLAINER_STYLES:
        pool = [
            "video editing workstation dark studio",
            "server rack data center glowing",
            "software developer code monitor",
            "3d graphics rendering computer",
            "miami skyline neon night",
            "processor microchip circuit dark",
        ]
        return pool[beat_idx % len(pool)]
    if "futbol" in t_low or "fútbol" in t_low:
        pool = [
            "football stadium lights night crowd",
            "soccer match stadium fans",
            "broadcast television studio camera",
            "money currency finance bank",
        ]
        return pool[beat_idx % len(pool)]
    pool = [
        "city street night lights cinema",
        "modern architecture urban skyline",
        "technology workstation dark room",
        "crowd people city plaza",
    ]
    return pool[beat_idx % len(pool)]


def _normalize_characters(raw_chars: Any, default_voice: str) -> List[Dict[str, Any]]:
    chars: List[Dict[str, Any]] = []
    if isinstance(raw_chars, list):
        for idx, ch in enumerate(raw_chars[:3]):
            if not isinstance(ch, dict):
                continue
            v = ch.get("voice")
            if v not in VOICES:
                v = default_voice if idx == 0 and default_voice in VOICES else VALID_VOICES[idx % len(VALID_VOICES)]
            chars.append({
                "id": str(ch.get("id") or f"c{idx + 1}"),
                "name": str(ch.get("name") or f"Voz {idx + 1}")[:24],
                "archetype": str(ch.get("archetype") or ("citizen" if idx == 0 else "analyst")),
                "voice": v,
                "accent_color": str(ch.get("accent_color") or ("#38BDF8" if idx == 0 else "#2BF0C8")),
            })
    if not chars:
        v0 = default_voice if default_voice in VOICES else VALID_VOICES[0]
        v1 = next((v for v in VALID_VOICES if v != v0), VALID_VOICES[1])
        chars = [
            {"id": "c1", "name": "Narrador", "archetype": "analyst", "voice": v0, "accent_color": "#2BF0C8"},
            {"id": "c2", "name": "Contrapunto", "archetype": "citizen", "voice": v1, "accent_color": "#38BDF8"},
        ]
    return chars


def _split_long_text(text: str, max_words: int = 16) -> List[str]:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return []
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    chunks: List[str] = []
    for sent in sentences:
        words = sent.split()
        if len(words) <= max_words:
            chunks.append(sent)
        else:
            mid = len(words) // 2
            chunks.append(" ".join(words[:mid]))
            chunks.append(" ".join(words[mid:]))
    return chunks or [text]


def _normalize_beat(
    raw: Dict[str, Any],
    idx: int,
    topic: str,
    style: str,
    characters: List[Dict[str, Any]],
) -> Dict[str, Any]:
    char_ids = {c["id"] for c in characters}
    char_map = {c["id"]: c for c in characters}
    is_explainer = style in EXPLAINER_STYLES

    btype = str(raw.get("beat_type") or "").strip()
    if btype not in VALID_BEAT_TYPES:
        btype = "data_chart" if is_explainer and idx % 2 == 1 else "broll_drama"

    cam = str(raw.get("camera_motion") or "").strip()
    if cam not in VALID_CAMERAS:
        cam = ["zoom_in", "pan_left", "camera_shake", "pan_right"][idx % 4]

    trans = str(raw.get("transition_in") or "").strip()
    if trans not in VALID_TRANSITIONS:
        trans = ["flash_white", "whip_left", "iris", "slide_up"][idx % 4]

    grading = str(raw.get("grading") or "").strip()
    if grading not in VALID_GRADINGS:
        grading = "cyber_dark" if is_explainer else ("alert_crimson" if btype in ("news_alert", "broll_surveillance") else "noir_teal")

    lottie = str(raw.get("lottie_badge") or "none").strip()
    if lottie not in VALID_LOTTI_BADGES:
        lottie = "sparkles"

    hud = str(raw.get("hud_overlay") or "none").strip()
    if hud not in ("camcorder", "news_ticker", "radar_focus", "none"):
        hud = "none"

    dlgs_out: List[Dict[str, Any]] = []
    for d_idx, d in enumerate(raw.get("dialogues") or []):
        if not isinstance(d, dict):
            continue
        txt = sanitize_tts_text(str(d.get("text") or ""))
        if not txt:
            continue
        sp_id = str(d.get("speaker_id") or "")
        if sp_id not in char_ids:
            sp_id = characters[d_idx % len(characters)]["id"]
        sp = char_map[sp_id]
        dlgs_out.append({
            "speaker_id": sp_id,
            "speaker_name": sp["name"],
            "archetype": sp.get("archetype", "analyst"),
            "accent_color": sp.get("accent_color", "#2BF0C8"),
            "voice": sp["voice"],
            "text": txt,
        })

    if not dlgs_out:
        sp = characters[idx % len(characters)]
        fallback_txt = sanitize_tts_text(str(raw.get("headline") or "")) or sanitize_tts_text(topic) or f"Escena {idx + 1}"
        dlgs_out.append({
            "speaker_id": sp["id"],
            "speaker_name": sp["name"],
            "archetype": sp.get("archetype", "analyst"),
            "accent_color": sp.get("accent_color", "#2BF0C8"),
            "voice": sp["voice"],
            "text": fallback_txt,
        })

    accent = str(raw.get("accent_color") or "").strip()
    if not re.match(r"^#[0-9a-fA-F]{6}$", accent):
        accent = "#2BF0C8" if is_explainer else ("#EF4444" if btype == "news_alert" else "#38BDF8")

    hbox = raw.get("highlight_box")
    if not isinstance(hbox, dict):
        hbox = None

    payload = raw.get("visual_payload")
    if not isinstance(payload, dict):
        payload = {}

    # Ensure structured payload defaults exist for specialized beat types
    if btype == "chat_reveal" and not payload.get("messages"):
        msgs = []
        for m_i, d in enumerate(dlgs_out[:3]):
            msgs.append({
                "side": "recv" if m_i % 2 == 0 else "sent",
                "sender": d["speaker_name"],
                "text": d["text"][:110],
            })
        if not msgs:
            msgs = [{"side": "recv", "sender": "Fuente", "text": raw.get("headline") or topic[:80]}]
        payload = {
            "app_title": payload.get("app_title") or ("AI Studio" if is_explainer else "Canal Directo"),
            "messages": msgs,
        }
    elif btype == "data_chart" and not payload.get("values"):
        if not is_explainer:
            btype = "broll_drama"
        else:
            payload = {
                "chart_type": payload.get("chart_type") or "bars",
                "title": payload.get("title") or (raw.get("headline") or "IMPACTO COMPARADO"),
                "subtitle": payload.get("subtitle") or "Métrica en tiempo real",
                "unit": payload.get("unit") or "%",
                "labels": ["Base", "Fase 1", "Fase 2", "Pico"],
                "values": [24, 52, 79, 96],
                "emphasize_idx": 3,
            }
    elif btype == "code_diff" and not payload.get("added"):
        payload = {
            "filename": payload.get("filename") or "pipeline.py",
            "removed": payload.get("removed") or ["render_static_frame(dur=12.0)", "fps = 10  # bottleneck"],
            "added": payload.get("added") or ["seek_deterministic_stage(beat_t)", "encode_gpu_amf(fps=20, res='1080x1920')"],
        }
    elif btype == "terminal_run" and not payload.get("logs"):
        payload = {
            "prompt": payload.get("prompt") or "hyperframes render --fps 20 --gpu h264_amf",
            "logs": ["[STAGE] B-Roll + Lottie cargados", "[GPU] Radeon AMF 1080x1920 activo", "[OK] 0 frames perdidos · Listo"],
        }
    elif btype == "flow_diagram" and not payload.get("nodes"):
        payload = {
            "title": payload.get("title") or "ARQUITECTURA",
            "nodes": [
                {"title": "1. Entrada", "detail": "Audio & Guion"},
                {"title": "2. Motor Visual", "detail": "B-Roll + Lottie + GSAP"},
                {"title": "3. Render GPU", "detail": "1080x1920 H.264 AMF"},
            ],
        }
    elif btype == "kinetic_stat" and payload.get("value") is None:
        if not is_explainer:
            btype = "broll_drama"
        else:
            payload = {
                "value": 99.2,
                "decimals": 1,
                "prefix": "",
                "suffix": "%",
                "label": (raw.get("headline") or "EFICIENCIA").upper(),
                "sub": "Comparativa de arquitectura en tiempo real",
            }

    return {
        "beat_id": idx + 1,
        "beat_type": btype,
        "headline": str(raw.get("headline") or f"Escena {idx + 1}")[:56],
        "kicker": str(raw.get("kicker") or f"BEAT 0{idx + 1}").upper()[:36],
        "visual_query": str(raw.get("visual_query") or _pick_default_visual_query(topic, style, idx))[:80],
        "camera_motion": cam,
        "transition_in": trans,
        "grading": grading,
        "accent_color": accent,
        "lottie_badge": lottie,
        "hud_overlay": hud,
        "ticker_text": str(raw.get("ticker_text") or raw.get("headline") or topic)[:90],
        "highlight_box": hbox,
        "visual_payload": payload,
        "dialogues": dlgs_out,
    }


def _fallback_split_to_beats(
    topic: str,
    style: str,
    title: str,
    script_json: Dict[str, Any],
    scene_plan_json: List[Dict[str, Any]],
    default_voice: str,
) -> Dict[str, Any]:
    """Deterministic beat-by-beat storyboard choreographer when Gemini is unavailable or skipped."""
    characters = _normalize_characters(script_json.get("characters"), default_voice)
    is_explainer = style in EXPLAINER_STYLES

    drama_cycle = [
        ("broll_drama", "editorial_flash", "flash_white", "police_light", "none"),
        ("broll_surveillance", "camera_shake", "glitch_cut", "eyes", "camcorder"),
        ("chat_reveal", "zoom_in", "slide_up", "warning", "none"),
        ("broll_drama", "pan_right", "whip_left", "fire", "news_ticker"),
        ("news_alert", "camera_shake", "flash_white", "megaphone", "news_ticker"),
        ("kinetic_stat", "zoom_in", "iris", "chart_up", "none"),
        ("lottie_callout", "pan_left", "crossfade", "mascot_walk", "none"),
        ("broll_drama", "dolly_zoom", "flash_white", "lightning", "radar_focus"),
    ]
    explainer_cycle = [
        ("broll_drama", "editorial_flash", "flash_white", "rocket", "none"),
        ("code_diff", "zoom_in", "slide_up", "laptop", "none"),
        ("data_chart", "pan_left", "whip_left", "chart_up", "none"),
        ("terminal_run", "zoom_in", "glitch_cut", "gear", "none"),
        ("flow_diagram", "pan_right", "iris", "brain", "none"),
        ("kinetic_stat", "dolly_zoom", "flash_white", "100", "none"),
        ("chat_reveal", "zoom_in", "slide_up", "sparkles", "none"),
        ("broll_drama", "zoom_in", "crossfade", "trophy", "radar_focus"),
    ]
    cycle = explainer_cycle if is_explainer else drama_cycle

    # Collect all dialogue turns and split long lines so we hit 6-9 tight beats
    turns: List[Dict[str, Any]] = []
    scenes = script_json.get("scenes") or []
    plan_by_id = {sc.get("scene_id"): sc for sc in (scene_plan_json or []) if isinstance(sc, dict)}

    for s_idx, sc in enumerate(scenes):
        sid = sc.get("scene_id") or (s_idx + 1)
        plan = plan_by_id.get(sid) or {}
        headline = plan.get("stage_caption") or plan.get("headline") or title
        dlgs = sc.get("dialogues") or []
        if not dlgs and sc.get("spoken_text"):
            dlgs = [{"speaker_id": characters[s_idx % len(characters)]["id"], "text": sc["spoken_text"]}]
        for d in dlgs:
            sp_id = d.get("speaker_id") or characters[0]["id"]
            for piece in _split_long_text(d.get("text", ""), max_words=17):
                turns.append({"speaker_id": sp_id, "text": piece, "hint": headline})

    if not turns:
        hook = script_json.get("hook") or title or topic
        turns = [
            {"speaker_id": characters[0]["id"], "text": hook, "hint": title},
            {"speaker_id": characters[-1]["id"], "text": f"Analizamos a fondo {topic}.", "hint": title},
        ]

    # Target 6 to 9 beats
    while len(turns) < 6 and any(len(t["text"].split()) > 8 for t in turns):
        expanded = []
        for t in turns:
            words = t["text"].split()
            if len(words) > 8 and len(expanded) + len(turns) < 9:
                mid = len(words) // 2
                expanded.append({**t, "text": " ".join(words[:mid])})
                expanded.append({**t, "text": " ".join(words[mid:])})
            else:
                expanded.append(t)
        turns = expanded
        if len(turns) >= 6:
            break

    beats_raw: List[Dict[str, Any]] = []
    for idx, t in enumerate(turns[:10]):
        btype, cam, trans, lottie, hud = cycle[idx % len(cycle)]
        beats_raw.append({
            "beat_type": btype,
            "headline": (t.get("hint") or title)[:48],
            "kicker": f"BEAT 0{idx + 1} · {style.upper()}",
            "visual_query": _pick_default_visual_query(topic, style, idx),
            "camera_motion": cam,
            "transition_in": trans,
            "lottie_badge": lottie,
            "hud_overlay": hud,
            "highlight_box": {"label": "FOCO CLAVE", "x": 0.22, "y": 0.28, "w": 0.56, "h": 0.34} if hud == "radar_focus" else None,
            "dialogues": [{"speaker_id": t["speaker_id"], "text": t["text"]}],
        })

    beats = [_normalize_beat(b, i, topic, style, characters) for i, b in enumerate(beats_raw)]
    return {"title": title or topic[:48], "characters": characters, "beats": beats}


async def enhance_studio_storyboard(
    topic: str,
    style: str,
    title: str,
    script_json: Dict[str, Any],
    scene_plan_json: List[Dict[str, Any]],
    default_voice: str = "es-MX-DaliaNeural",
) -> Dict[str, Any]:
    """Transforms a coarse StudioVideo script into a rich 6-10 beat Motion Graphics storyboard."""
    # If already directed into >= 6 beats, normalize and return cleanly
    existing_beats = script_json.get("beats") if isinstance(script_json, dict) else None
    if isinstance(existing_beats, list) and len(existing_beats) >= 6:
        chars = _normalize_characters(script_json.get("characters"), default_voice)
        norm_beats = [_normalize_beat(b, i, topic, style, chars) for i, b in enumerate(existing_beats[:10])]
        return {"title": title or script_json.get("title") or topic, "characters": chars, "beats": norm_beats}

    characters = _normalize_characters(script_json.get("characters"), default_voice)
    is_explainer = style in EXPLAINER_STYLES

    mode_rules = (
        "MODO EXPLAINER/TECH: Alterna dinámicamente entre:\n"
        "- 'broll_drama' (foto real tech/gaming con Ken Burns + radar_focus)\n"
        "- 'code_diff' (visual_payload: {filename, removed: [2 líneas], added: [2 líneas]})\n"
        "- 'terminal_run' (visual_payload: {prompt, logs: [3 líneas]})\n"
        "- 'data_chart' (visual_payload: {chart_type: 'bars'|'line'|'progress', title, subtitle, unit, labels: [4], values: [4 números], emphasize_idx: 0..3})\n"
        "- 'flow_diagram' (visual_payload: {title, nodes: [{title, detail}, ...] de 3-4 pasos})\n"
        "- 'kinetic_stat' (visual_payload: {value: float, decimals: int, prefix, suffix, label, sub})\n"
        "- 'chat_reveal' (visual_payload: {app_title, messages: [{side:'recv'|'sent', sender, text}]})"
        if is_explainer
        else
        "MODO DRAMA/HISTORIA/CURIOSIDADES: Alterna dinámicamente cada 3-5s entre:\n"
        "- 'broll_drama' (foto real cinematográfica con Ken Burns/camera_shake + Lottie + titular)\n"
        "- 'broll_surveillance' (hud_overlay='camcorder' + highlight_box={label,x,y,w,h} + foto nocturna/vigilancia)\n"
        "- 'chat_reveal' (mensajes reales tipo chat privado/vecinal: visual_payload={app_title, messages:[{side:'recv'|'sent', sender, text}]})\n"
        "- 'news_alert' (hud_overlay='news_ticker' + titular de última hora sobre foto real)\n"
        "- 'kinetic_stat' o 'data_chart' (para contrastar cifras reales ej. '1000 vs 1' o porcentaje)\n"
        "- 'lottie_callout' (personaje/ícono Lottie destacado + tarjeta)"
    )

    system_instruction = (
        "Eres Director Creativo de Motion Graphics y Storytelling Visual para video vertical 9:16 (HyperFrames + Lottie + B-Roll). "
        "JAMÁS dejes una escena estática más de 5 segundos. Divide toda la historia en 6 a 9 BEATS cortos (3 a 5 segundos cada uno, ~30-42s en total). "
        "Responde SIEMPRE en JSON válido."
    )

    prompt = f"""
Tema: {topic}
Título: {title}
Estilo: {style}
Personajes disponibles: {json.dumps(characters, ensure_ascii=False)}
Guion base a coreografiar (conserva la fuerza de sus diálogos y repártelos en 6 a 9 beats cortos):
{json.dumps(script_json, ensure_ascii=False)[:4500]}

{mode_rules}

REGLAS CRÍTICAS DE B-ROLL Y DISEÑO:
1. Cada beat debe tener 1 o 2 líneas cortas de diálogo (`dialogues`: [{{speaker_id, text}}]) para durar ~3.5 a 5.0 segundos.
2. `visual_query` DEBE ser una búsqueda fotográfica de SOLO 2 a 3 PALABRAS concretas en INGLÉS (ej. "Caracas protest", "security camera CCTV", "night city street", "police patrol car", "server room", "computer code screen"). NUNCA pongas frases largas ni conceptos abstractos.
3. Si eliges `kinetic_stat`, `data_chart`, `code_diff`, `terminal_run`, `flow_diagram` o `chat_reveal`, DEBES llenar su `visual_payload` completo con datos reales del tema (ej. para drama "1000 vs 1" -> `kinetic_stat` con `value: 1000, suffix: ":1", label: "MIL CIUDADANOS POR CADA UNO"`). Si no hay cifras, usa `broll_drama`, `broll_surveillance`, `chat_reveal`, `news_alert` o `lottie_callout`.
4. Varía `beat_type`, `camera_motion` ("zoom_in"|"pan_left"|"pan_right"|"camera_shake"|"dolly_zoom"|"editorial_flash"), `transition_in` ("whip_left"|"flash_white"|"iris"|"crossfade"|"glitch_cut"|"slide_up") y `lottie_badge` ("fire"|"rocket"|"warning"|"chart_up"|"eyes"|"brain"|"lightning"|"check_mark"|"globe"|"money_wings"|"lock"|"police_light"|"trophy"|"sparkles"|"megaphone"|"mascot_walk"|"none") para que cada corte se sienta vivo y diferente.

Devuelve un JSON dict EXACTO:
{{
  "title": "{title}",
  "beats": [
    {{
      "beat_id": 1,
      "beat_type": "...",
      "headline": "TITULAR CORTO (<=42 chars)",
      "kicker": "ETIQUETA 2-3 PALABRAS",
      "visual_query": "concrete english photo search",
      "camera_motion": "zoom_in",
      "transition_in": "flash_white",
      "grading": "noir_teal" | "warm_amber" | "alert_crimson" | "cyber_dark" | "documentary",
      "accent_color": "#2BF0C8",
      "lottie_badge": "...",
      "hud_overlay": "camcorder" | "news_ticker" | "radar_focus" | "none",
      "ticker_text": "texto corto de teletipo si aplica",
      "highlight_box": {{"label": "PUNTO CLAVE", "x": 0.2, "y": 0.25, "w": 0.6, "h": 0.35}} | null,
      "visual_payload": {{ ... }},
      "dialogues": [{{"speaker_id": "c1", "text": "..."}}]
    }}
  ]
}}
"""
    try:
        res = await gemini_pool.generate_json(prompt, system_instruction, task_name="director_storyboard")
        if isinstance(res, dict) and isinstance(res.get("beats"), list) and len(res["beats"]) >= 4:
            norm_beats = [_normalize_beat(b, i, topic, style, characters) for i, b in enumerate(res["beats"][:10])]
            # Ensure we have at least 6 beats by splitting if Gemini returned 4-5
            if len(norm_beats) < 6:
                return _fallback_split_to_beats(topic, style, title, script_json, scene_plan_json, default_voice)
            return {
                "title": str(res.get("title") or title or topic),
                "characters": characters,
                "beats": norm_beats,
            }
    except Exception as e:
        print(f"[DIRECTOR] Fallback storyboard choreographer used ({type(e).__name__}: {e})")

    return _fallback_split_to_beats(topic, style, title, script_json, scene_plan_json, default_voice)


async def create_storyboard(
    topic: str,
    style: str = "drama",
    default_voice: str = "es-MX-DaliaNeural",
) -> Dict[str, Any]:
    """Generates a complete character cast + 6-10 beat Motion Graphics storyboard directly from a topic."""
    is_explainer = style in EXPLAINER_STYLES
    v0 = default_voice if default_voice in VOICES else VALID_VOICES[0]
    v1 = next((v for v in VALID_VOICES if v != v0), VALID_VOICES[1])
    v2 = next((v for v in VALID_VOICES if v not in (v0, v1)), VALID_VOICES[2])

    default_chars = (
        [
            {"id": "c1", "name": "Arquitecto", "archetype": "developer", "voice": v0, "accent_color": "#2BF0C8"},
            {"id": "c2", "name": "Analista", "archetype": "analyst", "voice": v1, "accent_color": "#38BDF8"},
        ]
        if is_explainer
        else [
            {"id": "c1", "name": "Testigo", "archetype": "citizen", "voice": v0, "accent_color": "#38BDF8"},
            {"id": "c2", "name": "Narrador", "archetype": "analyst", "voice": v1, "accent_color": "#F59E0B"},
            {"id": "c3", "name": "Poder", "archetype": "authority", "voice": v2, "accent_color": "#EF4444"},
        ]
    )

    seed_script = {
        "title": topic[:52],
        "characters": default_chars,
        "scenes": [
            {
                "scene_id": 1,
                "dialogues": [
                    {"speaker_id": "c1", "text": f"¿Alguna vez te preguntaste la verdad detrás de {topic}?"},
                    {"speaker_id": "c2", "text": "Mira los datos y el mecanismo real que casi nadie ve."},
                ],
            }
        ],
    }

    system_instruction = (
        "Eres guionista y director de cortometrajes motion graphics verticales en español (32-44s, 6 a 8 beats). "
        "Creas guiones intensos con diálogo humano real y coreografía visual variada. Responde en JSON válido."
    )
    prompt = f"""
Tema: {topic}
Estilo: {style}
Elenco: {json.dumps(default_chars, ensure_ascii=False)}

Escribe un guion corto de 6 a 8 beats (total 32-44 segundos, cada beat ~4s con 1-2 frases cortas de diálogo) en JSON:
{{
  "title": string corto y atractivo,
  "characters": {json.dumps(default_chars, ensure_ascii=False)},
  "beats": [
    {{
      "beat_id": 1,
      "beat_type": "broll_drama" | "broll_surveillance" | "chat_reveal" | "news_alert" | "data_chart" | "code_diff" | "terminal_run" | "flow_diagram" | "kinetic_stat" | "lottie_callout",
      "headline": string <= 42 chars,
      "kicker": string <= 28 chars,
      "visual_query": "2-4 concrete english photo keywords",
      "camera_motion": "zoom_in" | "pan_left" | "pan_right" | "camera_shake" | "dolly_zoom" | "editorial_flash",
      "transition_in": "whip_left" | "flash_white" | "iris" | "crossfade" | "glitch_cut" | "slide_up",
      "grading": "noir_teal" | "warm_amber" | "alert_crimson" | "cyber_dark" | "documentary",
      "accent_color": "#2BF0C8",
      "lottie_badge": "fire"|"rocket"|"warning"|"chart_up"|"eyes"|"brain"|"lightning"|"check_mark"|"globe"|"money_wings"|"lock"|"police_light"|"trophy"|"sparkles"|"megaphone"|"mascot_walk"|"none",
      "hud_overlay": "camcorder" | "news_ticker" | "radar_focus" | "none",
      "ticker_text": string,
      "highlight_box": {{"label": "...", "x": 0.22, "y": 0.28, "w": 0.56, "h": 0.34}} | null,
      "visual_payload": {{}},
      "dialogues": [{{"speaker_id": "c1", "text": "..."}}]
    }}
  ]
}}
"""
    try:
        res = await gemini_pool.generate_json(prompt, system_instruction, task_name="director_create_storyboard")
        if isinstance(res, dict) and isinstance(res.get("beats"), list) and len(res["beats"]) >= 6:
            chars = _normalize_characters(res.get("characters") or default_chars, default_voice)
            norm_beats = [_normalize_beat(b, i, topic, style, chars) for i, b in enumerate(res["beats"][:10])]
            return {
                "title": str(res.get("title") or topic[:52]),
                "characters": chars,
                "beats": norm_beats,
            }
    except Exception as e:
        print(f"[DIRECTOR] create_storyboard fallback ({type(e).__name__}: {e})")

    return _fallback_split_to_beats(topic, style, topic[:52], seed_script, [], default_voice)
