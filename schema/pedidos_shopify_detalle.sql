-- =============================================================================
-- Plantilla Tienda de Tatuaje — Más detalle en los pedidos de Shopify
-- Migración incremental: se corre SOBRE pedidos_shopify que ya existe.
--
-- Agrega el nombre de quien compró (Shopify lo manda aunque compre sin
-- cuenta) y el estado del pedido (para saber si se reembolsó después). No
-- borra nada y se puede correr dos veces sin romper nada.
--
-- Cómo cargarlo en Windows (PowerShell no soporta `<` para redirigir entrada):
--     mysql -u root -p --default-character-set=utf8mb4 -e "source schema/pedidos_shopify_detalle.sql"
-- =============================================================================

SET NAMES utf8mb4;

-- MySQL 8 NO tiene `ADD COLUMN IF NOT EXISTS` (eso es de MariaDB), así que la
-- idempotencia se hace a mano: se mira information_schema y, si la columna ya
-- está, se ejecuta un DO 0 que no hace nada. Mismo patrón que
-- actividad_imagen.sql y evento_voucher.sql.

SET @existe := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name   = 'pedidos_shopify'
      AND column_name  = 'nombre_comprador'
);
SET @sql := IF(@existe = 0,
    'ALTER TABLE pedidos_shopify
       ADD COLUMN nombre_comprador VARCHAR(160) NULL
       COMMENT ''Del payload del webhook: customer, o si compró sin cuenta, la dirección de facturación/despacho''
       AFTER correo_comprador',
    'DO 0');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- ESTADO — 'pagado' hasta que llegue un aviso de reembolso. No es un
-- historial completo (para eso están los movimientos en Shopify mismo):
-- es solo lo que este registro necesita para no seguir mostrando como
-- venta normal un pedido que el cliente devolvió.
SET @existe := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name   = 'pedidos_shopify'
      AND column_name  = 'estado'
);
SET @sql := IF(@existe = 0,
    'ALTER TABLE pedidos_shopify
       ADD COLUMN estado VARCHAR(20) NOT NULL DEFAULT ''pagado''
       COMMENT ''pagado | reembolso_parcial | reembolsado''
       AFTER moneda',
    'DO 0');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @existe := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name   = 'pedidos_shopify'
      AND column_name  = 'estado_actualizado_at'
);
SET @sql := IF(@existe = 0,
    'ALTER TABLE pedidos_shopify
       ADD COLUMN estado_actualizado_at DATETIME NULL
       COMMENT ''UTC. Cuándo cambió `estado` por última vez, según orders/updated''
       AFTER estado',
    'DO 0');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
