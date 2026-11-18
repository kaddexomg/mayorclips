import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from app.config import FFMPEG_PATH, RENDERS_DIR, BASE_DIR

SFX_DIR = BASE_DIR / "assets" / "sfx"


def get_best_h264_encoder() -> tuple[str, list[str]]:
    """Returns hardware AMD AMF encoder args with balanced mobile bitrate if available, else libx264."""
    try:
        res = subprocess.run([FFMPEG_PATH, "-hide_banner", "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if "h264_amf" in res.stdout:
            return "h264_amf", ["-c:v", "h264_amf", "-quality", "speed", "-b:v", "3500k", "-maxrate", "5000k", "-bufsize", "7000k"]
    except Exception:
        pass
    return "libx264", ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]


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
) -> Dict[str, Any]:
    """Renders 1080x1920 vertical clip with active speaker tracking / duo split, PNG color-emoji cards, ASS subs, and subtle SFX."""
    output_path = RENDERS_DIR / output_filename
    thumb_path = RENDERS_DIR / f"{Path(output_filename).stem}_thumb.jpg"
    encoder_name, encoder_args = get_best_h264_encoder()

    seek_args = []
    if start_sec > 0:
        seek_args.extend(["-ss", str(round(start_sec, 2))])
    if end_sec > start_sec:
        seek_args.extend(["-t", str(round(end_sec - start_sec, 2))])

    # Inputs list: 0 = video, optional PNGs, optional SFX wavs
    inputs = [*seek_args, "-i", str(source_video_path)]
    idx_counter = 1

    hook_idx = None
    if hook_png_path and Path(hook_png_path).exists():
        inputs.extend(["-loop", "1", "-t", "5.0", "-i", str(hook_png_path)])
        hook_idx = idx_counter
        idx_counter += 1

    card_idx = None
    if card_png_path and Path(card_png_path).exists():
        inputs.extend(["-loop", "1", "-t", "10.5", "-i", str(card_png_path)])
        card_idx = idx_counter
        idx_counter += 1

    pop_wav = SFX_DIR / "pop_soft.wav"
    whoosh_wav = SFX_DIR / "whoosh_light.wav"
    pop_idx = None
    whoosh_idx = None
    if enable_sfx and pop_wav.exists():
        inputs.extend(["-i", str(pop_wav)])
        pop_idx = idx_counter
        idx_counter += 1
    if enable_sfx and whoosh_wav.exists() and card_idx is not None:
        inputs.extend(["-i", str(whoosh_wav)])
        whoosh_idx = idx_counter
        idx_counter += 1

    # Base video layout graph -> outputs [basev] at 1080x1920
    spks = speakers or []
    if layout == "duo_split" and len(spks) >= 2:
        x1, y1, w1, h1 = _clamp_box(spks[0]["box"], {"x": 0.05, "y": 0.05, "w": 0.4, "h": 0.7})
        x2, y2, w2, h2 = _clamp_box(spks[1]["box"], {"x": 0.55, "y": 0.05, "w": 0.4, "h": 0.7})
        layout_graph = (
            f"[0:v]split=2[s1][s2];"
            f"[s1]crop=in_w*{w1:.3f}:in_h*{h1:.3f}:in_w*{x1:.3f}:in_h*{y1:.3f},scale=1080:958:force_original_aspect_ratio=increase,crop=1080:958,setsar=1[top];"
            f"[s2]crop=in_w*{w2:.3f}:in_h*{h2:.3f}:in_w*{x2:.3f}:in_h*{y2:.3f},scale=1080:958:force_original_aspect_ratio=increase,crop=1080:958,setsar=1[bot];"
            f"[top]pad=1080:962:0:0:#060B10[top_pad];"
            f"[top_pad][bot]vstack=inputs=2[basev]"
        )
    elif layout == "speaker_focus" and (timeline_segments or len(spks) >= 1):
        segs = timeline_segments[:12] if timeline_segments else [{"start": 0.0, "end": 999.0, "box": spks[0]["box"]}]
        # Use median w/h across segments so crop size is constant (required by FFmpeg scale/vstack!)
        avg_w = max(0.18, min(0.85, sum(s["box"]["w"] for s in segs) / len(segs)))
        avg_h = max(0.20, min(0.85, sum(s["box"]["h"] for s in segs) / len(segs)))
        x_expr = _build_dynamic_crop_expr(segs, "x", 0.25)
        y_expr = _build_dynamic_crop_expr(segs, "y", 0.05)
        layout_graph = (
            f"[0:v]split=2[spk][scr];"
            f"[spk]crop=w='in_w*{avg_w:.3f}':h='in_h*{avg_h:.3f}':x='{x_expr}':y='{y_expr}',scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960,setsar=1[top];"
            f"[scr]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960,setsar=1[bot];"
            f"[top][bot]vstack=inputs=2[basev]"
        )
    elif layout == "split_screen":
        wx, wy, ww, wh = _clamp_box(webcam_box, {"x": 0.02, "y": 0.04, "w": 0.30, "h": 0.35})
        layout_graph = (
            f"[0:v]split=2[cam][game];"
            f"[cam]crop=in_w*{ww:.3f}:in_h*{wh:.3f}:in_w*{wx:.3f}:in_h*{wy:.3f},scale=1080:672:force_original_aspect_ratio=increase,crop=1080:672,setsar=1[top];"
            f"[game]scale=1080:1248:force_original_aspect_ratio=increase,crop=1080:1248,setsar=1[bot];"
            f"[top][bot]vstack=inputs=2[basev]"
        )
    elif layout == "centered_face":
        if spks:
            cx = spks[0]["cx"]
            x_off = max(0.0, min(0.70, cx - 0.16))
            layout_graph = (
                f"[0:v]crop=in_h*9/16:in_h:in_w*{x_off:.3f}:0,scale=1080:1920,setsar=1[basev]"
            )
        else:
            layout_graph = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[basev]"
    else: # blur_bg
        layout_graph = (
            f"[0:v]split=2[fg][bg];"
            f"[bg]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=8:2,scale=1080:1920,setsar=1[bg_blur];"
            f"[fg]scale=1080:608:force_original_aspect_ratio=decrease,setsar=1[fg_sharp];"
            f"[bg_blur][fg_sharp]overlay=(W-w)/2:(H-h)/2[basev]"
        )

    # Composite graphic PNG cards (with smooth alpha fade)
    fc_parts = [layout_graph]
    cur_v = "basev"

    if hook_idx is not None:
        fc_parts.append(f"[{hook_idx}:v]format=rgba,fade=t=in:st=0:d=0.25:alpha=1,fade=t=out:st=4.2:d=0.3:alpha=1[hk_ov]")
        fc_parts.append(f"[{cur_v}][hk_ov]overlay=0:0:eof_action=pass:enable='between(t,0,4.6)'[v_hk]")
        cur_v = "v_hk"

    if card_idx is not None:
        fc_parts.append(f"[{card_idx}:v]format=rgba,fade=t=in:st=4.8:d=0.25:alpha=1,fade=t=out:st=9.6:d=0.3:alpha=1[cd_ov]")
        fc_parts.append(f"[{cur_v}][cd_ov]overlay=0:0:eof_action=pass:enable='between(t,4.8,10.0)'[v_cd]")
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
    if has_audio and (pop_idx is not None or whoosh_idx is not None):
        mix_labels = ["[0:a]"]
        if pop_idx is not None:
            fc_parts.append(f"[{pop_idx}:a]adelay=100|100,volume=0.16[sfx_pop]")
            mix_labels.append("[sfx_pop]")
        if whoosh_idx is not None:
            fc_parts.append(f"[{whoosh_idx}:a]adelay=4800|4800,volume=0.14[sfx_whoosh]")
            mix_labels.append("[sfx_whoosh]")
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
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(output_path),
            ]
            subprocess.run(cmd_fallback, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        else:
            raise

    thumb_cmd = [
        FFMPEG_PATH, "-y", "-ss", "00:00:01.50", "-i", str(output_path),
        "-vframes", "1", "-vf", "scale=360:640", str(thumb_path),
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
