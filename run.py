"""Arranque del servidor de desarrollo.

Uso:  python run.py

Usa un `loop_factory` propio (`app.core.event_loop:new_event_loop`) para forzar
el SelectorEventLoop en Windows, requerido por psycopg en modo async. Así el
servidor funciona igual con o sin recarga automática.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        loop="app.core.event_loop:new_event_loop",
    )
