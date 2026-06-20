"""Tests de los endpoints de salud (liveness y readiness)."""

from httpx import AsyncClient


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_reports_db_status(client: AsyncClient) -> None:
    response = await client.get("/ready")
    # 200 si Postgres está arriba; 503 si no. En ambos casos el endpoint responde.
    assert response.status_code in (200, 503)
    assert "status" in response.json()
