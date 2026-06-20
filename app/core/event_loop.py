"""Selección del event loop de asyncio según la plataforma.

En Windows, el driver async de PostgreSQL (psycopg 3) no funciona con el
`ProactorEventLoop` por defecto: necesita un `SelectorEventLoop`. Esta fábrica
se usa como `loop_factory`:
  - en Alembic:  `asyncio.run(..., loop_factory=new_event_loop)`
  - en uvicorn:  `--loop app.core.event_loop:new_event_loop` (ver `run.py`)
"""

import asyncio
import selectors
import sys


def new_event_loop() -> asyncio.AbstractEventLoop:
    """Crea un event loop compatible con psycopg (SelectorEventLoop en Windows)."""
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()
