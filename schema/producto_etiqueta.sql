-- =============================================================================
-- Plantilla Tienda de Tatuaje — Etiqueta opcional de los productos de la carta
-- Migración incremental: se corre SOBRE la base que ya existe.
--
-- El admin y Carta.menu() usan esta columna. Antes solo se agregaba dentro de
-- los archivos seed; una instalación deliberadamente vacía quedaba sin ella y
-- fallaban tanto el INSERT del admin como la lectura pública de ambas marcas.
--
-- No borra ni inserta productos. Se puede correr más de una vez.
-- =============================================================================

SET NAMES utf8mb4;

SET @existe := (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'productos'
      AND column_name = 'etiqueta'
);

SET @sql := IF(
    @existe = 0,
    'ALTER TABLE productos
       ADD COLUMN etiqueta VARCHAR(30) NULL
       COMMENT ''Favorito, Nuevo, Verano...''
       AFTER descripcion',
    'DO 0'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

