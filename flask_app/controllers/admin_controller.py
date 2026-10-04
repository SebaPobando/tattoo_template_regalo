# ==========================================================================
# admin_controller.py — administración de la carta
#
# Una sola pantalla por marca: todos los productos agrupados por categoría,
# editables ahí mismo. Crear, actualizar, eliminar, y apagar/prender de un
# click.
#
# La marca va SIEMPRE en la URL (/admin/carta/<slug-de-la-marca>). No es decoración:
# es lo que evita que una pizza de la segunda marca termine colgada de la carta de
# la cafetería por un POST mal dirigido. Son dos sociedades con RUT distinto;
# mezclarles los productos no es un bug cosmético.
#
# Todo va detrás de @requiere_admin. Ojo con el orden de los decoradores:
# @app.route va PRIMERO, y debajo el que protege. Al revés, Flask registra
# la vista sin protección.
# ==========================================================================

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

from flask_app import app
from flask_app.config import csrf, tiempo
from flask_app.controllers.main_controller import (requiere_admin,
                                                   requiere_personal)
from flask_app.config.negocio import NEGOCIO
from flask_app.models.carta_model import Carta
from flask_app.models.combo_model import Combo

MARCA_POR_DEFECTO = NEGOCIO["slug"]


# ------------------------------------------------------------------ ayudas

def _marca_o_404(slug):
    """
    Resuelve el slug de la URL a la marca. Si no existe o está desactivada,
    404: no tiene sentido administrar la carta de algo que no atiende.
    """
    marca = next((m for m in Carta.marcas_activas() if m["slug"] == slug), None)
    if not marca:
        abort(404)
    return marca


def _producto_de_la_marca(producto_id, marca):
    """
    Trae el producto y comprueba que sea de ESTA marca.

    Sin esta comprobación, /admin/carta/<marca-principal>/97 editaría la pizza 97
    de la segunda marca y le estamparía marca_id de la cafetería, moviéndola de
    empresa en silencio. Devuelve 404 y no 403 a propósito: desde la carta
    de una marca, los productos de la otra sencillamente no existen.
    """
    producto = Carta.obtener(producto_id)
    if not producto or producto["marca_id"] != marca["id"]:
        abort(404)
    return producto


def _protegido_csrf():
    """Corta la petición si el token no calza. 400, no 403: no damos pistas."""
    if not csrf.valido(request.form.get("csrf")):
        abort(400, "Token de seguridad inválido. Recarga la página.")


def _numero(valor, minimo=0, por_defecto=0):
    """Convierte texto de formulario a entero sin reventar con basura."""
    try:
        n = int(str(valor).strip().replace(".", "").replace("$", "") or por_defecto)
    except (TypeError, ValueError):
        return por_defecto
    return max(n, minimo)


def _texto(valor, maximo, obligatorio=False):
    v = (valor or "").strip()
    if obligatorio and not v:
        return None
    return v[:maximo] if v else None


def _numero_o_nada(valor):
    """
    Como _numero, pero el campo vacío devuelve None en vez de 0.

    Es la diferencia entre «esta pizza no tiene tamaño individual» y «el
    individual sale gratis». Un 0 en la carta pública se vería como $0.
    """
    if valor is None or not str(valor).strip():
        return None
    return _numero(valor)


def _datos_del_formulario(marca):
    nombre = _texto(request.form.get("nombre"), 150, obligatorio=True)
    if not nombre:
        return None, "El nombre no puede quedar vacío."

    # La categoría tiene que existir Y pertenecer a esta marca. Sin esta
    # comprobación, un POST a mano podría colgar un café de una categoría de
    # la segunda marca, o mandar un id inexistente y reventar la app con un 500.
    categoria_id = request.form.get("categoria_id") or None
    if categoria_id:
        validas = {str(c["id"]) for c in Carta.categorias_de(marca["slug"])}
        if str(categoria_id) not in validas:
            return None, "Esa categoría no existe en este catálogo."

    return {
        "marca_id": marca["id"],
        "categoria_id": int(categoria_id) if categoria_id else None,
        "nombre": nombre,
        "descripcion": _texto(request.form.get("descripcion"), 2000),
        "etiqueta": _texto(request.form.get("etiqueta"), 30),
        "precio_clp": _numero(request.form.get("precio_clp")),
        "precio_individual_clp": _numero_o_nada(request.form.get("precio_individual_clp")),
        "imagen_url": _texto(request.form.get("imagen_url"), 255),
        "disponible": 1 if request.form.get("disponible") else 0,
        "orden": _numero(request.form.get("orden")),
    }, None


# --------------------------------------------------------------------- vistas

@app.route("/admin")
@requiere_personal
def admin_inicio():
    """
    El panel. Existe para que el menú de arriba no crezca: cada sección nueva
    de administración era un enlace más en la barra, y con dos ya se partía
    en dos líneas. Ahora la barra lleva un solo «Admin» y lo demás vive acá.

    El barista también entra, pero ve solo las tarjetas de la barra (vales y
    ruleta). Lo demás ni se consulta para él.
    """
    from flask import session
    es_admin = session["usuario"].get("rol") == "admin"
    # Cada módulo opcional va en su try: sin su migración, la tarjeta no
    # sale y el panel no se cae.
    try:
        from flask_app.models.vale_model import Vale
        vales = Vale.resumen()
    except Exception:
        vales = None
    try:
        from flask_app.models.ruleta_model import Ruleta
        ruleta = Ruleta.resumen()
    except Exception:
        ruleta = None
    # Los pedidos para retiro: el personal del mesón también los atiende.
    # Si falta su migración, la tarjeta simplemente no sale.
    try:
        from flask_app.models.barra_model import Barra
        barra = {**Barra.resumen_hoy(), "activo": Barra.config()["activo"]}
    except Exception:
        barra = None
    if not es_admin:
        # Al personal solo se le muestran los pedidos si están abiertos: la
        # configuración (abrirlos, horarios) es del admin.
        return render_template("admin_inicio.html", es_admin=False,
                               vales=vales, ruleta=ruleta,
                               barra=barra if barra and barra["activo"] else None)

    from flask_app.models.actividad_model import Actividad
    from flask_app.models.muro_model import Muro
    from flask_app.models.pedido_shopify_model import Pedido
    from flask_app.models.promo_model import Promo
    from flask_app.models.usuario_model import Usuario
    try:
        from flask_app.models.destacado_model import Destacado
        destacados = len(Destacado.todos())
    except Exception:
        destacados = None
    return render_template(
        "admin_inicio.html",
        es_admin=True,
        destacados=destacados,
        vales=vales,
        barra=barra,
        ruleta=ruleta,
        promos=Promo.resumen(),
        pedidos=Pedido.resumen(),
        productos=len(Carta.listar_para_admin(NEGOCIO["slug"]))
                  + len(Carta.listar_para_admin(NEGOCIO["segunda"]["slug"])),
        publicadas=sum(1 for a in Actividad.listar_para_admin()
                       if a["estado"] == "publicada"),
        muro=Muro.resumen(),
        usuarios=Usuario.resumen(),
    )


@app.route("/admin/carta")
@requiere_admin
def admin_carta_inicio():
    """El enlace del menú no conoce marcas: lo mandamos a la de siempre."""
    return redirect(url_for("admin_carta", marca_slug=MARCA_POR_DEFECTO))


@app.route("/admin/carta/<marca_slug>")
@requiere_admin
def admin_carta(marca_slug):
    marca = _marca_o_404(marca_slug)
    productos = Carta.listar_para_admin(marca_slug)
    categorias = Carta.categorias_de(marca_slug)

    # Agrupar en Python y no con otra consulta: son 60 filas, no vale la pena.
    grupos, indice = [], {}
    for p in productos:
        clave = p["categoria_id"]
        if clave not in indice:
            indice[clave] = {"nombre": p["categoria_nombre"] or "Sin categoría",
                             "id": clave, "items": []}
            grupos.append(indice[clave])
        indice[clave]["items"].append(p)

    # Cuantos productos cuelgan de cada categoria: se muestra al lado del
    # nombre para que se note cual esta vacia antes de reordenar.
    conteo = {}
    for prod in productos:
        conteo[prod["categoria_id"]] = conteo.get(prod["categoria_id"], 0) + 1

    return render_template("admin_carta.html",
                           grupos=grupos, categorias=categorias, marca=marca,
                           productos_por_categoria=conteo,
                           marcas=Carta.marcas_activas(),
                           total=len(productos),
                           apagados=sum(1 for p in productos if not p["disponible"]),
                           csrf_token=csrf.token())


# =========================================================== categorías
#
# La carta se agrupa por categorías y hasta ahora solo se podían crear por
# SQL: el panel las listaba pero no dejaba tocarlas. Se pueden crear,
# renombrar y reordenar; BORRAR no, y es deliberado: una categoría con
# productos adentro está protegida por una llave foránea, y las dos salidas
# —bloquear o dejar los productos sin categoría— son decisiones que conviene
# tomar mirando el caso, no con un botón que parece inofensivo.


def _datos_categoria():
    """
    (datos, error) desde el formulario. Mismo contrato que
    `_datos_del_formulario` de los productos, para que las dos rutas se lean
    igual.
    """
    nombre = (request.form.get("nombre") or "").strip()
    if not nombre:
        return None, "La categoría necesita un nombre."
    if len(nombre) > 100:
        return None, "El nombre de la categoría es muy largo (máximo 100)."

    try:
        orden = int(request.form.get("orden") or 0)
    except ValueError:
        return None, "El orden tiene que ser un número."

    return {"nombre": nombre, "orden": orden}, None


def _categoria_de_la_marca(categoria_id, marca):
    """404 si esa categoría no es de esta marca (ver categoria_de_marca)."""
    categoria = Carta.categoria_de_marca(categoria_id, marca["id"])
    if not categoria:
        abort(404)
    return categoria


@app.route("/admin/carta/<marca_slug>/categorias/crear", methods=["POST"])
@requiere_admin
def admin_categoria_crear(marca_slug):
    _protegido_csrf()
    marca = _marca_o_404(marca_slug)
    datos, error = _datos_categoria()
    if error:
        flash(error, "error")
    else:
        # Si no dicen dónde va, al final: menos sorpresas que meterla arriba
        # y descolocar una carta que ya estaba ordenada.
        if not request.form.get("orden"):
            existentes = Carta.categorias_de(marca_slug)
            datos["orden"] = max((c["orden"] for c in existentes), default=0) + 1
        Carta.crear_categoria(marca["id"], datos["nombre"], datos["orden"])
        flash(f"Categoría «{datos['nombre']}» creada.", "info")
    return redirect(url_for("admin_carta", marca_slug=marca_slug))


@app.route("/admin/carta/<marca_slug>/categorias/<int:categoria_id>",
           methods=["POST"])
@requiere_admin
def admin_categoria_actualizar(marca_slug, categoria_id):
    _protegido_csrf()
    marca = _marca_o_404(marca_slug)
    _categoria_de_la_marca(categoria_id, marca)
    datos, error = _datos_categoria()
    if error:
        flash(error, "error")
    else:
        Carta.actualizar_categoria(categoria_id, marca["id"],
                                   datos["nombre"], datos["orden"])
        flash(f"Categoría «{datos['nombre']}» actualizada.", "info")
    return redirect(url_for("admin_carta", marca_slug=marca_slug))


@app.route("/admin/carta/<marca_slug>/crear", methods=["POST"])
@requiere_admin
def admin_carta_crear(marca_slug):
    _protegido_csrf()
    marca = _marca_o_404(marca_slug)
    datos, error = _datos_del_formulario(marca)
    if error:
        flash(error, "error")
    else:
        Carta.crear(datos)
        flash(f"«{datos['nombre']}» agregado al catálogo.", "info")
    return redirect(url_for("admin_carta", marca_slug=marca_slug))


@app.route("/admin/carta/<marca_slug>/<int:producto_id>", methods=["POST"])
@requiere_admin
def admin_carta_actualizar(marca_slug, producto_id):
    _protegido_csrf()
    marca = _marca_o_404(marca_slug)
    _producto_de_la_marca(producto_id, marca)
    datos, error = _datos_del_formulario(marca)
    if error:
        flash(error, "error")
    else:
        Carta.actualizar(producto_id, datos)
        flash(f"«{datos['nombre']}» actualizado.", "info")
    return redirect(url_for("admin_carta", marca_slug=marca_slug))


@app.route("/admin/carta/<marca_slug>/<int:producto_id>/eliminar", methods=["POST"])
@requiere_admin
def admin_carta_eliminar(marca_slug, producto_id):
    _protegido_csrf()
    marca = _marca_o_404(marca_slug)
    producto = _producto_de_la_marca(producto_id, marca)
    if Carta.eliminar(producto_id):
        flash(f"«{producto['nombre']}» eliminado.", "info")
    else:
        # Lo bloqueó una llave foránea: alguien lo tiene en su lista de deseos.
        flash(f"No se puede eliminar «{producto['nombre']}» porque hay datos "
              "que lo referencian. Márcalo como no disponible.", "error")
    return redirect(url_for("admin_carta", marca_slug=marca_slug))


@app.route("/admin/carta/<marca_slug>/<int:producto_id>/disponible", methods=["POST"])
@requiere_admin
def admin_carta_disponible(marca_slug, producto_id):
    """
    El toggle de un click. Responde JSON porque lo llama fetch() desde la
    página, sin recargar: es la acción que más se va a usar en el día a día.
    """
    _protegido_csrf()
    marca = _marca_o_404(marca_slug)
    producto = _producto_de_la_marca(producto_id, marca)
    nuevo = not producto["disponible"]
    Carta.cambiar_disponible(producto_id, nuevo)
    return jsonify({"id": producto_id, "disponible": nuevo})


# ============================================================== combos
#
# Los «combos» son las promos de la CARTA: «café + algo dulce por $4.990».
# No confundir con las promos de promo_controller, que son el banner de la
# portada. Por qué son una tabla propia y no una categoría llamada «Promos»
# está explicado entero en schema/carta_combos.sql; el resumen es que un
# producto pertenece a UNA categoría, así que meter el Latte en «Promos» lo
# sacaría de «Cafés».

DIAS_MAX_COMBO = 365


def _datos_combo():
    """(datos, error), con el mismo contrato que las otras dos del archivo."""
    nombre = (request.form.get("nombre") or "").strip()
    if len(nombre) < 2:
        return None, "El pack necesita un nombre."
    if len(nombre) > 120:
        return None, "El nombre del pack es muy largo (máximo 120)."

    try:
        precio = int(request.form.get("precio_clp") or 0)
    except ValueError:
        return None, "El precio tiene que ser un número."
    if precio < 0:
        return None, "El precio no puede ser negativo."

    # Mismas dos fechas absolutas que el banner, y por el mismo motivo:
    # editar el texto no puede reiniciar ningún plazo (ver promos.sql).
    inicio = tiempo.local_a_utc(request.form.get("inicio"))
    if not inicio:
        return None, "Revisa la fecha de inicio: no se entiende."

    # Sin término: corre hasta que alguien lo apague. La fecha de fin que
    # venga en el formulario se ignora a propósito —el campo queda
    # deshabilitado en pantalla, pero un POST a mano podría traerla igual.
    if request.form.get("sin_termino"):
        fin = None
    else:
        fin = tiempo.local_a_utc(request.form.get("fin"))
        if not fin:
            return None, "Revisa la fecha de término: no se entiende."
        if fin <= inicio:
            return None, "El pack no puede terminar antes de empezar."
        if (fin - inicio).days > DIAS_MAX_COMBO:
            return None, f"El plazo no puede pasar de {DIAS_MAX_COMBO} días."

    try:
        orden = int(request.form.get("orden") or 0)
        prioridad = int(request.form.get("prioridad") or 0)
    except ValueError:
        return None, "El orden y la prioridad tienen que ser números."

    return {
        "nombre": nombre,
        "descripcion": (request.form.get("descripcion") or "").strip()[:300] or None,
        "precio_clp": precio,
        "inicio_at": inicio,
        "fin_at": fin,
        "disponible": 1 if request.form.get("disponible") else 0,
        "orden": orden,
        "mostrar_en_banner": 1 if request.form.get("mostrar_en_banner") else 0,
        "prioridad": max(-99, min(99, prioridad)),
    }, None


def _items_del_formulario(marca):
    """
    [(producto_id, cantidad)] desde el formulario, quedándose SOLO con los
    productos que son de esta marca.

    Ese filtro es el que impide armar un combo de la cafetería con una pizza
    de la otra marca mandando un id a mano. Descarta en silencio en vez de
    fallar: el formulario nunca ofrece esos productos, así que un id ajeno
    solo puede venir de alguien jugando con el POST.
    """
    validos = {p["id"] for p in Carta.listar_para_admin(marca["slug"])}
    items, vistos = [], set()
    for crudo in request.form.getlist("producto_id"):
        try:
            pid = int(crudo)
        except (TypeError, ValueError):
            continue
        if pid not in validos or pid in vistos:
            continue
        vistos.add(pid)
        try:
            cantidad = int(request.form.get(f"cantidad_{pid}") or 1)
        except ValueError:
            cantidad = 1
        items.append((pid, max(1, cantidad)))
    return items


def _combo_de_la_marca(combo_id, marca):
    combo = Combo.combo_de_marca(combo_id, marca["id"])
    if not combo:
        abort(404)
    return combo


@app.route("/admin/carta/<marca_slug>/combos")
@requiere_admin
def admin_combos(marca_slug):
    marca = _marca_o_404(marca_slug)
    return render_template("admin_combos.html",
                           marca=marca,
                           marcas=Carta.marcas_activas(),
                           combos=Combo.listar_para_admin(marca_slug),
                           productos=Carta.listar_para_admin(marca_slug),
                           tiempo=tiempo,
                           csrf_token=csrf.token())


@app.route("/admin/carta/<marca_slug>/combos/crear", methods=["POST"])
@requiere_admin
def admin_combo_crear(marca_slug):
    _protegido_csrf()
    marca = _marca_o_404(marca_slug)
    datos, error = _datos_combo()
    if error:
        flash(error, "error")
        return redirect(url_for("admin_combos", marca_slug=marca_slug))

    items = _items_del_formulario(marca)
    if not items:
        flash("Un pack necesita al menos un producto adentro.", "error")
        return redirect(url_for("admin_combos", marca_slug=marca_slug))

    combo_id = Combo.crear(dict(datos, marca_id=marca["id"]))
    Combo.fijar_items(combo_id, items)
    flash(f"Pack «{datos['nombre']}» creado.", "info")
    return redirect(url_for("admin_combos", marca_slug=marca_slug))


@app.route("/admin/carta/<marca_slug>/combos/<int:combo_id>", methods=["POST"])
@requiere_admin
def admin_combo_actualizar(marca_slug, combo_id):
    _protegido_csrf()
    marca = _marca_o_404(marca_slug)
    _combo_de_la_marca(combo_id, marca)
    datos, error = _datos_combo()
    if error:
        flash(error, "error")
        return redirect(url_for("admin_combos", marca_slug=marca_slug))

    items = _items_del_formulario(marca)
    if not items:
        flash("Un pack necesita al menos un producto adentro.", "error")
        return redirect(url_for("admin_combos", marca_slug=marca_slug))

    Combo.actualizar(combo_id, marca["id"], datos)
    Combo.fijar_items(combo_id, items)
    flash(f"Pack «{datos['nombre']}» actualizado.", "info")
    return redirect(url_for("admin_combos", marca_slug=marca_slug))


@app.route("/admin/carta/<marca_slug>/combos/<int:combo_id>/interruptor",
           methods=["POST"])
@requiere_admin
def admin_combo_interruptor(marca_slug, combo_id):
    """
    Prender y apagar sin editar nada más: es lo que se usa cuando se acabó
    un ingrediente a mitad de tarde. Las fechas quedan intactas, así que
    volver a encenderlo lo repone con el plazo original.
    """
    _protegido_csrf()
    marca = _marca_o_404(marca_slug)
    combo = _combo_de_la_marca(combo_id, marca)
    Combo.cambiar_disponible(combo_id, marca["id"], not combo["disponible"])
    flash(f"Pack «{combo['nombre']}» "
          f"{'apagado' if combo['disponible'] else 'encendido'}.", "info")
    return redirect(url_for("admin_combos", marca_slug=marca_slug))


@app.route("/admin/carta/<marca_slug>/combos/<int:combo_id>/eliminar",
           methods=["POST"])
@requiere_admin
def admin_combo_eliminar(marca_slug, combo_id):
    _protegido_csrf()
    marca = _marca_o_404(marca_slug)
    combo = _combo_de_la_marca(combo_id, marca)
    Combo.eliminar(combo_id, marca["id"])
    flash(f"Pack «{combo['nombre']}» eliminado.", "info")
    return redirect(url_for("admin_combos", marca_slug=marca_slug))
