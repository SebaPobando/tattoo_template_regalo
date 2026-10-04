-- =============================================================================
-- Plantilla Tienda de Tatuaje — Muro de deseos
-- Migración incremental: se corre SOBRE la base que ya existe.
--
-- Este archivo NO borra nada y no toca ninguna tabla existente. Se puede
-- correr dos veces sin romper nada (CREATE TABLE IF NOT EXISTS).
--
-- Cómo cargarlo en Windows (PowerShell no soporta `<` para redirigir):
--     mysql -u root -p --default-character-set=utf8mb4 -e "source schema/muro.sql"
-- o abrirlo en MySQL Workbench con File → Open SQL Script.
-- =============================================================================

SET NAMES utf8mb4;


-- =============================================================================
-- MURO_MENSAJES — lo que la gente deja escrito sobre la cafetería
--
-- OJO CON EL NOMBRE: ya existe una tabla `deseos`, y es OTRA COSA — es la
-- lista de deseos de productos de la carta (usuario_id + producto_id). Esta
-- es el muro público. Se llama `muro_mensajes` justamente para que nadie
-- escriba un JOIN contra la equivocada.
--
-- Nada se publica solo: todo entra en 'pendiente' y lo aprueba el admin.
-- =============================================================================

CREATE TABLE IF NOT EXISTS muro_mensajes (
    id            BIGINT       NOT NULL AUTO_INCREMENT,

    -- Hay que tener cuenta para escribir (decisión de Seba). Así cada mensaje
    -- tiene dueño: si alguien abusa, se bloquea la cuenta y no vuelve a pasar
    -- por el filtro cambiando de navegador.
    usuario_id    BIGINT       NOT NULL,

    -- COPIA del nickname al momento de enviar, NO un JOIN a usuarios.
    --
    -- Es a propósito y es lo más importante de esta tabla: el admin aprueba
    -- un par nickname + mensaje concreto. Si el nombre saliera por JOIN,
    -- cualquiera podría mandar «rico el café», esperar la aprobación y
    -- después cambiarse el nickname del perfil por un insulto — que
    -- aparecería publicado en la portada, ya aprobado, sin que nadie lo
    -- toque. La copia congela exactamente lo que se revisó.
    nickname      VARCHAR(45)  NOT NULL,

    -- 280 caracteres: un deseo, no un ensayo. El largo también se valida en
    -- la app; acá está para que la base no acepte lo que la app rechazaría.
    mensaje       VARCHAR(280) NOT NULL,

    estado        ENUM('pendiente','aprobado','rechazado')
                               NOT NULL DEFAULT 'pendiente',

    -- Nota PRIVADA del admin ("spam", "ofensivo"). No se muestra nunca en el
    -- sitio público: es para acordarse de por qué se rechazó, tres semanas
    -- después, cuando la misma persona reclame.
    motivo        VARCHAR(140) NULL,

    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'UTC',
    revisado_at   DATETIME     NULL COMMENT 'UTC. NULL = nadie lo ha mirado',
    revisado_por  BIGINT       NULL COMMENT 'Qué admin lo aprobó o rechazó',

    PRIMARY KEY (id),

    -- La consulta del público es siempre la misma: estado='aprobado'
    -- ordenado por fecha descendente. El índice la cubre entera.
    KEY idx_muro_publico (estado, created_at DESC),

    -- Para el freno anti-spam: cuántos mandó esta persona hoy, y si tiene
    -- alguno esperando revisión.
    KEY idx_muro_usuario (usuario_id, estado, created_at),

    CONSTRAINT fk_muro_usuario FOREIGN KEY (usuario_id)
        REFERENCES usuarios(id) ON DELETE CASCADE,

    -- Sin CASCADE a propósito: si se borra la cuenta del admin no queremos
    -- que desaparezcan los mensajes que revisó.
    CONSTRAINT fk_muro_revisor FOREIGN KEY (revisado_por)
        REFERENCES usuarios(id),

    CONSTRAINT chk_muro_mensaje CHECK (CHAR_LENGTH(TRIM(mensaje)) >= 3)
) ENGINE=InnoDB;
