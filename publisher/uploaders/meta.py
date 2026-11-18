import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx


class MetaPublisher:
    """Official Meta Graph API v21.0 publisher for Facebook Pages and Instagram Reels (direct binary upload supported)."""

    BASE_URL = "https://graph.facebook.com/v21.0"

    async def exchange_long_lived_token(self, app_id: str, app_secret: str, short_token: str) -> str:
        """Exchanges a 2h Meta User Token for a ~60-day token (pages retrieved from /me/accounts become permanent)."""
        if not (app_id and app_secret and short_token):
            return short_token
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                f"{self.BASE_URL}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "fb_exchange_token": short_token,
                },
            )
            if r.status_code == 200:
                return r.json().get("access_token") or short_token
        return short_token

    async def verify_account_token(self, account_id: str, access_token: str) -> Dict[str, Any]:
        """Checks live validity of a Facebook Page or Instagram Business Account token."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{self.BASE_URL}/{account_id}",
                params={"fields": "id,name,username", "access_token": access_token},
            )
            if r.status_code != 200:
                raise RuntimeError(f"Token Meta expirado o revocado: {r.text}")
            return r.json()

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
        """Publishes a public Facebook Page Reel uploading the local MP4 binary directly."""
        path = Path(video_file_path)
        if not path.exists():
            raise FileNotFoundError(f"Archivo de video no encontrado: {video_file_path}")
        video_bytes = path.read_bytes()
        file_size = len(video_bytes)

        async with httpx.AsyncClient(timeout=180.0) as client:
            init_url = f"{self.BASE_URL}/{page_id}/video_reels"
            r_init = await client.post(
                init_url, data={"upload_phase": "start", "access_token": page_access_token}
            )
            if r_init.status_code != 200:
                raise RuntimeError(f"Error iniciando Facebook Reel: {r_init.text}")

            init_data = r_init.json()
            video_id = init_data.get("video_id")
            upload_url = init_data.get("upload_url")

            headers = {
                "Authorization": f"OAuth {page_access_token}",
                "offset": "0",
                "file_size": str(file_size),
                "Content-Type": "application/octet-stream",
            }
            r_up = await client.post(upload_url, headers=headers, content=video_bytes)
            if r_up.status_code != 200:
                raise RuntimeError(f"Error subiendo video binario a Facebook: {r_up.text}")

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
        self,
        ig_user_id: str,
        access_token: str,
        video_public_url: Optional[str] = None,
        caption: str = "",
        video_file_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Publishes a public Instagram Reel via direct Resumable Binary Upload (no VPS required) or public HTTPS URL."""
        use_resumable = bool(video_file_path and Path(video_file_path).exists())
        if not use_resumable and not (video_public_url and video_public_url.startswith("https://")):
            raise RuntimeError(
                "No se encontró el archivo local MP4 ni una URL HTTPS pública para subir el Reel de Instagram."
            )

        async with httpx.AsyncClient(timeout=180.0) as client:
            init_url = f"{self.BASE_URL}/{ig_user_id}/media"
            init_payload: Dict[str, Any] = {
                "media_type": "REELS",
                "caption": caption,
                "share_to_feed": "true",
                "access_token": access_token,
            }
            if use_resumable:
                init_payload["upload_type"] = "resumable"
            else:
                init_payload["video_url"] = video_public_url

            r_init = await client.post(init_url, data=init_payload)
            if r_init.status_code != 200:
                raise RuntimeError(f"Error creando contenedor Instagram Reel: {r_init.text}")

            init_data = r_init.json()
            creation_id = init_data.get("id")
            if use_resumable:
                rupload_uri = init_data.get("uri") or f"https://rupload.facebook.com/ig-api-upload/v21.0/{creation_id}"
                video_bytes = Path(video_file_path).read_bytes()
                r_up = await client.post(
                    rupload_uri,
                    headers={
                        "Authorization": f"OAuth {access_token}",
                        "offset": "0",
                        "file_size": str(len(video_bytes)),
                        "Content-Type": "video/mp4",
                    },
                    content=video_bytes,
                )
                if r_up.status_code != 200:
                    raise RuntimeError(f"Error subiendo binario MP4 directo a Instagram: {r_up.text}")

            status_url = f"{self.BASE_URL}/{creation_id}?fields=status_code,status&access_token={access_token}"
            for _ in range(30):
                await asyncio.sleep(4.0)
                r_status = await client.get(status_url)
                if r_status.status_code == 200:
                    status = r_status.json().get("status_code")
                    if status == "FINISHED":
                        break
                    if status == "ERROR":
                        raise RuntimeError(f"Meta reportó error procesando el Reel: {r_status.text}")

            r_pub = await client.post(
                f"{self.BASE_URL}/{ig_user_id}/media_publish",
                data={"creation_id": creation_id, "access_token": access_token},
            )
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
