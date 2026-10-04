-- =============================================================================
-- Plantilla Tienda de Tatuaje — Pedidos para retiro
-- Migración incremental: se corre SOBRE la base que ya existe.
-- No borra nada y se puede correr dos veces (CREATE TABLE IF NOT EXISTS).
--
-- Cómo cargarlo en Windows (PowerShell no soporta `<` para redirigir entrada):
--     mysql -u root -p --default-character-set=utf8mb4 -e "source schema/barra_pedidos.sql"
-- o abrirlo en MySQL Workbench con File → Open SQL Script.
-- =============================================================================

SET NAMES utf8mb4;


-- =============================================================================
-- LA IDEA
--
-- Alguien pide desde la página, elige una franja horaria («sábado 10:15») y
-- pasa a buscarlo. Paga al retirar. No hay mesas, no hay delivery, no hay
-- carrito de Shopify: es la carta del local con un reloj.
--
-- Está pensado para el negocio más chico posible —una barra en la casa de
-- alguien, un carrito, una ventana— donde lo que se acaba no es el café sino
-- las manos: quien prepara puede hacer N pedidos cada cuarto de hora y no
-- más. Por eso el límite no es de productos, es de PEDIDOS POR FRANJA.
-- =============================================================================


-- =============================================================================
-- BARRA_CONFIG — UNA sola fila, id = 1
--
-- Una tabla de una fila en vez de variables de entorno porque esto lo cambia
-- el dueño desde el panel, un martes cualquiera, sin redesplegar: «hoy abro
-- solo hasta las 11», «esta semana no atiendo». Lo que vive en el .env es lo
-- que se decide al instalar; esto es lo que se decide al levantarse.
-- =============================================================================

CREATE TABLE IF NOT EXISTS barra_config (
    id                 TINYINT      NOT NULL,

    -- EL INTERRUPTOR GENERAL. Nace APAGADO: una plantilla recién instalada
    -- no puede ofrecer un botón «Pedir para retirar» que lleve a un negocio
    -- que todavía no decidió sus horarios. Mientras esté en 0, ningún enlace
    -- público lo menciona y /pedir dice que no se están tomando pedidos.
    activo             TINYINT(1)   NOT NULL DEFAULT 0,

    -- Qué días se atiende, como lista de números ISO: 1 = lunes … 7 = domingo.
    -- Texto y no siete columnas: se lee y se escribe de una vez desde siete
    -- casillas, y no hay consultas que filtren por día.
    dias               VARCHAR(20)  NOT NULL DEFAULT '1,2,3,4,5,6',

    -- La ventana del día, en hora de Chile (no UTC: «abro a las 8» es una
    -- hora de reloj de pared y tiene que seguir siéndolo cuando cambia el
    -- horario de verano). La última franja es la que EMPIEZA antes de
    -- hora_fin: con 08:00–11:00 cada 15 min, la última es 10:45.
    hora_inicio        TIME         NOT NULL DEFAULT '08:00:00',
    hora_fin           TIME         NOT NULL DEFAULT '11:00:00',
    intervalo_min      SMALLINT     NOT NULL DEFAULT 15,

    -- El límite real del negocio: cuántos pedidos alcanza a preparar en una
    -- franja. Se CUENTA contra los pedidos vivos; no hay columna de «cupos
    -- tomados» que se desincronice (mismo criterio que las actividades).
    cupos_por_franja   SMALLINT     NOT NULL DEFAULT 3,

    -- Unidades máximas por pedido. Sin esto, un solo pedido de 20 cafés se
    -- come la mañana entera con un cupo.
    max_items          SMALLINT     NOT NULL DEFAULT 6,

    -- Cuánto antes hay que pedir. Con 20, a las 9:50 la primera franja que
    -- se ofrece es la de las 10:15 (la de las 10:00 ya no alcanza).
    anticipacion_min   SMALLINT     NOT NULL DEFAULT 20,

    -- Cuántos días hacia adelante se puede pedir: 0 = solo hoy, 1 = hoy y
    -- mañana. Más que eso rara vez sirve en una barra: nadie sabe qué café
    -- quiere el jueves.
    dias_adelante      TINYINT      NOT NULL DEFAULT 1,

    -- Qué parte de la carta se puede pedir. Lista de ids de categoría;
    -- NULL = todas. Existe porque en la barra de la casa quizá no se hace
    -- todo lo que hay en la carta del local.
    categorias         VARCHAR(255) NULL,
    incluir_combos     TINYINT(1)   NOT NULL DEFAULT 1,

    -- DÓNDE SE RETIRA, en dos niveles, porque puede ser una casa:
    --   lugar_publico     lo que ve cualquiera en /pedir («Villa Los Robles»).
    --   direccion_retiro  la dirección exacta, que SOLO aparece en la página
    --                     del pedido, o sea, a quien ya pidió. No hace falta
    --                     publicar en internet dónde vive uno para venderle
    --                     un café a un vecino.
    lugar_publico      VARCHAR(120) NULL,
    direccion_retiro   VARCHAR(200) NULL,

    -- Una línea libre arriba del formulario: «Este sábado solo filtrados».
    aviso              VARCHAR(300) NULL,

    actualizado_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP COMMENT 'UTC',

    PRIMARY KEY (id),
    CONSTRAINT chk_barra_config_unica CHECK (id = 1)
) ENGINE=InnoDB;

-- La fila única. INSERT IGNORE: si ya existe (segunda corrida), no la pisa.
INSERT IGNORE INTO barra_config (id) VALUES (1);


-- =============================================================================
-- BARRA_PEDIDOS
-- =============================================================================

CREATE TABLE IF NOT EXISTS barra_pedidos (
    id              BIGINT       NOT NULL AUTO_INCREMENT,

    -- 'PD-4KQ7-9XTM'. Es la llave de la página del pedido (/pedido/<codigo>):
    -- quien lo tiene ve el estado y la dirección de retiro. Por eso es azar
    -- de `secrets` y no el id correlativo, que se adivina sumando uno.
    codigo          VARCHAR(20)  NOT NULL,

    -- NULL si pidió sin cuenta, que es lo normal. Pedir un café no exige
    -- registrarse; si tiene sesión iniciada, queda asociado igual.
    usuario_id      BIGINT       NULL,

    -- Con esto se le llama por su nombre al entregar y se le escribe si
    -- pasa algo. El teléfono es obligatorio por la misma razón que en las
    -- actividades: es el único canal que llega sí o sí.
    nombre          VARCHAR(60)  NOT NULL,
    telefono        VARCHAR(20)  NOT NULL COMMENT 'Normalizado: +56912345678',

    -- El comienzo de la franja elegida, en UTC.
    franja_at       DATETIME     NOT NULL COMMENT 'UTC. Inicio de la franja',

    -- recibido     llegó, nadie lo ha tocado. Es el único en que el cliente
    --              todavía puede cancelarlo solo.
    -- preparando   se está haciendo.
    -- listo        esperando que lo vengan a buscar.
    -- entregado    se lo llevó. Fin.
    -- cancelado    lo canceló el cliente (desde recibido) o el admin.
    -- no_retirado  pasó la hora y nunca vino. Se distingue de cancelado
    --              porque es un dato: quien no retira dos veces, el panel
    --              lo muestra antes de que vuelva a pedir.
    estado          ENUM('recibido','preparando','listo','entregado',
                         'cancelado','no_retirado')
                                 NOT NULL DEFAULT 'recibido',
    estado_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'UTC. Último cambio de estado',

    -- CÓMO PAGA. Hoy existe solo 'al_retirar'. 'en_linea' queda declarado
    -- para cuando se conecte Mercado Pago, y NINGÚN formulario lo ofrece
    -- todavía: un botón de pagar que no cobra es peor que no tenerlo.
    -- Declararlo ahora evita reescribir el ENUM entero en esa migración.
    metodo_pago     ENUM('al_retirar','en_linea') NOT NULL DEFAULT 'al_retirar',
    pagado_at       DATETIME     NULL COMMENT 'UTC. NULL = no se ha cobrado',

    -- Suma de los ítems, calculada en el servidor con los precios de la base
    -- en el momento del pedido. Lo que mande el navegador no se usa nunca.
    total_clp       INT          NOT NULL,

    notas           VARCHAR(200) NULL COMMENT 'Sin azúcar, leche aparte…',

    -- «ESTOY AFUERA». El cliente toca el botón al llegar y el panel lo
    -- marca: así quien está en la barra no tiene que mirar por la ventana.
    -- `afuera_detalle` es opcional y libre: «auto gris», «en la reja».
    afuera_at       DATETIME     NULL COMMENT 'UTC',
    afuera_detalle  VARCHAR(80)  NULL,

    creado_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'UTC',

    PRIMARY KEY (id),
    UNIQUE KEY uq_barra_pedidos_codigo (codigo),
    -- La cola del día y el conteo de cupos filtran por franja y estado.
    KEY ix_barra_pedidos_franja (franja_at, estado),
    -- «¿Cuántos pedidos vivos tiene este teléfono?» y «¿cuántas veces no
    -- retiró?».
    KEY ix_barra_pedidos_telefono (telefono, estado),
    CONSTRAINT fk_barra_pedidos_usuario FOREIGN KEY (usuario_id)
        REFERENCES usuarios(id) ON DELETE SET NULL
) ENGINE=InnoDB;


-- =============================================================================
-- BARRA_PEDIDO_ITEMS
--
-- Nombre y precio se COPIAN al pedido, a diferencia de los combos (que
-- referencian). La razón es la contraria: un combo describe lo que se vende
-- HOY y tiene que seguir al producto si cambia; un pedido es lo que se vendió
-- AYER, y si mañana el Latte sube a $3.800, el pedido de ayer tiene que
-- seguir diciendo $3.500. El id queda para estadísticas, y se suelta (SET
-- NULL) si el producto se borra: el pedido no se pierde por eso.
--
-- Cada fila es un producto O un combo, nunca los dos.
-- =============================================================================

CREATE TABLE IF NOT EXISTS barra_pedido_items (
    id           BIGINT       NOT NULL AUTO_INCREMENT,
    pedido_id    BIGINT       NOT NULL,
    producto_id  BIGINT       NULL,
    combo_id     BIGINT       NULL,
    nombre       VARCHAR(150) NOT NULL COMMENT 'Copia al momento del pedido',
    precio_clp   INT          NOT NULL COMMENT 'Unitario, copia al momento del pedido',
    cantidad     SMALLINT     NOT NULL,

    PRIMARY KEY (id),
    KEY ix_barra_items_pedido (pedido_id),
    CONSTRAINT fk_barra_items_pedido FOREIGN KEY (pedido_id)
        REFERENCES barra_pedidos(id) ON DELETE CASCADE,
    CONSTRAINT fk_barra_items_producto FOREIGN KEY (producto_id)
        REFERENCES productos(id) ON DELETE SET NULL,
    CONSTRAINT fk_barra_items_combo FOREIGN KEY (combo_id)
        REFERENCES carta_combos(id) ON DELETE SET NULL
) ENGINE=InnoDB;
