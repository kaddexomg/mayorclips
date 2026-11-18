import os
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Any, List
from sqlmodel import Session

from app.db import engine
from app.models import StudioVideo
from app.config import RENDERS_DIR, CACHE_DIR, FFMPEG_PATH
from pulpo import pulpo
from render.subtitles import generate_ass_file


async def render_studio_video_job(job_id: str, studio_id: str, progress_callback=None) -> Dict[str, Any]:
    """Synthesizes neural Spanish voiceover, builds synced motion graphics & subtitles, and outputs 1080x1920 MP4."""
    with Session(engine) as session:
        sv = session.get(StudioVideo, studio_id)
        if not sv:
            raise ValueError(f"StudioVideo {studio_id} no encontrado")
        script = sv.script_json or {}
        voice_name = sv.voice_name or "es-MX-DaliaNeural"
        title = sv.title

    scenes = script.get("scenes") or []
    spoken_parts = [script.get("hook", "")]
    for sc in scenes:
        t = sc.get("spoken_text", "").strip()
        if t:
            spoken_parts.append(t)
    full_narration = " ".join(p for p in spoken_parts if p).strip()
    if not full_narration:
        full_narration = f"Hoy te contamos sobre {title}."

    if progress_callback:
        progress_callback(20, f"Generando locución neuronal ({voice_name})...")

    tts_res = await pulpo.run("tts", {"text": full_narration, "voice": voice_name}, use_cache=False)
    audio_path = tts_res["audio_path"]
    word_boundaries = tts_res.get("word_boundaries", [])
    duration_sec = max(5.0, float(tts_res.get("duration_sec") or 12.0) + 0.8)

    if progress_callback:
        progress_callback(48, "Sincronizando subtítulos cinéticos palabra por palabra...")

    ass_words = [
        {"word": w["word"], "start_sec": w["start_sec"], "end_sec": w["end_sec"]}
        for w in word_boundaries
    ]
    ass_path = str(CACHE_DIR / f"studio_subs_{studio_id[:8]}.ass")
    generate_ass_file(ass_words, ass_path, style_name="neon", title_hook=title)

    if progress_callback:
        progress_callback(70, "Renderizando Motion Graphics 1080x1920...")

    out_filename = f"studio_{studio_id[:8]}.mp4"
    out_path = RENDERS_DIR / out_filename
    escaped_sub = str(Path(ass_path).resolve()).replace("\\", "/").replace(":", "\\:")

    # Animated Quanty-themed procedural motion graphics background + burned-in synced kinetic text
    # Uses subtle moving wave/glow grid via FFmpeg geq/drawbox + subtitles + neural audio
    vf = (
        f"color=c=#060B10:s=1080x1920:r=30:d={duration_sec:.2f},"
        f"drawbox=x=0:y='mod(t*180,1920)':w=1080:h=6:color=#2BF0C8@0.12:t=fill,"
        f"drawbox=x=80:y=200:w=920:h=4:color=#2BF0C8@0.35:t=fill,"
        f"drawbox=x=80:y=1700:w=920:h=4:color=#2BF0C8@0.35:t=fill,"
        f"subtitles='{escaped_sub}'"
    )

    cmd = [
        FFMPEG_PATH, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=#060B10:s=1080x1920:r=30:d={duration_sec:.2f}",
        "-i", audio_path,
        "-vf", vf.split(",", 1)[1],
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
        str(out_path),
    ]
    await asyncio.to_thread(subprocess.run, cmd, check=True, timeout=180)

    with Session(engine) as session:
        sv = session.get(StudioVideo, studio_id)
        if sv:
            sv.status = "rendered"
            sv.audio_path = audio_path
            sv.output_path = str(out_path)
            session.add(sv)
            session.commit()

    if progress_callback:
        progress_callback(100, "¡Video Motion Graphics renderizado con éxito!")

    return {
        "studio_id": studio_id,
        "output_path": str(out_path),
        "video_url": f"/renders/{out_filename}",
        "duration_sec": duration_sec,
    }
