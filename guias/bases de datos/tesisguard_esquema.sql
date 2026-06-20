-- TesisGuard — esquema completo de base de datos (PostgreSQL)
-- Generado desde el esquema único del proyecto. Cubre los 3 sprints.

BEGIN;

-- Tipos enumerados
CREATE TYPE rol_usuario AS ENUM ('ESTUDIANTE', 'ADMINISTRADOR');
CREATE TYPE estado_suscripcion AS ENUM ('PENDIENTE', 'ACTIVA', 'EXPIRADA', 'CANCELADA');
CREATE TYPE estado_pago AS ENUM ('PENDIENTE', 'PAGADO', 'FALLIDO', 'REEMBOLSADO');
CREATE TYPE formato_documento AS ENUM ('DOCX', 'PDF');
CREATE TYPE estado_analisis AS ENUM ('PENDIENTE', 'EN_PROCESO', 'COMPLETADO', 'ERROR');
CREATE TYPE nivel_preparacion AS ENUM ('ALTO', 'MEDIO', 'BAJO');
CREATE TYPE categoria_observacion AS ENUM ('COHERENCIA', 'NORMAS', 'SUGERENCIA');
CREATE TYPE estado_alerta_etica AS ENUM ('PENDIENTE', 'EN_REVISION', 'CONFIRMADA', 'DESESTIMADA');
CREATE TYPE nivel_dificultad AS ENUM ('EXPLORACION', 'ESTANDAR', 'RIGUROSO');
CREATE TYPE estado_sesion AS ENUM ('EN_CURSO', 'FINALIZADA', 'CANCELADA');
CREATE TYPE estado_avance AS ENUM ('PENDIENTE', 'APROBADO', 'RECHAZADO');

CREATE TABLE usuario (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    rol rol_usuario NOT NULL,
    foto_perfil_url VARCHAR(500),
    activo BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE token_reset_password (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT NOT NULL,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE plan_suscripcion (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    precio NUMERIC(10,2) NOT NULL,
    moneda VARCHAR(3) NOT NULL,
    periodo_dias INTEGER NOT NULL,
    activo BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE suscripcion (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT NOT NULL,
    plan_id BIGINT NOT NULL,
    estado estado_suscripcion NOT NULL,
    fecha_inicio TIMESTAMPTZ,
    fecha_fin TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE pago (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT NOT NULL,
    suscripcion_id BIGINT,
    plan_id BIGINT NOT NULL,
    monto NUMERIC(10,2) NOT NULL,
    moneda VARCHAR(3) NOT NULL,
    estado estado_pago NOT NULL,
    stripe_checkout_session_id VARCHAR(255) UNIQUE,
    stripe_payment_intent_id VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evento_webhook (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stripe_event_id VARCHAR(255) NOT NULL UNIQUE,
    pago_id BIGINT,
    tipo VARCHAR(120) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE bitacora (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id BIGINT,
    accion VARCHAR(120) NOT NULL,
    entidad VARCHAR(120) NOT NULL,
    entidad_id BIGINT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE documento (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT NOT NULL,
    titulo VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE version_documento (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    documento_id BIGINT NOT NULL,
    numero_version INTEGER NOT NULL,
    archivo_url VARCHAR(500) NOT NULL,
    formato formato_documento NOT NULL,
    estado_analisis estado_analisis NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE resultado_auditoria (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version_id BIGINT NOT NULL UNIQUE,
    nivel_documento nivel_preparacion NOT NULL,
    resumen TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE observacion (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    resultado_id BIGINT NOT NULL,
    categoria categoria_observacion NOT NULL,
    severidad VARCHAR(20) NOT NULL,
    descripcion TEXT NOT NULL,
    ubicacion VARCHAR(255)
);

CREATE TABLE alerta_etica (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version_id BIGINT NOT NULL,
    tipo VARCHAR(120) NOT NULL,
    fragmento TEXT,
    estado estado_alerta_etica NOT NULL,
    decision_admin_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sesion_simulacion (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT NOT NULL,
    version_documento_id BIGINT NOT NULL,
    nivel_dificultad nivel_dificultad NOT NULL,
    estado estado_sesion NOT NULL,
    fecha_inicio TIMESTAMPTZ NOT NULL,
    fecha_fin TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE metrica_biometrica (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sesion_id BIGINT NOT NULL,
    postura_score NUMERIC(5,2),
    muletillas_conteo INTEGER NOT NULL,
    ritmo_wpm INTEGER,
    contacto_visual_pct NUMERIC(5,2),
    momento TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE pregunta_tribunal (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sesion_id BIGINT NOT NULL,
    orden INTEGER NOT NULL,
    texto TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE respuesta_estudiante (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pregunta_id BIGINT NOT NULL UNIQUE,
    texto TEXT,
    audio_url VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evaluacion_respuesta (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    respuesta_id BIGINT NOT NULL UNIQUE,
    puntuacion NUMERIC(5,2) NOT NULL,
    observaciones TEXT,
    profundidad VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE resultado_simulacion (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sesion_id BIGINT NOT NULL UNIQUE,
    nivel_defensa nivel_preparacion NOT NULL,
    oratoria_score NUMERIC(5,2),
    comunicacion_no_verbal_score NUMERIC(5,2),
    dominio_score NUMERIC(5,2),
    resumen TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE avance_formal (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT NOT NULL,
    etapa VARCHAR(120) NOT NULL,
    estado estado_avance NOT NULL,
    aprobado_por_id BIGINT,
    fecha_aprobacion TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Claves foráneas
ALTER TABLE token_reset_password ADD CONSTRAINT fk_token_reset_password_usuario_id FOREIGN KEY (usuario_id) REFERENCES usuario(id);
ALTER TABLE suscripcion ADD CONSTRAINT fk_suscripcion_usuario_id FOREIGN KEY (usuario_id) REFERENCES usuario(id);
ALTER TABLE suscripcion ADD CONSTRAINT fk_suscripcion_plan_id FOREIGN KEY (plan_id) REFERENCES plan_suscripcion(id);
ALTER TABLE pago ADD CONSTRAINT fk_pago_usuario_id FOREIGN KEY (usuario_id) REFERENCES usuario(id);
ALTER TABLE pago ADD CONSTRAINT fk_pago_suscripcion_id FOREIGN KEY (suscripcion_id) REFERENCES suscripcion(id);
ALTER TABLE pago ADD CONSTRAINT fk_pago_plan_id FOREIGN KEY (plan_id) REFERENCES plan_suscripcion(id);
ALTER TABLE evento_webhook ADD CONSTRAINT fk_evento_webhook_pago_id FOREIGN KEY (pago_id) REFERENCES pago(id);
ALTER TABLE bitacora ADD CONSTRAINT fk_bitacora_actor_id FOREIGN KEY (actor_id) REFERENCES usuario(id);
ALTER TABLE documento ADD CONSTRAINT fk_documento_usuario_id FOREIGN KEY (usuario_id) REFERENCES usuario(id);
ALTER TABLE version_documento ADD CONSTRAINT fk_version_documento_documento_id FOREIGN KEY (documento_id) REFERENCES documento(id);
ALTER TABLE resultado_auditoria ADD CONSTRAINT fk_resultado_auditoria_version_id FOREIGN KEY (version_id) REFERENCES version_documento(id);
ALTER TABLE observacion ADD CONSTRAINT fk_observacion_resultado_id FOREIGN KEY (resultado_id) REFERENCES resultado_auditoria(id);
ALTER TABLE alerta_etica ADD CONSTRAINT fk_alerta_etica_version_id FOREIGN KEY (version_id) REFERENCES version_documento(id);
ALTER TABLE alerta_etica ADD CONSTRAINT fk_alerta_etica_decision_admin_id FOREIGN KEY (decision_admin_id) REFERENCES usuario(id);
ALTER TABLE sesion_simulacion ADD CONSTRAINT fk_sesion_simulacion_usuario_id FOREIGN KEY (usuario_id) REFERENCES usuario(id);
ALTER TABLE sesion_simulacion ADD CONSTRAINT fk_sesion_simulacion_version_documento_id FOREIGN KEY (version_documento_id) REFERENCES version_documento(id);
ALTER TABLE metrica_biometrica ADD CONSTRAINT fk_metrica_biometrica_sesion_id FOREIGN KEY (sesion_id) REFERENCES sesion_simulacion(id);
ALTER TABLE pregunta_tribunal ADD CONSTRAINT fk_pregunta_tribunal_sesion_id FOREIGN KEY (sesion_id) REFERENCES sesion_simulacion(id);
ALTER TABLE respuesta_estudiante ADD CONSTRAINT fk_respuesta_estudiante_pregunta_id FOREIGN KEY (pregunta_id) REFERENCES pregunta_tribunal(id);
ALTER TABLE evaluacion_respuesta ADD CONSTRAINT fk_evaluacion_respuesta_respuesta_id FOREIGN KEY (respuesta_id) REFERENCES respuesta_estudiante(id);
ALTER TABLE resultado_simulacion ADD CONSTRAINT fk_resultado_simulacion_sesion_id FOREIGN KEY (sesion_id) REFERENCES sesion_simulacion(id);
ALTER TABLE avance_formal ADD CONSTRAINT fk_avance_formal_usuario_id FOREIGN KEY (usuario_id) REFERENCES usuario(id);
ALTER TABLE avance_formal ADD CONSTRAINT fk_avance_formal_aprobado_por_id FOREIGN KEY (aprobado_por_id) REFERENCES usuario(id);

-- Índices de apoyo
CREATE INDEX ix_token_reset_password_usuario_id ON token_reset_password(usuario_id);
CREATE INDEX ix_suscripcion_usuario_id ON suscripcion(usuario_id);
CREATE INDEX ix_suscripcion_plan_id ON suscripcion(plan_id);
CREATE INDEX ix_pago_usuario_id ON pago(usuario_id);
CREATE INDEX ix_pago_suscripcion_id ON pago(suscripcion_id);
CREATE INDEX ix_pago_plan_id ON pago(plan_id);
CREATE INDEX ix_evento_webhook_pago_id ON evento_webhook(pago_id);
CREATE INDEX ix_bitacora_actor_id ON bitacora(actor_id);
CREATE INDEX ix_documento_usuario_id ON documento(usuario_id);
CREATE INDEX ix_version_documento_documento_id ON version_documento(documento_id);
CREATE INDEX ix_resultado_auditoria_version_id ON resultado_auditoria(version_id);
CREATE INDEX ix_observacion_resultado_id ON observacion(resultado_id);
CREATE INDEX ix_alerta_etica_version_id ON alerta_etica(version_id);
CREATE INDEX ix_alerta_etica_decision_admin_id ON alerta_etica(decision_admin_id);
CREATE INDEX ix_sesion_simulacion_usuario_id ON sesion_simulacion(usuario_id);
CREATE INDEX ix_sesion_simulacion_version_documento_id ON sesion_simulacion(version_documento_id);
CREATE INDEX ix_metrica_biometrica_sesion_id ON metrica_biometrica(sesion_id);
CREATE INDEX ix_pregunta_tribunal_sesion_id ON pregunta_tribunal(sesion_id);
CREATE INDEX ix_respuesta_estudiante_pregunta_id ON respuesta_estudiante(pregunta_id);
CREATE INDEX ix_evaluacion_respuesta_respuesta_id ON evaluacion_respuesta(respuesta_id);
CREATE INDEX ix_resultado_simulacion_sesion_id ON resultado_simulacion(sesion_id);
CREATE INDEX ix_avance_formal_usuario_id ON avance_formal(usuario_id);
CREATE INDEX ix_avance_formal_aprobado_por_id ON avance_formal(aprobado_por_id);

COMMIT;
