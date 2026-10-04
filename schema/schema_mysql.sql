-- =============================================================================
-- Plantilla Tienda de Tatuaje — Base de datos, primera parte
-- MySQL 8.0.16+  ·  septiembre 2026
--
-- Contiene: cuentas, carta (marcas / categorías / productos), actividades
--           con inscripciones, lista de deseos y el muro de deseos.
--
-- NO contiene el saldo ni el historial de compras. Eso es a propósito: una
-- columna `saldo` no es una versión simple del ledger, es una versión distinta
-- que después habría que migrar con plata de clientes adentro. Es más fácil no
-- tener billetera que tener una que hay que desarmar.
--
-- Se puede correr muchas veces: todo es CREATE TABLE IF NOT EXISTS e
-- INSERT IGNORE. No hay que correrlo a mano: lo hace instalar_base.py.
-- =============================================================================

-- Fija la codificación de la conexión. Sin esto, según cómo cargues el archivo
-- (consola, pipe de PowerShell, otro cliente) los acentos pueden quedar
-- doble-codificados: 'Café' se guarda como 'CafÃ©' y ya no hay vuelta atrás
-- salvo recargando. Con esta línea da igual desde dónde lo corras.
SET NAMES utf8mb4;

-- La base la crea instalar_base.py (o ya existe, como en Railway). Este
-- archivo NO la borra ni la crea: solo arma las tablas que falten, así que se
-- puede correr las veces que haga falta sin perder nada.


-- =============================================================================
-- 1. MARCAS
-- la marca principal (café) y la segunda marca (pizzas) comparten local, sitio y clientes,
-- pero son SOCIEDADES DISTINTAS, con RUT distinto. Por eso la tabla existe:
-- cada venta tiene que poder atribuirse a la empresa que corresponde.
-- =============================================================================

CREATE TABLE IF NOT EXISTS marcas (
    id            SMALLINT     NOT NULL AUTO_INCREMENT,
    slug          VARCHAR(50)  NOT NULL COMMENT 'Identificador corto para URLs y código',
    nombre        VARCHAR(100) NOT NULL COMMENT 'El nombre comercial, para mostrar',
    razon_social  VARCHAR(150) NULL     COMMENT 'Nombre legal de la sociedad',
    rut           VARCHAR(12)  NULL     COMMENT 'RUT de la empresa',
    tema_css      VARCHAR(50)  NOT NULL COMMENT 'La paleta que aplica el front',
    activa        BOOLEAN      NOT NULL DEFAULT TRUE,
    PRIMARY KEY (id),
    UNIQUE KEY uq_marcas_slug (slug),
    UNIQUE KEY uq_marcas_rut (rut)
) ENGINE=InnoDB;


-- =============================================================================
-- 2. USUARIOS
-- Una sola tabla para clientes, invitados y staff. El invitado que se inscribe
-- a una actividad sin crear cuenta queda con estado='invitado'; cuando después
-- se registre con el mismo correo, hereda su historial en vez de partir de cero.
-- =============================================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id                  BIGINT       NOT NULL AUTO_INCREMENT,
    -- La colación ai_ci ya compara sin distinguir mayúsculas, pero igual
    -- normaliza a minúsculas en la app antes de guardar.
    email               VARCHAR(255) NOT NULL,
    email_verificado_at DATETIME     NULL COMMENT 'UTC. NULL = correo sin confirmar',
    nombre              VARCHAR(45)  NULL,
    apellido            VARCHAR(45)  NULL,
    nickname            VARCHAR(45)  NULL,
    telefono            VARCHAR(20)  NULL COMMENT 'Con esto lo identificas en el mesón',
    -- RUT como '12345678-K'. El dígito verificador puede ser K y hay RUTs con
    -- ceros a la izquierda: por eso nunca INT. Pídelo SOLO si emitirás boleta.
    rut                 VARCHAR(12)  NULL,
    fecha_nacimiento    DATE         NULL COMMENT 'Para la promo de cumpleaños',
    password_hash       VARCHAR(255) NULL COMMENT 'argon2 o bcrypt. Nunca texto plano',
    rol                 ENUM('cliente','barista','admin')     NOT NULL DEFAULT 'cliente',
    estado              ENUM('invitado','activo','bloqueado') NOT NULL DEFAULT 'invitado',
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at          DATETIME     NULL COMMENT 'Borrado lógico: derecho del titular',
    PRIMARY KEY (id),
    UNIQUE KEY uq_usuarios_email (email),
    UNIQUE KEY uq_usuarios_rut (rut),        -- MySQL permite varios NULL en UNIQUE
    KEY idx_usuarios_telefono (telefono),
    KEY idx_usuarios_rol (rol)
) ENGINE=InnoDB;


-- =============================================================================
-- 3. CARTA: CATEGORÍAS Y PRODUCTOS
--
-- SOLO la carta que se consume en el local: cafetería, pastelería, pizzas.
-- El café en grano que se despacha NO va acá: esa es la tienda y vive en
-- Shopify, con su stock, sus variantes (250 g / 1 kg, grano / molido) y sus
-- envíos. Duplicarla en MySQL obligaría a mantener dos catálogos a mano.
--
-- Regla simple: si se sirve en una taza o en un plato, va acá.
--               Si se despacha en una caja, es de Shopify.
-- =============================================================================

CREATE TABLE IF NOT EXISTS categorias (
    id        INT          NOT NULL AUTO_INCREMENT,
    marca_id  SMALLINT     NOT NULL,
    slug      VARCHAR(50)  NOT NULL,
    nombre    VARCHAR(100) NOT NULL,
    orden     INT          NOT NULL DEFAULT 0 COMMENT 'Para ordenar la carta a mano',
    PRIMARY KEY (id),
    UNIQUE KEY uq_categorias_marca_slug (marca_id, slug),
    CONSTRAINT fk_categorias_marca FOREIGN KEY (marca_id) REFERENCES marcas(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS productos (
    id            BIGINT       NOT NULL AUTO_INCREMENT,
    marca_id      SMALLINT     NOT NULL,
    categoria_id  INT          NULL,
    slug          VARCHAR(80)  NOT NULL,
    nombre        VARCHAR(150) NOT NULL,
    descripcion   TEXT         NULL,
    etiqueta      VARCHAR(30)  NULL COMMENT 'Favorito, Nuevo, Verano...',
    -- El precio en puntos NO se guarda: es precio_clp / 10.
    -- Guardar los dos garantiza que algún día se desincronicen.
    precio_clp    INT          NOT NULL COMMENT 'El precio principal. el precio que se muestra primero',
    -- Segundo precio opcional. Las pizzas de la segunda marca vienen en familiar e
    -- individual; todo lo demás (cafés, bebidas, promos) lo deja en NULL.
    -- Dos columnas y no una tabla de variantes porque hoy son exactamente dos
    -- tamaños fijos. Si aparece un tercero, migrar 11 filas es una tarde.
    precio_individual_clp INT  NULL COMMENT 'NULL = el producto tiene un solo precio',
    imagen_url    VARCHAR(255) NULL,
    disponible    BOOLEAN      NOT NULL DEFAULT TRUE COMMENT 'Lo que apagas cuando se acaba',
    orden         INT          NOT NULL DEFAULT 0,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_productos_marca_slug (marca_id, slug),
    KEY idx_productos_carta (marca_id, categoria_id, disponible, orden),
    CONSTRAINT fk_productos_marca     FOREIGN KEY (marca_id)     REFERENCES marcas(id),
    CONSTRAINT fk_productos_categoria FOREIGN KEY (categoria_id) REFERENCES categorias(id),
    CONSTRAINT chk_producto_precio    CHECK (precio_clp >= 0),
    CONSTRAINT chk_producto_precio_ind CHECK (precio_individual_clp IS NULL
                                              OR precio_individual_clp >= 0)
) ENGINE=InnoDB;


-- =============================================================================
-- 4. ACTIVIDADES
-- Catas, talleres y eventos. `inicio_at` y `fin_at` reemplazan al par
-- fecha_actividad + horario_actividad, que se pisaban entre sí.
-- =============================================================================

CREATE TABLE IF NOT EXISTS actividades (
    id                       BIGINT       NOT NULL AUTO_INCREMENT,
    marca_id                 SMALLINT     NULL COMMENT 'NULL = vale para las dos marcas',
    slug                     VARCHAR(80)  NOT NULL COMMENT 'Para la URL',
    nombre                   VARCHAR(150) NOT NULL,
    descripcion              TEXT         NULL,
    inicio_at                DATETIME     NOT NULL COMMENT 'UTC',
    fin_at                   DATETIME     NULL,
    lugar                    VARCHAR(200) NULL,
    imagen_url               VARCHAR(500) NULL COMMENT 'URL del afiche. Se muestra entero, no recortado',
    cupos                    SMALLINT     NOT NULL,
    precio_clp               INT          NOT NULL DEFAULT 0 COMMENT '0 = gratis',
    google_calendar_event_id VARCHAR(120) NULL COMMENT 'Para el botón del calendario',
    estado                   ENUM('borrador','publicada','cancelada','realizada')
                                          NOT NULL DEFAULT 'borrador',
    created_at               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_actividades_slug (slug),
    KEY idx_actividades_agenda (estado, inicio_at),
    CONSTRAINT fk_actividades_marca FOREIGN KEY (marca_id) REFERENCES marcas(id),
    CONSTRAINT chk_actividad_cupos  CHECK (cupos > 0),
    CONSTRAINT chk_actividad_fin    CHECK (fin_at IS NULL OR fin_at > inicio_at)
) ENGINE=InnoDB;


-- =============================================================================
-- 5. INSCRIPCIONES
-- Antes era solo un puente entre usuarios y actividades. Ahora tiene datos
-- propios (estado del pago, monto, referencia), así que lleva id propio.
-- =============================================================================

CREATE TABLE IF NOT EXISTS usuarios_en_actividad (
    id            BIGINT       NOT NULL AUTO_INCREMENT,
    actividad_id  BIGINT       NOT NULL,
    usuario_id    BIGINT       NOT NULL COMMENT 'El invitado también es un usuario',
    estado        ENUM('pendiente','pagada','cancelada','asistio','no_asistio')
                               NOT NULL DEFAULT 'pendiente',
    monto_clp     INT          NOT NULL DEFAULT 0,
    pago_ref      VARCHAR(100) NULL COMMENT 'Id de la orden en Shopify',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_inscripcion (actividad_id, usuario_id),   -- nadie se inscribe dos veces
    KEY idx_inscripciones_estado (actividad_id, estado),
    CONSTRAINT fk_inscripcion_actividad FOREIGN KEY (actividad_id) REFERENCES actividades(id),
    CONSTRAINT fk_inscripcion_usuario   FOREIGN KEY (usuario_id)   REFERENCES usuarios(id),
    CONSTRAINT chk_inscripcion_monto    CHECK (monto_clp >= 0)
) ENGINE=InnoDB;


-- =============================================================================
-- 6. LISTA DE DESEOS
-- Antes era texto libre. Apuntando a productos sirve para algo concreto:
-- saber qué quiere la gente que aún no vendes o que se te acaba seguido.
-- =============================================================================

CREATE TABLE IF NOT EXISTS deseos (
    id           BIGINT   NOT NULL AUTO_INCREMENT,
    usuario_id   BIGINT   NOT NULL,
    producto_id  BIGINT   NULL,
    nota         TEXT     NULL COMMENT 'Para lo que todavía no está en la carta',
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_deseo (usuario_id, producto_id),
    CONSTRAINT fk_deseos_usuario  FOREIGN KEY (usuario_id)  REFERENCES usuarios(id) ON DELETE CASCADE,
    CONSTRAINT fk_deseos_producto FOREIGN KEY (producto_id) REFERENCES productos(id)
) ENGINE=InnoDB;


-- =============================================================================
-- DATOS INICIALES
-- =============================================================================

-- Completa razon_social y rut cuando los tengas a mano.
-- Las dos marcas de ejemplo. El slug 'principal' es el que espera
-- flask_app/config/negocio.py (NEGOCIO_SLUG); si lo cambias acá, cámbialo
-- allá. El nombre sí es solo para el panel de administración: lo que ve el
-- público sale de negocio.py.
--
-- La segunda marca existe para el local que vende dos cosas con identidades
-- distintas —café de día, pizzas de noche—. Si tu cliente tiene una sola,
-- deja MARCA2_ACTIVA en «no» y esta fila simplemente no se usa.
INSERT IGNORE INTO marcas (slug, nombre, tema_css) VALUES
    ('principal',     'Tienda',  'lp'),
    ('segunda-marca', 'Estudio', 'segunda-marca');

-- Las categorías del catálogo: son las pestañas, en este orden. Se
-- cambian desde /admin/carta sin tocar este archivo. INSERT IGNORE: si ya
-- existen (segunda corrida, o las editaste), no se tocan.
INSERT IGNORE INTO categorias (marca_id, slug, nombre, orden)
SELECT m.id, c.slug, c.nombre, c.orden
FROM marcas m
JOIN (
    SELECT 'cartuchos'      AS slug, 'Cartuchos'            AS nombre, 1 AS orden UNION ALL
    SELECT 'agujas',                 'Agujas y tubos',              2 UNION ALL
    SELECT 'tintas',                 'Tintas',                      3 UNION ALL
    SELECT 'maquinas',               'Máquinas',                    4 UNION ALL
    SELECT 'fuentes',                'Fuentes de poder',            5 UNION ALL
    SELECT 'bioseguridad',           'Bioseguridad',                6 UNION ALL
    SELECT 'cuidado',                'Cuidado post-tatuaje',        7 UNION ALL
    SELECT 'accesorios',             'Accesorios',                  8
) c
WHERE m.slug = 'principal';

-- La segunda marca (apagada por defecto) es para una tienda que además
-- tiene un estudio con su propia identidad: sus «categorías» serían los
-- servicios del estudio.
INSERT IGNORE INTO categorias (marca_id, slug, nombre, orden)
SELECT m.id, c.slug, c.nombre, c.orden
FROM marcas m
JOIN (
    SELECT 'tatuajes' AS slug, 'Tatuajes' AS nombre, 1 AS orden UNION ALL
    SELECT 'piercing',         'Piercing',           2
) c
WHERE m.slug = 'segunda-marca';

-- LA CUENTA DE ADMINISTRADOR NO SE SIEMBRA ACÁ, y es una regla de seguridad,
-- no una molestia (auditoría 2026-09-16).
--
-- Antes esta línea creaba un correo conocido con rol admin y el hash en
-- NULL, de cuando el registro era una maqueta. Con el registro real eso quedó
-- siendo una puerta: el formulario trata a toda cuenta sin contraseña como un
-- «invitado» reclamable, así que cualquiera que se registrara con ese correo
-- —que está publicado en el pie del sitio— se quedaba con la cuenta Y con su
-- rol de administrador. El registro ya no lo permite, y acá tampoco se deja
-- la cuenta servida.
--
-- El administrador se crea con contraseña, desde la máquina, una sola vez:
--
--     python crear_admin.py
--
-- y después, en la base:  UPDATE usuarios SET rol='admin' WHERE email='...';


-- =============================================================================
-- COMPROBACIÓN
-- =============================================================================

SELECT table_name AS tabla, table_rows AS filas
FROM information_schema.tables
WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'
ORDER BY table_name;


-- =============================================================================
-- 8. MURO_MENSAJES
-- El muro de deseos de la portada: alguien con cuenta escribe algo sobre la
-- cafetería y el admin lo aprueba antes de que se publique.
--
-- NO CONFUNDIR CON `deseos` (la tabla de arriba), que es la lista de deseos
-- de productos de la carta. Son dos cosas distintas y por eso esta lleva el
-- prefijo `muro_`.
-- =============================================================================

CREATE TABLE IF NOT EXISTS muro_mensajes (
    id            BIGINT       NOT NULL AUTO_INCREMENT,
    usuario_id    BIGINT       NOT NULL COMMENT 'Hay que tener cuenta para escribir',
    -- COPIA del nickname al enviar, no un JOIN a usuarios. El admin aprueba
    -- un par nickname + mensaje; si el nombre saliera por JOIN, alguien
    -- podría hacerse aprobar un mensaje amable y después cambiarse el
    -- nickname del perfil por un insulto, ya publicado en la portada.
    nickname      VARCHAR(45)  NOT NULL,
    mensaje       VARCHAR(280) NOT NULL COMMENT 'Un deseo, no un ensayo',
    estado        ENUM('pendiente','aprobado','rechazado')
                               NOT NULL DEFAULT 'pendiente',
    motivo        VARCHAR(140) NULL COMMENT 'Nota privada del admin. Nunca se muestra',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'UTC',
    revisado_at   DATETIME     NULL COMMENT 'UTC. NULL = nadie lo ha mirado',
    revisado_por  BIGINT       NULL,
    PRIMARY KEY (id),
    KEY idx_muro_publico (estado, created_at DESC),   -- la consulta del público
    KEY idx_muro_usuario (usuario_id, estado, created_at),  -- el freno anti-spam
    CONSTRAINT fk_muro_usuario FOREIGN KEY (usuario_id)
        REFERENCES usuarios(id) ON DELETE CASCADE,
    -- Sin CASCADE: borrar la cuenta del admin no puede llevarse los mensajes
    -- que revisó.
    CONSTRAINT fk_muro_revisor FOREIGN KEY (revisado_por)
        REFERENCES usuarios(id),
    CONSTRAINT chk_muro_mensaje CHECK (CHAR_LENGTH(TRIM(mensaje)) >= 3)
) ENGINE=InnoDB;
