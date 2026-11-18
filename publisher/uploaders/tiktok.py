from pathlib import Path
from typing import Dict, Any, Optional
import httpx


class TikTokPublisher:
    """Official TikTok Login Kit OAuth v2 & Content Posting API integration (Inbox 1-Tap Public via FILE_UPLOAD)."""

    TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
    INIT_INBOX_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
    USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name,avatar_url"

    async def exchange_code(self, client_key: str, client_secret: str, code: str, redirect_uri: str, code_verifier: Optional[str] = None) -> Dict[str, Any]:
        """Exchanges OAuth authorization code for TikTok access_token + refresh_token."""
        payload = {
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            payload["code_verifier"] = code_verifier
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                self.TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=payload,
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

    # Reglas de TikTok: cada chunk entre 5 MB y 64 MB; el último puede llegar a 128 MB.
    # Archivos <= 64 MB se suben completos en un solo chunk.
    MAX_CHUNK_SIZE = 64 * 1024 * 1024
    MAX_CHUNKS = 1000

    @classmethod
    def _plan_chunks(cls, size: int) -> tuple:
        """Devuelve (chunk_size, total_chunk_count) según la Media Transfer Guide."""
        if size <= 0:
            raise ValueError("El video está vacío.")
        if size <= cls.MAX_CHUNK_SIZE:
            return size, 1
        chunk_size = cls.MAX_CHUNK_SIZE
        total_chunks = size // chunk_size
        if total_chunks > cls.MAX_CHUNKS:
            raise ValueError(f"El video es demasiado grande para TikTok ({size} bytes).")
        return chunk_size, total_chunks

    async def upload_file_to_inbox(self, access_token: str, video_file_path: str) -> Dict[str, Any]:
        """Uploads local MP4 bytes directly to TikTok Creator Inbox. User gets mobile notification and posts publicly in 1 tap."""
        path = Path(video_file_path)
        if not path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {video_file_path}")
        size = path.stat().st_size
        chunk_size, total_chunks = self._plan_chunks(size)

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        payload = {
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            }
        }
        async with httpx.AsyncClient(timeout=600.0) as client:
            r = await client.post(self.INIT_INBOX_URL, headers=headers, json=payload)
            if r.status_code != 200:
                raise RuntimeError(f"TikTok Inbox Init error: {r.text}")

            data = r.json().get("data", {})
            publish_id = data.get("publish_id")
            upload_url = data.get("upload_url")
            if not upload_url:
                raise RuntimeError(f"TikTok no devolvió upload_url: {r.text}")

            with path.open("rb") as fh:
                for index in range(total_chunks):
                    start = index * chunk_size
                    # El último chunk absorbe el resto del archivo (hasta 128 MB).
                    end = size - 1 if index == total_chunks - 1 else start + chunk_size - 1
                    length = end - start + 1
                    fh.seek(start)
                    chunk = fh.read(length)
                    if len(chunk) != length:
                        raise RuntimeError(f"Lectura incompleta del video en el chunk {index + 1}/{total_chunks}.")

                    put_headers = {
                        "Content-Type": "video/mp4",
                        "Content-Length": str(length),
                        "Content-Range": f"bytes {start}-{end}/{size}",
                    }
                    r_put = await client.put(upload_url, headers=put_headers, content=chunk)
                    if r_put.status_code not in (200, 201, 204, 206):
                        raise RuntimeError(
                            f"Error subiendo MP4 a TikTok (chunk {index + 1}/{total_chunks}): "
                            f"{r_put.status_code} {r_put.text}"
                        )

            return {
                "platform": "tiktok",
                "remote_id": str(publish_id),
                "status": "draft_inbox",
                "message": "Video subido a tu bandeja de entrada de TikTok. Abre la notificación en tu móvil y toca Publicar.",
            }


tiktok_publisher = TikTokPublisher()
