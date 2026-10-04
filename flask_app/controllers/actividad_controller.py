# ==========================================================================
# actividad_controller.py — talleres y catas
#
# Dos mitades:
#   público  /actividades, /actividades/<slug> e inscribirse
#   admin    /admin/actividades y la lista de inscritos
#
# Inscribirse NO exige tener cuenta. Quien llega desde Instagram a anotarse
# en una cata no quiere inventar una contraseña primero: deja su nombre y su
# correo y queda como 'invitado'. Si algún día se registra con ese mismo
# correo, Usuario.reclamar() convierte esa fila en su cuenta y hereda lo que
# ya hizo. Esa es toda la razón de que el estado 'invitado' exista.
# ==========================================================================

import re
from urllib.parse import quote

from flask import (Response, abort, flash, jsonify, redirect, render_template, request,
                   session, url_for)

from flask_app import app
from flask_app.config import calendario, correo, csrf, qr, tiempo
from flask_app.controllers.main_controller import (_bloqueado_registro,
                                                   _sumar_registro,
                                                   _url_absoluta,
                                                   requiere_admin,
                                                   requiere_sesion)
from flask_app.config.negocio import NEGOCIO
from flask_app.models.actividad_model import (Actividad, CupoAgotado,
                                              HORAS_DE_RESERVA, TEXTO_ESTADO,
                                              YaInscrito)
from flask_app.models.carta_model import Carta
from flask_app.models.usuario_model import Usuario, normalizar_email

ESTADOS_ACTIVIDAD = ("borrador", "publicada", "cancelada", "realizada")
ESTADOS_INSCRIPCION = ("pendiente", "por_revisar", "pagada", "cancelada",
                       "vencida", "asistio", "no_asistio")



# ------------------------------------------------------------------ ayudas

def _protegido_csrf():
    if not csrf.valido(request.form.get("csrf")):
        abort(400, "Token de seguridad inválido. Recarga la página.")


def _numero(valor, minimo=0, por_defecto=0):
    try:
        n = int(str(valor).strip().replace(".", "").replace("$", "") or por_defecto)
    except (TypeError, ValueError):
        return por_defecto
    return max(n, minimo)


def _texto(valor, maximo):
    v = (valor or "").strip()
    return v[:maximo] if v else None


def _telefono(valor):
    """
    El celular de quien se inscribe sin cuenta. Devuelve (numero, error).

    **Es obligatorio a propósito.** El voucher tiene que llegarle sí o sí, y
    mientras el envío automático de correos no esté activo (decisión de Seba:
    va en una segunda etapa), el único camino que de verdad llega es que
    alguien del local le escriba por WhatsApp. Sin número, esa persona queda
    dependiendo de que se acuerde de volver al enlace — y si cierra la
    pestaña, no queda nada.

    Se guarda normalizado a +56XXXXXXXXX: así el botón de WhatsApp del admin
    funciona siempre, sin adivinar. Un número de otro país se acepta tal cual
    si viene con su código: en una cata puede haber alguien de vacaciones, y
    es mejor guardar su número raro que rechazarlo.
    """
    crudo = (valor or "").strip()
    if not crudo:
        return None, ("Necesitamos tu celular: por ahí te mandamos el "
                      "voucher.")

    digitos = re.sub(r"\D", "", crudo)
    if not digitos:
        return None, "Ese número no se entiende. Escríbelo como +56 9 1234 5678."

    # Extranjero: llegó con + y no es chileno. No se valida con reglas de acá.
    if crudo.startswith("+") and not digitos.startswith("56"):
        if 8 <= len(digitos) <= 15:
            return "+" + digitos, None
        return None, ("Ese número no parece completo. Escríbelo con el código "
                      "del país, por ejemplo +54 9 11 1234 5678.")

    if digitos.startswith("56"):
        digitos = digitos[2:]
    if len(digitos) == 9 and digitos.startswith("9"):
        return "+56" + digitos, None

    # NO se adivina agregándole un 9 a un número de 8 dígitos: un teléfono de
    # casa de la ciudad también tiene 8, y quedaría guardado como un celular que
    # no existe. Mejor que la persona lo corrija ahora y no el día del evento.
    return None, ("Escribe tu celular con los 9 dígitos, partiendo por 9 "
                  "(por ejemplo 9 1234 5678).")


def _url_externa(valor, que="el afiche"):
    """
    Una URL que va a terminar dentro de un atributo del HTML. Devuelve
    (url, error). La usan el afiche y el formulario del evento.

    Solo se aceptan http, https y rutas del propio sitio. No es paranoia: un
    `javascript:` pegado acá
    terminaría dentro de un atributo del HTML, y aunque hoy solo el admin
    llena este campo, el filtro cuesta tres líneas y la alternativa es
    confiar para siempre en que nadie se equivoque.

    Lo que NO se comprueba es que la imagen exista o que sea una imagen: eso
    solo se sabe pidiéndola, y no vale la pena bloquear el guardado por una
    petición a un servidor ajeno que puede tardar. Si la URL está mala, se ve
    al tiro en la ficha.
    """
    v = (valor or "").strip()[:500]
    if not v:
        return None, None
    # También se acepta una ruta del propio sitio («/static/img/afiche.jpg»),
    # para poder dejar el afiche junto a las demás imágenes en vez de depender
    # de que un servidor ajeno siga vivo el día del evento.
    if v.startswith("/") and not v.startswith("//"):
        return v, None
    if not (v.startswith("http://") or v.startswith("https://")):
        return None, (f"La URL de {que} tiene que empezar con http:// o "
                      "https://, o ser una ruta del sitio que parta con /.")
    return v, None


def _volver_seguro(por_defecto):
    """
    A dónde vuelve un formulario del panel. SOLO rutas de este sitio.

    El campo `volver` viaja escondido en el formulario para devolver al admin
    a la misma pantalla y con los mismos filtros. Aceptarlo tal cual era un
    redirect abierto (auditoría 2026-09-16): el sitio prestaba su nombre para
    llevar a cualquier parte. El resto del proyecto ya lo hacía bien —ver
    _destino() en muro_controller y _volver() en usuarios_controller—; estas
    cuatro rutas se habían quedado atrás.

    '//otro.sitio' se rechaza además de 'https://otro.sitio': el navegador lee
    las dos barras como «mismo protocolo, otro dominio».
    """
    destino = (request.form.get("volver") or "").strip()
    if destino.startswith("/") and not destino.startswith("//"):
        return destino
    return por_defecto


def _vista(fila):
    """
    Agrega a la fila lo que la plantilla necesita y el SQL no da: las fechas
    en hora de Chile y los cupos ya calculados.
    """
    d = dict(fila)
    libres = d["cupos"] - d["inscritos"]
    d["libres"] = max(libres, 0)
    d["agotada"] = libres <= 0
    d["cuando"] = tiempo.largo(d["inicio_at"])
    d["cuando_corto"] = tiempo.corto(d["inicio_at"])
    d["dia"], d["mes"] = tiempo.dia_y_mes(d["inicio_at"])
    d["termina"] = tiempo.largo(d["fin_at"]) if d.get("fin_at") else None
    d["ya_paso"] = (d.get("fin_at") or d["inicio_at"]) < tiempo.ahora_utc()
    d["gratis"] = d["precio_clp"] == 0
    d["precio_fmt"] = "Gratis" if d["gratis"] else f"${d['precio_clp']:,.0f}".replace(",", ".")
    return d


def _publica(fila):
    """
    La misma actividad, pero solo con lo que la landing necesita y en tipos
    que sobreviven a JSON (nada de datetime crudo).

    La URL se arma acá con url_for y no en el JavaScript: el front no tiene
    por qué saber cómo se construyen las rutas de Flask, y el día que la
    landing vuelva a Pages basta con que esto devuelva una URL absoluta.
    """
    d = _vista(fila)
    return {
        "slug": d["slug"],
        "nombre": d["nombre"],
        "url": url_for("actividad", slug=d["slug"]),
        "dia": d["dia"],
        "mes": d["mes"],
        "cuando": d["cuando"],
        "lugar": d.get("lugar"),
        "imagen": d.get("imagen_url"),
        "precio_fmt": d["precio_fmt"],
        "libres": d["libres"],
        "agotada": d["agotada"],
    }


# ------------------------------------------------------------------ público

@app.route("/actividades")
def actividades():
    Actividad.liberar_vencidas()
    lista = [_vista(a) for a in Actividad.agenda()]
    return render_template("actividades.html", actividades=lista)


@app.route("/api/v1/agenda")
def api_agenda():
    """
    Las próximas actividades publicadas, para la sección de la landing.

    Existe por la misma razón que /api/v1/menu: que la landing pueda vivir
    en GitHub Pages sin quedarse con una agenda escrita a mano. Y acá pesa
    más todavía que en la carta, porque los cupos cambian solos cada vez que
    alguien se inscribe: una agenda estática mostraría cupos que ya no hay.

    ?limite=N recorta (1..12). Si la base no responde devolvemos 503 y el
    front deja lo que ya venía renderizado en el HTML.
    """
    try:
        limite = max(1, min(int(request.args.get("limite", 3)), 12))
    except (TypeError, ValueError):
        limite = 3
    try:
        # Soltar acá las reservas vencidas es lo que mantiene honesto el
        # número de cupos: esta consulta es la que más se mira.
        Actividad.liberar_vencidas()
        return jsonify([_publica(a) for a in Actividad.agenda(limite=limite)])
    except Exception as e:
        app.logger.error("No se pudo leer la agenda: %s", e)
        return jsonify({"error": "agenda no disponible"}), 503


@app.route("/actividades/<slug>")
def actividad(slug):
    Actividad.liberar_vencidas()
    fila = Actividad.por_slug(slug)
    # Un borrador no existe para el público. 404 y no 403: no le confirmamos
    # a nadie que estamos preparando algo que todavía no anunciamos.
    if not fila or fila["estado"] == "borrador":
        abort(404)

    mia = None
    if session.get("usuario"):
        mia = Actividad.inscripcion_de(fila["id"], session["usuario"]["id"])
        # Las inscripciones de antes del voucher no tienen código. Se les
        # crea el primero cuando hace falta enlazarlas, no en la migración.
        if mia and mia["estado"] != "cancelada" and not mia.get("voucher_codigo"):
            mia = dict(mia)
            mia["voucher_codigo"] = Actividad.codigo_de(mia["id"])

    return render_template("actividad.html", a=_vista(fila), mia=mia,
                           csrf_token=csrf.token())


@app.route("/actividades/<slug>/inscribirme", methods=["POST"])
def inscribirme(slug):
    _protegido_csrf()
    fila = Actividad.por_slug(slug)
    if not fila or fila["estado"] != "publicada":
        abort(404)

    volver = redirect(url_for("actividad", slug=slug))

    # --- ¿quién se inscribe? ---
    if session.get("usuario"):
        usuario_id = session["usuario"]["id"]
    else:
        # Sin sesión: nombre y correo, y queda como invitado.
        espera = _bloqueado_registro()
        if espera:
            flash(f"Demasiadas inscripciones desde esta conexión. "
                  f"Espera {espera // 60 + 1} minutos.", "error")
            return volver

        email = normalizar_email(request.form.get("email"))
        nombre = _texto(request.form.get("nombre"), 45)
        if "@" not in email or not nombre:
            flash("Necesitamos tu nombre y un correo válido.", "error")
            return volver

        telefono, error_tel = _telefono(request.form.get("telefono"))
        if error_tel:
            flash(error_tel, "error")
            return volver

        existente = Usuario.por_email(email)
        if existente:
            # Ojo: si ya tiene cuenta con contraseña, NO lo inscribimos a
            # ciegas. Cualquiera podría anotar a otra persona escribiendo su
            # correo, y peor, ver su nombre confirmado en la respuesta.
            if existente["password_hash"]:
                flash("Ese correo ya tiene cuenta. Inicia sesión para inscribirte.", "error")
                return redirect(url_for("login", next=url_for("actividad", slug=slug)))
            usuario_id = existente["id"]
            # Un invitado que vuelve puede haber cambiado de número. El que
            # acaba de escribir es el bueno: si no, el admin le escribiría al
            # viejo y no llegaría nada.
            Usuario.completar_contacto(usuario_id, nombre=nombre, telefono=telefono)
        else:
            Usuario.crear(email, password_hash=None, nombre=nombre,
                          rol="cliente", estado="invitado",
                          telefono=telefono)
            usuario_id = Usuario.por_email(email)["id"]
        _sumar_registro()

    # --- tomar el cupo ---
    try:
        ins = Actividad.inscribir(fila["id"], usuario_id)
    except YaInscrito as e:
        # Ya estaba inscrito: igual lo mandamos a su página, que es donde
        # está lo que tiene que hacer. Dejarlo en la ficha con un aviso rojo
        # no le resuelve nada.
        previa = Actividad.inscripcion_de(fila["id"], usuario_id)
        flash(str(e), "info")
        if previa:
            return redirect(url_for("inscripcion",
                                    codigo=Actividad.codigo_de(previa["id"])))
        return volver
    except CupoAgotado as e:
        flash(str(e), "error")
        return volver

    completa = Actividad.por_codigo(ins["codigo"])
    if completa:
        _correo_inscripcion(completa)

    if fila["precio_clp"]:
        flash(f"Te guardamos el cupo en «{fila['nombre']}» por "
              f"{HORAS_DE_RESERVA} horas. Acá está lo que falta.", "info")
    else:
        flash(f"¡Listo! Te esperamos en «{fila['nombre']}». "
              "Este es tu voucher.", "info")
    # A su página y no de vuelta a la ficha: ahí está el enlace al
    # formulario, el plazo y —cuando se confirme el pago— el voucher.
    return redirect(url_for("inscripcion", codigo=ins["codigo"]))


@app.route("/actividades/<slug>/cancelar", methods=["POST"])
@requiere_sesion
def cancelar_inscripcion(slug):
    _protegido_csrf()
    fila = Actividad.por_slug(slug)
    if not fila:
        abort(404)
    Actividad.cancelar_inscripcion(fila["id"], session["usuario"]["id"])
    flash("Cancelamos tu inscripción. El cupo queda libre para alguien más.", "info")
    return redirect(url_for("actividad", slug=slug))


# ------------------------------------------------------------------- admin

def _datos_del_formulario():
    nombre = _texto(request.form.get("nombre"), 150)
    if not nombre:
        return None, "El nombre no puede quedar vacío."

    inicio = tiempo.local_a_utc(request.form.get("inicio_at"))
    if not inicio:
        return None, "Falta la fecha de inicio, o está mal escrita."

    fin = tiempo.local_a_utc(request.form.get("fin_at"))
    # La base tiene un CHECK que exige fin > inicio. Comprobarlo acá evita
    # que el error salga como un 500 sin explicación.
    if fin and fin <= inicio:
        return None, "La hora de término tiene que ser posterior a la de inicio."

    marca_id = request.form.get("marca_id") or None
    if marca_id:
        validas = {str(m["id"]) for m in Carta.marcas_activas()}
        if str(marca_id) not in validas:
            return None, "Esa marca no existe."

    estado = request.form.get("estado", "borrador")
    if estado not in ESTADOS_ACTIVIDAD:
        return None, "Ese estado no existe."

    cupos = _numero(request.form.get("cupos"), minimo=1, por_defecto=1)

    imagen_url, error_imagen = _url_externa(request.form.get("imagen_url"),
                                            "el afiche")
    if error_imagen:
        return None, error_imagen

    # El formulario donde la persona sube su comprobante. Va por actividad y
    # no en la configuración porque el dueño arma uno nuevo para cada taller,
    # con la fecha y el precio escritos adentro.
    formulario_url, error_form = _url_externa(request.form.get("formulario_url"),
                                              "el formulario")
    if error_form:
        return None, error_form

    return {
        "marca_id": int(marca_id) if marca_id else None,
        "nombre": nombre,
        "descripcion": _texto(request.form.get("descripcion"), 4000),
        "inicio_at": inicio,
        "fin_at": fin,
        "lugar": _texto(request.form.get("lugar"), 200),
        "imagen_url": imagen_url,
        "formulario_url": formulario_url,
        "cupos": cupos,
        "precio_clp": _numero(request.form.get("precio_clp")),
        "estado": estado,
    }, None


@app.route("/admin/actividades")
@requiere_admin
def admin_actividades():
    lista = []
    for a in Actividad.listar_para_admin():
        v = _vista(a)
        v["inicio_form"] = tiempo.para_formulario(a["inicio_at"])
        v["fin_form"] = tiempo.para_formulario(a["fin_at"])
        lista.append(v)
    return render_template("admin_actividades.html",
                           actividades=lista,
                           marcas=Carta.marcas_activas(),
                           estados=ESTADOS_ACTIVIDAD,
                           csrf_token=csrf.token())


@app.route("/admin/actividades/crear", methods=["POST"])
@requiere_admin
def admin_actividades_crear():
    _protegido_csrf()
    datos, error = _datos_del_formulario()
    if error:
        flash(error, "error")
    else:
        Actividad.crear(datos)
        flash(f"«{datos['nombre']}» creada.", "info")
    return redirect(url_for("admin_actividades"))


@app.route("/admin/actividades/<int:actividad_id>", methods=["POST"])
@requiere_admin
def admin_actividades_actualizar(actividad_id):
    _protegido_csrf()
    actual = Actividad.obtener(actividad_id)
    if not actual:
        abort(404)
    datos, error = _datos_del_formulario()
    if error:
        flash(error, "error")
    # Bajar los cupos por debajo de la gente ya inscrita dejaría a alguien
    # fuera sin avisarle. Se bloquea y se explica.
    elif datos["cupos"] < actual["inscritos"]:
        flash(f"No puedes dejar {datos['cupos']} cupos: ya hay "
              f"{actual['inscritos']} personas inscritas.", "error")
    else:
        Actividad.actualizar(actividad_id, datos)
        flash(f"«{datos['nombre']}» actualizada.", "info")
    return redirect(url_for("admin_actividades"))


@app.route("/admin/actividades/<int:actividad_id>/eliminar", methods=["POST"])
@requiere_admin
def admin_actividades_eliminar(actividad_id):
    _protegido_csrf()
    actual = Actividad.obtener(actividad_id)
    if not actual:
        abort(404)
    if Actividad.eliminar(actividad_id):
        flash(f"«{actual['nombre']}» eliminada.", "info")
    else:
        flash(f"No se puede eliminar «{actual['nombre']}»: hay gente inscrita. "
              "Primero márcala como Cancelada y guarda (así ellos lo ven al "
              "entrar); después ya se puede eliminar.", "error")
    return redirect(url_for("admin_actividades"))


@app.route("/admin/actividades/<int:actividad_id>/estado", methods=["POST"])
@requiere_admin
def admin_actividades_estado(actividad_id):
    _protegido_csrf()
    estado = request.form.get("estado")
    if estado not in ESTADOS_ACTIVIDAD or not Actividad.obtener(actividad_id):
        abort(400)
    Actividad.cambiar_estado(actividad_id, estado)
    return jsonify({"id": actividad_id, "estado": estado})


@app.route("/admin/actividades/<int:actividad_id>/inscritos")
@requiere_admin
def admin_inscritos(actividad_id):
    Actividad.liberar_vencidas()
    fila = Actividad.obtener(actividad_id)
    if not fila:
        abort(404)
    vista = _vista(fila)
    return render_template("admin_inscritos.html",
                           a=vista,
                           inscritos=[_vista_inscrito(i, vista)
                                      for i in Actividad.inscritos_en(actividad_id)],
                           estados=ESTADOS_INSCRIPCION,
                           csrf_token=csrf.token())


@app.route("/admin/inscripciones/<int:inscripcion_id>/estado", methods=["POST"])
@requiere_admin
def admin_inscripcion_estado(inscripcion_id):
    _protegido_csrf()
    estado = request.form.get("estado")
    if estado not in ESTADOS_INSCRIPCION:
        abort(400)
    Actividad.cambiar_estado_inscripcion(inscripcion_id, estado)
    flash("Inscripción actualizada.", "info")
    return redirect(_volver_seguro(url_for("admin_actividades")))


# ========================================================================
# La página de la inscripción — y, cuando el pago está confirmado, el voucher
#
# UNA sola página para las dos cosas, y con la misma dirección de principio a
# fin. Quien se inscribe recibe un enlace que sirve el primer día («falta que
# llenes el formulario») y el día del evento («este es tu voucher»). Dos
# páginas distintas obligarían a mandar dos enlaces, y el segundo llegaría
# justo cuando la persona ya archivó el primero.
#
# El código ES la llave: no pide sesión. Tiene que funcionar para el invitado
# que se inscribió sin cuenta, que es medio mundo, y en el teléfono donde
# abrió el correo. Lo que protege es el azar del código (40 bits) y que lo
# que hay detrás no es delicado: el nombre del evento y el suyo propio.
# ========================================================================

def _vista_inscripcion(fila):
    """Lo que la plantilla necesita, ya masticado."""
    d = dict(fila)
    titulo, detalle = TEXTO_ESTADO.get(d["estado"], ("Inscripción", ""))

    d["titulo_estado"] = titulo
    d["detalle_estado"] = detalle
    d["activo"] = d["estado"] == "pagada"
    d["usado"] = d["estado"] == "asistio"
    d["esperando_formulario"] = d["estado"] == "pendiente"
    d["en_revision"] = d["estado"] == "por_revisar"
    d["cerrada"] = d["estado"] in ("cancelada", "vencida", "no_asistio")

    d["persona"] = " ".join(x for x in (d.get("nombre"), d.get("apellido")) if x) or d["email"]
    d["cuando"] = tiempo.largo(d["inicio_at"])
    d["dia"], d["mes"] = tiempo.dia_y_mes(d["inicio_at"])
    d["gratis"] = d["precio_clp"] == 0
    d["precio_fmt"] = "Gratis" if d["gratis"] else f"${d['precio_clp']:,.0f}".replace(",", ".")
    d["vence"] = tiempo.largo(d["reserva_vence_at"]) if d.get("reserva_vence_at") else None
    d["ya_paso"] = (d.get("fin_at") or d["inicio_at"]) < tiempo.ahora_utc()

    # El QR solo cuando el voucher vale. Uno impreso sobre un «falta que
    # pagues» sería una entrada falsa esperando a que alguien la muestre.
    d["url"] = _url_absoluta("inscripcion", codigo=d["voucher_codigo"])
    d["qr"] = qr.svg(d["url"]) if (d["activo"] or d["usado"]) else None

    # «Agregar a mi calendario»: solo con el voucher activo y el evento por
    # venir. Agendar algo que todavía puede vencer, o que ya pasó, confunde.
    d["calendario"] = d["activo"] and not d["ya_paso"]
    d["calendario_url"] = _url_absoluta("inscripcion_calendario", codigo=d["voucher_codigo"])
    return d


# --------------------------------------------- llevarlo al calendario

def _evento_calendario(d):
    """Los datos del taller tal como quedan en el calendario de la persona."""
    detalle = f"Tu voucher (muéstralo al llegar): {d['url']}"
    if d.get("descripcion"):
        descripcion = d["descripcion"].strip()
        if len(descripcion) > 600:
            descripcion = descripcion[:600].rsplit(" ", 1)[0] + "…"
        detalle = f"{descripcion}\n\n{detalle}"
    return {
        "titulo": f"{d['actividad']} · {NEGOCIO['nombre']}",
        "inicio": d["inicio_at"],
        "fin": d.get("fin_at"),
        "detalle": detalle,
        "lugar": d.get("lugar") or f"{NEGOCIO['nombre']}, {NEGOCIO['direccion']}, {NEGOCIO['ciudad']}",
    }


def _inscripcion_para_calendario(codigo):
    """La vista de la inscripción si se puede agendar; si no, None."""
    fila = Actividad.por_codigo(codigo)
    if not fila:
        abort(404)
    d = _vista_inscripcion(fila)
    return d if d["calendario"] else None


@app.route("/inscripcion/<codigo>/calendario")
def inscripcion_calendario(codigo):
    """
    Lleva a Google Calendar con el taller ya escrito.

    Es una dirección propia que redirige, y no el enlace de Google directo,
    por dos razones: en un WhatsApp se lee corto y limpio, y si el admin
    cambia la hora del taller, el enlace que ya se mandó lleva a la hora
    nueva. Sin voucher activo (o con el evento ya pasado) vuelve a la
    página de la inscripción, que explica en qué va.
    """
    d = _inscripcion_para_calendario(codigo)
    if not d:
        return redirect(url_for("inscripcion", codigo=codigo))
    e = _evento_calendario(d)
    return redirect(calendario.google_url(e["titulo"], e["inicio"], e["fin"],
                                          e["detalle"], e["lugar"]))


@app.route("/inscripcion/<codigo>/calendario.ics")
def inscripcion_calendario_ics(codigo):
    """El mismo evento como .ics, para el iPhone, Outlook y el resto."""
    d = _inscripcion_para_calendario(codigo)
    if not d:
        return redirect(url_for("inscripcion", codigo=codigo))
    e = _evento_calendario(d)
    texto = calendario.ics(f"{d['voucher_codigo']}@{request.host}", e["titulo"],
                           e["inicio"], e["fin"], e["detalle"], e["lugar"],
                           url=d["url"])
    return Response(texto, mimetype="text/calendar", headers={
        "Content-Disposition": f'attachment; filename="curso-{d["voucher_codigo"]}.ics"',
        "Cache-Control": "no-store",
    })


@app.route("/inscripcion/<codigo>")
def inscripcion(codigo):
    Actividad.liberar_vencidas()
    fila = Actividad.por_codigo(codigo)
    if not fila:
        abort(404)
    return render_template("inscripcion.html", i=_vista_inscripcion(fila),
                           csrf_token=csrf.token())


@app.route("/inscripcion/<codigo>/ya-envie", methods=["POST"])
def inscripcion_aviso(codigo):
    """
    «Ya envié el formulario». Detiene el reloj de la reserva y pone la
    inscripción en la cola del admin.

    Es la declaración de la persona, no una comprobación: el comprobante vive
    en un formulario de Google y la app no tiene cómo preguntarle a Google si
    llegó. Mentir acá no consigue un voucher —eso lo activa el admin mirando
    el comprobante— sino solo estirar la reserva, y esa es la peor
    consecuencia posible de que alguien apriete el botón de más.
    """
    _protegido_csrf()
    fila = Actividad.por_codigo(codigo)
    if not fila:
        abort(404)

    if Actividad.avisar_formulario(fila["id"]):
        flash("Gracias. Tu cupo queda guardado mientras revisamos el "
              "comprobante.", "info")
    else:
        flash("Esta inscripción ya no está esperando el formulario.", "info")
    return redirect(url_for("inscripcion", codigo=codigo))


# --------------------------------------------------------------- correos

def _correo_inscripcion(fila):
    """
    El correo del cupo recién tomado: qué falta, dónde y hasta cuándo.

    Se manda también a quien tiene cuenta, no solo al invitado: es el único
    lugar donde queda guardado el enlace de su inscripción cuando cierre la
    pestaña.
    """
    d = _vista_inscripcion(fila)
    if d["gratis"]:
        cuerpo = (
            f"{d['persona']}:\n\n"
            f"Te esperamos en «{d['actividad']}», {d['cuando']}"
            f"{', ' + d['lugar'] if d.get('lugar') else ''}.\n\n"
            f"Este es tu voucher, muéstralo al llegar:\n{d['url']}\n"
        )
        asunto = f"Tu cupo en {d['actividad']} · {NEGOCIO['nombre']}"
    else:
        cuerpo = (
            f"{d['persona']}:\n\n"
            f"Te guardamos un cupo en «{d['actividad']}», {d['cuando']}.\n"
            f"Valor: {d['precio_fmt']}.\n\n"
            f"Para confirmarlo, completa el formulario con tu comprobante de "
            f"transferencia y después avísanos desde tu página:\n\n"
            f"{d['url']}\n\n"
            f"El cupo queda reservado hasta {d['vence']}"
            f" (unas {HORAS_DE_RESERVA} horas).\n"
            "Apenas revisemos el comprobante te activamos el voucher.\n"
        )
        asunto = f"Tu cupo en {d['actividad']} · {NEGOCIO['nombre']}"
    return correo.enviar(d["email"], asunto, cuerpo, logger=app.logger)


def _correo_voucher(fila):
    """El pago quedó confirmado: acá está la entrada."""
    d = _vista_inscripcion(fila)
    cuerpo = (
        f"{d['persona']}:\n\n"
        f"Listo, confirmamos tu pago de «{d['actividad']}».\n\n"
        f"Este es tu voucher — muéstralo el día del evento:\n{d['url']}\n\n"
        f"Código: {d['voucher_codigo']}\n"
        f"Cuándo: {d['cuando']}\n"
        + (f"Dónde: {d['lugar']}\n" if d.get("lugar") else "")
        + (f"\nAgrégalo a tu calendario:\n{d['calendario_url']}\n" if d["calendario"] else "")
        + "\n¡Nos vemos!\n"
    )
    return correo.enviar(d["email"],
                         f"Tu voucher para {d['actividad']} · {NEGOCIO['nombre']}",
                         cuerpo, logger=app.logger)


def _correo_rechazo(fila):
    """El comprobante no cuadró. Se dice el motivo y que puede reintentar."""
    d = _vista_inscripcion(fila)
    motivo = d.get("nota_admin") or "no pudimos validar el comprobante"
    cuerpo = (
        f"{d['persona']}:\n\n"
        f"Revisamos tu inscripción a «{d['actividad']}» y {motivo}.\n\n"
        f"Tu cupo sigue guardado hasta {d['vence']}. Puedes volver a enviar "
        f"el formulario con el comprobante desde tu página:\n\n{d['url']}\n\n"
        "Si crees que es un error, respóndenos este correo.\n"
    )
    return correo.enviar(d["email"],
                         f"Sobre tu inscripción a {d['actividad']} · {NEGOCIO['nombre']}",
                         cuerpo, logger=app.logger)


# ----------------------------------------------------- admin del voucher

@app.route("/admin/inscripciones/<int:inscripcion_id>/confirmar", methods=["POST"])
@requiere_admin
def admin_inscripcion_confirmar(inscripcion_id):
    """Vi el comprobante en el formulario: activa el voucher y avisa."""
    _protegido_csrf()
    if not Actividad.obtener_inscripcion(inscripcion_id):
        abort(404)
    Actividad.codigo_de(inscripcion_id)      # las viejas no tienen código
    fila = Actividad.confirmar_pago(inscripcion_id)
    _correo_voucher(fila)
    quien = fila.get("nombre") or fila["email"]
    if correo.hay_envio_real():
        flash(f"Voucher activado para {quien}. Le mandamos el correo.", "info")
    else:
        # Sin SMTP configurado, correo.enviar() escribe el mensaje en la
        # carpeta buzon/ y devuelve True. Decirle al admin «le mandamos el
        # correo» sería mentirle, y se enteraría el día del evento.
        flash(f"Voucher activado para {quien}. El envío de correos todavía no "
              "está configurado, así que el mensaje quedó en la carpeta "
              "buzon/: cópiale el enlace y mándaselo tú.", "info")
    return redirect(_volver_seguro(url_for("admin_actividades")))


@app.route("/admin/inscripciones/<int:inscripcion_id>/rechazar", methods=["POST"])
@requiere_admin
def admin_inscripcion_rechazar(inscripcion_id):
    """
    El comprobante no cuadra. NO cancela: devuelve la inscripción a
    'pendiente' con el motivo y el reloj de nuevo andando, para que la
    persona pueda arreglarlo. Echarla del evento es otro botón.
    """
    _protegido_csrf()
    if not Actividad.obtener_inscripcion(inscripcion_id):
        abort(404)
    motivo = _texto(request.form.get("motivo"), 255)
    fila = Actividad.rechazar_pago(inscripcion_id, motivo)
    _correo_rechazo(fila)
    flash("Le avisamos que el comprobante no cuadró.", "info")
    return redirect(_volver_seguro(url_for("admin_actividades")))


# ------------------------------------- compartir el enlace a mano

def _whatsapp(telefono, texto):
    """
    El enlace wa.me para escribirle a esa persona con el mensaje ya escrito.

    Abrir WhatsApp no manda nada: deja la conversación lista y el envío lo
    hace el admin. Es a propósito — mandar mensajes solo sería otra cosa.

    El número se normaliza adivinando: en Chile los celulares son 9 dígitos
    empezando en 9, y mucha gente los guarda sin el +56. Si el formato no
    calza con nada conocido se manda tal cual y que WhatsApp reclame; peor
    sería no ofrecer el botón.
    """
    if not telefono:
        return None
    digitos = re.sub(r"\D", "", telefono)
    if not digitos:
        return None
    if len(digitos) == 9 and digitos.startswith("9"):
        digitos = "56" + digitos
    elif len(digitos) == 8:
        digitos = "569" + digitos
    return f"https://wa.me/{digitos}?text={quote(texto)}"


def _vista_inscrito(fila, actividad):
    """
    Una fila de la lista del admin, con lo que hace falta para escribirle a
    esa persona: el enlace absoluto a su inscripción y el de WhatsApp.

    El enlace se arma acá con _url_absoluta y no en la plantilla porque tiene
    que ser absoluto —se pega en un WhatsApp, no se hace clic en el sitio— y
    eso el HTML no lo sabe hacer.
    """
    d = dict(fila)
    if not d.get("voucher_codigo"):
        # Una inscripción de antes del voucher. Se le crea el código al
        # mirarla, que es justo cuando alguien va a querer mandárselo.
        d["voucher_codigo"] = Actividad.codigo_de(d["id"])

    d["url"] = _url_absoluta("inscripcion", codigo=d["voucher_codigo"])
    nombre = (d.get("nombre") or "").strip()
    saludo = f"Hola {nombre}: " if nombre else "Hola: "

    if d["estado"] in ("pagada", "asistio"):
        mensaje = (f"{saludo}este es tu voucher para «{actividad['nombre']}», "
                   f"{actividad['cuando']}. Muéstralo al llegar: {d['url']}")
        # El enlace al calendario va solo con el voucher activo y el taller
        # por venir: es el mismo criterio del botón del voucher.
        if d["estado"] == "pagada" and not actividad.get("ya_paso"):
            d["calendario_url"] = _url_absoluta("inscripcion_calendario",
                                                codigo=d["voucher_codigo"])
            mensaje += f"\n\nAgrégalo a tu calendario: {d['calendario_url']}"
    else:
        mensaje = (f"{saludo}acá puedes ver tu inscripción a «{actividad['nombre']}» "
                   f"y subir tu comprobante: {d['url']}")
    d["mensaje"] = mensaje
    d["whatsapp"] = _whatsapp(d.get("telefono"), mensaje)
    return d


@app.route("/admin/inscripciones/<int:inscripcion_id>/reenviar", methods=["POST"])
@requiere_admin
def admin_inscripcion_reenviar(inscripcion_id):
    """
    Le manda otra vez el correo con su enlace. El que corresponda: el del
    voucher si ya está pagada, y el del cupo reservado si todavía no.
    """
    _protegido_csrf()
    if not Actividad.obtener_inscripcion(inscripcion_id):
        abort(404)
    Actividad.codigo_de(inscripcion_id)
    fila = Actividad.obtener_inscripcion(inscripcion_id)

    if fila["estado"] in ("pagada", "asistio"):
        salio = _correo_voucher(fila)
    else:
        salio = _correo_inscripcion(fila)

    if salio and not correo.hay_envio_real():
        flash("El envío de correos todavía no está configurado: el mensaje "
              f"para {fila['email']} quedó en la carpeta buzon/. Copia el "
              "enlace y mándaselo por WhatsApp.", "info")
    elif salio:
        flash(f"Le reenviamos el enlace a {fila['email']}.", "info")
    else:
        # correo.enviar() no lanza nunca: devuelve False y deja el detalle en
        # el log. Decirle «listo» al admin cuando no salió sería peor.
        flash(f"No pude enviar el correo a {fila['email']}. Revisa el log; "
              "igual puedes copiar el enlace y mandárselo tú.", "error")
    return redirect(_volver_seguro(url_for("admin_actividades")))
