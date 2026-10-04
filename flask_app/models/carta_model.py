# ==========================================================================
# carta_model.py — la carta que se consume en el local
#
# SOLO la carta: cafetería, pastelería, pizzas. El café en grano vive en
# Shopify con su stock y sus variantes, y no se duplica acá.
#
# SQL crudo, sin ORM, con consultas parametrizadas (%(nombre)s). Nunca pegues
# valores dentro del string de la consulta: así es como entra un SQL injection.
# ==========================================================================

import re
import unicodedata

import pymysql.err

from flask_app import DB
from flask_app.config.mysqlconnection import connectToMySQL
from flask_app.config.negocio import NEGOCIO

CLP_POR_PUNTO = NEGOCIO["puntos"]["por_peso"]  # pesos por punto, desde negocio.py


class Carta:
    """Lectura de la carta. La escritura llega con el admin."""

    @staticmethod
    def menu(marca_slug=None):
        """
        Devuelve la carta agrupada por categoría, en la misma forma que
        usaba el array que estaba escrito a mano en el HTML:

            [{"id": "cafe", "label": "Café", "items": [
                {"name": "Long Black", "clp": 3200, "desc": "...",
                 "tag": null, "lp": 320}
             ]}]

        Mantener la forma idéntica es lo que permite que el front no cambie
        casi nada: solo pasa de leer una constante a leer la API.

        Los productos AGOTADOS también se devuelven, marcados con
        "agotado": true. En una tienda de insumos saber que algo existe pero
        no hay stock es información útil («vuelve pronto, pregunta»), no
        ruido: esconderlo haría creer que se dejó de vender. Van al final de
        su categoría. Las categorías sin ningún producto no se devuelven.
        """
        marca_slug = marca_slug or NEGOCIO["slug"]
        query = """
            SELECT  c.slug         AS categoria_slug,
                    c.nombre       AS categoria_nombre,
                    c.orden        AS categoria_orden,
                    p.nombre       AS producto_nombre,
                    p.descripcion  AS producto_desc,
                    p.etiqueta     AS producto_etiqueta,
                    p.precio_clp   AS producto_precio,
                    p.precio_individual_clp AS producto_precio_ind,
                    p.disponible   AS producto_disponible,
                    p.orden        AS producto_orden
            FROM categorias c
            JOIN marcas m      ON m.id = c.marca_id
            LEFT JOIN productos p ON p.categoria_id = c.id
            WHERE m.slug = %(marca)s
              AND m.activa = TRUE
            ORDER BY c.orden, p.disponible DESC, p.orden, p.nombre
        """
        filas = connectToMySQL(DB).query_db(query, {"marca": marca_slug})

        categorias = []
        indice = {}
        for f in filas:
            slug = f["categoria_slug"]
            if slug not in indice:
                indice[slug] = {"id": slug, "label": f["categoria_nombre"], "items": []}
                categorias.append(indice[slug])
            if f["producto_nombre"] is None:
                continue  # categoría sin productos disponibles
            ind = f["producto_precio_ind"]
            indice[slug]["items"].append({
                "name": f["producto_nombre"],
                "clp":  f["producto_precio"],
                "lp":   f["producto_precio"] // CLP_POR_PUNTO,
                "desc": f["producto_desc"],
                "tag":  f["producto_etiqueta"],
                "agotado": not f["producto_disponible"],
                # Segundo precio opcional (por ejemplo, unidad suelta y caja).
                # Va como None cuando el producto tiene uno solo, que es lo
                # normal: así el front pregunta por él y no rompe nada.
                "clp_ind": ind,
                "lp_ind":  (ind // CLP_POR_PUNTO) if ind is not None else None,
            })

        visibles = [c for c in categorias if c["items"]]

        # Los packs (combos) van ADELANTE, como una sección más del catálogo.
        #
        # Ojo con lo que esto es y lo que no: es PRESENTACIÓN. En la base no
        # existe ninguna categoría «Promos» —los combos viven en su propia
        # tabla y los productos siguen en sus categorías de siempre—, pero
        # quien mira la carta ve una sección normal. Armarla acá y no en la
        # plantilla hace que /api/v1/menu la entregue igual, sin repetir la
        # lógica en dos lados.
        combos = Carta._combos_como_seccion(marca_slug)
        return ([combos] + visibles) if combos else visibles

    @staticmethod
    def _combos_como_seccion(marca_slug):
        """
        Los combos vigentes con la MISMA forma que un grupo de la carta, para
        que la plantilla no tenga que distinguirlos. None si no hay ninguno.

        La descripción se arma con lo que trae, usando los nombres reales de
        los productos: si mañana se renombra el brownie, la promo se actualiza
        sola. Ese es justamente el motivo de referenciar productos en vez de
        copiar sus nombres dentro del combo.
        """
        from flask_app.models.combo_model import Combo

        vigentes = Combo.vigentes_para_carta(marca_slug)
        if not vigentes:
            return None

        items = []
        for c in vigentes:
            trae = ", ".join(f"{i['cantidad']}× {i['producto_nombre']}"
                             for i in c["items"])
            items.append({
                "name": c["nombre"],
                "clp": c["precio_clp"],
                "lp": c["precio_clp"] // CLP_POR_PUNTO,
                "desc": f"{c['descripcion']} · Incluye: {trae}"
                        if c["descripcion"] else f"Incluye: {trae}",
                "tag": "Pack",
                "agotado": False,
                "clp_ind": None,
                "lp_ind": None,
            })
        return {"id": "packs", "label": "Packs", "items": items}

    @staticmethod
    def marcas_activas():
        return connectToMySQL(DB).query_db(
            "SELECT id, slug, nombre, tema_css FROM marcas WHERE activa = TRUE ORDER BY id"
        )

    # ======================================================================
    # Escritura — lo que usa el admin
    # ======================================================================

    @staticmethod
    def categorias_de(marca_slug=None):
        marca_slug = marca_slug or NEGOCIO["slug"]
        return connectToMySQL(DB).query_db(
            """SELECT c.id, c.slug, c.nombre, c.orden
               FROM categorias c JOIN marcas m ON m.id = c.marca_id
               WHERE m.slug = %(marca)s ORDER BY c.orden, c.nombre""",
            {"marca": marca_slug})

    @staticmethod
    def listar_para_admin(marca_slug=None):
        """
        Todos los productos, incluidos los no disponibles — al revés que menu(),
        que solo devuelve lo que el cliente puede pedir.
        """
        marca_slug = marca_slug or NEGOCIO["slug"]
        return connectToMySQL(DB).query_db(
            """SELECT p.*, c.nombre AS categoria_nombre, c.orden AS categoria_orden
               FROM productos p
               JOIN marcas m ON m.id = p.marca_id
               LEFT JOIN categorias c ON c.id = p.categoria_id
               WHERE m.slug = %(marca)s
               ORDER BY c.orden, p.orden, p.nombre""",
            {"marca": marca_slug})

    @staticmethod
    def obtener(producto_id):
        filas = connectToMySQL(DB).query_db(
            "SELECT * FROM productos WHERE id = %(id)s", {"id": producto_id})
        return filas[0] if filas else None

    # Las dos tablas que llevan slug por marca. El nombre de una tabla no se
    # puede pasar como parámetro en SQL —va interpolado—, así que la lista
    # blanca no es adorno: es lo que impide que un día alguien meta texto de
    # un formulario acá y quede una inyección.
    _TABLAS_CON_SLUG = {"productos": "producto", "categorias": "categoria"}

    @staticmethod
    def _slug_libre(marca_id, nombre, excluir_id=None, tabla="productos"):
        """
        Genera un slug a partir del nombre y le agrega -2, -3... si ya existe.
        El UNIQUE de la base es (marca_id, slug) —en productos y en
        categorías—, así que dos marcas pueden tener 'margarita' sin chocar.
        """
        if tabla not in Carta._TABLAS_CON_SLUG:
            raise ValueError(f"tabla no permitida: {tabla!r}")

        base = unicodedata.normalize("NFKD", nombre or "")
        base = base.encode("ascii", "ignore").decode()
        base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()[:70]
        base = base or Carta._TABLAS_CON_SLUG[tabla]

        candidato, n = base, 1
        while True:
            filas = connectToMySQL(DB).query_db(
                f"""SELECT id FROM {tabla}
                    WHERE marca_id = %(marca)s AND slug = %(slug)s
                      AND (%(excluir)s IS NULL OR id <> %(excluir)s) LIMIT 1""",
                {"marca": marca_id, "slug": candidato, "excluir": excluir_id})
            if not filas:
                return candidato
            n += 1
            candidato = f"{base}-{n}"

    # ------------------------------------------------------- categorías

    @staticmethod
    def categoria_de_marca(categoria_id, marca_id):
        """
        La categoría, solo si pertenece a esa marca. None si no.

        Mismo motivo que el chequeo equivalente de los productos: sin esto,
        /admin/carta/<otra-marca>/categorias/7 renombraría la categoría 7 de
        la marca ajena desde el panel de esta.
        """
        filas = connectToMySQL(DB).query_db(
            """SELECT id, slug, nombre, orden FROM categorias
               WHERE id = %(id)s AND marca_id = %(marca)s""",
            {"id": categoria_id, "marca": marca_id})
        return filas[0] if filas else None

    @staticmethod
    def crear_categoria(marca_id, nombre, orden=0):
        """
        Devuelve el id de la categoría nueva.

        El slug se calcula del nombre y nunca se pide en el formulario: es un
        detalle técnico y dejarlo escribir a mano solo abre la puerta a dos
        categorías con el mismo slug o a uno con espacios.
        """
        return connectToMySQL(DB).query_db(
            """INSERT INTO categorias (marca_id, slug, nombre, orden)
               VALUES (%(marca)s, %(slug)s, %(nombre)s, %(orden)s);""",
            {"marca": marca_id, "nombre": nombre, "orden": orden,
             "slug": Carta._slug_libre(marca_id, nombre, tabla="categorias")})

    @staticmethod
    def actualizar_categoria(categoria_id, marca_id, nombre, orden):
        """
        Renombra y reordena.

        El slug NO se regenera al renombrar, a propósito: puede estar en la
        URL de la carta pública o en un enlace que alguien guardó, y cambiarlo
        por corregir una tilde rompería ese enlace sin avisar.
        """
        return connectToMySQL(DB).query_db(
            """UPDATE categorias SET nombre = %(nombre)s, orden = %(orden)s
               WHERE id = %(id)s AND marca_id = %(marca)s;""",
            {"id": categoria_id, "marca": marca_id,
             "nombre": nombre, "orden": orden})

    @staticmethod
    def cuantos_productos_tiene(categoria_id):
        """Para mostrar al lado de cada categoría cuántos productos cuelgan."""
        filas = connectToMySQL(DB).query_db(
            """SELECT COUNT(*) AS n FROM productos
               WHERE categoria_id = %(id)s""", {"id": categoria_id})
        return int(filas[0]["n"]) if filas else 0

    @staticmethod
    def crear(datos):
        datos = dict(datos)
        datos["slug"] = Carta._slug_libre(datos["marca_id"], datos["nombre"])
        return connectToMySQL(DB).query_db(
            """INSERT INTO productos
               (marca_id, categoria_id, slug, nombre, descripcion, etiqueta,
                precio_clp, precio_individual_clp, imagen_url, disponible, orden)
               VALUES (%(marca_id)s, %(categoria_id)s, %(slug)s, %(nombre)s,
                       %(descripcion)s, %(etiqueta)s, %(precio_clp)s,
                       %(precio_individual_clp)s,
                       %(imagen_url)s, %(disponible)s, %(orden)s)""", datos)

    @staticmethod
    def actualizar(producto_id, datos):
        datos = dict(datos)
        datos["id"] = producto_id
        # El slug sigue al nombre, pero conserva el suyo si no cambió: así los
        # enlaces que alguien haya guardado no se rompen sin necesidad.
        actual = Carta.obtener(producto_id)
        if actual and actual["nombre"] != datos["nombre"]:
            datos["slug"] = Carta._slug_libre(actual["marca_id"], datos["nombre"], producto_id)
        else:
            datos["slug"] = actual["slug"] if actual else None
        return connectToMySQL(DB).query_db(
            """UPDATE productos SET
                 categoria_id = %(categoria_id)s, slug = %(slug)s, nombre = %(nombre)s,
                 descripcion = %(descripcion)s, etiqueta = %(etiqueta)s,
                 precio_clp = %(precio_clp)s,
                 precio_individual_clp = %(precio_individual_clp)s,
                 imagen_url = %(imagen_url)s,
                 disponible = %(disponible)s, orden = %(orden)s
               WHERE id = %(id)s""", datos)

    @staticmethod
    def cambiar_disponible(producto_id, disponible):
        """La acción del día a día: se acabó el croissant."""
        return connectToMySQL(DB).query_db(
            "UPDATE productos SET disponible = %(d)s WHERE id = %(id)s",
            {"d": 1 if disponible else 0, "id": producto_id})

    @staticmethod
    def eliminar(producto_id):
        """
        Borrado real, para lo que se creó por error.

        Si alguien lo tiene en su lista de deseos, MySQL lo impide por la llave
        foránea y devolvemos False. En ese caso lo correcto no es borrar sino
        marcarlo como no disponible: el producto existió y hay datos que lo
        referencian.
        """
        try:
            connectToMySQL(DB).query_db(
                "DELETE FROM productos WHERE id = %(id)s", {"id": producto_id})
            return True
        except pymysql.err.IntegrityError:
            return False
