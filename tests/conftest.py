"""Fixtures compartidas de pytest.

Estrategia de DB: base de test separada (`tesisguard_test`). El esquema se crea
con `create_all` (idempotente) y cada test corre dentro de una transacción que se
revierte al final, garantizando aislamiento. Todo en el loop selector (Windows).
"""

import asyncio
import sys
import warnings
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models.registry  # noqa: F401  -> registra TODAS las tablas en Base.metadata
from app.core.config import settings
from app.core.database import get_db
from app.core.enums import RolUsuario
from app.core.security import hash_password
from app.integrations.factory import get_email_port, get_payment_gateway
from app.integrations.payments.port import CheckoutSession, CheckoutStatus, WebhookEvent
from app.main import app
from app.models.base import Base
from app.modules.administracion.usuarios.models import Usuario

test_engine = create_async_engine(settings.test_database_url, poolclass=NullPool)
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """psycopg async requiere SelectorEventLoop en Windows (igual que en runtime)."""
    if sys.platform == "win32":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    """Sesión por test dentro de una transacción que se revierte al final."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # idempotente
    conn = await test_engine.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()


@pytest.fixture(autouse=True)
def _override_db(db_session: AsyncSession) -> AsyncGenerator[None]:
    """Hace que la app use la sesión de test (sin commitear)."""

    async def _get_test_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db
    yield
    app.dependency_overrides.clear()


class FakeEmail:
    """Adaptador de correo de test: captura los mensajes en memoria."""

    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def send(self, *, to: str, subject: str, body: str) -> None:
        self.messages.append({"to": to, "subject": subject, "body": body})


@pytest.fixture
def fake_email() -> AsyncGenerator[FakeEmail]:
    fake = FakeEmail()
    app.dependency_overrides[get_email_port] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_email_port, None)


class FakePaymentGateway:
    """Pasarela de pago de test: no llama a Stripe. Recuerda el último checkout
    y simula un webhook 'completado' para ese pago."""

    def __init__(self) -> None:
        self.last_metadata: dict[str, str] = {}

    async def create_checkout_session(
        self,
        *,
        amount_cents: int,
        currency: str,
        metadata: dict[str, str],
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession:
        self.last_metadata = metadata
        return CheckoutSession(id="cs_test_fake", url="https://stripe.test/checkout/fake")

    async def retrieve_checkout_session(self, session_id: str) -> CheckoutStatus:
        return CheckoutStatus(
            payment_status="paid", payment_intent_id="pi_test_1", metadata=self.last_metadata
        )

    async def parse_webhook_event(self, payload: bytes, sig_header: str) -> WebhookEvent:
        return WebhookEvent(
            id="evt_test_1",
            type="checkout.session.completed",
            checkout_session_id="cs_test_fake",
            payment_intent_id="pi_test_1",
            metadata=self.last_metadata,
        )


@pytest.fixture
def fake_gateway() -> AsyncGenerator[FakePaymentGateway]:
    gateway = FakePaymentGateway()
    app.dependency_overrides[get_payment_gateway] = lambda: gateway
    yield gateway
    app.dependency_overrides.pop(get_payment_gateway, None)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """Cliente HTTP async que habla con la app en memoria (sin red real)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def estudiante_token(client: AsyncClient) -> str:
    """Registra e inicia sesión como estudiante; devuelve su token."""
    await client.post(
        "/api/v1/auth/register",
        json={"nombre": "Estudiante", "email": "estu@example.com", "password": "secret123"},
    )
    r = await client.post(
        "/api/v1/auth/login", data={"username": "estu@example.com", "password": "secret123"}
    )
    return str(r.json()["access_token"])


@pytest.fixture
async def estudiante2_token(client: AsyncClient) -> str:
    """Segundo estudiante, para probar el aislamiento entre usuarios (IDOR)."""
    await client.post(
        "/api/v1/auth/register",
        json={"nombre": "Estudiante 2", "email": "estu2@example.com", "password": "secret123"},
    )
    r = await client.post(
        "/api/v1/auth/login", data={"username": "estu2@example.com", "password": "secret123"}
    )
    return str(r.json()["access_token"])


@pytest.fixture
async def admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    """Crea un administrador (el registro solo crea estudiantes) y devuelve su token."""
    db_session.add(
        Usuario(
            nombre="Admin",
            email="admin@example.com",
            password_hash=hash_password("secret123"),
            rol=RolUsuario.ADMINISTRADOR,
        )
    )
    await db_session.flush()
    r = await client.post(
        "/api/v1/auth/login", data={"username": "admin@example.com", "password": "secret123"}
    )
    return str(r.json()["access_token"])
