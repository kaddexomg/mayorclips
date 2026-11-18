import time
import httpx
from typing import Dict, Any, Optional

class MetaPublisher:
    """Official Meta Graph API publisher for Instagram Reels and Facebook Page Reels."""

    BASE_URL = "https://graph.facebook.com/v21.0"

    async def publish_instagram_reel(self, ig_user_id: str, access_token: str, video_public_url: str, caption: str) -> Dict[str, Any]:
        """Publishes a public Reel to an Instagram Creator/Business account."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. Initialize Reel Container
            init_url = f"{self.BASE_URL}/{ig_user_id}/media"
            init_payload = {
                "media_type": "REELS",
                "video_url": video_public_url,
                "caption": caption,
                "share_to_feed": True,
                "access_token": access_token
            }
            r_init = await client.post(init_url, data=init_payload)
            if r_init.status_code != 200:
                raise RuntimeError(f"Error creando contenedor Instagram Reel: {r_init.text}")
            
            creation_id = r_init.json().get("id")

            # 2. Poll for upload completion
            status_url = f"{self.BASE_URL}/{creation_id}?fields=status_code&access_token={access_token}"
            for _ in range(30):
                await asyncio.sleep(4.0)
                r_status = await client.get(status_url)
                if r_status.status_code == 200:
                    status = r_status.json().get("status_code")
                    if status == "FINISHED":
                        break
                    elif status == "ERROR":
                        raise RuntimeError(f"Meta reportó error procesando el video: {r_status.text}")

            # 3. Publish container
            pub_url = f"{self.BASE_URL}/{ig_user_id}/media_publish"
            r_pub = await client.post(pub_url, data={"creation_id": creation_id, "access_token": access_token})
            if r_pub.status_code != 200:
                raise RuntimeError(f"Error publicando contenedor Instagram: {r_pub.text}")

            media_id = r_pub.json().get("id")
            return {
                "platform": "instagram",
                "remote_id": media_id,
                "status": "published",
                "direct_url": f"https://www.instagram.com/reel/{media_id}/"
            }

    async def publish_facebook_reel(self, page_id: str, access_token: str, video_public_url: str, description: str) -> Dict[str, Any]:
        """Publishes a public Reel to a Facebook Page."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. Initialize upload session
            init_url = f"{self.BASE_URL}/{page_id}/video_reels"
            r_init = await client.post(init_url, data={"upload_phase": "start", "access_token": access_token})
            if r_init.status_code != 200:
                raise RuntimeError(f"Error iniciando Facebook Reel: {r_init.text}")
            
            video_id = r_init.json().get("video_id")
            upload_url = r_init.json().get("upload_url")

            # 2. Transfer video binary or trigger hosted URL
            pub_url = f"{self.BASE_URL}/{page_id}/video_reels"
            pub_payload = {
                "upload_phase": "finish",
                "video_id": video_id,
                "video_state": "PUBLISHED",
                "description": description,
                "video_url": video_public_url,
                "access_token": access_token
            }
            r_pub = await client.post(pub_url, data=pub_payload)
            if r_pub.status_code != 200:
                raise RuntimeError(f"Error finalizando Facebook Reel: {r_pub.text}")

            return {
                "platform": "facebook",
                "remote_id": video_id,
                "status": "published",
                "direct_url": f"https://www.facebook.com/reel/{video_id}"
            }

meta_publisher = MetaPublisher()
