# ==========================================================================
# muro_controller.py — el muro de deseos
#
# Dos mitades:
#   público  /muro, POST /muro/enviar y /api/v1/muro
#   admin    /admin/muro y aprobar / rechazar
#
# Para escribir hay que tener sesión iniciada (decisión de Seba). Es distinto
# del flujo de las actividades, donde sí se puede participar como invitado: en
# una inscripción el nombre lo lee el barista, acá el texto queda publicado en
# la portada. Con cuenta, si alguien abusa se bloquea la cuenta y se acabó;
# sin cuenta, vuelve con otro correo inventado a los diez segundos.
#
# NADA SE PUBLICA SOLO. Todo entra en 'pendiente'. La única consulta que
# alimenta la portada filtra por 'aprobado'.
# ==========================================================================

from flask import (abort, flash, jsonify, redirect, render_template, request,
                   session, url_for)

from flask_app import app
from flask_app.config import csrf, tiempo
from flask_app.controllers.main_controller import requiere_admin, requiere_sesion
from flask_app.models.muro_model import (ESTADOS, LARGO_MENSAJE,
                                         LARGO_MOTIVO, LARGO_NICKNAME,
                                         MINIMO_MENSAJE, CuentaBloqueada,
                                         DemasiadosEnvios, Muro, SinNickname,
                                         YaTienePendiente)

# Cuántos se traen para el carrusel de la portada, y de a cuántos avanza /muro.
#
# Eran 6 cuando la portada los mostraba en grilla y más tarjetas significaban
# más alto de página. Con el carrusel el alto no cambia: caben más sin que la
# portada crezca. El número baja hasta el data-muro-limite de la pista, y de
# ahí lo lee muro.js para pedir lo mismo al refrescar — así no hay dos cifras
# que se puedan separar.
EN_LA_LANDING = 12
POR_PAGINA = 24


# ------------------------------------------------------------------ ayudas

def _protegido_csrf():
    """Corta la petición si el token no calza. 400, no 403: no damos pistas."""
    if not csrf.valido(request.form.get("csrf")):
        abort(400, "Token de seguridad inválido. Recarga la página.")


def _limpiar(texto, maximo):
    """
    Deja el texto listo para guardar: sin espacios de sobra y en una sola
    línea.

    Los saltos de línea se colapsan a propósito. Un muro son tarjetas del
    mismo porte; con saltos libres, un mensaje de tres palabras repartido en
    diez líneas descuadra la grilla entera. Y evita el truco de mandar 200
    saltos de línea para ocupar media portada.
    """
    if texto is None:
        return ""
    return " ".join(str(texto).split())[:maximo]


def _vista(fila):
    """Agrega lo que la plantilla necesita y el SQL no da."""
    d = dict(fila)
    d["cuando"] = tiempo.fecha(d["created_at"])
    return d


def _publica(fila):
    """
    El mismo mensaje, pero solo con lo que la portada necesita y en tipos que
    sobreviven a JSON (nada de datetime crudo).

    No expone usuario_id ni el correo: el muro es público y ahí no tiene
    nada que hacer quién es esa persona en la base.
    """
    return {
        "id": fila["id"],
        "nickname": fila["nickname"],
        "mensaje": fila["mensaje"],
        "cuando": tiempo.fecha(fila["created_at"]),
    }


def _destino():
    """
    A dónde volver después de enviar.

    El formulario manda `volver=landing` o `volver=muro`, NUNCA una URL. Si
    aceptáramos una URL del formulario tendríamos un redirect abierto: basta
    con mandarle a alguien un enlace a nuestro propio sitio que rebote a una
    copia falsa del login para que el sitio preste su credibilidad al engaño.
    """
    if request.form.get("volver") == "muro":
        return url_for("muro")
    return url_for("home") + "#muro"


# ------------------------------------------------------------------ público

@app.route("/muro")
def muro():
    """
    El muro completo, paginado.

    Quien tiene sesión ve además SUS mensajes en cualquier estado, con la
    etiqueta correspondiente. Es la única forma de que alguien sepa que su
    deseo está esperando y no se perdió: para el resto del mundo, un mensaje
    pendiente y uno que nunca llegó se ven exactamente igual.
    """
    try:
        pagina = max(1, int(request.args.get("pagina", 1)))
    except (TypeError, ValueError):
        pagina = 1

    total = Muro.contar_aprobados()
    desde = (pagina - 1) * POR_PAGINA
    mensajes = [_vista(m) for m in Muro.aprobados(limite=POR_PAGINA, desde=desde)]

    usuario = session.get("usuario")
    mios = [_vista(m) for m in Muro.mios(usuario["id"])] if usuario else []

    return render_template(
        "muro.html",
        mensajes=mensajes,
        mios=mios,
        pagina=pagina,
        hay_mas=(desde + POR_PAGINA) < total,
        total=total,
        largo_mensaje=LARGO_MENSAJE,
        largo_nickname=LARGO_NICKNAME,
    )


@app.route("/api/v1/muro")
def api_muro():
    """
    Los últimos deseos aprobados, para la sección de la portada.

    Existe por lo mismo que /api/v1/agenda: que la landing pueda vivir en
    GitHub Pages sin quedarse con un muro escrito a mano. Y acá pesa además
    la moderación — un mensaje que el admin rechaza tiene que desaparecer de
    la portada sin esperar a que alguien vuelva a desplegar el sitio.

    ?limite=N recorta (1..50). Si la base no responde devolvemos 503 y el
    front deja lo que ya venía renderizado en el HTML.
    """
    try:
        limite = max(1, min(int(request.args.get("limite", EN_LA_LANDING)), 50))
    except (TypeError, ValueError):
        limite = EN_LA_LANDING
    try:
        return jsonify([_publica(m) for m in Muro.aprobados(limite=limite)])
    except Exception as e:
        app.logger.error("No se pudo leer el muro: %s", e)
        return jsonify({"error": "no disponible"}), 503


@app.route("/muro/enviar", methods=["POST"])
@requiere_sesion
def muro_enviar():
    _protegido_csrf()
    usuario = session["usuario"]

    mensaje = _limpiar(request.form.get("mensaje"), LARGO_MENSAJE)

    # Del formulario ya NO sale con qué nombre se firma: si llega un campo
    # `nickname`, se ignora. El nombre lo pone el modelo leyéndolo de la
    # cuenta (decisión de Seba), y de paso cierra que alguien firme como otra
    # persona mandando el campo a mano.

    if len(mensaje) < MINIMO_MENSAJE:
        flash("Escribe algo un poco más largo para el muro.", "error")
        return redirect(_destino())

    try:
        Muro.crear(usuario["id"], mensaje)
    except (SinNickname, CuentaBloqueada, YaTienePendiente, DemasiadosEnvios) as e:
        flash(str(e), "error")
        return redirect(_destino())
    except Exception as e:
        # Que no se caiga la portada por esto. El mensaje se perdió, pero la
        # persona lo sabe y puede reintentar.
        app.logger.error("No se pudo guardar el deseo del muro: %s", e)
        flash("No pudimos guardar tu mensaje. Inténtalo de nuevo en un rato.",
              "error")
        return redirect(_destino())

    flash("¡Gracias! Tu mensaje queda esperando aprobación y se publica apenas "
          "lo revisemos.", "info")
    return redirect(_destino())


# ------------------------------------------------------------------- admin

@app.route("/admin/muro")
@requiere_admin
def admin_muro():
    """
    La bandeja de moderación. Por defecto muestra lo pendiente, que es lo
    único que pide acción.
    """
    estado = request.args.get("estado", "pendiente")
    if estado not in ESTADOS and estado != "todos":
        estado = "pendiente"

    mensajes = [_vista(m) for m in
                Muro.listar_para_admin(None if estado == "todos" else estado)]

    return render_template(
        "admin_muro.html",
        mensajes=mensajes,
        estado=estado,
        conteo=Muro.resumen(),
        largo_motivo=LARGO_MOTIVO,
        csrf_token=csrf.token(),
    )


@app.route("/admin/muro/<int:mensaje_id>/estado", methods=["POST"])
@requiere_admin
def admin_muro_estado(mensaje_id):
    _protegido_csrf()

    if not Muro.obtener(mensaje_id):
        abort(404)

    nuevo = request.form.get("estado")
    if nuevo not in ESTADOS:
        abort(400, "Estado desconocido.")

    motivo = _limpiar(request.form.get("motivo"), LARGO_MOTIVO) or None
    Muro.cambiar_estado(mensaje_id, nuevo, session["usuario"]["id"], motivo)

    flash({"aprobado": "Publicado en el muro.",
           "rechazado": "Rechazado. No aparece en el sitio.",
           "pendiente": "Vuelve a la bandeja."}[nuevo], "info")

    return redirect(url_for("admin_muro",
                            estado=request.form.get("volver_estado", "pendiente")))


@app.route("/admin/muro/<int:mensaje_id>/eliminar", methods=["POST"])
@requiere_admin
def admin_muro_eliminar(mensaje_id):
    """
    Borrado de verdad, para lo que no debería quedar ni en la bandeja (el
    teléfono de un tercero, por ejemplo). Lo normal es rechazar: eso lo saca
    del sitio y deja el rastro de qué se revisó.
    """
    _protegido_csrf()
    if not Muro.obtener(mensaje_id):
        abort(404)
    Muro.eliminar(mensaje_id)
    flash("Mensaje eliminado.", "info")
    return redirect(url_for("admin_muro",
                            estado=request.form.get("volver_estado", "pendiente")))
