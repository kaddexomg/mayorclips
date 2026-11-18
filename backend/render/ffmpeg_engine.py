import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from app.config import FFMPEG_PATH, RENDERS_DIR, BASE_DIR

SFX_DIR = BASE_DIR / "assets" / "sfx"
LIBX264_FALLBACK_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def get_best_h264_encoder() -> tuple[str, list[str]]:
    """Returns hardware AMD AMF encoder args with balanced mobile bitrate if available, else libx264."""
    try:
        res = subprocess.run([FFMPEG_PATH, "-hide_banner", "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if "h264_amf" in res.stdout:
            return "h264_amf", ["-c:v", "h264_amf", "-quality", "balanced", "-b:v", "6000k", "-maxrate", "8000k", "-bufsize", "10000k"]
    except Exception:
        pass
    return "libx264", list(LIBX264_FALLBACK_ARGS)


def extract_frame_jpeg(video_path: str, out_jpg: str, at_sec: float = 2.0) -> Optional[str]:
    cmd = [
        FFMPEG_PATH, "-y", "-hide_banner", "-loglevel", "error",
        "-ss", str(round(at_sec, 2)), "-i", str(video_path),
        "-vframes", "1", "-q:v", "4", str(out_jpg),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if proc.returncode == 0 and Path(out_jpg).exists():
        return str(out_jpg)
    return None


def _has_audio_stream(video_path: str) -> bool:
    try:
        ffprobe = str(Path(FFMPEG_PATH).parent / "ffprobe.exe")
        if not Path(ffprobe).exists():
            ffprobe = "ffprobe"
        out = subprocess.check_output(
            [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(video_path)],
            text=True,
            timeout=10,
        )
        return bool(out.strip())
    except Exception:
        return True


def _clamp_box(box: Optional[Dict[str, float]], default: Dict[str, float]) -> tuple[float, float, float, float]:
    b = box or default
    x = max(0.0, min(0.85, float(b.get("x", default["x"]))))
    y = max(0.0, min(0.85, float(b.get("y", default["y"]))))
    w = max(0.12, min(1.0 - x, float(b.get("w", default["w"]))))
    h = max(0.12, min(1.0 - y, float(b.get("h", default["h"]))))
    return x, y, w, h


def _build_dynamic_crop_expr(segments: List[Dict[str, Any]], coord: str, fallback: float) -> str:
    """Builds a nested FFmpeg if(lt(t,...)) expression for smooth active-speaker camera switching."""
    if not segments or len(segments) == 1:
        val = segments[0]["box"].get(coord, fallback) if segments else fallback
        return f"in_w*{val:.3f}" if coord in ("x", "w") else f"in_h*{val:.3f}"

    dim = "in_w" if coord in ("x", "w") else "in_h"
    expr = f"{dim}*{segments[-1]['box'].get(coord, fallback):.3f}"
    # Build from last segment backwards
    for seg in reversed(segments[:-1]):
        end_t = float(seg["end"])
        val = float(seg["box"].get(coord, fallback))
        expr = f"if(lt(t,{end_t:.2f}),{dim}*{val:.3f},{expr})"
    return expr


def _build_climax_subgraph(
    src_label: str,
    climax_beat: Dict[str, Any],
    at_sec: float,
) -> str:
    """Builds a crisp 1080x1920 centered zoom-punch stream [clm] around focus_box with entry brightness pulse."""
    fx, fy, fw, fh = _clamp_box(climax_beat.get("focus_box"), {"x": 0.20, "y": 0.15, "w": 0.60, "h": 0.70})
    try:
        zoom = max(1.05, min(2.4, float(climax_beat.get("zoom_factor", 1.35))))
    except (TypeError, ValueError):
        zoom = 1.35

    fcx = fx + fw * 0.5
    fcy = fy + fh * 0.5
    cw = max(0.30, min(0.95, fw / zoom))
    ch = max(0.36, min(0.95, fh / zoom))
    cx = max(0.0, min(1.0 - cw, fcx - cw * 0.5))
    cy = max(0.0, min(1.0 - ch, fcy - ch * 0.5))
    flash_end = at_sec + 0.12

    return (
        f"[{src_label}]split=2[clm_fg_s][clm_bg_s];"
        f"[clm_bg_s]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
        f"boxblur=12:2,eq=brightness=-0.12,scale=1080:1920:flags=lanczos,setsar=1[clm_bg];"
        f"[clm_fg_s]crop=w='in_w*{cw:.3f}':h='in_h*{ch:.3f}':x='in_w*{cx:.3f}':y='in_h*{cy:.3f}',"
        f"scale=1080:1320:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1320,"
        f"setsar=1,unsharp=3:3:0.35[clm_fg];"
        f"[clm_bg][clm_fg]overlay=0:300,"
        f"eq=brightness='0.18*between(t,{at_sec:.2f},{flash_end:.2f})':eval=frame[clm]"
    )


def render_vertical_clip(
    source_video_path: str,
    output_filename: str,
    layout: str = "blur_bg",
    start_sec: float = 0.0,
    end_sec: float = 0.0,
    ass_subtitle_path: Optional[str] = None,
    webcam_box: Optional[Dict[str, float]] = None,
    speakers: Optional[List[Dict[str, Any]]] = None,
    timeline_segments: Optional[List[Dict[str, Any]]] = None,
    hook_png_path: Optional[str] = None,
    card_png_path: Optional[str] = None,
    enable_sfx: bool = True,
    hook_persistence: str = "intro",
    video_transitions: bool = True,
    roi_box: Optional[Dict[str, float]] = None,
    climax_beat: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Renders 1080x1920 vertical clip with active speaker tracking, gaming ROI zoom, smooth transitions, climax beat zoom-punch, PNG color-emoji cards, ASS subs, and SFX."""
    output_path = RENDERS_DIR / output_filename
    thumb_path = RENDERS_DIR / f"{Path(output_filename).stem}_thumb.jpg"
    encoder_name, encoder_args = get_best_h264_encoder()

    seek_args = []
    if start_sec > 0:
        seek_args.extend(["-ss", str(round(start_sec, 2))])
    if end_sec > start_sec:
        seek_args.extend(["-t", str(round(end_sec - start_sec, 2))])

    climax_active = False
    climax_at = 0.0
    climax_dur = 0.0
    clip_dur = (end_sec - start_sec) if end_sec > start_sec else 0.0
    if (
        video_transitions
        and isinstance(climax_beat, dict)
        and layout in ("split_screen", "gaming_zoom", "blur_bg")
    ):
        try:
            climax_at = float(climax_beat.get("at_sec", -1.0))
            climax_dur = float(climax_beat.get("duration_sec", 2.0))
        except (TypeError, ValueError):
            climax_at = -1.0
        if climax_at >= 0.0 and climax_dur > 0.1 and clip_dur > climax_at + 2.0:
            climax_dur = min(climax_dur, max(0.25, clip_dur - climax_at - 0.15))
            climax_active = True

    # Inputs list: 0 = video, optional PNGs, optional SFX wavs
    inputs = [*seek_args, "-i", str(source_video_path)]
    idx_counter = 1

    hook_idx = None
    if hook_persistence != "off" and hook_png_path and Path(hook_png_path).exists():
        if hook_persistence == "always":
            hook_dur = max(10.0, (end_sec - start_sec) if end_sec > start_sec else 120.0)
            inputs.extend(["-loop", "1", "-t", f"{hook_dur:.2f}", "-i", str(hook_png_path)])
        else:
            inputs.extend(["-loop", "1", "-t", "5.0", "-i", str(hook_png_path)])
        hook_idx = idx_counter
        idx_counter += 1

    card_start = 0.5 if hook_idx is None else 4.8
    card_end = card_start + 5.2
    card_idx = None
    if card_png_path and Path(card_png_path).exists():
        inputs.extend(["-loop", "1", "-t", f"{card_end + 0.5:.1f}", "-i", str(card_png_path)])
        card_idx = idx_counter
        idx_counter += 1

    pop_wav = SFX_DIR / "pop_soft.wav"
    whoosh_wav = SFX_DIR / "whoosh_light.wav"
    impact_wav = SFX_DIR / "impact_punch.wav"
    riser_wav = SFX_DIR / "riser_whoosh.wav"
    pop_idx = None
    whoosh_idx = None
    impact_idx = None
    riser_idx = None
    if enable_sfx and pop_wav.exists() and (hook_idx is not None or video_transitions):
        inputs.extend(["-i", str(pop_wav)])
        pop_idx = idx_counter
        idx_counter += 1
    if enable_sfx and whoosh_wav.exists() and (card_idx is not None or (video_transitions and layout in ("speaker_focus", "gaming_zoom"))):
        inputs.extend(["-i", str(whoosh_wav)])
        whoosh_idx = idx_counter
        idx_counter += 1
    if enable_sfx and climax_active and impact_wav.exists():
        inputs.extend(["-i", str(impact_wav)])
        impact_idx = idx_counter
        idx_counter += 1
    if enable_sfx and climax_active and climax_at >= 0.35 and riser_wav.exists():
        inputs.extend(["-i", str(riser_wav)])
        riser_idx = idx_counter
        idx_counter += 1

    # Base video layout graph -> outputs [basev] at 1080x1920
    spks = speakers or []
    cut_times: List[float] = []
    fc_parts: List[str] = []
    src_label = "0:v"
    if climax_active:
        fc_parts.append("[0:v]split=2[lsrc][clm_src]")
        src_label = "lsrc"

    if layout == "duo_split" and len(spks) >= 2:
        x1, y1, w1, h1 = _clamp_box(spks[0]["box"], {"x": 0.05, "y": 0.05, "w": 0.4, "h": 0.7})
        x2, y2, w2, h2 = _clamp_box(spks[1]["box"], {"x": 0.55, "y": 0.05, "w": 0.4, "h": 0.7})
        layout_graph = (
            f"[{src_label}]split=2[s1][s2];"
            f"[s1]crop=in_w*{w1:.3f}:in_h*{h1:.3f}:in_w*{x1:.3f}:in_h*{y1:.3f},scale=1080:958:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:958,setsar=1,unsharp=3:3:0.35[top];"
            f"[s2]crop=in_w*{w2:.3f}:in_h*{h2:.3f}:in_w*{x2:.3f}:in_h*{y2:.3f},scale=1080:958:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:958,setsar=1,unsharp=3:3:0.35[bot];"
            f"[top]pad=1080:962:0:0:#060B10[top_pad];"
            f"[top_pad][bot]vstack=inputs=2[basev]"
        )
    elif layout == "speaker_focus" and (timeline_segments or len(spks) >= 1):
        segs = timeline_segments[:12] if timeline_segments else [{"start": 0.0, "end": 999.0, "box": spks[0]["box"]}]
        avg_w = max(0.18, min(0.85, sum(s["box"]["w"] for s in segs) / len(segs)))
        avg_h = max(0.20, min(0.85, sum(s["box"]["h"] for s in segs) / len(segs)))
        x_expr = _build_dynamic_crop_expr(segs, "x", 0.25)
        y_expr = _build_dynamic_crop_expr(segs, "y", 0.05)
        cut_times = [float(s["end"]) for s in segs[:-1] if 0.8 < float(s["end"]) < 55.0][:3]
        cut_pulse = ""
        if video_transitions and cut_times:
            terms = "+".join([f"between(t,{ct:.2f},{ct + 0.14:.2f})" for ct in cut_times])
            cut_pulse = f",eq=brightness='0.11*({terms})':eval=frame"
        layout_graph = (
            f"[{src_label}]split=2[spk][scr];"
            f"[spk]crop=w='in_w*{avg_w:.3f}':h='in_h*{avg_h:.3f}':x='{x_expr}':y='{y_expr}',scale=1080:960:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:960,setsar=1,unsharp=3:3:0.35{cut_pulse}[top];"
            f"[scr]scale=1080:960:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:960,setsar=1[bot];"
            f"[top][bot]vstack=inputs=2[basev]"
        )
    elif layout == "gaming_zoom":
        rx, ry, rw, rh = _clamp_box(roi_box, {"x": 0.14, "y": 0.08, "w": 0.72, "h": 0.82})
        # Maintain constant crop dimensions centered on the GTA/gameplay ROI; gently pan if transitions enabled
        cw = max(0.42, min(0.88, rw))
        ch = max(0.48, min(0.92, rh))
        cx_base = max(0.0, min(1.0 - cw, rx + (rw - cw) * 0.5))
        cy_base = max(0.0, min(1.0 - ch, ry + (rh - ch) * 0.5))
        if video_transitions:
            pan_x = f"max(0,min(in_w*(1-{cw:.3f}),in_w*({cx_base:.3f}+0.03*sin(t*0.7))))"
            pan_y = f"max(0,min(in_h*(1-{ch:.3f}),in_h*({cy_base:.3f}+0.015*cos(t*0.5))))"
        else:
            pan_x = f"in_w*{cx_base:.3f}"
            pan_y = f"in_h*{cy_base:.3f}"
        layout_graph = (
            f"[{src_label}]split=2[fg][bg];"
            f"[bg]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=10:2,scale=1080:1920:flags=lanczos,setsar=1[bg_blur];"
            f"[fg]crop=w='in_w*{cw:.3f}':h='in_h*{ch:.3f}':x='{pan_x}':y='{pan_y}',scale=1080:1220:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1220,setsar=1[fg_roi];"
            f"[bg_blur][fg_roi]overlay=0:350[basev]"
        )
    elif layout == "split_screen":
        wx, wy, ww, wh = _clamp_box(webcam_box, {"x": 0.02, "y": 0.04, "w": 0.30, "h": 0.35})
        layout_graph = (
            f"[{src_label}]split=2[cam][game];"
            f"[cam]crop=in_w*{ww:.3f}:in_h*{wh:.3f}:in_w*{wx:.3f}:in_h*{wy:.3f},scale=1080:672:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:672,setsar=1,unsharp=3:3:0.35[top];"
            f"[game]scale=1080:1248:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1248,setsar=1[bot];"
            f"[top][bot]vstack=inputs=2[basev]"
        )
    elif layout == "centered_face":
        if spks:
            cx = spks[0]["cx"]
            x_off = max(0.0, min(0.70, cx - 0.16))
            layout_graph = (
                f"[{src_label}]crop=in_h*9/16:in_h:in_w*{x_off:.3f}:0,scale=1080:1920:flags=lanczos,setsar=1[basev]"
            )
        else:
            layout_graph = f"[{src_label}]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1[basev]"
    else: # blur_bg
        layout_graph = (
            f"[{src_label}]split=2[fg][bg];"
            f"[bg]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=8:2,scale=1080:1920:flags=lanczos,setsar=1[bg_blur];"
            f"[fg]scale=1080:608:force_original_aspect_ratio=decrease:flags=lanczos,setsar=1[fg_sharp];"
            f"[bg_blur][fg_sharp]overlay=(W-w)/2:(H-h)/2[basev]"
        )

    # Composite climax beat highlight and graphic PNG cards (with smooth ease-out slide-down + alpha transition)
    fc_parts.append(layout_graph)
    cur_v = "basev"

    if climax_active and climax_beat is not None:
        fc_parts.append(_build_climax_subgraph("clm_src", climax_beat, climax_at))
        fc_parts.append(
            f"[{cur_v}][clm]overlay=0:0:enable='between(t,{climax_at:.2f},{climax_at + climax_dur:.2f})'[basev_clm]"
        )
        cur_v = "basev_clm"

    if video_transitions:
        # Crisp subtle brightness ramp-in at 0.0 -> 0.28s
        fc_parts.append(f"[{cur_v}]fade=t=in:st=0:d=0.22:color=#060B10[v_tr]")
        cur_v = "v_tr"

    if hook_idx is not None:
        if hook_persistence == "always":
            fc_parts.append(f"[{hook_idx}:v]format=rgba,fade=t=in:st=0:d=0.25:alpha=1[hk_ov]")
            y_slide = "if(lt(t,0.35),-72*(1-t/0.35)*(1-t/0.35),0)"
            fc_parts.append(f"[{cur_v}][hk_ov]overlay=x=0:y='{y_slide}':shortest=1[v_hk]")
        else:
            fc_parts.append(f"[{hook_idx}:v]format=rgba,fade=t=in:st=0:d=0.25:alpha=1,fade=t=out:st=4.2:d=0.3:alpha=1[hk_ov]")
            y_slide = "if(lt(t,0.35),-72*(1-t/0.35)*(1-t/0.35),0)"
            fc_parts.append(f"[{cur_v}][hk_ov]overlay=x=0:y='{y_slide}':eof_action=pass:enable='between(t,0,4.6)'[v_hk]")
        cur_v = "v_hk"

    if card_idx is not None:
        fc_parts.append(
            f"[{card_idx}:v]format=rgba,fade=t=in:st={card_start:.2f}:d=0.25:alpha=1,"
            f"fade=t=out:st={card_end - 0.35:.2f}:d=0.3:alpha=1[cd_ov]"
        )
        y_card_slide = f"if(lt(t-{card_start:.2f},0.35),-56*(1-max(0,t-{card_start:.2f})/0.35)*(1-max(0,t-{card_start:.2f})/0.35),0)"
        fc_parts.append(
            f"[{cur_v}][cd_ov]overlay=x=0:y='{y_card_slide}':eof_action=pass:enable='between(t,{card_start:.2f},{card_end:.2f})'[v_cd]"
        )
        cur_v = "v_cd"

    # Burn-in animated ASS subtitles
    if ass_subtitle_path and Path(ass_subtitle_path).exists():
        escaped_sub = str(Path(ass_subtitle_path).resolve()).replace("\\", "/").replace(":", "\\:")
        fc_parts.append(f"[{cur_v}]subtitles='{escaped_sub}'[outv]")
    else:
        fc_parts.append(f"[{cur_v}]copy[outv]")

    # Subtle Audio SFX Mixing (normalize=0 keeps main speaker voice 100% loud!)
    has_audio = _has_audio_stream(source_video_path)
    audio_map = "0:a?"
    if has_audio and (pop_idx is not None or whoosh_idx is not None or impact_idx is not None or riser_idx is not None):
        mix_labels = ["[0:a]"]
        if pop_idx is not None:
            fc_parts.append(f"[{pop_idx}:a]adelay=100|100,volume=0.16[sfx_pop]")
            mix_labels.append("[sfx_pop]")
        if whoosh_idx is not None:
            delay_ms = int((cut_times[0] * 1000) if cut_times else (card_start * 1000))
            fc_parts.append(f"[{whoosh_idx}:a]adelay={delay_ms}|{delay_ms},volume=0.14[sfx_whoosh]")
            mix_labels.append("[sfx_whoosh]")
        if riser_idx is not None:
            riser_ms = max(0, int((climax_at - 0.35) * 1000))
            fc_parts.append(f"[{riser_idx}:a]adelay={riser_ms}|{riser_ms},volume=0.18[sfx_riser]")
            mix_labels.append("[sfx_riser]")
        if impact_idx is not None:
            impact_ms = max(0, int(climax_at * 1000))
            fc_parts.append(f"[{impact_idx}:a]adelay={impact_ms}|{impact_ms},volume=0.32[sfx_impact]")
            mix_labels.append("[sfx_impact]")
        fc_parts.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:normalize=0[outa]")
        audio_map = "[outa]"

    filter_complex = ";".join(fc_parts)

    cmd = [
        FFMPEG_PATH,
        "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", audio_map,
        "-r", "30",
        *encoder_args,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "160k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
    except subprocess.CalledProcessError:
        if "amf" in encoder_name:
            cmd_fallback = [
                FFMPEG_PATH, "-y", *inputs, "-filter_complex", filter_complex,
                "-map", "[outv]", "-map", audio_map, "-r", "30",
                *LIBX264_FALLBACK_ARGS, "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(output_path),
            ]
            subprocess.run(cmd_fallback, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
            encoder_name = "libx264"
        else:
            raise

    thumb_cmd = [
        FFMPEG_PATH, "-y", "-ss", "00:00:01.50", "-i", str(output_path),
        "-vframes", "1", "-vf", "scale=540:960:flags=lanczos", "-q:v", "3", str(thumb_path),
    ]
    try:
        subprocess.run(thumb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    except Exception:
        pass

    return {
        "output_path": str(output_path),
        "thumbnail_path": str(thumb_path) if thumb_path.exists() else None,
        "encoder_used": encoder_name,
    }
