from pathlib import Path
from typing import Dict, Any
import httpx


class TikTokPublisher:
    """Official TikTok Login Kit OAuth v2 & Content Posting API integration (Inbox 1-Tap Public via FILE_UPLOAD)."""

    TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
    INIT_INBOX_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
    USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name,avatar_url"

    async def exchange_code(self, client_key: str, client_secret: str, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchanges OAuth authorization code for TikTok access_token + refresh_token."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                self.TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "client_key": client_key,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code != 200 or not data.get("access_token"):
                raise RuntimeError(f"Error TikTok OAuth token: {r.text}")
            return data

    async def refresh_token(self, client_key: str, client_secret: str, refresh_token_str: str) -> Dict[str, Any]:
        """Refreshes an expired TikTok access token silently using stored refresh_token."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                self.TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "client_key": client_key,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token_str,
                },
            )
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code != 200 or not data.get("access_token"):
                raise RuntimeError(f"Error refrescando token TikTok: {r.text}")
            return data

    async def verify_token(self, access_token: str) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(self.USER_INFO_URL, headers=headers)
            if r.status_code != 200:
                raise RuntimeError(f"Token TikTok inválido o expirado: {r.text}")
            return r.json().get("data", {}).get("user", {})

    async def upload_file_to_inbox(self, access_token: str, video_file_path: str) -> Dict[str, Any]:
        """Uploads local MP4 bytes directly to TikTok Creator Inbox. User gets mobile notification and posts publicly in 1 tap."""
        path = Path(video_file_path)
        if not path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {video_file_path}")
        video_bytes = path.read_bytes()
        size = len(video_bytes)

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        payload = {
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": size,
                "total_chunk_count": 1,
            }
        }
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(self.INIT_INBOX_URL, headers=headers, json=payload)
            if r.status_code != 200:
                raise RuntimeError(f"TikTok Inbox Init error: {r.text}")

            data = r.json().get("data", {})
            publish_id = data.get("publish_id")
            upload_url = data.get("upload_url")
            if not upload_url:
                raise RuntimeError(f"TikTok no devolvió upload_url: {r.text}")

            put_headers = {
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes 0-{size - 1}/{size}",
            }
            r_put = await client.put(upload_url, headers=put_headers, content=video_bytes)
            if r_put.status_code not in (200, 201, 204):
                raise RuntimeError(f"Error subiendo MP4 a TikTok: {r_put.status_code} {r_put.text}")

            return {
                "platform": "tiktok",
                "remote_id": str(publish_id),
                "status": "draft_inbox",
                "message": "Video subido a tu bandeja de entrada de TikTok. Abre la notificación en tu móvil y toca Publicar.",
            }


tiktok_publisher = TikTokPublisher()
