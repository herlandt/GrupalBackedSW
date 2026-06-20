"""Autenticación de endpoints internos (worker de colas / servicios de confianza).

Estos endpoints no los invoca un usuario final, sino un consumidor de confianza
(p. ej. el worker que desencola los análisis de documentos). Por eso no se protegen
con JWT de usuario, sino con un secreto compartido enviado en la cabecera
``X-Internal-Token``. Falla cerrado: si el secreto no está configurado, rechaza todo.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.config import settings


async def require_internal_token(
    x_internal_token: Annotated[str | None, Header()] = None,
) -> None:
    """Exige el secreto interno. Sin él (o con uno inválido) responde 401."""
    esperado = settings.internal_api_token
    if not esperado or x_internal_token != esperado:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token interno inválido o ausente.",
        )


RequireInternalToken = Annotated[None, Depends(require_internal_token)]
