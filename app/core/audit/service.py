"""Servicio de bitácora/auditoría. Los services del dominio lo llaman para
registrar eventos sensibles (altas, cambios, pagos, etc.)."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.models import Bitacora


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log(
        self,
        *,
        accion: str,
        entidad: str,
        actor_id: int | None = None,
        entidad_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.db.add(
            Bitacora(
                actor_id=actor_id,
                accion=accion,
                entidad=entidad,
                entidad_id=entidad_id,
                metadata_=metadata,
            )
        )
        await self.db.flush()
