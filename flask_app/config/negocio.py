# ==========================================================================
# negocio.py — TODO lo que cambia de un cliente a otro
#
# ESTE ES EL ARCHIVO QUE SE TOCA AL VENDER UNA INSTALACIÓN NUEVA. La idea es
# simple: el código no sabe cómo se llama el negocio. Lo pregunta acá.
#
# Nada de esto es secreto —son los datos que el sitio muestra en público—, así
# que viven en un archivo de Python normal y no en el .env. En el .env van las
# claves (base de datos, SMTP, Shopify). Aun así, cada valor puede pisarse con
# una variable de entorno del mismo nombre en MAYÚSCULAS: útil para probar una
# instalación sin tocar el archivo, o para servir dos marcas desde el mismo
# código.
#
# En las plantillas se llama `negocio` y NO `marca`: «marca» ya significa otra
# cosa en este proyecto —cada uno de los catálogos que tiene el local (la
# tienda y, si existe, el estudio), la fila de la tabla `marcas`— y dos cosas distintas con el mismo nombre en la misma
# plantilla terminan en un bug raro de encontrar.
#
# Cómo se usa desde las plantillas, sin importar nada:
#
#     {{ negocio.nombre }}            Insumos Tattoo Ejemplo
#     {{ negocio.correo }}            hola@insumostattoo.cl
#     {{ negocio.whatsapp_url }}      https://wa.me/56900000000
#     {{ negocio.puntos.nombre }}     Puntos Tinta
#
# Y desde Python:
#
#     from flask_app.config.negocio import NEGOCIO
# ==========================================================================

import os


def _env(clave, por_defecto):
    """El entorno pisa al archivo. Vacío cuenta como «no definido»."""
    valor = os.environ.get(clave.upper())
    return valor if valor not in (None, "") else por_defecto


# --------------------------------------------------------------------------
# 1. EL NEGOCIO
# --------------------------------------------------------------------------
SLUG = _env("NEGOCIO_SLUG", "principal")   # el identificador corto en la base
NOMBRE = _env("MARCA_NOMBRE", "Insumos Tattoo Ejemplo")
NOMBRE_CORTO = _env("MARCA_NOMBRE_CORTO", "Insumos")   # el del logo, arriba
TAG = _env("MARCA_TAG", "TATTOO")                       # la palabra bajo el logo
LEMA = _env("MARCA_LEMA", "Insumos de tatuaje para profesionales")
# El nombre bajo el icono cuando alguien instala el sitio en su teléfono.
# Conviene que quepa en unos 12 caracteres: más largo, el teléfono lo corta.
# Vacío, se usa el nombre completo.
PWA_NOMBRE = _env("MARCA_PWA_NOMBRE", NOMBRE)
# Lo grande de la portada. El título es lo primero que se lee del negocio:
# vale la pena pensarlo, no dejar el de la plantilla.
HERO_TITULO = _env("MARCA_HERO_TITULO", "Todo para tu estación, en un solo lugar")
HERO_TEXTO = _env(
    "MARCA_HERO_TEXTO",
    "Cartuchos, tintas, máquinas y bioseguridad para tatuadores y estudios. "
    "Revisa el stock, pide online y retira en tienda. Cambia este texto por el del negocio.")
DESCRIPCION = _env(
    "MARCA_DESCRIPCION",
    "Insumos de tatuaje para profesionales: catálogo con stock, pedidos para "
    "retirar, cursos y programa de puntos. Cambia este texto por el de tu negocio.")

# --------------------------------------------------------------------------
# 2. DÓNDE ESTÁ Y CÓMO LO UBICAN
# --------------------------------------------------------------------------
CIUDAD = _env("MARCA_CIUDAD", "Tu Ciudad")
REGION = _env("MARCA_REGION", "Tu Región")
PAIS = _env("MARCA_PAIS", "Chile")
DIRECCION = _env("MARCA_DIRECCION", "Calle Principal 123")
HORARIO = _env("MARCA_HORARIO", "Lun–Vie · 11:00–20:00 || Sáb · 11:00–15:00")

CORREO = _env("MARCA_CORREO", "hola@insumostattoo.cl")
TELEFONO = _env("MARCA_TELEFONO", "+56 9 0000 0000")
# Solo dígitos, con código de país y sin el +. Es lo que pide wa.me.
WHATSAPP = _env("MARCA_WHATSAPP", "56900000000")
INSTAGRAM = _env("MARCA_INSTAGRAM", "")     # solo el usuario, sin @ ni URL
FACEBOOK = _env("MARCA_FACEBOOK", "")
DOMINIO = _env("MARCA_DOMINIO", "https://www.insumostattoo.cl")

# Google Maps. El Place ID («ChIJ...») activa «Dejar una reseña» en la sección
# del mapa. Se saca en developers.google.com/maps/documentation/places/web-service/place-id
# buscando el negocio. La nota («4,9») y el total de reseñas («144») se
# copian de la ficha de Google y se actualizan a mano de vez en cuando.
# Lo que quede vacío no se muestra.
GOOGLE_PLACE_ID = _env("MARCA_GOOGLE_PLACE_ID", "")
GOOGLE_NOTA = _env("MARCA_GOOGLE_NOTA", "")
GOOGLE_RESENAS = _env("MARCA_GOOGLE_RESENAS", "")

# --------------------------------------------------------------------------
# 3. EL PROGRAMA DE PUNTOS
# El sitio muestra precios duales: «$15.000 | 1.500 PT». Acá se define cómo se
# llaman esos puntos y cuántos pesos vale cada uno.
# --------------------------------------------------------------------------
PUNTOS_NOMBRE = _env("MARCA_PUNTOS_NOMBRE", "Puntos Tinta")
PUNTOS_SIGLA = _env("MARCA_PUNTOS_SIGLA", "PT")
PUNTOS_POR_PESO = int(_env("MARCA_PUNTOS_POR_PESO", "10"))   # 1 punto = $10

# --------------------------------------------------------------------------
# 4. LOS COLORES Y LAS IMÁGENES
# Estos cinco colores se inyectan como variables CSS y mandan sobre todo el
# sitio. No hay que buscar códigos de color en las hojas de estilo.
# --------------------------------------------------------------------------
COLOR_ACENTO = _env("MARCA_COLOR_ACENTO", "#161616")        # botones, enlaces: tinta negra
COLOR_ACENTO_HOVER = _env("MARCA_COLOR_ACENTO_HOVER", "#3A3A3A")
COLOR_ACENTO_OSCURO = _env("MARCA_COLOR_ACENTO_OSCURO", "#0B0B0B")  # fondos oscuros
COLOR_TEXTO = _env("MARCA_COLOR_TEXTO", "#1B1B1B")          # casi negro
COLOR_FONDO = _env("MARCA_COLOR_FONDO", "#F3F1ED")          # papel de transfer
COLOR_DESTACADO = _env("MARCA_COLOR_DESTACADO", "#C8102E")  # rojo de los puntos

LOGO = _env("MARCA_LOGO", "img/logo.png")
IMAGEN_HERO = _env("MARCA_IMAGEN_HERO", "img/hero.jpg")
IMAGEN_EQUIPO = _env("MARCA_IMAGEN_EQUIPO", "img/equipo.jpg")
IMAGEN_COMPARTIR = _env("MARCA_IMAGEN_COMPARTIR", "img/og-cover.jpg")
# Las ilustraciones decorativas de las esquinas. En false desaparecen todas y
# el sitio queda más sobrio, sin tocar ninguna plantilla.
# Vienen APAGADAS: la plantilla trae solo dibujos de marcador. Si la tienda
# tiene ilustraciones propias, se ponen en static/img/mascotas/ (mismos
# nombres de archivo) y se enciende con «si».
MASCOTAS = _env("MARCA_MASCOTAS", "no").lower() in ("1", "si", "sí", "true")

# --------------------------------------------------------------------------
# 5. LA SEGUNDA MARCA (opcional)
# Pensado para la tienda que además tiene un ESTUDIO con su propia identidad:
# una página aparte con sus servicios y precios (tatuajes, piercing). Con
# ACTIVA en «no», la página y su enlace desaparecen del sitio.
# --------------------------------------------------------------------------
SEGUNDA_ACTIVA = _env("MARCA2_ACTIVA", "no").lower() in ("1", "si", "sí", "true")
SEGUNDA_SLUG = _env("MARCA2_SLUG", "segunda-marca")   # no cambiar: es el de la base
SEGUNDA_NOMBRE = _env("MARCA2_NOMBRE", "Estudio Ejemplo")
SEGUNDA_LEMA = _env("MARCA2_LEMA", "Tatuajes y piercing")
SEGUNDA_DESCRIPCION = _env("MARCA2_DESCRIPCION",
                           "Nuestro estudio, en el mismo lugar: agenda tu sesión.")
SEGUNDA_COLOR = _env("MARCA2_COLOR", "#C8102E")
SEGUNDA_LOGO = _env("MARCA2_LOGO", "img/segunda-marca/logo.png")

# --------------------------------------------------------------------------
# 6. LA TIENDA (Shopify)
# OPCIONAL. Solo si la tienda ya vende con Shopify. Sin esto, la sección
# «Tienda online» no aparece y el catálogo propio (el de /admin/carta) es el
# que manda. El dominio va acá porque es público; el token, en el .env.
# --------------------------------------------------------------------------
TIENDA_URL = _env("SHOPIFY_DOMINIO", "")

# --------------------------------------------------------------------------
# 6b. LA RULETA DE PREMIOS
# Los colores de los gajos, en el orden en que se repiten en el sentido del
# reloj. Tres colores con 12 gajos calzan perfecto (12 es múltiplo de 3); con
# una cantidad que no lo sea, el último y el primero quedan iguales y juntos,
# y el panel lo avisa. El texto de cada gajo se pone blanco o negro solo,
# según qué se lea mejor sobre ese color.
#
# Las dos ilustraciones de arriba del puntero salen de static/ y el sello de
# abajo es el logo. Con MASCOTAS en false no se muestran.
# --------------------------------------------------------------------------
RULETA_COLORES = _env("MARCA_RULETA_COLORES", f"#161616,#FFFFFF,{COLOR_DESTACADO}")
RULETA_MASCOTA_IZQ = _env("MARCA_RULETA_MASCOTA_IZQ", "img/mascotas/brindis.png")
RULETA_MASCOTA_DER = _env("MARCA_RULETA_MASCOTA_DER", "img/mascotas/mano.png")

# --------------------------------------------------------------------------
# 7. EL CRÉDITO DEL PIE — FIJO, NO SE CONFIGURA
#
# No se quita, no se vuelve configurable y no se vacía por .env. Es la
# firma de quien hizo el sitio y es una decisión del autor: va en todas las
# instalaciones, en el footer (con el easter egg de las galletas) y en el
# JSON-LD de la landing.
#
# Antes salía de MARCA_CREDITO_TEXTO / MARCA_CREDITO_URL con valor vacío por
# defecto, y el resultado no era «no se muestra»: era un footer roto que
# decía «programado por , desarrollador en Tu Ciudad». Además usaba la ciudad
# del NEGOCIO, cuando la que corresponde es la de quien lo programó.
# --------------------------------------------------------------------------
CREDITO_TEXTO = "Sr. Jengibre"
CREDITO_URL = "https://www.linkedin.com/in/sebapoba/"
CREDITO_CIUDAD = "Osorno"
CREDITO_PAIS = "Chile"


# ==========================================================================
# De acá para abajo NO hay nada que configurar: se arma el diccionario que
# ven las plantillas.
# ==========================================================================

def _url_tienda(dominio):
    if not dominio:
        return ""
    return dominio if dominio.startswith("http") else "https://" + dominio


NEGOCIO = {
    "slug": SLUG,
    "nombre": NOMBRE,
    "nombre_corto": NOMBRE_CORTO,
    "tag": TAG,
    "lema": LEMA,
    "pwa_nombre": PWA_NOMBRE,
    "hero_titulo": HERO_TITULO,
    "hero_texto": HERO_TEXTO,
    "descripcion": DESCRIPCION,

    "ciudad": CIUDAD,
    "region": REGION,
    "pais": PAIS,
    "direccion": DIRECCION,
    # «Lun–Sáb · 9:00–20:00 || Dom · cerrado» se parte en dos líneas.
    "horario": [t.strip() for t in HORARIO.split("||") if t.strip()],

    "correo": CORREO,
    "telefono": TELEFONO,
    "whatsapp": WHATSAPP,
    "whatsapp_url": ("https://wa.me/" + WHATSAPP) if WHATSAPP else "",
    "instagram": INSTAGRAM,
    "instagram_url": ("https://www.instagram.com/" + INSTAGRAM + "/") if INSTAGRAM else "",
    "facebook": FACEBOOK,
    "facebook_url": ("https://www.facebook.com/" + FACEBOOK) if FACEBOOK else "",
    "dominio": DOMINIO.rstrip("/"),
    "google": {
        "place_id": GOOGLE_PLACE_ID,
        "nota": GOOGLE_NOTA,
        "resenas": GOOGLE_RESENAS,
        "resena_url": ("https://search.google.com/local/writereview?placeid=" + GOOGLE_PLACE_ID) if GOOGLE_PLACE_ID else "",
        "resenas_url": ("https://search.google.com/local/reviews?placeid=" + GOOGLE_PLACE_ID) if GOOGLE_PLACE_ID else "",
    },

    "puntos": {
        "nombre": PUNTOS_NOMBRE,
        "sigla": PUNTOS_SIGLA,
        "por_peso": PUNTOS_POR_PESO,
    },

    "colores": {
        "acento": COLOR_ACENTO,
        "acento_hover": COLOR_ACENTO_HOVER,
        "acento_oscuro": COLOR_ACENTO_OSCURO,
        "texto": COLOR_TEXTO,
        "fondo": COLOR_FONDO,
        "destacado": COLOR_DESTACADO,
    },

    "logo": LOGO,
    "imagen_hero": IMAGEN_HERO,
    "imagen_equipo": IMAGEN_EQUIPO,
    "imagen_compartir": IMAGEN_COMPARTIR,
    "mascotas": MASCOTAS,

    "segunda": {
        "activa": SEGUNDA_ACTIVA,
        "slug": SEGUNDA_SLUG,
        "nombre": SEGUNDA_NOMBRE,
        "lema": SEGUNDA_LEMA,
        "descripcion": SEGUNDA_DESCRIPCION,
        "color": SEGUNDA_COLOR,
        "logo": SEGUNDA_LOGO,
    },

    "tienda_url": _url_tienda(TIENDA_URL),
    "ruleta": {
        "colores": [c.strip() for c in RULETA_COLORES.split(",") if c.strip()],
        "mascota_izq": RULETA_MASCOTA_IZQ,
        "mascota_der": RULETA_MASCOTA_DER,
    },

    "credito": {
        "texto": CREDITO_TEXTO,
        "url": CREDITO_URL,
        "ciudad": CREDITO_CIUDAD,
        "pais": CREDITO_PAIS,
    },
}


def en_puntos(pesos):
    """
    Cuántos puntos equivalen a ese precio. Es la mitad del precio dual que se
    muestra en todo el catálogo. Si algún día la conversión deja de ser una
    división, se cambia acá y el sitio entero sigue.
    """
    try:
        return round(int(pesos) / PUNTOS_POR_PESO)
    except (TypeError, ValueError):
        return 0
