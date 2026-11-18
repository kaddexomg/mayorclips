import httpx
from typing import Dict, Any

class TikTokPublisher:
    """Official TikTok Content Posting API integration."""

    INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
    DIRECT_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"

    async def upload_to_inbox(self, access_token: str, video_url: str, title: str) -> Dict[str, Any]:
        """Uploads video to Creator Inbox. The user receives a notification in TikTok and posts it publicly with 1 tap."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "source_info": {
                "source": "PULL_FROM_URL",
                "video_url": video_url
            }
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.post(self.INIT_URL, headers=headers, json=payload)
            if r.status_code != 200:
                # If inbox endpoint not allowed, fallback to response info
                raise RuntimeError(f"TikTok Inbox Upload failed: {r.text}")
            
            publish_id = r.json().get("data", {}).get("publish_id")
            return {
                "platform": "tiktok",
                "remote_id": publish_id,
                "status": "draft_inbox",
                "message": "Video enviado exitosamente a la bandeja de entrada de tu app TikTok. Abre la notificación para publicar en público."
            }

tiktok_publisher = TikTokPublisher()
