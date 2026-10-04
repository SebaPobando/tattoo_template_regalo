# ==========================================================================
# main_controller.py — rutas del área de cuenta
#
# ESTADO: el esqueleto renderiza y navega. La lógica real llega por fases:
#   Fase 2 -> login, registro, recuperar contraseña, verificar correo  [HECHO]
#   Fase 3 -> saldo y movimientos reales desde lp_movimientos
#   Fase 3 -> recarga con MercadoPago
#   Fase 4 -> credencial con código de canje
#   Fase 7 -> suscripción
#
# Los datos de demostración están marcados con DEMO y viven en un solo lugar,
# para que borrarlos sea trivial cuando llegue la fase que corresponde.
# ==========================================================================

import time
from functools import wraps

from flask import (Response, abort, jsonify, redirect, render_template, request,
                   session, url_for, flash)

from flask_app import app, SITIO_PUBLICO
from flask_app.config import correo, csrf, enlaces, tiempo
from flask_app.config import rut as rut_chileno
from flask_app.config.seguridad import MAX_BYTES, necesita_rehash, hashear, verificar
from flask_app.models.actividad_model import Actividad, TEXTO_ESTADO
from flask_app.models.carta_model import Carta
from flask_app.config.negocio import NEGOCIO
from flask_app.models.usuario_model import Usuario, normalizar_email

# --------------------------------------------------------------- utilidades

CLP_POR_PUNTO = 10  # 1 LP = $10 CLP. La conversión vive solo acá.
MINIMO_CLAVE = 10   # OWASP pide 8; con 10 no cuesta más y aguanta bastante más


def miles(n):
    """3500 -> '3.500' (formato chileno)."""
    return f"{int(n):,}".replace(",", ".")


app.template_filter("miles")(miles)


# --- El nickname --------------------------------------------------------
# Es con lo que se firma en el muro de deseos, y por eso es obligatorio al
# registrarse: si no existiera, el muro terminaría firmando con el nombre
# real de la persona, que es justo lo que un apodo viene a evitar.
#
# NO se exige único a propósito. Dos «Anita» en el muro no le hacen daño a
# nadie, la bandeja de moderación muestra el correo de cada una, y exigirlo
# significa rechazar un registro por un motivo que se siente arbitrario
# («ese nombre ya está tomado») justo en el peor momento.

LARGO_NICKNAME = 45
MINIMO_NICKNAME = 2


def _nickname_del_formulario(valor):
    """
    Devuelve (nickname, error). Espacios de sobra fuera y en una sola línea,
    igual que los mensajes del muro: lo que se escriba acá va a aparecer
    publicado en la portada.
    """
    limpio = " ".join((valor or "").split())[:LARGO_NICKNAME]
    if len(limpio) < MINIMO_NICKNAME:
        return None, ("Elige un nombre para mostrar de al menos "
                      f"{MINIMO_NICKNAME} caracteres.")
    return limpio, None


def _sesion_vigente():
    """
    Relee de la base la cuenta de quien tiene la sesión abierta y devuelve la
    fila, o None si esa sesión ya no vale.

    POR QUÉ NO BASTA LA COOKIE (auditoría 2026-09-16). La cookie guarda el rol
    y el nombre tal como estaban al iniciar sesión, y está firmada, así que no
    se puede falsificar. Pero se queda vieja: bloquear a alguien desde
    /admin/usuarios no lo echaba del sitio, y quitarle el rol a un admin lo
    dejaba entrando al panel hasta que se le ocurriera cerrar sesión. Un botón
    que dice «bloquear» tiene que bloquear ahora.

    Cuesta una consulta por página protegida, por id y con índice. Si algún
    día eso pesa, el paso siguiente es revalidar cada N segundos guardando la
    marca de tiempo en la sesión — no volver a confiar en la cookie.

    Si la base no responde, se deja pasar con lo que dice la cookie: una
    caída de MySQL no puede cerrarle la sesión a todo el mundo, y el riesgo
    de mostrarle su propio panel unos minutos a alguien recién bloqueado es
    menor que el de dejar el sitio inservible.
    """
    guardado = session.get("usuario")
    if not guardado:
        return None
    try:
        fila = Usuario.por_id(guardado["id"])
    except Exception as e:
        app.logger.error("No pude revalidar la sesión: %s", e)
        return guardado

    if not fila or fila["estado"] == "bloqueado":
        session.clear()
        return None

    # La cookie se refresca con lo que dice la base: así el nombre, el rol y
    # el nickname que ven las plantillas están al día sin cerrar sesión.
    session["usuario"] = Usuario.para_sesion(fila)
    return session["usuario"]


def requiere_sesion(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if not _sesion_vigente():
            flash("Inicia sesión para ver esa página.", "error")
            return redirect(url_for("login"))
        return vista(*args, **kwargs)
    return envoltura


def requiere_admin(vista):
    """
    Para las pantallas de administración.

    Responde 404 y no 403 a propósito: a quien no es admin no le confirmamos
    que la ruta existe.
    """
    @wraps(vista)
    def envoltura(*args, **kwargs):
        usuario = _sesion_vigente()
        if not usuario:
            flash("Inicia sesión para ver esa página.", "error")
            return redirect(url_for("login"))
        if usuario.get("rol") != "admin":
            abort(404)
        return vista(*args, **kwargs)
    return envoltura


# Quienes trabajan en el local. El barista entra a lo que se usa en la barra
# (vales, ruleta) y a nada más: ni precios, ni ventas, ni cuentas.
PERSONAL = ("admin", "barista")


def es_personal(usuario):
    return bool(usuario) and usuario.get("rol") in PERSONAL


def requiere_personal(vista):
    """
    Como requiere_admin, pero también deja pasar al barista. Para las
    pantallas de la barra. Con el mismo 404 para el resto, y revalidando el
    rol contra la base en cada página: quitarle el rol a un barista surte
    efecto al tiro, no cuando cierre sesión (ver _sesion_vigente).
    """
    @wraps(vista)
    def envoltura(*args, **kwargs):
        usuario = _sesion_vigente()
        if not usuario:
            flash("Inicia sesión para ver esa página.", "error")
            return redirect(url_for("login"))
        if not es_personal(usuario):
            abort(404)
        return vista(*args, **kwargs)
    return envoltura


# --- Correos de cuenta ------------------------------------------------------
# Los dos correos que manda esta app. El texto vive acá y no en plantillas
# porque son cuatro líneas cada uno; si crecen o se les pone diseño, se pasan
# a templates/correo/*.html y se renderizan con render_template.

def _url_absoluta(endpoint, **kwargs):
    """
    Un enlace dentro de un correo NO puede ser relativo: se abre desde Gmail,
    no desde el sitio. _external=True lo hace absoluto usando el host de la
    petición actual.
    """
    return url_for(endpoint, _external=True, **kwargs)


def enviar_verificacion(fila):
    """
    Manda (o deja en el buzón) el enlace para verificar el correo.

    Devuelve True/False, pero quien llama casi siempre debería ignorarlo: que
    el correo no salga no puede romper el registro. Lo que sí hace es quedar
    en el log.
    """
    token = enlaces.token_verificacion(fila["id"], fila["email"])
    enlace = _url_absoluta("verificar_email", token=token)
    nombre = fila.get("nombre") or "hola"
    texto = (
        f"{nombre}:\n\n"
        f"Confirma tu correo para terminar de activar tu cuenta en {NEGOCIO['nombre']}.\n\n"
        f"{enlace}\n\n"
        f"El enlace vence en {enlaces.HORAS_VERIFICACION} horas.\n"
        "Si no fuiste tú, puedes ignorar este mensaje.\n"
    )
    return correo.enviar(fila["email"], f"Confirma tu correo · {NEGOCIO['nombre']}",
                         texto, logger=app.logger)


def enviar_reset(fila):
    """El enlace para crear una contraseña nueva."""
    token = enlaces.token_reset(fila["id"], fila["password_hash"])
    enlace = _url_absoluta("restablecer_password", token=token)
    nombre = fila.get("nombre") or "hola"
    texto = (
        f"{nombre}:\n\n"
        f"Pediste recuperar tu contraseña de {NEGOCIO['nombre']}. "
        "Abre este enlace para crear una nueva:\n\n"
        f"{enlace}\n\n"
        f"Vence en {enlaces.MINUTOS_RESET} minutos y sirve una sola vez.\n"
        "Si no lo pediste tú, no hagas nada: tu contraseña sigue igual.\n"
    )
    return correo.enviar(fila["email"], f"Recupera tu contraseña · {NEGOCIO['nombre']}",
                         texto, logger=app.logger)


def enlace_invitacion(fila):
    """El enlace para que alguien del personal cree su contraseña."""
    token = enlaces.token_invitacion(fila["id"], fila["password_hash"])
    return _url_absoluta("bienvenida_personal", token=token)


def enviar_invitacion(fila, enlace):
    """Además del enlace que el admin le pasa a mano, va por correo."""
    nombre = fila.get("nombre") or "hola"
    texto = (
        f"{nombre}:\n\n"
        f"Te crearon una cuenta de vendedor(a) en {NEGOCIO['nombre']}. Abre este "
        "enlace para elegir tu contraseña:\n\n"
        f"{enlace}\n\n"
        f"Vence en {enlaces.HORAS_INVITACION} horas y sirve una sola vez.\n"
    )
    return correo.enviar(fila["email"], f"Tu cuenta del equipo · {NEGOCIO['nombre']}",
                         texto, logger=app.logger)


# --- Freno a los intentos fallidos -----------------------------------------
# Contador en memoria: simple, sin dependencias, suficiente para un servidor.
# Limitaciones que conviene tener presentes: se borra al reiniciar Flask y no
# se comparte entre procesos. Cuando haya más de un worker, esto pasa a
# Flask-Limiter con Redis (está en la Fase 2 del roadmap).

INTENTOS_MAX = 5
BLOQUEO_SEGUNDOS = 300
_intentos = {}


def _clave_intentos():
    correo = normalizar_email(request.form.get("email", ""))
    return f"{request.remote_addr}|{correo}"


def _bloqueado():
    registro = _intentos.get(_clave_intentos())
    if not registro:
        return 0
    fallos, hasta = registro
    if fallos < INTENTOS_MAX:
        return 0
    restante = int(hasta - time.time())
    return restante if restante > 0 else 0


def _sumar_fallo():
    clave = _clave_intentos()
    fallos = _intentos.get(clave, (0, 0))[0] + 1
    _intentos[clave] = (fallos, time.time() + BLOQUEO_SEGUNDOS)


def _limpiar_fallos():
    _intentos.pop(_clave_intentos(), None)


# --- Freno a los registros ---------------------------------------------------
# El de arriba se lleva por correo, y en el registro el correo es siempre
# distinto: no frena nada. Este cuenta por IP a secas.

REGISTROS_MAX = 5
REGISTRO_VENTANA = 3600
_registros = {}


def _bloqueado_registro():
    fecha_limite = time.time() - REGISTRO_VENTANA
    hechos = [t for t in _registros.get(request.remote_addr, []) if t > fecha_limite]
    _registros[request.remote_addr] = hechos
    if len(hechos) < REGISTROS_MAX:
        return 0
    return int(hechos[0] + REGISTRO_VENTANA - time.time())


def _sumar_registro():
    _registros.setdefault(request.remote_addr, []).append(time.time())


# ---------------------------------------------------- saldo (sin ledger aún)
# La billetera está postergada a propósito. Mientras no exista lp_movimientos,
# el saldo de todo el mundo es CERO — y eso es lo que se muestra.
#
# Antes acá había un saldo de demostración de 4.280 puntos con movimientos
# inventados. Mientras el registro era una maqueta daba lo mismo, porque el
# único que lo veía era quien desarrollaba. Con el registro real, cualquiera
# que crea su cuenta veía "Tu saldo: 4.280 · equivalente a $42.800" a los diez
# segundos de existir. Eso no es un dato de prueba, es una promesa falsa a un
# cliente, y llega al mesón.

def _saldo_vacio():
    """
    Cuando exista el ledger, esto se reemplaza por la consulta a lp_saldos.
    La forma del diccionario se mantiene para que la plantilla no cambie.
    """
    return {
        "prepago": 0, "prepago_fmt": "0",
        "promo": 0, "promo_fmt": "0",
        "total": 0, "total_fmt": "0",
        "clp_fmt": "$0",
    }


# --------------------------------------------------------------- rutas

@app.route("/")
def home():
    """
    La landing. Hoy la sirve esta misma app, así que todo vive en un solo
    origen (localhost:5000) y no hay que salir a producción para navegar.

    Cuando la landing vuelva a GitHub Pages, esto pasa a ser:
        return redirect(SITIO_PUBLICO)
    y se define SITIO_PUBLICO en el .env.

    La agenda se pinta acá para que la sección exista en el primer render
    (y en el HTML que ve Google). El JavaScript la refresca después contra
    /api/v1/agenda, porque los cupos cambian solos. Si MySQL no responde la
    landing igual se sirve: una landing sin la sección de talleres es mucho
    mejor que ninguna landing.
    """
    try:
        from flask_app.controllers.actividad_controller import _publica
        from flask_app.models.actividad_model import Actividad
        agenda = [_publica(a) for a in Actividad.agenda(limite=3)]
    except Exception as e:
        app.logger.error("No se pudo leer la agenda para la landing: %s", e)
        agenda = []

    # El muro de deseos, con el mismo trato que la agenda: se pinta acá para
    # que exista en el primer render, y muro.js lo refresca contra
    # /api/v1/muro. Refrescarlo importa porque está moderado: un mensaje que
    # se rechaza tiene que salir de la portada sin esperar un despliegue.
    #
    # El import del límite va FUERA del try, y no es un detalle de estilo: la
    # plantilla lo necesita SIEMPRE, también cuando la consulta falla. Si
    # viviera dentro, una caída de MySQL dejaría la variable sin definir y la
    # portada se caería con un NameError — justo lo que este try existe para
    # evitar.
    from flask_app.controllers.muro_controller import EN_LA_LANDING
    try:
        from flask_app.controllers.muro_controller import _publica as _publica_muro
        from flask_app.models.muro_model import Muro
        muro = [_publica_muro(m) for m in Muro.aprobados(limite=EN_LA_LANDING)]
    except Exception as e:
        app.logger.error("No se pudo leer el muro para la landing: %s", e)
        muro = []

    # Los largos bajan del modelo al maxlength de los campos y de ahí los lee
    # muro.js para el contador: el número vive en un solo lugar.
    # El catálogo de la tienda sale de Shopify. Si no contesta, esto viene
    # None y la plantilla pinta las tarjetas escritas a mano que quedaron
    # como respaldo. Nunca lanza.
    from flask_app.controllers.tienda_controller import catalogo_para_plantilla
    tienda = catalogo_para_plantilla()

    # La promo del banner. Viene resuelta desde el servidor y no por fetch:
    # con un fetch la portada se pintaria primero sin banner y el banner
    # caeria encima medio segundo despues, empujando lo que la persona ya
    # empezo a leer. `tiempo` va porque el banner escribe el plazo en
    # palabras para quien usa lector de pantalla. Nunca lanza.
    from flask_app.config import tiempo
    from flask_app.controllers.promo_controller import promo_para_plantilla
    promo = promo_para_plantilla()

    from flask_app.models.muro_model import LARGO_MENSAJE, LARGO_NICKNAME
    from flask_app.models.destacado_model import NOMBRE_PESTANA
    return render_template("landing.html", agenda=agenda, muro=muro,
                           tienda=tienda,
                           nombre_especiales=NOMBRE_PESTANA,
                           promo=promo,
                           tiempo=tiempo,
                           muro_limite=EN_LA_LANDING,
                           largo_mensaje=LARGO_MENSAJE,
                           largo_nickname=LARGO_NICKNAME)


@app.route("/producto")
def producto():
    """
    Ficha de producto. El id llega por querystring (?id=brasil) porque así
    venía del sitio estático; el checkout sigue ocurriendo en Shopify.

    NO lee de la tabla `productos`, y es a propósito. Acá había un TODO que
    decía lo contrario, de antes de que se fijara la regla: si se sirve en
    taza o plato va en MySQL (esa es la carta del local); si se despacha en
    caja es de Shopify. Esta ficha es café en grano, o sea Shopify, y su
    catálogo vive en static/js/tienda-productos.js, que es la única fuente
    de verdad de nombres, precios y IDs de variante.

    Meterlo también en MySQL sería duplicar stock y precios en dos sistemas
    que no se hablan, y el que cobra es Shopify.

    El catálogo se inyecta en el HTML y no se pide por fetch: así la ficha se
    pinta de una y no muestra primero el precio del respaldo para corregirlo
    medio segundo después.
    """
    from flask_app.controllers.tienda_controller import catalogo_para_plantilla
    return render_template("producto.html",
                           producto_id=request.args.get("id"),
                           tienda=catalogo_para_plantilla())


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method != "POST":
        return render_template("login.html")

    # El token se valida ANTES del freno por intentos: un POST forjado no
    # tiene por qué gastarte los 5 intentos y dejarte 5 minutos afuera de
    # tu propia cuenta.
    #
    # Por qué el login necesita token si no hay sesión que secuestrar: existe
    # el login CSRF. Un tercero te hace entrar en SU cuenta sin que te des
    # cuenta, y lo que hagas después —escribir en el muro, más adelante
    # recargar puntos— queda en la cuenta de esa persona. La cookie ya va con
    # SameSite=Lax, que bloquea el POST cruzado clásico; esto es la segunda
    # capa, y cuesta una línea.
    if not csrf.valido(request.form.get("csrf")):
        abort(400, "Token de seguridad inválido. Recarga la página.")

    espera = _bloqueado()
    if espera:
        flash(f"Demasiados intentos. Prueba de nuevo en {espera // 60 + 1} minutos.", "error")
        return render_template("login.html"), 429

    email = normalizar_email(request.form.get("email"))
    clave = request.form.get("password", "")

    fila = Usuario.por_email(email)

    # verificar() gasta el mismo tiempo aunque el usuario no exista, para no
    # delatar qué correos están registrados.
    if not verificar(clave, fila["password_hash"] if fila else None):
        _sumar_fallo()
        # Mensaje único a propósito: no decimos si falló el correo o la clave.
        flash("Correo o contraseña incorrectos.", "error")
        return render_template("login.html"), 401

    if fila["estado"] == "bloqueado":
        _sumar_fallo()
        flash(f"Esta cuenta está bloqueada. Escríbenos a {NEGOCIO['correo']}", "error")
        return render_template("login.html"), 403

    # Si el hash quedó viejo (otro algoritmo o menos cost), lo actualizamos
    # ahora que tenemos la contraseña en claro. La persona no se entera.
    if necesita_rehash(fila["password_hash"]):
        try:
            Usuario.guardar_hash(fila["id"], hashear(clave))
            app.logger.info("Hash actualizado para el usuario %s", fila["id"])
        except Exception as e:
            app.logger.warning("No se pudo rehashear: %s", e)

    _limpiar_fallos()
    # session.clear() antes de escribir: rota el identificador de sesión y
    # evita la fijación de sesión (que alguien te deje una cookie preparada).
    session.clear()
    session["usuario"] = Usuario.para_sesion(fila)
    # «Recordarme»: 30 días renovables (ver flask_app/__init__.py). Antes el
    # checkbox era solo dibujo —no tenía name y nadie lo leía— y la sesión
    # moría siempre al cerrar el navegador.
    session.permanent = request.form.get("recordarme") == "1"

    destino = request.args.get("next")
    if destino and destino.startswith("/") and not destino.startswith("//"):
        return redirect(destino)     # solo rutas internas: evita redirect abierto
    return redirect(url_for("dashboard"))


def _partir_nombre(completo):
    """
    El formulario pide «Nombre completo» y la tabla tiene nombre y apellido.
    La primera palabra es el nombre y el resto el apellido: 'Juan Pablo Soto'
    queda como nombre='Juan', apellido='Pablo Soto'. No es perfecto —hay
    nombres compuestos— pero es lo que se puede deducir de un solo campo, y
    en el perfil se editan por separado.
    """
    partes = (completo or "").strip().split()
    if not partes:
        return None, None
    return partes[0][:45], (" ".join(partes[1:])[:45] or None)


def _clave_valida(clave, confirmacion):
    """Devuelve el mensaje de error, o None si está bien."""
    if clave != confirmacion:
        return "Las contraseñas no coinciden."
    if len(clave) < MINIMO_CLAVE:
        return f"La contraseña debe tener al menos {MINIMO_CLAVE} caracteres."
    # bcrypt corta en 72 BYTES, no caracteres. Cada tilde o ñ ocupa dos, así
    # que 'contraseña'×8 son 80 caracteres pero 88 bytes. Si no avisamos acá,
    # hashear() lanza y el usuario ve un error 500 sin explicación.
    if len(clave.encode("utf-8")) > MAX_BYTES:
        return (f"La contraseña es demasiado larga (máximo {MAX_BYTES} bytes; "
                "las tildes y las ñ cuentan doble).")
    return None


def _rut_del_formulario(valor, obligatorio=False):
    """
    Devuelve (rut_normalizado, error). El RUT es OPCIONAL: el esquema dice
    pedirlo solo si vas a emitir boleta, y exigirlo para tomarse un café es
    pedir un dato que no necesitas.
    """
    valor = (valor or "").strip()
    if not valor:
        return (None, "El RUT es obligatorio.") if obligatorio else (None, None)
    try:
        return rut_chileno.normalizar(valor), None
    except rut_chileno.RutInvalido as e:
        return None, str(e)


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if session.get("usuario"):
        return redirect(url_for("dashboard"))
    if request.method != "POST":
        return render_template("registro.html", datos={})

    # Mismo criterio que en login, y antes del freno por IP. Acá el riesgo es
    # todavía más chico —que alguien te fuerce a crear una cuenta no le sirve
    # de nada— pero tener la mitad de los formularios con token y la otra
    # mitad sin él es peor que la regla simple: todos los POST lo llevan.
    if not csrf.valido(request.form.get("csrf")):
        abort(400, "Token de seguridad inválido. Recarga la página.")

    # Lo que escribió se devuelve a la plantilla si algo falla: nadie quiere
    # volver a tipear todo el formulario por un dígito verificador malo.
    datos = {
        "nombre_completo": (request.form.get("nombre_completo") or "").strip()[:90],
        "nickname":        (request.form.get("nickname") or "").strip()[:LARGO_NICKNAME],
        "email":           normalizar_email(request.form.get("email")),
        "rut":             (request.form.get("rut") or "").strip(),
        "telefono":        (request.form.get("telefono") or "").strip()[:20] or None,
    }

    def con_error(mensaje, codigo=400):
        flash(mensaje, "error")
        return render_template("registro.html", datos=datos), codigo

    # Freno por IP. Sin esto, un script crea diez mil cuentas en un minuto.
    espera = _bloqueado_registro()
    if espera:
        return con_error(
            f"Demasiados registros desde esta conexión. Espera {espera // 60 + 1} minutos.", 429)

    if "@" not in datos["email"] or "." not in datos["email"].split("@")[-1]:
        return con_error("Ese correo no parece válido.")
    if not datos["nombre_completo"]:
        return con_error("Necesitamos tu nombre.")

    nickname, error_nick = _nickname_del_formulario(datos["nickname"])
    if error_nick:
        return con_error(error_nick)

    clave = request.form.get("password", "")
    problema = _clave_valida(clave, request.form.get("password2", ""))
    if problema:
        return con_error(problema)

    rut, error_rut = _rut_del_formulario(datos["rut"])
    if error_rut:
        return con_error(error_rut)

    nombre, apellido = _partir_nombre(datos["nombre_completo"])

    existente = Usuario.por_email(datos["email"])

    # Un invitado es alguien que quedó en la base sin haberse registrado
    # (se inscribió a una actividad, por ejemplo). No es una cuenta: es un
    # marcador. Registrarse con ese correo la reclama y hereda el historial.
    #
    # LAS TRES CONDICIONES IMPORTAN, y mirar solo el hash fue un agujero real
    # (auditoría 2026-09-16): el esquema sembraba una cuenta de administrador
    # con el hash en NULL, así que cualquiera que se registrara con ESE correo
    # —publicado en el pie del sitio— se quedaba con la cuenta y con su rol.
    # Un invitado nace en actividad_controller con rol='cliente' y
    # estado='invitado'; cualquier otra cosa sin contraseña es una cuenta que
    # no se reclama, se recupera por correo.
    es_invitado = (existente
                   and not existente["password_hash"]
                   and existente["estado"] == "invitado"
                   and existente["rol"] == "cliente")

    if es_invitado:
        Usuario.reclamar(existente["id"], hashear(clave), nombre, apellido,
                         rut, datos["telefono"], nickname=nickname)
        fila = Usuario.por_id(existente["id"])
        app.logger.info("Invitado %s reclamado como cuenta", existente["id"])
    elif existente:
        # DECIDIDO (2026-09-11): esto confirma que el correo está registrado,
        # y se queda así. No es un pendiente.
        #
        # Esconderlo obliga a cambiar TODO el flujo: hoy registrarse deja la
        # sesión iniciada de inmediato, así que responder «revisa tu correo»
        # solo en el caso duplicado delata la diferencia igual. Para no
        # delatarla habría que dejar de iniciar sesión al registrarse y
        # mandar a todo el mundo a confirmar por correo primero — fricción
        # real, para todos, a cambio de esconder «esta persona tiene cuenta
        # en una cafetería».
        #
        # Lo que sí se cuida está cuidado: el login da un mensaje único y
        # recuperar contraseña responde lo mismo exista o no la cuenta. Ahí
        # el ataque es a una cuenta concreta; acá es una lista de correos.
        #
        # Si algún día el registro deja de iniciar sesión solo, esto se
        # revisa junto con ese cambio.
        _sumar_registro()
        return con_error("Ya hay una cuenta con ese correo. "
                         "Inicia sesión o recupera tu contraseña.", 409)
    else:
        if rut and Usuario.por_rut(rut):
            _sumar_registro()
            return con_error("Ya hay una cuenta con ese RUT.", 409)
        Usuario.crear(datos["email"], password_hash=hashear(clave),
                      nombre=nombre, apellido=apellido, nickname=nickname,
                      rol="cliente", estado="activo", rut=rut,
                      telefono=datos["telefono"])
        fila = Usuario.por_email(datos["email"])

    _sumar_registro()

    # El correo de verificación sale acá, y su resultado NO se mira: si el
    # SMTP está caído, la cuenta igual queda creada y la persona igual entra.
    # Desde el dashboard puede pedir que se lo reenvíen.
    enviar_verificacion(fila)

    # Sesión iniciada de inmediato: obligar a escribir la contraseña otra vez
    # justo después de crearla no aporta seguridad, solo fricción.
    session.clear()
    session["usuario"] = Usuario.para_sesion(fila)
    # Quien se registra lo hace desde su propio teléfono: queda recordado,
    # igual que al entrar con «Recordarme» marcado.
    session.permanent = True
    flash(f"¡Bienvenido, {fila['nombre'] or 'a ' + NEGOCIO['nombre_corto']}!", "info")
    return redirect(url_for("dashboard"))


@app.route("/salir")
def salir():
    session.clear()
    return redirect(url_for("login"))


@app.route("/recuperar-password", methods=["GET", "POST"])
def recuperar_password():
    if request.method != "POST":
        return render_template("recuperar_password.html", csrf_token=csrf.token())

    if not csrf.valido(request.form.get("csrf")):
        abort(400, "Token de seguridad inválido. Recarga la página.")

    # Freno por IP: sin esto esto es una máquina de mandar correos a terceros.
    espera = _bloqueado_registro()
    if espera:
        flash(f"Demasiadas solicitudes desde esta conexión. "
              f"Espera {espera // 60 + 1} minutos.", "error")
        return render_template("recuperar_password.html",
                               csrf_token=csrf.token()), 429

    email = normalizar_email(request.form.get("email"))
    fila = Usuario.por_email(email)

    # Solo mandamos si la cuenta existe y no está bloqueada, pero la RESPUESTA
    # es siempre la misma. Si dijéramos "ese correo no está registrado",
    # cualquiera podría averiguar quién tiene cuenta probando correos.
    if fila and fila["estado"] != "bloqueado":
        enviar_reset(fila)
    else:
        app.logger.info("Reset pedido para un correo sin cuenta utilizable: %s", email)

    _sumar_registro()
    return render_template("recuperar_password.html", enviado=True,
                           csrf_token=csrf.token())


@app.route("/restablecer-password", methods=["GET", "POST"])
def restablecer_password():
    """
    La segunda mitad: el enlace del correo llega acá con ?token=.

    El token no se guarda en ninguna tabla. Lleva adentro a quién apunta y
    una huella del hash actual de la contraseña, así que cambiarla lo mata.
    Ver config/enlaces.py.
    """
    return _crear_clave_con_enlace(
        enlaces.leer_reset, "restablecer_password", bienvenida=False,
        vencido=("Este enlace venció. Pide uno nuevo, vencen a los "
                 f"{enlaces.MINUTOS_RESET} minutos."),
        invalido="Este enlace no es válido. Pide uno nuevo desde «¿Olvidaste tu contraseña?».")


@app.route("/bienvenida", methods=["GET", "POST"])
def bienvenida_personal():
    """
    El enlace que recibe un barista cuando el admin le crea la cuenta: acá
    elige su contraseña. Es la misma pantalla que restablecer, con otro
    token (dura días, no minutos) y otros textos.
    """
    return _crear_clave_con_enlace(
        enlaces.leer_invitacion, "bienvenida_personal", bienvenida=True,
        vencido=("Este enlace venció: duran "
                 f"{enlaces.HORAS_INVITACION} horas. Pídele al administrador uno nuevo."),
        invalido="Este enlace no es válido. Pídele al administrador uno nuevo.")


def _crear_clave_con_enlace(leer, endpoint, bienvenida, vencido, invalido):
    token = request.values.get("token", "")
    # Segundo valor: el motivo del rechazo si falló, la huella si sirvió.
    usuario_id, huella_o_motivo = leer(token)

    def enlace_muerto(texto):
        return render_template("restablecer_password.html", invalido=texto,
                               bienvenida=bienvenida), 400

    if not usuario_id:
        return enlace_muerto(vencido if huella_o_motivo == "expirado" else invalido)

    fila = Usuario.por_id(usuario_id)
    if not fila or fila["estado"] == "bloqueado":
        return enlace_muerto("Este enlace ya no sirve para esta cuenta.")

    # La huella no calza => la contraseña ya cambió desde que se emitió el
    # enlace. O alguien lo usó, o la cambió por otra vía. En los dos casos
    # este enlace se acabó: eso es lo que le da un solo uso sin tabla.
    if not enlaces.reset_corresponde(huella_o_motivo, fila["password_hash"]):
        return enlace_muerto(
            "Este enlace ya se usó. Si necesitas cambiarla otra vez, pide uno nuevo.")

    if request.method != "POST":
        return render_template("restablecer_password.html", token=token,
                               accion=url_for(endpoint), bienvenida=bienvenida,
                               fila=fila, csrf_token=csrf.token())

    if not csrf.valido(request.form.get("csrf")):
        abort(400, "Token de seguridad inválido. Recarga la página.")

    clave = request.form.get("password", "")
    problema = _clave_valida(clave, request.form.get("password2", ""))
    if problema:
        flash(problema, "error")
        return render_template("restablecer_password.html", token=token,
                               accion=url_for(endpoint), bienvenida=bienvenida,
                               fila=fila, csrf_token=csrf.token()), 400

    Usuario.restablecer_password(fila["id"], hashear(clave))
    app.logger.info("Contraseña restablecida para el usuario %s", fila["id"])

    # Sesión limpia y adentro: acaba de probar que es el dueño de la casilla.
    session.clear()
    session["usuario"] = Usuario.para_sesion(Usuario.por_id(fila["id"]))
    session.permanent = False
    if bienvenida:
        flash("¡Listo! Ya tienes tu cuenta. Desde «Mesón», en tu menú, entras "
              "a vales y ruleta.", "info")
        return redirect(url_for("admin_inicio"))
    flash("Listo, tu contraseña quedó cambiada.", "info")
    return redirect(url_for("dashboard"))


@app.route("/verificar-email")
def verificar_email():
    """
    El enlace del correo de bienvenida. No exige sesión: se abre desde el
    correo, muchas veces en otro navegador o en el teléfono.
    """
    token = request.args.get("token", "")
    if not token:
        return render_template("verificar_email.html", estado="sin_token")

    usuario_id, huella_o_motivo = enlaces.leer_verificacion(token)
    if not usuario_id:
        return render_template(
            "verificar_email.html",
            estado="expirado" if huella_o_motivo == "expirado" else "invalido"), 400

    fila = Usuario.por_id(usuario_id)
    if not fila or not enlaces.verificacion_corresponde(huella_o_motivo, fila["email"]):
        # La huella es el correo: si cambió, este enlace apuntaba a otra
        # casilla y no prueba nada sobre la actual.
        return render_template("verificar_email.html", estado="invalido"), 400

    ya_estaba = bool(fila["email_verificado_at"])
    if not ya_estaba:
        Usuario.marcar_email_verificado(fila["id"])
        app.logger.info("Correo verificado para el usuario %s", fila["id"])
        # Si esta persona tiene la sesión abierta acá, que lo vea al tiro.
        if (session.get("usuario") or {}).get("id") == fila["id"]:
            session["usuario"] = Usuario.para_sesion(Usuario.por_id(fila["id"]))

    return render_template("verificar_email.html",
                           estado="ya_estaba" if ya_estaba else "listo")


@app.route("/reenviar-verificacion", methods=["POST"])
@requiere_sesion
def reenviar_verificacion():
    """Para quien no encuentra el correo. Solo para la propia cuenta."""
    if not csrf.valido(request.form.get("csrf")):
        abort(400, "Token de seguridad inválido. Recarga la página.")

    fila = Usuario.por_id(session["usuario"]["id"])
    if not fila:
        abort(404)
    if fila["email_verificado_at"]:
        flash("Tu correo ya está verificado.", "info")
        return redirect(url_for("dashboard"))

    espera = _bloqueado_registro()
    if espera:
        flash(f"Espera {espera // 60 + 1} minutos antes de pedir otro.", "error")
        return redirect(url_for("dashboard"))

    enviar_verificacion(fila)
    _sumar_registro()
    flash(f"Te reenviamos el enlace a {fila['email']}. Revisa también el spam.", "info")
    return redirect(url_for("dashboard"))


def _mis_actividades(usuario_id):
    """
    «Mis actividades» del dashboard: en qué se anotó esta persona, en qué va
    cada inscripción y el enlace a su voucher.

    Las canceladas y las vencidas se muestran igual, no se esconden: quien se
    quedó sin cupo porque se le pasó el plazo tiene que poder entender por
    qué, y el texto del estado se lo dice. Esconderlas deja a esa persona
    mirando una lista donde su taller simplemente desapareció.

    Las pasadas se recortan a cinco: son historial, no pendientes.

    El texto de cada estado sale de TEXTO_ESTADO, el mismo que usa la página
    de la inscripción, para que las dos pantallas digan lo mismo.
    """
    Actividad.liberar_vencidas()

    lista = []
    for fila in Actividad.inscripciones_de(usuario_id):
        d = dict(fila)
        titulo, detalle = TEXTO_ESTADO.get(d["estado"], ("Inscripción", ""))
        d["titulo_estado"] = titulo
        d["detalle_estado"] = detalle
        d["cuando"] = tiempo.largo(d["inicio_at"])
        d["dia"], d["mes"] = tiempo.dia_y_mes(d["inicio_at"])
        d["activo"] = d["estado"] in ("pagada", "asistio")
        d["ya_paso"] = bool(d.get("ya_paso"))
        d["cerrada"] = d["estado"] in ("cancelada", "vencida", "no_asistio")
        lista.append(d)

    proximas = sorted((d for d in lista if not d["ya_paso"]),
                      key=lambda d: d["inicio_at"])
    pasadas = [d for d in lista if d["ya_paso"]]
    return {"proximas": proximas, "pasadas": pasadas[:5], "hay": bool(lista)}


@app.route("/dashboard")
@requiere_sesion
def dashboard():
    # TODO Fase 3: cuando exista el ledger, saldo=Billetera.saldo_de(id) y
    # movimientos=Billetera.movimientos_de(id).
    return render_template(
        "dashboard.html",
        saldo=_saldo_vacio(),
        movimientos=[],
        actividades=_mis_actividades(session["usuario"]["id"]),
    )


@app.route("/perfil", methods=["GET", "POST"])
@requiere_sesion
def perfil():
    # Siempre desde la base, nunca desde la cookie: la cookie guarda cuatro
    # campos y va firmada al momento de iniciar sesión, así que muestra lo que
    # era, no lo que es.
    fila = Usuario.por_id(session["usuario"]["id"])
    if not fila:
        session.clear()
        flash("Tu cuenta ya no está disponible.", "error")
        return redirect(url_for("login"))

    def pantalla(codigo=200):
        return render_template(
            "perfil.html", cuenta=fila,
            rut_formateado=rut_chileno.formatear(fila["rut"]),
            csrf_token=csrf.token(),
        ), codigo

    if request.method != "POST":
        return pantalla()

    # Acá el token SÍ hace falta: es un POST autenticado que cambia datos.
    # En el registro no lo pongo porque no hay sesión que secuestrar — que
    # alguien te fuerce a crear una cuenta no le sirve de nada.
    if not csrf.valido(request.form.get("csrf")):
        abort(400, "Token de seguridad inválido. Recarga la página.")

    accion = request.form.get("accion", "datos")

    # ---------------------------------------------------------- contraseña
    if accion == "clave":
        actual = request.form.get("password_actual", "")
        # Pedir la contraseña actual no es burocracia: si alguien te agarra la
        # sesión abierta en un computador, sin esto te cambia la clave y te
        # deja fuera de tu propia cuenta.
        if not verificar(actual, fila["password_hash"]):
            flash("Tu contraseña actual no es correcta.", "error")
            return pantalla(401)

        nueva = request.form.get("password", "")
        problema = _clave_valida(nueva, request.form.get("password2", ""))
        if problema:
            flash(problema, "error")
            return pantalla(400)
        if verificar(nueva, fila["password_hash"]):
            flash("Esa es la contraseña que ya tenías.", "error")
            return pantalla(400)

        Usuario.guardar_hash(fila["id"], hashear(nueva))
        flash("Contraseña actualizada.", "info")
        return redirect(url_for("perfil"))

    # --------------------------------------------------------------- datos
    nombre = (request.form.get("nombre") or "").strip()[:45] or None
    apellido = (request.form.get("apellido") or "").strip()[:45] or None
    telefono = (request.form.get("telefono") or "").strip()[:20] or None

    nickname, error_nick = _nickname_del_formulario(request.form.get("nickname"))
    if error_nick:
        flash(error_nick, "error")
        return pantalla(400)

    rut, error_rut = _rut_del_formulario(request.form.get("rut"))
    if error_rut:
        flash(error_rut, "error")
        return pantalla(400)

    # Un RUT es de una persona. Si ya está en otra cuenta, algo está mal.
    if rut:
        duenio = Usuario.por_rut(rut)
        if duenio and duenio["id"] != fila["id"]:
            flash("Ese RUT ya está en otra cuenta.", "error")
            return pantalla(409)

    Usuario.actualizar_perfil(fila["id"], nombre, apellido, telefono, rut,
                              nickname=nickname)

    # La cookie guarda el nombre y las iniciales: si no la refrescamos, el
    # header sigue saludando con el nombre viejo hasta el próximo login.
    session["usuario"] = Usuario.para_sesion(Usuario.por_id(fila["id"]))
    flash("Datos guardados.", "info")
    return redirect(url_for("perfil"))


@app.route("/recarga")
@requiere_sesion
def recarga():
    # TODO Fase 3: tramos 10k/20k/40k y checkout de MercadoPago.
    return render_template("recarga.html")


@app.route("/credencial")
@requiere_sesion
def credencial():
    # TODO Fase 4: código de canje de 6 dígitos, válido 5 minutos.
    return render_template("credencial.html")


@app.route("/suscripcion")
def suscripcion():
    # TODO Fase 7: planes mensual, semestral y anual.
    return render_template("suscripcion.html")


@app.route("/" + NEGOCIO["segunda"]["slug"])
def segunda_marca():
    """
    La carta de la segunda marca, con su propia identidad.

    Existe para el local que vende dos cosas distintas bajo el mismo techo
    —café de día y pizzas de noche, por ejemplo— y quiere que cada una se vea
    como lo que es. Con marca.segunda.activa en false, esta página responde
    404 y su enlace desaparece del sitio: un negocio de una sola marca no
    tiene por qué cargar con ella.

    Se renderiza en el servidor y no por fetch como la landing: esa nació como
    página estática y conservó su copia del menú por compatibilidad. Esta nace
    acá, así que no hay nada de qué hacer respaldo. Si MySQL se cae, la página
    falla — y una carta en blanco es mejor que una carta con precios viejos
    en un negocio donde el precio es lo que cobras.
    """
    if not NEGOCIO["segunda"]["activa"]:
        abort(404)
    return render_template("segunda_marca.html",
                           menu=Carta.menu(NEGOCIO["segunda"]["slug"]))


@app.route("/api/v1/menu")
def api_menu():
    """
    La carta, desde la base de datos.

    La landing la consume acá en vez de tener el menú escrito a mano en el
    HTML: cambiar un precio pasa a ser un UPDATE, no un deploy.

    Si la base no responde devolvemos 503 y el front muestra un estado de error.
    Una copia escrita a mano podría ocultar una migración pendiente y publicar
    productos o precios que ya no existen.
    """
    marca = request.args.get("marca") or NEGOCIO["slug"]
    try:
        return jsonify(Carta.menu(marca))
    except Exception as e:
        app.logger.error("No se pudo leer el catálogo: %s", e)
        return jsonify({"error": "catálogo no disponible"}), 503


@app.route("/manifest.webmanifest")
def manifest():
    """
    El manifest de la PWA — lo que permite instalar el sitio en la pantalla
    de inicio del teléfono.

    Es una ruta y no un archivo estático porque el nombre, la descripción y
    los colores salen de config/negocio.py: así una instalación nueva no
    depende de que alguien se acuerde de editar un JSON aparte.

    El tipo MIME importa: con `application/json` los navegadores igual suelen
    aceptarlo, pero `application/manifest+json` es el que pide la norma y el
    que las herramientas de auditoría revisan.
    """
    return Response(render_template("manifest.webmanifest"),
                    mimetype="application/manifest+json")


@app.route("/health")
def health():
    """Para el monitor externo (UptimeRobot)."""
    return {"ok": True}, 200
