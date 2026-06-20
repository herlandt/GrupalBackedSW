"""Puerto de envío de correo (contrato). El adaptador real se elige por entorno."""

from typing import Protocol


class EmailPort(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...
