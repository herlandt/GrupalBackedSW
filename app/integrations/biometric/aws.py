"""Adaptador REAL del servicio biométrico sobre AWS Rekognition (análisis por frame).

`analizar_imagen` envía un frame de la cámara a Rekognition `detect_faces` y traduce la
**pose** (cabeza erguida) y el **yaw** (mirar a la cámara) + apertura de ojos a
**postura** y **contacto visual** (RF-04). El análisis de video/audio completo
(Rekognition Video + Transcribe, asíncrono) queda como evolución futura.
"""

from __future__ import annotations

import anyio

from app.integrations.aws.session import get_aws_client
from app.integrations.biometric.port import BiometricServiceError, SegmentoMetricasDTO


class AwsBiometricService:
    async def analizar_segmento(
        self, *, sesion_id: int, audio_url: str | None, video_url: str | None
    ) -> SegmentoMetricasDTO:
        # El análisis de video/audio completo es asíncrono (Rekognition Video + Transcribe);
        # para el flujo en vivo usa `analizar_imagen` (frame). Aquí, métricas neutras.
        return SegmentoMetricasDTO(
            postura_score=None, contacto_visual_pct=None, muletillas_conteo=0, ritmo_wpm=None
        )

    async def analizar_imagen(self, *, imagen: bytes) -> SegmentoMetricasDTO:
        # Rekognition es boto3 SÍNCRONO y bloqueante; lo movemos a un hilo para no congelar
        # el event loop (el WS de video lo llama por cada frame, junto al WS de audio).
        return await anyio.to_thread.run_sync(self._analizar_imagen, imagen)

    def _analizar_imagen(self, imagen: bytes) -> SegmentoMetricasDTO:
        try:
            rekognition = get_aws_client("rekognition")
            resp = rekognition.detect_faces(Image={"Bytes": imagen}, Attributes=["ALL"])
            caras = resp.get("FaceDetails", [])
            if not caras:  # no se detectó rostro
                return SegmentoMetricasDTO(
                    postura_score=0.0, contacto_visual_pct=0.0, muletillas_conteo=0, ritmo_wpm=None
                )
            # `dict.get(k, 0.0)` no protege si la clave EXISTE con valor None: Rekognition puede
            # devolver `Yaw: null`; `float(None)` reventaría el frame. El `or 0.0` lo cubre.
            pose = caras[0].get("Pose") or {}
            yaw = abs(float(pose.get("Yaw") or 0.0))
            pitch = abs(float(pose.get("Pitch") or 0.0))
            roll = abs(float(pose.get("Roll") or 0.0))
            ojos_abiertos = bool((caras[0].get("EyesOpen") or {}).get("Value", True))
        except BiometricServiceError:
            raise
        except Exception as exc:  # red / credenciales / imagen inválida / respuesta inesperada
            raise BiometricServiceError(f"Rekognition falló: {exc}") from exc

        postura = max(0.0, 100.0 - (pitch + roll))  # cabeza erguida
        contacto = max(0.0, 100.0 - yaw * 2.0)  # mirando a la cámara
        if not ojos_abiertos:
            contacto *= 0.5
        return SegmentoMetricasDTO(
            postura_score=round(postura, 1),
            contacto_visual_pct=round(contacto, 1),
            muletillas_conteo=0,
            ritmo_wpm=None,
        )
