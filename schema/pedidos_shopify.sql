-- =============================================================================
-- Plantilla Tienda de Tatuaje — Pedidos confirmados de la tienda (Shopify)
-- Migración incremental: se corre SOBRE la base que ya existe.
--
-- No borra nada y se puede correr dos veces (CREATE TABLE IF NOT EXISTS).
--
-- Cómo cargarlo en Windows (PowerShell no soporta `<` para redirigir):
--     mysql -u root -p --default-character-set=utf8mb4 -e "source schema/pedidos_shopify.sql"
-- =============================================================================

SET NAMES utf8mb4;


-- =============================================================================
-- PEDIDOS_SHOPIFY — el registro de lo que Shopify confirma como pagado
--
-- ESTO ES UN REGISTRO, NO UNA BILLETERA. No descuenta ni suma saldo de
-- puntos — eso necesita una tabla de movimientos aparte (lp_movimientos, ver
-- config/mysqlconnection.py) que todavía no existe. Lo que esta tabla sí
-- hace es dejar guardado quién compró qué y por cuánto, para que el panel
-- muestre algo y para que el día que se construya la billetera, no haya que
-- rearmar el historial desde el admin de Shopify.
--
-- `puntos_acreditados_at` viaja vacía a propósito: es el enganche para esa
-- fase futura, y hasta entonces no la toca nadie.
-- =============================================================================

CREATE TABLE IF NOT EXISTS pedidos_shopify (
    id                     BIGINT       NOT NULL AUTO_INCREMENT,

    -- El id numérico de la orden en Shopify. Es lo que llega en `id` del
    -- webhook, y lo que hace que procesar el mismo pedido dos veces (Shopify
    -- reintenta un webhook que no contestó 2xx a tiempo, aunque a veces sí
    -- haya llegado bien) no invente un segundo registro.
    shopify_order_id      BIGINT       NOT NULL,
    numero_orden           VARCHAR(20)  NULL COMMENT 'El "#1001" que ve el cliente',

    -- NULL si compró sin cuenta, o con un correo distinto al de su cuenta.
    -- No se exige tener cuenta para que el pedido quede guardado.
    usuario_id             BIGINT       NULL,
    correo_comprador       VARCHAR(255) NOT NULL,

    monto_clp              INT          NOT NULL,
    moneda                 VARCHAR(3)   NOT NULL DEFAULT 'CLP',

    -- Resumen de lo comprado: [{"titulo","cantidad","clp"}]. A propósito NO
    -- se guarda el pedido completo que manda Shopify — eso trae dirección de
    -- despacho y datos de contacto que esta tabla no necesita.
    items                  JSON         NULL,

    creado_shopify_at      DATETIME     NULL COMMENT 'UTC. Cuándo se pagó, según Shopify',
    recibido_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'UTC. Cuándo llegó el webhook',
    puntos_acreditados_at  DATETIME     NULL COMMENT 'Para cuando exista la billetera de puntos — no se usa todavía',

    PRIMARY KEY (id),
    -- El freno de idempotencia: ver el comentario de shopify_order_id.
    UNIQUE KEY uq_pedido_shopify (shopify_order_id),
    KEY idx_pedido_usuario (usuario_id),
    KEY idx_pedido_recibido (recibido_at),

    -- Sin CASCADE a propósito: si se borra la cuenta del cliente no
    -- queremos que desaparezca el registro de que compró. Mismo criterio
    -- que el revisor del muro y el autor de una promo.
    CONSTRAINT fk_pedido_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
) ENGINE=InnoDB;
