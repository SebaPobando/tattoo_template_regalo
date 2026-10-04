# ==========================================================================
# destacado_model.py — los cafés que el admin resalta en la tienda
#
# El catálogo viene de Shopify (config/shopify.py) y NO se toca. Esto solo
# decide cómo se muestra: qué productos van destacados, con qué color, qué
# dice su cinta y en qué orden. Ver schema/tienda_destacados.sql.
#
# Lo que hace un destacado en la tienda:
#   1. su tarjeta lleva un borde y una cinta del color elegido;
#   2. va PRIMERO en «Todos» (la landing los pone delante de todo) y
#      dentro de su categoría (Café, por ejemplo);
#   3. aparece en la pastilla «Especiales», que junta todos los destacados.
# ==========================================================================

from flask_app import DB
from flask_app.config.mysqlconnection import connectToMySQL, transaccion

# Los colores que puede elegir el admin. Una lista cerrada a propósito: un
# hex libre termina en un fucsia sobre fondo crema. Cada uno tiene su clase
# CSS en static/css/destacados.css.
COLORES = {
    "dorado":       "Dorado",
    "verde":        "Verde",
    "verde_dorado": "Verde y dorado",
    "rojo":         "Rojo",
    "negro":        "Negro",
    "cafe":         "Café",
    "terracota":    "Terracota",
    "vino":         "Vino",
    "azul":         "Azul",
    "plata":        "Plata",
    "rosa":         "Rosa",
}
COLOR_POR_DEFECTO = "dorado"
CINTA_POR_DEFECTO = "Edición especial"
LARGO_CINTA = 30

# El nombre de la pastilla que junta todos los destacados.
NOMBRE_PESTANA = "Especiales"


class Destacado:

    @staticmethod
    def todos():
        """{handle: {"color", "cinta", "orden"}}"""
        filas = connectToMySQL(DB).query_db(
            "SELECT handle, color, cinta, orden FROM tienda_destacados ORDER BY orden, handle") or []
        return {f["handle"]: f for f in filas}

    @staticmethod
    def guardar(destacados):
        """
        Reemplaza la lista entera. `destacados` = [{"handle", "color",
        "cinta", "orden"}], ya validados. Todo o nada: una lista guardada a
        medias dejaría la tienda con la mitad de los destacados.
        """
        with transaccion(DB) as cur:
            cur.execute("DELETE FROM tienda_destacados")
            for d in destacados:
                cur.execute("""
                    INSERT INTO tienda_destacados (handle, color, cinta, orden)
                    VALUES (%s, %s, %s, %s)
                """, (d["handle"], d["color"], d["cinta"], d["orden"]))


def aplicar(catalogo, destacados=None):
    """
    El catálogo de Shopify con los destacados puestos: cada producto
    destacado lleva `destacado` = {"color", "cinta", "orden"} (los demás,
    None), y dentro de cada categoría los destacados van primero.

    Devuelve una LISTA NUEVA con copias de los productos: el catálogo que
    llega es la caché de config/shopify.py y modificarlo en el lugar
    ensuciaría la caché para todas las páginas siguientes.

    El orden de las CATEGORÍAS no cambia (lo sigue mandando la colección de
    Shopify): se reordena solo dentro de cada una. Si un accesorio se
    destaca, sube entre los accesorios, no se pone delante de los cafés.

    Nunca lanza: si la base no responde, la tienda se muestra igual, sin
    destacados.
    """
    if not catalogo:
        return catalogo
    if destacados is None:
        try:
            destacados = Destacado.todos()
        except Exception:
            destacados = {}

    productos = []
    for p in catalogo:
        copia = dict(p)
        copia["destacado"] = destacados.get(p.get("id"))
        productos.append(copia)
    if not destacados:
        return productos

    categorias = []
    for p in productos:
        if p.get("categoria") not in categorias:
            categorias.append(p.get("categoria"))

    ordenados = []
    for c in categorias:
        del_grupo = [p for p in productos if p.get("categoria") == c]
        # sorted() es estable: entre los no destacados se conserva el orden
        # de la colección de Shopify.
        del_grupo.sort(key=lambda p: (0, p["destacado"]["orden"]) if p["destacado"] else (1, 0))
        ordenados.extend(del_grupo)
    return ordenados
