"""Lógica de negocio — submódulo etica (CU-12)."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import AuditService
from app.core.enums import EstadoAlertaEtica, EstadoEticaTesis, RolUsuario
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

    async def crear_alerta_si_nueva(
        self, version_id: int, tipo: str, fragmento: str | None
    ) -> AlertaEtica | None:
        """Crea la alerta solo si no existe ya una del mismo tipo para la versión.

        La usa el motor de análisis al reanalizar una versión, para no duplicar alertas.
        """
        if await self.alertas.existe_por_version_tipo(version_id, tipo):
            return None
        return await self.crear_alerta(version_id, tipo, fragmento)

    async def crear_alerta(self, version_id: int, tipo: str, fragmento: str | None) -> AlertaEtica:
        """Abre una alerta (PENDIENTE), marca la tesis EN_REVISION y notifica a estudiante+admins.

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

        # CU-12 (postcondición): el sistema actualiza el estado de la tesis afectada.
        documento = await self.alertas.documento_de_version(version_id)
        if documento is not None and documento.estado_etico == EstadoEticaTesis.LIMPIO:
            documento.estado_etico = EstadoEticaTesis.EN_REVISION
            await self.db.flush()

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

        # CU-12 (paso 6 + postcondición): recalcular el estado ÉTICO de la tesis a partir de
        # TODAS sus alertas (no solo la recién resuelta), para no "limpiar" un documento que
        # aún tiene alertas pendientes o confirmadas en otra versión/tipo.
        documento = await self.alertas.documento_de_version(alerta.version_id)
        estado_tesis: EstadoEticaTesis | None = None
        if documento is not None:
            estados = await self.alertas.estados_de_documento(documento.id)
            if any(e == EstadoAlertaEtica.CONFIRMADA for e in estados):
                estado_tesis = EstadoEticaTesis.OBSERVADA
            elif any(
                e in (EstadoAlertaEtica.PENDIENTE, EstadoAlertaEtica.EN_REVISION) for e in estados
            ):
                estado_tesis = EstadoEticaTesis.EN_REVISION
            else:
                estado_tesis = EstadoEticaTesis.LIMPIO
            documento.estado_etico = estado_tesis
            await self.db.flush()

        await self.audit.log(
            actor_id=admin.id,
            accion="ALERTA_ETICA_RESUELTA",
            entidad="alerta_etica",
            entidad_id=alerta.id,
            metadata={
                "estado": nuevo_estado.value,
                "estado_tesis": estado_tesis.value if estado_tesis else None,
            },
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
