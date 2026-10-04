-- =============================================================================
-- Plantilla Tienda de Tatuaje — Promos de la portada
-- Migración incremental: se corre SOBRE la base que ya existe.
--
-- No borra nada, no toca ninguna tabla existente y se puede correr dos veces
-- (CREATE TABLE IF NOT EXISTS).
--
-- Cómo cargarlo en Windows (PowerShell no soporta `<` para redirigir):
--     mysql -u root -p --default-character-set=utf8mb4 -e "source schema/promos.sql"
-- o abrirlo en MySQL Workbench con File → Open SQL Script.
-- =============================================================================

SET NAMES utf8mb4;


-- =============================================================================
-- PROMOS — lo que se anuncia en la portada, con su plazo
--
-- POR QUÉ DOS FECHAS Y NO UNA DURACIÓN:
--
-- La alternativa era guardar «dura 48 horas» y contarlas desde la publicación.
-- Suena más simple hasta el primer cambio: si el dueño edita la promo el
-- martes para corregir una palabra, ¿se reinicia el plazo? Con dos fechas
-- absolutas no hay nada que interpretar, y editar el texto no mueve el plazo.
-- La comodidad («24 horas», «hasta el domingo») vive en los botones del
-- formulario, que rellenan `fin_at`; lo que se guarda es siempre una fecha.
--
-- UTC, como todo lo demás en esta base. Chile cambia de huso dos veces al año
-- y una promo que cruza el cambio de horario se correría una hora. Ver
-- config/tiempo.py, donde esa regla está escrita completa.
-- =============================================================================

CREATE TABLE IF NOT EXISTS promos (
    id             BIGINT       NOT NULL AUTO_INCREMENT,

    -- El titular del banner y el texto de la burbuja: «Filtrados 2x1».
    nombre         VARCHAR(80)  NOT NULL,

    -- La letra chica: días, horario, condiciones. Opcional a propósito: una
    -- promo que se explica sola no necesita una segunda línea.
    bajada         VARCHAR(180) NULL,

    -- El botón es opcional, y cuando existe apunta SOLO al propio sitio.
    -- `boton_destino` se valida en el controlador: tiene que empezar con '#'
    -- o con '/' y no con '//'. Aceptar una URL cualquiera sería un redirect
    -- abierto, y un `javascript:` pegado ahí terminaría dentro de un atributo
    -- del HTML. Mismo cuidado que el `volver` del muro y el afiche de las
    -- actividades.
    boton_texto    VARCHAR(40)  NULL,
    boton_destino  VARCHAR(120) NULL,

    inicio_at      DATETIME     NOT NULL COMMENT 'UTC. Antes de esto está programada',
    fin_at         DATETIME     NOT NULL COMMENT 'UTC. Después de esto se retira sola',

    -- EL INTERRUPTOR. Separado de las fechas y no mezclado con ellas.
    --
    -- El caso real: el 2x1 de filtrados se cae a las seis de la tarde porque
    -- se acabó el café. El dueño necesita sacar el banner en ese momento, sin
    -- editar fechas ni entender estados. Apagar esto lo baja al tiro y
    -- volver a encenderlo lo repone con el plazo original intacto.
    activa         TINYINT(1)   NOT NULL DEFAULT 1,

    -- Pueden convivir varias promos cargadas, pero se MUESTRA UNA SOLA.
    -- Sin esto, el día que el dueño deje una programada y olvide la anterior,
    -- habría dos banners peleando por el mismo espacio.
    prioridad      INT          NOT NULL DEFAULT 0,

    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'UTC',
    updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP COMMENT 'UTC',
    creada_por     BIGINT       NULL COMMENT 'Qué admin la cargó',

    PRIMARY KEY (id),

    -- La consulta del público es siempre la misma: la vigente de mayor
    -- prioridad. El índice la cubre entera.
    KEY idx_promo_vigente (activa, inicio_at, fin_at, prioridad),

    -- Sin CASCADE a propósito: si se borra la cuenta del admin no queremos
    -- que desaparezcan las promos que cargó. Mismo criterio que el revisor
    -- del muro.
    CONSTRAINT fk_promo_autor FOREIGN KEY (creada_por)
        REFERENCES usuarios(id),

    -- Una promo que termina antes de empezar no se muestra nunca y nadie
    -- entiende por qué. Se rechaza en el controlador y otra vez acá, que es
    -- barato.
    CONSTRAINT chk_promo_rango CHECK (fin_at > inicio_at),
    CONSTRAINT chk_promo_nombre CHECK (CHAR_LENGTH(TRIM(nombre)) >= 2)
) ENGINE=InnoDB;
