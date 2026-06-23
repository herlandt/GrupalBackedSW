"""Tests del submódulo Usuarios (CU-01): registro, login, perfil y reset."""

from httpx import AsyncClient

from tests.conftest import FakeEmail

REGISTRO = {"nombre": "Ana López", "email": "ana@example.com", "password": "secret123"}


async def test_register_login_me(client: AsyncClient) -> None:
    r = await client.post("/api/v1/auth/register", json=REGISTRO)
    assert r.status_code == 201
    assert r.json()["email"] == "ana@example.com"
    assert r.json()["rol"] == "ESTUDIANTE"

    r = await client.post(
        "/api/v1/auth/login",
        data={"username": REGISTRO["email"], "password": REGISTRO["password"]},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]

    r = await client.get("/api/v1/usuarios/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "ana@example.com"


async def test_register_email_duplicado(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=REGISTRO)
    r = await client.post("/api/v1/auth/register", json=REGISTRO)
    assert r.status_code == 409


async def test_login_credenciales_invalidas(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=REGISTRO)
    r = await client.post(
        "/api/v1/auth/login", data={"username": REGISTRO["email"], "password": "incorrecta"}
    )
    # CU-01: credenciales inválidas -> 401 (autenticación), no 409.
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"


async def _registrar_y_token(client: AsyncClient) -> str:
    await client.post("/api/v1/auth/register", json=REGISTRO)
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": REGISTRO["email"], "password": REGISTRO["password"]},
    )
    return str(r.json()["access_token"])


async def test_logout_cu01(client: AsyncClient) -> None:
    token = await _registrar_y_token(client)
    r = await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    # Requiere sesión: sin token, 401.
    assert (await client.post("/api/v1/auth/logout")).status_code == 401


async def test_editar_preferencias_cu01(client: AsyncClient) -> None:
    token = await _registrar_y_token(client)
    cab = {"Authorization": f"Bearer {token}"}
    r = await client.patch(
        "/api/v1/usuarios/me",
        json={"preferencias": {"tema": "oscuro", "idioma": "es"}},
        headers=cab,
    )
    assert r.status_code == 200
    assert r.json()["preferencias"] == {"tema": "oscuro", "idioma": "es"}
    # Persisten al releer el perfil.
    r = await client.get("/api/v1/usuarios/me", headers=cab)
    assert r.json()["preferencias"]["tema"] == "oscuro"


async def test_me_requiere_autenticacion(client: AsyncClient) -> None:
    r = await client.get("/api/v1/usuarios/me")
    assert r.status_code == 401


async def test_password_reset_flow(client: AsyncClient, fake_email: FakeEmail) -> None:
    await client.post("/api/v1/auth/register", json=REGISTRO)

    r = await client.post("/api/v1/auth/password-reset/request", json={"email": REGISTRO["email"]})
    assert r.status_code == 202
    assert len(fake_email.messages) == 1

    token = fake_email.messages[-1]["body"].split("token=")[-1].strip()
    r = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "nuevaclave123"},
    )
    assert r.status_code == 200

    r = await client.post(
        "/api/v1/auth/login",
        data={"username": REGISTRO["email"], "password": "nuevaclave123"},
    )
    assert r.status_code == 200
