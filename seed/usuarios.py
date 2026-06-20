"""Semilla de usuarios de prueba (admin + estudiante)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RolUsuario
from app.core.security import hash_password
from app.modules.administracion.usuarios.models import Usuario

USUARIOS = [
    ("Administrador", "admin@tesisguard.com", "Admin1234", RolUsuario.ADMINISTRADOR),
    ("Estudiante Demo", "estudiante@tesisguard.com", "Estudiante1234", RolUsuario.ESTUDIANTE),
]


async def seed(db: AsyncSession) -> None:
    for nombre, email, password, rol in USUARIOS:
        existe = (
            await db.execute(select(Usuario).where(Usuario.email == email))
        ).scalar_one_or_none()
        if existe is not None:
            print(f"= usuario ya existe: {email}")
            continue
        db.add(
            Usuario(
                nombre=nombre,
                email=email,
                password_hash=hash_password(password),
                rol=rol,
            )
        )
        print(f"+ usuario creado: {email} ({rol.value})")
