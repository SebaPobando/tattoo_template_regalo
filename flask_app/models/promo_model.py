# ==========================================================================
# promo_model.py — las promos que se anuncian en la portada
#
# Qué es: el admin carga una promo («Filtrados 2x1») con su plazo, y la
# landing muestra un banner con el tiempo que le queda. Cuando el plazo se
# cumple, el banner se retira solo: nadie tiene que acordarse de apagarlo.
#
# Cuatro ideas que valen para todo el archivo:
#
# 1. EL PLAZO SON DOS FECHAS, NO UNA DURACIÓN. Guardar «dura 48 horas» obliga
#    a resolver contra el momento de publicación, y a la primera edición del
#    texto nadie sabe si el plazo se reinicia. Con `inicio_at` y `fin_at`
#    absolutas no hay nada que interpretar. Los atajos del formulario
#    («24 horas», «hasta el domingo») rellenan una fecha; no se guardan.
#
# 1b. EL BANNER PUEDE VENIR DE DOS LADOS.
#    De esta tabla (un anuncio cualquiera: un taller, un horario especial) o
#    de un combo de la carta marcado «mostrar en el banner». `vigente()` los
#    une en la misma consulta y los normaliza a la misma forma.
#
#    Los combos NO se copian acá como filas: se leen desde carta_combos. Dos
#    copias del nombre y las fechas es garantizar que algún día discrepen.
#    Cuando los dos están vigentes compiten por el mismo espacio con el
#    criterio de siempre: prioridad más alta y, a igualdad, la que termina
#    antes.
#
# 2. LOS SEGUNDOS QUE QUEDAN LOS CALCULA MYSQL, NO PYTHON NI EL NAVEGADOR.
#    `vigente()` devuelve `segundos` ya restados contra UTC_TIMESTAMP(). El
#    navegador recibe un número y cuenta hacia abajo desde ahí.
#
#    Si el front contara contra la fecha de fin con su propio reloj, el plazo
#    dependería del reloj de cada visitante: quien lo tenga corrido ve otra
#    cosa, y quien lo atrase se extiende la promo solo. El mismo criterio con
#    que el catálogo se inyecta ya resuelto en el HTML.
#
# 3. SE MUESTRA UNA SOLA, aunque haya varias cargadas. Mayor prioridad
#    primero y, a igual prioridad, la que termina antes — la que corre riesgo
#    de no alcanzar a mostrarse. Dos banners compitiendo por el mismo espacio
#    es un problema que aparece el día que el dueño deja una programada y
#    olvida la anterior.
#
# 4. EL ESTADO SE DERIVA, NO SE GUARDA. Programada, activa, terminada y
#    pausada salen de comparar las fechas con el ahora, en el mismo SELECT.
#    Una columna `estado` habría que mantenerla al día con un cron, y el
#    primer día que ese cron no corra el sitio va a mostrar una promo vencida.
#    Mismo criterio que los cupos, que se cuentan en vez de guardarse.
# ==========================================================================

from flask_app import DB
from flask_app.config.mysqlconnection import connectToMySQL

# Límites. Están acá y no repartidos por el controlador para que cambiarlos
# sea tocar una línea; el formulario lee estos mismos números para su
# maxlength, igual que hace el muro.
LARGO_NOMBRE = 80
LARGO_BAJADA = 180
LARGO_BOTON = 40
LARGO_DESTINO = 120
MINIMO_NOMBRE = 2

# El estado se calcula en SQL para que la portada y el panel no puedan
# discrepar. El orden de los CASE importa: el interruptor manda sobre las
# fechas, porque apagar una promo vigente es justamente para lo que existe.
_ESTADO = """
    CASE
        WHEN p.activa = 0                   THEN 'pausada'
        WHEN UTC_TIMESTAMP() < p.inicio_at  THEN 'programada'
        WHEN UTC_TIMESTAMP() >= p.fin_at    THEN 'terminada'
        ELSE 'activa'
    END AS estado
"""


class Promo:

    # ------------------------------------------------------------ portada

    @staticmethod
    def vigente():
        """
        La promo que corresponde mostrar ahora mismo, o None.

        `segundos` es lo que el front necesita: cuánto falta para el término,
        medido por el reloj del servidor. Nunca sale negativo — el WHERE ya
        descartó las terminadas — pero el front igual se defiende de un cero.
        """
        consulta = """
            SELECT p.id, CONCAT('promo-', p.id) AS clave,
                   p.nombre, p.bajada, p.boton_texto, p.boton_destino,
                   p.fin_at, p.prioridad,
                   TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), p.fin_at) AS segundos
            FROM promos p
            WHERE p.activa = 1
              AND p.inicio_at <= UTC_TIMESTAMP()
              AND p.fin_at    >  UTC_TIMESTAMP()

            UNION ALL

            /*
               Los combos de la carta marcados «mostrar en el banner».
               Se LEEN desde carta_combos; NO se copia una fila a `promos`.
               Copiar nombre y fechas a otra tabla es garantizar que algún
               día discrepen: acá la única fuente es el combo.

               La bajada y el botón se arman al vuelo porque un combo no
               tiene esos campos: lo que tiene es precio, y eso es justo lo
               que se quiere anunciar. El botón apunta a la carta, que es
               donde está la promo completa.

               Un combo sin productos adentro queda fuera, igual que en la
               carta: anunciar algo que no se sabe qué trae es peor que no
               anunciarlo.

               `clave` lleva el origen adelante ('promo-3' / 'combo-3') y no
               es cosmética: el front guarda en localStorage cuál promo
               cerró la persona, POR ID. Sin el prefijo, un banner con id 3
               y un combo con id 3 serían el mismo para el navegador, y
               cerrar uno silenciaría el otro sin que nadie entienda por
               qué.
            */
            SELECT c.id, CONCAT('combo-', c.id) AS clave,
                   c.nombre,
                   CONCAT_WS(' · ', c.descripcion,
                             CONCAT('$', FORMAT(c.precio_clp, 0, 'de_DE'))) AS bajada,
                   'Ver en la carta' AS boton_texto,
                   '#carta'          AS boton_destino,
                   c.fin_at, c.prioridad,
                   TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), c.fin_at) AS segundos
            FROM carta_combos c
            WHERE c.mostrar_en_banner = 1
              AND c.disponible = 1
              AND c.inicio_at <= UTC_TIMESTAMP()
              -- fin_at NULL = sin término. `segundos` sale NULL y la
              -- plantilla, al no tener plazo, no pinta el contador (ver
              -- _promo.html): el banner se queda hasta que lo apaguen.
              AND (c.fin_at IS NULL OR c.fin_at > UTC_TIMESTAMP())
              AND EXISTS (SELECT 1 FROM carta_combo_items i
                          WHERE i.combo_id = c.id)

            /* A igualdad de prioridad gana la que termina antes, y las
               que no terminan nunca van al final: una promo con plazo es
               más urgente que una permanente. `fin_at IS NULL` ordena los
               NULL después sin depender de cómo los trate el motor. */
            ORDER BY prioridad DESC, fin_at IS NULL, fin_at ASC
            LIMIT 1;
        """
        filas = connectToMySQL(DB).query_db(consulta)
        return filas[0] if filas else None

    # -------------------------------------------------------------- panel

    @staticmethod
    def todas():
        """
        Todo lo cargado, para el panel. Las que piden atención primero: lo
        vigente y lo que está por empezar arriba, lo terminado al final.
        """
        consulta = f"""
            SELECT p.*, {_ESTADO}
            FROM promos p
            ORDER BY
                CASE
                    WHEN p.activa = 1 AND p.inicio_at <= UTC_TIMESTAMP()
                                      AND p.fin_at > UTC_TIMESTAMP() THEN 0
                    WHEN p.inicio_at > UTC_TIMESTAMP()               THEN 1
                    WHEN p.activa = 0                                THEN 2
                    ELSE 3
                END,
                p.prioridad DESC, p.fin_at DESC;
        """
        return connectToMySQL(DB).query_db(consulta)

    @staticmethod
    def una(promo_id):
        filas = connectToMySQL(DB).query_db(
            f"SELECT p.*, {_ESTADO} FROM promos p WHERE p.id = %(id)s;",
            {"id": promo_id})
        return filas[0] if filas else None

    @staticmethod
    def resumen():
        """Para la pastilla del panel: cuántas vigentes y cuántas cargadas."""
        filas = connectToMySQL(DB).query_db("""
            SELECT
                COUNT(*) AS total,
                SUM(activa = 1 AND inicio_at <= UTC_TIMESTAMP()
                                AND fin_at    >  UTC_TIMESTAMP()) AS vigentes
            FROM promos;
        """)
        fila = filas[0] if filas else {}
        return {"total": int(fila.get("total") or 0),
                "vigentes": int(fila.get("vigentes") or 0)}

    # ------------------------------------------------------------ escribir

    @staticmethod
    def crear(datos):
        """
        Devuelve el id. Las fechas llegan ya en UTC desde el controlador
        (config/tiempo.local_a_utc); acá no se interpreta ninguna hora.
        """
        return connectToMySQL(DB).query_db("""
            INSERT INTO promos
                (nombre, bajada, boton_texto, boton_destino,
                 inicio_at, fin_at, activa, prioridad, creada_por)
            VALUES
                (%(nombre)s, %(bajada)s, %(boton_texto)s, %(boton_destino)s,
                 %(inicio_at)s, %(fin_at)s, %(activa)s, %(prioridad)s,
                 %(creada_por)s);
        """, datos)

    @staticmethod
    def actualizar(promo_id, datos):
        datos = dict(datos, id=promo_id)
        return connectToMySQL(DB).query_db("""
            UPDATE promos SET
                nombre        = %(nombre)s,
                bajada        = %(bajada)s,
                boton_texto   = %(boton_texto)s,
                boton_destino = %(boton_destino)s,
                inicio_at     = %(inicio_at)s,
                fin_at        = %(fin_at)s,
                prioridad     = %(prioridad)s
            WHERE id = %(id)s;
        """, datos)

    @staticmethod
    def interruptor(promo_id, encendida):
        """
        Bajar o reponer la promo sin tocar el plazo.

        El `AND activa <> %(activa)s` no es redundante aunque lo parezca:
        MySQL cuenta filas CAMBIADAS, pero eso depende de las banderas de la
        conexión (CLIENT_FOUND_ROWS cuenta las que calzan). Dicho en el SQL,
        el 0 no depende de la configuración. Misma trampa que en bloquear()
        de usuarios.
        """
        valor = 1 if encendida else 0
        return connectToMySQL(DB).query_db("""
            UPDATE promos SET activa = %(activa)s
            WHERE id = %(id)s AND activa <> %(activa)s;
        """, {"id": promo_id, "activa": valor})

    @staticmethod
    def eliminar(promo_id):
        """
        Acá sí se borra de verdad, a diferencia de un mensaje del muro o de
        una inscripción: una promo no tiene nada colgando, no es registro de
        nada que haya que conservar, y dejar basura acumulada en el panel
        haría más difícil encontrar la que está corriendo.
        """
        return connectToMySQL(DB).query_db(
            "DELETE FROM promos WHERE id = %(id)s;", {"id": promo_id})
