"""Configuración central de la app, leída desde variables de entorno.

Única fuente de verdad para la configuración. Se importa donde se necesite
(`from app.core.config import settings`). Los secretos jamás se hardcodean:
viven en `.env` (desarrollo) o en variables de entorno del contenedor (producción).
"""

from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # --- App ---
    app_name: str = "GrupalBackedSW"
    app_env: str = "development"
    debug: bool = True

    # --- Base de datos (PostgreSQL local + psycopg 3, async) ---
    # Valor de respaldo; el real (con tu contraseña) va en `.env`, no en el repo.
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/tesisguard"

    # --- Seguridad / JWT (>=32 bytes para HS256) ---
    jwt_secret: str = "dev-insecure-change-me-0123456789-abcdef"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30

    # --- AWS (usa el perfil de AWS CLI configurado en la máquina) ---
    aws_profile: str | None = "default"
    aws_region: str = "us-east-1"  # región real del despliegue (Bedrock/Textract/S3/EC2)
    s3_documents_bucket: str | None = None
    s3_video_bucket: str | None = None
    textract_bucket: str | None = None  # bucket para OCR de PDFs escaneados (Textract async)
    ses_sender_email: str | None = None
    # Extractor del análisis documental: "stub" (dev, sin AWS) | "aws" (Comprehend + Titan).
    analysis_backend: str = "stub"
    bedrock_embeddings_model: str = "amazon.titan-embed-text-v2:0"
    # Servicio biométrico: "stub" (dev) | "aws" (Rekognition detect_faces por frame).
    biometric_backend: str = "stub"
    # Tribunal virtual: "stub" (preguntas genéricas) | "aws" (preguntas desde el documento
    # real con Comprehend + evaluación por similitud Titan; sin LLM generativo) | "claude"
    # (Claude en Bedrock genera las preguntas, coherentes; evalúa por similitud; cae a "aws"
    # si Claude falla/no hay acceso — complementario y de bajo costo).
    tribunal_llm_backend: str = "stub"
    # Modelo Claude (Bedrock) para el tribunal "claude". Inference profile us. (los 4.x no
    # admiten on-demand directo). Haiku = el más barato; suficiente para generar preguntas.
    tribunal_claude_model: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    # Tribunal "gemini": API de Google AI Studio (tier gratuito). En GEMINI_API_KEY puedes
    # poner UNA o VARIAS keys separadas por coma; al agotarse una (HTTP 429) salta a la siguiente.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    # Embeddings de Gemini (gratis) para la coherencia discurso↔documento: si hay GEMINI_API_KEY
    # se usa esto en vez de Titan (Bedrock), que está en cuota 0.
    gemini_embed_model: str = "gemini-embedding-001"

    # --- CORS (frontend web y móvil son separados) ---
    # NoDecode: evita que pydantic-settings intente parsear el valor como JSON,
    # para poder declararlo como CSV legible en el .env.
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:4200",  # Angular (GrupalFrontSW)
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # --- Frontend (para enlaces en correos) ---
    frontend_base_url: str = "http://localhost:4200"

    # --- Integraciones: selección de adaptador por entorno ---
    email_backend: str = "console"  # console | ses
    storage_backend: str = "local"  # local | s3
    local_media_dir: str = "./media"

    # --- Recuperación de contraseña ---
    password_reset_expire_minutes: int = 60

    # --- Endpoints internos (worker de colas): secreto compartido por cabecera ---
    # No los invoca un usuario, sino el consumidor de confianza que desencola análisis.
    internal_api_token: str = "dev-internal-token-change-me"

    # --- Stripe (modo test) ---
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_success_url: str = (
        "http://localhost:4200/app/administracion/pagos?pago=ok&session_id={CHECKOUT_SESSION_ID}"
    )
    stripe_cancel_url: str = "http://localhost:4200/app/administracion/pagos?pago=cancelado"

    # --- Tests ---
    test_database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/tesisguard_test"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def gemini_api_keys(self) -> list[str]:
        """Lista de claves de Gemini (GEMINI_API_KEY admite varias separadas por coma)."""
        return [k.strip() for k in self.gemini_api_key.split(",") if k.strip()]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv_origins(cls, value: object) -> object:
        """Permite definir CORS_ORIGINS como lista separada por comas en el .env."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _require_prod_secrets(self) -> "Settings":
        """En producción no se permite arrancar con el secreto JWT de desarrollo."""
        if self.app_env == "production" and self.jwt_secret.startswith("dev-"):
            raise ValueError("JWT_SECRET debe configurarse en producción (no usar el de dev).")
        if self.app_env == "production" and self.internal_api_token.startswith("dev-"):
            raise ValueError("INTERNAL_API_TOKEN debe configurarse en producción.")
        return self


settings = Settings()
