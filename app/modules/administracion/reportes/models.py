"""Modelos ORM — submódulo reportes (Administración del Sistema).

CU-05 Reportes Dinámicos. Submódulo *read-only*: no define tablas propias; solo
consulta `pago`, `usuario` y `plan_suscripcion` (ya registradas en
`app/models/registry.py`). Por eso este archivo no declara ninguna clase ORM ni
requiere migración Alembic.
"""
