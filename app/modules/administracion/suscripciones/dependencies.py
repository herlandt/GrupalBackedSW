"""Dependencias del submódulo Suscripciones (gating por suscripción activa)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.core.database import DbDep
from app.modules.administracion.suscripciones.models import Suscripcion
from app.modules.administracion.suscripciones.repository import SuscripcionRepository
from app.modules.administracion.usuarios.dependencies import CurrentUser


async def require_suscripcion_activa(user: CurrentUser, db: DbDep) -> Suscripcion:
    """Exige una suscripción activa y vigente. La usarán los Sprints 2-3."""
    suscripcion = await SuscripcionRepository(db).activa_de_usuario(user.id)
    ahora = datetime.now(UTC).replace(tzinfo=None)
    if suscripcion is None or (suscripcion.fecha_fin is not None and suscripcion.fecha_fin < ahora):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Necesitas una suscripción activa para acceder a esta función.",
        )
    return suscripcion


SuscripcionActiva = Annotated[Suscripcion, Depends(require_suscripcion_activa)]
