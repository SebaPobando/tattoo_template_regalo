# ==========================================================================
# actividad_model.py — talleres, catas y eventos
#
# Dos ideas que valen para todo el archivo:
#
# 1. LOS CUPOS SE CUENTAN, NO SE GUARDAN. No existe una columna
#    'cupos_tomados' que se sume y se reste: existe COUNT() sobre las
#    inscripciones vivas. Es el mismo criterio que el saldo del ledger — un
#    contador que se actualiza solo se desincroniza al primer error, y ahí
#    tienes una cata con 13 personas y 12 sillas.
#
# 2. INSCRIBIRSE VA EN UNA TRANSACCIÓN CON FOR UPDATE. Dos personas que
#    tocan «Inscribirme» a la vez para el último cupo leerían las dos que
#    queda uno, y las dos entrarían. El bloqueo de la fila de la actividad es
#    lo que hace que la segunda espere y vea el cupo ya tomado.
# ==========================================================================

import re
import secrets
import unicodedata

import pymysql.err

from flask_app import DB
from flask_app.config.mysqlconnection import connectToMySQL, transaccion

# Una inscripción cancelada o vencida libera el cupo; las demás lo ocupan.
# 'por_revisar' ocupa: esa persona dice que ya pagó y está esperando que el
# admin mire el formulario. Soltarle el cupo mientras espera es justo el error
# que esta lista tiene que impedir.
ESTADOS_QUE_OCUPAN = ("pendiente", "por_revisar", "pagada", "asistio", "no_asistio")

# El mismo listado, ya escrito para meterlo en un IN (...) de SQL. Estaba
# copiado a mano en tres consultas y las tres tenían que acordarse de cambiar
# juntas: agregar un estado y olvidar una es cómo se sobrevende una cata.
_OCUPAN_SQL = ", ".join(f"'{e}'" for e in ESTADOS_QUE_OCUPAN)

# Cuánto se le guarda el cupo a alguien que todavía no avisa que pagó.
HORAS_DE_RESERVA = 24

# Cómo se le dice a la persona en qué va su inscripción. Vive acá, y no en un
# controlador, porque lo leen DOS pantallas —la página de la inscripción y
# «Mis actividades» del dashboard— y dos copias se separan a la primera
# corrección de redacción. El estado crudo no sirve para mostrar: nadie
# entiende «por_revisar».
TEXTO_ESTADO = {
    "pendiente":   ("Cupo reservado",          "Falta que completes el formulario con tu comprobante."),
    "por_revisar": ("Comprobante en revisión", "Recibimos tu aviso. Te confirmamos apenas lo revisemos."),
    "pagada":      ("Voucher activo",          "Muéstralo el día del evento."),
    "asistio":     ("Voucher usado",           "Ya lo presentaste en la puerta."),
    "no_asistio":  ("No asististe",            "Escríbenos si crees que es un error."),
    "cancelada":   ("Inscripción cancelada",   "El cupo quedó libre para otra persona."),
    "vencida":     ("Reserva vencida",         "Pasaron las horas del plazo sin aviso de pago y el cupo se liberó."),
}

# Sin I, O, 0 ni 1: el código se dicta por teléfono y se lee de una pantalla
# con brillo de cafetería. Confundir un 0 con una O es el error obvio.
_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def nuevo_codigo():
    """
    'LP-4KQ7-9XTM'. 8 caracteres de 32 símbolos = 40 bits de azar: no se
    adivina a mano, y la columna es UNIQUE por si el azar se repite.

    secrets y no random: random es predecible si alguien ve suficientes
    códigos, y este código es la llave de la página de la inscripción.
    """
    bloque = lambda: "".join(secrets.choice(_ALFABETO) for _ in range(4))
    return f"LP-{bloque()}-{bloque()}"


class CupoAgotado(Exception):
    pass


class YaInscrito(Exception):
    pass


class Actividad:

    # ------------------------------------------------------------- lectura

    @staticmethod
    def _con_cupos(where, datos=None, orden="a.inicio_at"):
        """
        El SELECT base. `inscritos` sale de contar, no de una columna.
        `libres` puede quedar en negativo si alguna vez sobrevendes a mano:
        se muestra como 0 pero conviene que el número real no se esconda.
        """
        return connectToMySQL(DB).query_db(f"""
            SELECT a.*,
                   m.nombre AS marca_nombre,
                   m.slug   AS marca_slug,
                   (SELECT COUNT(*) FROM usuarios_en_actividad i
                     WHERE i.actividad_id = a.id
                       AND i.estado IN ({_OCUPAN_SQL})
                   ) AS inscritos
            FROM actividades a
            LEFT JOIN marcas m ON m.id = a.marca_id
            WHERE {where}
            ORDER BY {orden}
        """, datos)

    @staticmethod
    def agenda(limite=None):
        """
        Lo que ve el público: publicadas y que todavía no han pasado.

        Se compara con UTC_TIMESTAMP() y no con una fecha de Python para que
        el reloj que manda sea el de la base, uno solo, y no el del servidor
        de la app que puede ir corrido.
        """
        filas = Actividad._con_cupos(
            "a.estado = 'publicada' AND COALESCE(a.fin_at, a.inicio_at) >= UTC_TIMESTAMP()")
        return filas[:limite] if limite else filas

    @staticmethod
    def por_slug(slug):
        filas = Actividad._con_cupos("a.slug = %(slug)s", {"slug": slug})
        return filas[0] if filas else None

    @staticmethod
    def obtener(actividad_id):
        filas = Actividad._con_cupos("a.id = %(id)s", {"id": actividad_id})
        return filas[0] if filas else None

    @staticmethod
    def listar_para_admin():
        """Todas, incluidos borradores y pasadas. Las próximas primero."""
        return Actividad._con_cupos("1 = 1", orden="a.inicio_at DESC")

    @staticmethod
    def inscritos_en(actividad_id):
        return connectToMySQL(DB).query_db("""
            SELECT i.id, i.estado, i.monto_clp, i.created_at,
                   i.voucher_codigo, i.reserva_vence_at, i.aviso_formulario_at,
                   i.voucher_emitido_at, i.usado_at, i.nota_admin,
                   u.id AS usuario_id, u.nombre, u.apellido, u.email,
                   u.telefono, u.estado AS estado_usuario
            FROM usuarios_en_actividad i
            JOIN usuarios u ON u.id = i.usuario_id
            WHERE i.actividad_id = %(id)s
            ORDER BY i.created_at
        """, {"id": actividad_id})

    @staticmethod
    def inscripciones_de(usuario_id):
        """Para el dashboard: en qué se anotó esta persona."""
        return connectToMySQL(DB).query_db("""
            SELECT i.id, i.estado, i.monto_clp, i.voucher_codigo,
                   i.reserva_vence_at, i.usado_at,
                   a.id AS actividad_id, a.slug, a.nombre, a.inicio_at,
                   a.fin_at, a.lugar, a.imagen_url, a.precio_clp,
                   a.estado AS estado_actividad,
                   COALESCE(a.fin_at, a.inicio_at) < UTC_TIMESTAMP() AS ya_paso
            FROM usuarios_en_actividad i
            JOIN actividades a ON a.id = i.actividad_id
            WHERE i.usuario_id = %(u)s
            ORDER BY a.inicio_at DESC
        """, {"u": usuario_id})

    @staticmethod
    def inscripcion_de(actividad_id, usuario_id):
        filas = connectToMySQL(DB).query_db("""
            SELECT * FROM usuarios_en_actividad
            WHERE actividad_id = %(a)s AND usuario_id = %(u)s LIMIT 1
        """, {"a": actividad_id, "u": usuario_id})
        return filas[0] if filas else None

    # ------------------------------------------------------------ escritura

    @staticmethod
    def _slug_libre(nombre, excluir_id=None):
        base = unicodedata.normalize("NFKD", nombre or "")
        base = base.encode("ascii", "ignore").decode()
        base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()[:70] or "actividad"
        candidato, n = base, 1
        while True:
            filas = connectToMySQL(DB).query_db(
                """SELECT id FROM actividades WHERE slug = %(slug)s
                   AND (%(excluir)s IS NULL OR id <> %(excluir)s) LIMIT 1""",
                {"slug": candidato, "excluir": excluir_id})
            if not filas:
                return candidato
            n += 1
            candidato = f"{base}-{n}"

    @staticmethod
    def crear(datos):
        datos = dict(datos)
        datos["slug"] = Actividad._slug_libre(datos["nombre"])
        return connectToMySQL(DB).query_db("""
            INSERT INTO actividades
              (marca_id, slug, nombre, descripcion, inicio_at, fin_at,
               lugar, imagen_url, formulario_url, cupos, precio_clp, estado)
            VALUES (%(marca_id)s, %(slug)s, %(nombre)s, %(descripcion)s,
                    %(inicio_at)s, %(fin_at)s, %(lugar)s, %(imagen_url)s,
                    %(formulario_url)s, %(cupos)s, %(precio_clp)s, %(estado)s)
        """, datos)

    @staticmethod
    def actualizar(actividad_id, datos):
        datos = dict(datos)
        datos["id"] = actividad_id
        actual = Actividad.obtener(actividad_id)
        # El slug sigue al nombre solo si el nombre cambió: si alguien ya
        # compartió el enlace de la cata, no se lo rompemos por editar el lugar.
        if actual and actual["nombre"] != datos["nombre"]:
            datos["slug"] = Actividad._slug_libre(datos["nombre"], actividad_id)
        else:
            datos["slug"] = actual["slug"] if actual else None
        return connectToMySQL(DB).query_db("""
            UPDATE actividades SET
              marca_id = %(marca_id)s, slug = %(slug)s, nombre = %(nombre)s,
              descripcion = %(descripcion)s, inicio_at = %(inicio_at)s,
              fin_at = %(fin_at)s, lugar = %(lugar)s,
              imagen_url = %(imagen_url)s,
              formulario_url = %(formulario_url)s, cupos = %(cupos)s,
              precio_clp = %(precio_clp)s, estado = %(estado)s
            WHERE id = %(id)s
        """, datos)

    @staticmethod
    def cambiar_estado(actividad_id, estado):
        return connectToMySQL(DB).query_db(
            "UPDATE actividades SET estado = %(e)s WHERE id = %(id)s",
            {"e": estado, "id": actividad_id})

    @staticmethod
    def eliminar(actividad_id):
        """
        Borra la actividad. Devuelve True si se borró.

        Sin inscripciones se borra directo. Con inscripciones, SOLO si está
        cancelada: ahí se borran también sus inscripciones (y sus vouchers
        dejan de funcionar), todo en una transacción. Una actividad viva con
        gente inscrita no se borra: hay personas que contaban con ella, y para
        eso está primero el estado 'cancelada', que ellos ven al entrar.
        """
        with transaccion(DB) as cur:
            cur.execute("SELECT estado FROM actividades WHERE id = %s FOR UPDATE",
                        (actividad_id,))
            fila = cur.fetchone()
            if not fila:
                return False
            estado = fila["estado"] if isinstance(fila, dict) else fila[0]
            cur.execute("SELECT COUNT(*) AS n FROM usuarios_en_actividad WHERE actividad_id = %s",
                        (actividad_id,))
            c = cur.fetchone()
            n = c["n"] if isinstance(c, dict) else c[0]
            if n and estado != "cancelada":
                return False
            cur.execute("DELETE FROM usuarios_en_actividad WHERE actividad_id = %s", (actividad_id,))
            cur.execute("DELETE FROM actividades WHERE id = %s", (actividad_id,))
            return True

    # --------------------------------------------------------- inscripción

    @staticmethod
    def inscribir(actividad_id, usuario_id):
        """
        Toma un cupo. Devuelve {"id", "codigo", "estado"}.

        Todo dentro de una transacción con FOR UPDATE sobre la actividad:
        sin ese bloqueo, dos personas que tocan el botón en el mismo segundo
        para el último cupo leen las dos "queda 1" y entran las dos. El
        bloqueo hace que la segunda espere a que la primera confirme, y
        entonces ya lee "quedan 0".

        Levanta CupoAgotado o YaInscrito en vez de devolver False, para que
        el controlador no pueda ignorarlo por descuido.
        """
        with transaccion(DB) as cur:
            cur.execute("""
                SELECT id, cupos, estado, precio_clp,
                       COALESCE(fin_at, inicio_at) AS termina_at,
                       COALESCE(fin_at, inicio_at) < UTC_TIMESTAMP() AS ya_paso
                FROM actividades WHERE id = %s FOR UPDATE
            """, (actividad_id,))
            act = cur.fetchone()

            if not act or act["estado"] != "publicada":
                raise CupoAgotado("Esta actividad no está abierta a inscripciones.")
            if act["ya_paso"]:
                raise CupoAgotado("Esta actividad ya pasó.")

            cur.execute("""
                SELECT id, estado, voucher_codigo FROM usuarios_en_actividad
                WHERE actividad_id = %s AND usuario_id = %s
            """, (actividad_id, usuario_id))
            previa = cur.fetchone()
            # 'vencida' cuenta como libre igual que 'cancelada': a esa persona
            # se le soltó el cupo por el reloj, así que tiene todo el derecho
            # a tomar otro. Sin esto, vencerse una vez la dejaba fuera del
            # evento para siempre con un «ya estabas inscrito» absurdo.
            if previa and previa["estado"] not in ("cancelada", "vencida"):
                raise YaInscrito("Ya estabas inscrito en esta actividad.")

            # Antes de contar, soltar las reservas de este evento que ya se
            # vencieron. Sin cron y sin tarea de fondo: el cupo se libera
            # justo cuando alguien lo necesita, que es cuando importa. Va
            # DENTRO del FOR UPDATE, así que nadie cuenta a medio barrido.
            cur.execute("""
                UPDATE usuarios_en_actividad SET estado = 'vencida'
                 WHERE actividad_id = %s
                   AND estado = 'pendiente'
                   AND reserva_vence_at IS NOT NULL
                   AND reserva_vence_at < UTC_TIMESTAMP()
            """, (actividad_id,))

            cur.execute(f"""
                SELECT COUNT(*) AS n FROM usuarios_en_actividad
                WHERE actividad_id = %s
                  AND estado IN ({_OCUPAN_SQL})
            """, (actividad_id,))
            if cur.fetchone()["n"] >= act["cupos"]:
                raise CupoAgotado("Se acabaron los cupos.")

            # Un evento gratis no tiene pago que revisar: la inscripción
            # nace pagada y con el voucher listo. Uno con precio nace
            # reservado por HORAS_DE_RESERVA, esperando el formulario.
            gratis = act["precio_clp"] == 0
            estado = "pagada" if gratis else "pendiente"
            emitido = "UTC_TIMESTAMP()" if gratis else "NULL"
            vence = ("NULL" if gratis else
                     f"DATE_ADD(UTC_TIMESTAMP(), INTERVAL {HORAS_DE_RESERVA} HOUR)")

            # Quien se había borrado y vuelve reusa su fila: el UNIQUE
            # (actividad_id, usuario_id) impide crear una segunda. Se le
            # respeta el código que ya tenía: puede haberlo compartido o
            # tenerlo en un correo.
            if previa:
                codigo = previa.get("voucher_codigo") or Actividad._codigo_libre(cur)
                cur.execute(f"""
                    UPDATE usuarios_en_actividad
                       SET estado = %s, monto_clp = %s, voucher_codigo = %s,
                           reserva_vence_at = {vence},
                           voucher_emitido_at = {emitido},
                           aviso_formulario_at = NULL, nota_admin = NULL,
                           usado_at = NULL
                     WHERE id = %s
                """, (estado, act["precio_clp"], codigo, previa["id"]))
                return {"id": previa["id"], "codigo": codigo, "estado": estado}

            codigo = Actividad._codigo_libre(cur)
            cur.execute(f"""
                INSERT INTO usuarios_en_actividad
                  (actividad_id, usuario_id, estado, monto_clp, voucher_codigo,
                   reserva_vence_at, voucher_emitido_at)
                VALUES (%s, %s, %s, %s, %s, {vence}, {emitido})
            """, (actividad_id, usuario_id, estado, act["precio_clp"], codigo))
            return {"id": cur.lastrowid, "codigo": codigo, "estado": estado}

    @staticmethod
    def cancelar_inscripcion(actividad_id, usuario_id):
        """
        No se borra la fila: se marca cancelada. Así queda registro de que
        esa persona se había anotado y se arrepintió, que es información útil
        (y evita que el UNIQUE estorbe si vuelve a inscribirse).
        """
        return connectToMySQL(DB).query_db("""
            UPDATE usuarios_en_actividad SET estado = 'cancelada'
            WHERE actividad_id = %(a)s AND usuario_id = %(u)s
              AND estado <> 'cancelada'
        """, {"a": actividad_id, "u": usuario_id})

    @staticmethod
    def cambiar_estado_inscripcion(inscripcion_id, estado):
        """
        Lo que usa el admin desde el selector: cualquier estado a mano.

        Marcar 'asistio' además sella `usado_at`. Con eso el voucher deja de
        decir «válido» y pasa a decir «ya se usó»: si alguien muestra la misma
        captura dos veces en la puerta, se nota.
        """
        return connectToMySQL(DB).query_db("""
            UPDATE usuarios_en_actividad
               SET estado = %(e)s,
                   usado_at = IF(%(e)s = 'asistio',
                                 COALESCE(usado_at, UTC_TIMESTAMP()),
                                 usado_at)
             WHERE id = %(id)s
        """, {"e": estado, "id": inscripcion_id})

    # ------------------------------------------------ reserva y voucher

    @staticmethod
    def _codigo_libre(cur):
        """
        Un código que no esté tomado. Reintenta porque la columna es UNIQUE:
        con 40 bits de azar la colisión es rarísima, pero «rarísimo» no es
        «imposible» y un INSERT que revienta dejaría a alguien sin cupo.
        """
        for _ in range(6):
            codigo = nuevo_codigo()
            cur.execute(
                "SELECT id FROM usuarios_en_actividad WHERE voucher_codigo = %s",
                (codigo,))
            if not cur.fetchone():
                return codigo
        raise RuntimeError("No pude generar un código de voucher libre.")

    @staticmethod
    def liberar_vencidas():
        """
        Suelta los cupos cuya reserva se venció, en toda la base.

        Se llama al pasar —al mirar la agenda, la ficha o el admin— en vez de
        con una tarea programada. Un cron es una pieza más que instalar, que
        vigilar y que se olvida de correr; esto no puede quedar desfasado
        porque corre justo antes de que alguien lea los cupos.

        NO toca 'por_revisar': esa persona dice que ya pagó y está esperando
        al admin. Su cupo no lo suelta el reloj.
        """
        return connectToMySQL(DB).query_db("""
            UPDATE usuarios_en_actividad SET estado = 'vencida'
             WHERE estado = 'pendiente'
               AND reserva_vence_at IS NOT NULL
               AND reserva_vence_at < UTC_TIMESTAMP()
        """)

    @staticmethod
    def por_codigo(codigo):
        """
        La inscripción con todo lo que la página necesita: la actividad y la
        persona. El código es la llave: quien lo tiene, ve esta página.
        """
        filas = connectToMySQL(DB).query_db("""
            SELECT i.*,
                   a.slug, a.nombre AS actividad, a.descripcion, a.inicio_at,
                   a.fin_at, a.lugar, a.imagen_url, a.formulario_url,
                   a.precio_clp, a.estado AS estado_actividad,
                   u.nombre, u.apellido, u.email, u.telefono
            FROM usuarios_en_actividad i
            JOIN actividades a ON a.id = i.actividad_id
            JOIN usuarios u    ON u.id = i.usuario_id
            WHERE i.voucher_codigo = %(c)s
            LIMIT 1
        """, {"c": codigo})
        return filas[0] if filas else None

    @staticmethod
    def obtener_inscripcion(inscripcion_id):
        """La misma vista de arriba, pero por id: es la que usa el admin."""
        filas = connectToMySQL(DB).query_db("""
            SELECT i.*,
                   a.slug, a.nombre AS actividad, a.inicio_at, a.lugar,
                   a.imagen_url, a.formulario_url, a.precio_clp,
                   u.nombre, u.apellido, u.email, u.telefono
            FROM usuarios_en_actividad i
            JOIN actividades a ON a.id = i.actividad_id
            JOIN usuarios u    ON u.id = i.usuario_id
            WHERE i.id = %(id)s
            LIMIT 1
        """, {"id": inscripcion_id})
        return filas[0] if filas else None

    @staticmethod
    def codigo_de(inscripcion_id):
        """
        El código de una inscripción, creándolo si no tiene.

        Las inscripciones anteriores a esta función existen sin código. En vez
        de rellenarlas todas en la migración —y quedar con códigos emitidos
        para gente que quizá nunca vuelva— se crea el primero que haga falta.
        """
        fila = Actividad.obtener_inscripcion(inscripcion_id)
        if not fila:
            return None
        if fila.get("voucher_codigo"):
            return fila["voucher_codigo"]
        with transaccion(DB) as cur:
            codigo = Actividad._codigo_libre(cur)
            cur.execute(
                "UPDATE usuarios_en_actividad SET voucher_codigo = %s WHERE id = %s",
                (codigo, inscripcion_id))
        return codigo

    @staticmethod
    def avisar_formulario(inscripcion_id):
        """
        La persona dice que ya mandó el formulario con su comprobante.

        Es una declaración suya, no una comprobación: la app no tiene cómo
        preguntarle a Google si llegó. Lo que compra es tiempo — el cupo deja
        de vencer y pasa a la cola del admin, que es quien sí mira.

        Solo desde 'pendiente': si ya está pagada o cancelada, no hay nada
        que avisar. Devuelve True si de verdad cambió algo.
        """
        # Se mira cuántas filas cambiaron, no en qué estado quedó la fila.
        # Preguntar «¿quedó en por_revisar?» devuelve que sí también cuando ya
        # estaba así desde antes, y entonces el segundo clic —o el F5— le
        # agradece a la persona un aviso que no dio.
        cambiadas = connectToMySQL(DB).query_db("""
            UPDATE usuarios_en_actividad
               SET estado = 'por_revisar',
                   aviso_formulario_at = UTC_TIMESTAMP(),
                   reserva_vence_at = NULL
             WHERE id = %(id)s AND estado = 'pendiente'
        """, {"id": inscripcion_id})
        return bool(cambiadas)

    @staticmethod
    def confirmar_pago(inscripcion_id):
        """
        El admin vio el comprobante en el formulario: el voucher queda activo.

        `voucher_emitido_at` se escribe solo la primera vez (COALESCE), para
        que volver a confirmar no mueva la fecha.
        """
        connectToMySQL(DB).query_db("""
            UPDATE usuarios_en_actividad
               SET estado = 'pagada',
                   voucher_emitido_at = COALESCE(voucher_emitido_at, UTC_TIMESTAMP()),
                   reserva_vence_at = NULL,
                   nota_admin = NULL
             WHERE id = %(id)s
        """, {"id": inscripcion_id})
        return Actividad.obtener_inscripcion(inscripcion_id)

    @staticmethod
    def rechazar_pago(inscripcion_id, motivo=None):
        """
        No cuadra el comprobante. Vuelve a 'pendiente' con el motivo a la
        vista y el reloj de nuevo en marcha: la idea es que pueda arreglarlo,
        no echarla del evento. Para eso está cancelar, que es otra cosa.
        """
        connectToMySQL(DB).query_db(f"""
            UPDATE usuarios_en_actividad
               SET estado = 'pendiente',
                   nota_admin = %(m)s,
                   aviso_formulario_at = NULL,
                   voucher_emitido_at = NULL,
                   reserva_vence_at =
                       DATE_ADD(UTC_TIMESTAMP(), INTERVAL {HORAS_DE_RESERVA} HOUR)
             WHERE id = %(id)s
        """, {"id": inscripcion_id, "m": (motivo or None)})
        return Actividad.obtener_inscripcion(inscripcion_id)
