-- =============================================================================
-- Plantilla Tienda de Tatuaje — Vales de regalo y gift cards
-- Migración incremental: se corre SOBRE la base que ya existe.
-- No borra nada y se puede correr dos veces (CREATE TABLE IF NOT EXISTS).
--
-- Cómo cargarlo en Windows (PowerShell no soporta `<` para redirigir entrada):
--     mysql -u root -p --default-character-set=utf8mb4 -e "source schema/vales.sql"
-- o abrirlo en MySQL Workbench con File → Open SQL Script.
-- =============================================================================

SET NAMES utf8mb4;


-- =============================================================================
-- LA IDEA
--
-- Un vale es un papel con QR que se canjea UNA vez en la barra. Hay dos
-- tipos, y los dos viven en la misma tabla porque se emiten, se envían y se
-- canjean igual:
--
--   regalo    lo emite el local (un evento, una cortesía, un sorteo). No se
--             cobra. Puede vencer: la fecha la elige quien lo emite.
--   giftcard  lo compra un cliente, en la caja. Se anota cuánto pagó. NO
--             vence: está pagado.
--
-- Lo que cubre el vale es TEXTO LIBRE («1 café de la carta», «1 Latte + 1
-- brownie», «$10.000 en consumo») que escribe el barista al emitirlo. El vale
-- se canjea COMPLETO, de una vez: no hay saldo parcial.
--
-- Solo el personal (admin o barista) puede canjear. Cualquiera que escanee
-- el QR ve el vale; solo quien tiene sesión de personal ve el botón.
-- =============================================================================


-- =============================================================================
-- VALE_LOTES — vales emitidos de a muchos, para un evento
--
-- Un lote es solo el grupo: «30 vales "1 café" para el aniversario». Sirve
-- para imprimir la hoja de QR de todos juntos y para saber, después, cuántos
-- de ese evento se canjearon.
-- =============================================================================

CREATE TABLE IF NOT EXISTS vale_lotes (
    id           BIGINT       NOT NULL AUTO_INCREMENT,
    nombre       VARCHAR(120) NOT NULL COMMENT 'El evento: «Aniversario 2026»',
    creado_por   BIGINT       NULL,
    creado_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'UTC',

    PRIMARY KEY (id),
    CONSTRAINT fk_vale_lotes_usuario FOREIGN KEY (creado_por)
        REFERENCES usuarios(id) ON DELETE SET NULL
) ENGINE=InnoDB;


-- =============================================================================
-- VALES
-- =============================================================================

CREATE TABLE IF NOT EXISTS vales (
    id               BIGINT       NOT NULL AUTO_INCREMENT,

    -- 'VL-4KQ7-9XTM'. La llave de la página del vale (/vale/<codigo>), que
    -- es lo que va en el QR y en el WhatsApp. Azar de `secrets`, no un
    -- número correlativo: el vale 41 no se adivina sumando uno al 40.
    codigo           VARCHAR(20)  NOT NULL,

    tipo             ENUM('regalo','giftcard') NOT NULL,

    -- Lo que se entrega al canjearlo. Texto libre, lo escribe el barista.
    valido_por       VARCHAR(160) NOT NULL,

    -- Para quién es. Opcional en los de evento (se reparten impresos).
    para_nombre      VARCHAR(80)  NULL,
    para_telefono    VARCHAR(20)  NULL COMMENT 'Para mandárselo por WhatsApp',

    -- De regalo: por qué se dio («Evento aniversario», «Disculpa por la
    -- espera»). Gift card: quién la compró.
    motivo           VARCHAR(120) NULL,
    comprador        VARCHAR(80)  NULL,

    -- Gift card: lo que se cobró. Es lo que suma en «vendido en gift cards».
    -- NULL en los de regalo, que no se cobran.
    monto_pagado_clp INT          NULL,

    lote_id          BIGINT       NULL,

    emitido_por      BIGINT       NULL,
    emitido_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'UTC',

    -- Hasta cuándo vale, en UTC: el último segundo del día elegido, en hora
    -- de Chile. NULL = no vence. Una gift card NUNCA vence (ver el CHECK).
    vence_at         DATETIME     NULL,

    canjeado_at      DATETIME     NULL COMMENT 'UTC. NULL = todavía no se usa',
    canjeado_por     BIGINT       NULL,

    -- Emitido por error. Un vale anulado no se canjea; no se borra, para
    -- que quede la huella de que existió.
    anulado_at       DATETIME     NULL COMMENT 'UTC',

    PRIMARY KEY (id),
    UNIQUE KEY uq_vales_codigo (codigo),
    KEY ix_vales_emitido (emitido_at),
    KEY ix_vales_lote (lote_id),
    CONSTRAINT fk_vales_lote FOREIGN KEY (lote_id)
        REFERENCES vale_lotes(id) ON DELETE SET NULL,
    CONSTRAINT fk_vales_emitido_por FOREIGN KEY (emitido_por)
        REFERENCES usuarios(id) ON DELETE SET NULL,
    CONSTRAINT fk_vales_canjeado_por FOREIGN KEY (canjeado_por)
        REFERENCES usuarios(id) ON DELETE SET NULL,
    -- La regla del dueño, escrita donde nadie se la puede saltar: una gift
    -- card está pagada y no vence.
    CONSTRAINT chk_vales_giftcard_no_vence
        CHECK (tipo = 'regalo' OR vence_at IS NULL)
) ENGINE=InnoDB;
