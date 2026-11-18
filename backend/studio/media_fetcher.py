import hashlib
import io
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx
from PIL import Image
from sqlmodel import Session

from app.config import BASE_DIR, CACHE_DIR
from app.db import engine
from app.models import AppSetting

STUDIO_MEDIA_CACHE = CACHE_DIR / "studio_media"
IMAGES_CACHE_DIR = STUDIO_MEDIA_CACHE / "images"
VIDEOS_CACHE_DIR = STUDIO_MEDIA_CACHE / "videos"
LOTTIE_ASSETS_DIR = BASE_DIR / "assets" / "lottie"
HF_BLOCKS_DIR = BASE_DIR / "assets" / "hf_blocks"

for _d in (STUDIO_MEDIA_CACHE, IMAGES_CACHE_DIR, VIDEOS_CACHE_DIR, LOTTIE_ASSETS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

_HTTP_HEADERS = {
    "User-Agent": "MayorClipsStudio/2.0 (contact@mayorclips.local)",
    "Accept": "application/json,image/*,*/*;q=0.8",
}

_STOPWORDS = {
    "en", "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "por", "para",
    "que", "con", "sin", "sobre", "entre", "como", "cuando", "donde", "quien", "hay",
    "tiene", "mas", "más", "del", "al", "se", "su", "sus", "este", "esta", "eso",
    "the", "and", "with", "from", "into", "over", "under", "about", "why", "how",
}

_SPANISH_TO_VISUAL = {
    "venezuela": "Caracas Venezuela city",
    "caracas": "Caracas city street",
    "miedo": "dark shadow night street",
    "poder": "government palace monument",
    "vigilancia": "security camera night",
    "multitud": "crowd people city plaza",
    "protesta": "street rally crowd",
    "futbol": "football stadium night",
    "fútbol": "football stadium night",
    "dinero": "currency finance bank",
    "tecnologia": "computer technology code",
    "tecnología": "computer technology code",
    "motor": "3d engine graphics workstation",
    "ciudad": "city skyline night",
    "historia": "historic archive architecture",
    "policia": "police car night lights",
    "policía": "police car night lights",
    "ia": "artificial intelligence server",
}

_SKIP_TITLE_TERMS = (
    "flag of", "coat of arms", "escudo", "bandera", "locator map", "svg",
    "signature", "autograph", "logo", "icon", "blank map", "diagram",
    "bulletin", "weekly", "gazette", "journal", "magazine", "catalogue",
    "census", "yearbook", "almanac", ".pdf", ".djvu", ".tiff",
)

LOTTIE_ALIASES: Dict[str, str] = {
    "fire": "fire.json",
    "flame": "fire.json",
    "hot": "fire.json",
    "rocket": "rocket.json",
    "launch": "rocket.json",
    "boost": "rocket.json",
    "warning": "warning.json",
    "alert": "warning.json",
    "danger": "warning.json",
    "chart_up": "chart_up.json",
    "chart": "chart_up.json",
    "growth": "chart_up.json",
    "chart_down": "chart_down.json",
    "decline": "chart_down.json",
    "eyes": "eyes.json",
    "watch": "eyes.json",
    "surveillance": "eyes.json",
    "brain": "brain.json",
    "ai": "brain.json",
    "mind": "brain.json",
    "lightning": "lightning.json",
    "power": "lightning.json",
    "energy": "lightning.json",
    "check_mark": "check_mark.json",
    "check": "check_mark.json",
    "verified": "check_mark.json",
    "globe": "globe.json",
    "world": "globe.json",
    "money_wings": "money_wings.json",
    "money": "money_wings.json",
    "finance": "money_wings.json",
    "lock": "lock.json",
    "security": "lock.json",
    "privacy": "lock.json",
    "police_light": "police_light.json",
    "police": "police_light.json",
    "siren": "police_light.json",
    "trophy": "trophy.json",
    "win": "trophy.json",
    "sparkles": "sparkles.json",
    "magic": "sparkles.json",
    "100": "100.json",
    "clapper": "clapper.json",
    "cinema": "clapper.json",
    "gear": "gear.json",
    "engine": "gear.json",
    "laptop": "laptop.json",
    "code": "laptop.json",
    "megaphone": "megaphone.json",
    "protest": "megaphone.json",
    "voice": "megaphone.json",
    "mascot_walk": "mascot_walk.json",
    "mascot": "mascot_walk.json",
    "character": "mascot_walk.json",
}

_LOTTIE_MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}


def get_pexels_api_key() -> str:
    """Reads Pexels API key from PEXELS_API_KEY env var or SQLite AppSetting('pexels_api_key')."""
    env_key = os.getenv("PEXELS_API_KEY", "").strip()
    if env_key:
        return env_key
    try:
        with Session(engine) as session:
            row = session.get(AppSetting, "pexels_api_key")
            if row and row.value and row.value.strip():
                return row.value.strip()
    except Exception:
        pass
    return ""


def _slug_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _simplify_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ0-9]+", query.lower())
    mapped: List[str] = []
    for tok in tokens:
        if tok in _SPANISH_TO_VISUAL:
            mapped.append(_SPANISH_TO_VISUAL[tok])
        elif tok not in _STOPWORDS and len(tok) >= 3:
            mapped.append(tok)
    dedup: List[str] = []
    for chunk in mapped:
        for w in chunk.split():
            if w not in dedup:
                dedup.append(w)
    return " ".join(dedup[:5]) or "city street night architecture"


def _save_verified_jpeg(raw_bytes: bytes, dest_path: Path, max_dim: int = 1280) -> Optional[str]:
    """Validates downloaded bytes via Pillow and normalizes to a crisp RGB JPEG."""
    if not raw_bytes or len(raw_bytes) < 6000:
        return None
    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            img.load()
            w, h = img.size
            if w < 360 or h < 240:
                return None
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            elif img.mode == "L":
                img = img.convert("RGB")
            if max(w, h) > max_dim:
                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(dest_path, format="JPEG", quality=88, optimize=True)
        return str(dest_path)
    except Exception:
        return None


def fetch_wikimedia_images(
    query: str,
    max_results: int = 4,
    used_paths: Optional[Set[str]] = None,
) -> List[str]:
    """Searches Wikimedia Commons for high-res real photography and caches normalized JPEGs locally."""
    import time

    clean_q = (query or "").strip()
    if not clean_q:
        clean_q = "city street night"

    q_hash = _slug_hash(f"wm2:{clean_q.lower()}")
    manifest_path = IMAGES_CACHE_DIR / f"wm_{q_hash}.json"
    if manifest_path.exists():
        try:
            cached_list = [p for p in json.loads(manifest_path.read_text(encoding="utf-8")) if Path(p).exists()]
            if cached_list:
                return cached_list
        except Exception:
            pass

    words = [w for w in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ0-9]+", clean_q) if len(w) >= 2]
    queries_to_try: List[str] = []
    for cand in [
        " ".join(words[:3]) if len(words) >= 3 else clean_q,
        " ".join(words[:2]) if len(words) >= 2 else clean_q,
        clean_q,
        _simplify_query(clean_q),
    ]:
        c = cand.strip()
        if c and c.lower() not in [x.lower() for x in queries_to_try]:
            queries_to_try.append(c)

    saved_paths: List[str] = []
    with httpx.Client(headers=_HTTP_HEADERS, timeout=12.0, follow_redirects=True) as client:
        for q_try in queries_to_try:
            if len(saved_paths) >= max_results:
                break
            try:
                resp = client.get(
                    "https://commons.wikimedia.org/w/api.php",
                    params={
                        "action": "query",
                        "generator": "search",
                        "gsrsearch": q_try,
                        "gsrnamespace": 6,
                        "gsrlimit": 12,
                        "prop": "imageinfo",
                        "iiprop": "url|mime|size",
                        "iiurlwidth": 1080,
                        "format": "json",
                    },
                )
                time.sleep(0.12)
                if resp.status_code != 200 or "json" not in (resp.headers.get("content-type") or "").lower():
                    continue
                pages = (resp.json().get("query") or {}).get("pages") or {}
                candidates = sorted(
                    pages.values(),
                    key=lambda p: int(p.get("index", 999)),
                )
                for p in candidates:
                    if len(saved_paths) >= max_results:
                        break
                    title = (p.get("title") or "").lower()
                    if any(bad in title for bad in _SKIP_TITLE_TERMS):
                        continue
                    info = (p.get("imageinfo") or [{}])[0]
                    mime = (info.get("mime") or "").lower()
                    if mime not in ("image/jpeg", "image/png", "image/webp"):
                        continue
                    w = int(info.get("width") or 0)
                    h = int(info.get("height") or 0)
                    if w < 500 or h < 340:
                        continue
                    dl_url = info.get("thumburl") or info.get("url")
                    if not dl_url:
                        continue
                    img_file = IMAGES_CACHE_DIR / f"wm_{_slug_hash(dl_url)}.jpg"
                    if img_file.exists():
                        if str(img_file) not in saved_paths:
                            saved_paths.append(str(img_file))
                        continue
                    img_resp = client.get(dl_url)
                    time.sleep(0.06)
                    if img_resp.status_code == 200:
                        saved = _save_verified_jpeg(img_resp.content, img_file)
                        if saved and saved not in saved_paths:
                            saved_paths.append(saved)
            except Exception:
                continue

    if saved_paths:
        try:
            manifest_path.write_text(json.dumps(saved_paths), encoding="utf-8")
        except Exception:
            pass
    return saved_paths


def fetch_pexels_broll(
    query: str,
    prefer_video: bool = False,
    used_paths: Optional[Set[str]] = None,
) -> Optional[Dict[str, str]]:
    """Fetches portrait photo or MP4 video B-roll from Pexels if an API key is configured."""
    api_key = get_pexels_api_key()
    if not api_key:
        return None

    headers = {**_HTTP_HEADERS, "Authorization": api_key}
    clean_q = _simplify_query(query) or query or "cinematic dark street"

    with httpx.Client(headers=headers, timeout=15.0, follow_redirects=True) as client:
        if prefer_video:
            try:
                rv = client.get(
                    "https://api.pexels.com/videos/search",
                    params={"query": clean_q, "orientation": "portrait", "per_page": 6},
                )
                if rv.status_code == 200:
                    for vid in rv.json().get("videos", []):
                        files = [
                            vf for vf in vid.get("video_files", [])
                            if vf.get("file_type") == "video/mp4" and 480 <= int(vf.get("width") or 0) <= 1440
                        ]
                        files.sort(key=lambda vf: int(vf.get("width") or 0), reverse=True)
                        if not files:
                            continue
                        vurl = files[0].get("link")
                        if not vurl:
                            continue
                        vpath = VIDEOS_CACHE_DIR / f"px_{_slug_hash(vurl)}.mp4"
                        if vpath.exists() and (used_paths is None or str(vpath) not in used_paths):
                            return {"kind": "video", "path": str(vpath), "source": "pexels", "query": clean_q}
                        vr = client.get(vurl)
                        if vr.status_code == 200 and len(vr.content) > 25000 and len(vr.content) < 18_000_000:
                            vpath.write_bytes(vr.content)
                            return {"kind": "video", "path": str(vpath), "source": "pexels", "query": clean_q}
            except Exception:
                pass

        try:
            rp = client.get(
                "https://api.pexels.com/v1/search",
                params={"query": clean_q, "orientation": "portrait", "per_page": 6},
            )
            if rp.status_code == 200:
                for ph in rp.json().get("photos", []):
                    src = ph.get("src") or {}
                    purl = src.get("large2x") or src.get("large") or src.get("original")
                    if not purl:
                        continue
                    ipath = IMAGES_CACHE_DIR / f"px_{_slug_hash(purl)}.jpg"
                    if ipath.exists() and (used_paths is None or str(ipath) not in used_paths):
                        return {"kind": "image", "path": str(ipath), "source": "pexels", "query": clean_q}
                    ir = client.get(purl)
                    if ir.status_code == 200:
                        saved = _save_verified_jpeg(ir.content, ipath)
                        if saved:
                            return {"kind": "image", "path": saved, "source": "pexels", "query": clean_q}
        except Exception:
            pass

    return None


def fetch_visual_broll(
    query: str,
    prefer_video: bool = False,
    used_paths: Optional[Set[str]] = None,
    fallback_queries: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Fetches a real photo/video asset for a visual beat via Pexels (optional) or Wikimedia Commons."""
    px = fetch_pexels_broll(query, prefer_video=prefer_video, used_paths=used_paths)
    if px:
        if used_paths is not None and px.get("path"):
            used_paths.add(px["path"])
        return px

    tries = [query] + (fallback_queries or ["city street night lights", "modern technology server dark"])
    for q in tries:
        imgs = fetch_wikimedia_images(q, max_results=5, used_paths=used_paths)
        for p in imgs:
            if used_paths is None or p not in used_paths:
                if used_paths is not None:
                    used_paths.add(p)
                return {"kind": "image", "path": p, "source": "wikimedia", "query": q}
        if imgs:
            return {"kind": "image", "path": imgs[0], "source": "wikimedia", "query": q}

    return {"kind": "none", "path": None, "source": "none", "query": query}


def prefetch_storyboard_media(
    beats: List[Dict[str, Any]],
    topic: str = "",
    style: str = "drama",
) -> Dict[int, Dict[str, Any]]:
    """Resolves distinct visual B-roll assets for all storyboard beats serially (polite to Wikimedia API)."""
    used_paths: Set[str] = set()
    results: Dict[int, Dict[str, Any]] = {}
    fallback_q = (
        ["server room data center", "computer code screen"]
        if style in ("explainer", "data_charts")
        else ["night city street", "crowd protest plaza"]
    )

    unique_queries: List[str] = []
    for b in beats:
        q = (b.get("visual_query") or b.get("headline") or topic or "night city street").strip()
        if q not in unique_queries:
            unique_queries.append(q)

    fetched_lists: Dict[str, List[Dict[str, Any]]] = {}
    for q in unique_queries:
        items: List[Dict[str, Any]] = []
        px = fetch_pexels_broll(q, prefer_video=(style in ("drama", "history", "curiosities")), used_paths=None)
        if px:
            items.append(px)
        for p in fetch_wikimedia_images(q, max_results=4):
            items.append({"kind": "image", "path": p, "source": "wikimedia", "query": q})
        fetched_lists[q] = items

    all_pool: List[Dict[str, Any]] = []
    for items in fetched_lists.values():
        all_pool.extend(items)

    if len(all_pool) < len(beats):
        for fq in fallback_q:
            for p in fetch_wikimedia_images(fq, max_results=4):
                all_pool.append({"kind": "image", "path": p, "source": "wikimedia", "query": fq})

    for idx, b in enumerate(beats):
        q = (b.get("visual_query") or b.get("headline") or topic or "night city street").strip()
        candidates = fetched_lists.get(q, [])
        chosen = None
        for item in candidates:
            if item["path"] not in used_paths:
                chosen = item
                break
        if not chosen:
            for item in all_pool:
                if item["path"] not in used_paths:
                    chosen = item
                    break
        if not chosen and candidates:
            chosen = candidates[idx % len(candidates)]
        elif not chosen and all_pool:
            chosen = all_pool[idx % len(all_pool)]

        if chosen and chosen.get("path"):
            used_paths.add(chosen["path"])
            results[idx] = chosen
        else:
            results[idx] = {"kind": "none", "path": None, "source": "none", "query": q}

    return results


def get_lottie_json(name_or_tag: str) -> Optional[Dict[str, Any]]:
    """Loads and validates a local Lottie JSON animation by semantic tag or filename."""
    key = (name_or_tag or "").strip().lower()
    if not key or key == "none":
        return None
    filename = LOTTIE_ALIASES.get(key)
    if not filename:
        # Fuzzy match substring
        for alias, fname in LOTTIE_ALIASES.items():
            if alias in key or key in alias:
                filename = fname
                break
    if not filename:
        candidate = LOTTIE_ASSETS_DIR / f"{key}.json"
        if candidate.exists():
            filename = candidate.name
    if not filename:
        filename = "sparkles.json"

    if filename in _LOTTIE_MEMORY_CACHE:
        return _LOTTIE_MEMORY_CACHE[filename]

    fpath = LOTTIE_ASSETS_DIR / filename
    if not fpath.exists():
        return None
    try:
        data = json.loads(fpath.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "layers" in data and "fr" in data:
            _LOTTIE_MEMORY_CACHE[filename] = data
            return data
    except Exception:
        return None
    return None


def fetch_and_cache_lottie(name: str, url: str) -> Optional[Path]:
    """Downloads a Lottie JSON from an open URL, validates JSON schema, and caches under assets/lottie/."""
    clean_name = re.sub(r"[^a-z0-9_-]", "_", name.lower())
    dest = LOTTIE_ASSETS_DIR / f"{clean_name}.json"
    try:
        with httpx.Client(headers=_HTTP_HEADERS, timeout=12.0, follow_redirects=True) as client:
            r = client.get(url)
            if r.status_code != 200:
                return None
            data = r.json()
            if isinstance(data, dict) and "layers" in data and "fr" in data:
                dest.write_bytes(r.content)
                _LOTTIE_MEMORY_CACHE[dest.name] = data
                return dest
    except Exception:
        return None
    return None


def get_hf_vendor_paths() -> Dict[str, Optional[Path]]:
    """Returns local cached paths for gsap.min.js and lottie.min.js under assets/hf_blocks/vendor/."""
    vdir = HF_BLOCKS_DIR / "vendor"
    gsap = vdir / "gsap.min.js"
    lottie = vdir / "lottie.min.js"
    return {
        "gsap": gsap if gsap.exists() else None,
        "lottie": lottie if lottie.exists() else None,
    }


def list_hf_blocks() -> List[str]:
    """Lists locally cached HyperFrames registry blocks in assets/hf_blocks/compositions/."""
    cdir = HF_BLOCKS_DIR / "compositions"
    if not cdir.exists():
        return []
    blocks: List[str] = []
    for item in sorted(cdir.iterdir()):
        if item.suffix == ".html":
            blocks.append(item.stem)
        elif item.is_dir() and item.name not in ("assets", "components"):
            blocks.append(item.name)
    comp_dir = cdir / "components"
    if comp_dir.exists():
        for item in sorted(comp_dir.iterdir()):
            if item.suffix == ".html":
                blocks.append(item.stem)
    return blocks
