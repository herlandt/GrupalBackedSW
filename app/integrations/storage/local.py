"""Adaptador de almacenamiento para desarrollo: guarda en disco local.

Los archivos se sirven en `/media/...` (ver StaticFiles en app/main.py).
"""

from pathlib import Path

from app.core.config import settings


class LocalStorage:
    async def save(self, *, key: str, data: bytes, content_type: str) -> str:
        path = Path(settings.local_media_dir) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"/media/{key}"
