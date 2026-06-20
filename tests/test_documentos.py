"""Tests del submódulo Documentos (CU-08, CU-09, CU-11)."""

import io
from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from app.integrations.factory import get_analysis_queue, get_storage_port
from app.main import app
from app.modules.administracion.suscripciones.dependencies import require_suscripcion_activa


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class _FakeStorage:
    async def save(self, *, key: str, data: bytes, content_type: str) -> str:
        return f"/media/{key}"


class _FakeQueue:
    def __init__(self) -> None:
        self.encolados: list[tuple[int, int]] = []

    async def enqueue_analysis(self, *, documento_id: int, version_id: int) -> None:
        self.encolados.append((documento_id, version_id))


@pytest.fixture
def documentos_overrides() -> Iterator[_FakeQueue]:
    """Neutraliza storage, cola y gating de suscripción; limpia al terminar."""
    queue = _FakeQueue()
    app.dependency_overrides[get_storage_port] = lambda: _FakeStorage()
    app.dependency_overrides[get_analysis_queue] = lambda: queue
    app.dependency_overrides[require_suscripcion_activa] = lambda: object()
    yield queue
    app.dependency_overrides.pop(get_storage_port, None)
    app.dependency_overrides.pop(get_analysis_queue, None)
    app.dependency_overrides.pop(require_suscripcion_activa, None)


def _pdf() -> tuple[str, io.BytesIO, str]:
    return ("tesis.pdf", io.BytesIO(b"%PDF-1.4 contenido"), "application/pdf")


async def _subir(client: AsyncClient, token: str, titulo: str = "Mi tesis") -> dict[str, object]:
    r = await client.post(
        "/api/v1/documentos",
        data={"titulo": titulo},
        files={"file": _pdf()},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_subir_documento_crea_version_y_encola(
    client: AsyncClient, estudiante_token: str, documentos_overrides: _FakeQueue
) -> None:
    body = await _subir(client, estudiante_token)
    assert body["numero_version"] == 1
    assert body["estado_analisis"] == "PENDIENTE"
    assert body["formato"] == "PDF"
    assert len(documentos_overrides.encolados) == 1  # se encoló el análisis

    r = await client.get("/api/v1/documentos", headers=auth(estudiante_token))
    assert r.status_code == 200
    assert len(r.json()) == 1


async def test_subir_nueva_version_incrementa_y_encola(
    client: AsyncClient, estudiante_token: str, documentos_overrides: _FakeQueue
) -> None:
    primera = await _subir(client, estudiante_token)
    documento_id = primera["documento_id"]

    r = await client.post(
        f"/api/v1/documentos/{documento_id}/versiones",
        files={"file": _pdf()},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["numero_version"] == 2
    assert len(documentos_overrides.encolados) == 2  # se encoló de nuevo


async def test_historial_versiones(
    client: AsyncClient, estudiante_token: str, documentos_overrides: _FakeQueue
) -> None:
    primera = await _subir(client, estudiante_token)
    documento_id = primera["documento_id"]
    r = await client.get(
        f"/api/v1/documentos/{documento_id}/versiones", headers=auth(estudiante_token)
    )
    assert r.status_code == 200
    versiones = r.json()
    assert len(versiones) == 1
    assert versiones[0]["numero_version"] == 1


async def test_sin_token_devuelve_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/documentos")
    assert r.status_code == 401


async def test_admin_devuelve_403(
    client: AsyncClient, admin_token: str, documentos_overrides: _FakeQueue
) -> None:
    # Suscripción permitida por el fixture; el admin no es ESTUDIANTE -> 403.
    r = await client.get("/api/v1/documentos", headers=auth(admin_token))
    assert r.status_code == 403


async def test_sin_suscripcion_devuelve_402(
    client: AsyncClient, estudiante_token: str
) -> None:
    # Sin sobreescribir require_suscripcion_activa: el gating real responde 402.
    r = await client.post(
        "/api/v1/documentos",
        data={"titulo": "X"},
        files={"file": _pdf()},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 402


async def test_formato_invalido_devuelve_409(
    client: AsyncClient, estudiante_token: str, documentos_overrides: _FakeQueue
) -> None:
    r = await client.post(
        "/api/v1/documentos",
        data={"titulo": "X"},
        files={"file": ("notas.txt", io.BytesIO(b"texto"), "text/plain")},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 409


async def test_documento_inexistente_devuelve_404(
    client: AsyncClient, estudiante_token: str, documentos_overrides: _FakeQueue
) -> None:
    r = await client.get(
        "/api/v1/documentos/999999/versiones", headers=auth(estudiante_token)
    )
    assert r.status_code == 404


async def test_idor_documento_ajeno_devuelve_404(
    client: AsyncClient,
    estudiante_token: str,
    estudiante2_token: str,
    documentos_overrides: _FakeQueue,
) -> None:
    # estu sube un documento; estu2 NO debe poder leerlo ni versionarlo (se trata
    # como inexistente -> 404, sin revelar que pertenece a otro usuario).
    primera = await _subir(client, estudiante_token)
    documento_id = primera["documento_id"]

    r = await client.get(
        f"/api/v1/documentos/{documento_id}/versiones", headers=auth(estudiante2_token)
    )
    assert r.status_code == 404

    r = await client.post(
        f"/api/v1/documentos/{documento_id}/versiones",
        files={"file": _pdf()},
        headers=auth(estudiante2_token),
    )
    assert r.status_code == 404
