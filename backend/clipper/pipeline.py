import os
import uuid
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from sqlmodel import Session, select

from app.db import engine
from app.models import Project, Moment, Clip, Transcript
from app.config import MEDIA_DIR, RENDERS_DIR
from ingest import ingester, analyze_audio_peaks
from pulpo import pulpo
from render import generate_ass_file, render_vertical_clip

async def process_project_pipeline(job_id: str, project_id: str, progress_callback=None) -> Dict[str, Any]:
    """Complete automated clipping pipeline: Ingest -> Signals -> Pulpo Moments -> Ready."""
    with Session(engine) as session:
        proj = session.get(Project, project_id)
        if not proj:
            raise ValueError(f"Proyecto {project_id} no encontrado")
        url = proj.source_url
        title = proj.title

    if progress_callback:
        progress_callback(10, "Extrayendo metadatos e información de la fuente...")

    # 1. Metadata extraction
    info = ingester.extract_info(url)
    with Session(engine) as session:
        proj = session.get(Project, project_id)
        if proj:
            proj.title = info.get("title", title)
            proj.duration_sec = info.get("duration_sec", 0.0)
            proj.status = "ingesting"
            session.add(proj)
            session.commit()

    if progress_callback:
        progress_callback(25, "Descargando audio optimizado (audio-first)...")

    # 2. Download audio stream only
    audio_file = ingester.download_audio_first(url, project_id)
    with Session(engine) as session:
        proj = session.get(Project, project_id)
        if proj:
            proj.audio_path = audio_file
            session.add(proj)
            session.commit()

    if progress_callback:
        progress_callback(45, "Analizando señales de audio y picos de reacción...")

    # 3. Audio peaks analysis
    peaks = analyze_audio_peaks(audio_file)
    top_peaks = sorted(peaks, key=lambda p: p["intensity"], reverse=True)[:20]

    if progress_callback:
        progress_callback(60, "El Pulpo IA está detectando los momentos de mayor impacto...")

    # 4. Transcribe summary & detect moments with Gemini Pool
    # Simulated/sample transcript segment if full speech recognition not done locally
    transcript_summary = (
        f"Transmisión de {info.get('streamer', 'Streamer')}: {info.get('title')}. "
        f"Se detectaron {len(top_peaks)} picos de volumen y risas en los segundos: {[p['time_sec'] for p in top_peaks[:8]]}."
    )

    moments_raw = await pulpo.run("find_moments", {
        "transcript": transcript_summary,
        "signals": {"audio_peaks": top_peaks[:10]},
        "streamer": info.get("streamer", "Streamer")
    })

    created_moments = []
    with Session(engine) as session:
        # Clear previous moments if re-running
        prev_moments = session.exec(select(Moment).where(Moment.project_id == project_id)).all()
        for pm in prev_moments:
            session.delete(pm)

        for m_data in moments_raw:
            start_t = float(m_data.get("start_sec", 0.0))
            end_t = float(m_data.get("end_sec", start_t + 35.0))
            # Validate bounds
            if start_t < 0: start_t = 0.0
            if end_t <= start_t: end_t = start_t + 30.0
            dur = round(end_t - start_t, 2)

            moment = Moment(
                project_id=project_id,
                start_sec=start_t,
                end_sec=end_t,
                duration_sec=dur,
                hook=m_data.get("hook", "MIRA ESTO"),
                title=m_data.get("title", "Momento Viral"),
                reason=m_data.get("reason", "Pico de reacción"),
                virality_score=int(m_data.get("virality_score", 85)),
                event_comment=m_data.get("event_comment", None),
                tags_json=m_data.get("tags", [])
            )
            session.add(moment)
            created_moments.append(moment)

        proj = session.get(Project, project_id)
        if proj:
            proj.status = "ready"
            session.add(proj)
        session.commit()

    if progress_callback:
        progress_callback(100, f"¡Análisis completado! Se encontraron {len(created_moments)} momentos virales.")

    return {
        "project_id": project_id,
        "moments_count": len(created_moments),
        "top_virality": max([m.virality_score for m in created_moments]) if created_moments else 0
    }

async def render_single_clip_job(job_id: str, clip_id: str, progress_callback=None) -> Dict[str, Any]:
    """Renders a single approved clip: downloads slice, builds animated subs, encodes 9:16 vertical video."""
    with Session(engine) as session:
        clip = session.get(Clip, clip_id)
        if not clip:
            raise ValueError(f"Clip {clip_id} no existe")
        proj = session.get(Project, clip.project_id)
        if not proj:
            raise ValueError(f"Proyecto {clip.project_id} no existe")
        
        url = proj.source_url
        start_sec = clip.start_sec
        end_sec = clip.end_sec
        layout = clip.layout
        sub_style = clip.subtitle_style
        hook_text = clip.hook_text or clip.title
        event_comment = clip.event_comment or ""

    if progress_callback:
        progress_callback(15, "Descargando sección exacta del video...")

    # Download section
    slice_filename = f"slice_{clip_id[:8]}.mp4"
    slice_path = ingester.download_clip_section(url, start_sec, end_sec, slice_filename)

    if progress_callback:
        progress_callback(50, "Generando subtítulos dinámicos y estilos visuales...")

    # Generate word timings (using duration interpolation or TTS alignment)
    duration = max(1.0, end_sec - start_sec)
    sample_words = []
    # If hook text exists, split it for subtitles
    tokens = (hook_text + " " + (clip.title if clip.title != hook_text else "")).strip().split()
    if tokens:
        w_dur = min(1.2, duration / len(tokens))
        for i, t in enumerate(tokens):
            w_s = round(i * w_dur, 2)
            w_e = round(w_s + w_dur, 2)
            sample_words.append({"word": t, "start_sec": w_s, "end_sec": w_e})

    ass_path = str(MEDIA_DIR / f"subs_{clip_id[:8]}.ass")
    generate_ass_file(sample_words, ass_path, style_name=sub_style, title_hook=hook_text, event_comment=event_comment)

    if progress_callback:
        progress_callback(75, "Codificando video vertical 9:16 con aceleración de hardware...")

    out_mp4 = f"clip_{clip_id[:8]}_vertical.mp4"
    render_res = render_vertical_clip(
        source_video_path=slice_path,
        output_filename=out_mp4,
        layout=layout,
        start_sec=0.0,
        end_sec=duration,
        ass_subtitle_path=ass_path
    )

    with Session(engine) as session:
        clip = session.get(Clip, clip_id)
        if clip:
            clip.status = "ready"
            clip.output_path = render_res["output_path"]
            clip.thumbnail_path = render_res["thumbnail_path"]
            session.add(clip)
            session.commit()

    if progress_callback:
        progress_callback(100, "¡Clip renderizado exitosamente y listo para publicar!")

    return render_res
