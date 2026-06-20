"""Lógica de negocio — submódulo etica (CU-12)."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import AuditService
from app.core.enums import EstadoAlertaEtica, RolUsuario
from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.integrations.email.port import EmailPort
from app.modules.administracion.usuarios.models import Usuario
from app.modules.auditoria_documental.etica.models import AlertaEtica
from app.modules.auditoria_documental.etica.repository import AlertaEticaRepository


class EticaService:
    def __init__(self, db: AsyncSession, email: EmailPort) -> None:
        self.db = db
        self.alertas = AlertaEticaRepository(db)
        self.audit = AuditService(db)
        self.email = email

    async def crear_alerta(self, version_id: int, tipo: str, fragmento: str | None) -> AlertaEtica:
        """Abre una alerta (PENDIENTE) y notifica al estudiante y a los admins.

        Lo invoca el motor de análisis al detectar un posible incumplimiento.
        """
        dueno_id = await self.alertas.dueno_de_version(version_id)
        if dueno_id is None:
            raise ResourceNotFoundError(f"VersionDocumento {version_id} no existe")

        alerta = AlertaEtica(
            version_id=version_id,
            tipo=tipo,
            fragmento=fragmento,
            estado=EstadoAlertaEtica.PENDIENTE,
        )
        await self.alertas.add(alerta)

        await self.audit.log(
            actor_id=None,
            accion="ALERTA_ETICA_CREADA",
            entidad="alerta_etica",
            entidad_id=alerta.id,
            metadata={"tipo": tipo, "version_id": version_id},
        )

        # Notificar al estudiante dueño.
        estudiante = await self.db.get(Usuario, dueno_id)
        if estudiante is not None:
            await self.email.send(
                to=estudiante.email,
                subject="Alerta de integridad académica — TesisGuard",
                body=(
                    f"Se detectó un posible incumplimiento ético ({tipo}) en tu documento. "
                    "Un administrador la revisará y te informaremos la decisión."
                ),
            )

        # Notificar a los administradores.
        for admin in await self._admins():
            await self.email.send(
                to=admin.email,
                subject="Nueva alerta de ética pendiente — TesisGuard",
                body=f"Hay una alerta de ética PENDIENTE (#{alerta.id}, tipo {tipo}) por revisar.",
            )
        return alerta

    async def listar(self) -> Sequence[AlertaEtica]:
        return await self.alertas.listar_todas()

    async def obtener(self, alerta_id: int) -> AlertaEtica:
        return await self.alertas.get_or_404(alerta_id)

    async def mis_alertas(self, usuario: Usuario) -> Sequence[AlertaEtica]:
        return await self.alertas.por_estudiante(usuario.id)

    async def resolver(
        self, alerta_id: int, admin: Usuario, nuevo_estado: EstadoAlertaEtica
    ) -> AlertaEtica:
        """El admin cambia el estado, se registra quién decidió, bitácora y aviso."""
        if nuevo_estado == EstadoAlertaEtica.PENDIENTE:
            raise BusinessRuleError("No se puede volver a PENDIENTE una alerta")
        alerta = await self.alertas.get_or_404(alerta_id)

        alerta.estado = nuevo_estado
        alerta.decision_admin_id = admin.id
        await self.db.flush()

        await self.audit.log(
            actor_id=admin.id,
            accion="ALERTA_ETICA_RESUELTA",
            entidad="alerta_etica",
            entidad_id=alerta.id,
            metadata={"estado": nuevo_estado.value},
        )

        dueno_id = await self.alertas.dueno_de_version(alerta.version_id)
        estudiante = await self.db.get(Usuario, dueno_id) if dueno_id is not None else None
        if estudiante is not None:
            await self.email.send(
                to=estudiante.email,
                subject="Resolución de tu alerta de integridad — TesisGuard",
                body=f"Tu alerta de ética #{alerta.id} fue marcada como {nuevo_estado.value}.",
            )
        return alerta

    async def _admins(self) -> Sequence[Usuario]:
        result = await self.db.execute(
            select(Usuario).where(
                Usuario.rol == RolUsuario.ADMINISTRADOR, Usuario.activo.is_(True)
            )
        )
        return result.scalars().all()
