# ==========================================================================
# barra_controller.py — pedidos para retiro
#
#   público  /pedir                     la carta con un reloj
#            /pedido/<codigo>           el seguimiento, se refresca solo
#            /api/v1/pedido/<codigo>    lo mismo en JSON, para ese refresco
#   admin    /admin/barra               la cola del día y la configuración
#
# Pedir NO exige cuenta: nombre y celular, como en las actividades. Si hay
# sesión iniciada, el pedido queda asociado y los campos vienen llenos.
#
# El pago es al retirar. Mercado Pago entra después por este mismo módulo
# (la columna metodo_pago ya lo contempla), pero hasta que exista no se
# ofrece ningún botón de «pagar en línea»: un botón que no cobra es peor que
# no tenerlo.
# ==========================================================================

import re
import time
from datetime import date, timedelta

from flask import (abort, flash, jsonify, redirect, render_template, request,
                   session, url_for)

from flask_app import app
from flask_app.config import csrf, tiempo
from flask_app.config.negocio import NEGOCIO
from flask_app.controllers.actividad_controller import _telefono, _whatsapp
from flask_app.controllers.main_controller import requiere_admin, requiere_personal
from flask_app.models.barra_model import (ESTADOS, ESTADOS_VIVOS, ETIQUETA_PASO,
                                          PASOS,
                                          SIGUIENTE, TEXTO_ESTADO, Barra,
                                          PedidoRechazado)
from flask_app.models.carta_model import Carta

# El código va en la URL. Se valida la forma antes de ir a la base: una URL
# inventada no cuesta una consulta.
_CODIGO = re.compile(r"^PD-[A-Z2-9]{4}-[A-Z2-9]{4}$")

# Freno por conexión, en memoria, aparte del de registros: compartir ese
# contador haría que alguien que pidió tres cafés no pudiera crearse una
# cuenta. Seis pedidos por hora desde la misma IP es mucho más de lo que hace
# una casa; es poco para quien quiere llenar todas las franjas de la mañana.
PEDIDOS_POR_HORA = 6
_pedidos_por_ip = {}

# Los pedidos que esta persona hizo desde este navegador, para ofrecerle
# volver a su seguimiento si entra de nuevo a /pedir. Se guardan los últimos.
_MIS_PEDIDOS = "barra_mis_pedidos"
_MIS_PEDIDOS_MAX = 5

INTERVALOS = (10, 15, 20, 30, 45, 60)


# ------------------------------------------------------------------ ayudas

def _protegido_csrf():
    if not csrf.valido(request.form.get("csrf")):
        abort(400, "Token de seguridad inválido. Recarga la página.")


def _texto(valor, maximo):
    v = (valor or "").strip()
    return v[:maximo] if v else None


def _entero(valor, minimo, maximo, por_defecto):
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        return por_defecto
    return min(max(n, minimo), maximo)


def _bloqueado():
    limite = time.time() - 3600
    hechos = [t for t in _pedidos_por_ip.get(request.remote_addr, []) if t > limite]
    _pedidos_por_ip[request.remote_addr] = hechos
    return len(hechos) >= PEDIDOS_POR_HORA


def _sumar():
    _pedidos_por_ip.setdefault(request.remote_addr, []).append(time.time())


def _pedido_o_404(codigo):
    codigo = (codigo or "").upper()
    if not _CODIGO.match(codigo):
        abort(404)
    pedido = Barra.por_codigo(codigo)
    if not pedido:
        abort(404)
    return pedido


def _vista(p):
    """Lo que la página del pedido y su JSON necesitan, y nada más: ni el
    id interno ni el teléfono viajan al navegador por el JSON."""
    titulo, texto = TEXTO_ESTADO[p["estado"]]
    return {
        "codigo": p["codigo"],
        "estado": p["estado"],
        "titulo": titulo,
        "texto": texto,
        "paso": PASOS.index(p["estado"]) if p["estado"] in PASOS else None,
        "vivo": p["estado"] in ESTADOS_VIVOS,
        "cancelable": p["estado"] == "recibido",
        "afuera": bool(p["afuera_at"]),
        "pagado": bool(p["pagado_at"]),
        "franja_dia": tiempo.dia_relativo(p["franja_at"]),
        "franja_hora": tiempo.hora(p["franja_at"]),
    }


def _hoy_local():
    return tiempo.utc_a_local(tiempo.ahora_utc()).date()


# ---------------------------------------------------------------- público

def _render_pedir(cfg, previo=None, error=None, estado_http=200):
    carta = Barra.carta(cfg) if cfg and cfg["activo"] else []
    franjas = Barra.franjas_con_cupo(cfg) if cfg and cfg["activo"] else []

    if previo is None:
        u = session.get("usuario") or {}
        previo = {"nombre": u.get("nombre") or "", "telefono": u.get("telefono") or "",
                  "franja": "", "notas": "", "cant": {}}

    # La franja preseleccionada: la que eligió (si volvió con error y sigue
    # libre) o la primera con cupo. Preseleccionar ahorra un toque en el
    # caso más común, que es «lo antes posible».
    libres = [f["clave"] for f in franjas if f["libres"] > 0]
    if previo.get("franja") not in libres:
        previo["franja"] = libres[0] if libres else ""

    # Agrupadas por día para pintarlas en filas («Hoy», «Mañana»).
    dias = []
    for f in franjas:
        if not dias or dias[-1]["dia"] != f["dia"]:
            dias.append({"dia": f["dia"], "franjas": []})
        dias[-1]["franjas"].append(f)

    mis = [c for c in session.get(_MIS_PEDIDOS, [])]
    en_curso = []
    for c in mis[-3:]:
        p = Barra.por_codigo(c)
        if p and p["estado"] in ESTADOS_VIVOS:
            en_curso.append(_vista(p))

    return render_template(
        "pedir.html", cfg=cfg, carta=carta, dias=dias, hay_libres=bool(libres),
        previo=previo, error=error, en_curso=en_curso,
        csrf_token=csrf.token()), estado_http


@app.route("/pedir")
def pedir():
    try:
        cfg = Barra.config()
    except Exception as e:
        # Sin la migración la tabla no existe. Mejor «no estamos tomando
        # pedidos» que un error 500 en una página pública.
        app.logger.error("barra_config no responde (¿falta schema/barra_pedidos.sql?): %s", e)
        cfg = None
    return _render_pedir(cfg)


@app.route("/pedir", methods=["POST"])
def pedir_enviar():
    _protegido_csrf()
    cfg = Barra.config()
    if not cfg or not cfg["activo"]:
        flash("En este momento no estamos tomando pedidos.", "info")
        return redirect(url_for("pedir"))

    # Las cantidades llegan como cant_p-14 = 2. Se aceptan solo claves con
    # la forma esperada; qué existe y a qué precio lo decide el modelo.
    cant = {}
    for k, v in request.form.items():
        if k.startswith("cant_") and re.match(r"^[pc]-\d{1,10}$", k[5:]):
            n = _entero(v, 0, 99, 0)
            if n:
                cant[k[5:]] = n

    previo = {
        "nombre": _texto(request.form.get("nombre"), 60) or "",
        "telefono": (request.form.get("telefono") or "").strip()[:30],
        "franja": (request.form.get("franja") or "").strip()[:16],
        "notas": _texto(request.form.get("notas"), 200) or "",
        "cant": cant,
    }

    if _bloqueado():
        return _render_pedir(cfg, previo, "Demasiados pedidos desde esta conexión. "
                                          "Espera un rato o escríbenos.", 429)
    if not previo["nombre"]:
        return _render_pedir(cfg, previo, "¿A nombre de quién lo dejamos listo?", 400)
    telefono, error_tel = _telefono(previo["telefono"])
    if not previo["telefono"]:
        error_tel = "Necesitamos tu celular, por si hay que avisarte algo del pedido."
    if error_tel:
        return _render_pedir(cfg, previo, error_tel, 400)

    usuario = session.get("usuario")
    try:
        codigo = Barra.crear_pedido(
            nombre=previo["nombre"], telefono=telefono,
            franja_clave=previo["franja"], cantidades=cant,
            notas=previo["notas"] or None,
            usuario_id=usuario["id"] if usuario else None)
    except PedidoRechazado as e:
        return _render_pedir(cfg, previo, str(e), 409)

    _sumar()
    mis = session.get(_MIS_PEDIDOS, [])
    session[_MIS_PEDIDOS] = (mis + [codigo])[-_MIS_PEDIDOS_MAX:]
    return redirect(url_for("pedido", codigo=codigo))


@app.route("/pedido/<codigo>")
def pedido(codigo):
    p = _pedido_o_404(codigo)
    try:
        cfg = Barra.config()
    except Exception:
        cfg = None
    resp = app.make_response(render_template(
        "pedido.html", p=p, v=_vista(p), cfg=cfg, pasos=PASOS,
        etiqueta_paso=ETIQUETA_PASO, tiempo=tiempo,
        csrf_token=csrf.token()))
    # Trae la dirección de retiro: que no quede en ningún caché compartido.
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@app.route("/api/v1/pedido/<codigo>")
def api_pedido(codigo):
    p = _pedido_o_404(codigo)
    resp = jsonify(_vista(p))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/pedido/<codigo>/afuera", methods=["POST"])
def pedido_afuera(codigo):
    _protegido_csrf()
    p = _pedido_o_404(codigo)
    detalle = _texto(request.form.get("detalle"), 80)
    if Barra.avisar_afuera(p["codigo"], detalle):
        flash("¡Avisado! Ya vamos.", "info")
    else:
        flash("Ese pedido ya no está en curso.", "info")
    return redirect(url_for("pedido", codigo=p["codigo"]))


@app.route("/pedido/<codigo>/cancelar", methods=["POST"])
def pedido_cancelar(codigo):
    _protegido_csrf()
    p = _pedido_o_404(codigo)
    if Barra.cancelar_por_cliente(p["codigo"]):
        flash("Pedido cancelado. No hay nada que pagar.", "info")
    else:
        flash("Ya lo estamos preparando, así que no se puede cancelar desde "
              "acá. Escríbenos y lo vemos.", "error")
    return redirect(url_for("pedido", codigo=p["codigo"]))


# ------------------------------------------------------------------ admin

def _dia_pedido():
    """El día que se mira en el panel: ?dia=2026-10-03, o hoy."""
    try:
        return date.fromisoformat(request.values.get("dia", ""))
    except ValueError:
        return _hoy_local()


# Las etiquetas del panel son cortas y en tercera persona; los títulos de
# TEXTO_ESTADO le hablan al cliente («¡Listo para retirar!»).
ETIQUETA_ADMIN = {**ETIQUETA_PASO, "cancelado": "Cancelado", "no_retirado": "No vino"}


def _texto_dia(d, hoy):
    """«Hoy», «Ayer», «Mañana» o «mar 29»: lo que cabe en una pastilla."""
    delta = (d - hoy).days
    if delta in (-1, 0, 1):
        return {-1: "Ayer", 0: "Hoy", 1: "Mañana"}[delta]
    return f"{tiempo.DIAS[d.weekday()][:3]} {d.day}"


def _vista_admin(p):
    titulo = ETIQUETA_ADMIN[p["estado"]]
    sig = SIGUIENTE.get(p["estado"])
    texto_wsp = (f"Hola {p['nombre']}, te escribimos de {NEGOCIO['nombre']} "
                 f"por tu pedido {p['codigo']}.")
    return {
        **p,
        "titulo": titulo,
        "siguiente": sig,
        "hora": tiempo.hora(p["franja_at"]),
        "afuera_hace": tiempo.hora(p["afuera_at"]) if p["afuera_at"] else None,
        "wsp": _whatsapp(p["telefono"], texto_wsp),
    }


@app.route("/admin/barra")
@requiere_personal
def admin_barra():
    try:
        cfg = Barra.config()
    except Exception as e:
        app.logger.error("barra_config no responde: %s", e)
        cfg = None
    if not cfg:
        flash("Falta la tabla de pedidos para retiro: corre "
              "python instalar_base.py (ver README).", "error")
        return redirect(url_for("admin_inicio"))

    dia = _dia_pedido()
    hoy = _hoy_local()
    pedidos = [_vista_admin(p) for p in Barra.cola(dia)]

    grupos = []
    for p in pedidos:
        if not grupos or grupos[-1]["hora"] != p["hora"]:
            grupos.append({"hora": p["hora"], "pedidos": []})
        grupos[-1]["pedidos"].append(p)

    vivos = [p for p in pedidos if p["estado"] in ESTADOS_VIVOS]
    cobrado = sum(p["total_clp"] for p in pedidos if p["pagado_at"])
    por_cobrar = sum(p["total_clp"] for p in pedidos
                     if not p["pagado_at"] and p["estado"] in ESTADOS_VIVOS)

    # Los días navegables: unos atrás para revisar y los que se pueden pedir
    # hacia adelante.
    navegables = [hoy + timedelta(days=d) for d in range(-2, cfg["dias_adelante"] + 1)]

    return render_template(
        "admin_barra.html", cfg=cfg, dia=dia, hoy=hoy, grupos=grupos,
        vivos=len(vivos), cobrado=cobrado, por_cobrar=por_cobrar,
        total_pedidos=len(pedidos),
        navegables=[{"fecha": d, "texto": _texto_dia(d, hoy)} for d in navegables],
        firma=Barra.firma(dia)["firma"],
        categorias=Carta.categorias_de(NEGOCIO["slug"]) or [],
        intervalos=INTERVALOS, texto_estado=TEXTO_ESTADO,
        enlace_publico=url_for("pedir", _external=True),
        # El personal del mesón atiende la cola; abrir, cerrar y configurar
        # los pedidos es cosa del admin.
        es_admin=session["usuario"].get("rol") == "admin",
        csrf_token=csrf.token())


@app.route("/admin/barra/firma")
@requiere_personal
def admin_barra_firma():
    resp = jsonify(Barra.firma(_dia_pedido()))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/admin/barra/<int:pedido_id>/estado", methods=["POST"])
@requiere_personal
def admin_barra_estado(pedido_id):
    _protegido_csrf()
    estado = request.form.get("estado")
    if estado not in ESTADOS or not Barra.obtener(pedido_id):
        abort(400)
    Barra.cambiar_estado(pedido_id, estado)
    return redirect(url_for("admin_barra", dia=_dia_pedido().isoformat())
                    + f"#pedido-{pedido_id}")


@app.route("/admin/barra/<int:pedido_id>/pagado", methods=["POST"])
@requiere_personal
def admin_barra_pagado(pedido_id):
    _protegido_csrf()
    if not Barra.obtener(pedido_id):
        abort(404)
    Barra.marcar_pagado(pedido_id, request.form.get("pagado") == "1")
    return redirect(url_for("admin_barra", dia=_dia_pedido().isoformat())
                    + f"#pedido-{pedido_id}")


_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@app.route("/admin/barra/config", methods=["POST"])
@requiere_admin
def admin_barra_config():
    _protegido_csrf()
    f = request.form
    volver = redirect(url_for("admin_barra") + "#config")

    dias = {int(d) for d in f.getlist("dias") if d.isdigit() and 1 <= int(d) <= 7}
    inicio = (f.get("hora_inicio") or "").strip()[:5]
    fin = (f.get("hora_fin") or "").strip()[:5]
    if not _HORA.match(inicio) or not _HORA.match(fin):
        flash("Revisa las horas de apertura y cierre (formato 08:30).", "error")
        return volver
    if fin <= inicio:
        flash("La hora de cierre tiene que ser después de la de apertura.", "error")
        return volver

    intervalo = _entero(f.get("intervalo_min"), 5, 120, 15)
    if intervalo not in INTERVALOS:
        intervalo = 15

    # Categorías: todas marcadas se guarda como NULL («todas»), para que una
    # categoría que se cree mañana entre sola. Ninguna marcada no se acepta:
    # sería una barra abierta sin nada que pedir.
    propias = {c["id"] for c in (Carta.categorias_de(NEGOCIO["slug"]) or [])}
    elegidas = sorted({int(c) for c in f.getlist("categorias")
                       if c.isdigit() and int(c) in propias})
    incluir_combos = f.get("incluir_combos") == "1"
    if not elegidas and not incluir_combos:
        flash("Marca al menos una categoría del catálogo para pedir.", "error")
        return volver
    categorias = None if set(elegidas) == propias else elegidas
    if not elegidas:
        categorias = [0]  # solo combos: ninguna categoría real calza con 0

    activo = f.get("activo") == "1"
    if activo and not dias:
        flash("Para abrir los pedidos marca al menos un día de atención.", "error")
        return volver

    Barra.guardar_config({
        "activo": activo,
        "dias": dias,
        "hora_inicio": inicio,
        "hora_fin": fin,
        "intervalo_min": intervalo,
        "cupos_por_franja": _entero(f.get("cupos_por_franja"), 1, 50, 3),
        "max_items": _entero(f.get("max_items"), 1, 50, 6),
        "anticipacion_min": _entero(f.get("anticipacion_min"), 0, 240, 20),
        "dias_adelante": _entero(f.get("dias_adelante"), 0, 6, 1),
        "categorias": categorias,
        "incluir_combos": incluir_combos,
        "lugar_publico": _texto(f.get("lugar_publico"), 120),
        "direccion_retiro": _texto(f.get("direccion_retiro"), 200),
        "aviso": _texto(f.get("aviso"), 300),
    })
    flash("Pedidos abiertos: el enlace ya aparece en el catálogo." if activo
          else "Configuración guardada. Los pedidos están cerrados.", "info")
    return volver
