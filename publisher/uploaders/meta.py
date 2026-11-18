import asyncio
from pathlib import Path
import httpx
from typing import Dict, Any, List


class MetaPublisher:
    """Official Meta Graph API publisher for Instagram Reels and Facebook Page Reels."""

    BASE_URL = "https://graph.facebook.com/v21.0"

    async def discover_pages_and_ig(self, user_access_token: str) -> List[Dict[str, Any]]:
        """Queries Meta Graph API to discover user's Facebook Pages and linked Instagram Business/Creator accounts."""
        url = f"{self.BASE_URL}/me/accounts"
        params = {
            "fields": "id,name,access_token,instagram_business_account{id,username}",
            "access_token": user_access_token,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                raise RuntimeError(f"Token Meta inválido o sin permisos: {r.text}")
            return r.json().get("data", [])

    async def publish_facebook_reel_file(
        self, page_id: str, page_access_token: str, video_file_path: str, description: str
    ) -> Dict[str, Any]:
        """Publishes a public Facebook Page Reel uploading the local MP4 binary directly (no public URL needed)."""
        path = Path(video_file_path)
        if not path.exists():
            raise FileNotFoundError(f"Archivo de video no encontrado: {video_file_path}")
        video_bytes = path.read_bytes()
        file_size = len(video_bytes)

        async with httpx.AsyncClient(timeout=180.0) as client:
            # 1. Start upload session
            init_url = f"{self.BASE_URL}/{page_id}/video_reels"
            r_init = await client.post(
                init_url, data={"upload_phase": "start", "access_token": page_access_token}
            )
            if r_init.status_code != 200:
                raise RuntimeError(f"Error iniciando Facebook Reel: {r_init.text}")

            init_data = r_init.json()
            video_id = init_data.get("video_id")
            upload_url = init_data.get("upload_url")

            # 2. Binary upload directly to rupload.facebook.com
            headers = {
                "Authorization": f"OAuth {page_access_token}",
                "offset": "0",
                "file_size": str(file_size),
                "Content-Type": "application/octet-stream",
            }
            r_up = await client.post(upload_url, headers=headers, content=video_bytes)
            if r_up.status_code != 200:
                raise RuntimeError(f"Error subiendo video binario a Facebook: {r_up.text}")

            # 3. Publish Reel publicly
            r_pub = await client.post(
                init_url,
                data={
                    "upload_phase": "finish",
                    "video_id": video_id,
                    "video_state": "PUBLISHED",
                    "description": description,
                    "access_token": page_access_token,
                },
            )
            if r_pub.status_code != 200:
                raise RuntimeError(f"Error publicando Facebook Reel: {r_pub.text}")

            return {
                "platform": "facebook",
                "remote_id": str(video_id),
                "status": "published",
                "direct_url": f"https://www.facebook.com/reel/{video_id}",
            }

    async def publish_instagram_reel(
        self, ig_user_id: str, access_token: str, video_public_url: str, caption: str
    ) -> Dict[str, Any]:
        """Publishes a public Reel to an Instagram Creator/Business account (requires public HTTPS video URL)."""
        if not video_public_url or not video_public_url.startswith("https://"):
            raise RuntimeError(
                "Instagram Graph API exige una URL pública HTTPS del MP4 (configura VPS_PUBLIC_BASE_URL en .env o sube el archivo al VPS)."
            )

        async with httpx.AsyncClient(timeout=60.0) as client:
            init_url = f"{self.BASE_URL}/{ig_user_id}/media"
            init_payload = {
                "media_type": "REELS",
                "video_url": video_public_url,
                "caption": caption,
                "share_to_feed": True,
                "access_token": access_token,
            }
            r_init = await client.post(init_url, data=init_payload)
            if r_init.status_code != 200:
                raise RuntimeError(f"Error creando contenedor Instagram Reel: {r_init.text}")

            creation_id = r_init.json().get("id")
            status_url = f"{self.BASE_URL}/{creation_id}?fields=status_code&access_token={access_token}"
            for _ in range(30):
                await asyncio.sleep(4.0)
                r_status = await client.get(status_url)
                if r_status.status_code == 200:
                    status = r_status.json().get("status_code")
                    if status == "FINISHED":
                        break
                    elif status == "ERROR":
                        raise RuntimeError(f"Meta reportó error procesando el Reel: {r_status.text}")

            pub_url = f"{self.BASE_URL}/{ig_user_id}/media_publish"
            r_pub = await client.post(pub_url, data={"creation_id": creation_id, "access_token": access_token})
            if r_pub.status_code != 200:
                raise RuntimeError(f"Error publicando contenedor Instagram: {r_pub.text}")

            media_id = r_pub.json().get("id")
            return {
                "platform": "instagram",
                "remote_id": str(media_id),
                "status": "published",
                "direct_url": f"https://www.instagram.com/reel/{media_id}/",
            }


meta_publisher = MetaPublisher()
