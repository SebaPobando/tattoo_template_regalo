# ==========================================================================
# vale_controller.py — vales de regalo y gift cards
#
#   público   /vale/<codigo>              el vale con su QR. Cualquiera lo ve;
#                                         solo el personal ve «Canjear vale».
#   personal  /vale/<codigo>/canjear      POST: lo canjea (admin o barista)
#             /admin/vales                emitir, emitir para un evento, y la
#                                         lista de TODOS los vales
#             /admin/vales/lote/<id>      la hoja de QR de un evento, para
#                                         imprimir
#   admin     anular y revertir un canje
#
# Escanear el QR NO canjea. El QR lleva a la página del vale, y en el
# celular del barista (con sesión iniciada) esa página muestra el botón. Un
# enlace que canjeara con solo abrirse se gastaría al revisarlo, al abrirlo
# desde el historial o al reenviarlo por error.
# ==========================================================================

import re
from datetime import date
from urllib.parse import quote

from flask import (abort, flash, redirect, render_template, request, session,
                   url_for)

from flask_app import app
from flask_app.config import csrf, qr, tiempo
from flask_app.config.negocio import NEGOCIO
from flask_app.controllers.actividad_controller import _telefono, _whatsapp
from flask_app.controllers.main_controller import (es_personal, requiere_admin,
                                                   requiere_personal)
from flask_app.models.vale_model import (ESTADOS, MAX_POR_LOTE, NOMBRE_TIPO,
                                         TIPOS, CanjeRechazado, Vale)

_CODIGO = re.compile(r"^VL-[A-Z2-9]{4}-[A-Z2-9]{4}$")


def _protegido_csrf():
    if not csrf.valido(request.form.get("csrf")):
        abort(400, "Token de seguridad inválido. Recarga la página.")


def _texto(valor, maximo):
    v = " ".join((valor or "").split())
    return v[:maximo] if v else None


def _monto(valor):
    try:
        n = int(str(valor or "").strip().replace(".", "").replace("$", "").replace(" ", ""))
    except ValueError:
        return None
    return n if n > 0 else None


def _fecha(valor):
    try:
        return date.fromisoformat((valor or "").strip())
    except ValueError:
        return None


def _hoy():
    return tiempo.utc_a_local(tiempo.ahora_utc()).date()


def _vale_o_404(codigo):
    codigo = (codigo or "").upper()
    if not _CODIGO.match(codigo):
        abort(404)
    v = Vale.por_codigo(codigo)
    if not v:
        abort(404)
    return v


def _quien(nombre, nick):
    return (nick or nombre or "").strip() or None


def _mensaje_whatsapp(v, url):
    saludo = f"¡Hola {v['para_nombre']}!" if v.get("para_nombre") else "¡Hola!"
    if v["tipo"] == "giftcard":
        cuerpo = f"Te regalaron una gift card de {NEGOCIO['nombre']}: {v['valido_por']}."
    else:
        cuerpo = f"{NEGOCIO['nombre']} te regala un vale: {v['valido_por']}."
    vence = (f" Vale hasta el {tiempo.fecha(v['vence_at'])}." if v.get("vence_at") else "")
    return f"{saludo} {cuerpo}{vence} Muéstralo en el mesón: {url}"


def _vista(v):
    """El vale con lo que las plantillas necesitan ya en palabras."""
    d = dict(v)
    d["nombre_tipo"] = NOMBRE_TIPO[v["tipo"]]
    d["url"] = url_for("vale", codigo=v["codigo"], _external=True)
    d["vence_txt"] = tiempo.fecha(v["vence_at"]) if v["vence_at"] else None
    d["emitido_txt"] = f"{tiempo.dia_relativo(v['emitido_at'])} {tiempo.hora(v['emitido_at'])}"
    d["canjeado_txt"] = tiempo.largo(v["canjeado_at"]) if v["canjeado_at"] else None
    d["emitido_quien"] = _quien(v.get("emitido_nombre"), v.get("emitido_nick"))
    d["canjeado_quien"] = _quien(v.get("canjeado_nombre"), v.get("canjeado_nick"))
    mensaje = _mensaje_whatsapp(v, d["url"])
    # Con número va directo a esa conversación; sin número, WhatsApp pregunta
    # a quién mandarlo.
    d["wsp"] = (_whatsapp(v["para_telefono"], mensaje) if v.get("para_telefono")
                else f"https://wa.me/?text={quote(mensaje)}")
    return d


# ---------------------------------------------------------------- público

@app.route("/vale/<codigo>")
def vale(codigo):
    v = _vista(_vale_o_404(codigo))
    usuario = session.get("usuario")
    resp = app.make_response(render_template(
        "vale.html", v=v, qr_svg=qr.svg(v["url"]),
        es_personal=es_personal(usuario),
        es_admin=(usuario or {}).get("rol") == "admin",
        recien=request.args.get("nuevo") == "1",
        csrf_token=csrf.token()))
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@app.route("/vale/<codigo>/canjear", methods=["POST"])
@requiere_personal
def vale_canjear(codigo):
    _protegido_csrf()
    v = _vale_o_404(codigo)
    try:
        Vale.canjear(v["codigo"], session["usuario"]["id"])
        flash(f"Vale canjeado. Entrega: {v['valido_por']}.", "success")
    except CanjeRechazado as e:
        flash(str(e), "error")
    return redirect(url_for("vale", codigo=v["codigo"]))


# ------------------------------------------------------------- personal

@app.route("/admin/vales")
@requiere_personal
def admin_vales():
    try:
        resumen = Vale.resumen()
    except Exception as e:
        app.logger.error("vales no responde: %s", e)
        flash("Falta la tabla de vales: corre  python instalar_base.py  (ver README).", "error")
        return redirect(url_for("admin_inicio"))
    tipo = request.args.get("tipo") if request.args.get("tipo") in TIPOS else None
    estado = request.args.get("estado") if request.args.get("estado") in ESTADOS else None
    busca = _texto(request.args.get("busca"), 60)
    vales = [_vista(v) for v in Vale.listar(tipo, estado, busca)]
    return render_template(
        "admin_vales.html", vales=vales, resumen=resumen, tipo=tipo,
        estado=estado, busca=busca or "", nombre_tipo=NOMBRE_TIPO,
        es_admin=session["usuario"].get("rol") == "admin",
        hoy=_hoy().isoformat(), max_lote=MAX_POR_LOTE,
        csrf_token=csrf.token())


@app.route("/admin/vales/emitir", methods=["POST"])
@requiere_personal
def admin_vales_emitir():
    _protegido_csrf()
    f = request.form
    volver = redirect(url_for("admin_vales") + "#emitir")
    tipo = f.get("tipo")
    if tipo not in TIPOS:
        abort(400)
    valido_por = _texto(f.get("valido_por"), 160)
    if not valido_por:
        flash("Escribe qué incluye el vale (por ejemplo «1 caja de cartuchos»).", "error")
        return volver

    telefono = None
    if (f.get("para_telefono") or "").strip():
        telefono, error = _telefono(f.get("para_telefono"))
        if error:
            flash(error.replace("por ahí te mandamos el voucher", "para mandarle el vale"), "error")
            return volver

    monto = None
    vence = None
    if tipo == "giftcard":
        monto = _monto(f.get("monto_pagado_clp"))
        if not monto:
            flash("Anota cuánto se pagó por la gift card.", "error")
            return volver
    elif (f.get("vence") or "").strip():
        vence = _fecha(f.get("vence"))
        if not vence or vence < _hoy():
            flash("La fecha de vencimiento tiene que ser hoy o después.", "error")
            return volver

    codigo = Vale.emitir(
        tipo=tipo, valido_por=valido_por,
        emitido_por=session["usuario"]["id"],
        para_nombre=_texto(f.get("para_nombre"), 80), para_telefono=telefono,
        motivo=_texto(f.get("motivo"), 120), comprador=_texto(f.get("comprador"), 80),
        monto_pagado_clp=monto, vence=vence)
    return redirect(url_for("vale", codigo=codigo, nuevo=1))


@app.route("/admin/vales/lote", methods=["POST"])
@requiere_personal
def admin_vales_lote():
    _protegido_csrf()
    f = request.form
    volver = redirect(url_for("admin_vales") + "#evento")
    nombre = _texto(f.get("nombre"), 120)
    valido_por = _texto(f.get("valido_por"), 160)
    try:
        cantidad = int(f.get("cantidad") or 0)
    except ValueError:
        cantidad = 0
    if not nombre or not valido_por:
        flash("Ponle nombre al evento y escribe qué incluye cada vale.", "error")
        return volver
    if not 1 <= cantidad <= MAX_POR_LOTE:
        flash(f"Se pueden emitir entre 1 y {MAX_POR_LOTE} vales por evento.", "error")
        return volver
    vence = None
    if (f.get("vence") or "").strip():
        vence = _fecha(f.get("vence"))
        if not vence or vence < _hoy():
            flash("La fecha de vencimiento tiene que ser hoy o después.", "error")
            return volver
    lote_id = Vale.emitir_lote(nombre=nombre, cantidad=cantidad, valido_por=valido_por,
                               emitido_por=session["usuario"]["id"], vence=vence)
    flash(f"{cantidad} vales emitidos para «{nombre}». Imprime la hoja y recórtalos.", "success")
    return redirect(url_for("admin_vales_lote_ver", lote_id=lote_id))


@app.route("/admin/vales/lote/<int:lote_id>")
@requiere_personal
def admin_vales_lote_ver(lote_id):
    lote, vales = Vale.del_lote(lote_id)
    if not lote:
        abort(404)
    vales = [_vista(v) for v in vales]
    for v in vales:
        v["qr"] = qr.svg(v["url"], borde=1)
    return render_template("admin_vale_lote.html", lote=lote, vales=vales,
                           canjeados=sum(1 for v in vales if v["estado"] == "canjeado"))


# ------------------------------------------------------------------ admin

@app.route("/admin/vales/<int:vale_id>/anular", methods=["POST"])
@requiere_admin
def admin_vales_anular(vale_id):
    _protegido_csrf()
    v = Vale.obtener(vale_id)
    if not v:
        abort(404)
    if Vale.anular(vale_id):
        flash("Vale anulado: ese QR ya no se puede canjear.", "info")
    else:
        flash("Ese vale ya se canjeó o ya estaba anulado.", "error")
    return redirect(url_for("vale", codigo=v["codigo"]))


@app.route("/admin/vales/<int:vale_id>/revertir", methods=["POST"])
@requiere_admin
def admin_vales_revertir(vale_id):
    _protegido_csrf()
    v = Vale.obtener(vale_id)
    if not v:
        abort(404)
    if Vale.revertir_canje(vale_id):
        flash("Canje revertido: el vale vuelve a estar disponible.", "info")
    return redirect(url_for("vale", codigo=v["codigo"]))
