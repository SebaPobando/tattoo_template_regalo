# ==========================================================================
# muro_model.py — el muro de deseos
#
# Qué es: la gente que tiene cuenta deja un mensaje corto sobre la cafetería,
# el admin lo aprueba, y recién ahí sale publicado en la portada.
#
# OJO: la tabla se llama `muro_mensajes`, no `deseos`. `deseos` ya existe y es
# otra cosa (la lista de deseos de productos de la carta).
#
# Tres ideas que valen para todo el archivo:
#
# 1. NADA SE PUBLICA SOLO. El estado por defecto es 'pendiente'. La consulta
#    pública filtra por 'aprobado' y no hay ningún camino que salte ese filtro.
#
# 2. EL NICKNAME SE COPIA, NO SE JOINEA. Lo que el admin aprueba es un par
#    nickname + mensaje. Si el nombre saliera de usuarios por JOIN, alguien
#    podría hacerse aprobar un mensaje amable y después cambiar su nickname
#    del perfil por un insulto, que aparecería publicado y ya aprobado.
#
#    Y el nickname lo pone LA BASE, no el formulario: `crear()` lo lee de la
#    fila del usuario dentro de la misma transacción. Antes llegaba como
#    parámetro desde el controlador, que a su vez lo sacaba del formulario:
#    cualquiera podía firmar con el nombre que se le ocurriera, incluido el
#    de otra persona. Ahora no hay forma de mandarlo.
#
# 3. EL FRENO ANTI-SPAM VA DENTRO DE UNA TRANSACCIÓN CON FOR UPDATE. Mismo
#    motivo que los cupos de las actividades: dos POST en el mismo segundo
#    leerían los dos "no tiene ninguno pendiente" y entrarían los dos.
# ==========================================================================

from flask_app import DB
from flask_app.config.mysqlconnection import connectToMySQL, transaccion

ESTADOS = ("pendiente", "aprobado", "rechazado")

# Límites. Están acá y no repartidos por el controlador para que cambiarlos
# sea tocar una línea.
LARGO_MENSAJE = 280
LARGO_NICKNAME = 45
LARGO_MOTIVO = 140
MINIMO_MENSAJE = 3

# Un pendiente a la vez: mientras el admin no revise el anterior, no se puede
# mandar otro. Es el freno más efectivo y el que menos molesta a quien escribe
# de buena fe — esa persona manda uno y se va.
PENDIENTES_MAX = 1

# Y un techo diario para que nadie llene la bandeja a punta de aprobados.
ENVIOS_DIA_MAX = 5


class YaTienePendiente(Exception):
    pass


class DemasiadosEnvios(Exception):
    pass


class CuentaBloqueada(Exception):
    pass


class SinNickname(Exception):
    pass


class Muro:

    # ------------------------------------------------------------- lectura

    @staticmethod
    def aprobados(limite=None, desde=0):
        """
        Lo que ve cualquiera. Los más nuevos primero.

        LIMIT/OFFSET van como parámetros y no interpolados en el texto de la
        consulta: son números que vienen de la querystring.
        """
        if limite is None:
            return connectToMySQL(DB).query_db("""
                SELECT id, nickname, mensaje, created_at
                FROM muro_mensajes
                WHERE estado = 'aprobado'
                ORDER BY created_at DESC, id DESC
            """)
        return connectToMySQL(DB).query_db("""
            SELECT id, nickname, mensaje, created_at
            FROM muro_mensajes
            WHERE estado = 'aprobado'
            ORDER BY created_at DESC, id DESC
            LIMIT %(limite)s OFFSET %(desde)s
        """, {"limite": int(limite), "desde": int(desde)})

    @staticmethod
    def contar_aprobados():
        filas = connectToMySQL(DB).query_db(
            "SELECT COUNT(*) AS n FROM muro_mensajes WHERE estado = 'aprobado'")
        return filas[0]["n"] if filas else 0

    @staticmethod
    def mios(usuario_id, limite=10):
        """
        Los de esta persona, en cualquier estado.

        Existe para que quien escribe no quede a ciegas: manda su deseo, ve
        «esperando aprobación» y sabe que no se perdió. Sin esto, la única
        señal es que el mensaje no aparece, que se lee igual que un error.
        """
        return connectToMySQL(DB).query_db("""
            SELECT id, nickname, mensaje, estado, created_at
            FROM muro_mensajes
            WHERE usuario_id = %(u)s
            ORDER BY created_at DESC, id DESC
            LIMIT %(limite)s
        """, {"u": usuario_id, "limite": int(limite)})

    @staticmethod
    def obtener(mensaje_id):
        filas = connectToMySQL(DB).query_db(
            "SELECT * FROM muro_mensajes WHERE id = %(id)s LIMIT 1",
            {"id": mensaje_id})
        return filas[0] if filas else None

    @staticmethod
    def listar_para_admin(estado=None):
        """
        La bandeja de moderación.

        Trae del autor lo que ayuda a decidir: si el correo está verificado y
        si la cuenta está bloqueada. Un mensaje raro de una cuenta con correo
        sin confirmar creada hace diez minutos se lee distinto que el mismo
        mensaje de alguien que va a los talleres desde marzo.

        Los pendientes salen del más ANTIGUO al más nuevo (el que lleva más
        rato esperando va arriba); el resto, al revés.
        """
        if estado and estado not in ESTADOS:
            estado = None
        orden = "ASC" if estado == "pendiente" else "DESC"
        return connectToMySQL(DB).query_db(f"""
            SELECT m.*,
                   u.email, u.estado AS estado_usuario,
                   u.email_verificado_at,
                   u.created_at AS usuario_desde,
                   r.nickname AS revisor_nickname, r.nombre AS revisor_nombre
            FROM muro_mensajes m
            JOIN usuarios u ON u.id = m.usuario_id
            LEFT JOIN usuarios r ON r.id = m.revisado_por
            WHERE (%(estado)s IS NULL OR m.estado = %(estado)s)
            ORDER BY m.created_at {orden}, m.id {orden}
        """, {"estado": estado})

    @staticmethod
    def resumen():
        """Cuántos hay en cada estado. Para el contador del panel de admin."""
        filas = connectToMySQL(DB).query_db(
            "SELECT estado, COUNT(*) AS n FROM muro_mensajes GROUP BY estado")
        conteo = {e: 0 for e in ESTADOS}
        for f in filas:
            conteo[f["estado"]] = f["n"]
        conteo["total"] = sum(conteo[e] for e in ESTADOS)
        return conteo

    # ------------------------------------------------------------ escritura

    @staticmethod
    def crear(usuario_id, mensaje):
        """
        Guarda un deseo en estado 'pendiente'. Devuelve el id.

        El nickname NO se recibe: se lee de la fila del usuario acá adentro.
        Eso es lo que hace imposible firmar con un nombre inventado.

        Todo dentro de una transacción con FOR UPDATE sobre la fila del
        usuario: sin ese bloqueo, dos envíos simultáneos (doble click, o un
        script) leen los dos «no tiene ninguno pendiente» y pasan los dos.
        Es el mismo patrón que usa Actividad.inscribir con los cupos.

        Levanta SinNickname / CuentaBloqueada / YaTienePendiente /
        DemasiadosEnvios en vez de devolver False, para que el controlador no
        pueda ignorarlo por descuido.
        """
        with transaccion(DB) as cur:
            cur.execute("""
                SELECT id, estado, nickname FROM usuarios
                WHERE id = %s AND deleted_at IS NULL FOR UPDATE
            """, (usuario_id,))
            autor = cur.fetchone()
            if not autor:
                raise ValueError("Ese usuario no existe.")

            # Acá es donde el bloqueo muerde de verdad. Una sesión que ya
            # estaba abierta sobrevive a que el admin bloquee la cuenta: la
            # cookie va firmada y no se consulta la base en cada página. Por
            # eso el estado se comprueba en el momento de actuar, y sale
            # gratis: esta fila ya se estaba leyendo con FOR UPDATE para el
            # freno anti-spam.
            if autor["estado"] == "bloqueado":
                raise CuentaBloqueada(
                    "Tu cuenta no puede escribir en el muro. "
                    "Escríbenos a hola@tunegocio.cl")

            cur.execute("""
                SELECT COUNT(*) AS n FROM muro_mensajes
                WHERE usuario_id = %s AND estado = 'pendiente'
            """, (usuario_id,))
            if cur.fetchone()["n"] >= PENDIENTES_MAX:
                raise YaTienePendiente(
                    "Ya tienes un mensaje esperando aprobación. "
                    "Cuando lo revisemos podrás mandar otro.")

            # La ventana es de 24 horas móviles, no «hoy»: si fuera por día
            # calendario, alguien podría mandar 5 a las 23:59 y 5 más a las
            # 00:01. El reloj es el de la base (UTC_TIMESTAMP), uno solo.
            cur.execute("""
                SELECT COUNT(*) AS n FROM muro_mensajes
                WHERE usuario_id = %s
                  AND created_at > UTC_TIMESTAMP() - INTERVAL 1 DAY
            """, (usuario_id,))
            if cur.fetchone()["n"] >= ENVIOS_DIA_MAX:
                raise DemasiadosEnvios(
                    "Mandaste varios mensajes hoy. Vuelve mañana y seguimos.")

            # El nickname es obligatorio al registrarse, pero las cuentas
            # creadas antes de esa regla —y los invitados que se inscribieron
            # a un taller sin crear cuenta— no tienen. A esas se les pide
            # ponerlo antes de escribir, en vez de firmarlas con su nombre
            # real sin que se enteren.
            nickname = (autor.get("nickname") or "").strip()[:LARGO_NICKNAME]
            if not nickname:
                raise SinNickname(
                    "Ponle un nombre a tu cuenta para firmar tu mensaje.")

            cur.execute("""
                INSERT INTO muro_mensajes (usuario_id, nickname, mensaje, estado)
                VALUES (%s, %s, %s, 'pendiente')
            """, (usuario_id, nickname, mensaje))
            return cur.lastrowid

    @staticmethod
    def cambiar_estado(mensaje_id, estado, revisor_id, motivo=None):
        """
        Aprobar o rechazar. Se puede ir y volver entre estados: un mensaje
        aprobado que después resulta ser un problema se rechaza y desaparece
        de la portada sin borrar la fila, que es lo que deja rastro de qué se
        publicó y quién lo aprobó.
        """
        if estado not in ESTADOS:
            raise ValueError(f"Estado desconocido: {estado}")
        return connectToMySQL(DB).query_db("""
            UPDATE muro_mensajes
            SET estado = %(estado)s,
                motivo = %(motivo)s,
                revisado_at = UTC_TIMESTAMP(),
                revisado_por = %(revisor)s
            WHERE id = %(id)s
        """, {"estado": estado, "motivo": motivo,
              "revisor": revisor_id, "id": mensaje_id})

    @staticmethod
    def eliminar(mensaje_id):
        """
        Borrado de verdad. Se usa poco: para lo que hay que sacar de encima
        (datos personales de terceros, algo que no debería quedar ni en la
        bandeja). Rechazar es lo normal.
        """
        return connectToMySQL(DB).query_db(
            "DELETE FROM muro_mensajes WHERE id = %(id)s", {"id": mensaje_id})
