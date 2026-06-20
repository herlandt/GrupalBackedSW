"""OCR de PDFs ESCANEADOS con AWS Textract (fallback cuando el PDF no trae capa de texto).

Sube el PDF a un bucket S3 dedicado, lanza un job ASÍNCRONO de detección de texto
(multipágina), espera el resultado y devuelve el texto reconocido. Solo se usa como
fallback cuando `pypdf` no extrae texto. Limpia el archivo de S3 al terminar (no se dejan
datos del estudiante). Devuelve "" ante cualquier fallo (degradación silenciosa hacia el
error estándar "documento sin texto legible"). Requiere `settings.textract_bucket`.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.integrations.aws.session import get_aws_client

logger = logging.getLogger(__name__)

_INTERVALO_S = 3.0
_TIMEOUT_S = 300.0


def ocr_pdf(path: Path) -> str:
    """Extrae texto de un PDF escaneado vía Textract async. "" si no hay bucket o falla."""
    bucket = settings.textract_bucket
    if not bucket:
        return ""
    s3: Any = get_aws_client("s3")
    textract: Any = get_aws_client("textract")
    # Key ÚNICA por job: dos PDFs con el mismo nombre (p.ej. "tesis.pdf") o un reproceso
    # en paralelo no deben pisarse ni borrar el objeto del otro en el `finally`.
    clave = f"ocr/{uuid.uuid4().hex}/{path.name}"
    try:
        s3.upload_file(str(path), bucket, clave)
        inicio = textract.start_document_text_detection(
            DocumentLocation={"S3Object": {"Bucket": bucket, "Name": clave}}
        )
        texto = _recoger_texto(textract, str(inicio["JobId"]))
        logger.info("Textract OCR: %d caracteres extraídos de %s", len(texto), path.name)
        return texto
    except Exception:  # red / permisos / job fallido -> degradar a "sin texto"
        logger.exception("Textract OCR falló para %s", path.name)
        return ""
    finally:
        try:
            s3.delete_object(Bucket=bucket, Key=clave)
        except Exception:
            logger.warning("No se pudo borrar %s de S3 tras el OCR", clave)


def _recoger_texto(textract: Any, job_id: str) -> str:
    """Espera a que el job termine y junta las líneas de todas las páginas (paginado)."""
    limite = time.monotonic() + _TIMEOUT_S
    while True:
        estado = textract.get_document_text_detection(JobId=job_id)["JobStatus"]
        if estado == "SUCCEEDED":
            break
        if estado == "FAILED":
            raise RuntimeError("Textract marcó el job como FAILED")
        if time.monotonic() > limite:
            raise TimeoutError("Textract excedió el tiempo de espera")
        time.sleep(_INTERVALO_S)

    lineas: list[str] = []
    token: str | None = None
    while True:
        kwargs = {"JobId": job_id, "NextToken": token} if token else {"JobId": job_id}
        resp = textract.get_document_text_detection(**kwargs)
        lineas.extend(
            b.get("Text", "") for b in resp.get("Blocks", []) if b.get("BlockType") == "LINE"
        )
        token = resp.get("NextToken")
        if not token:
            return "\n".join(lineas)
