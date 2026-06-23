"""Tests del submódulo Monitoreo (CU-07 monitoreo, RF-08 avance formal)."""

from httpx import AsyncClient


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _id_estudiante(client: AsyncClient, admin_token: str) -> int:
    r = await client.get("/api/v1/monitoreo/estudiantes", headers=auth(admin_token))
    assert r.status_code == 200
    return int(r.json()[0]["id"])


async def test_listar_estudiantes_incluye_al_registrado(
    client: AsyncClient, admin_token: str, estudiante_token: str
) -> None:
    # estudiante_token registra "estu@example.com"; debe salir en la lista del admin
    r = await client.get("/api/v1/monitoreo/estudiantes", headers=auth(admin_token))
    assert r.status_code == 200
    emails = [e["email"] for e in r.json()]
    assert "estu@example.com" in emails
    assert r.json()[0]["nivel_general"] in {"ALTO", "MEDIO", "BAJO"}


async def test_registrar_y_aprobar_avance(
    client: AsyncClient, admin_token: str, estudiante_token: str
) -> None:
    uid = await _id_estudiante(client, admin_token)

    r = await client.post(
        f"/api/v1/monitoreo/estudiantes/{uid}/avances",
        json={"etapa": "Marco teórico"},
        headers=auth(admin_token),
    )
    assert r.status_code == 201
    avance_id = r.json()["id"]
    assert r.json()["estado"] == "PENDIENTE"

    r = await client.post(
        f"/api/v1/monitoreo/avances/{avance_id}/aprobar", headers=auth(admin_token)
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "APROBADO"
    assert r.json()["aprobado_por_id"] is not None

    # aprobar de nuevo viola la regla de negocio -> 409
    r = await client.post(
        f"/api/v1/monitoreo/avances/{avance_id}/aprobar", headers=auth(admin_token)
    )
    assert r.status_code == 409


async def test_monitoreo_requiere_autenticacion(client: AsyncClient) -> None:
    r = await client.get("/api/v1/monitoreo/estudiantes")
    assert r.status_code == 401


async def test_estudiante_no_puede_monitorear(
    client: AsyncClient, estudiante_token: str
) -> None:
    r = await client.get("/api/v1/monitoreo/estudiantes", headers=auth(estudiante_token))
    assert r.status_code == 403


async def test_detalle_estudiante_inexistente(client: AsyncClient, admin_token: str) -> None:
    r = await client.get("/api/v1/monitoreo/estudiantes/999999", headers=auth(admin_token))
    assert r.status_code == 404


async def test_detalle_estudiante_ok(
    client: AsyncClient, admin_token: str, estudiante_token: str
) -> None:
    uid = await _id_estudiante(client, admin_token)
    r = await client.get(f"/api/v1/monitoreo/estudiantes/{uid}", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["estudiante"]["email"] == "estu@example.com"
    assert r.json()["nivel_general"] in {"ALTO", "MEDIO", "BAJO"}


async def test_detalle_incluye_simulaciones_y_versiones(
    client: AsyncClient, admin_token: str, estudiante_token: str
) -> None:
    # CU-07: el detalle trae las listas de simulaciones y versiones (vacías para un alumno nuevo).
    uid = await _id_estudiante(client, admin_token)
    r = await client.get(f"/api/v1/monitoreo/estudiantes/{uid}", headers=auth(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["simulaciones"] == []
    assert body["versiones"] == []
    assert "avances" in body


async def test_exportar_estudiante_pdf(
    client: AsyncClient, admin_token: str, estudiante_token: str
) -> None:
    # CU-07: el admin descarga el reporte del estudiante en PDF.
    uid = await _id_estudiante(client, admin_token)
    r = await client.get(
        f"/api/v1/monitoreo/estudiantes/{uid}/export", headers=auth(admin_token)
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


async def test_exportar_estudiante_requiere_admin(
    client: AsyncClient, estudiante_token: str
) -> None:
    r = await client.get(
        "/api/v1/monitoreo/estudiantes/1/export", headers=auth(estudiante_token)
    )
    assert r.status_code == 403


async def test_registrar_y_rechazar_avance(
    client: AsyncClient, admin_token: str, estudiante_token: str
) -> None:
    uid = await _id_estudiante(client, admin_token)
    r = await client.post(
        f"/api/v1/monitoreo/estudiantes/{uid}/avances",
        json={"etapa": "Resultados"},
        headers=auth(admin_token),
    )
    avance_id = r.json()["id"]

    r = await client.post(
        f"/api/v1/monitoreo/avances/{avance_id}/rechazar", headers=auth(admin_token)
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "RECHAZADO"

    # rechazar de nuevo viola la regla de negocio -> 409
    r = await client.post(
        f"/api/v1/monitoreo/avances/{avance_id}/rechazar", headers=auth(admin_token)
    )
    assert r.status_code == 409


async def test_estudiante_no_puede_registrar_avance(
    client: AsyncClient, admin_token: str, estudiante_token: str
) -> None:
    uid = await _id_estudiante(client, admin_token)
    r = await client.post(
        f"/api/v1/monitoreo/estudiantes/{uid}/avances",
        json={"etapa": "X"},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 403
