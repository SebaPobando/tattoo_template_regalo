# ==========================================================================
# promo_controller.py — las promos de la portada
#
# El admin carga una promo con su plazo y la landing muestra un banner con el
# tiempo que le queda. Cuando el plazo se cumple, el banner se retira solo.
#
# Todo lo de administración va detrás de @requiere_admin. Ojo con el orden de
# los decoradores: @app.route va PRIMERO y debajo el que protege. Al revés,
# Flask registra la vista sin protección.
#
# Lo público es una sola función, `promo_para_plantilla()`, que usa home().
# No hay fetch: el banner se inyecta ya resuelto en el HTML, igual que el
# catálogo de la tienda. Con un fetch la portada se pintaría primero sin
# banner y el banner caería encima medio segundo después, empujando el
# contenido que la persona ya empezó a leer.
# ==========================================================================

from flask import (abort, flash, jsonify, redirect, render_template, request,
                   session, url_for)

from flask_app import app
from flask_app.config import csrf, tiempo
from flask_app.controllers.main_controller import requiere_admin
from flask_app.models.promo_model import (LARGO_BAJADA, LARGO_BOTON,
                                          LARGO_DESTINO, LARGO_NOMBRE,
                                          MINIMO_NOMBRE, Promo)

# Un plazo máximo, para que un dedo torpe en el año del formulario no deje un
# contador de 300 días en la portada. No es una regla de negocio: es un tope
# de cordura, y el mensaje de error dice exactamente eso.
DIAS_MAX = 120


# ------------------------------------------------------------------ ayudas

def _protegido_csrf():
    """Corta la petición si el token no calza. 400, no 403: no damos pistas."""
    if not csrf.valido(request.form.get("csrf")):
        abort(400, "Token de seguridad inválido. Recarga la página.")


def _texto(valor, maximo):
    v = (valor or "").strip()
    return v[:maximo] if v else None


def _destino_propio(valor):
    """
    El destino del botón tiene que ser del propio sitio.

    Se acepta un ancla ('#tienda') o una ruta ('/muro'), y nada más. Una URL
    cualquiera sería un redirect abierto, y un 'javascript:' pegado acá
    terminaría dentro de un atributo del HTML de la portada. Mismo cuidado
    que el `volver` del muro y que el afiche de las actividades.

    '//evil.cl' se rechaza a propósito: el navegador lo lee como una URL
    absoluta con el mismo esquema, no como una ruta.
    """
    v = _texto(valor, LARGO_DESTINO)
    if not v:
        return None
    if v.startswith("//") or not v.startswith(("#", "/")):
        return False
    return v


def _datos_del_formulario():
    """
    Devuelve (datos, error). Si error no es None, el controlador avisa y no
    guarda nada.
    """
    nombre = _texto(request.form.get("nombre"), LARGO_NOMBRE)
    if not nombre or len(nombre) < MINIMO_NOMBRE:
        return None, "La promo necesita un nombre."

    inicio = tiempo.local_a_utc(request.form.get("inicio"))
    fin = tiempo.local_a_utc(request.form.get("fin"))
    if not inicio or not fin:
        return None, "Revisa las fechas: alguna no se entiende."
    if fin <= inicio:
        return None, "La promo no puede terminar antes de empezar."
    if (fin - inicio).days > DIAS_MAX:
        return None, f"El plazo no puede pasar de {DIAS_MAX} días."

    destino = _destino_propio(request.form.get("boton_destino"))
    if destino is False:
        return None, ("El destino del botón tiene que ser una sección de este "
                      "sitio, como #tienda o /muro.")

    texto_boton = _texto(request.form.get("boton_texto"), LARGO_BOTON)
    # Un botón sin destino no lleva a ninguna parte y un destino sin texto no
    # se ve. O los dos, o ninguno: es más claro que pintar medio botón.
    if bool(texto_boton) != bool(destino):
        return None, "Para el botón hace falta el texto y el destino, o ninguno."

    try:
        prioridad = int(request.form.get("prioridad") or 0)
    except (TypeError, ValueError):
        prioridad = 0

    return {
        "nombre": nombre,
        "bajada": _texto(request.form.get("bajada"), LARGO_BAJADA),
        "boton_texto": texto_boton,
        "boton_destino": destino,
        "inicio_at": inicio,
        "fin_at": fin,
        "prioridad": max(-99, min(99, prioridad)),
    }, None


def promo_para_plantilla():
    """
    Lo que recibe la landing: la promo vigente o None.

    Nunca lanza. Una promo es decoración de la portada; que MySQL tropiece
    mientras se lee no puede llevarse la página por delante. Mismo criterio
    que el catálogo de la tienda y que la agenda.
    """
    try:
        return Promo.vigente()
    except Exception as e:
        app.logger.error("No se pudo leer la promo para la landing: %s", e)
        return None


# ---------------------------------------------------------------- lo público

@app.route("/api/v1/promo")
def api_promo():
    """
    La promo vigente en JSON.

    Existe por lo mismo que /api/v1/menu, /api/v1/agenda y /api/v1/tienda: el
    día que la landing vuelva a Pages no va a haber servidor que pinte el
    banner y este endpoint pasa a ser de dónde sale.

    204 cuando no hay nada vigente, y no un 404 ni un objeto vacío: «no hay
    promo» es una respuesta correcta, no un error ni un recurso que falta.
    """
    promo = promo_para_plantilla()
    if not promo:
        return ("", 204)
    return jsonify({
        "id": promo["id"],
        "nombre": promo["nombre"],
        "bajada": promo["bajada"],
        "boton_texto": promo["boton_texto"],
        "boton_destino": promo["boton_destino"],
        "segundos": max(0, int(promo["segundos"] or 0)),
    })


# --------------------------------------------------------------- el panel

@app.route("/admin/promos")
@requiere_admin
def admin_promos():
    return render_template("admin_promos.html",
                           promos=Promo.todas(),
                           tiempo=tiempo,
                           largo_nombre=LARGO_NOMBRE,
                           largo_bajada=LARGO_BAJADA,
                           largo_boton=LARGO_BOTON,
                           largo_destino=LARGO_DESTINO)


@app.route("/admin/promos/crear", methods=["POST"])
@requiere_admin
def admin_promos_crear():
    _protegido_csrf()
    datos, error = _datos_del_formulario()
    if error:
        flash(error, "error")
        return redirect(url_for("admin_promos"))

    datos["activa"] = 1
    datos["creada_por"] = (session.get("usuario") or {}).get("id")
    Promo.crear(datos)
    flash(f"Promo «{datos['nombre']}» cargada.", "exito")
    return redirect(url_for("admin_promos"))


@app.route("/admin/promos/<int:promo_id>", methods=["POST"])
@requiere_admin
def admin_promos_actualizar(promo_id):
    _protegido_csrf()
    if not Promo.una(promo_id):
        abort(404)
    datos, error = _datos_del_formulario()
    if error:
        flash(error, "error")
        return redirect(url_for("admin_promos"))
    Promo.actualizar(promo_id, datos)
    flash("Promo actualizada.", "exito")
    return redirect(url_for("admin_promos"))


@app.route("/admin/promos/<int:promo_id>/interruptor", methods=["POST"])
@requiere_admin
def admin_promos_interruptor(promo_id):
    """
    Bajar la promo al tiro, o reponerla con su plazo intacto.

    Es el botón para cuando se acaba el café del 2x1 a media tarde: sacar el
    banner en ese momento sin editar fechas ni entender estados.
    """
    _protegido_csrf()
    promo = Promo.una(promo_id)
    if not promo:
        abort(404)
    encender = request.form.get("encender") == "1"
    Promo.interruptor(promo_id, encender)
    flash("Promo repuesta." if encender else "Promo bajada de la portada.",
          "exito")
    return redirect(url_for("admin_promos"))


@app.route("/admin/promos/<int:promo_id>/eliminar", methods=["POST"])
@requiere_admin
def admin_promos_eliminar(promo_id):
    _protegido_csrf()
    if not Promo.una(promo_id):
        abort(404)
    Promo.eliminar(promo_id)
    flash("Promo eliminada.", "exito")
    return redirect(url_for("admin_promos"))
