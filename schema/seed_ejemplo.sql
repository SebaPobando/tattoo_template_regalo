-- =============================================================================
-- Plantilla Tienda de Tatuaje — Catálogo de EJEMPLO
--
-- Productos inventados, para que el sitio no se vea vacío el primer día y para
-- que quien lo recibe entienda de una mirada cómo se llena el catálogo.
--
-- BÓRRALOS antes de abrir al público, desde /admin/carta (o cámbiales el
-- nombre y el precio por los de verdad).
--
-- Los precios son redondos a propósito: son de mentira y tienen que parecerlo.
-- Las marcas son genéricas a propósito: no es publicidad de nadie.
--
-- Se carga con:   python instalar_base.py --ejemplos
-- Se puede correr dos veces: INSERT IGNORE no duplica nada.
-- =============================================================================

SET NAMES utf8mb4;

SET @marca1 = (SELECT id FROM marcas WHERE slug = 'principal' LIMIT 1);

-- Las categorías vienen de schema_mysql.sql. Se buscan por slug y no por id
-- para que este archivo funcione aunque hayas agregado o borrado categorías.
SET @cartuchos    = (SELECT id FROM categorias WHERE marca_id = @marca1 AND slug = 'cartuchos'    LIMIT 1);
SET @agujas       = (SELECT id FROM categorias WHERE marca_id = @marca1 AND slug = 'agujas'       LIMIT 1);
SET @tintas       = (SELECT id FROM categorias WHERE marca_id = @marca1 AND slug = 'tintas'       LIMIT 1);
SET @maquinas     = (SELECT id FROM categorias WHERE marca_id = @marca1 AND slug = 'maquinas'     LIMIT 1);
SET @fuentes      = (SELECT id FROM categorias WHERE marca_id = @marca1 AND slug = 'fuentes'      LIMIT 1);
SET @bioseguridad = (SELECT id FROM categorias WHERE marca_id = @marca1 AND slug = 'bioseguridad' LIMIT 1);
SET @cuidado      = (SELECT id FROM categorias WHERE marca_id = @marca1 AND slug = 'cuidado'      LIMIT 1);
SET @accesorios   = (SELECT id FROM categorias WHERE marca_id = @marca1 AND slug = 'accesorios'   LIMIT 1);

INSERT IGNORE INTO productos
    (marca_id, categoria_id, slug, nombre, descripcion, etiqueta, precio_clp, disponible, orden)
VALUES
    (@marca1, @cartuchos, 'cartuchos-rl-caja-20', 'Cartuchos Round Liner · caja de 20',
     'Para línea. Elige el calibre al pedir: 1, 3, 5, 7 o 9 RL. Membrana de seguridad.', 'Más vendido', 15000, 1, 1),
    (@marca1, @cartuchos, 'cartuchos-m1-caja-20', 'Cartuchos Magnum · caja de 20',
     'Para relleno y sombra: 7, 9, 11 o 13 M1. Membrana de seguridad.', NULL, 16000, 1, 2),
    (@marca1, @cartuchos, 'cartuchos-rm-caja-20', 'Cartuchos Curved Magnum · caja de 20',
     'Para degradados suaves: 9, 11, 13 o 15 RM.', NULL, 16000, 0, 3),

    (@marca1, @agujas, 'agujas-rl-caja-50', 'Agujas Round Liner · caja de 50',
     'Para máquina de bobina o rotativa con tubo. Esterilizadas.', NULL, 12000, 1, 1),
    (@marca1, @agujas, 'tubos-desechables-caja-50', 'Tubos desechables · caja de 50',
     'Grip de 25 mm, punta según la aguja.', NULL, 14000, 1, 2),

    (@marca1, @tintas, 'tinta-negra-linea-120', 'Tinta negra para línea · 120 ml',
     'Negro intenso, de secado parejo.', NULL, 18000, 1, 1),
    (@marca1, @tintas, 'tinta-negra-sombra-240', 'Tinta negra para sombra · 240 ml',
     'Rinde para lavados y grises.', NULL, 25000, 1, 2),
    (@marca1, @tintas, 'set-grises-6', 'Set de grises · 6 tonos',
     'Seis diluciones listas, de la más clara a la más oscura.', 'Nuevo', 45000, 1, 3),
    (@marca1, @tintas, 'tinta-blanca-30', 'Tinta blanca · 30 ml',
     'Para luces y detalles.', NULL, 9000, 1, 4),

    (@marca1, @maquinas, 'maquina-pen-rotativa', 'Máquina pen rotativa',
     'Inalámbrica, carrera de 3,5 mm. Batería de recambio incluida.', NULL, 180000, 1, 1),
    (@marca1, @maquinas, 'maquina-rotativa-clasica', 'Máquina rotativa clásica',
     'Con cable RCA. Liviana y silenciosa.', NULL, 90000, 1, 2),

    (@marca1, @fuentes, 'fuente-digital', 'Fuente de poder digital',
     'Pantalla con voltaje y tiempo de sesión. Incluye pedal.', NULL, 60000, 1, 1),
    (@marca1, @fuentes, 'cable-rca', 'Cable RCA',
     'Repuesto, 1,8 m.', NULL, 8000, 1, 2),

    (@marca1, @bioseguridad, 'guantes-nitrilo-negro-100', 'Guantes de nitrilo negros · caja de 100',
     'Sin polvo. Tallas S, M y L.', 'Más vendido', 10000, 1, 1),
    (@marca1, @bioseguridad, 'film-barrera-rollo', 'Film barrera · rollo',
     'Para máquina, cables y superficies.', NULL, 7000, 1, 2),
    (@marca1, @bioseguridad, 'bolsas-maquina-200', 'Bolsas para máquina · 200 unidades',
     'Cubren la máquina entera.', NULL, 9000, 1, 3),
    (@marca1, @bioseguridad, 'jabon-verde-500', 'Jabón verde · 500 ml',
     'Para limpiar la piel durante la sesión.', NULL, 8000, 1, 4),

    (@marca1, @cuidado, 'film-cicatrizante-rollo', 'Film cicatrizante · rollo de 10 m',
     'Segunda piel transpirable para los primeros días.', NULL, 22000, 1, 1),
    (@marca1, @cuidado, 'crema-cicatrizante-50', 'Crema cicatrizante · 50 g',
     'Para recomendar o revender a tus clientes.', NULL, 7000, 1, 2),

    (@marca1, @accesorios, 'papel-transfer-100', 'Papel transfer · 100 hojas',
     'Para impresora térmica o a mano.', NULL, 25000, 1, 1),
    (@marca1, @accesorios, 'vasitos-tinta-1000', 'Vasitos para tinta · 1.000 unidades',
     'Tamaño mediano.', NULL, 5000, 1, 2);

-- Un pack de ejemplo: varios productos a un precio. Sale en el catálogo
-- como una sección aparte y se edita en /admin/carta → Packs.
INSERT INTO carta_combos (marca_id, nombre, descripcion, precio_clp, inicio_at, fin_at, disponible, orden)
SELECT @marca1, 'Pack bioseguridad semanal',
       'Guantes, film barrera y bolsas para máquina.', 24000,
       UTC_TIMESTAMP(), NULL, 1, 1
WHERE NOT EXISTS (SELECT 1 FROM carta_combos WHERE nombre = 'Pack bioseguridad semanal');

SET @pack = (SELECT id FROM carta_combos WHERE nombre = 'Pack bioseguridad semanal' LIMIT 1);
INSERT IGNORE INTO carta_combo_items (combo_id, producto_id, cantidad)
SELECT @pack, id, 1 FROM productos
WHERE slug IN ('guantes-nitrilo-negro-100', 'film-barrera-rollo', 'bolsas-maquina-200');

-- Un curso de ejemplo, para que la agenda de la portada muestre algo.
-- Está en BORRADOR: no aparece en el sitio hasta que lo publiques desde
-- /admin/actividades. Así nadie se inscribe a un curso que no existe.
INSERT IGNORE INTO actividades
    (marca_id, slug, nombre, descripcion, lugar, inicio_at, fin_at,
     cupos, precio_clp, estado)
VALUES
    (@marca1, 'curso-de-ejemplo', 'Capacitación en bioseguridad',
     'Tres horas sobre montaje y desmontaje de la estación, barreras, manejo de residuos y limpieza. Incluye un pack de bioseguridad para llevar.',
     'En la tienda',
     DATE_ADD(UTC_TIMESTAMP(), INTERVAL 21 DAY),
     DATE_ADD(UTC_TIMESTAMP(), INTERVAL 21 DAY) + INTERVAL 3 HOUR,
     12, 30000, 'borrador');

SELECT c.nombre AS categoria, COUNT(p.id) AS productos
FROM categorias c LEFT JOIN productos p ON p.categoria_id = c.id
WHERE c.marca_id = @marca1
GROUP BY c.id, c.nombre
ORDER BY c.orden;
