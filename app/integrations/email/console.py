"""Adaptador de correo para desarrollo: imprime el mensaje en el log.

Útil para ver enlaces de verificación/restablecimiento sin configurar SES.
"""

import logging

logger = logging.getLogger("tesisguard.email")


class ConsoleEmail:
    async def send(self, *, to: str, subject: str, body: str) -> None:
        logger.info("CORREO (dev) -> %s | asunto: %s\n%s", to, subject, body)
