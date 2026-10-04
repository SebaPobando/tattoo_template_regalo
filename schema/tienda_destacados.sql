-- =============================================================================
-- Plantilla Tienda de Tatuaje — Cafés destacados de la tienda
-- Migración incremental: se corre SOBRE la base que ya existe.
-- No borra nada y se puede correr dos veces (CREATE TABLE IF NOT EXISTS).
--
-- Cómo cargarlo en Windows (PowerShell no soporta `<` para redirigir entrada):
--     mysql -u root -p --default-character-set=utf8mb4 -e "source schema/tienda_destacados.sql"
-- o abrirlo en MySQL Workbench con File → Open SQL Script.
-- =============================================================================

SET NAMES utf8mb4;


-- =============================================================================
-- TIENDA_DESTACADOS — los productos de Shopify que el admin resalta
--
-- El catálogo (nombres, precios, stock) sigue viviendo en Shopify y no se
-- copia acá. Esta tabla guarda SOLO la decisión del local sobre cómo
-- mostrarlo: este producto va destacado, con este color, esta cinta y en
-- este lugar. Una fila = un producto destacado; sacarlo es borrar la fila.
--
-- Se identifica por el HANDLE de Shopify («el-oso-250-gr»), que es el mismo
-- id que ya usan la ficha y el carrito. Si alguien cambia el handle en
-- Shopify, el destacado deja de calzar y el panel lo muestra como «ya no
-- está en la tienda»: no se pierde en silencio.
-- =============================================================================

CREATE TABLE IF NOT EXISTS tienda_destacados (
    handle      VARCHAR(255) NOT NULL,

    -- Un color de una lista fija (ver COLORES en destacado_model.py), no un
    -- hex libre: así cualquier combinación que elija el admin se ve bien y
    -- respeta la marca.
    color       VARCHAR(20)  NOT NULL DEFAULT 'dorado',

    -- El texto de la cinta sobre la foto: «Micro lote», «Edición especial».
    cinta       VARCHAR(30)  NOT NULL DEFAULT 'Edición especial',

    -- Entre los destacados, cuál va primero. Menor = antes.
    orden       SMALLINT     NOT NULL DEFAULT 0,

    creado_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'UTC',

    PRIMARY KEY (handle)
) ENGINE=InnoDB;
