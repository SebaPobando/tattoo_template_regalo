-- =============================================================================
-- Plantilla Tienda de Tatuaje — La ruleta de premios
-- Migración incremental: se corre SOBRE la base que ya existe.
-- No borra nada y se puede correr dos veces (CREATE TABLE IF NOT EXISTS).
--
-- Cómo cargarlo en Windows (PowerShell no soporta `<` para redirigir entrada):
--     mysql -u root -p --default-character-set=utf8mb4 -e "source schema/ruleta.sql"
-- o abrirlo en MySQL Workbench con File → Open SQL Script.
-- =============================================================================

SET NAMES utf8mb4;


-- =============================================================================
-- LA IDEA
--
-- Quien compra sobre cierto monto EN EL LOCAL tiene derecho a girar la
-- ruleta. La compra la ve el barista, no la página: por eso cada giro lo
-- HABILITA alguien del local desde el panel, y la página pública solo sirve
-- para girar un giro que ya existe. Una página con un botón «Girar» abierto
-- a cualquiera se gira mil veces desde la casa.
--
-- El resultado lo sortea el SERVIDOR. La animación del navegador solo
-- muestra dónde cae lo que ya se decidió; tocar el JavaScript no cambia el
-- premio.
-- =============================================================================


-- =============================================================================
-- RULETA_CONFIG — una sola fila, id = 1
-- =============================================================================

CREATE TABLE IF NOT EXISTS ruleta_config (
    id              TINYINT      NOT NULL,

    -- Solo informativo: se muestra en el panel y en la página del giro
    -- («por compras sobre $40.000»). La app no ve la boleta, así que no
    -- puede validarlo; lo valida quien habilita el giro.
    monto_minimo    INT          NOT NULL DEFAULT 40000,

    -- Cuántos minutos vale un giro habilitado y sin girar. Corto a propósito:
    -- el giro es para la persona que está en la caja ahora, no un cupón para
    -- la semana. Uno vencido no gira y queda en el historial como vencido.
    vence_min       SMALLINT     NOT NULL DEFAULT 30,

    actualizado_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP COMMENT 'UTC',

    PRIMARY KEY (id),
    CONSTRAINT chk_ruleta_config_unica CHECK (id = 1)
) ENGINE=InnoDB;

INSERT IGNORE INTO ruleta_config (id) VALUES (1);


-- =============================================================================
-- RULETA_GAJOS — lo que dice cada gajo, en orden
--
-- TODOS LOS GAJOS SALEN CON LA MISMA PROBABILIDAD. No hay columna de «peso»
-- a propósito: con 12 gajos cada uno es 1/12, y eso se puede explicar en
-- voz alta en la caja. Si un premio tiene que salir menos, se ponen más
-- gajos de premios chicos; el panel muestra el % real de cada premio sumando
-- sus gajos.
--
-- Nace VACÍA: no se siembran premios de ejemplo. Una ruleta que regala «Café
-- gratis» porque nadie cambió el ejemplo es un problema real en la caja.
-- Mientras no estén todos los gajos escritos, el panel no deja habilitar
-- giros.
-- =============================================================================

CREATE TABLE IF NOT EXISTS ruleta_gajos (
    id          INT          NOT NULL AUTO_INCREMENT,
    -- 0 = el primero a la derecha del puntero, en el sentido del reloj.
    posicion    SMALLINT     NOT NULL,
    premio      VARCHAR(30)  NOT NULL COMMENT 'Corto: tiene que caber en el gajo',

    PRIMARY KEY (id),
    UNIQUE KEY uq_ruleta_gajos_posicion (posicion)
) ENGINE=InnoDB;


-- =============================================================================
-- RULETA_GIROS — cada giro habilitado, girado o no
--
-- Guarda una FOTO de la ruleta en el momento de girar (`gajos_json`) y el
-- premio en texto. Si mañana el admin cambia los premios, el giro de hoy
-- sigue mostrando la ruleta que se giró y lo que salió de verdad.
-- =============================================================================

CREATE TABLE IF NOT EXISTS ruleta_giros (
    id              BIGINT       NOT NULL AUTO_INCREMENT,

    -- 'RL-4KQ7-9XTM'. Es la llave de la página del giro (/ruleta/<codigo>):
    -- quien la tiene puede girar UNA vez. Azar de `secrets`, no un número
    -- correlativo que se adivina sumando uno.
    codigo          VARCHAR(20)  NOT NULL,

    -- Quién lo habilitó. SET NULL: si esa cuenta se borra, el giro no.
    habilitado_por  BIGINT       NULL,

    -- Libre y opcional: número de boleta, monto, nombre. Sirve para
    -- responder «¿y este giro de quién fue?» sin abrir la caja.
    referencia      VARCHAR(80)  NULL,

    creado_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'UTC',
    vence_at        DATETIME     NOT NULL COMMENT 'UTC. Pasado esto no gira',

    -- El resultado. Todo NULL mientras no se gire.
    girado_at       DATETIME     NULL COMMENT 'UTC',
    gajo_indice     SMALLINT     NULL COMMENT 'Posición del gajo que salió',
    premio          VARCHAR(30)  NULL,
    gajos_json      TEXT         NULL COMMENT 'La ruleta tal como estaba al girar',

    entregado_at    DATETIME     NULL COMMENT 'UTC. Cuándo se le dio el premio',
    anulado_at      DATETIME     NULL COMMENT 'UTC. Habilitado por error',

    PRIMARY KEY (id),
    UNIQUE KEY uq_ruleta_giros_codigo (codigo),
    KEY ix_ruleta_giros_creado (creado_at),
    CONSTRAINT fk_ruleta_giros_usuario FOREIGN KEY (habilitado_por)
        REFERENCES usuarios(id) ON DELETE SET NULL
) ENGINE=InnoDB;
