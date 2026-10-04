# ==========================================================================
# combo_model.py — los combos de la carta («promos»)
#
# Un combo es «café + algo dulce por $4.990»: nombre y precio propios, y
# adentro varios productos que SIGUEN viviendo en sus categorías de siempre.
#
# POR QUÉ NO ES UNA CATEGORÍA LLAMADA «PROMO»
#   `productos.categoria_id` es una sola llave: meter el Latte en «Promos» lo
#   sacaría de «Cafés». Para tenerlo en las dos habría que duplicar el
#   producto, y ahí el mismo café vive en dos filas con dos precios que algún
#   día discrepan. Además una categoría no tiene dónde guardar el precio del
#   combo. Ver el encabezado de schema/carta_combos.sql, que lo explica
#   entero.
#
# POR QUÉ NO SE LLAMA `promos`
#   Esa tabla ya existe y es el banner de la portada. En pantalla las dos se
#   llaman «promo»; acá tienen nombres distintos para no confundirlas al leer
#   el código.
#
# EL PRECIO NO SE CALCULA DE LOS PRODUCTOS
#   La gracia de una promo es justamente que no es la suma. Se guarda tal
#   cual lo escribe quien la crea.
# ==========================================================================

from flask_app import DB
from flask_app.config.mysqlconnection import connectToMySQL, transaccion


# Mismo criterio y mismo orden de CASE que promo_model: el interruptor manda
# sobre las fechas, porque apagar un combo vigente es para lo que existe.
_ESTADO = """
    CASE
        WHEN c.disponible = 0               THEN 'pausado'
        WHEN UTC_TIMESTAMP() < c.inicio_at  THEN 'programado'
        WHEN c.fin_at IS NOT NULL
             AND UTC_TIMESTAMP() >= c.fin_at THEN 'terminado'
        ELSE 'activo'
    END AS estado
"""


class Combo:

    # --------------------------------------------------------- consultas

    @staticmethod
    def _con_items(combos):
        """
        Le cuelga a cada combo su lista de productos, en UNA consulta para
        todos y no una por combo.

        Trae también `disponible` de cada producto: es lo que deja avisar en
        el panel que a un combo le falta un ingrediente, sin que el combo se
        apague solo (decisión del dueño).
        """
        if not combos:
            return []

        ids = [c["id"] for c in combos]
        huecos = ", ".join(["%s"] * len(ids))
        filas = connectToMySQL(DB).query_db(f"""
            SELECT i.combo_id, i.producto_id, i.cantidad,
                   p.nombre AS producto_nombre, p.disponible AS producto_disponible
            FROM carta_combo_items i
            JOIN productos p ON p.id = i.producto_id
            WHERE i.combo_id IN ({huecos})
            ORDER BY p.nombre;
        """, ids) or []

        por_combo = {}
        for f in filas:
            por_combo.setdefault(f["combo_id"], []).append(f)

        for c in combos:
            c["items"] = por_combo.get(c["id"], [])
            # Cuántos de sus productos están apagados. El panel lo muestra
            # como aviso; la carta no lo usa para ocultar nada.
            c["agotados"] = [i["producto_nombre"] for i in c["items"]
                             if not i["producto_disponible"]]
        return combos

    @staticmethod
    def vigentes_para_carta(marca_slug):
        """
        Los combos que corresponde mostrar AHORA en la carta pública.

        Un combo sin productos adentro no sale: es una promo a medio cargar y
        mostrarla sería ofrecer algo que no se sabe qué trae.
        """
        combos = connectToMySQL(DB).query_db("""
            SELECT c.id, c.nombre, c.descripcion, c.precio_clp, c.orden
            FROM carta_combos c
            JOIN marcas m ON m.id = c.marca_id
            WHERE m.slug = %(marca)s
              AND c.disponible = 1
              AND c.inicio_at <= UTC_TIMESTAMP()
              -- fin_at NULL = sin término: corre hasta que lo apaguen.
              AND (c.fin_at IS NULL OR c.fin_at > UTC_TIMESTAMP())
            ORDER BY c.orden, c.nombre;
        """, {"marca": marca_slug}) or []
        return [c for c in Combo._con_items(combos) if c["items"]]

    @staticmethod
    def listar_para_admin(marca_slug):
        """Todos, incluidos los pausados y los terminados, con su estado."""
        combos = connectToMySQL(DB).query_db(f"""
            SELECT c.id, c.nombre, c.descripcion, c.precio_clp, c.orden,
                   c.disponible, c.inicio_at, c.fin_at,
                   c.mostrar_en_banner, c.prioridad,
                   {_ESTADO}
            FROM carta_combos c
            JOIN marcas m ON m.id = c.marca_id
            WHERE m.slug = %(marca)s
            ORDER BY c.orden, c.fin_at IS NULL, c.fin_at DESC;
        """, {"marca": marca_slug}) or []
        return Combo._con_items(combos)

    @staticmethod
    def combo_de_marca(combo_id, marca_id):
        """
        El combo, solo si es de esa marca. None si no.

        Mismo motivo que el chequeo equivalente de productos y categorías:
        sin esto el panel de una marca podría editar los combos de la otra.
        """
        filas = connectToMySQL(DB).query_db(
            """SELECT * FROM carta_combos
               WHERE id = %(id)s AND marca_id = %(marca)s""",
            {"id": combo_id, "marca": marca_id})
        return filas[0] if filas else None

    # ---------------------------------------------------------- escritura

    @staticmethod
    def crear(datos):
        return connectToMySQL(DB).query_db("""
            INSERT INTO carta_combos
                (marca_id, nombre, descripcion, precio_clp, inicio_at, fin_at,
                 disponible, orden, mostrar_en_banner, prioridad)
            VALUES
                (%(marca_id)s, %(nombre)s, %(descripcion)s, %(precio_clp)s,
                 %(inicio_at)s, %(fin_at)s, %(disponible)s, %(orden)s,
                 %(mostrar_en_banner)s, %(prioridad)s);
        """, datos)

    @staticmethod
    def actualizar(combo_id, marca_id, datos):
        return connectToMySQL(DB).query_db("""
            UPDATE carta_combos
               SET nombre = %(nombre)s, descripcion = %(descripcion)s,
                   precio_clp = %(precio_clp)s, inicio_at = %(inicio_at)s,
                   fin_at = %(fin_at)s, disponible = %(disponible)s,
                   orden = %(orden)s, mostrar_en_banner = %(mostrar_en_banner)s,
                   prioridad = %(prioridad)s
             WHERE id = %(id)s AND marca_id = %(marca_id)s;
        """, dict(datos, id=combo_id, marca_id=marca_id))

    @staticmethod
    def fijar_items(combo_id, items):
        """
        Reemplaza de una vez lo que trae el combo. `items` es
        [(producto_id, cantidad)].

        Se borra y se reinserta en vez de calcular qué cambió: son tres o
        cuatro filas y el diff sería más código que valor. Los ítems no
        tienen identidad propia —nadie enlaza a «el ítem 12»—, así que
        renumerarlos no le rompe nada a nadie.

        VA EN UNA TRANSACCIÓN, y no es adorno: el borrado y las inserciones
        son un solo cambio. Con `query_db` cada consulta hace su propio
        commit, así que un error a mitad de camino —un producto que ya no
        existe, la conexión que se cae— dejaría el combo con la mitad de sus
        productos y sin ninguna señal de que quedó incompleto. Todo o nada.
        """
        with transaccion(DB) as cur:
            cur.execute("DELETE FROM carta_combo_items WHERE combo_id = %s",
                        (combo_id,))
            for producto_id, cantidad in items:
                cur.execute(
                    "INSERT INTO carta_combo_items (combo_id, producto_id, cantidad)"
                    " VALUES (%s, %s, %s)",
                    (combo_id, producto_id, max(1, int(cantidad or 1))))

    @staticmethod
    def cambiar_disponible(combo_id, marca_id, disponible):
        return connectToMySQL(DB).query_db("""
            UPDATE carta_combos SET disponible = %(d)s
             WHERE id = %(id)s AND marca_id = %(marca)s;
        """, {"id": combo_id, "marca": marca_id, "d": 1 if disponible else 0})

    @staticmethod
    def eliminar(combo_id, marca_id):
        """Los ítems se van solos: la llave de carta_combo_items va CASCADE."""
        return connectToMySQL(DB).query_db("""
            DELETE FROM carta_combos
             WHERE id = %(id)s AND marca_id = %(marca)s;
        """, {"id": combo_id, "marca": marca_id})
