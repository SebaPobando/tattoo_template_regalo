-- =============================================================================
-- Plantilla Tienda de Tatuaje — Afiche de las actividades
-- Migración incremental: se corre SOBRE la base que ya existe.
--
-- Agrega `imagen_url` a `actividades`. No borra nada y se puede correr dos
-- veces sin romper nada.
--
-- Cómo cargarlo en Windows (PowerShell no soporta `<` para redirigir entrada):
--     mysql -u root -p --default-character-set=utf8mb4 -e "source schema/actividad_imagen.sql"
-- =============================================================================

SET NAMES utf8mb4;

-- MySQL 8 NO tiene `ADD COLUMN IF NOT EXISTS` (eso es de MariaDB), así que la
-- idempotencia se hace a mano: se mira information_schema y, si la columna ya
-- está, se ejecuta un DO 0 que no hace nada.
--
-- Ojo con information_schema: devuelve los nombres de columna en MAYÚSCULAS
-- según el cliente. Acá no molesta porque se usa COUNT(*), pero es la misma
-- trampa que ya mordió una vez desde PyMySQL.
SET @existe := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name   = 'actividades'
      AND column_name  = 'imagen_url'
);

SET @sql := IF(@existe = 0,
    'ALTER TABLE actividades
       ADD COLUMN imagen_url VARCHAR(500) NULL
       COMMENT ''URL del afiche. Se muestra entero, no recortado''
       AFTER lugar',
    'DO 0');

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
