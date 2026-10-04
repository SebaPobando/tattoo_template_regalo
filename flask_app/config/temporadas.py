# ==========================================================================
# temporadas.py — las mascotas de temporada (Halloween, Navidad...)
#
# Durante una temporada, las mascotas del sitio se cambian solas por las de
# esa fecha y al terminar vuelven las de siempre, sin tocar nada. Las fechas
# son mes y día y se repiten todos los años: Halloween va del 1 al 31 de
# octubre, y el 1 de noviembre el sitio amanece con las mascotas normales.
#
# Las plantillas NO escriben la ruta de la imagen: piden
#     {{ mascota('sirviendo.png', 'hero') }}
# y esto devuelve la URL que toca hoy. Se busca primero por LUGAR (para que
# la portada no repita el mismo disfraz en tres secciones) y después por
# ARCHIVO (para el resto de las páginas). Lo que la temporada no reemplaza
# sale con la mascota normal.
#
# La fecha es la de Chile (config/tiempo.py), no la del servidor: Railway
# corre en UTC y el 31 a las 21:00 de acá allá ya es 1 de noviembre.
#
# Una temporada también puede cambiar COLORES: las variables CSS de
# `colores` se pisan en las páginas públicas (portada, tienda, cuenta...)
# mientras dure. El panel de admin no cambia: es una herramienta de
# trabajo, no una vitrina. Ver templates/_temporada.html.
#
# Para probar o apagarla sin esperar a la fecha, en el .env:
#     TEMPORADA=halloween   fuerza esa temporada
#     TEMPORADA=no          apaga todas
# ==========================================================================

import os

from flask import url_for

from flask_app.config import tiempo

CARPETA = "img/mascotas"

# Vacía por defecto: el negocio no tiene mascotas de temporada hasta que
# las dibuje. Para agregar una, copia este ejemplo, pon las imágenes en su
# carpeta y descoméntalo. Lo que no se nombre sigue con la mascota normal.
TEMPORADAS = [
    # {
    #     "nombre": "halloween",
    #     "desde": (10, 1),     # (mes, día), los dos incluidos
    #     "hasta": (10, 31),
    #     "carpeta": "img/mascotas/halloween",
    #     "colores": {          # opcional: variables CSS de la temporada
    #         "--accent": "#2E1F3B",
    #         "--accent-hover": "#45305A",
    #         "--lp-forest": "#2E1F3B",
    #         "--surface-forest": "#2E1F3B",
    #         "--points": "#D9651F",
    #         "--lp-gold": "#D9651F",
    #         "--lp-gold-bg": "#FBE0C6",
    #     },
    #     "por_lugar": {        # secciones de la portada
    #         "hero": "calabaza.png",
    #         "about": "vampiro.png",
    #         "carta": "frankenstein.png",
    #         "tienda": "momia.png",
    #         "talleres": "fantasma.png",
    #         "agenda": "momia.png",
    #         "muro": "fantasma.png",
    #         "puntos": "calabaza.png",
    #         "promo": "vampiro.png",
    #         "promo-burbuja": "fantasma.png",
    #     },
    #     "por_archivo": {      # el resto de las páginas
    #         "sirviendo.png": "calabaza.png",
    #         "mano.png": "fantasma.png",
    #     },
    # },
]


def _en_rango(hoy, desde, hasta):
    md = (hoy.month, hoy.day)
    if desde <= hasta:
        return desde <= md <= hasta
    # Una temporada que cruza el año (15 de diciembre al 6 de enero).
    return md >= desde or md <= hasta


def actual(hoy=None):
    """La temporada vigente hoy en Chile, o None."""
    forzada = (os.environ.get("TEMPORADA") or "").strip().lower()
    if forzada in ("no", "ninguna", "0"):
        return None
    if forzada:
        return next((t for t in TEMPORADAS if t["nombre"] == forzada), None)
    if hoy is None:
        hoy = tiempo.utc_a_local(tiempo.ahora_utc()).date()
    return next((t for t in TEMPORADAS if _en_rango(hoy, t["desde"], t["hasta"])), None)


def mascota(archivo, lugar=None):
    """La URL de la mascota que toca mostrar hoy en ese lugar."""
    t = actual()
    if t:
        cambio = t["por_lugar"].get(lugar) if lugar else None
        cambio = cambio or t["por_archivo"].get(archivo)
        if cambio:
            return url_for("static", filename=t["carpeta"] + "/" + cambio)
    return url_for("static", filename=CARPETA + "/" + archivo)
