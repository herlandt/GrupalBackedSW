"""Adaptador REAL del servicio biométrico sobre AWS Rekognition (análisis por frame).

`analizar_imagen` envía un frame de la cámara a Rekognition `detect_faces` y traduce la
**pose** (cabeza erguida) y el **yaw** (mirar a la cámara) + apertura de ojos a
**postura** y **contacto visual** (RF-04). El análisis de video/audio completo
(Rekognition Video + Transcribe, asíncrono) queda como evolución futura.
"""

from __future__ import annotations

from app.integrations.aws.session import get_boto_session
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
        try:
            rekognition = get_boto_session().client("rekognition")
            resp = rekognition.detect_faces(Image={"Bytes": imagen}, Attributes=["ALL"])
        except Exception as exc:  # red / credenciales / imagen inválida
            raise BiometricServiceError(f"Rekognition falló: {exc}") from exc

        caras = resp.get("FaceDetails", [])
        if not caras:  # no se detectó rostro
            return SegmentoMetricasDTO(
                postura_score=0.0, contacto_visual_pct=0.0, muletillas_conteo=0, ritmo_wpm=None
            )

        pose = caras[0].get("Pose", {})
        yaw = abs(float(pose.get("Yaw", 0.0)))
        pitch = abs(float(pose.get("Pitch", 0.0)))
        roll = abs(float(pose.get("Roll", 0.0)))
        ojos_abiertos = bool(caras[0].get("EyesOpen", {}).get("Value", True))

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
