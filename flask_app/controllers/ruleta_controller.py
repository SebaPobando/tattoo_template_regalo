# ==========================================================================
# ruleta_controller.py — la ruleta de premios
#
#   público  /ruleta/<codigo>            la ruleta de UN giro habilitado
#            /ruleta/<codigo>/girar      POST: sortea (una sola vez) y responde
#                                        dónde tiene que caer
#   personal /admin/ruleta               habilitar giros e historial (admin y
#                                        barista); los premios, la
#                                        configuración y anular, solo el admin
#
# No hay /ruleta a secas, ni botón en la portada: la ruleta existe solo para
# quien compró en el local, y ese giro lo habilita alguien desde el panel.
# Ver models/ruleta_model.py.
# ==========================================================================

import re

from flask import (abort, flash, jsonify, redirect, render_template, request,
                   session, url_for)

from flask_app import app
from flask_app.config import csrf, qr, tiempo
from flask_app.config.negocio import NEGOCIO
from flask_app.controllers.main_controller import (es_personal, requiere_admin,
                                                   requiere_personal)
from flask_app.models.ruleta_model import (LARGO_PREMIO, MAX_GAJOS, MIN_GAJOS,
                                           GiroNoValido, Ruleta,
                                           RuletaIncompleta, _color_texto,
                                           geometria)

_CODIGO = re.compile(r"^RL-[A-Z2-9]{4}-[A-Z2-9]{4}$")


def _protegido_csrf():
    if not csrf.valido(request.form.get("csrf")):
        abort(400, "Token de seguridad inválido. Recarga la página.")


def _giro_o_404(codigo):
    codigo = (codigo or "").upper()
    if not _CODIGO.match(codigo):
        abort(404)
    g = Ruleta.por_codigo(codigo)
    if not g:
        abort(404)
    return g


def _entero(valor, minimo, maximo, por_defecto):
    try:
        n = int(str(valor).strip().replace(".", "").replace("$", ""))
    except (TypeError, ValueError):
        return por_defecto
    return min(max(n, minimo), maximo)


# ---------------------------------------------------------------- público

@app.route("/ruleta/<codigo>")
def ruleta_giro(codigo):
    g = _giro_o_404(codigo)
    # La ruleta que se muestra: la foto del momento si ya se giró (aunque
    # después hayan cambiado los premios), la de ahora si no.
    premios = g["premios_ruleta"] or Ruleta.premios()
    rueda = geometria(premios)
    if g["estado"] == "girado" and rueda["n"]:
        rotacion = -rueda["gajos"][g["gajo_indice"]]["centro"]
    elif rueda["n"]:
        rotacion = -rueda["gajos"][0]["centro"]
    else:
        rotacion = 0
    cfg = Ruleta.config() or {}
    resp = app.make_response(render_template(
        "ruleta.html", g=g, rueda=rueda, rotacion=round(rotacion, 3),
        premios=premios, monto_minimo=cfg.get("monto_minimo"),
        es_personal=es_personal(session.get("usuario")),
        csrf_token=csrf.token()))
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@app.route("/ruleta/<codigo>/girar", methods=["POST"])
def ruleta_girar(codigo):
    if not csrf.valido(request.form.get("csrf")):
        return jsonify({"error": "Recarga la página e inténtalo de nuevo."}), 400
    codigo = (codigo or "").upper()
    if not _CODIGO.match(codigo):
        abort(404)
    try:
        r = Ruleta.girar(codigo)
    except GiroNoValido as e:
        return jsonify({"error": str(e)}), 410
    resp = jsonify(r)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ------------------------------------------------------------------ admin

@app.route("/admin/ruleta")
@requiere_personal
def admin_ruleta():
    try:
        cfg = Ruleta.config()
    except Exception as e:
        app.logger.error("ruleta_config no responde: %s", e)
        cfg = None
    if not cfg:
        flash("Falta la tabla de la ruleta: corre  python instalar_base.py  (ver README).", "error")
        return redirect(url_for("admin_inicio"))

    premios = Ruleta.premios()
    rueda = geometria(premios)
    historial = Ruleta.historial()

    # El giro recién habilitado, con su QR. Viaja como ?nuevo=<codigo> para
    # que recargar la página no habilite otro.
    nuevo = None
    codigo_nuevo = (request.args.get("nuevo") or "").upper()
    if _CODIGO.match(codigo_nuevo):
        g = Ruleta.por_codigo(codigo_nuevo)
        if g and g["estado"] == "pendiente":
            url = url_for("ruleta_giro", codigo=g["codigo"], _external=True)
            nuevo = {**g, "url": url, "qr": qr.svg(url),
                     "vence": tiempo.hora(g["vence_at"])}

    for h in historial:
        h["cuando"] = f"{tiempo.dia_relativo(h['creado_at'])} {tiempo.hora(h['creado_at'])}"
        h["vence"] = tiempo.hora(h["vence_at"])

    return render_template(
        "admin_ruleta.html", cfg=cfg, premios=premios,
        rueda=rueda,
        rotacion=round(-rueda["gajos"][0]["centro"], 3) if premios else 0,
        probabilidades=Ruleta.probabilidades(premios),
        lista=len(premios) >= MIN_GAJOS, historial=historial, nuevo=nuevo,
        colores=len(NEGOCIO["ruleta"]["colores"]),
        paleta=[{"fondo": c, "tinta": _color_texto(c)} for c in NEGOCIO["ruleta"]["colores"]],
        min_gajos=MIN_GAJOS, max_gajos=MAX_GAJOS, largo_premio=LARGO_PREMIO,
        es_admin=session["usuario"].get("rol") == "admin",
        csrf_token=csrf.token())


@app.route("/admin/ruleta/habilitar", methods=["POST"])
@requiere_personal
def admin_ruleta_habilitar():
    _protegido_csrf()
    referencia = (request.form.get("referencia") or "").strip()[:80] or None
    try:
        codigo = Ruleta.habilitar(session["usuario"]["id"], referencia)
    except RuletaIncompleta as e:
        flash(str(e), "error")
        return redirect(url_for("admin_ruleta") + "#premios")
    return redirect(url_for("admin_ruleta", nuevo=codigo))


@app.route("/admin/ruleta/premios", methods=["POST"])
@requiere_admin
def admin_ruleta_premios():
    _protegido_csrf()
    volver = redirect(url_for("admin_ruleta") + "#premios")
    premios = [" ".join((p or "").split()) for p in request.form.getlist("premio")]
    if any(not p for p in premios):
        flash("Hay gajos sin premio. Escríbelos todos o quita los que sobran "
              "(si un gajo no regala nada, escribe «Sigue participando»).", "error")
        return volver
    if any(len(p) > LARGO_PREMIO for p in premios):
        flash(f"Cada premio puede tener hasta {LARGO_PREMIO} letras: tiene que caber en el gajo.", "error")
        return volver
    if not MIN_GAJOS <= len(premios) <= MAX_GAJOS:
        flash(f"La ruleta tiene que tener entre {MIN_GAJOS} y {MAX_GAJOS} gajos.", "error")
        return volver
    Ruleta.guardar_premios(premios)
    flash(f"Ruleta guardada: {len(premios)} gajos, cada uno con 1 de {len(premios)} de probabilidad.", "info")
    return volver


@app.route("/admin/ruleta/config", methods=["POST"])
@requiere_admin
def admin_ruleta_config():
    _protegido_csrf()
    Ruleta.guardar_config(
        _entero(request.form.get("monto_minimo"), 0, 10_000_000, 40000),
        _entero(request.form.get("vence_min"), 5, 24 * 60, 30))
    flash("Configuración de la ruleta guardada.", "info")
    return redirect(url_for("admin_ruleta") + "#config")


@app.route("/admin/ruleta/giros/<int:giro_id>/entregado", methods=["POST"])
@requiere_personal
def admin_ruleta_entregado(giro_id):
    _protegido_csrf()
    Ruleta.marcar_entregado(giro_id, request.form.get("entregado") == "1")
    return redirect(url_for("admin_ruleta") + f"#giro-{giro_id}")


@app.route("/admin/ruleta/giros/<int:giro_id>/anular", methods=["POST"])
@requiere_admin
def admin_ruleta_anular(giro_id):
    _protegido_csrf()
    if Ruleta.anular(giro_id):
        flash("Giro anulado: ese enlace ya no gira.", "info")
    else:
        flash("Ese giro ya se giró: no se puede anular.", "error")
    return redirect(url_for("admin_ruleta") + "#historial")
