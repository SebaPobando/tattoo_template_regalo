# ==========================================================================
# barra_model.py — pedidos para retiro
#
# Alguien pide desde la página, elige una franja («hoy 10:15») y pasa a
# buscarlo. Paga al retirar. Ver schema/barra_pedidos.sql para el porqué de
# cada columna.
#
# Tres ideas que valen para todo el archivo:
#
# 1. EL PRECIO LO PONE EL SERVIDOR. El formulario manda «2 del producto 14»,
#    nunca «2 a $3.500». El precio sale de la base en el momento de pedir y
#    se copia al pedido. Un precio que viene del navegador se edita con F12.
#
# 2. LAS FRANJAS NO SE GUARDAN, SE CALCULAN. Salen de la configuración (días,
#    horario, intervalo) y del reloj. Lo único que se guarda es la franja que
#    eligió cada pedido; los cupos libres son una cuenta, igual que en las
#    actividades.
#
# 3. TOMAR UNA FRANJA VA EN UNA TRANSACCIÓN CON FOR UPDATE. Sobre la fila de
#    configuración: dos vecinos que piden el último cupo de las 10:15 en el
#    mismo segundo no pueden entrar los dos. Bloquear esa fila serializa
#    TODOS los pedidos, y está bien: en una barra chica entra uno cada
#    tanto, no cien por segundo.
# ==========================================================================

import secrets
import time
from datetime import datetime, timedelta

from flask_app import DB
from flask_app.config import tiempo
from flask_app.config.mysqlconnection import connectToMySQL, transaccion
from flask_app.config.negocio import NEGOCIO, en_puntos

# Los que todavía están en juego: el cliente los puede seguir en su página y
# el panel los muestra en la cola.
ESTADOS_VIVOS = ("recibido", "preparando", "listo")

# Todos los estados posibles, en el orden en que se recorren.
ESTADOS = ("recibido", "preparando", "listo", "entregado",
           "cancelado", "no_retirado")

# Una franja la ocupa todo pedido que no se canceló. 'entregado' y
# 'no_retirado' también: esa media hora ya se usó (o se preparó para alguien
# que no vino), y liberarla a posteriori no le sirve a nadie.
_OCUPA_SQL = "estado <> 'cancelado'"

# El botón principal de cada pedido en el panel: a qué estado lo lleva.
SIGUIENTE = {"recibido": "preparando", "preparando": "listo", "listo": "entregado"}

# Cuántos pedidos vivos puede tener un mismo teléfono a la vez. Alguien que
# pide para él y para la pareja en dos pedidos, bien; diez pedidos desde el
# mismo número es alguien jugando con el formulario y llenando las franjas.
MAX_VIVOS_POR_TELEFONO = 2

# Lo que ve el cliente en la página de su pedido. Vive acá y no en la
# plantilla porque lo leen dos lugares —la página y el JSON con que se
# refresca sola— y dos copias se separan a la primera corrección.
TEXTO_ESTADO = {
    "recibido":    ("Pedido recibido",
                    "Lo tenemos. Esta página se actualiza sola cuando empecemos a juntarlo."),
    "preparando":  ("Preparando tu pedido",
                    "Lo estamos juntando en el mesón."),
    "listo":       ("¡Listo para retirar!",
                    "Te esperamos. Si ya llegaste, avísanos con el botón de abajo."),
    "entregado":   ("Entregado",
                    "Gracias por venir. Que lo disfrutes."),
    "cancelado":   ("Pedido cancelado",
                    "No hay nada que pagar. Puedes hacer otro cuando quieras."),
    "no_retirado": ("No se retiró",
                    "Pasó la hora y no alcanzamos a verte. Si fue un error, escríbenos."),
}

# Los pasos de la barrita de progreso de la página del pedido.
PASOS = ("recibido", "preparando", "listo", "entregado")
ETIQUETA_PASO = {"recibido": "Recibido", "preparando": "Preparando",
                 "listo": "Listo", "entregado": "Entregado"}

# Mismo alfabeto que los vouchers: sin I, O, 0 ni 1, porque se dicta.
_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class PedidoRechazado(Exception):
    """Un pedido que no se puede tomar, con un mensaje para mostrarle a la
    persona tal cual. Se levanta en vez de devolver False para que el
    controlador no lo pueda ignorar por descuido."""


# ------------------------------------------------------------- utilidades

def _nuevo_codigo():
    bloque = lambda: "".join(secrets.choice(_ALFABETO) for _ in range(4))
    return f"PD-{bloque()}-{bloque()}"


def _a_hhmm(valor):
    """
    PyMySQL devuelve una columna TIME como timedelta (porque TIME puede
    valer '-838:59:59', que no es una hora del día). Para un horario de
    apertura siempre está entre 00:00 y 23:59.
    """
    if isinstance(valor, timedelta):
        minutos = int(valor.total_seconds()) // 60
        return f"{minutos // 60:02d}:{minutos % 60:02d}"
    return str(valor or "")[:5]


def _minutos(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _config_vista(fila):
    """La fila cruda de barra_config, convertida a tipos con los que se
    puede trabajar sin parsear en cada lugar."""
    dias = {int(d) for d in (fila["dias"] or "").split(",") if d.strip().isdigit()}
    categorias = None
    if fila.get("categorias"):
        categorias = [int(c) for c in fila["categorias"].split(",") if c.strip().isdigit()]
    return {
        "activo": bool(fila["activo"]),
        "dias": dias,
        "hora_inicio": _a_hhmm(fila["hora_inicio"]),
        "hora_fin": _a_hhmm(fila["hora_fin"]),
        "intervalo_min": int(fila["intervalo_min"]),
        "cupos_por_franja": int(fila["cupos_por_franja"]),
        "max_items": int(fila["max_items"]),
        "anticipacion_min": int(fila["anticipacion_min"]),
        "dias_adelante": int(fila["dias_adelante"]),
        "categorias": categorias,
        "incluir_combos": bool(fila["incluir_combos"]),
        "lugar_publico": fila.get("lugar_publico"),
        "direccion_retiro": fila.get("direccion_retiro"),
        "aviso": fila.get("aviso"),
    }


# Cache del interruptor para el pie de página. El enlace «Pedir para retirar»
# sale en el footer de TODAS las páginas; preguntarle a MySQL en cada una por
# una fila que cambia un par de veces al mes es gasto puro. Un minuto de
# atraso al prender o apagar no le importa a nadie. Con varios workers de
# gunicorn cada uno tiene su copia: se ponen al día solos en ese minuto.
_cache_activo = {"valor": False, "hasta": 0.0}
_CACHE_SEGUNDOS = 60


def barra_activa():
    """¿Se están tomando pedidos? Para mostrar u ocultar los enlaces
    públicos. Nunca lanza: si la tabla no existe todavía (no se corrió la
    migración) la respuesta es simplemente no."""
    ahora = time.monotonic()
    if ahora < _cache_activo["hasta"]:
        return _cache_activo["valor"]
    try:
        filas = connectToMySQL(DB).query_db(
            "SELECT activo FROM barra_config WHERE id = 1")
        valor = bool(filas and filas[0]["activo"])
    except Exception:
        valor = False
    _cache_activo.update(valor=valor, hasta=ahora + _CACHE_SEGUNDOS)
    return valor


def generar_franjas(cfg, ahora_utc=None):
    """
    Las franjas que se pueden elegir ahora, ANTES de mirar los cupos.

    Se arman en hora de Chile, porque «abro a las 8» es una hora de reloj de
    pared: tiene que seguir siendo las 8 el día después del cambio de
    horario. Recién al final se pasan a UTC para comparar con la base.

    Cada franja: {"clave": "2026-10-03T10:15" (local, es lo que viaja en el
    formulario), "inicio_utc", "dia" ("Hoy", "Mañana", "sábado 3 de
    octubre"), "hora" ("10:15"), "fecha" (date local)}.
    """
    ahora_utc = ahora_utc or tiempo.ahora_utc()
    ahora_local = tiempo.utc_a_local(ahora_utc)
    desde = ahora_local + timedelta(minutes=cfg["anticipacion_min"])
    intervalo = timedelta(minutes=max(cfg["intervalo_min"], 5))
    ini = _minutos(cfg["hora_inicio"])
    fin = _minutos(cfg["hora_fin"])

    franjas = []
    for d in range(cfg["dias_adelante"] + 1):
        fecha = ahora_local.date() + timedelta(days=d)
        if fecha.isoweekday() not in cfg["dias"]:
            continue
        base = datetime(fecha.year, fecha.month, fecha.day, tzinfo=tiempo.CHILE)
        t = base + timedelta(minutes=ini)
        limite = base + timedelta(minutes=fin)
        while t < limite:
            if t >= desde:
                clave = t.strftime("%Y-%m-%dT%H:%M")
                inicio_utc = tiempo.local_a_utc(clave)
                franjas.append({
                    "clave": clave,
                    "inicio_utc": inicio_utc,
                    "dia": tiempo.dia_relativo(inicio_utc),
                    "hora": t.strftime("%H:%M"),
                    "fecha": fecha,
                })
            t += intervalo
    return franjas


def _ocupacion(cur_o_none, desde_utc, hasta_utc):
    """{franja_at: pedidos que la ocupan} entre dos instantes."""
    q = f"""
        SELECT franja_at, COUNT(*) AS n FROM barra_pedidos
        WHERE franja_at BETWEEN %s AND %s AND {_OCUPA_SQL}
        GROUP BY franja_at
    """
    if cur_o_none is None:
        filas = connectToMySQL(DB).query_db(q, (desde_utc, hasta_utc)) or []
    else:
        cur_o_none.execute(q, (desde_utc, hasta_utc))
        filas = cur_o_none.fetchall()
    return {f["franja_at"]: f["n"] for f in filas}


class Barra:

    # ---------------------------------------------------------- configuración

    @staticmethod
    def config():
        filas = connectToMySQL(DB).query_db("SELECT * FROM barra_config WHERE id = 1")
        return _config_vista(filas[0]) if filas else None

    @staticmethod
    def guardar_config(datos):
        """`datos` ya validado por el controlador."""
        datos = dict(datos)
        datos["dias"] = ",".join(str(d) for d in sorted(datos["dias"]))
        cats = datos.get("categorias")
        datos["categorias"] = ",".join(str(c) for c in cats) if cats else None
        connectToMySQL(DB).query_db("""
            UPDATE barra_config SET
              activo = %(activo)s, dias = %(dias)s,
              hora_inicio = %(hora_inicio)s, hora_fin = %(hora_fin)s,
              intervalo_min = %(intervalo_min)s,
              cupos_por_franja = %(cupos_por_franja)s,
              max_items = %(max_items)s,
              anticipacion_min = %(anticipacion_min)s,
              dias_adelante = %(dias_adelante)s,
              categorias = %(categorias)s,
              incluir_combos = %(incluir_combos)s,
              lugar_publico = %(lugar_publico)s,
              direccion_retiro = %(direccion_retiro)s,
              aviso = %(aviso)s
            WHERE id = 1
        """, datos)
        # Quien lo acaba de prender quiere ver el enlace al tiro, no en un
        # minuto. (Solo en este worker; los otros se ponen al día solos.)
        _cache_activo["hasta"] = 0.0

    # --------------------------------------------------------------- franjas

    @staticmethod
    def franjas_con_cupo(cfg, ahora_utc=None):
        """Las franjas de generar_franjas() con sus cupos libres. Incluye las
        llenas (con `libres` = 0) para que el formulario las muestre
        tachadas: ver que las 10:00 se llenó explica por qué no aparece."""
        franjas = generar_franjas(cfg, ahora_utc)
        if not franjas:
            return []
        ocupadas = _ocupacion(None, franjas[0]["inicio_utc"], franjas[-1]["inicio_utc"])
        for f in franjas:
            f["libres"] = max(cfg["cupos_por_franja"] - ocupadas.get(f["inicio_utc"], 0), 0)
        return franjas

    # ----------------------------------------------------------------- carta

    @staticmethod
    def carta(cfg):
        """
        Lo que se puede pedir, agrupado como la carta:
            [{"id", "label", "items": [{"clave": "p-14", "nombre", "desc",
                                         "clp", "lp"}]}]

        Solo la marca principal y solo lo disponible. La clave lleva el tipo
        («p-» producto, «c-» combo) porque los ids de las dos tablas se
        pisan: el producto 3 y el combo 3 son cosas distintas.

        El segundo precio (precio_individual_clp, el de las pizzas) no se
        ofrece: esto es la barra de la cafetería, y un producto con dos
        tamaños pedido sin decir cuál es un problema en el mesón.
        """
        filas = connectToMySQL(DB).query_db("""
            SELECT p.id, p.nombre, p.descripcion, p.precio_clp,
                   c.id AS categoria_id, c.slug AS categoria_slug,
                   c.nombre AS categoria_nombre
            FROM productos p
            JOIN categorias c ON c.id = p.categoria_id
            JOIN marcas m     ON m.id = p.marca_id
            WHERE m.slug = %(marca)s AND m.activa = TRUE
              AND p.disponible = TRUE
            ORDER BY c.orden, c.nombre, p.orden, p.nombre
        """, {"marca": NEGOCIO["slug"]}) or []

        permitidas = set(cfg["categorias"]) if cfg["categorias"] else None
        grupos, indice = [], {}
        for f in filas:
            if permitidas is not None and f["categoria_id"] not in permitidas:
                continue
            slug = f["categoria_slug"]
            if slug not in indice:
                indice[slug] = {"id": slug, "label": f["categoria_nombre"], "items": []}
                grupos.append(indice[slug])
            indice[slug]["items"].append({
                "clave": f"p-{f['id']}", "tipo": "producto", "id": f["id"],
                "nombre": f["nombre"], "desc": f["descripcion"],
                "clp": f["precio_clp"], "lp": en_puntos(f["precio_clp"]),
            })

        if cfg["incluir_combos"]:
            from flask_app.models.combo_model import Combo
            combos = Combo.vigentes_para_carta(NEGOCIO["slug"])
            if combos:
                grupos.insert(0, {"id": "packs", "label": "Packs", "items": [{
                    "clave": f"c-{c['id']}", "tipo": "combo", "id": c["id"],
                    "nombre": c["nombre"],
                    "desc": "Incluye: " + ", ".join(
                        f"{i['cantidad']}× {i['producto_nombre']}" for i in c["items"]),
                    "clp": c["precio_clp"], "lp": en_puntos(c["precio_clp"]),
                } for c in combos]})
        return grupos

    @staticmethod
    def armar_items(cfg, cantidades):
        """
        De {"p-14": 2, "c-3": 1} a la lista de ítems con nombre y precio de
        la BASE. Lo que no está en la carta pedible (apagado, de otra marca,
        de una categoría que la barra no ofrece, inventado) se descarta en
        silencio... salvo que deje el pedido vacío, y eso sí se avisa.
        """
        disponibles = {it["clave"]: it for g in Barra.carta(cfg) for it in g["items"]}
        items = []
        for clave, cant in cantidades.items():
            it = disponibles.get(clave)
            if not it or cant <= 0:
                continue
            items.append({
                "producto_id": it["id"] if it["tipo"] == "producto" else None,
                "combo_id": it["id"] if it["tipo"] == "combo" else None,
                "nombre": it["nombre"], "precio_clp": it["clp"], "cantidad": cant,
            })
        if not items:
            raise PedidoRechazado("Elige al menos un producto del catálogo.")
        unidades = sum(i["cantidad"] for i in items)
        if unidades > cfg["max_items"]:
            raise PedidoRechazado(
                f"Por pedido podemos preparar hasta {cfg['max_items']} "
                f"unidades. Si necesitas más, escríbenos.")
        return items

    # ----------------------------------------------------------------- pedir

    @staticmethod
    def crear_pedido(*, nombre, telefono, franja_clave, cantidades,
                     notas=None, usuario_id=None):
        """
        Toma la franja y guarda el pedido. Devuelve el código.

        Levanta PedidoRechazado con un mensaje para la persona si la barra
        está cerrada, la franja ya no se ofrece o se llenó, el teléfono ya
        tiene demasiados pedidos vivos, o el pedido viene vacío o es muy
        grande.
        """
        # Los ítems se arman FUERA de la transacción: leen la carta, que no
        # se bloquea, y si el pedido viene vacío no vale la pena tomar el
        # candado para rechazarlo.
        cfg_previa = Barra.config()
        if not cfg_previa or not cfg_previa["activo"]:
            raise PedidoRechazado("En este momento no estamos tomando pedidos.")
        items = Barra.armar_items(cfg_previa, cantidades)
        total = sum(i["precio_clp"] * i["cantidad"] for i in items)

        with transaccion(DB) as cur:
            # El candado. Ver la nota 3 del encabezado.
            cur.execute("SELECT * FROM barra_config WHERE id = 1 FOR UPDATE")
            cfg = _config_vista(cur.fetchone())
            if not cfg["activo"]:
                raise PedidoRechazado("En este momento no estamos tomando pedidos.")

            # La franja se busca entre las que se ofrecen AHORA, con el reloj
            # de este instante: una pestaña abierta desde las 9 no puede
            # pedir para las 9:15 a las 9:14.
            ofrecidas = {f["clave"]: f for f in generar_franjas(cfg)}
            franja = ofrecidas.get(franja_clave)
            if not franja:
                raise PedidoRechazado("Esa hora ya no está disponible. Elige otra.")

            ocupadas = _ocupacion(cur, franja["inicio_utc"], franja["inicio_utc"])
            if ocupadas.get(franja["inicio_utc"], 0) >= cfg["cupos_por_franja"]:
                raise PedidoRechazado(
                    f"Se llenó la franja de las {franja['hora']}. Elige otra hora.")

            vivos_sql = ", ".join(f"'{e}'" for e in ESTADOS_VIVOS)
            cur.execute(f"""
                SELECT COUNT(*) AS n FROM barra_pedidos
                WHERE telefono = %s AND estado IN ({vivos_sql})
            """, (telefono,))
            if cur.fetchone()["n"] >= MAX_VIVOS_POR_TELEFONO:
                raise PedidoRechazado(
                    "Ya tienes pedidos en curso con ese número. Espera a "
                    "retirarlos o escríbenos si necesitas cambiar algo.")

            codigo = None
            for _ in range(6):
                candidato = _nuevo_codigo()
                cur.execute("SELECT id FROM barra_pedidos WHERE codigo = %s", (candidato,))
                if not cur.fetchone():
                    codigo = candidato
                    break
            if not codigo:
                raise RuntimeError("No pude generar un código de pedido libre.")

            cur.execute("""
                INSERT INTO barra_pedidos
                  (codigo, usuario_id, nombre, telefono, franja_at,
                   metodo_pago, total_clp, notas,
                   estado_at, creado_at)
                VALUES (%s, %s, %s, %s, %s, 'al_retirar', %s, %s,
                        UTC_TIMESTAMP(), UTC_TIMESTAMP())
            """, (codigo, usuario_id, nombre, telefono, franja["inicio_utc"],
                  total, notas))
            pedido_id = cur.lastrowid
            for it in items:
                cur.execute("""
                    INSERT INTO barra_pedido_items
                      (pedido_id, producto_id, combo_id, nombre, precio_clp, cantidad)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (pedido_id, it["producto_id"], it["combo_id"], it["nombre"],
                      it["precio_clp"], it["cantidad"]))
        return codigo

    # ---------------------------------------------------------------- lectura

    @staticmethod
    def _con_items(pedidos):
        if not pedidos:
            return []
        ids = [p["id"] for p in pedidos]
        huecos = ", ".join(["%s"] * len(ids))
        filas = connectToMySQL(DB).query_db(f"""
            SELECT pedido_id, nombre, precio_clp, cantidad
            FROM barra_pedido_items WHERE pedido_id IN ({huecos}) ORDER BY id
        """, ids) or []
        por_pedido = {}
        for f in filas:
            por_pedido.setdefault(f["pedido_id"], []).append(f)
        for p in pedidos:
            # ['items'] y no .items en las plantillas: un dict ya tiene un
            # método items() y Jinja lo prefiere.
            p["items"] = por_pedido.get(p["id"], [])
        return pedidos

    @staticmethod
    def por_codigo(codigo):
        filas = connectToMySQL(DB).query_db(
            "SELECT * FROM barra_pedidos WHERE codigo = %s", (codigo,))
        return Barra._con_items(filas)[0] if filas else None

    @staticmethod
    def obtener(pedido_id):
        filas = connectToMySQL(DB).query_db(
            "SELECT * FROM barra_pedidos WHERE id = %s", (pedido_id,))
        return filas[0] if filas else None

    @staticmethod
    def cola(fecha_local):
        """
        Los pedidos de un día (en hora de Chile), por franja. Con cada uno,
        cuántas veces ese teléfono NO retiró antes: es el dato que hace
        falta para decidir si preparar algo con mucha anticipación.
        """
        inicio_local = datetime(fecha_local.year, fecha_local.month, fecha_local.day)
        desde = tiempo.local_a_utc(inicio_local.isoformat())
        hasta = tiempo.local_a_utc((inicio_local + timedelta(days=1)).isoformat())
        filas = connectToMySQL(DB).query_db("""
            SELECT p.*,
                   (SELECT COUNT(*) FROM barra_pedidos x
                     WHERE x.telefono = p.telefono AND x.estado = 'no_retirado'
                       AND x.id <> p.id) AS veces_no_retiro
            FROM barra_pedidos p
            WHERE p.franja_at >= %s AND p.franja_at < %s
            ORDER BY p.franja_at, p.creado_at
        """, (desde, hasta)) or []
        return Barra._con_items(filas)

    @staticmethod
    def firma(fecha_local):
        """
        Una huella de la cola del día: cambia si entra un pedido, si alguno
        cambia de estado o si alguien avisa que está afuera. El panel la
        pregunta cada tanto y se recarga solo cuando cambió, en vez de
        recargarse a ciegas y borrarle a alguien lo que estaba escribiendo.
        """
        inicio_local = datetime(fecha_local.year, fecha_local.month, fecha_local.day)
        desde = tiempo.local_a_utc(inicio_local.isoformat())
        hasta = tiempo.local_a_utc((inicio_local + timedelta(days=1)).isoformat())
        f = connectToMySQL(DB).query_db("""
            SELECT COUNT(*) AS n, MAX(estado_at) AS e, MAX(afuera_at) AS a,
                   MAX(pagado_at) AS p,
                   SUM(estado = 'recibido') AS nuevos
            FROM barra_pedidos WHERE franja_at >= %s AND franja_at < %s
        """, (desde, hasta))[0]
        return {"firma": f"{f['n']}|{f['e']}|{f['a']}|{f['p']}",
                "nuevos": int(f["nuevos"] or 0)}

    @staticmethod
    def resumen_hoy():
        """Para la tarjeta del panel: lo vivo de hoy."""
        hoy = tiempo.utc_a_local(tiempo.ahora_utc()).date()
        vivos = [p for p in Barra.cola(hoy) if p["estado"] in ESTADOS_VIVOS]
        return {"vivos": len(vivos),
                "nuevos": sum(1 for p in vivos if p["estado"] == "recibido")}

    # -------------------------------------------------------------- escritura

    @staticmethod
    def cambiar_estado(pedido_id, estado):
        """
        Lo usa el panel. Entregar un pedido que se paga al retirar lo marca
        también como cobrado: en la ventana no se entrega un café sin
        cobrarlo, y pedir dos clics para lo mismo es pedir que se olvide uno.
        """
        if estado not in ESTADOS:
            raise ValueError(estado)
        return connectToMySQL(DB).query_db("""
            UPDATE barra_pedidos
               SET estado = %(e)s, estado_at = UTC_TIMESTAMP(),
                   pagado_at = CASE
                       WHEN %(e)s = 'entregado' AND metodo_pago = 'al_retirar'
                       THEN COALESCE(pagado_at, UTC_TIMESTAMP())
                       ELSE pagado_at END
             WHERE id = %(id)s
        """, {"e": estado, "id": pedido_id})

    @staticmethod
    def marcar_pagado(pedido_id, pagado):
        return connectToMySQL(DB).query_db(f"""
            UPDATE barra_pedidos
               SET pagado_at = {'COALESCE(pagado_at, UTC_TIMESTAMP())' if pagado else 'NULL'}
             WHERE id = %s
        """, (pedido_id,))

    @staticmethod
    def cancelar_por_cliente(codigo):
        """Solo mientras nadie lo ha tocado. Una vez que se empezó a
        preparar, cancelarlo es una conversación, no un botón. Devuelve
        cuántas filas cambió (0 = ya no se podía)."""
        return connectToMySQL(DB).query_db("""
            UPDATE barra_pedidos SET estado = 'cancelado', estado_at = UTC_TIMESTAMP()
             WHERE codigo = %s AND estado = 'recibido'
        """, (codigo,))

    @staticmethod
    def avisar_afuera(codigo, detalle=None):
        vivos_sql = ", ".join(f"'{e}'" for e in ESTADOS_VIVOS)
        return connectToMySQL(DB).query_db(f"""
            UPDATE barra_pedidos
               SET afuera_at = UTC_TIMESTAMP(), afuera_detalle = %s
             WHERE codigo = %s AND estado IN ({vivos_sql})
        """, (detalle, codigo))
