# ==========================================================================
# shopify.py — el catálogo de la tienda, traído de Shopify
#
# TODO el diálogo con Shopify vive acá. Ningún otro archivo sabe que existe
# GraphQL. Misma idea que correo.py con smtplib y seguridad.py con bcrypt: si
# algún día cambia la tienda, se toca este archivo y nada más.
#
# Se usa la STOREFRONT API, no la Admin API, y no es un detalle menor: el
# token de Storefront solo da acceso a lo que ya es público en la tienda
# (nombres, precios, si hay stock). Si se filtra, lo que se filtró es el
# catálogo que cualquiera ve entrando a la tienda. Un token de Admin, en
# cambio, lee clientes y pedidos.
#
# Sin dependencias nuevas: urllib de la biblioteca estándar. Un cliente HTTP
# entero para un POST con un JSON adentro no se justifica.
#
# DOS REGLAS que hacen que esto no pueda tumbar el sitio:
#
#   1. `catalogo()` NUNCA lanza si alguna vez funcionó. Cuando Shopify no
#      responde se devuelve la última copia buena. Un precio de hace veinte
#      minutos es infinitamente mejor que una tienda vacía.
#
#   2. Quien llama igual tiene que estar preparado para recibir None (la
#      primera vez, si Shopify nunca contestó). Ahí entra el respaldo escrito
#      a mano en static/js/tienda-productos.js.
# ==========================================================================

import base64
import hashlib
import hmac
import json
import os
import time
import unicodedata
import urllib.error
import urllib.request

# 2026-07 es la versión estable al momento de escribir esto. Shopify saca una
# nueva cada trimestre y mantiene cada una por un año; conviene subirla una
# vez al año, como tzdata. Se deja en el entorno para poder cambiarla sin
# tocar código si algo se rompe.
VERSION_API = "2026-07"

# Cuánto rato se reusa la respuesta antes de volver a preguntarle a Shopify.
# Cinco minutos es el equilibrio: un cambio de precio aparece casi al tiro y
# la portada no le pega a Shopify en cada visita.
CACHE_SEGUNDOS = 300

TIEMPO_LIMITE = 10      # segundos para que Shopify conteste
MAX_PRODUCTOS = 50
MAX_VARIANTES = 100

# Cómo se llaman las opciones en la tienda. Se comparan sin tildes ni
# mayúsculas. Si Seba las nombró de otra forma, se agregan acá y no hay que
# tocar nada más — o se dejan en el entorno.
# La categoría de las pastillas de la tienda sale del campo «Tipo de
# producto» de Shopify, que es el que existe para esto y se escribe en la
# misma ficha del producto (Cartuchos, Tintas, Máquinas...). Escríbelo
# siempre: cuando está en blanco se deduce a ciegas —con dos opciones o con
# ficha técnica cae en «Insumos», y si no en «Accesorios»—, y lo escrito manda.
#
# Nota de nombres: esta tienda nació para café, por eso en el código la
# PRIMERA opción de un producto se llama «tamaño» y la SEGUNDA «molienda».
# Para tatuaje son, por ejemplo, Calibre y Variante: se muestran así en la
# ficha, y los nombres internos no se ven en ninguna parte.
CATEGORIA_CAFE = "Insumos"
CATEGORIA_OTROS = "Accesorios"

NOMBRES_TAMANO = ("tamano", "size", "formato", "peso", "gramaje", "calibre",
                  "medida", "talla", "cantidad", "contenido")
NOMBRES_MOLIENDA = ("molienda", "molido", "grind", "grano", "variante", "color",
                    "tono", "modelo", "tipo")
VALORES_MOLIENDA = ("entero", "fino", "medio", "grueso", "espresso",
                    "moka", "filtrado", "francesa")

# La ficha técnica se administra en Shopify junto al producto. El orden de
# esta lista es el orden editorial que ve la persona en la ficha: no se
# deduce del JSON ni del orden en que Shopify devuelva los campos.
CAMPOS_FICHA = (
    ("marca", "Marca"),
    ("compatibilidad", "Compatibilidad"),
    ("contenido", "Contenido"),
    ("medidas", "Medidas"),
    ("registro", "Registro sanitario"),
    ("uso", "Modo de uso"),
    ("garantia", "Garantía"),
)

# La consulta pide SOLO campos que llevan años estables. En particular NO
# pide `options` del producto: ese campo ha cambiado de forma entre versiones
# (values, optionValues...), y las opciones se pueden reconstruir enteras
# desde selectedOptions de cada variante, que no ha cambiado nunca.
CONSULTA = """
query catalogo($handle: String!, $nproductos: Int!, $nvariantes: Int!) {
  collection(handle: $handle) {
    title
    products(first: $nproductos) {
      nodes {
        handle
        title
        description
        vendor
        productType
        featuredImage { url altText }
        marca: metafield(namespace: "custom", key: "marca") { value }
        compatibilidad: metafield(namespace: "custom", key: "compatibilidad") { value }
        contenido: metafield(namespace: "custom", key: "contenido") { value }
        medidas: metafield(namespace: "custom", key: "medidas") { value }
        registro: metafield(namespace: "custom", key: "registro") { value }
        uso: metafield(namespace: "custom", key: "uso") { value }
        garantia: metafield(namespace: "custom", key: "garantia") { value }
        variants(first: $nvariantes) {
          nodes {
            id
            title
            availableForSale
            price { amount currencyCode }
            selectedOptions { name value }
          }
        }
      }
    }
  }
}
"""


class ShopifyNoResponde(Exception):
    pass


# ------------------------------------------------------------------ entorno

def _entorno():
    """
    Se lee en cada llamada y no una vez al importar, para que un .env recién
    editado tome efecto sin reiniciar Flask. Mismo criterio que correo.py.
    """
    dominio = (os.environ.get("SHOPIFY_DOMINIO") or "").strip()
    # Se acepta que lo peguen con https:// y con barra al final, porque es
    # exactamente lo que uno copia desde el navegador.
    dominio = dominio.replace("https://", "").replace("http://", "").strip("/")
    return {
        "dominio": dominio,
        "token": (os.environ.get("SHOPIFY_STOREFRONT_TOKEN") or "").strip(),
        "coleccion": (os.environ.get("SHOPIFY_COLECCION") or "tienda-web").strip(),
        "version": (os.environ.get("SHOPIFY_API_VERSION") or VERSION_API).strip(),
        "cache": int(os.environ.get("SHOPIFY_CACHE_SEGUNDOS") or CACHE_SEGUNDOS),
        # El secreto del webhook de pedidos. Es OTRO valor que el token de la
        # Storefront API de arriba, y vive en una parte distinta del admin de
        # Shopify — ver docs/TECNICO.md.
        "webhook_secret": (os.environ.get("SHOPIFY_WEBHOOK_SECRET") or "").strip(),
    }


def verificar_firma_webhook(cuerpo_bruto, firma_recibida, cfg=None):
    """
    ¿Este webhook lo mandó Shopify de verdad?

    Shopify firma cada webhook con HMAC-SHA256 sobre el CUERPO CRUDO de la
    petición —antes de parsear el JSON— usando el secreto del webhook, y lo
    manda en base64 en la cabecera `X-Shopify-Hmac-Sha256`. Sin esto,
    cualquiera podría mandar un POST fabricado a mano a la ruta del webhook y
    hacer aparecer pedidos que nunca existieron.

    `compare_digest` en vez de `==`, por la misma razón que `csrf.valido()`:
    una comparación normal con `==` se corta en el primer byte distinto, y
    ese diferencial de tiempo se puede medir para adivinar la firma.

    Sin secreto configurado devuelve False y no True: sin secreto no hay
    contra qué verificar, así que un webhook sin configurar se trata como
    NO verificado, nunca como confiable por defecto.
    """
    cfg = cfg or _entorno()
    secreto = cfg.get("webhook_secret")
    if not secreto or not firma_recibida:
        return False
    calculada = hmac.new(secreto.encode("utf-8"), cuerpo_bruto,
                         hashlib.sha256).digest()
    calculada_b64 = base64.b64encode(calculada).decode("utf-8")
    return hmac.compare_digest(calculada_b64, firma_recibida)


def url_admin_pedido(shopify_order_id):
    """
    El link directo a esa orden en el admin de Shopify, para no tener que
    buscarla a mano desde /admin/pedidos.

    None si no hay dominio configurado o no hay id — la plantilla decide
    qué hacer (no mostrar el botón), nunca arma un link roto.
    """
    dominio = _entorno().get("dominio")
    if not dominio or not shopify_order_id:
        return None
    return f"https://{dominio}/admin/orders/{shopify_order_id}"


def configurado():
    """¿Hay dominio y token? Si no, el sitio usa el respaldo escrito a mano."""
    cfg = _entorno()
    return bool(cfg["dominio"] and cfg["token"])


# ------------------------------------------------------------------- la red

def consultar(consulta, variables=None, cfg=None):
    """
    Un POST a la Storefront API. Devuelve el `data` de la respuesta.

    Levanta ShopifyNoResponde con un mensaje legible en vez de dejar salir el
    error crudo de urllib: acá lo que importa es distinguir «el token está
    malo» de «no hay internet», y eso el traceback no lo dice.
    """
    cfg = cfg or _entorno()
    if not cfg["dominio"] or not cfg["token"]:
        raise ShopifyNoResponde(
            "Falta SHOPIFY_DOMINIO o SHOPIFY_STOREFRONT_TOKEN en el .env.")

    url = f"https://{cfg['dominio']}/api/{cfg['version']}/graphql.json"
    cuerpo = json.dumps({"query": consulta,
                         "variables": variables or {}}).encode("utf-8")

    peticion = urllib.request.Request(url, data=cuerpo, method="POST")
    peticion.add_header("Content-Type", "application/json")
    peticion.add_header("X-Shopify-Storefront-Access-Token", cfg["token"])
    peticion.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(peticion, timeout=TIEMPO_LIMITE) as r:
            datos = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalle = ""
        try:
            detalle = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        if e.code in (401, 403):
            raise ShopifyNoResponde(
                f"Shopify rechazó el token ({e.code}). Revisa "
                f"SHOPIFY_STOREFRONT_TOKEN y que sea de Storefront, no de "
                f"Admin. {detalle}") from e
        if e.code == 404:
            raise ShopifyNoResponde(
                f"Shopify devolvió 404. Revisa SHOPIFY_DOMINIO "
                f"({cfg['dominio']}) y la versión de la API "
                f"({cfg['version']}).") from e
        raise ShopifyNoResponde(f"Shopify respondió {e.code}. {detalle}") from e
    except urllib.error.URLError as e:
        raise ShopifyNoResponde(f"No se pudo llegar a Shopify: {e.reason}") from e
    except (ValueError, TimeoutError) as e:
        raise ShopifyNoResponde(f"Respuesta ilegible de Shopify: {e}") from e

    # GraphQL devuelve 200 aunque la consulta esté mal: los errores vienen
    # dentro del cuerpo. Sin esta comprobación, una consulta rota se vería
    # como una colección vacía.
    if datos.get("errors"):
        primero = datos["errors"][0].get("message", "sin mensaje")
        raise ShopifyNoResponde(f"Shopify rechazó la consulta: {primero}")

    return datos.get("data") or {}


# ----------------------------------------------------------- normalización

def _sin_tildes(texto):
    limpio = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    return limpio.encode("ascii", "ignore").decode()


def _id_numerico(gid):
    """
    'gid://shopify/ProductVariant/56000936771750' -> 56000936771750

    El permalink del carrito usa el número pelado, no el GID. Es el mismo
    número que aparece en la URL del admin de Shopify.
    """
    try:
        return int(str(gid).rstrip("/").split("/")[-1])
    except (TypeError, ValueError):
        return None


def _pesos(monto):
    """
    '12990.0' -> 12990. Los precios del proyecto son enteros en CLP: el peso
    chileno no tiene decimales, y un float para plata es pedir problemas.
    """
    try:
        return int(round(float(monto)))
    except (TypeError, ValueError):
        return 0


def _clasificar(nombres):
    """
    Decide cuál opción de Shopify es el tamaño y cuál la molienda.

    Primero por nombre (sin tildes ni mayúsculas). Si no calza ninguno —
    porque en la tienda se llaman de otra forma— cae al orden en que Shopify
    las devuelve, que es el orden en que están definidas en el producto: la
    primera hace de tamaño y la segunda de molienda.

    Devuelve (nombre_tamano, nombre_molienda), cualquiera puede ser None.
    """
    tamano = molienda = None
    for n in nombres:
        plano = _sin_tildes(n)
        if tamano is None and any(p in plano for p in NOMBRES_TAMANO):
            tamano = n
        elif molienda is None and any(p in plano for p in NOMBRES_MOLIENDA):
            molienda = n

    sin_asignar = [n for n in nombres if n not in (tamano, molienda)]
    if tamano is None and sin_asignar:
        tamano = sin_asignar.pop(0)
    if molienda is None and sin_asignar:
        molienda = sin_asignar.pop(0)
    return tamano, molienda


def _opcion_unica_es_molienda(variantes, nombre):
    """
    Detecta una opción mal rotulada mirando sus valores reales.

    En la tienda ocurrió que la opción se llamaba ``Tamaño``, pero contenía
    Entero, Fino, Medio y Grueso. Confiar solo en el rótulo convertía cada
    molienda en un tamaño y después el front buscaba una combinación que no
    existía; el carrito la descartaba. Dos valores reconocibles bastan para
    corregir la clasificación sin confundir un tamaño aislado con molienda.
    """
    valores = []
    for variante in variantes:
        for opcion in (variante.get("selectedOptions") or []):
            if opcion.get("name") == nombre and opcion.get("value"):
                valor = _sin_tildes(opcion["value"])
                if valor not in valores:
                    valores.append(valor)

    reconocidos = sum(
        1 for valor in valores
        if any(marcador in valor for marcador in VALORES_MOLIENDA)
    )
    return reconocidos >= 2


def _categoria(producto, hay_molienda, hay_ficha=False):
    """
    La categoría con la que el producto entra a una pastilla de la tienda.

    Lo escrito en «Tipo de producto» manda; si está en blanco, se deduce del
    contenido: con dos opciones (por ejemplo calibre y variante) o con ficha
    técnica es «Insumos», y si no, «Accesorios». Deducir es la última
    opción: conviene escribir el tipo en Shopify.
    """
    escrita = (producto.get("productType") or "").strip()
    if escrita:
        return escrita
    return CATEGORIA_CAFE if (hay_molienda or hay_ficha) else CATEGORIA_OTROS


def _es_variante_unica(variantes):
    """
    Shopify le pone la opción 'Title' con valor 'Default Title' a los
    productos sin opciones. Eso no es una opción de verdad: es su forma de
    decir «este producto tiene una sola versión».
    """
    if len(variantes) != 1:
        return False
    opciones = variantes[0].get("selectedOptions") or []
    return all(_sin_tildes(o.get("value")) == "default title" for o in opciones)


def normalizar(producto):
    """
    Traduce un producto de Shopify a la forma que el front ya habla.

    Se conserva a propósito la forma vieja de LP_TIENDA (sizes -> grinds ->
    id de variante) en vez de inventar una nueva: el modal de la landing, la
    ficha y el carrito ya funcionan y están probados contra esa forma. Lo que
    cambia es de dónde salen los datos, no su estructura.

    Lo NUEVO es la disponibilidad: `sin_stock` por tamaño (qué moliendas no
    hay) y `agotado` a nivel de producto.
    """
    variantes = ((producto.get("variants") or {}).get("nodes")) or []
    if not variantes:
        return None

    ficha = []
    for clave, etiqueta in CAMPOS_FICHA:
        campo = producto.get(clave) or {}
        valor = campo.get("value") if isinstance(campo, dict) else None
        if isinstance(valor, str) and valor.strip():
            ficha.append({"etiqueta": etiqueta, "valor": valor.strip()})

    base = {
        "id": producto.get("handle"),
        "name": producto.get("title") or "",
        "vendor": producto.get("vendor") or "",
        "desc": (producto.get("description") or "").strip(),
        "imagen": ((producto.get("featuredImage") or {}).get("url")) or None,
        "imagen_alt": ((producto.get("featuredImage") or {}).get("altText")) or "",
        "ficha": ficha,
    }

    # ---- producto de una sola versión (los filtros, una taza, un libro)
    if _es_variante_unica(variantes):
        v = variantes[0]
        base.update({
            "type": "acc",
            "categoria": _categoria(producto, hay_molienda=False, hay_ficha=bool(ficha)),
            "clp": _pesos((v.get("price") or {}).get("amount")),
            "variant": _id_numerico(v.get("id")),
            "disponible": bool(v.get("availableForSale")),
            "agotado": not v.get("availableForSale"),
            "desde_clp": _pesos((v.get("price") or {}).get("amount")),
        })
        return base

    # ---- producto con opciones
    nombres = []
    for v in variantes:
        for o in (v.get("selectedOptions") or []):
            if o.get("name") and o["name"] not in nombres:
                nombres.append(o["name"])
    n_tamano, n_molienda = _clasificar(nombres)
    # El contenido manda sobre un rótulo equivocado en Shopify. Esto permite
    # que un producto separado por peso tenga una sola opción de molienda
    # aunque esa opción se haya llamado accidentalmente "Tamaño".
    if len(nombres) == 1 and _opcion_unica_es_molienda(variantes, nombres[0]):
        n_tamano, n_molienda = None, nombres[0]

    sizes, moliendas, precios = {}, [], []
    for v in variantes:
        opciones = {o.get("name"): o.get("value")
                    for o in (v.get("selectedOptions") or [])}
        tamano = opciones.get(n_tamano) or "Único"
        molienda = opciones.get(n_molienda) if n_molienda else None
        hay = bool(v.get("availableForSale"))
        clp = _pesos((v.get("price") or {}).get("amount"))
        precios.append(clp)

        caja = sizes.setdefault(tamano, {"clp": clp, "grinds": {}, "sin_stock": []})
        # El precio del tamaño es el de sus variantes; si difieren entre
        # moliendas (no debería, pero Shopify lo permite) se muestra el menor,
        # que es el que acompaña al «Desde» de la tarjeta.
        caja["clp"] = min(caja["clp"], clp) if caja["clp"] else clp

        clave = molienda if molienda else "Único"
        caja["grinds"][clave] = _id_numerico(v.get("id"))
        if not hay:
            caja["sin_stock"].append(clave)
        if molienda and molienda not in moliendas:
            moliendas.append(molienda)

    base.update({
        "type": "cafe",
        "categoria": _categoria(producto, hay_molienda=bool(n_molienda), hay_ficha=bool(ficha)),
        "sizes": sizes,
        # El orden de los tamaños va como LISTA aparte y no se deduce de las
        # claves de `sizes`. Que un objeto JSON conserve el orden funciona en
        # la práctica, pero es una promesa que nadie firmó: basta un
        # serializador que ordene alfabético para que «250 g, 1 kg» se
        # convierta en «1 kg, 250 g» y el sitio ofrezca el kilo por defecto.
        # Ya pasó una vez con el |tojson de Jinja.
        "tamanos": list(sizes.keys()),
        "moliendas": moliendas,
        "desde_clp": min(precios) if precios else 0,
        "agotado": all(not v.get("availableForSale") for v in variantes),
    })
    return base


# -------------------------------------------------------------- el catálogo

_cache = {"hasta": 0, "datos": None, "error": None, "desde": None}


def catalogo(forzar=False):
    """
    La lista de productos de la colección, ya normalizada.

    Devuelve None solo si Shopify nunca contestó bien. Si alguna vez contestó,
    se devuelve la última copia buena aunque ahora esté caído — con precios de
    hace un rato, pero con tienda.
    """
    cfg = _entorno()
    ahora = time.time()

    if not forzar and _cache["datos"] is not None and ahora < _cache["hasta"]:
        return _cache["datos"]

    if not (cfg["dominio"] and cfg["token"]):
        _cache["error"] = "Shopify no está configurado (falta dominio o token)."
        return _cache["datos"]

    try:
        datos = consultar(CONSULTA, {
            "handle": cfg["coleccion"],
            "nproductos": MAX_PRODUCTOS,
            "nvariantes": MAX_VARIANTES,
        }, cfg)
    except ShopifyNoResponde as e:
        # Se guarda el motivo y se devuelve lo último bueno. El que llama
        # decide si avisar o callar; el sitio no se cae por esto.
        _cache["error"] = str(e)
        # Se reintenta pronto, no en cinco minutos: si fue un tropiezo, que
        # se arregle solo en la siguiente visita.
        _cache["hasta"] = ahora + 30
        return _cache["datos"]

    coleccion = datos.get("collection")
    if not coleccion:
        _cache["error"] = (
            f"No existe la colección «{cfg['coleccion']}» en la tienda, o no "
            f"está publicada en el canal de ventas de la Storefront API.")
        _cache["hasta"] = ahora + 30
        return _cache["datos"]

    productos = []
    for p in ((coleccion.get("products") or {}).get("nodes")) or []:
        normalizado = normalizar(p)
        if normalizado and normalizado.get("id"):
            productos.append(normalizado)

    _cache.update({
        "datos": productos,
        "hasta": ahora + cfg["cache"],
        "error": None,
        "desde": ahora,
    })
    return productos


def estado():
    """Para el diagnóstico y el panel: qué sabe la caché ahora mismo."""
    return {
        "configurado": configurado(),
        "coleccion": _entorno()["coleccion"],
        "productos": len(_cache["datos"] or []),
        "error": _cache["error"],
        "edad_segundos": int(time.time() - _cache["desde"]) if _cache["desde"] else None,
    }


def limpiar_cache():
    """Para las pruebas y para un botón de «recargar» si algún día hace falta."""
    _cache.update({"hasta": 0, "datos": None, "error": None, "desde": None})
