-- =============================================================================
-- Plantilla Tienda de Tatuaje — Combos de la carta («promos»)
-- Migración incremental: se corre SOBRE la base que ya existe.
-- No borra nada y se puede correr dos veces (CREATE TABLE IF NOT EXISTS).
--
-- Cómo cargarlo en Windows (PowerShell no soporta `<` para redirigir entrada):
--     mysql -u root -p --default-character-set=utf8mb4 -e "source schema/carta_combos.sql"
-- o abrirlo en MySQL Workbench con File → Open SQL Script.
-- =============================================================================

SET NAMES utf8mb4;


-- =============================================================================
-- POR QUÉ UNA TABLA Y NO UNA CATEGORÍA LLAMADA «PROMO»
--
-- La idea natural es crear una categoría «Promos» y meter ahí los productos
-- del combo. No funciona, por dos motivos concretos:
--
--   1. `productos.categoria_id` es UNA sola llave. Si el Latte entra a la
--      categoría «Promos», SALE de «Cafés» y desaparece de su sección real
--      de la carta. Para tenerlo en las dos habría que duplicar el producto,
--      y entonces el mismo café vive en dos filas: cambias el precio en una
--      y la otra miente. Es exactamente el problema que este proyecto ya
--      peleó con los precios de Shopify.
--
--   2. Una promo tiene precio propio —«los tres por $6.990»— y una categoría
--      no tiene dónde guardarlo: es slug, nombre y orden.
--
-- Un combo no es una agrupación de productos: es un producto COMPUESTO, con
-- nombre y precio propios, que REFERENCIA productos que siguen viviendo en
-- sus categorías de siempre. De ahí estas dos tablas.
--
-- El nombre NO es `promos` porque esa tabla ya existe y es otra cosa: el
-- banner de la portada. En pantalla las dos se llaman «promo»; en la base
-- tienen nombres distintos para que dentro de seis meses se sepa cuál es
-- cuál al leer el código.
-- =============================================================================

CREATE TABLE IF NOT EXISTS carta_combos (
    id            BIGINT       NOT NULL AUTO_INCREMENT,

    -- Los combos son por marca, igual que los productos y las categorías: un
    -- combo de la cafetería no tiene por qué aparecer en la carta de la otra.
    marca_id      SMALLINT     NOT NULL,

    nombre        VARCHAR(120) NOT NULL COMMENT 'Café + algo dulce',
    descripcion   VARCHAR(300) NULL     COMMENT 'La letra chica, opcional',

    -- El precio del combo completo. No se calcula de los productos a
    -- propósito: la gracia de una promo es justamente que NO es la suma.
    precio_clp    INT          NOT NULL,

    -- LAS FECHAS, con el mismo criterio que `promos` (ver promos.sql):
    -- dos fechas absolutas y no una duración, para que editar el texto un
    -- martes no reinicie ningún plazo.
    inicio_at     DATETIME     NOT NULL COMMENT 'UTC. Antes de esto está programado',

    -- NULL = SIN FECHA DE TÉRMINO: corre hasta que alguien lo apague.
    --
    -- No se usa una fecha muy lejana (2099) para representarlo: sería mentira
    -- en pantalla —«termina el 1 de enero de 2099»— y el contador del banner
    -- mostraría una cuenta regresiva de setenta años. NULL dice exactamente
    -- lo que pasa: no termina.
    fin_at        DATETIME     NULL     COMMENT 'UTC. NULL = no termina hasta que lo apaguen',

    -- EL INTERRUPTOR, aparte de las fechas. Se acabó el brownie a las seis:
    -- se apaga al tiro y se repone después con el plazo original intacto.
    --
    -- Decisión tomada con el dueño: un combo NO se apaga solo cuando se
    -- agota uno de sus productos. El panel lo AVISA, pero no actúa por su
    -- cuenta — que una promo desaparezca sola de la carta sin que nadie la
    -- tocara es más confuso que útil.
    disponible    TINYINT(1)   NOT NULL DEFAULT 1,

    orden         INT          NOT NULL DEFAULT 0 COMMENT 'Dentro de la sección de la carta',

    -- EL PUENTE CON EL BANNER DE LA PORTADA.
    --
    -- Marcado, el banner LEE este combo; no se copia una fila a `promos`.
    -- Copiar nombre y fechas a otra tabla es garantizar que algún día
    -- discrepen. Con esto hay una sola fuente: el combo.
    mostrar_en_banner TINYINT(1) NOT NULL DEFAULT 0,

    -- Compite con las promos del banner por el mismo espacio, con el mismo
    -- criterio que ya usa promos: prioridad más alta primero y, a igualdad,
    -- la que termina antes.
    prioridad     INT          NOT NULL DEFAULT 0,

    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'UTC',
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP COMMENT 'UTC',

    PRIMARY KEY (id),

    -- La consulta de la carta es siempre la misma: los vigentes de una marca,
    -- en orden. El índice la cubre entera.
    KEY idx_combo_vigente (marca_id, disponible, inicio_at, fin_at, orden),

    CONSTRAINT fk_combo_marca FOREIGN KEY (marca_id) REFERENCES marcas(id),

    -- Un combo que termina antes de empezar no se muestra nunca y nadie
    -- entiende por qué. Se rechaza en el controlador y otra vez acá.
    -- Con fin_at NULL esta comprobación da UNKNOWN, y MySQL trata UNKNOWN
    -- como aprobada: un combo sin término pasa sin necesidad de excepciones.
    CONSTRAINT chk_combo_rango  CHECK (fin_at > inicio_at),
    CONSTRAINT chk_combo_precio CHECK (precio_clp >= 0),
    CONSTRAINT chk_combo_nombre CHECK (CHAR_LENGTH(TRIM(nombre)) >= 2)
) ENGINE=InnoDB;


-- =============================================================================
-- QUÉ TRAE CADA COMBO
--
-- Una fila por producto incluido. `cantidad` porque «dos cafés y un brownie»
-- es una promo perfectamente normal y repetir la fila dos veces sería peor.
--
-- El borrado va en CASCADE solo de un lado: si se borra el COMBO, sus ítems
-- se van con él (no significan nada sueltos). Si se intenta borrar un
-- PRODUCTO que está dentro de un combo, la llave lo bloquea a propósito —
-- igual que hoy bloquea borrar un producto que está en una lista de deseos.
-- Mejor un error claro que una promo que se queda sin la mitad en silencio.
-- =============================================================================

CREATE TABLE IF NOT EXISTS carta_combo_items (
    id          BIGINT NOT NULL AUTO_INCREMENT,
    combo_id    BIGINT NOT NULL,
    producto_id BIGINT NOT NULL,
    cantidad    INT    NOT NULL DEFAULT 1,

    PRIMARY KEY (id),

    -- El mismo producto no se repite dentro de un combo: para dos cafés está
    -- `cantidad`. Sin esto, dos filas iguales harían que la carta liste
    -- «Latte, Latte» en vez de «2× Latte».
    UNIQUE KEY uq_combo_producto (combo_id, producto_id),
    KEY idx_item_producto (producto_id),

    CONSTRAINT fk_item_combo    FOREIGN KEY (combo_id)
        REFERENCES carta_combos(id) ON DELETE CASCADE,
    CONSTRAINT fk_item_producto FOREIGN KEY (producto_id)
        REFERENCES productos(id),

    CONSTRAINT chk_item_cantidad CHECK (cantidad >= 1)
) ENGINE=InnoDB;


-- =============================================================================
-- PARA LAS BASES QUE YA TENÍAN LA TABLA
--
-- El CREATE de arriba es IF NOT EXISTS, así que en una base donde los combos
-- ya existen no haría nada y `fin_at` seguiría siendo NOT NULL. Esto lo
-- corrige, y se puede correr las veces que sea: si la columna ya acepta NULL,
-- no hace nada.
--
-- MySQL 8 no tiene un `MODIFY ... IF`, así que la idempotencia se hace a mano
-- mirando information_schema, igual que en las otras migraciones del proyecto.
-- =============================================================================

SET @acepta_null := (
    SELECT IS_NULLABLE FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name   = 'carta_combos'
      AND column_name  = 'fin_at'
);
SET @sql := IF(@acepta_null = 'NO',
    'ALTER TABLE carta_combos
       MODIFY fin_at DATETIME NULL
       COMMENT ''UTC. NULL = no termina hasta que lo apaguen''',
    'DO 0');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
