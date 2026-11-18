import httpx
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlmodel import Session, select
from app.db import engine
from app.models import PostMetric, PostTarget, SocialAccount

async def collect_instagram_metrics(ig_user_id: str, media_id: str, access_token: str) -> Dict[str, int]:
    """Fetches views, likes, comments, and shares for an Instagram Reel."""
    url = f"https://graph.facebook.com/v21.0/{media_id}/insights?metric=views,reach,likes,comments,shares,saved&access_token={access_token}"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json().get("data", [])
                stats = {"views": 0, "likes": 0, "comments": 0, "shares": 0}
                for item in data:
                    name = item.get("name")
                    val = item.get("values", [{}])[0].get("value", 0)
                    if name in stats:
                        stats[name] = val
                    elif name == "reach" and stats["views"] == 0:
                        stats["views"] = val
                return stats
    except Exception as e:
        print(f"[STATS ERROR] Instagram metrics failed: {e}")
    return {"views": 0, "likes": 0, "comments": 0, "shares": 0}

async def update_all_metrics_job():
    """Background cron job running on the VPS or local backend collecting statistics every 3 hours."""
    with Session(engine) as session:
        targets = session.exec(select(PostTarget).where(PostTarget.status == "published")).all()
        for t in targets:
            if not t.remote_post_id:
                continue
            
            # Fetch matching account token
            acc = session.exec(select(SocialAccount).where(SocialAccount.platform == t.platform)).first()
            if not acc or not acc.access_token_enc:
                continue

            metrics = {"views": 0, "likes": 0, "comments": 0, "shares": 0}
            if t.platform == "instagram":
                metrics = await collect_instagram_metrics(acc.account_id, t.remote_post_id, acc.access_token_enc)

            metric_record = PostMetric(
                post_target_id=t.id,
                platform=t.platform,
                views=metrics.get("views", 0),
                likes=metrics.get("likes", 0),
                comments=metrics.get("comments", 0),
                shares=metrics.get("shares", 0),
                recorded_at=datetime.now(timezone.utc)
            )
            session.add(metric_record)
        session.commit()
