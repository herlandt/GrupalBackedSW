"""Puerto de almacenamiento de archivos (contrato). Devuelve la URL pública."""

from typing import Protocol


class StoragePort(Protocol):
    async def save(self, *, key: str, data: bytes, content_type: str) -> str: ...
