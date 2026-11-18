import html
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright

from app.config import FFMPEG_PATH, STORAGE_DIR
from render.ffmpeg_engine import get_best_h264_encoder
from studio.media_fetcher import get_hf_vendor_paths, get_lottie_json

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
STUDIO_HF_DIR = STORAGE_DIR / "studio_hf"

_SAFE_SVG_TAG_RE = re.compile(
    r"</?(?:script|foreignObject|iframe|object|embed|text|tspan|image|animateMotion)[^>]*>",
    re.IGNORECASE,
)
_EVENT_ATTR_RE = re.compile(r"\son\w+\s*=\s*(['\"]).*?\1", re.IGNORECASE)


def sanitize_bespoke_svg(raw_svg: Optional[str]) -> str:
    """Strips unsafe tags, event attributes, and accidental <text> clutter from AI-generated <g> layers."""
    if not raw_svg or not isinstance(raw_svg, str):
        return ""
    cleaned = _SAFE_SVG_TAG_RE.sub("", raw_svg)
    cleaned = _EVENT_ATTR_RE.sub("", cleaned)
    cleaned = cleaned.strip()
    if not cleaned:
        return ""
    if not cleaned.startswith("<g"):
        cleaned = f'<g opacity="0.65">{cleaned}</g>'
    return cleaned


def _probe_media_duration(media_path: str, fallback: float) -> float:
    """Probes exact media duration via ffprobe so frame counts never overrun audio length."""
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
                str(media_path),
            ],
            text=True,
            timeout=10,
        )
        val = float(out.strip())
        if val > 0.3:
            return val
    except Exception:
        pass
    return max(1.0, float(fallback))


def build_motion_stage_html(
    title: str,
    characters: List[Dict[str, Any]],
    beats: List[Dict[str, Any]],
    dialogue_timeline: List[Dict[str, Any]],
    beat_media_rel: Dict[int, Dict[str, Any]],
    lottie_keys: List[str],
    total_duration: float,
    has_vendor_gsap: bool = True,
    has_vendor_lottie: bool = True,
) -> str:
    """Builds a deterministic HyperFrames/GSAP/Lottie 1080x1920 vertical motion graphics composition."""
    prepared_beats: List[Dict[str, Any]] = []
    for idx, b in enumerate(beats):
        bc = dict(b)
        m = beat_media_rel.get(idx) or {"kind": "none", "rel_path": ""}
        bc["media_kind"] = m.get("kind", "none")
        bc["media_src"] = m.get("rel_path", "")
        prepared_beats.append(bc)

    story_payload = {
        "title": title,
        "characters": characters,
        "beats": prepared_beats,
        "dialogues": dialogue_timeline,
        "lottie_keys": lottie_keys,
        "total_duration": total_duration,
    }
    data_json = json.dumps(story_payload, ensure_ascii=False)

    gsap_tag = '<script src="assets/vendor/gsap.min.js"></script>' if has_vendor_gsap else ""
    lottie_tag = '<script src="assets/vendor/lottie.min.js"></script>' if has_vendor_lottie else ""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
{gsap_tag}
{lottie_tag}
<script src="assets/lottie_bundle.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{
    width: 100%; height: 100%; overflow: hidden;
    background: #04070d;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    color: #f8fafc;
  }}
  #stageWrap {{
    position: relative;
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    background: #04070d;
  }}
  #stageRoot {{
    position: absolute;
    left: 0; top: 0;
    width: 1080px;
    height: 1920px;
    transform-origin: top left;
    overflow: hidden;
    background: #050912;
  }}
  #cameraRig {{
    position: absolute;
    inset: -80px;
    will-change: transform, filter;
  }}
  #brollImg, #brollVid {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: none;
  }}
  #ambientFallback {{
    position: absolute;
    inset: 0;
    background: radial-gradient(circle at 30% 25%, rgba(43, 240, 200, 0.22), transparent 55%),
                radial-gradient(circle at 75% 65%, rgba(56, 189, 248, 0.18), transparent 52%),
                linear-gradient(170deg, #070d1a 0%, #0b1628 55%, #04070d 100%);
  }}
  #gradeOverlay {{
    position: absolute;
    inset: 0;
    pointer-events: none;
    transition: none;
  }}
  #vignetteOverlay {{
    position: absolute;
    inset: 0;
    pointer-events: none;
    background:
      linear-gradient(180deg, rgba(4, 7, 13, 0.80) 0%, rgba(4, 7, 13, 0.18) 22%, rgba(4, 7, 13, 0.18) 62%, rgba(4, 7, 13, 0.92) 84%, rgba(4, 7, 13, 0.97) 100%),
      radial-gradient(ellipse at 50% 45%, transparent 45%, rgba(2, 5, 10, 0.72) 100%);
  }}
  #techGrid {{
    position: absolute;
    inset: 0;
    pointer-events: none;
    opacity: 0.18;
    background-image:
      linear-gradient(rgba(56, 189, 248, 0.18) 1px, transparent 1px),
      linear-gradient(90deg, rgba(56, 189, 248, 0.18) 1px, transparent 1px);
    background-size: 72px 72px;
  }}

  /* Top HUD */
  #topHud {{
    position: absolute;
    top: 48px; left: 48px; right: 48px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    z-index: 40;
  }}
  .hud-pill {{
    display: inline-flex;
    align-items: center;
    gap: 14px;
    padding: 14px 26px;
    border-radius: 999px;
    background: rgba(6, 11, 20, 0.88);
    border: 1.5px solid rgba(255, 255, 255, 0.16);
    font-size: 24px;
    font-weight: 700;
    letter-spacing: 1.4px;
    text-transform: uppercase;
  }}
  .hud-dot {{
    width: 14px; height: 14px; border-radius: 50%;
    background: #ef4444;
    box-shadow: 0 0 14px #ef4444;
  }}
  .hud-time {{
    font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace;
    color: #94a3b8;
    font-size: 22px;
  }}

  /* Headline Kinetic Banner */
  #headlineZone {{
    position: absolute;
    top: 156px; left: 54px; right: 250px;
    z-index: 30;
  }}
  #headlineKicker {{
    display: inline-block;
    padding: 8px 18px;
    border-radius: 8px;
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 14px;
    background: rgba(43, 240, 200, 0.16);
    border: 1.5px solid rgba(43, 240, 200, 0.55);
    color: #2bf0c8;
  }}
  #headlineTitle {{
    font-size: 56px;
    font-weight: 900;
    line-height: 1.08;
    letter-spacing: -0.02em;
    color: #ffffff;
    text-shadow: 0 8px 28px rgba(0, 0, 0, 0.78);
  }}
  #headlineRule {{
    margin-top: 16px;
    height: 7px;
    width: 180px;
    border-radius: 4px;
    background: #2bf0c8;
    transform-origin: left center;
  }}

  /* Lottie Slot */
  #lottieCorner {{
    position: absolute;
    top: 150px; right: 48px;
    width: 176px; height: 176px;
    border-radius: 28px;
    background: rgba(7, 13, 24, 0.65);
    border: 1.5px solid rgba(255, 255, 255, 0.14);
    display: none;
    align-items: center;
    justify-content: center;
    padding: 12px;
    z-index: 35;
    box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  }}
  #lottieHero {{
    position: absolute;
    left: 50%; top: 470px;
    width: 440px; height: 440px;
    transform: translateX(-50%);
    display: none;
    z-index: 25;
  }}
  .lottie-slot {{
    width: 100%; height: 100%;
    display: none;
  }}

  /* Main Interactive Visual Card Area (y=360..1210) */
  #moduleStage {{
    position: absolute;
    left: 54px; right: 54px;
    top: 375px; height: 830px;
    z-index: 25;
    pointer-events: none;
  }}
  .glass-card {{
    width: 100%; height: 100%;
    border-radius: 30px;
    background: rgba(8, 14, 26, 0.88);
    border: 2px solid rgba(255, 255, 255, 0.14);
    box-shadow: 0 32px 80px rgba(0, 0, 0, 0.65);
    padding: 40px;
    overflow: hidden;
    position: relative;
  }}

  /* Radar Focus Box */
  #radarBox {{
    position: absolute;
    display: none;
    border: 3px solid #2bf0c8;
    border-radius: 18px;
    box-shadow: 0 0 36px rgba(43, 240, 200, 0.35), inset 0 0 30px rgba(43, 240, 200, 0.12);
    z-index: 26;
  }}
  #radarScanLine {{
    position: absolute;
    left: 0; right: 0; height: 4px;
    background: linear-gradient(90deg, transparent, #2bf0c8, transparent);
    box-shadow: 0 0 16px #2bf0c8;
  }}
  #radarTag {{
    position: absolute;
    top: -42px; left: 0;
    background: #2bf0c8; color: #050912;
    font-size: 21px; font-weight: 900;
    padding: 6px 16px; border-radius: 8px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
  }}

  /* Camcorder HUD Overlay */
  #camcorderHud {{
    position: absolute;
    inset: 145px 46px 560px 46px;
    display: none;
    pointer-events: none;
    z-index: 27;
    font-family: ui-monospace, Consolas, monospace;
    color: rgba(248, 250, 252, 0.9);
  }}
  .cam-corner {{
    position: absolute; width: 52px; height: 52px;
    border-color: rgba(248, 250, 252, 0.72);
    border-style: solid; border-width: 0;
  }}
  .cam-tl {{ top: 0; left: 0; border-top-width: 4px; border-left-width: 4px; }}
  .cam-tr {{ top: 0; right: 0; border-top-width: 4px; border-right-width: 4px; }}
  .cam-bl {{ bottom: 0; left: 0; border-bottom-width: 4px; border-left-width: 4px; }}
  .cam-br {{ bottom: 0; right: 0; border-bottom-width: 4px; border-right-width: 4px; }}
  .cam-meta {{
    position: absolute; bottom: 18px; left: 24px; right: 24px;
    display: flex; justify-content: space-between;
    font-size: 24px; font-weight: 700;
    text-shadow: 0 2px 8px rgba(0, 0, 0, 0.9);
  }}

  /* News Ticker / Breaking Banner */
  #newsTickerBar {{
    position: absolute;
    left: 48px; right: 48px; top: 1125px;
    height: 102px;
    display: none;
    border-radius: 18px;
    overflow: hidden;
    background: rgba(9, 14, 24, 0.94);
    border: 2px solid rgba(239, 68, 68, 0.65);
    box-shadow: 0 18px 40px rgba(0, 0, 0, 0.65);
    z-index: 32;
  }}
  .nt-badge {{
    width: 215px; height: 100%;
    background: linear-gradient(135deg, #ef4444, #991b1b);
    display: flex; align-items: center; justify-content: center;
    font-size: 25px; font-weight: 900; letter-spacing: 1.8px;
    flex-shrink: 0;
  }}
  .nt-track {{
    flex: 1; display: flex; align-items: center;
    overflow: hidden; padding: 0 26px;
  }}
  #ntText {{
    white-space: nowrap;
    font-size: 31px; font-weight: 700; color: #f8fafc;
  }}

  /* Active Speaker Lower-Third (above ASS subtitle safe zone) */
  #speakerPill {{
    position: absolute;
    left: 50%; top: 1245px;
    transform: translateX(-50%);
    height: 92px;
    padding: 0 34px 0 18px;
    border-radius: 999px;
    background: rgba(7, 13, 24, 0.92);
    border: 2.5px solid #2bf0c8;
    box-shadow: 0 16px 36px rgba(0, 0, 0, 0.6);
    display: flex; align-items: center; gap: 20px;
    z-index: 38;
    opacity: 0;
  }}
  #speakerAvatar {{
    width: 60px; height: 60px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 28px; font-weight: 900; color: #04070d;
    background: #2bf0c8;
  }}
  #speakerName {{
    font-size: 30px; font-weight: 800; color: #ffffff;
    letter-spacing: 0.4px;
  }}
  #speakerRole {{
    font-size: 19px; font-weight: 700; color: #94a3b8;
    text-transform: uppercase; letter-spacing: 1.5px;
  }}
  #voiceWave {{
    display: flex; align-items: center; gap: 5px; height: 42px; margin-left: 10px;
  }}
  .wave-bar {{
    width: 6px; border-radius: 3px; background: #2bf0c8; height: 12px;
  }}

  /* Chat Reveal UI */
  .chat-shell {{
    width: 100%; height: 100%;
    border-radius: 34px;
    background: rgba(10, 16, 28, 0.92);
    border: 2px solid rgba(255, 255, 255, 0.14);
    display: flex; flex-direction: column;
    overflow: hidden;
    box-shadow: 0 28px 70px rgba(0, 0, 0, 0.7);
  }}
  .chat-header {{
    padding: 26px 34px;
    background: rgba(15, 23, 42, 0.96);
    border-bottom: 1.5px solid rgba(255, 255, 255, 0.1);
    display: flex; align-items: center; justify-content: space-between;
  }}
  .chat-title {{ font-size: 32px; font-weight: 800; }}
  .chat-sub {{ font-size: 22px; color: #2bf0c8; font-weight: 700; }}
  .chat-body {{
    flex: 1; padding: 34px;
    display: flex; flex-direction: column; gap: 24px; justify-content: center;
  }}
  .chat-msg {{
    max-width: 84%;
    padding: 24px 30px;
    border-radius: 26px;
    font-size: 32px; line-height: 1.35; font-weight: 600;
  }}
  .chat-recv {{
    align-self: flex-start;
    background: #1e293b; color: #f8fafc;
    border-bottom-left-radius: 6px;
    border: 1.5px solid rgba(255, 255, 255, 0.12);
  }}
  .chat-sent {{
    align-self: flex-end;
    background: linear-gradient(135deg, #0ea5e9, #2563eb); color: #ffffff;
    border-bottom-right-radius: 6px;
  }}
  .chat-sender {{
    font-size: 20px; font-weight: 800; letter-spacing: 1px;
    text-transform: uppercase; opacity: 0.8; margin-bottom: 8px;
  }}

  /* Code Diff & Terminal */
  .code-titlebar {{
    display: flex; align-items: center; gap: 14px;
    padding-bottom: 24px; margin-bottom: 24px;
    border-bottom: 1.5px solid rgba(255, 255, 255, 0.1);
  }}
  .mac-dot {{ width: 18px; height: 18px; border-radius: 50%; }}
  .code-line {{
    font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace;
    font-size: 26px; line-height: 1.5;
    padding: 14px 20px; border-radius: 12px;
    margin-bottom: 14px; white-space: pre-wrap; word-break: break-word;
  }}
  .code-rem {{
    background: rgba(239, 68, 68, 0.16);
    border-left: 6px solid #ef4444;
    color: #fca5a5;
  }}
  .code-add {{
    background: rgba(34, 197, 94, 0.18);
    border-left: 6px solid #22c55e;
    color: #86efac;
  }}
  .term-cmd {{
    font-family: ui-monospace, Consolas, monospace;
    font-size: 30px; color: #2bf0c8; font-weight: 700;
    margin-bottom: 28px;
  }}
  .term-log {{
    font-family: ui-monospace, Consolas, monospace;
    font-size: 26px; color: #e2e8f0;
    padding: 16px 20px; margin-bottom: 14px;
    border-radius: 12px; background: rgba(15, 23, 42, 0.85);
    border-left: 5px solid #38bdf8;
  }}

  /* Flow Diagram */
  .flow-node {{
    padding: 24px 30px;
    border-radius: 20px;
    background: rgba(15, 23, 42, 0.92);
    border: 2px solid rgba(255, 255, 255, 0.14);
    display: flex; align-items: center; justify-content: space-between;
  }}
  .flow-node-title {{ font-size: 32px; font-weight: 800; }}
  .flow-node-sub {{ font-size: 24px; color: #94a3b8; margin-top: 4px; }}

  /* Flash & Transition Layer */
  #transitionOverlay {{
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 60;
    opacity: 0;
  }}

  /* Bottom Progress Bar */
  #bottomProgressTrack {{
    position: absolute;
    left: 48px; right: 48px; bottom: 38px;
    height: 8px; border-radius: 4px;
    background: rgba(255, 255, 255, 0.14);
    overflow: hidden;
    z-index: 50;
  }}
  #bottomProgressFill {{
    height: 100%; width: 0%;
    background: linear-gradient(90deg, #2bf0c8, #38bdf8);
  }}
</style>
</head>
<body>
<div id="stageWrap">
  <div id="stageRoot">
    <div id="cameraRig">
      <div id="ambientFallback"></div>
      <img id="brollImg" alt="" />
      <video id="brollVid" muted playsinline preload="auto"></video>
      <div id="techGrid"></div>
    </div>

    <div id="gradeOverlay"></div>
    <div id="vignetteOverlay"></div>

    <div id="topHud">
      <div class="hud-pill">
        <div class="hud-dot" id="hudRecDot"></div>
        <span id="hudBeatLabel">01/06 · HISTORIA</span>
      </div>
      <div class="hud-pill hud-time" id="hudClock">00:00</div>
    </div>

    <div id="headlineZone">
      <div id="headlineKicker">BEAT 01</div>
      <div id="headlineTitle">{html.escape(title)}</div>
      <div id="headlineRule"></div>
    </div>

    <div id="lottieCorner"></div>
    <div id="lottieHero"></div>

    <div id="radarBox">
      <div id="radarTag">PUNTO CLAVE</div>
      <div id="radarScanLine"></div>
    </div>

    <div id="camcorderHud">
      <div class="cam-corner cam-tl"></div>
      <div class="cam-corner cam-tr"></div>
      <div class="cam-corner cam-bl"></div>
      <div class="cam-corner cam-br"></div>
      <div class="cam-meta">
        <span id="camRecTxt">● REC · ISO 3200</span>
        <span id="camTcTxt">TC 00:00:00</span>
      </div>
    </div>

    <div id="moduleStage"></div>

    <div id="newsTickerBar">
      <div class="nt-badge">● EN VIVO</div>
      <div class="nt-track"><div id="ntText">ÚLTIMA HORA</div></div>
    </div>

    <div id="speakerPill">
      <div id="speakerAvatar">A</div>
      <div>
        <div id="speakerName">NARRADOR</div>
        <div id="speakerRole">ANÁLISIS</div>
      </div>
      <div id="voiceWave">
        <div class="wave-bar"></div><div class="wave-bar"></div><div class="wave-bar"></div><div class="wave-bar"></div><div class="wave-bar"></div>
      </div>
    </div>

    <div id="transitionOverlay"></div>

    <div id="bottomProgressTrack">
      <div id="bottomProgressFill"></div>
    </div>
  </div>
</div>

<script>
const STORY = {data_json};
const LOTTIE_DATA = window.__LOTTIE_ASSETS || {{}};
const cornerPlayers = {{}};
const heroPlayers = {{}};
let currentMediaSrc = "";

function clamp(v, lo, hi) {{ return Math.max(lo, Math.min(hi, v)); }}
function easeOutCubic(x) {{ const c = clamp(x, 0, 1); return 1 - Math.pow(1 - c, 3); }}
function easeOutBack(x) {{
  const c = clamp(x, 0, 1);
  const c1 = 1.70158, c3 = c1 + 1;
  return 1 + c3 * Math.pow(c - 1, 3) + c1 * Math.pow(c - 1, 2);
}}
function escHtml(s) {{
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}}

function resizeStage() {{
  const s = Math.min(window.innerWidth / 1080, window.innerHeight / 1920);
  const root = document.getElementById("stageRoot");
  if (root) root.style.transform = "scale(" + s.toFixed(6) + ")";
}}
window.addEventListener("resize", resizeStage);
resizeStage();

function initLotties() {{
  if (typeof lottie === "undefined") return;
  const cornerHost = document.getElementById("lottieCorner");
  const heroHost = document.getElementById("lottieHero");
  (STORY.lottie_keys || []).forEach((key) => {{
    const data = LOTTIE_DATA[key];
    if (!data) return;
    const cDiv = document.createElement("div");
    cDiv.className = "lottie-slot";
    cornerHost.appendChild(cDiv);
    cornerPlayers[key] = {{
      el: cDiv,
      anim: lottie.loadAnimation({{
        container: cDiv, renderer: "svg", loop: false, autoplay: false, animationData: JSON.parse(JSON.stringify(data))
      }})
    }};

    const hDiv = document.createElement("div");
    hDiv.className = "lottie-slot";
    heroHost.appendChild(hDiv);
    heroPlayers[key] = {{
      el: hDiv,
      anim: lottie.loadAnimation({{
        container: hDiv, renderer: "svg", loop: false, autoplay: false, animationData: JSON.parse(JSON.stringify(data))
      }})
    }};
  }});
}}
initLotties();

function applyGrade(grading, accent) {{
  const g = document.getElementById("gradeOverlay");
  if (grading === "alert_crimson") {{
    g.style.background = "linear-gradient(160deg, rgba(127,29,29,0.34), rgba(15,23,42,0.22))";
  }} else if (grading === "warm_amber") {{
    g.style.background = "linear-gradient(160deg, rgba(180,83,9,0.24), rgba(10,16,32,0.35))";
  }} else if (grading === "cyber_dark") {{
    g.style.background = "linear-gradient(160deg, rgba(14,165,233,0.18), rgba(17,24,39,0.42))";
  }} else if (grading === "documentary") {{
    g.style.background = "linear-gradient(180deg, rgba(15,23,42,0.20), rgba(4,7,13,0.45))";
  }} else {{
    g.style.background = "linear-gradient(160deg, rgba(20,184,166,0.20), rgba(7,13,26,0.38))";
  }}
}}

function renderModule(beat, localT, beatDur, accent) {{
  const stage = document.getElementById("moduleStage");
  const bt = beat.beat_type || "broll_drama";
  const p = beat.visual_payload || {{}};
  const enterP = easeOutCubic(localT / 0.42);
  const ySlide = ((1 - enterP) * 44).toFixed(1);

  if (bt === "broll_drama" || bt === "broll_surveillance" || bt === "news_alert") {{
    stage.innerHTML = "";
    return;
  }}

  if (bt === "lottie_callout") {{
    stage.innerHTML = `
      <div style="position:absolute; left:0; right:0; bottom:30px; opacity:${{enterP.toFixed(3)}}; transform:translateY(${{ySlide}}px);">
        <div class="glass-card" style="height:auto; padding:36px 42px; border-color:${{accent}}66;">
          <div style="font-size:22px; font-weight:800; letter-spacing:2px; color:${{accent}}; text-transform:uppercase; margin-bottom:10px;">${{escHtml(beat.kicker)}}</div>
          <div style="font-size:44px; font-weight:900; line-height:1.12; color:#fff;">${{escHtml(beat.headline)}}</div>
        </div>
      </div>`;
    return;
  }}

  if (bt === "chat_reveal") {{
    const msgs = Array.isArray(p.messages) ? p.messages : [];
    const span = Math.max(0.7, (beatDur - 0.5) / Math.max(1, msgs.length));
    let msgHtml = "";
    msgs.forEach((m, idx) => {{
      const showAt = 0.25 + idx * span;
      if (localT < showAt) return;
      const mp = easeOutBack((localT - showAt) / 0.28);
      const cls = m.side === "sent" ? "chat-sent" : "chat-recv";
      msgHtml += `
        <div class="chat-msg ${{cls}}" style="opacity:${{clamp(mp,0,1).toFixed(3)}}; transform:scale(${{(0.78 + 0.22 * mp).toFixed(3)}});">
          <div class="chat-sender">${{escHtml(m.sender || "Contacto")}}</div>
          <div>${{escHtml(m.text || "")}}</div>
        </div>`;
    }});
    if (localT < 0.25 + msgs.length * span) {{
      const dots = ".".repeat(1 + (Math.floor(localT * 4) % 3));
      msgHtml += `<div style="align-self:flex-start; padding:12px 22px; border-radius:20px; background:#1e293b; color:#94a3b8; font-size:26px; font-weight:700;">escribiendo${{dots}}</div>`;
    }}
    stage.innerHTML = `
      <div class="chat-shell" style="opacity:${{enterP.toFixed(3)}}; transform:translateY(${{ySlide}}px);">
        <div class="chat-header">
          <div>
            <div class="chat-title">${{escHtml(p.app_title || "Canal Directo")}}</div>
            <div class="chat-sub">● CIFRADO · ACTIVO</div>
          </div>
          <div style="font-size:22px; color:#94a3b8; font-weight:700;">EN VIVO</div>
        </div>
        <div class="chat-body">${{msgHtml}}</div>
      </div>`;
    return;
  }}

  if (bt === "data_chart") {{
    const labels = Array.isArray(p.labels) && p.labels.length ? p.labels : ["Q1", "Q2", "Q3", "Q4"];
    const values = Array.isArray(p.values) && p.values.length ? p.values.map(Number) : [20, 48, 76, 94];
    const maxV = Math.max(1, ...values);
    const emp = Number.isFinite(Number(p.emphasize_idx)) ? Number(p.emphasize_idx) : values.length - 1;
    const unit = p.unit || "%";
    const chartType = p.chart_type || "bars";

    let svgBody = "";
    if (chartType === "line") {{
      const pts = values.map((v, i) => {{
        const x = 110 + (i * 660) / Math.max(1, values.length - 1);
        const y = 390 - (v / maxV) * 310;
        return [x, y, v];
      }});
      const drawP = easeOutCubic((localT - 0.2) / 1.4);
      const visPts = pts.map(([x, y]) => `${{x.toFixed(1)}},${{y.toFixed(1)}}`).join(" ");
      svgBody = `
        <polyline points="${{visPts}}" fill="none" stroke="${{accent}}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"
          stroke-dasharray="1200" stroke-dashoffset="${{((1 - drawP) * 1200).toFixed(1)}}" />`;
      pts.forEach(([x, y, v], i) => {{
        const dotP = easeOutBack((localT - (0.25 + i * 0.26)) / 0.35);
        if (dotP > 0.02) {{
          const isEmp = i === emp;
          svgBody += `
            <circle cx="${{x}}" cy="${{y}}" r="${{(isEmp ? 15 : 10) * dotP}}" fill="${{isEmp ? '#ffffff' : accent}}" stroke="${{accent}}" stroke-width="5"/>
            <text x="${{x}}" y="${{y - 26}}" text-anchor="middle" fill="#ffffff" font-size="28" font-weight="800" opacity="${{clamp(dotP,0,1)}}">${{Math.round(v * clamp(dotP,0,1))}}${{escHtml(unit)}}</text>
            <text x="${{x}}" y="445" text-anchor="middle" fill="#94a3b8" font-size="25" font-weight="700">${{escHtml(labels[i] || "")}}</text>`;
        }}
      }});
    }} else {{
      const n = values.length;
      const colW = 720 / n;
      const barW = Math.min(115, colW * 0.58);
      values.forEach((v, i) => {{
        const barP = easeOutCubic((localT - (0.18 + i * 0.2)) / 0.75);
        const h = (v / maxV) * 310 * barP;
        const x = 95 + i * colW + (colW - barW) / 2;
        const y = 390 - h;
        const isEmp = i === emp;
        const fill = isEmp ? accent : "rgba(148, 163, 184, 0.45)";
        const valNow = Math.round(v * barP);
        svgBody += `
          <rect x="${{x.toFixed(1)}}" y="${{y.toFixed(1)}}" width="${{barW.toFixed(1)}}" height="${{Math.max(4, h).toFixed(1)}}" rx="14" fill="${{fill}}"/>
          <text x="${{(x + barW / 2).toFixed(1)}}" y="${{(y - 18).toFixed(1)}}" text-anchor="middle" fill="${{isEmp ? accent : '#f8fafc'}}" font-size="30" font-weight="900">${{valNow}}${{escHtml(unit)}}</text>
          <text x="${{(x + barW / 2).toFixed(1)}}" y="448" text-anchor="middle" fill="#cbd5e1" font-size="25" font-weight="700">${{escHtml(labels[i] || "")}}</text>`;
      }});
    }}

    stage.innerHTML = `
      <div class="glass-card" style="opacity:${{enterP.toFixed(3)}}; transform:translateY(${{ySlide}}px); border-color:${{accent}}55;">
        <div style="font-size:22px; font-weight:800; color:${{accent}}; letter-spacing:2px; text-transform:uppercase;">${{escHtml(p.subtitle || "DATOS EN VIVO")}}</div>
        <div style="font-size:40px; font-weight:900; margin:10px 0 26px;">${{escHtml(p.title || beat.headline)}}</div>
        <svg viewBox="0 0 880 480" style="width:100%; height:560px; overflow:visible;">
          <line x1="60" y1="390" x2="830" y2="390" stroke="rgba(255,255,255,0.22)" stroke-width="2"/>
          <line x1="60" y1="235" x2="830" y2="235" stroke="rgba(255,255,255,0.08)" stroke-width="2" stroke-dasharray="8 8"/>
          <line x1="60" y1="80" x2="830" y2="80" stroke="rgba(255,255,255,0.08)" stroke-width="2" stroke-dasharray="8 8"/>
          ${{svgBody}}
        </svg>
      </div>`;
    return;
  }}

  if (bt === "code_diff") {{
    const rem = Array.isArray(p.removed) ? p.removed : ["- render_static(dur=12.0)"];
    const add = Array.isArray(p.added) ? p.added : ["+ render_gpu_amf(fps=24)"];
    const phase = clamp(localT / 1.4, 0, 1);
    const remOp = clamp(1.0 - Math.max(0, (phase - 0.35) * 1.1), 0.25, 1.0);
    let linesHtml = "";
    rem.forEach((ln) => {{
      linesHtml += `<div class="code-line code-rem" style="opacity:${{remOp.toFixed(2)}}; text-decoration:${{phase > 0.5 ? 'line-through' : 'none'}};">- ${{escHtml(ln)}}</div>`;
    }});
    add.forEach((ln, idx) => {{
      const ap = easeOutCubic((localT - (0.38 + idx * 0.25)) / 0.55);
      if (ap > 0.02) {{
        const chars = Math.max(1, Math.floor(ln.length * ap));
        linesHtml += `<div class="code-line code-add" style="opacity:${{ap.toFixed(2)}}; transform:translateX(${{((1-ap)*24).toFixed(1)}}px);">+ ${{escHtml(ln.slice(0, chars))}}</div>`;
      }}
    }});
    stage.innerHTML = `
      <div class="glass-card" style="background:#0b101b; opacity:${{enterP.toFixed(3)}}; transform:translateY(${{ySlide}}px); border-color:${{accent}}55;">
        <div class="code-titlebar">
          <div class="mac-dot" style="background:#ff5f57;"></div>
          <div class="mac-dot" style="background:#febc2e;"></div>
          <div class="mac-dot" style="background:#28c840;"></div>
          <div style="margin-left:14px; font-family:monospace; font-size:24px; color:#94a3b8;">${{escHtml(p.filename || "engine.py")}}</div>
        </div>
        ${{linesHtml}}
      </div>`;
    return;
  }}

  if (bt === "terminal_run") {{
    const cmd = String(p.prompt || "hyperframes render --fps 24");
    const typeP = clamp(localT / 1.1, 0, 1);
    const shownCmd = cmd.slice(0, Math.floor(cmd.length * typeP));
    const cursor = (Math.floor(localT * 3) % 2 === 0) ? "█" : " ";
    const logs = Array.isArray(p.logs) ? p.logs : ["[OK] Pipeline inicializado"];
    let logsHtml = "";
    logs.forEach((lg, i) => {{
      const lp = easeOutCubic((localT - (1.0 + i * 0.48)) / 0.35);
      if (lp > 0.02) {{
        logsHtml += `<div class="term-log" style="opacity:${{lp.toFixed(2)}}; transform:translateY(${{((1-lp)*16).toFixed(1)}}px);">${{escHtml(lg)}}</div>`;
      }}
    }});
    const barP = clamp((localT - 0.8) / Math.max(1.2, beatDur - 1.2), 0, 1);
    stage.innerHTML = `
      <div class="glass-card" style="background:#06090f; opacity:${{enterP.toFixed(3)}}; transform:translateY(${{ySlide}}px); border-color:${{accent}}66;">
        <div class="code-titlebar">
          <div class="mac-dot" style="background:#ff5f57;"></div>
          <div class="mac-dot" style="background:#febc2e;"></div>
          <div class="mac-dot" style="background:#28c840;"></div>
          <div style="margin-left:14px; font-family:monospace; font-size:23px; color:#64748b;">TERMINAL · GPU STREAM</div>
        </div>
        <div class="term-cmd">$ ${{escHtml(shownCmd)}}<span style="color:#fff;">${{cursor}}</span></div>
        ${{logsHtml}}
        <div style="position:absolute; left:40px; right:40px; bottom:38px;">
          <div style="display:flex; justify-content:space-between; font-family:monospace; font-size:22px; color:#94a3b8; margin-bottom:10px;">
            <span>PROGRESO</span><span>${{Math.round(barP * 100)}}%</span>
          </div>
          <div style="height:14px; border-radius:7px; background:#1e293b; overflow:hidden;">
            <div style="height:100%; width:${{(barP * 100).toFixed(1)}}%; background:${{accent}};"></div>
          </div>
        </div>
      </div>`;
    return;
  }}

  if (bt === "flow_diagram") {{
    const nodes = Array.isArray(p.nodes) && p.nodes.length ? p.nodes : [
      {{ title: "1. Captura", detail: "Entrada en tiempo real" }},
      {{ title: "2. Proceso IA", detail: "Análisis y composición" }},
      {{ title: "3. Salida 9:16", detail: "Render GPU 1080x1920" }}
    ];
    let nodesHtml = "";
    const activeIdx = Math.floor((localT / Math.max(0.8, beatDur - 0.4)) * nodes.length) % nodes.length;
    nodes.slice(0, 4).forEach((nd, i) => {{
      const np = easeOutCubic((localT - i * 0.25) / 0.4);
      const isActive = i === activeIdx;
      const borderCol = isActive ? accent : "rgba(255,255,255,0.14)";
      const bgCol = isActive ? "rgba(43, 240, 200, 0.14)" : "rgba(15, 23, 42, 0.9)";
      nodesHtml += `
        <div class="flow-node" style="opacity:${{np.toFixed(3)}}; border-color:${{borderCol}}; background:${{bgCol}};">
          <div>
            <div class="flow-node-title" style="color:${{isActive ? accent : '#fff'}};">${{escHtml(nd.title)}}</div>
            <div class="flow-node-sub">${{escHtml(nd.detail)}}</div>
          </div>
          <div style="width:20px; height:20px; border-radius:50%; background:${{isActive ? accent : '#334155'}}; box-shadow:${{isActive ? '0 0 18px ' + accent : 'none'}};"></div>
        </div>`;
      if (i < nodes.slice(0, 4).length - 1) {{
        const dotPos = ((localT * 1.8) % 1) * 34;
        nodesHtml += `
          <div style="height:44px; display:flex; justify-content:center; position:relative;">
            <div style="width:4px; height:100%; background:linear-gradient(180deg, ${{accent}}, #334155);"></div>
            <div style="position:absolute; top:${{dotPos.toFixed(1)}}px; width:14px; height:14px; border-radius:50%; background:${{accent}}; box-shadow:0 0 14px ${{accent}};"></div>
          </div>`;
      }}
    }});
    stage.innerHTML = `
      <div class="glass-card" style="opacity:${{enterP.toFixed(3)}}; transform:translateY(${{ySlide}}px); border-color:${{accent}}44; display:flex; flex-direction:column; justify-content:center;">
        <div style="font-size:24px; font-weight:800; color:${{accent}}; letter-spacing:2px; margin-bottom:26px;">${{escHtml(p.title || "ARQUITECTURA")}}</div>
        ${{nodesHtml}}
      </div>`;
    return;
  }}

  if (bt === "kinetic_stat") {{
    const targetVal = Number(p.value != null ? p.value : 99.2);
    const decimals = Number(p.decimals || 0);
    const countP = easeOutCubic((localT - 0.12) / 1.35);
    const curVal = (targetVal * countP).toFixed(decimals);
    const circ = 2 * Math.PI * 195;
    const fillFrac = clamp((targetVal > 100 ? 0.92 : targetVal / 100) * countP, 0.08, 1.0);
    stage.innerHTML = `
      <div class="glass-card" style="opacity:${{enterP.toFixed(3)}}; transform:translateY(${{ySlide}}px); border-color:${{accent}}55; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center;">
        <div style="position:relative; width:440px; height:440px; display:flex; align-items:center; justify-content:center;">
          <svg viewBox="0 0 440 440" style="position:absolute; inset:0; transform:rotate(-90deg);">
            <circle cx="220" cy="220" r="195" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="20"/>
            <circle cx="220" cy="220" r="195" fill="none" stroke="${{accent}}" stroke-width="20" stroke-linecap="round"
              stroke-dasharray="${{circ.toFixed(1)}}" stroke-dashoffset="${{(circ * (1 - fillFrac)).toFixed(1)}}"/>
          </svg>
          <div>
            <div style="font-size:108px; font-weight:900; letter-spacing:-2px; color:#fff; font-variant-numeric:tabular-nums;">${{escHtml(p.prefix || "")}}${{curVal}}${{escHtml(p.suffix || "")}}</div>
          </div>
        </div>
        <div style="font-size:38px; font-weight:900; color:${{accent}}; margin-top:24px; letter-spacing:1px;">${{escHtml(p.label || beat.headline)}}</div>
        <div style="font-size:26px; color:#cbd5e1; margin-top:10px;">${{escHtml(p.sub || "")}}</div>
      </div>`;
    return;
  }}

  stage.innerHTML = "";
}}

window.__seek = function(t) {{
  const beats = STORY.beats || [];
  let bIdx = beats.length - 1;
  for (let i = 0; i < beats.length; i++) {{
    if (t >= beats[i].start_sec && t <= beats[i].end_sec) {{
      bIdx = i;
      break;
    }}
  }}
  const beat = beats[Math.max(0, bIdx)] || {{}};
  const bStart = Number(beat.start_sec || 0);
  const bDur = Math.max(1.0, Number(beat.duration_sec || 4.0));
  const localT = Math.max(0, t - bStart);
  const accent = beat.accent_color || "#2BF0C8";

  // Top HUD
  const numStr = String(bIdx + 1).padStart(2, "0") + "/" + String(Math.max(1, beats.length)).padStart(2, "0");
  document.getElementById("hudBeatLabel").textContent = numStr + " · " + (beat.kicker || "ESCENA").toUpperCase();
  const secInt = Math.floor(t);
  const mm = String(Math.floor(secInt / 60)).padStart(2, "0");
  const ss = String(secInt % 60).padStart(2, "0");
  document.getElementById("hudClock").textContent = mm + ":" + ss;
  document.getElementById("hudRecDot").style.opacity = (Math.floor(t * 2.5) % 2 === 0) ? "1" : "0.35";

  // Bottom Timeline Progress
  const tot = Math.max(1, Number(STORY.total_duration || 30));
  document.getElementById("bottomProgressFill").style.width = (clamp(t / tot, 0, 1) * 100).toFixed(2) + "%";
  document.getElementById("bottomProgressFill").style.background = `linear-gradient(90deg, ${{accent}}, #38bdf8)`;

  // Headline
  const hEnter = easeOutCubic(localT / 0.35);
  document.getElementById("headlineKicker").textContent = beat.kicker || ("BEAT " + numStr);
  document.getElementById("headlineKicker").style.color = accent;
  document.getElementById("headlineKicker").style.borderColor = accent + "88";
  document.getElementById("headlineKicker").style.background = accent + "24";
  document.getElementById("headlineTitle").textContent = beat.headline || STORY.title || "";
  document.getElementById("headlineZone").style.opacity = hEnter.toFixed(3);
  document.getElementById("headlineZone").style.transform = `translateY(${{((1 - hEnter) * 26).toFixed(1)}}px)`;
  document.getElementById("headlineRule").style.background = accent;
  document.getElementById("headlineRule").style.transform = `scaleX(${{hEnter.toFixed(3)}})`;

  // B-Roll Media Visibility + Ken Burns / Camera Shake
  const imgEl = document.getElementById("brollImg");
  const vidEl = document.getElementById("brollVid");
  const mSrc = beat.media_src || "";
  const mKind = beat.media_kind || "none";
  if (mKind === "video" && mSrc) {{
    imgEl.style.display = "none";
    vidEl.style.display = "block";
    if (currentMediaSrc !== mSrc) {{
      currentMediaSrc = mSrc;
      vidEl.src = mSrc;
    }}
    if (vidEl.readyState >= 1 && vidEl.duration > 0.2) {{
      const targetVt = localT % vidEl.duration;
      if (Math.abs(vidEl.currentTime - targetVt) > 0.04) {{
        vidEl.currentTime = targetVt;
      }}
    }}
  }} else if (mKind === "image" && mSrc) {{
    vidEl.style.display = "none";
    imgEl.style.display = "block";
    if (currentMediaSrc !== mSrc) {{
      currentMediaSrc = mSrc;
      imgEl.src = mSrc;
    }}
  }} else {{
    imgEl.style.display = "none";
    vidEl.style.display = "none";
  }}

  // Grading + Camera Rig
  applyGrade(beat.grading || "noir_teal", accent);
  const prog = clamp(localT / bDur, 0, 1);
  const cam = beat.camera_motion || "zoom_in";
  let camScale = 1.05 + 0.12 * prog;
  let camX = 0, camY = 0, camRot = 0;
  if (cam === "pan_left") {{ camScale = 1.12; camX = 36 - 72 * prog; }}
  else if (cam === "pan_right") {{ camScale = 1.12; camX = -36 + 72 * prog; }}
  else if (cam === "dolly_zoom") {{ camScale = 1.02 + 0.22 * prog; }}
  else if (cam === "camera_shake") {{
    camScale = 1.10;
    camX = Math.sin(t * 9.3) * 9 + Math.sin(t * 17.7) * 4;
    camY = Math.cos(t * 8.1) * 7 + Math.sin(t * 14.3) * 3;
    camRot = Math.sin(t * 6.5) * 0.6;
  }} else if (cam === "editorial_flash") {{
    const pHit = easeOutCubic(localT / 0.45);
    camScale = 1.16 - 0.08 * pHit + 0.06 * prog;
  }}
  const isCardBeat = !["broll_drama", "broll_surveillance", "news_alert"].includes(beat.beat_type);
  const rigEl = document.getElementById("cameraRig");
  rigEl.style.transform = `translate(${{camX.toFixed(1)}}px, ${{camY.toFixed(1)}}px) scale(${{camScale.toFixed(4)}}) rotate(${{camRot.toFixed(2)}}deg)`;
  rigEl.style.filter = isCardBeat ? "brightness(0.32)" : "brightness(0.88) contrast(1.06)";

  // Transitions in first 0.35s
  const tr = beat.transition_in || "crossfade";
  const trOverlay = document.getElementById("transitionOverlay");
  if (localT < 0.35 && bIdx > 0) {{
    const tp = clamp(localT / 0.35, 0, 1);
    if (tr === "flash_white") {{
      trOverlay.style.background = "radial-gradient(circle at 50% 45%, #ffffff, rgba(255,235,205,0.9))";
      trOverlay.style.opacity = ((1 - tp) * 0.88).toFixed(3);
    }} else if (tr === "glitch_cut") {{
      trOverlay.style.background = (Math.floor(localT * 40) % 2 === 0) ? "rgba(43,240,200,0.22)" : "rgba(239,68,68,0.22)";
      trOverlay.style.opacity = ((1 - tp) * 0.75).toFixed(3);
    }} else {{
      trOverlay.style.background = "#04070d";
      trOverlay.style.opacity = ((1 - tp) * 0.55).toFixed(3);
    }}
  }} else {{
    trOverlay.style.opacity = "0";
  }}

  // Lottie Rendering
  const lottieKey = beat.lottie_badge || "none";
  const isHeroLottie = beat.beat_type === "lottie_callout";
  const cHost = document.getElementById("lottieCorner");
  const hHost = document.getElementById("lottieHero");
  Object.values(cornerPlayers).forEach(p => p.el.style.display = "none");
  Object.values(heroPlayers).forEach(p => p.el.style.display = "none");

  if (lottieKey !== "none" && cornerPlayers[lottieKey]) {{
    if (isHeroLottie && heroPlayers[lottieKey]) {{
      cHost.style.display = "none";
      hHost.style.display = "block";
      const obj = heroPlayers[lottieKey];
      obj.el.style.display = "block";
      const fr = obj.anim.frameRate || 30;
      const totF = Math.max(1, obj.anim.totalFrames || 60);
      obj.anim.goToAndStop((localT * fr) % totF, true);
    }} else {{
      hHost.style.display = "none";
      cHost.style.display = "flex";
      cHost.style.borderColor = accent + "66";
      const obj = cornerPlayers[lottieKey];
      obj.el.style.display = "block";
      const fr = obj.anim.frameRate || 30;
      const totF = Math.max(1, obj.anim.totalFrames || 60);
      obj.anim.goToAndStop((localT * fr) % totF, true);
    }}
  }} else {{
    cHost.style.display = "none";
    hHost.style.display = "none";
  }}

  // HUD Overlays: Camcorder, Radar Box, News Ticker
  const hud = beat.hud_overlay || "none";
  const camHud = document.getElementById("camcorderHud");
  camHud.style.display = (hud === "camcorder" || beat.beat_type === "broll_surveillance") ? "block" : "none";
  document.getElementById("camTcTxt").textContent = "TC 00:" + mm + ":" + ss;

  const rBox = document.getElementById("radarBox");
  if ((hud === "radar_focus" || beat.highlight_box) && !isCardBeat) {{
    const hb = beat.highlight_box || {{ x: 0.22, y: 0.26, w: 0.56, h: 0.28, label: "FOCO CLAVE" }};
    const rLeft = clamp(Number(hb.x || 0.2), 0.08, 0.68) * 1080;
    const rTop = clamp(Number(hb.y || 0.26), 0.22, 0.42) * 1920;
    const rW = Math.min(1000 - rLeft, clamp(Number(hb.w || 0.55), 0.22, 0.84) * 1080);
    const rH = Math.min(1150 - rTop, clamp(Number(hb.h || 0.28), 0.14, 0.32) * 1920);
    rBox.style.display = "block";
    rBox.style.left = rLeft.toFixed(0) + "px";
    rBox.style.top = rTop.toFixed(0) + "px";
    rBox.style.width = rW.toFixed(0) + "px";
    rBox.style.height = Math.max(160, rH).toFixed(0) + "px";
    rBox.style.borderColor = accent;
    document.getElementById("radarTag").textContent = (hb.label || "FOCO CLAVE").toUpperCase();
    document.getElementById("radarTag").style.background = accent;
    const scanY = ((localT * 0.7) % 1) * 100;
    document.getElementById("radarScanLine").style.top = scanY.toFixed(1) + "%";
  }} else {{
    rBox.style.display = "none";
  }}

  const ntBar = document.getElementById("newsTickerBar");
  if (hud === "news_ticker" || beat.beat_type === "news_alert") {{
    ntBar.style.display = "flex";
    const tTxt = document.getElementById("ntText");
    const baseStr = (beat.ticker_text || beat.headline || "").toUpperCase() + "  ·  EN DIRECTO  ·  " + (beat.kicker || "");
    tTxt.textContent = baseStr + "   •   " + baseStr;
    const scrollPx = Math.max(0, localT - 0.85) * 95;
    tTxt.style.transform = `translateX(${{(- (scrollPx % 680)).toFixed(1)}}px)`;
  }} else {{
    ntBar.style.display = "none";
  }}

  // Specialized Visual Module
  renderModule(beat, localT, bDur, accent);

  // Active Multi-Voice Speaker Indicator
  let activeDlg = null;
  for (const d of (STORY.dialogues || [])) {{
    if (t >= d.start_sec && t <= d.end_sec) {{ activeDlg = d; break; }}
  }}
  const spPill = document.getElementById("speakerPill");
  if (activeDlg) {{
    const spCol = activeDlg.accent_color || accent;
    spPill.style.opacity = "1";
    spPill.style.borderColor = spCol;
    const av = document.getElementById("speakerAvatar");
    av.style.background = spCol;
    av.textContent = (activeDlg.speaker_name || "V").slice(0, 1).toUpperCase();
    document.getElementById("speakerName").textContent = (activeDlg.speaker_name || "VOZ").toUpperCase();
    document.getElementById("speakerRole").textContent = (activeDlg.archetype || "NARRADOR").toUpperCase();
    const bars = document.querySelectorAll("#voiceWave .wave-bar");
    bars.forEach((b, i) => {{
      const h = 10 + 28 * Math.abs(Math.sin(t * 14 + i * 1.1));
      b.style.height = h.toFixed(1) + "px";
      b.style.background = spCol;
    }});
  }} else {{
    spPill.style.opacity = "0";
  }}
}};

window.__seekAsync = function(t) {{
  window.__seek(t);
  const vid = document.getElementById("brollVid");
  if (vid && vid.style.display === "block" && vid.seeking) {{
    return new Promise((resolve) => {{
      let done = false;
      const fin = () => {{ if (!done) {{ done = true; resolve(true); }} }};
      vid.addEventListener("seeked", fin, {{ once: true }});
      setTimeout(fin, 120);
    }});
  }}
  return Promise.resolve(true);
}};
</script>
</body>
</html>"""


def build_stage_html(
    title: str,
    characters: List[Dict[str, Any]],
    scenes: List[Dict[str, Any]],
    dialogue_timeline: List[Dict[str, Any]],
    total_duration: float,
) -> str:
    """Backward-compatible wrapper converting simple scenes into beat structure."""
    beats = []
    for idx, sc in enumerate(scenes):
        beats.append({
            "beat_id": idx + 1,
            "beat_type": sc.get("beat_type") or "broll_drama",
            "headline": sc.get("stage_caption") or sc.get("headline") or title,
            "kicker": f"ESCENA 0{idx + 1}",
            "camera_motion": sc.get("camera_motion") or "zoom_in",
            "transition_in": sc.get("transition_in") or "flash_white",
            "grading": sc.get("grading") or "noir_teal",
            "accent_color": sc.get("accent_color") or "#2BF0C8",
            "lottie_badge": sc.get("lottie_badge") or "sparkles",
            "hud_overlay": sc.get("hud_overlay") or "none",
            "start_sec": sc.get("start_sec", 0.0),
            "end_sec": sc.get("end_sec", total_duration),
            "duration_sec": sc.get("duration_sec", total_duration),
        })
    return build_motion_stage_html(
        title=title,
        characters=characters,
        beats=beats,
        dialogue_timeline=dialogue_timeline,
        beat_media_rel={},
        lottie_keys=[],
        total_duration=total_duration,
        has_vendor_gsap=False,
        has_vendor_lottie=False,
    )


def export_studio_stage_project(
    studio_id: str,
    title: str,
    characters: List[Dict[str, Any]],
    beats: List[Dict[str, Any]],
    dialogue_timeline: List[Dict[str, Any]],
    beat_media: Dict[int, Dict[str, Any]],
    total_dur: float,
    audio_src_path: Optional[str],
) -> str:
    """Writes self-contained HyperFrames-compatible HTML5 stage + B-Roll + Lottie assets into storage/studio_hf/<id>/."""
    proj_dir = STUDIO_HF_DIR / studio_id
    assets_dir = proj_dir / "assets"
    vendor_dir = assets_dir / "vendor"
    lottie_dir = assets_dir / "lottie"
    assets_dir.mkdir(parents=True, exist_ok=True)
    vendor_dir.mkdir(parents=True, exist_ok=True)
    lottie_dir.mkdir(parents=True, exist_ok=True)

    if audio_src_path and Path(audio_src_path).exists():
        shutil.copy2(audio_src_path, assets_dir / "voiceover.m4a")

    vendors = get_hf_vendor_paths()
    has_gsap = False
    has_lottie = False
    if vendors.get("gsap"):
        shutil.copy2(vendors["gsap"], vendor_dir / "gsap.min.js")
        has_gsap = True
    if vendors.get("lottie"):
        shutil.copy2(vendors["lottie"], vendor_dir / "lottie.min.js")
        has_lottie = True

    # Copy fetched B-Roll images/videos locally into project assets/
    beat_media_rel: Dict[int, Dict[str, Any]] = {}
    for idx, info in (beat_media or {}).items():
        src_p = info.get("path")
        kind = info.get("kind", "none")
        if src_p and Path(src_p).exists() and kind in ("image", "video"):
            ext = Path(src_p).suffix.lower() or (".mp4" if kind == "video" else ".jpg")
            dest_name = f"broll_{idx}{ext}"
            shutil.copy2(src_p, assets_dir / dest_name)
            beat_media_rel[idx] = {"kind": kind, "rel_path": f"assets/{dest_name}"}
        else:
            beat_media_rel[idx] = {"kind": "none", "rel_path": ""}

    # Bundle required Lottie JSONs synchronously into assets/lottie_bundle.js (avoids file:// CORS)
    unique_lotties: List[str] = []
    for b in beats:
        lk = (b.get("lottie_badge") or "none").strip()
        if lk != "none" and lk not in unique_lotties:
            unique_lotties.append(lk)

    lottie_bundle: Dict[str, Any] = {}
    for lk in unique_lotties:
        ldata = get_lottie_json(lk)
        if ldata:
            lottie_bundle[lk] = ldata
            (lottie_dir / f"{lk}.json").write_text(json.dumps(ldata), encoding="utf-8")

    (assets_dir / "lottie_bundle.js").write_text(
        f"window.__LOTTIE_ASSETS = {json.dumps(lottie_bundle, ensure_ascii=False)};\n",
        encoding="utf-8",
    )

    stage_html = build_motion_stage_html(
        title=title,
        characters=characters,
        beats=beats,
        dialogue_timeline=dialogue_timeline,
        beat_media_rel=beat_media_rel,
        lottie_keys=list(lottie_bundle.keys()),
        total_duration=total_dur,
        has_vendor_gsap=has_gsap,
        has_vendor_lottie=has_lottie,
    )
    (proj_dir / "index.html").write_text(stage_html, encoding="utf-8")
    return str(proj_dir)


def export_hyperframes_drama_project(
    studio_id: str,
    stage_html: str,
    total_dur: float,
    audio_src_path: Optional[str],
) -> str:
    """Saves editable HTML5 stage composition + assets into storage/studio_hf/<id>/."""
    proj_dir = STUDIO_HF_DIR / studio_id
    assets_dir = proj_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    if audio_src_path and Path(audio_src_path).exists():
        shutil.copy2(audio_src_path, assets_dir / "voiceover.m4a")
    (proj_dir / "index.html").write_text(stage_html, encoding="utf-8")
    return str(proj_dir)


def render_html_stage_to_mp4(
    stage_html_path: str,
    audio_path: str,
    ass_path: str,
    out_mp4_path: str,
    total_duration: float,
    fps: int = 20,
    progress_callback=None,
) -> None:
    """Captures 720x1280 frames deterministically into FFmpeg lanczos 1080x1920 without BrokenPipeError."""
    encoder_name, encoder_args = get_best_h264_encoder()
    escaped_ass = str(Path(ass_path).resolve()).replace("\\", "/").replace(":", "\\:")

    # Probe exact audio stream length so video pipe stops cleanly before audio ends (prevents BrokenPipeError)
    actual_audio_dur = _probe_media_duration(audio_path, fallback=total_duration)
    render_duration = max(1.0, min(float(total_duration), actual_audio_dur) if actual_audio_dur > 0 else float(total_duration))
    last_t = max(0.05, render_duration - (0.5 / float(fps)))
    total_frames = max(2, int(math.floor(last_t * fps)) + 1)

    cmd = [
        FFMPEG_PATH,
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "-framerate", str(fps),
        "-i", "-",
        "-i", str(audio_path),
        "-vf", f"scale=1080:1920:flags=lanczos,subtitles='{escaped_ass}'",
        "-r", str(fps),
        *encoder_args,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "160k",
        "-t", f"{render_duration:.3f}",
        "-movflags", "+faststart",
        str(out_mp4_path),
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    stage_url = Path(stage_html_path).resolve().as_uri()

    broken_pipe_hit = False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=CHROME_PATH,
                headless=True,
                args=[
                    "--disable-dev-shm-usage",
                    "--autoplay-policy=no-user-gesture-required",
                ],
            )
            page = browser.new_page(viewport={"width": 720, "height": 1280}, device_scale_factor=1)
            page.goto(stage_url, wait_until="load")

            for i in range(total_frames):
                t = min(last_t, round(i / float(fps), 4))
                page.evaluate(f"window.__seekAsync({t})")
                jpg_bytes = page.screenshot(type="jpeg", quality=88)
                try:
                    proc.stdin.write(jpg_bytes)
                except BrokenPipeError:
                    broken_pipe_hit = True
                    print(f"[STAGE RENDERER] Pipe closed cleanly at frame {i}/{total_frames}")
                    break

                if progress_callback and (i % 40 == 0 or i == total_frames - 1):
                    pct = 55 + int((i / max(1, total_frames - 1)) * 40)
                    progress_callback(pct, f"Renderizando Motion Graphics 1080x1920 ({i + 1}/{total_frames} frames)...")

            browser.close()
    finally:
        if proc.stdin:
            try:
                proc.stdin.flush()
            except Exception:
                pass
            try:
                proc.stdin.close()
            except Exception:
                pass

    stderr_bytes = proc.stderr.read() if proc.stderr else b""
    rc = proc.wait(timeout=180)
    if rc != 0:
        err = stderr_bytes.decode("utf-8", errors="ignore")
        raise RuntimeError(f"FFmpeg stage encode error ({rc}): {err}")
    if broken_pipe_hit:
        print("[STAGE RENDERER] Recovered cleanly after early pipe close; MP4 verified rc=0.")
