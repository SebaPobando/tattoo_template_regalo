# ==========================================================================
# usuario_model.py — cuentas
#
# El email es la llave. Se guarda y se busca SIEMPRE en minúsculas: la
# colación de MySQL ya compara sin distinguir mayúsculas, pero normalizar
# en la app evita que se cuelen dos filas 'Ana@x.cl' y 'ana@x.cl' si algún
# día la base cambia de colación.
# ==========================================================================

from flask_app import DB
from flask_app.config.mysqlconnection import connectToMySQL


def normalizar_email(email):
    return (email or "").strip().lower()


class Usuario:

    CAMPOS = """id, email, email_verificado_at, nombre, apellido, nickname,
                telefono, rut, fecha_nacimiento, password_hash, rol, estado,
                created_at"""

    @staticmethod
    def por_email(email):
        """Devuelve el usuario o None. Ignora los borrados lógicamente."""
        filas = connectToMySQL(DB).query_db(
            f"SELECT {Usuario.CAMPOS} FROM usuarios "
            "WHERE email = %(email)s AND deleted_at IS NULL LIMIT 1",
            {"email": normalizar_email(email)},
        )
        return filas[0] if filas else None

    @staticmethod
    def por_id(usuario_id):
        filas = connectToMySQL(DB).query_db(
            f"SELECT {Usuario.CAMPOS} FROM usuarios "
            "WHERE id = %(id)s AND deleted_at IS NULL LIMIT 1",
            {"id": usuario_id},
        )
        return filas[0] if filas else None

    @staticmethod
    def guardar_hash(usuario_id, password_hash):
        """Usado al crear la contraseña y al rehashear en silencio."""
        return connectToMySQL(DB).query_db(
            "UPDATE usuarios SET password_hash = %(hash)s WHERE id = %(id)s",
            {"hash": password_hash, "id": usuario_id},
        )

    @staticmethod
    def marcar_email_verificado(usuario_id):
        """
        Deja constancia de que esta persona abrió el enlace que le mandamos
        a su casilla. Se escribe UTC_TIMESTAMP() y no una fecha de Python:
        el reloj que manda es el de la base, uno solo.

        Idempotente a propósito — COALESCE conserva la primera verificación.
        Abrir el enlace dos veces no debería mover la fecha, porque lo que
        importa es cuándo probó ser el dueño, no la última vez que hizo clic.
        """
        return connectToMySQL(DB).query_db(
            "UPDATE usuarios "
            "SET email_verificado_at = COALESCE(email_verificado_at, UTC_TIMESTAMP()) "
            "WHERE id = %(id)s AND deleted_at IS NULL",
            {"id": usuario_id},
        )

    @staticmethod
    def restablecer_password(usuario_id, password_hash):
        """
        Cambia la contraseña desde el enlace que llegó al correo.

        Hace tres cosas en un solo UPDATE porque las tres son consecuencia
        del mismo hecho — la persona demostró tener acceso a esa casilla:

          1. Guarda la contraseña nueva. Esto además MATA los enlaces de
             recuperación que quedaran pendientes: la huella del token es el
             hash anterior (ver config/enlaces.py).
          2. Marca el correo como verificado, si no lo estaba.
          3. Asciende un 'invitado' a 'activo'. Un invitado es alguien que
             quedó en la base al inscribirse a una actividad y nunca creó
             clave; si acaba de crear una desde su propio correo, ya es una
             cuenta. Un 'bloqueado' NO se toca: recuperar la contraseña no
             puede ser la forma de saltarse un bloqueo.
        """
        return connectToMySQL(DB).query_db(
            """UPDATE usuarios SET
                 password_hash       = %(hash)s,
                 email_verificado_at = COALESCE(email_verificado_at, UTC_TIMESTAMP()),
                 estado              = CASE WHEN estado = 'invitado'
                                            THEN 'activo' ELSE estado END
               WHERE id = %(id)s AND deleted_at IS NULL""",
            {"hash": password_hash, "id": usuario_id},
        )

    @staticmethod
    def por_rut(rut):
        """
        Para avisar de un RUT repetido antes de que reviente el UNIQUE.
        El RUT llega ya normalizado ('12345678-9') desde config/rut.py.
        """
        if not rut:
            return None
        filas = connectToMySQL(DB).query_db(
            f"SELECT {Usuario.CAMPOS} FROM usuarios "
            "WHERE rut = %(rut)s AND deleted_at IS NULL LIMIT 1",
            {"rut": rut},
        )
        return filas[0] if filas else None

    @staticmethod
    def crear(email, password_hash=None, nombre=None, apellido=None,
              rol="cliente", estado="invitado", rut=None, telefono=None,
              nickname=None):
        return connectToMySQL(DB).query_db(
            """INSERT INTO usuarios
                 (email, password_hash, nombre, apellido, nickname,
                  rol, estado, rut, telefono)
               VALUES (%(email)s, %(hash)s, %(nombre)s, %(apellido)s,
                       %(nickname)s, %(rol)s, %(estado)s, %(rut)s, %(telefono)s)""",
            {"email": normalizar_email(email), "hash": password_hash,
             "nombre": nombre, "apellido": apellido, "nickname": nickname,
             "rol": rol, "estado": estado, "rut": rut, "telefono": telefono},
        )

    @staticmethod
    def reclamar(usuario_id, password_hash, nombre=None, apellido=None,
                 rut=None, telefono=None, nickname=None):
        """
        Convierte un 'invitado' en cuenta de verdad, conservando su historial.

        El esquema lo dice desde el principio: quien se inscribe a una
        actividad sin crear cuenta queda con estado='invitado' y sin
        contraseña. Cuando después se registra con el mismo correo, hereda
        lo que ya hizo en vez de partir de cero — y sobre todo, no queda un
        segundo usuario con el mismo correo.

        COALESCE deja que los campos que llegan vacíos conserven lo que ya
        había: si el invitado tenía teléfono y ahora no lo escribe, no se
        borra.

        EL WHERE ES LA SEGURIDAD, no una optimización (auditoría 2026-09-16).
        Reclamar convierte a quien se registra en dueño de una fila que ya
        existe, con el rol que esa fila tenga. Si el filtro vive solo en el
        controlador, el día que alguien llame a este método desde otro lado
        —un importador, un script, una ruta nueva— el agujero vuelve. Acá:
        solo filas que de verdad son invitados, cliente y sin contraseña.
        Devuelve las filas afectadas: 0 significa que no correspondía.
        """
        return connectToMySQL(DB).query_db(
            """UPDATE usuarios SET
                 password_hash = %(hash)s,
                 estado        = 'activo',
                 nombre        = COALESCE(%(nombre)s, nombre),
                 apellido      = COALESCE(%(apellido)s, apellido),
                 nickname      = COALESCE(%(nickname)s, nickname),
                 rut           = COALESCE(%(rut)s, rut),
                 telefono      = COALESCE(%(telefono)s, telefono)
               WHERE id = %(id)s
                 AND password_hash IS NULL
                 AND estado = 'invitado'
                 AND rol = 'cliente'
                 AND deleted_at IS NULL""",
            {"hash": password_hash, "nombre": nombre, "apellido": apellido,
             "nickname": nickname, "rut": rut, "telefono": telefono,
             "id": usuario_id},
        )

    @staticmethod
    def completar_contacto(usuario_id, nombre=None, telefono=None):
        """
        Rellena los datos de contacto de un invitado que se vuelve a inscribir.

        Dos criterios distintos a propósito:

        - El **teléfono** se pisa con el nuevo. Es el que acaba de escribir,
          así que es el que sirve para mandarle el voucher; guardar el viejo
          sería escribirle a un número que ya no usa.
        - El **nombre** solo se pone si no había. Alguien que ya tiene su
          nombre y apellido cargados no puede perder el apellido porque en el
          formulario rápido escribió solo su nombre de pila.

        No toca contraseña, estado ni rol: esto no convierte a nadie en
        cuenta. Para eso está reclamar().
        """
        return connectToMySQL(DB).query_db(
            """UPDATE usuarios SET
                 nombre   = COALESCE(nombre, %(nombre)s),
                 telefono = COALESCE(%(telefono)s, telefono)
               WHERE id = %(id)s""",
            {"nombre": nombre, "telefono": telefono, "id": usuario_id},
        )

    @staticmethod
    def actualizar_perfil(usuario_id, nombre=None, apellido=None,
                          telefono=None, rut=None, nickname=None):
        """
        Lo que el titular puede cambiar de sí mismo.

        El nickname SÍ está acá: es con lo que firma en el muro de deseos, y
        tiene que poder cambiarlo sin pedirle permiso a nadie. Ojo con la
        consecuencia: cambiarlo NO reescribe lo que ya publicó — cada mensaje
        del muro guarda una copia del nombre con el que se aprobó, justamente
        para que nadie se haga aprobar algo amable y después se renombre.

        El correo NO está acá a propósito: cambiarlo es cambiar la llave con
        la que inicia sesión, y sin verificación por correo alguien que te
        deje la sesión abierta podría apoderarse de la cuenta poniendo su
        propio correo. Llega cuando exista el envío de correos.

        El rol tampoco: si estuviera, un POST a mano te convierte en admin.
        """
        return connectToMySQL(DB).query_db(
            """UPDATE usuarios SET
                 nombre = %(nombre)s, apellido = %(apellido)s,
                 nickname = %(nickname)s,
                 telefono = %(telefono)s, rut = %(rut)s
               WHERE id = %(id)s AND deleted_at IS NULL""",
            {"nombre": nombre, "apellido": apellido, "nickname": nickname,
             "telefono": telefono, "rut": rut, "id": usuario_id},
        )

    @staticmethod
    def para_sesion(fila):
        """
        Lo mínimo que guardamos en la cookie de sesión.

        Nunca metas el hash acá: la cookie va firmada, no cifrada, y el
        cliente puede leer su contenido. Tampoco el RUT ni el teléfono:
        si los necesitas en una vista, los lees de la base.
        """
        nombre = fila.get("nombre") or fila["email"].split("@")[0]
        apellido = fila.get("apellido") or ""
        iniciales = "".join(p[0] for p in f"{nombre} {apellido}".split()[:2]).upper()

        # 'etiqueta' es como se llama a esta persona en pantalla. El nickname
        # es opcional en la base, así que el fallback tiene que existir en
        # algún lado: va acá y no en las plantillas, porque el header lo
        # pintan tres y no quiero tres fallbacks distintos.
        nickname = (fila.get("nickname") or "").strip()
        return {
            "id": fila["id"],
            "email": fila["email"],
            "nombre": nombre,
            "apellido": apellido,
            "nickname": nickname or None,
            "etiqueta": nickname or nombre,
            "iniciales": iniciales,
            "rol": fila["rol"],
            # Va en la cookie para que el aviso de "verifica tu correo" no
            # tenga que consultar la base en cada página. Es un booleano y no
            # la fecha: la fecha exacta no le sirve a nadie en pantalla.
            "email_verificado": bool(fila.get("email_verificado_at")),
        }


    # ------------------------------------------------- administración

    # El listado se topa a propósito en vez de paginarse: con búsqueda y
    # filtros encima, quien pasa de acá es porque quiere mirar «todos», y
    # para eso la respuesta correcta es afinar la búsqueda, no cargar mil
    # filas. La vista avisa cuando se llega al tope.
    TOPE_LISTADO = 100

    @staticmethod
    def listar_para_admin(busca=None, rol=None, estado=None, limite=None):
        """
        El listado del panel. Nunca trae cuentas dadas de baja.

        `busca` mira correo, nombre, apellido, nickname y teléfono. Los
        comodines de LIKE se escapan: sin eso, alguien que escribe «%» en el
        buscador hace que todo calce, y un «_» calza cualquier carácter — no
        es un agujero de seguridad, es un buscador que miente.

        El carácter de escape es '!' y va declarado con ESCAPE en la consulta.
        Se podría usar la barra invertida, que es la que MySQL toma por
        defecto, pero entonces habría que escribirla doble dentro del SQL y
        cuádruple en Python, y basta con que el servidor arranque con
        NO_BACKSLASH_ESCAPES para que deje de funcionar en silencio. Con '!'
        no hay nada que interpretar dos veces.
        """
        patron = None
        if busca and busca.strip():
            limpio = (busca.strip()
                      .replace("!", "!!")
                      .replace("%", "!%")
                      .replace("_", "!_"))
            patron = f"%{limpio}%"

        return connectToMySQL(DB).query_db("""
            SELECT id, email, nombre, apellido, nickname, telefono,
                   rol, estado, email_verificado_at, created_at,
                   (password_hash IS NOT NULL) AS tiene_clave
            FROM usuarios
            WHERE deleted_at IS NULL
              AND (%(patron)s IS NULL
                   OR email    LIKE %(patron)s ESCAPE '!'
                   OR nickname LIKE %(patron)s ESCAPE '!'
                   OR telefono LIKE %(patron)s ESCAPE '!'
                   OR CONCAT_WS(' ', nombre, apellido) LIKE %(patron)s ESCAPE '!')
              AND (%(rol)s IS NULL OR rol = %(rol)s)
              AND (%(estado)s IS NULL OR estado = %(estado)s)
            ORDER BY created_at DESC, id DESC
            LIMIT %(limite)s
        """, {"patron": patron, "rol": rol, "estado": estado,
              "limite": int(limite or Usuario.TOPE_LISTADO)})

    @staticmethod
    def resumen():
        """Cuántas cuentas hay por estado. Para el contador del panel."""
        filas = connectToMySQL(DB).query_db("""
            SELECT estado, COUNT(*) AS n FROM usuarios
            WHERE deleted_at IS NULL GROUP BY estado
        """)
        conteo = {"invitado": 0, "activo": 0, "bloqueado": 0}
        for f in filas:
            conteo[f["estado"]] = f["n"]
        conteo["total"] = sum(conteo[e] for e in ("invitado", "activo", "bloqueado"))
        return conteo

    @staticmethod
    def bloquear(usuario_id):
        """
        Deja a esa persona afuera: el login la rechaza y recuperar contraseña
        no le manda enlace (recuperar la clave no puede ser la forma de
        saltarse un bloqueo).

        `rol <> 'admin'` va en el SQL y no solo en el controlador: es la
        salvaguarda de que nadie deje el sistema sin administradores por una
        ruta que se agregue después.

        OJO: una sesión que YA está abierta sobrevive al bloqueo. La cookie
        va firmada y no se consulta la base en cada página. Por eso las
        acciones que importan comprueban el estado en el momento de actuar
        — el muro lo hace dentro de la misma transacción que ya bloquea la
        fila del usuario. Al cerrar sesión o al caducar, no vuelve a entrar.

        Devuelve el número de filas afectadas: 0 si no existe, si ya estaba
        bloqueada o si es un admin.

        El `estado <> 'bloqueado'` del WHERE parece redundante — MySQL ya
        cuenta las filas CAMBIADAS, y volver a escribir el mismo valor no
        cambia nada — pero esa cuenta depende de con qué banderas se conectó
        el cliente (CLIENT_FOUND_ROWS devuelve las que CALZAN). Dicho en el
        WHERE, el 0 es del SQL y no de la configuración de la conexión. Es
        simétrico con desbloquear().
        """
        return connectToMySQL(DB).query_db("""
            UPDATE usuarios SET estado = 'bloqueado'
            WHERE id = %(id)s AND deleted_at IS NULL
              AND rol <> 'admin' AND estado <> 'bloqueado'
        """, {"id": usuario_id})

    @staticmethod
    def cambiar_rol_personal(usuario_id, rol):
        """
        Hace barista a un cliente, o lo devuelve a cliente. Nada más.

        Las condiciones van en el SQL, no solo en el controlador:
          - nunca toca a un admin, ni convierte a nadie en admin (el admin se
            crea con crear_admin.py, desde el servidor);
          - solo cuentas activas: un invitado no tiene contraseña con qué
            entrar, y una bloqueada primero se desbloquea.
        Devuelve las filas cambiadas: 0 si no correspondía.
        """
        if rol not in ("cliente", "barista"):
            raise ValueError(rol)
        return connectToMySQL(DB).query_db("""
            UPDATE usuarios SET rol = %(rol)s
            WHERE id = %(id)s AND deleted_at IS NULL
              AND rol IN ('cliente', 'barista') AND rol <> %(rol)s
              AND estado = 'activo'
        """, {"id": usuario_id, "rol": rol})

    @staticmethod
    def desbloquear(usuario_id):
        """
        Devuelve la cuenta al estado que tenía antes.

        No hace falta guardar cuál era, y por eso no hay columna nueva: en
        este esquema 'activo' e 'invitado' se distinguen exactamente por
        tener contraseña o no. Quien se inscribió a un taller sin crear
        cuenta vuelve a ser 'invitado' y no asciende a 'activo' de regalo.
        """
        return connectToMySQL(DB).query_db("""
            UPDATE usuarios
            SET estado = IF(password_hash IS NULL, 'invitado', 'activo')
            WHERE id = %(id)s AND deleted_at IS NULL AND estado = 'bloqueado'
        """, {"id": usuario_id})
