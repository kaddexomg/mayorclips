import html
import math
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image, ImageDraw
from sqlmodel import Session

from app.config import STORAGE_DIR, RENDERS_DIR, CACHE_DIR, FFMPEG_PATH, BASE_DIR
from app.db import engine
from app.models import StudioVideo
from pulpo import pulpo
from render.ffmpeg_engine import get_best_h264_encoder
from render.overlays import _load_font, _layout_lines, FONT_BOLD, FONT_EMOJI
from render.subtitles import generate_ass_file

STUDIO_HF_DIR = STORAGE_DIR / "studio_hf"
SFX_DIR = BASE_DIR / "assets" / "sfx"
XFADE_TYPES = ["smoothleft", "wipeup", "slideleft", "circleopen"]


def _parse_hex_rgb(color_str: Optional[str], fallback: Tuple[int, int, int] = (43, 240, 200)) -> Tuple[int, int, int]:
    raw = (color_str or "").strip().lstrip("#")
    if len(raw) == 6:
        try:
            return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
        except ValueError:
            pass
    return fallback


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    y_start: int,
    max_width: int,
    font_size: int,
    fill_rgba: Tuple[int, int, int, int],
    centered: bool = True,
    left_x: int = 110,
) -> int:
    """Draws wrapped text with inline full-color Windows 11 emojis. Returns bottom Y coordinate."""
    clean = (text or "").strip()
    if not clean:
        return y_start
    text_font = _load_font(FONT_BOLD, font_size)
    emoji_font = _load_font(FONT_EMOJI, int(font_size * 0.94))
    lines = _layout_lines(draw, clean, max_width, text_font, emoji_font)
    line_h = int(font_size * 1.30)
    cur_y = y_start
    for line_tokens, line_w in lines:
        cur_x = ((1080 - line_w) // 2) if centered else left_x
        for tok, is_em, tw in line_tokens:
            if is_em:
                draw.text((cur_x, cur_y + 4), tok, font=emoji_font, embedded_color=True)
            else:
                draw.text((cur_x, cur_y), tok, font=text_font, fill=fill_rgba)
            cur_x += tw
        cur_y += line_h
    return cur_y


def _draw_glow_backdrop(img: Image.Image, accent: Tuple[int, int, int]) -> Image.Image:
    """Composites subtle glow orbs, faint architectural grid lines, and outer frame using true alpha compositing."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    r, g, b = accent
    for radius, alpha in [(500, 14), (360, 20), (220, 26)]:
        draw.ellipse(
            [540 - radius, 420 - radius, 540 + radius, 420 + radius],
            fill=(r, g, b, alpha),
        )
    for gx in range(60, 1080, 90):
        draw.line([(gx, 0), (gx, 1920)], fill=(255, 255, 255, 12), width=1)
    for gy in range(80, 1920, 90):
        draw.line([(0, gy), (1080, gy)], fill=(255, 255, 255, 12), width=1)
    draw.rounded_rectangle([44, 44, 1036, 1876], radius=36, outline=(r, g, b, 55), width=2)
    return Image.alpha_composite(img, overlay)


def render_scene_slide_png(
    scene: Dict[str, Any],
    idx: int,
    total: int,
    out_path: str,
    video_title: str = "",
) -> str:
    """Renders a 1080x1920 high-contrast Motion Graphics slide (stats, code/explainer cards, kinetic headlines)."""
    img = Image.new("RGBA", (1080, 1920), (6, 11, 16, 255))
    accent = _parse_hex_rgb(scene.get("accent_color"), (43, 240, 200))
    img = _draw_glow_backdrop(img, accent)

    # Layer semi-transparent cards using true alpha compositing onto RGBA canvas
    card_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(card_layer)

    r, g, b = accent
    template = scene.get("template", "kinetic_text")
    badge = (scene.get("badge") or f"ESCENA 0{idx + 1}").strip().upper()
    headline = (scene.get("headline") or f"Punto {idx + 1}").strip()
    subtitle = (scene.get("subtitle") or "").strip()
    stat_value = (scene.get("stat_value") or "").strip()
    stat_label = (scene.get("stat_label") or "").strip()
    progress_pct = max(12, min(98, int(scene.get("progress_pct") or (35 + idx * 18))))
    bullets = scene.get("bullets") or []

    # Top header bar + badge pill
    hdr_font = _load_font(FONT_BOLD, 24)
    cdraw.text((84, 92), f"MAYORCLIPS STUDIO // 0{idx + 1}/0{total}", font=hdr_font, fill=(148, 163, 184, 215))

    badge_font = _load_font(FONT_BOLD, 28)
    bb = cdraw.textbbox((0, 0), badge, font=badge_font)
    bw = (bb[2] - bb[0]) + 56
    bx0 = (1080 - bw) // 2
    cdraw.rounded_rectangle([bx0, 178, bx0 + bw, 238], radius=30, fill=(r, g, b, 36), outline=(r, g, b, 210), width=2)
    cdraw.text((bx0 + 28, 191), badge, font=badge_font, fill=(r, g, b, 255))

    # Main stage card (safe upper-middle zone y=280..1210 so lower 1300+ stays clean for kinetic ASS captions)
    cdraw.rounded_rectangle(
        [76, 280, 1004, 1210],
        radius=34,
        fill=(12, 22, 29, 238),
        outline=(255, 255, 255, 32),
        width=2,
    )
    cdraw.rounded_rectangle([76, 280, 1004, 292], radius=6, fill=(r, g, b, 235))

    cur_y = 338

    if stat_value or template == "stat_card":
        val_txt = stat_value or f"{progress_pct}%"
        cdraw.rounded_rectangle(
            [126, cur_y, 954, cur_y + 210],
            radius=24,
            fill=(6, 11, 16, 220),
            outline=(r, g, b, 130),
            width=2,
        )
        _draw_wrapped_text(cdraw, val_txt, cur_y + 28, 760, 88, (r, g, b, 255), centered=True)
        if stat_label:
            _draw_wrapped_text(cdraw, stat_label.upper(), cur_y + 144, 760, 26, (203, 213, 225, 230), centered=True)
        cur_y += 248

    # Kinetic headline
    cur_y = _draw_wrapped_text(cdraw, headline, cur_y, 820, 60, (248, 250, 252, 255), centered=True)
    cur_y += 22

    # Divider rule
    cdraw.rounded_rectangle([440, cur_y, 640, cur_y + 6], radius=3, fill=(r, g, b, 255))
    cur_y += 32

    if subtitle:
        cur_y = _draw_wrapped_text(cdraw, subtitle, cur_y, 810, 34, (203, 213, 225, 240), centered=True)
        cur_y += 24

    # Code / explainer step pills
    if bullets:
        for bi, btxt in enumerate(bullets[:3]):
            if cur_y + 74 > 1118:
                break
            cdraw.rounded_rectangle(
                [122, cur_y, 958, cur_y + 66],
                radius=16,
                fill=(18, 32, 42, 235),
                outline=(r, g, b, 95),
                width=2,
            )
            _draw_wrapped_text(cdraw, f"0{bi + 1} · {str(btxt)}", cur_y + 15, 780, 26, (241, 245, 249, 255), centered=False, left_x=148)
            cur_y += 80

    # Animated progress / metric bar at bottom of stage card
    bar_y = 1135
    cdraw.rounded_rectangle([126, bar_y, 954, bar_y + 20], radius=10, fill=(255, 255, 255, 28))
    fill_w = max(40, int((954 - 126) * (progress_pct / 100.0)))
    cdraw.rounded_rectangle([126, bar_y, 126 + fill_w, bar_y + 20], radius=10, fill=(r, g, b, 245))

    if video_title:
        _draw_wrapped_text(cdraw, video_title, 1810, 860, 24, (148, 163, 184, 170), centered=True)

    final_img = Image.alpha_composite(img, card_layer)
    final_img.convert("RGB").save(out_path, "PNG")
    return out_path


def export_hyperframes_project(
    studio_id: str,
    title: str,
    scene_plan: List[Dict[str, Any]],
    scene_durs: List[float],
    audio_src_path: Optional[str],
) -> str:
    """Writes a clean editable HyperFrames root composition + sub-compositions under storage/studio_hf/<id>/."""
    proj_dir = STUDIO_HF_DIR / studio_id
    comp_dir = proj_dir / "compositions"
    assets_dir = proj_dir / "assets"
    comp_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    audio_tag = ""
    total_dur = max(5.0, sum(scene_durs) - 0.40 * max(0, len(scene_durs) - 1))
    if audio_src_path and Path(audio_src_path).exists():
        shutil.copy2(audio_src_path, assets_dir / "voiceover.mp3")
        audio_tag = f'  <audio id="voiceover" class="clip" src="assets/voiceover.mp3" data-start="0" data-duration="{total_dur:.2f}"></audio>'

    hosts = []
    cur_t = 0.0
    for i, (sc, sdur) in enumerate(zip(scene_plan, scene_durs)):
        cid = f"scene-{i + 1}"
        accent = sc.get("accent_color") or "#2BF0C8"
        badge = html.escape(str(sc.get("badge") or f"ESCENA 0{i + 1}"))
        headline = html.escape(str(sc.get("headline") or ""))
        subtitle = html.escape(str(sc.get("subtitle") or ""))
        stat_val = html.escape(str(sc.get("stat_value") or ""))
        bullets_html = "".join(f'<li>{html.escape(str(b))}</li>' for b in (sc.get("bullets") or [])[:3])

        sub_html = f"""<template>
  <style>
    #root {{
      position: absolute; inset: 0;
      width: 1080px; height: 1920px;
      background: #060B10; color: #F8FAFC; font-family: sans-serif;
      display: flex; align-items: center; justify-content: center;
    }}
    .card {{
      width: 900px; padding: 64px; border-radius: 36px;
      background: rgba(12, 22, 29, 0.92); border: 2px solid {accent};
      text-align: center;
    }}
    .badge {{ color: {accent}; font-weight: 700; font-size: 28px; letter-spacing: 2px; margin-bottom: 24px; }}
    .stat {{ color: {accent}; font-size: 86px; font-weight: 900; margin-bottom: 16px; }}
    .headline {{ font-size: 58px; font-weight: 800; line-height: 1.15; margin-bottom: 22px; }}
    .subtitle {{ font-size: 32px; color: #CBD5E1; line-height: 1.35; }}
    ul {{ text-align: left; margin-top: 28px; list-style: none; padding: 0; font-size: 28px; }}
    li {{ padding: 12px 18px; margin-bottom: 10px; border-radius: 12px; background: rgba(255,255,255,0.05); }}
  </style>
  <div id="root" data-composition-id="{cid}" data-width="1080" data-height="1920">
    <div class="card clip" id="card" data-start="0" data-duration="{sdur:.2f}">
      <div class="badge" id="badge" data-var-text="badge">{badge}</div>
      {f'<div class="stat" id="stat" data-var-text="stat">{stat_val}</div>' if stat_val else ''}
      <h1 class="headline" id="headline" data-var-text="headline">{headline}</h1>
      <p class="subtitle" id="subtitle" data-var-text="subtitle">{subtitle}</p>
      {f'<ul>{bullets_html}</ul>' if bullets_html else ''}
    </div>
  </div>
  <script>
    window.__timelines = window.__timelines || {{}};
    const tl = gsap.timeline({{ paused: true }});
    tl.from("#headline", {{ opacity: 0.25, scale: 0.94, duration: 0.4, ease: "back.out(1.4)" }});
    window.__timelines["{cid}"] = tl;
  </script>
</template>
"""
        (comp_dir / f"scene_{i + 1}.html").write_text(sub_html, encoding="utf-8")
        hosts.append(
            f'    <div id="host_{cid}" data-composition-id="{cid}" data-composition-src="compositions/scene_{i + 1}.html" '
            f'data-track-index="1" data-track-kind="graphics" data-start="{cur_t:.2f}" data-duration="{sdur:.2f}" '
            f'data-width="1080" data-height="1920"></div>'
        )
        cur_t = max(0.0, cur_t + sdur - 0.40)

    root_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>{html.escape(title)}</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
  <style>* {{ margin: 0; padding: 0; box-sizing: border-box; }} body {{ background: #060B10; overflow: hidden; }}</style>
</head>
<body>
  <div id="root" data-composition-id="main" data-start="0" data-width="1080" data-height="1920" data-fps="30" data-duration="{total_dur:.2f}">
{chr(10).join(hosts)}
{audio_tag}
  </div>
  <script>
    window.__timelines = window.__timelines || {{}};
    window.__timelines["main"] = gsap.timeline({{ paused: true }});
  </script>
</body>
</html>
"""
    (proj_dir / "index.html").write_text(root_html, encoding="utf-8")
    return str(proj_dir)


async def render_studio_video_job(job_id: str, studio_id: str, progress_callback=None) -> Dict[str, Any]:
    """Synthesizes Edge-TTS audio, renders multi-scene Pillow graphic slides + FFmpeg xfade transitions + ASS subs + HyperFrames export."""
    with Session(engine) as session:
        sv = session.get(StudioVideo, studio_id)
        if not sv:
            raise ValueError(f"StudioVideo {studio_id} no encontrado")
        script = sv.script_json or {}
        scene_plan = sv.scene_plan_json or []
        voice = sv.voice_name
        title = sv.title

    if not scene_plan:
        scene_plan = [{
            "scene_id": 1,
            "template": "kinetic_text",
            "badge": "STUDIO IA",
            "headline": title,
            "subtitle": script.get("hook", ""),
            "accent_color": "#2BF0C8",
            "duration_sec": 6.0,
        }]

    scenes = script.get("scenes", [])
    hook_txt = script.get("hook", "")
    full_narration = hook_txt + " " + " ".join(s.get("spoken_text", "") for s in scenes)
    full_narration = full_narration.strip() or title

    if progress_callback:
        progress_callback(20, f"Generando locución neuronal con {voice}...")

    tts_res = await pulpo.run("tts", {"text": full_narration, "voice": voice})
    audio_path = tts_res["audio_path"]
    words = tts_res["word_boundaries"]
    total_dur = max(6.0, float(tts_res["duration_sec"]) + 0.6)

    if progress_callback:
        progress_callback(42, "Diseñando diapositivas Motion Graphics HD y proyecto HyperFrames...")

    ass_path = str(CACHE_DIR / f"studio_{studio_id[:8]}.ass")
    generate_ass_file(words, ass_path, style_name="neon", margin_v_override=350)

    # Normalize per-scene durations so sum(d_i) - (N - 1)*xfade == total_dur
    xfade_dur = 0.40
    n_scenes = len(scene_plan)
    raw_weights = [max(2.0, float(sc.get("duration_sec") or 5.0)) for sc in scene_plan]
    raw_sum = sum(raw_weights)
    needed_sum = total_dur + max(0, n_scenes - 1) * xfade_dur
    scene_durs = [max(2.2, round((w / raw_sum) * needed_sum, 2)) for w in raw_weights]
    # Adjust last scene slightly so total matches exactly
    diff = needed_sum - sum(scene_durs)
    scene_durs[-1] = max(2.2, round(scene_durs[-1] + diff, 2))

    slide_paths: List[str] = []
    for idx, sc in enumerate(scene_plan):
        sp = str(CACHE_DIR / f"studio_{studio_id[:8]}_s{idx + 1}.png")
        render_scene_slide_png(sc, idx, n_scenes, sp, video_title=title)
        slide_paths.append(sp)

    hf_dir = export_hyperframes_project(studio_id, title, scene_plan, scene_durs, audio_path)

    if progress_callback:
        progress_callback(68, f"Renderizando {n_scenes} escenas con transiciones xfade y subtítulos...")

    out_mp4 = RENDERS_DIR / f"studio_{studio_id[:8]}.mp4"
    encoder_name, encoder_args = get_best_h264_encoder()
    escaped_ass = str(Path(ass_path).resolve()).replace("\\", "/").replace(":", "\\:")

    inputs: List[str] = []
    for sp, sdur in zip(slide_paths, scene_durs):
        inputs.extend(["-loop", "1", "-t", f"{sdur:.2f}", "-i", sp])

    audio_idx = n_scenes
    inputs.extend(["-i", str(audio_path)])

    whoosh_wav = SFX_DIR / "whoosh_light.wav"
    whoosh_idx = None
    if n_scenes > 1 and whoosh_wav.exists():
        whoosh_idx = audio_idx + 1
        inputs.extend(["-i", str(whoosh_wav)])

    fc_parts: List[str] = []
    for i, sdur in enumerate(scene_durs):
        # Smooth lightweight Ken Burns pan over a slightly upscaled slide (fast CPU, zero blur)
        dx = 26 if i % 2 == 0 else -26
        x_expr = f"26+({dx})*(t/{sdur:.2f})" if dx > 0 else f"26-({abs(dx)})*(t/{sdur:.2f})"
        fc_parts.append(
            f"[{i}:v]scale=1132:2012,crop=1080:1920:x='{x_expr}':y='46*(t/{sdur:.2f})',fps=30,format=yuv420p,setsar=1[sc{i}]"
        )

    cur_v = "sc0"
    running_len = scene_durs[0]
    xfade_offsets: List[float] = []
    for i in range(1, n_scenes):
        offset = max(0.5, running_len - xfade_dur)
        xfade_offsets.append(offset)
        xtype = XFADE_TYPES[(i - 1) % len(XFADE_TYPES)]
        nxt = f"xf{i}"
        fc_parts.append(f"[{cur_v}][sc{i}]xfade=transition={xtype}:duration={xfade_dur:.2f}:offset={offset:.2f}[{nxt}]")
        cur_v = nxt
        running_len = offset + scene_durs[i]

    fc_parts.append(f"[{cur_v}]subtitles='{escaped_ass}'[outv]")

    # Mix Edge-TTS narration with subtle whoosh SFX at scene transition points
    audio_map = f"{audio_idx}:a"
    if whoosh_idx is not None and xfade_offsets:
        mix_labels = [f"[{audio_idx}:a]"]
        splits = [f"[wh{i}]" for i in range(len(xfade_offsets))]
        if len(xfade_offsets) == 1:
            delay_ms = int(xfade_offsets[0] * 1000)
            fc_parts.append(f"[{whoosh_idx}:a]adelay={delay_ms}|{delay_ms},volume=0.18[sfx0]")
            mix_labels.append("[sfx0]")
        else:
            fc_parts.append(f"[{whoosh_idx}:a]asplit={len(xfade_offsets)}{''.join(splits)}")
            for i, off in enumerate(xfade_offsets):
                delay_ms = int(off * 1000)
                fc_parts.append(f"[wh{i}]adelay={delay_ms}|{delay_ms},volume=0.16[sfx{i}]")
                mix_labels.append(f"[sfx{i}]")
        fc_parts.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:normalize=0[outa]")
        audio_map = "[outa]"

    cmd = [
        FFMPEG_PATH,
        "-y",
        *inputs,
        "-filter_complex", ";".join(fc_parts),
        "-map", "[outv]",
        "-map", audio_map,
        "-r", "30",
        *encoder_args,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "160k",
        "-shortest",
        "-movflags", "+faststart",
        str(out_mp4),
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=240)
    except subprocess.CalledProcessError:
        if "amf" in encoder_name:
            cmd_fb = [
                FFMPEG_PATH, "-y", *inputs, "-filter_complex", ";".join(fc_parts),
                "-map", "[outv]", "-map", audio_map, "-r", "30",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out_mp4),
            ]
            subprocess.run(cmd_fb, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=240)
        else:
            raise

    with Session(engine) as session:
        sv = session.get(StudioVideo, studio_id)
        if sv:
            sv.status = "rendered"
            sv.audio_path = audio_path
            sv.output_path = str(out_mp4)
            session.add(sv)
            session.commit()

    if progress_callback:
        progress_callback(100, "¡Video Motion Graphics MP4 y proyecto HyperFrames listos!")

    return {
        "output_path": str(out_mp4),
        "video_url": f"/renders/{out_mp4.name}",
        "hf_project_dir": hf_dir,
        "scenes_rendered": n_scenes,
    }
