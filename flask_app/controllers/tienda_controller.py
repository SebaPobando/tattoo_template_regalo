# ==========================================================================
# tienda_controller.py — el catálogo de la tienda online
#
# La tienda es café en grano y accesorios: lo que se despacha en caja. Vive en
# Shopify, no en MySQL (la regla de siempre: si se sirve en taza va en MySQL,
# si se despacha en caja es de Shopify).
#
# Hasta ahora el precio estaba escrito a mano en DOS lugares del código —el
# catálogo de `tienda-productos.js` y el texto de la tarjeta en la landing—
# más Shopify, que es el que de verdad cobra. Tres copias del mismo número.
# El modo de fallar era el peor posible: subes un precio en Shopify, olvidas
# el código, y la persona ve un número y paga otro.
#
# Ahora el precio y el stock salen de Shopify y nada más. Lo que queda escrito
# a mano es el RESPALDO, para cuando Shopify no contesta.
# ==========================================================================

import json
from datetime import date, datetime, timedelta, timezone

from flask import abort, jsonify, render_template, request

from flask_app import app
from flask_app.config import shopify, tiempo
from flask_app.controllers.main_controller import requiere_admin
from flask_app.models.pedido_shopify_model import Pedido
from flask_app.models.usuario_model import Usuario, normalizar_email


def catalogo_para_plantilla():
    """
    Lo que reciben la landing y la ficha.

    Devuelve None —no una lista vacía— cuando no hay catálogo de Shopify, y
    la diferencia importa: None significa «usa el respaldo escrito a mano»,
    mientras que una lista vacía significaría «la colección existe y no tiene
    nada», que es una tienda vacía de verdad.

    Nunca lanza: una caída de Shopify no puede llevarse la portada por
    delante.
    """
    try:
        catalogo = shopify.catalogo()
    except Exception as e:      # pragma: no cover  (shopify.catalogo ya atrapa)
        app.logger.error("No se pudo leer el catálogo de Shopify: %s", e)
        return None
    # Los destacados del panel (borde de color, cinta, primeros en su
    # categoría). aplicar() devuelve copias y nunca lanza: sin la tabla o
    # sin base, la tienda sale igual, sin destacados.
    from flask_app.models.destacado_model import aplicar
    return aplicar(catalogo)


@app.route("/api/v1/tienda")
def api_tienda():
    """
    El catálogo en JSON.

    Existe por lo mismo que /api/v1/menu y /api/v1/agenda: el día que la
    landing vuelva a GitHub Pages no va a haber servidor que pinte las
    tarjetas, y este endpoint pasa a ser de dónde las saca.

    Hoy las páginas servidas por Flask NO lo usan: reciben el catálogo
    inyectado en el HTML, que llega sin un segundo viaje y sin que las
    tarjetas parpadeen al cargar.

    503 si no hay catálogo: es más honesto que una lista vacía, que el front
    leería como «no hay productos».
    """
    datos = catalogo_para_plantilla()
    if datos is None:
        return jsonify({"error": "catálogo no disponible",
                        "detalle": shopify.estado()}), 503
    return jsonify(datos)


@app.route("/api/v1/tienda/estado")
def api_tienda_estado():
    """
    Diagnóstico. Dice si Shopify está configurado, cuántos productos trajo,
    de cuándo es la copia que se está sirviendo y, si algo falló, qué falló.

    Es lo primero que hay que mirar cuando la tienda muestre precios viejos:
    `error` distingue «el token está malo» de «la colección no existe» de
    «no hay internet», que desde afuera se ven todos igual.
    """
    return jsonify(shopify.estado())


# ============================================================== el webhook
#
# Cuando alguien paga en el checkout de Shopify, Shopify avisa acá con el
# webhook «orders/paid». Esto es un REGISTRO de lo que se vendió, no una
# billetera: no suma ni descuenta saldo de puntos (ver el encabezado de
# pedido_shopify_model.py). Cómo darlo de alta en el admin de Shopify está
# en docs/TECNICO.md — necesita el sitio ya desplegado, con URL pública.


def _pesos_shopify(monto):
    """'12990.00' -> 12990. Los pedidos también se guardan en CLP enteros."""
    try:
        return int(round(float(monto)))
    except (TypeError, ValueError):
        return 0


def _fecha_shopify(iso):
    """
    '2026-09-27T10:15:00-03:00' -> datetime UTC sin tzinfo, para que calce
    con el resto de la base (ver config/tiempo.py). None si no se pudo leer
    — un pedido con una fecha rara igual se guarda, solo que sin ese dato.
    """
    if not iso:
        return None
    try:
        con_zona = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return con_zona.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def _nombre_shopify(orden):
    """
    El nombre de quien compró, aunque haya comprado sin cuenta. Prueba
    primero el cliente, después la dirección de facturación, después la de
    despacho — Shopify no siempre manda las tres, y el orden es el de más
    confiable a menos confiable.
    """
    for bloque in (orden.get("customer") or {}, orden.get("billing_address") or {},
                   orden.get("shipping_address") or {}):
        nombre = " ".join(p for p in [bloque.get("first_name"), bloque.get("last_name")]
                          if p).strip()
        if nombre:
            return nombre[:160]
    return None


@app.route("/webhooks/shopify/orders-paid", methods=["POST"])
def webhook_shopify_orden_pagada():
    """
    Contesta rápido y simple a propósito: Shopify espera 2xx en unos
    segundos: si no lo recibe, reintenta con backoff durante horas y termina
    desactivando el webhook. Nada de lo que pasa acá debería demorar ni
    depender de que algo más responda.
    """
    cuerpo = request.get_data()   # crudo, ANTES de parsear: la firma es sobre esto
    firma = request.headers.get("X-Shopify-Hmac-Sha256", "")

    if not shopify.verificar_firma_webhook(cuerpo, firma):
        app.logger.warning("Webhook de Shopify con firma inválida o sin configurar.")
        return jsonify({"error": "firma inválida"}), 401

    try:
        orden = json.loads(cuerpo)
    except ValueError:
        return jsonify({"error": "cuerpo ilegible"}), 400

    if not orden.get("id"):
        return jsonify({"error": "sin id de orden"}), 400

    correo = normalizar_email(orden.get("email") or orden.get("contact_email") or "")
    usuario = Usuario.por_email(correo) if correo else None

    items = [{
        "titulo": (li.get("title") or li.get("name") or "")[:200],
        "cantidad": li.get("quantity") or 0,
        "clp": _pesos_shopify(li.get("price")),
    } for li in (orden.get("line_items") or [])]

    guardado = Pedido.registrar({
        "shopify_order_id": orden["id"],
        "numero_orden": (orden.get("name") or orden.get("order_number") or None),
        "usuario_id": usuario["id"] if usuario else None,
        "correo_comprador": correo or "(sin correo)",
        "nombre_comprador": _nombre_shopify(orden),
        "monto_clp": _pesos_shopify(orden.get("total_price")
                                    or orden.get("current_total_price")),
        "moneda": (orden.get("currency") or "CLP")[:3],
        "items": items,
        "creado_shopify_at": _fecha_shopify(orden.get("created_at")),
    })
    if not guardado:
        app.logger.info("Webhook de Shopify repetido, la orden %s ya estaba.",
                        orden["id"])

    return jsonify({"ok": True}), 200


# ==================================================== reembolsos después

# Lo único que a este registro le importa del financial_status de Shopify:
# el resto de los valores posibles (pending, paid, voided, etc.) no cambian
# nada acá — un pedido sigue "pagado" hasta que se demuestre lo contrario.
_ESTADOS_FINANCIEROS = {
    "refunded": "reembolsado",
    "partially_refunded": "reembolso_parcial",
}


@app.route("/webhooks/shopify/orders-updated", methods=["POST"])
def webhook_shopify_orden_actualizada():
    """
    Shopify llama acá cada vez que algo cambia en una orden — no solo
    reembolsos: dirección, etiquetas, notas, todo dispara este mismo
    webhook. A esta app solo le importa `financial_status`: si dice
    "refunded" o "partially_refunded", actualiza el estado del pedido que
    ya tenía guardado (ver Pedido.actualizar_estado). Cualquier otro
    cambio se ignora a propósito — esto no sincroniza con Shopify, solo
    evita que un pedido devuelto siga viéndose como venta normal.

    Un pedido que no pasó antes por orders/paid no se crea acá: sin fila
    que actualizar, no hay nada que hacer.
    """
    cuerpo = request.get_data()
    firma = request.headers.get("X-Shopify-Hmac-Sha256", "")

    if not shopify.verificar_firma_webhook(cuerpo, firma):
        app.logger.warning(
            "Webhook de Shopify (orders/updated) con firma inválida o sin configurar.")
        return jsonify({"error": "firma inválida"}), 401

    try:
        orden = json.loads(cuerpo)
    except ValueError:
        return jsonify({"error": "cuerpo ilegible"}), 400

    if not orden.get("id"):
        return jsonify({"error": "sin id de orden"}), 400

    estado = _ESTADOS_FINANCIEROS.get(orden.get("financial_status"))
    if estado:
        Pedido.actualizar_estado(orden["id"], estado)

    return jsonify({"ok": True}), 200


# --------------------------------------------------------------- el panel

# Cuántos pedidos con detalle se listan. No es el universo del panel: las
# sumas por período salen de TODOS los pedidos (ver Pedido.para_totales), así
# que subir o bajar este número cambia cuántas filas se ven, nunca la plata.
CUANTOS_SE_LISTAN = 300


def _cuando(pedido):
    """
    La fecha con que se ubica un pedido en el tiempo: la de Shopify, o la de
    cuándo llegó el aviso si Shopify no la mandó. Mismo respaldo que usa cada
    fila para mostrar la hora, y por eso está acá una sola vez: si la lista y
    las sumas eligieran distinto, un pedido caería en dos períodos.
    """
    return pedido.get("creado_shopify_at") or pedido.get("recibido_at")


def _sumar_por_periodo(filas, periodo):
    """
    {clave: {total, total_clp, reembolsados}} sobre TODOS los pedidos.

    Lo reembolsado no suma plata pero sí cuenta como pedido, igual que en la
    pastilla de arriba (ver Pedido.resumen, que explica por qué).
    """
    sumas = {}
    for f in filas:
        clave, _ = tiempo.periodo_de(_cuando(f), periodo)
        d = sumas.setdefault(clave, {"total": 0, "total_clp": 0, "reembolsados": 0})
        d["total"] += 1
        if f.get("estado") == "reembolsado":
            d["reembolsados"] += 1
        else:
            d["total_clp"] += int(f.get("monto_clp") or 0)
    return sumas


def _agrupar(pedidos, totales, periodo):
    """
    Lo que pinta el panel: [{etiqueta, pedidos, total, total_clp,
    reembolsados, de_mas}], en el orden en que ya vienen los pedidos (más
    reciente primero).

    `pedidos` trae el detalle que se va a mostrar y viene recortado;
    `totales` son todos, con lo justo para sumar. La plata sale SIEMPRE de
    `totales`: si saliera de la lista recortada, un período con más pedidos
    de los que caben mostraría un total más chico que el real sin avisar.
    `de_mas` es justamente cuántos quedaron sin listar en ese período.
    """
    sumas = _sumar_por_periodo(totales, periodo)
    grupos = []
    clave_actual = object()   # nada puede ser igual a esto en la primera vuelta
    for p in pedidos:
        clave, etiqueta = tiempo.periodo_de(_cuando(p), periodo)
        if clave != clave_actual:
            suma = sumas.get(clave, {"total": 0, "total_clp": 0, "reembolsados": 0})
            grupos.append({"etiqueta": etiqueta, "pedidos": [], **suma})
            clave_actual = clave
        grupos[-1]["pedidos"].append(p)

    for g in grupos:
        g["de_mas"] = max(0, g["total"] - len(g["pedidos"]))
    return grupos


@app.route("/admin/pedidos")
@requiere_admin
def admin_pedidos():
    """
    El período viaja en la URL (?periodo=mes) y no en la sesión: así el panel
    se puede compartir o dejar marcado mostrando el mismo corte. Un valor que
    no existe cae en «día» en vez de reventar — es un parámetro que cualquiera
    puede escribir a mano.
    """
    periodo = request.args.get("periodo", "dia")
    if periodo not in tiempo.PERIODOS:
        periodo = "dia"

    return render_template("admin_pedidos.html",
                           grupos=_agrupar(Pedido.recientes(CUANTOS_SE_LISTAN),
                                           Pedido.para_totales(), periodo),
                           periodo=periodo,
                           periodos=tiempo.PERIODOS,
                           resumen=Pedido.resumen(),
                           tiempo=tiempo,
                           url_pedido_shopify=shopify.url_admin_pedido)


# ============================================================ /admin/ventas
#
# El panel de pedidos es la bitacora —que se vendio y a quien—. Esto es la
# otra pregunta: como va el negocio. Los graficos se dibujan como SVG armado
# en el servidor, sin libreria de graficos ni JS: la geometria se calcula aca
# y la plantilla solo pinta lo que recibe. Asi la pagina funciona con el JS
# apagado y no entra una dependencia nueva al proyecto.

# Cuantos periodos se muestran hacia atras en cada corte. Son ventanas
# distintas a proposito: 14 dias se leen bien, 14 anios no dicen nada.
VENTANA = {"dia": 14, "semana": 12, "mes": 12, "anio": 5}


def _periodos_hacia_atras(periodo, cuantos):
    """
    Las claves y etiquetas de los ultimos `cuantos` periodos, del mas viejo
    al mas nuevo, terminando en el de hoy.

    Se generan desde el calendario y NO desde los pedidos: un mes sin ventas
    tiene que aparecer como una barra en cero. Si la serie saliera solo de
    los pedidos que existen, marzo y mayo quedarian pegados y el grafico
    diria que no hubo un abril malo, sino que abril no existio.
    """
    hoy = tiempo.utc_a_local(tiempo.ahora_utc()).date()
    vistos, salida = set(), []
    paso = {"dia": 1, "semana": 7}.get(periodo)

    for i in range(cuantos * (31 if periodo == "mes" else 366 if periodo == "anio" else 1)):
        if paso:
            f = hoy - timedelta(days=i * paso)
        elif periodo == "mes":
            mes = hoy.month - i
            anio = hoy.year + (mes - 1) // 12
            f = date(anio, (mes - 1) % 12 + 1, 1)
        else:
            f = date(hoy.year - i, 1, 1)

        clave, etiqueta = tiempo.periodo_de(
            datetime(f.year, f.month, f.day, 12), periodo)
        if clave not in vistos:
            vistos.add(clave)
            salida.append((clave, etiqueta, _etiqueta_corta(f, periodo)))
            if len(salida) == cuantos:
                break
    return list(reversed(salida))


def _etiqueta_corta(f, periodo):
    """
    La version corta que va bajo el eje: «25/9», «sep», «2025».

    Existe porque la etiqueta larga («noviembre 2025», «Semana del 7 al 13 de
    septiembre») no cabe bajo una barra y recortarla por caracteres deja
    cosas como «noviembre 2». La larga se sigue usando en el tooltip y en la
    tabla, donde si hay espacio.
    """
    if periodo == "dia" or periodo == "semana":
        return f"{f.day}/{f.month}"
    if periodo == "mes":
        return tiempo.MESES[f.month - 1][:3]
    return str(f.year)


def _serie_de_ventas(filas, periodo):
    """
    [{clave, etiqueta, clp, pedidos}] para la ventana del corte elegido, del
    periodo mas viejo al mas nuevo. Los periodos sin ventas van en cero.
    """
    sumas = _sumar_por_periodo(filas, periodo)
    vacio = {"total": 0, "total_clp": 0, "reembolsados": 0}
    return [{"clave": c, "etiqueta": e, "corta": corta,
             "clp": sumas.get(c, vacio)["total_clp"],
             "pedidos": sumas.get(c, vacio)["total"]}
            for c, e, corta in _periodos_hacia_atras(periodo, VENTANA[periodo])]


def _variacion(actual, anterior):
    """
    Cuanto cambio, en porcentaje, respecto del periodo anterior.

    None cuando no hay con que comparar (el periodo anterior fue cero): un
    "+100%" sobre cero no significa nada y es peor que no decir nada. La
    plantilla muestra un guion en ese caso.
    """
    if not anterior:
        return None
    return round((actual - anterior) / anterior * 100)


def _ranking_productos(filas, claves_ventana, periodo, tope=8):
    """
    Que se vendio mas dentro de la ventana, por unidades, con la plata que
    dejo cada producto.

    Solo mira los pedidos de la ventana y deja fuera los reembolsados, para
    que cuadre con lo que dicen los graficos de al lado. Se queda con los
    `tope` primeros: un ranking de treinta productos ya no es un grafico.
    """
    por_titulo = {}
    for f in filas:
        if f.get("estado") == "reembolsado":
            continue
        if tiempo.periodo_de(_cuando(f), periodo)[0] not in claves_ventana:
            continue
        for it in (f.get("items") or []):
            titulo = (it.get("titulo") or "").strip() or "(sin nombre)"
            d = por_titulo.setdefault(titulo, {"titulo": titulo, "unidades": 0, "clp": 0})
            d["unidades"] += int(it.get("cantidad") or 0)
            d["clp"] += int(it.get("cantidad") or 0) * int(it.get("clp") or 0)

    ordenado = sorted(por_titulo.values(),
                      key=lambda d: (-d["unidades"], -d["clp"], d["titulo"]))
    return ordenado[:tope]


# ------------------------------------------------- la geometria de los SVG
#
# Se calcula aca y no en la plantilla porque Jinja no es lugar para hacer
# cuentas: en el servidor esto se puede leer y probar.

ALTO_GRAFICO = 190          # solo el area de las barras; las etiquetas van fuera
GRUESO_MAXIMO = 24          # una barra nunca llena su carril: el aire es del diseno
REDONDEO = 4                # la punta redondeada; el pie queda cuadrado en la base
SEPARACION = 2              # el aire entre barras vecinas, en color de fondo


def _escala_limpia(maximo):
    """
    El techo del eje, redondeado a un numero que se pueda leer (1.000, 2.500,
    50.000) en vez del maximo crudo. 0 cuando no hay ventas todavia.
    """
    if maximo <= 0:
        return 0
    from math import log10
    magnitud = 10 ** int(log10(maximo))
    # Pasos finos a proposito: con (1, 2, 5, 10) un maximo de 62.000 saltaba
    # a un techo de 100.000 y las barras quedaban aplastadas contra el piso.
    for paso in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 7.5, 10):
        techo = magnitud * paso
        if techo >= maximo:
            return int(techo)
    return int(magnitud * 10)


def _columnas(serie, ancho=640):
    """
    Las barras verticales del grafico de ventas en el tiempo, ya con sus
    coordenadas. Devuelve tambien las marcas del eje y para que la plantilla
    no calcule nada.
    """
    techo = _escala_limpia(max((d["clp"] for d in serie), default=0))
    carril = ancho / len(serie) if serie else ancho
    grueso = min(GRUESO_MAXIMO, max(6, carril - SEPARACION * 2))

    barras = []
    for i, d in enumerate(serie):
        alto = (d["clp"] / techo * ALTO_GRAFICO) if techo else 0
        barras.append({
            "x": round(i * carril + (carril - grueso) / 2, 2),
            "y": round(ALTO_GRAFICO - alto, 2),
            "ancho": round(grueso, 2),
            "alto": round(alto, 2),
            "centro": round(i * carril + carril / 2, 2),
            "etiqueta": d["etiqueta"],
            "corta": d["corta"],
            "clp": d["clp"],
            "pedidos": d["pedidos"],
            # La ultima es el periodo en curso: va destacada porque es la que
            # se esta mirando, y ademas esta incompleta.
            "en_curso": i == len(serie) - 1,
        })

    marcas = []
    if techo:
        for parte in (0, 0.5, 1):
            marcas.append({"y": round(ALTO_GRAFICO * (1 - parte), 2),
                           "valor": int(techo * parte)})
    return {"barras": barras, "marcas": marcas, "techo": techo,
            "ancho": ancho, "alto": ALTO_GRAFICO}


def _barras_productos(productos, ancho=640):
    """Las barras horizontales del ranking, en fraccion del mas vendido."""
    tope = max((p["unidades"] for p in productos), default=0)
    return [dict(p, fraccion=round(p["unidades"] / tope * 100, 2) if tope else 0)
            for p in productos]


@app.route("/admin/ventas")
@requiere_admin
def admin_ventas():
    """
    El dashboard. Mismo corte de tiempo que /admin/pedidos y por el mismo
    parametro (?periodo=), asi que se puede saltar de una pagina a la otra
    sin perder lo que se estaba mirando.
    """
    periodo = request.args.get("periodo", "mes")
    if periodo not in tiempo.PERIODOS:
        periodo = "mes"

    filas = Pedido.para_dashboard()
    serie = _serie_de_ventas(filas, periodo)

    # El periodo en curso y el anterior, para los numeros de arriba.
    actual = serie[-1] if serie else {"clp": 0, "pedidos": 0, "etiqueta": ""}
    previo = serie[-2] if len(serie) > 1 else {"clp": 0, "pedidos": 0, "etiqueta": ""}
    ticket = round(actual["clp"] / actual["pedidos"]) if actual["pedidos"] else 0
    ticket_previo = round(previo["clp"] / previo["pedidos"]) if previo["pedidos"] else 0

    claves_ventana = {d["clave"] for d in serie}
    productos = _ranking_productos(filas, claves_ventana, periodo)

    return render_template(
        "admin_ventas.html",
        periodo=periodo, periodos=tiempo.PERIODOS,
        serie=serie, grafico=_columnas(serie),
        productos=_barras_productos(productos),
        actual=actual, previo=previo,
        ticket=ticket,
        var_clp=_variacion(actual["clp"], previo["clp"]),
        var_pedidos=_variacion(actual["pedidos"], previo["pedidos"]),
        var_ticket=_variacion(ticket, ticket_previo),
        hay_datos=any(d["clp"] or d["pedidos"] for d in serie),
    )


# ---------------------------------------------------------------------------
# Destacados de la tienda: el admin elige qué productos de Shopify resaltar,
# con qué color y qué cinta. Ver models/destacado_model.py.
# ---------------------------------------------------------------------------

def _protegido_csrf():
    from flask_app.config import csrf
    if not csrf.valido(request.form.get("csrf")):
        abort(400, "Token de seguridad inválido. Recarga la página.")


@app.route("/admin/tienda")
@requiere_admin
def admin_tienda():
    from flask_app.config import csrf
    from flask_app.models.destacado_model import (COLOR_POR_DEFECTO, COLORES,
                                                  CINTA_POR_DEFECTO, LARGO_CINTA,
                                                  NOMBRE_PESTANA, Destacado)
    try:
        destacados = Destacado.todos()
    except Exception as e:
        app.logger.error("tienda_destacados no responde: %s", e)
        from flask import flash, redirect, url_for
        flash("Falta la tabla de destacados: corre  python instalar_base.py  (ver README).", "error")
        return redirect(url_for("admin_inicio"))

    catalogo = None
    try:
        catalogo = shopify.catalogo()
    except Exception as e:      # pragma: no cover
        app.logger.error("No se pudo leer el catálogo de Shopify: %s", e)

    productos = []
    for i, p in enumerate(catalogo or []):
        d = destacados.get(p["id"])
        productos.append({
            "handle": p["id"], "nombre": p["name"], "imagen": p.get("imagen"),
            "categoria": p.get("categoria"), "agotado": p.get("agotado"),
            "destacado": bool(d),
            "color": d["color"] if d else COLOR_POR_DEFECTO,
            "cinta": d["cinta"] if d else CINTA_POR_DEFECTO,
            "orden": d["orden"] if d else 0,
        })
    # Destacados cuyo producto ya no viene en el catálogo (lo sacaron de la
    # colección o le cambiaron el handle en Shopify). Se muestran para que
    # el admin sepa que existen y los pueda quitar.
    en_catalogo = {p["handle"] for p in productos}
    huerfanos = [d for h, d in destacados.items() if catalogo is not None and h not in en_catalogo]

    return render_template(
        "admin_tienda.html", productos=productos, huerfanos=huerfanos,
        sin_catalogo=catalogo is None, colores=COLORES, largo_cinta=LARGO_CINTA,
        nombre_especiales=NOMBRE_PESTANA, total=len(destacados),
        csrf_token=csrf.token())


@app.route("/admin/tienda", methods=["POST"])
@requiere_admin
def admin_tienda_guardar():
    from flask import flash, redirect, url_for
    from flask_app.models.destacado_model import (COLOR_POR_DEFECTO, COLORES,
                                                  CINTA_POR_DEFECTO, LARGO_CINTA,
                                                  Destacado)
    _protegido_csrf()
    f = request.form
    # Solo se aceptan handles que existen: los del catálogo de ahora y los
    # que ya estaban destacados. Un handle inventado por POST no entra.
    try:
        catalogo = shopify.catalogo() or []
    except Exception:
        catalogo = []
    validos = {p["id"] for p in catalogo} | set(Destacado.todos())

    elegidos = []
    for h in dict.fromkeys(f.getlist("destacar")):
        if h not in validos:
            continue
        color = f.get(f"color__{h}")
        cinta = " ".join((f.get(f"cinta__{h}") or "").split())[:LARGO_CINTA]
        try:
            orden = max(0, min(999, int(f.get(f"orden__{h}") or 0)))
        except ValueError:
            orden = 0
        elegidos.append({"handle": h,
                         "color": color if color in COLORES else COLOR_POR_DEFECTO,
                         "cinta": cinta or CINTA_POR_DEFECTO, "orden": orden})
    Destacado.guardar(elegidos)
    flash(f"Tienda guardada: {len(elegidos)} producto{'s' if len(elegidos) != 1 else ''} "
          f"destacado{'s' if len(elegidos) != 1 else ''}.", "success")
    return redirect(url_for("admin_tienda"))
