import os
import uuid
import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from sqlmodel import Session, select

from app.db import engine
from app.models import Project, Moment, Clip, Transcript
from app.config import MEDIA_DIR, CACHE_DIR, RENDERS_DIR, FFMPEG_PATH
from ingest import ingester, analyze_audio_peaks, scan_kick_chat_peaks
from pulpo import pulpo
from render import generate_ass_file, render_vertical_clip, extract_frame_jpeg, render_pill_overlay_png
from clipper.transcriber import transcribe_clip_words, polish_words_with_pulpo
from clipper.face_tracker import analyze_speakers_and_motion


def _probe_local_duration(video_path: str) -> float:
    try:
        ffprobe = str(Path(FFMPEG_PATH).parent / "ffprobe.exe")
        if not Path(ffprobe).exists():
            ffprobe = "ffprobe"
        out = subprocess.check_output(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            text=True,
            timeout=15,
        )
        return float(out.strip())
    except Exception:
        return 60.0


async def process_project_pipeline(job_id: str, project_id: str, progress_callback=None) -> Dict[str, Any]:
    """Zero-Bloat Stream Hunter: analyzes 1-min videos AND 8-10h VODs without downloading gigabytes."""
    with Session(engine) as session:
        proj = session.get(Project, project_id)
        if not proj:
            raise ValueError(f"Proyecto {project_id} no encontrado")
        url = proj.source_url
        title = proj.title
        source_type = proj.source_type
        local_video = proj.video_path

    try:
        if source_type == "file" and local_video and Path(local_video).exists():
            if progress_callback:
                progress_callback(15, "Analizando video local...")
            dur_sec = await asyncio.to_thread(_probe_local_duration, local_video)
            info = {
                "title": title,
                "duration_sec": dur_sec,
                "streamer": "Archivo Local",
                "platform": "file",
                "low_stream_url": local_video,
                "heatmap": [],
                "subs_url": None,
            }
        else:
            if progress_callback:
                progress_callback(10, "Consultando metadatos, duración y streams disponibles (0 MB descargados)...")
            info = await asyncio.to_thread(ingester.extract_info, url)

        dur_sec = float(info.get("duration_sec") or 0.0)
        heatmap = info.get("heatmap") or []
        low_stream_url = info.get("low_stream_url")
        subs_url = info.get("subs_url")
        platform = info.get("platform", source_type)

        with Session(engine) as session:
            proj = session.get(Project, project_id)
            if proj:
                if proj.title in ("Nueva Transmisión", "", None) or source_type != "file":
                    proj.title = info.get("title") or title
                proj.duration_sec = dur_sec
                proj.status = "analyzing"
                session.add(proj)
                session.commit()

        # --- Signal Discovery Phase (Find candidate 90s windows across 0..10h) ---
        candidate_windows: List[Dict[str, Any]] = []

        # 1. Kick VOD Chat Burst Radar (~3.5s for 10h stream!)
        if "kick" in platform and info.get("channel_id") and info.get("timestamp") and dur_sec > 180:
            if progress_callback:
                progress_callback(22, f"Escaneando chat del stream ({dur_sec/3600:.1f}h) para localizar explosiones virales...")
            peaks = await scan_kick_chat_peaks(
                channel_id=str(info["channel_id"]),
                start_timestamp=float(info["timestamp"]),
                duration_sec=dur_sec,
                num_probes=36,
                top_k=7,
                min_gap_sec=180.0,
            )
            for p in peaks:
                w_start = max(0.0, p["time_sec"] - 45.0)
                w_dur = min(90.0, max(30.0, dur_sec - w_start))
                candidate_windows.append({
                    "start_sec": w_start,
                    "dur_sec": w_dur,
                    "chat_sample": f"({p['count']} msgs en {p['span_sec']}s) {p['sample']}",
                    "radar_score": p["score"],
                })

        # 2. YouTube Retention Heatmap (0 MB downloaded!)
        if not candidate_windows and heatmap:
            if progress_callback:
                progress_callback(25, "Analizando curva de retención 'Más repetidos' de YouTube...")
            sorted_hm = sorted(heatmap, key=lambda x: x.get("value", 0), reverse=True)
            picked: List[float] = []
            for pt in sorted_hm:
                t = float(pt.get("start_time", 0.0))
                if all(abs(t - old) >= 120.0 for old in picked):
                    picked.append(t)
                    w_start = max(0.0, t - 35.0)
                    w_dur = min(90.0, max(30.0, dur_sec - w_start))
                    candidate_windows.append({
                        "start_sec": w_start,
                        "dur_sec": w_dur,
                        "chat_sample": f"Pico de repetición de audiencia: {round(pt.get('value', 0)*100)}%",
                        "radar_score": round(pt.get("value", 0) * 100),
                    })
                if len(candidate_windows) >= 7:
                    break

        # 3. YouTube Auto-Captions fast text path (great for podcasts/talks on YouTube)
        moments_from_captions: List[Dict[str, Any]] = []
        if not candidate_windows and subs_url:
            if progress_callback:
                progress_callback(30, "Leyendo transcripción directa de YouTube...")
            segs = await asyncio.to_thread(ingester.fetch_youtube_transcript_segments, subs_url)
            if segs:
                lines = [f"[{s['start']:.0f}s] {s['text']}" for s in segs[:500]]
                full_text = "\n".join(lines)
                with Session(engine) as session:
                    session.add(Transcript(project_id=project_id, full_text=full_text[:50000], segments_json=segs[:500]))
                    session.commit()
                if progress_callback:
                    progress_callback(60, "El Pulpo IA está detectando los mejores momentos en la transcripción...")
                moments_from_captions = await pulpo.run("find_moments", {
                    "transcript": full_text,
                    "signals": {"duration_sec": dur_sec, "source": "youtube_captions"},
                    "streamer": info.get("streamer", "Creador"),
                })

        # 4. Distributed Window Sampling (works on ANY platform: Twitch, short videos, Kick fallback, local files)
        if not candidate_windows and not moments_from_captions:
            if dur_sec <= 480:
                # Short video (<8 min): slice sequentially into up to 4 windows covering the whole video
                if progress_callback:
                    progress_callback(28, "Preparando ventanas de audio del video...")
                step = 110.0
                t = 0.0
                while t < max(1.0, dur_sec - 10.0) and len(candidate_windows) < 4:
                    w_dur = min(115.0, dur_sec - t)
                    candidate_windows.append({
                        "start_sec": t,
                        "dur_sec": w_dur,
                        "chat_sample": "Video completo",
                        "radar_score": 80,
                    })
                    t += step
            else:
                # Long stream (>8 min up to 10h) without heatmap/Kick chat: sample 7 spaced 90s windows
                if progress_callback:
                    progress_callback(28, f"Muestreando {dur_sec/3600:.1f}h de transmisión por streaming directo...")
                n_samples = 7
                usable_start = min(180.0, dur_sec * 0.05)
                usable_end = max(usable_start + 90.0, dur_sec - 120.0)
                step = (usable_end - usable_start) / n_samples
                for i in range(n_samples):
                    w_start = usable_start + i * step
                    candidate_windows.append({
                        "start_sec": w_start,
                        "dur_sec": min(90.0, dur_sec - w_start),
                        "chat_sample": f"Muestra estratégica #{i+1}",
                        "radar_score": 70,
                    })

        # --- Multimodal Audio Listening Phase ---
        discovered_moments: List[Dict[str, Any]] = []
        heard_transcripts: List[str] = []

        if candidate_windows:
            total_w = len(candidate_windows)
            for idx, win in enumerate(candidate_windows):
                pct = 35 + int((idx / total_w) * 55)
                h, m = divmod(int(win["start_sec"] // 60), 60)
                if progress_callback:
                    progress_callback(pct, f"Escuchando segmento {idx+1}/{total_w} (@{h:02d}h{m:02d}m) con El Pulpo IA...")

                slice_audio = str(CACHE_DIR / f"probe_{project_id[:8]}_{idx}.m4a")
                try:
                    await asyncio.to_thread(
                        ingester.extract_audio_slice,
                        low_stream_url,
                        win["start_sec"],
                        win["dur_sec"],
                        slice_audio,
                        url if source_type != "file" else None,
                    )
                    res = await pulpo.run("analyze_audio_window", {
                        "audio_path": slice_audio,
                        "window_start_sec": win["start_sec"],
                        "window_dur_sec": win["dur_sec"],
                        "streamer": info.get("streamer", "Streamer"),
                        "stream_title": info.get("title", title),
                        "chat_sample": win["chat_sample"],
                    })
                    if res:
                        off_s = float(res.get("start_offset_sec", 10.0))
                        off_e = float(res.get("end_offset_sec", off_s + 45.0))
                        off_s = max(0.0, min(win["dur_sec"] - 15.0, off_s))
                        off_e = max(off_s + 15.0, min(win["dur_sec"], off_e))
                        g_start = round(win["start_sec"] + off_s, 2)
                        g_end = round(win["start_sec"] + off_e, 2)

                        summary = res.get("transcript_summary", "")
                        if summary:
                            heard_transcripts.append(f"[{h:02d}:{m:02d}] {summary}")

                        discovered_moments.append({
                            "start_sec": g_start,
                            "end_sec": g_end,
                            "hook": res.get("hook", "MIRA ESTO"),
                            "title": res.get("title", "Momento del Stream"),
                            "reason": res.get("reason", summary or "Momento destacado en vivo"),
                            "virality_score": int(res.get("virality_score", 78)),
                            "event_comment": res.get("event_comment"),
                            "tags": res.get("tags", []),
                        })
                except Exception as win_err:
                    print(f"[PIPELINE] Ventana {idx} falló ({win['start_sec']}s): {win_err}")
                finally:
                    if Path(slice_audio).exists():
                        try:
                            Path(slice_audio).unlink()
                        except Exception:
                            pass
        elif moments_from_captions:
            discovered_moments = moments_from_captions

        # Persist Moments & Transcript into SQLite
        saved_count = 0
        top_score = 0
        with Session(engine) as session:
            prev_moments = session.exec(select(Moment).where(Moment.project_id == project_id)).all()
            for pm in prev_moments:
                session.delete(pm)

            if heard_transcripts:
                session.add(Transcript(
                    project_id=project_id,
                    full_text="\n".join(heard_transcripts),
                    segments_json=[],
                ))

            for m_data in discovered_moments:
                s_sec = max(0.0, float(m_data.get("start_sec", 0.0)))
                e_sec = float(m_data.get("end_sec", s_sec + 35.0))
                if e_sec <= s_sec:
                    e_sec = s_sec + 35.0
                score = max(1, min(99, int(m_data.get("virality_score", 78))))
                top_score = max(top_score, score)

                moment = Moment(
                    project_id=project_id,
                    start_sec=s_sec,
                    end_sec=e_sec,
                    duration_sec=round(e_sec - s_sec, 2),
                    hook=str(m_data.get("hook", "MIRA ESTO"))[:120],
                    title=str(m_data.get("title", "Momento Viral"))[:120],
                    reason=str(m_data.get("reason", "Momento destacado")),
                    virality_score=score,
                    event_comment=m_data.get("event_comment"),
                    tags_json=m_data.get("tags", []),
                )
                session.add(moment)
                saved_count += 1

            proj = session.get(Project, project_id)
            if proj:
                proj.status = "ready"
                proj.error_message = None
                session.add(proj)
            session.commit()

        if saved_count == 0:
            raise RuntimeError("No se pudieron extraer momentos analizables de este enlace. Verifica que el VOD sea público.")

        if progress_callback:
            progress_callback(100, f"¡Listo! {saved_count} momentos reales extraídos del stream.")

        return {
            "project_id": project_id,
            "moments_count": saved_count,
            "top_virality": top_score,
            "duration_hours": round(dur_sec / 3600, 2),
        }

    except Exception as e:
        with Session(engine) as session:
            proj = session.get(Project, project_id)
            if proj:
                proj.status = "error"
                proj.error_message = str(e)
                session.add(proj)
                session.commit()
        raise


async def render_single_clip_job(job_id: str, clip_id: str, progress_callback=None) -> Dict[str, Any]:
    """Renders a 1080x1920 clip: surgical 1080p slice -> Vision webcam detect -> Whisper real words -> AMF encode."""
    with Session(engine) as session:
        clip = session.get(Clip, clip_id)
        if not clip:
            raise ValueError(f"Clip {clip_id} no existe")
        proj = session.get(Project, clip.project_id)
        if not proj:
            raise ValueError(f"Proyecto {clip.project_id} no existe")

        clip.status = "rendering"
        session.add(clip)
        session.commit()

        url = proj.source_url
        source_type = proj.source_type
        local_video = proj.video_path
        start_sec = float(clip.start_sec)
        end_sec = float(clip.end_sec)
        layout = clip.layout
        content_mode = getattr(clip, "content_mode", "auto") or "auto"
        hook_persistence = getattr(clip, "hook_persistence", "intro") or "intro"
        show_subtitles = getattr(clip, "show_subtitles", True)
        video_transitions = getattr(clip, "video_transitions", True)
        sub_style = clip.subtitle_style
        hook_text = clip.hook_text or clip.title
        event_comment = clip.event_comment or ""

    duration = max(5.0, end_sec - start_sec)
    slice_path = None
    temp_slice_created = False
    frame_jpg = str(CACHE_DIR / f"frame_{clip_id[:8]}.jpg")
    ass_path = str(CACHE_DIR / f"subs_{clip_id[:8]}.ass")
    hook_png_path = str(CACHE_DIR / f"hook_{clip_id[:8]}.png")
    card_png_path = str(CACHE_DIR / f"card_{clip_id[:8]}.png")
    stream_title = proj.title or ""

    try:
        if source_type == "file" and local_video and Path(local_video).exists():
            if progress_callback:
                progress_callback(15, f"Cortando segmento de {round(duration)}s del archivo local...")
            slice_path = str(MEDIA_DIR / f"slice_{clip_id[:8]}.mp4")
            cmd = [
                FFMPEG_PATH, "-y", "-hide_banner", "-loglevel", "error",
                "-ss", str(round(start_sec, 2)), "-t", str(round(duration, 2)),
                "-i", local_video, "-c", "copy", slice_path
            ]
            await asyncio.to_thread(subprocess.run, cmd, check=True)
            temp_slice_created = True
        else:
            if progress_callback:
                progress_callback(12, "Resolviendo URL HD del fragmento...")
            info = await asyncio.to_thread(ingester.extract_info, url)
            hq_url = info.get("hq_muxed_url")

            if progress_callback:
                progress_callback(25, f"Descargando únicamente el clip de {round(duration)}s en HD...")
            slice_filename = f"slice_{clip_id[:8]}.mp4"
            slice_path = await asyncio.to_thread(
                ingester.download_clip_section, url, start_sec, end_sec, slice_filename, hq_url
            )
            temp_slice_created = True

        # 2. Gemini Vision scene classification + OpenCV YuNet active-speaker tracking
        if progress_callback:
            progress_callback(40, "Analizando rostros, acción y seguimiento de cámara...")
        webcam_box = None
        roi_box = None
        vision = {}
        extracted_jpg = await asyncio.to_thread(extract_frame_jpeg, slice_path, frame_jpg, min(2.0, duration / 2))
        if extracted_jpg:
            vision = await pulpo.run("detect_facecam", {"image_path": extracted_jpg})
            webcam_box = vision.get("webcam_box")
            roi_box = vision.get("roi_box")

        track_data = await asyncio.to_thread(analyze_speakers_and_motion, slice_path, 3.0)
        speakers = track_data.get("speakers", [])
        timeline_segments = track_data.get("timeline_segments", [])

        # Resolve intelligent layout factoring content_mode (gaming_gta, podcast, etc.)
        if layout in ("auto", "", None):
            if content_mode == "gaming_gta":
                layout = "split_screen" if (vision.get("has_facecam") and webcam_box) else "gaming_zoom"
            elif content_mode == "podcast":
                if len(speakers) >= 2 and not vision.get("has_important_bottom_graphic"):
                    layout = "duo_split"
                elif len(speakers) >= 2:
                    layout = "speaker_focus"
                elif len(speakers) == 1:
                    layout = "centered_face"
                else:
                    layout = "blur_bg"
            elif vision.get("has_important_bottom_graphic") and len(speakers) >= 2:
                layout = "speaker_focus"
            elif vision.get("scene_type") == "two_person_split" and len(speakers) >= 2:
                layout = "duo_split"
            elif vision.get("has_facecam") and vision.get("scene_type") == "facecam_gameplay":
                layout = "split_screen"
            elif vision.get("scene_type") == "gaming_action":
                layout = "gaming_zoom"
            elif len(speakers) >= 2 and vision.get("scene_type") == "multi_panel":
                layout = "speaker_focus"
            else:
                layout = vision.get("layout_recommended") or track_data.get("recommended_layout") or "blur_bg"
        elif layout == "split_screen" and vision.get("has_facecam") is False:
            if len(speakers) == 2 and not vision.get("has_important_bottom_graphic"):
                layout = "duo_split"
            elif len(speakers) >= 2:
                layout = "speaker_focus"
            else:
                layout = vision.get("layout_recommended", "blur_bg")

        # 3. Whisper base transcription + Gemini LATAM slang polishing (only when subtitles enabled)
        words = []
        ass_arg = None
        if show_subtitles:
            if progress_callback:
                progress_callback(56, "Transcribiendo audio con Whisper Base y corrigiendo jerga...")
            words = await asyncio.to_thread(transcribe_clip_words, slice_path, "es")
            if words:
                words = await polish_words_with_pulpo(words, context=f"{stream_title} | {clip.title}")
            else:
                words = [{"word": w, "start_sec": round(i * 0.4, 2), "end_sec": round((i + 1) * 0.4, 2)} for i, w in enumerate(hook_text.split()[:6])]

            # Place subtitles cleanly in safe zone depending on layout
            margin_v = 920 if layout in ("duo_split", "speaker_focus") else (340 if layout == "centered_face" else 420)
            await asyncio.to_thread(
                generate_ass_file, words, ass_path, style_name=sub_style, margin_v_override=margin_v
            )
            ass_arg = ass_path

        # 4. Graphic PNG overlays with full-color emojis & hook_persistence support
        title_y = 125 if layout in ("duo_split", "speaker_focus") else 195
        hook_png = None
        if hook_persistence != "off":
            hook_png = await asyncio.to_thread(
                render_pill_overlay_png, hook_text, hook_png_path, y_center=title_y, font_size=44
            )
        card_png = None
        if event_comment and event_comment.strip() and event_comment.strip().lower() != hook_text.strip().lower():
            card_y = (title_y + 150) if (hook_persistence == "always" and hook_png) else title_y
            card_png = await asyncio.to_thread(
                render_pill_overlay_png, event_comment, card_png_path, y_center=card_y, font_size=36,
                bg_rgba=(20, 36, 43, 230), border_rgba=(255, 255, 255, 80)
            )

        # 5. Hardware-accelerated render + transitions + subtle SFX
        if progress_callback:
            progress_callback(78, f"Renderizando 9:16 ({layout}) con transiciones y SFX...")
        out_mp4 = f"clip_{clip_id[:8]}_vertical.mp4"
        render_res = await asyncio.to_thread(
            render_vertical_clip,
            slice_path,
            out_mp4,
            layout,
            0.0,
            duration,
            ass_arg,
            webcam_box,
            speakers,
            timeline_segments,
            hook_png,
            card_png,
            True,
            hook_persistence,
            video_transitions,
            roi_box,
        )

        with Session(engine) as session:
            clip = session.get(Clip, clip_id)
            if clip:
                clip.status = "ready"
                clip.layout = layout
                clip.output_path = render_res["output_path"]
                clip.thumbnail_path = render_res["thumbnail_path"]
                clip.error_message = None
                session.add(clip)
                session.commit()

        if progress_callback:
            progress_callback(100, "¡Clip vertical 9:16 renderizado y listo para publicar!")

        return {
            **render_res,
            "video_url": f"/renders/{out_mp4}",
            "words_transcribed": len(words),
        }

    except Exception as e:
        with Session(engine) as session:
            clip = session.get(Clip, clip_id)
            if clip:
                clip.status = "failed"
                clip.error_message = str(e)
                session.add(clip)
                session.commit()
        raise
    finally:
        for tmp in [frame_jpg, ass_path, hook_png_path, card_png_path]:
            if tmp and Path(tmp).exists():
                try:
                    Path(tmp).unlink()
                except Exception:
                    pass
        if temp_slice_created and slice_path and Path(slice_path).exists():
            try:
                Path(slice_path).unlink()
            except Exception:
                pass
