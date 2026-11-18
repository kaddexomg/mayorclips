import asyncio
import datetime
from typing import List, Dict, Any
import httpx

VIRAL_KEYWORDS = [
    "jaja", "ajja", "kekw", "lul", "lulw", "omegalul", "hyperclap",
    "gol", "nooo", "clip", "clipea", "xd", "omg", "wtf", "god",
    "ex programa", "burro", "terrible", "epoca", "cine", "peak", "💀", "🔥"
]


def _score_messages(msgs: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not msgs:
        return {"count": 0, "rate": 0.0, "viral_hits": 0, "score": 0.0, "sample": ""}

    try:
        t0 = datetime.datetime.fromisoformat(msgs[0]["created_at"].replace("Z", "+00:00")).timestamp()
        t1 = datetime.datetime.fromisoformat(msgs[-1]["created_at"].replace("Z", "+00:00")).timestamp()
        span = max(0.5, abs(t0 - t1))
    except Exception:
        span = 5.0

    rate = len(msgs) / span
    viral_hits = 0
    samples = []
    for m in msgs:
        txt = (m.get("content") or "").strip()
        low = txt.lower()
        if any(kw in low for kw in VIRAL_KEYWORDS):
            viral_hits += 1
        if txt and len(samples) < 4:
            # Clean emote markup like [emote:37226:KEKW] -> KEKW
            clean = txt.replace("[emote:", "").split(":")[-1].replace("]", "")
            samples.append(clean[:45])

    # Combined burst + emote/laugh score
    score = round(rate * 2.0 + viral_hits * 3.5 + len(msgs) * 0.4, 2)
    return {
        "count": len(msgs),
        "span_sec": round(span, 2),
        "rate": round(rate, 2),
        "viral_hits": viral_hits,
        "score": score,
        "sample": " | ".join(samples),
    }


async def scan_kick_chat_peaks(
    channel_id: str,
    start_timestamp: float,
    duration_sec: float,
    num_probes: int = 36,
    top_k: int = 8,
    min_gap_sec: float = 180.0,
) -> List[Dict[str, Any]]:
    """Scans an entire 1-10 hour Kick VOD's chat history in ~3-4 seconds with zero video download."""
    if not channel_id or not start_timestamp or duration_sec <= 60:
        return []

    # Avoid first 2 minutes and last 2 minutes where stream starts/ends
    usable_start = min(120.0, duration_sec * 0.05)
    usable_end = max(usable_start + 60.0, duration_sec - 120.0)
    step = (usable_end - usable_start) / max(1, num_probes)
    offsets = [usable_start + i * step for i in range(num_probes)]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        async def _probe(offset: float):
            iso = datetime.datetime.fromtimestamp(
                start_timestamp + offset, datetime.timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            url = f"https://kick.com/api/v2/channels/{channel_id}/messages?start_time={iso}"
            try:
                r = await client.get(url)
                if r.status_code != 200:
                    return None
                msgs = r.json().get("data", {}).get("messages", [])
                metrics = _score_messages(msgs)
                if metrics["count"] == 0:
                    return None
                return {"time_sec": round(offset, 1), **metrics}
            except Exception:
                return None

        results = await asyncio.gather(*[_probe(off) for off in offsets])

    valid = [r for r in results if r is not None]
    valid.sort(key=lambda x: x["score"], reverse=True)

    # Non-maximum suppression: space peaks out so clips aren't duplicates
    selected: List[Dict[str, Any]] = []
    for item in valid:
        if all(abs(item["time_sec"] - s["time_sec"]) >= min_gap_sec for s in selected):
            selected.append(item)
            if len(selected) >= top_k:
                break
    return selected
