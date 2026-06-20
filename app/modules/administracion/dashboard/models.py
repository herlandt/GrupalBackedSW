"""Modelos ORM — submódulo dashboard (Administración del Sistema).

CU-06, RF-08/09. Submódulo *read-only*: no define tablas propias. Lee de
`usuario`, `suscripcion`, `plan_suscripcion`, `pago` y `avance_formal` (ya
registradas en `app/models/registry.py`). No requiere migración Alembic.
"""
