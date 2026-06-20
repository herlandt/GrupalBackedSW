"""Acceso a datos del submódulo Dashboard (CU-06): agregados globales."""

from decimal import Decimal

from sqlalchemy import func, select

from app.core.enums import EstadoPago, EstadoSuscripcion
from app.core.repository import BaseRepository
from app.modules.administracion.pagos.models import Pago
from app.modules.administracion.suscripciones.models import Suscripcion
from app.modules.administracion.usuarios.models import Usuario


class DashboardRepository(BaseRepository[Usuario]):
    """Agregados de solo lectura para el panel del administrador."""

    model = Usuario

    async def total_usuarios(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(Usuario))
        return int(result.scalar_one())

    async def total_estudiantes_activos(self) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(Usuario).where(Usuario.activo.is_(True))
        )
        return int(result.scalar_one())

    async def total_suscripciones_activas(self) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(Suscripcion)
            .where(Suscripcion.estado == EstadoSuscripcion.ACTIVA)
        )
        return int(result.scalar_one())

    async def ingresos_totales(self) -> Decimal:
        """Suma de pagos en estado PAGADO (None -> 0)."""
        result = await self.db.execute(
            select(func.coalesce(func.sum(Pago.monto), 0)).where(
                Pago.estado == EstadoPago.PAGADO
            )
        )
        return Decimal(result.scalar_one())
