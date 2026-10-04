# ==========================================================================
# qr.py — el QR del voucher
#
# TODO el trato con la librería de QR vive acá. La idea es la misma que en
# seguridad.py y en correo.py: una sola puerta, y si algún día se cambia de
# librería se toca este archivo y nada más.
#
# LA IMPORTACIÓN ES OPCIONAL A PROPÓSITO. `qrcode` está en requirements.txt,
# pero si alguien levanta el proyecto sin instalarlo, el voucher tiene que
# seguir funcionando: el código escrito con letras grandes es lo que de
# verdad vale en el mesón, y el QR es comodidad. Un ImportError al arrancar
# dejaría la app entera abajo por un adorno.
#
# Se genera SVG y no PNG: no necesita Pillow, pesa menos que la imagen, se
# imprime nítido a cualquier tamaño y se puede incrustar en el HTML sin
# guardar ningún archivo ni servir ninguna ruta nueva.
# ==========================================================================

import io
import re

try:
    import qrcode
    import qrcode.image.svg
    HAY_QR = True
except ImportError:                                   # pragma: no cover
    HAY_QR = False


def disponible():
    return HAY_QR


def svg(texto, borde=2):
    """
    Devuelve el SVG del QR como texto listo para incrustar, o None si la
    librería no está instalada o el texto viene vacío.

    Se le quita la declaración <?xml ...?>: es válida en un archivo suelto,
    pero dentro de un HTML sobra y algunos navegadores la muestran como texto.
    """
    if not (HAY_QR and texto):
        return None
    try:
        codigo = qrcode.QRCode(
            # ERROR_CORRECT_M aguanta ~15% de daño: suficiente para una
            # pantalla con huellas o un papel doblado, sin agrandar el dibujo
            # como lo haría el nivel H.
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            border=borde,
        )
        codigo.add_data(texto)
        codigo.make(fit=True)
        imagen = codigo.make_image(image_factory=qrcode.image.svg.SvgPathImage)
        buf = io.BytesIO()
        imagen.save(buf)
        marcado = buf.getvalue().decode("utf-8")
        marcado = re.sub(r"<\?xml[^>]*\?>\s*", "", marcado)
        # El SVG trae width/height fijos en milímetros; mejor que mande el
        # CSS de la página, que sabe cuánto espacio hay.
        marcado = re.sub(r'\s(width|height)="[^"]*"', "", marcado, count=2)
        return marcado
    except Exception:                                 # pragma: no cover
        # Un QR que no sale no puede tumbar el voucher.
        return None
