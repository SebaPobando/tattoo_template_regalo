-- =============================================================================
-- Plantilla Tienda de Tatuaje — Voucher de acceso al evento
-- Migración incremental: se corre SOBRE la base que ya existe.
--
-- Qué agrega:
--   actividades.formulario_url      el Google Form de ese evento
--   usuarios_en_actividad           el estado del pago, la reserva y el voucher
--
-- No borra nada y se puede correr dos veces sin romper nada.
--
-- Cómo cargarlo en Windows (PowerShell no soporta `<` para redirigir entrada):
--     mysql -u root -p --default-character-set=utf8mb4 -e "source schema/evento_voucher.sql"
-- =============================================================================

SET NAMES utf8mb4;

-- MySQL 8 NO tiene `ADD COLUMN IF NOT EXISTS` (eso es de MariaDB), así que la
-- idempotencia se hace a mano: se mira information_schema y, si la columna ya
-- está, se ejecuta un DO 0 que no hace nada.

-- --------------------------------------------------------------------------
-- 1. El enlace del formulario, por actividad
--
-- Es por actividad y no una constante de la app porque el dueño arma un
-- formulario nuevo para cada taller, con su fecha y su precio adentro.
-- --------------------------------------------------------------------------
SET @existe := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name   = 'actividades'
      AND column_name  = 'formulario_url'
);
SET @sql := IF(@existe = 0,
    'ALTER TABLE actividades
       ADD COLUMN formulario_url VARCHAR(500) NULL
       COMMENT ''Google Form donde se sube el comprobante de ese evento''
       AFTER imagen_url',
    'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- --------------------------------------------------------------------------
-- 2. Dos estados nuevos en la inscripción
--
--   por_revisar  la persona dice que ya mandó el formulario con su
--                comprobante. Ocupa cupo y NO vence: está esperando al
--                admin, no al reloj.
--   vencida      se le acabaron las 24 h sin avisar. Libera el cupo.
--
-- 'vencida' existe aparte de 'cancelada' porque no son lo mismo: una la
-- decidió la persona y la otra el reloj, y a cada una hay que decirle algo
-- distinto en pantalla.
--
-- MODIFY COLUMN reescribe el ENUM entero: hay que nombrar TODOS los valores,
-- incluidos los que ya estaban, o los que falten se pierden.
-- --------------------------------------------------------------------------
SET @existe := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name   = 'usuarios_en_actividad'
      AND column_name  = 'estado'
      AND column_type LIKE '%por_revisar%'
);
SET @sql := IF(@existe = 0,
    'ALTER TABLE usuarios_en_actividad
       MODIFY COLUMN estado
         ENUM(''pendiente'',''por_revisar'',''pagada'',''cancelada'',
              ''vencida'',''asistio'',''no_asistio'')
         NOT NULL DEFAULT ''pendiente''',
    'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- --------------------------------------------------------------------------
-- 3. La reserva, el aviso y el voucher
--
-- voucher_codigo se genera al inscribirse y NO al pagar: es también la
-- dirección privada donde la persona ve en qué va su inscripción. Un invitado
-- sin cuenta no tiene otra forma de volver.
-- --------------------------------------------------------------------------
SET @existe := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name   = 'usuarios_en_actividad'
      AND column_name  = 'voucher_codigo'
);
SET @sql := IF(@existe = 0,
    'ALTER TABLE usuarios_en_actividad
       ADD COLUMN voucher_codigo VARCHAR(20) NULL
           COMMENT ''Código del voucher. También es la URL privada de la inscripción''
           AFTER pago_ref,
       ADD COLUMN reserva_vence_at DATETIME NULL
           COMMENT ''UTC. Hasta cuándo se guarda el cupo sin aviso de pago'',
       ADD COLUMN aviso_formulario_at DATETIME NULL
           COMMENT ''UTC. Cuándo dijo que envió el formulario'',
       ADD COLUMN voucher_emitido_at DATETIME NULL
           COMMENT ''UTC. Cuándo el admin confirmó el pago'',
       ADD COLUMN usado_at DATETIME NULL
           COMMENT ''UTC. Cuándo se presentó en la puerta'',
       ADD COLUMN nota_admin VARCHAR(255) NULL
           COMMENT ''Motivo del rechazo o nota interna'',
       ADD UNIQUE KEY uq_inscripcion_voucher (voucher_codigo)',
    'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- --------------------------------------------------------------------------
-- 4. Índice para el barrido de reservas vencidas
--
-- La app libera los cupos vencidos al pasar, sin cron: cada vez que alguien
-- mira la agenda o se inscribe corre un UPDATE con este WHERE. Sin índice ese
-- barrido lee la tabla entera.
-- --------------------------------------------------------------------------
SET @existe := (
    SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name   = 'usuarios_en_actividad'
      AND index_name   = 'idx_inscripciones_vencimiento'
);
SET @sql := IF(@existe = 0,
    'CREATE INDEX idx_inscripciones_vencimiento
       ON usuarios_en_actividad (estado, reserva_vence_at)',
    'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- --------------------------------------------------------------------------
-- 5. Las inscripciones que ya existían
--
-- Las que estaban 'pendiente' antes de esta migración no tienen código ni
-- vencimiento. El código se lo pone la app cuando haga falta; el vencimiento
-- se deja NULL a propósito: NULL significa «no vence», y no corresponde
-- soltarle el cupo a alguien que se inscribió bajo otras reglas.
-- --------------------------------------------------------------------------
