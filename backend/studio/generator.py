import asyncio
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List

from sqlmodel import Session

from app.config import BASE_DIR, CACHE_DIR, FFMPEG_PATH, MEDIA_DIR, RENDERS_DIR
from app.db import engine
from app.models import StudioVideo
from pulpo.tts import VOICES, generate_speech_with_timestamps
from render.subtitles import generate_ass_file
from studio.director import enhance_studio_storyboard
from studio.media_fetcher import prefetch_storyboard_media
from studio.stage_renderer import (
    export_studio_stage_project,
    render_html_stage_to_mp4,
)

SFX_DIR = BASE_DIR / "assets" / "sfx"
FALLBACK_VOICES = list(VOICES.keys())


def _probe_audio_duration(path: str, fallback: float = 3.0) -> float:
    try:
        ffprobe = str(Path(FFMPEG_PATH).parent / "ffprobe.exe")
        if not Path(ffprobe).exists():
            ffprobe = "ffprobe"
        out = subprocess.check_output(
            [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            text=True,
            timeout=10,
        )
        return max(0.6, float(out.strip()))
    except Exception:
        return fallback


async def render_studio_video_job(job_id: str, studio_id: str, progress_callback=None) -> Dict[str, Any]:
    """Directs beat-by-beat storyboard, fetches real B-Roll + Lottie, mixes multi-voice + ambient BGM, and renders 1080x1920 MP4."""
    with Session(engine) as session:
        sv = session.get(StudioVideo, studio_id)
        if not sv:
            raise ValueError(f"StudioVideo {studio_id} no encontrado")
        script = sv.script_json or {}
        scene_plan = sv.scene_plan_json or []
        default_voice = sv.voice_name
        title = sv.title
        topic = sv.topic or sv.title
        style = sv.style or "drama"

    if progress_callback:
        progress_callback(10, "Coreografiando guion visual beat-a-beat (B-Roll, Lottie & Motion Graphics)...")

    storyboard = await enhance_studio_storyboard(
        topic=topic,
        style=style,
        title=title,
        script_json=script,
        scene_plan_json=scene_plan,
        default_voice=default_voice,
    )
    characters = storyboard["characters"]
    beats = storyboard["beats"]
    final_title = storyboard.get("title") or title

    if progress_callback:
        progress_callback(18, f"Sintetizando {len(characters)} voces neuronales y descargando B-Roll para {len(beats)} beats...")

    # Flatten dialogue turns across all beats for concurrent Edge-TTS generation
    turn_jobs = []
    for b_idx, beat in enumerate(beats):
        dlgs = beat.get("dialogues") or []
        if not dlgs:
            dlgs = [{
                "speaker_id": characters[0]["id"],
                "speaker_name": characters[0]["name"],
                "archetype": characters[0].get("archetype", "analyst"),
                "accent_color": characters[0].get("accent_color", "#2BF0C8"),
                "voice": characters[0]["voice"],
                "text": beat.get("headline") or final_title,
            }]
            beat["dialogues"] = dlgs
        for t_idx, dlg in enumerate(dlgs):
            turn_jobs.append((b_idx, t_idx, dlg))

    tts_sem = asyncio.Semaphore(3)
    temp_audio_files: List[str] = []

    async def _gen_turn(b_idx: int, t_idx: int, dlg: Dict[str, Any]):
        fname = f"studio_{studio_id[:8]}_b{b_idx}_t{t_idx}_{uuid.uuid4().hex[:4]}.mp3"
        voice = dlg.get("voice") if dlg.get("voice") in VOICES else FALLBACK_VOICES[0]
        async with tts_sem:
            res = await generate_speech_with_timestamps(dlg["text"], voice=voice, output_filename=fname)
        dur = float(res.get("duration_sec") or 0.0)
        probed = _probe_audio_duration(res["audio_path"], fallback=max(1.4, len(dlg["text"].split()) * 0.42))
        dur = max(dur, probed)
        temp_audio_files.append(res["audio_path"])
        return b_idx, t_idx, dlg, res, dur

    tts_task = asyncio.gather(*[_gen_turn(bi, ti, d) for bi, ti, d in turn_jobs])
    media_task = asyncio.to_thread(prefetch_storyboard_media, beats, topic, style)
    tts_results, beat_media = await asyncio.gather(tts_task, media_task)
    tts_map = {(bi, ti): (dlg, res, dur) for bi, ti, dlg, res, dur in tts_results}

    # Assemble precise cumulative beat & dialogue timeline
    cur_t = 0.22
    all_words: List[Dict[str, Any]] = []
    dialogue_timeline: List[Dict[str, Any]] = []
    beat_transitions: List[float] = []
    pop_cues: List[float] = []
    mix_entries: List[tuple[str, float]] = []

    for b_idx, beat in enumerate(beats):
        b_start = round(cur_t, 3)
        if b_idx > 0:
            beat_transitions.append(b_start)
        if beat.get("beat_type") in ("chat_reveal", "kinetic_stat", "data_chart", "code_diff", "terminal_run"):
            pop_cues.append(b_start + 0.12)

        for t_idx in range(len(beat["dialogues"])):
            dlg, res, turn_dur = tts_map[(b_idx, t_idx)]
            t_start = round(cur_t, 3)
            t_end = round(t_start + turn_dur, 3)
            mix_entries.append((res["audio_path"], t_start))
            dialogue_timeline.append({
                "beat_idx": b_idx,
                "speaker_id": dlg["speaker_id"],
                "speaker_name": dlg["speaker_name"],
                "archetype": dlg.get("archetype", "analyst"),
                "accent_color": dlg.get("accent_color", "#2BF0C8"),
                "text": dlg["text"],
                "start_sec": t_start,
                "end_sec": t_end,
            })
            for wb in res.get("word_boundaries") or []:
                all_words.append({
                    "word": wb["word"],
                    "start_sec": round(t_start + float(wb["start_sec"]), 3),
                    "end_sec": round(t_start + float(wb["end_sec"]), 3),
                })
            cur_t = t_end + 0.14

        cur_t += 0.22
        beat["start_sec"] = b_start
        beat["end_sec"] = round(cur_t, 3)
        beat["duration_sec"] = round(max(1.8, cur_t - b_start), 3)

    total_duration = round(max(5.0, cur_t + 0.45), 2)

    if progress_callback:
        progress_callback(40, "Mezclando voces, música ambiental lo-fi, efectos SFX y subtítulos...")

    master_audio = str(MEDIA_DIR / f"studio_mix_{studio_id[:8]}.m4a")
    ass_path = str(CACHE_DIR / f"studio_{studio_id[:8]}.ass")
    generate_ass_file(all_words, ass_path, style_name="neon", margin_v_override=280)

    audio_inputs: List[str] = []
    audio_fc: List[str] = []
    mix_labels: List[str] = []
    in_idx = 0

    for ap, delay_s in mix_entries:
        audio_inputs.extend(["-i", str(ap)])
        ms = int(round(delay_s * 1000))
        audio_fc.append(f"[{in_idx}:a]adelay={ms}|{ms},volume=1.08[v{in_idx}]")
        mix_labels.append(f"[v{in_idx}]")
        in_idx += 1

    whoosh_wav = SFX_DIR / "whoosh_light.wav"
    if beat_transitions and whoosh_wav.exists():
        for ts in beat_transitions:
            audio_inputs.extend(["-i", str(whoosh_wav)])
            ms = int(round(max(0.0, ts - 0.08) * 1000))
            audio_fc.append(f"[{in_idx}:a]adelay={ms}|{ms},volume=0.16[wh{in_idx}]")
            mix_labels.append(f"[wh{in_idx}]")
            in_idx += 1

    pop_wav = SFX_DIR / "pop_soft.wav"
    if pop_cues and pop_wav.exists():
        for ts in pop_cues:
            audio_inputs.extend(["-i", str(pop_wav)])
            ms = int(round(max(0.0, ts) * 1000))
            audio_fc.append(f"[{in_idx}:a]adelay={ms}|{ms},volume=0.18[pp{in_idx}]")
            mix_labels.append(f"[pp{in_idx}]")
            in_idx += 1

    bgm_wav = SFX_DIR / "bgm_ambient.wav"
    if bgm_wav.exists():
        audio_inputs.extend(["-stream_loop", "-1", "-i", str(bgm_wav)])
        fade_out_st = max(0.5, total_duration - 0.9)
        audio_fc.append(
            f"[{in_idx}:a]atrim=0:{total_duration:.2f},afade=t=in:st=0:d=0.6,"
            f"afade=t=out:st={fade_out_st:.2f}:d=0.9,volume=0.10[bgm_bed]"
        )
        mix_labels.append("[bgm_bed]")
        in_idx += 1
    else:
        audio_fc.append(f"anullsrc=r=44100:cl=mono:d={total_duration:.2f}[sil_bed]")
        mix_labels.append("[sil_bed]")

    audio_fc.append(
        f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=longest:normalize=0,"
        f"atrim=0:{total_duration:.2f}[outa]"
    )
    mix_cmd = [
        FFMPEG_PATH, "-y", "-hide_banner", "-loglevel", "error",
        *audio_inputs,
        "-filter_complex", ";".join(audio_fc),
        "-map", "[outa]",
        "-c:a", "aac", "-b:a", "160k",
        master_audio,
    ]
    await asyncio.to_thread(
        subprocess.run, mix_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90
    )

    if progress_callback:
        progress_callback(50, "Ensamblando escenario HyperFrames + Lottie + B-Roll en HTML5...")

    hf_dir = export_studio_stage_project(
        studio_id=studio_id,
        title=final_title,
        characters=characters,
        beats=beats,
        dialogue_timeline=dialogue_timeline,
        beat_media=beat_media,
        total_dur=total_duration,
        audio_src_path=master_audio,
    )
    stage_html_path = str(Path(hf_dir) / "index.html")

    out_mp4 = RENDERS_DIR / f"studio_{studio_id[:8]}.mp4"
    try:
        await asyncio.to_thread(
            render_html_stage_to_mp4,
            stage_html_path,
            master_audio,
            ass_path,
            str(out_mp4),
            total_duration,
            20,
            progress_callback,
        )
    finally:
        for tp in temp_audio_files:
            if tp and Path(tp).exists():
                try:
                    Path(tp).unlink()
                except Exception:
                    pass

    with Session(engine) as session:
        sv = session.get(StudioVideo, studio_id)
        if sv:
            sv.status = "rendered"
            sv.audio_path = master_audio
            sv.output_path = str(out_mp4)
            session.add(sv)
            session.commit()

    if progress_callback:
        progress_callback(100, "¡Video Motion Graphics con B-Roll, Lottie y múltiples beats listo!")

    media_sources = sorted({v.get("source", "none") for v in beat_media.values() if v.get("source") != "none"})
    return {
        "output_path": str(out_mp4),
        "video_url": f"/renders/{out_mp4.name}",
        "hf_project_dir": hf_dir,
        "beats_rendered": len(beats),
        "scenes_rendered": len(beats),
        "characters_count": len(characters),
        "media_sources": media_sources,
    }
