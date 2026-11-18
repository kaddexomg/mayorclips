import asyncio
import datetime
import re
from typing import Any, Dict, List, Optional
import httpx

TWITCH_GQL_URL = "https://gql.twitch.tv/gql"
TWITCH_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"

VIRAL_KEYWORDS = [
    "jaja", "ajja", "jiji", "kekw", "kek", "lul", "lulw", "omegalul", "hyperclap",
    "gol", "nooo", "clip", "clipea", "xd", "omg", "wtf", "god",
    "ex programa", "burro", "terrible", "epoca", "cine", "peak",
    "lmfao", "lmao", "lol", "pog", "💀", "🔥",
]

_GQL_QUERY = """query VideoCommentsByOffsetOrCursor($videoID: ID!, $contentOffsetSeconds: Int) {
  video(id: $videoID) {
    comments(contentOffsetSeconds: $contentOffsetSeconds) {
      edges {
        node {
          contentOffsetSeconds
          createdAt
          message {
            fragments {
              text
            }
          }
        }
      }
    }
  }
}"""


def _extract_twitch_video_id(video_id: str) -> Optional[str]:
    """Extracts the numeric Twitch VOD ID from a raw ID, v-prefixed ID, or VOD URL."""
    raw = str(video_id or "").strip()
    if not raw:
        return None
    m_direct = re.fullmatch(r"v?(\d+)", raw, flags=re.IGNORECASE)
    if m_direct:
        return m_direct.group(1)
    m_url = re.search(r"/(?:videos|v)/(\d+)", raw, flags=re.IGNORECASE)
    if m_url:
        return m_url.group(1)
    m_any = re.search(r"\b(\d{6,})\b", raw)
    return m_any.group(1) if m_any else None


def _extract_node_text(node: Dict[str, Any]) -> str:
    """Joins Twitch message fragments into plain text."""
    msg = node.get("message") or {}
    fragments = msg.get("fragments") or []
    raw = "".join(str(f.get("text") or "") for f in fragments if isinstance(f, dict))
    return re.sub(r"[\u034f\u200b-\u200f\ufeff]+", "", raw).strip()


def _compute_span_seconds(nodes: List[Dict[str, Any]]) -> float:
    """Computes message burst span in seconds using createdAt timestamps or contentOffsetSeconds."""
    if len(nodes) < 2:
        return 5.0
    try:
        t0 = datetime.datetime.fromisoformat(str(nodes[0]["createdAt"]).replace("Z", "+00:00")).timestamp()
        t1 = datetime.datetime.fromisoformat(str(nodes[-1]["createdAt"]).replace("Z", "+00:00")).timestamp()
        return max(0.5, abs(t1 - t0))
    except Exception:
        pass
    try:
        o0 = float(nodes[0]["contentOffsetSeconds"])
        o1 = float(nodes[-1]["contentOffsetSeconds"])
        return max(1.0, abs(o1 - o0))
    except Exception:
        return 5.0


def _score_twitch_nodes(nodes: List[Dict[str, Any]], offset_sec: float) -> Dict[str, Any]:
    """Scores Twitch comment burst density and laugh/meme/surprise emotes around an offset."""
    local_nodes = [
        n for n in nodes
        if isinstance(n, dict)
        and (
            n.get("contentOffsetSeconds") is None
            or (offset_sec - 20.0 <= float(n["contentOffsetSeconds"]) <= offset_sec + 45.0)
        )
    ]
    if not local_nodes:
        return {"count": 0, "span_sec": 0.0, "rate": 0.0, "viral_hits": 0, "score": 0.0, "sample": ""}

    span = _compute_span_seconds(local_nodes)
    rate = len(local_nodes) / span
    viral_hits = 0
    samples: List[str] = []

    for node in local_nodes:
        txt = _extract_node_text(node)
        low = txt.lower()
        if any(kw in low for kw in VIRAL_KEYWORDS):
            viral_hits += 1
        if txt and len(samples) < 4:
            samples.append(txt[:45])

    score = round(rate * 2.0 + viral_hits * 3.5 + len(local_nodes) * 0.4, 2)
    return {
        "count": len(local_nodes),
        "span_sec": round(span, 2),
        "rate": round(rate, 2),
        "viral_hits": viral_hits,
        "score": score,
        "sample": " | ".join(samples),
    }


async def scan_twitch_chat_peaks(
    video_id: str,
    duration_sec: float,
    top_k: int = 7,
    min_gap_sec: float = 180.0,
) -> List[Dict[str, Any]]:
    """Scans a Twitch VOD's chat replay via GQL without downloading video, failing gracefully to []."""
    try:
        vid = _extract_twitch_video_id(video_id)
        if not vid or not duration_sec or duration_sec <= 60 or top_k <= 0:
            return []

        num_probes = 16
        usable_start = min(120.0, duration_sec * 0.05)
        usable_end = max(usable_start + 60.0, duration_sec - 120.0)
        step = (usable_end - usable_start) / num_probes
        offsets = [usable_start + (i + 0.5) * step for i in range(num_probes)]

        headers = {
            "Client-Id": TWITCH_CLIENT_ID,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        sem = asyncio.Semaphore(4)

        async with httpx.AsyncClient(headers=headers, timeout=6.0) as client:
            async def _probe(offset: float) -> Optional[Dict[str, Any]]:
                payload = {
                    "operationName": "VideoCommentsByOffsetOrCursor",
                    "query": _GQL_QUERY,
                    "variables": {
                        "videoID": vid,
                        "contentOffsetSeconds": int(round(offset)),
                    },
                }
                async with sem:
                    try:
                        resp = await client.post(TWITCH_GQL_URL, json=payload)
                        if resp.status_code != 200:
                            return None
                        body = resp.json()
                        if not isinstance(body, dict) or body.get("errors"):
                            return None
                        video = (body.get("data") or {}).get("video")
                        if not isinstance(video, dict):
                            return None
                        edges = ((video.get("comments") or {}).get("edges")) or []
                        nodes = [e.get("node") for e in edges if isinstance(e, dict) and isinstance(e.get("node"), dict)]
                        metrics = _score_twitch_nodes(nodes, offset)
                        if metrics["count"] == 0:
                            return None
                        return {"time_sec": round(offset, 1), **metrics}
                    except Exception:
                        return None

            results = await asyncio.gather(*[_probe(off) for off in offsets])

        valid = [r for r in results if r is not None]
        valid.sort(key=lambda x: x["score"], reverse=True)

        selected: List[Dict[str, Any]] = []
        for item in valid:
            if all(abs(item["time_sec"] - s["time_sec"]) >= min_gap_sec for s in selected):
                selected.append(item)
                if len(selected) >= top_k:
                    break
        return selected
    except Exception:
        return []
