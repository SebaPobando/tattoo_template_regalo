# ==========================================================================
# tiempo.py — UTC en la base, hora de Chile en pantalla
#
# La base guarda DATETIME en UTC, y eso no es capricho: Chile cambia de huso
# dos veces al año (UTC-4 en invierno, UTC-3 en verano). Si guardaras hora
# local, la noche en que se atrasa el reloj existen dos veces las 23:30 y no
# hay forma de saber a cuál se refiere una fila. Con UTC no hay ambigüedad y
# la conversión a pantalla es un cálculo, no una adivinanza.
#
# Regla: UTC entra y sale de la base. La hora de Chile solo existe en el
#        formulario del admin y en lo que ve la gente.
# ==========================================================================

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# zoneinfo no trae las zonas horarias: las lee del sistema operativo. Linux y
# macOS las traen; WINDOWS NO TRAE NINGUNA. Ahí hay que instalar el paquete
# 'tzdata' de PyPI, que es esa misma base de datos empaquetada.
#
# Sin este mensaje, la app revienta al arrancar con un traceback de treinta
# líneas que termina en ZoneInfoNotFoundError y no dice qué hacer.
#
# Y NO se cae a un desfase fijo de -3 o -4 horas a propósito: eso es
# exactamente el error que guardar en UTC viene a evitar. Un desfase fijo
# acierta media parte del año y se equivoca la otra media, en silencio.
try:
    CHILE = ZoneInfo("America/Santiago")
except ZoneInfoNotFoundError as e:  # pragma: no cover
    raise RuntimeError(
        "No encuentro la base de datos de zonas horarias.\n"
        "\n"
        "  Windows no trae husos horarios y zoneinfo los lee del sistema.\n"
        "  Se arregla instalando el paquete que los trae:\n"
        "\n"
        "      pip install -r requirements.txt\n"
        "\n"
        "  (o, solo eso:  pip install tzdata)\n"
    ) from e

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def ahora_utc():
    """Sin tzinfo, para comparar con lo que devuelve MySQL."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def local_a_utc(texto):
    """
    Toma lo que escribió el admin en un <input type="datetime-local">
    ('2026-09-20T19:00') y devuelve el DATETIME en UTC que va a la base.

    Devuelve None si el texto no sirve, para que el controlador avise en vez
    de guardar una fecha inventada.
    """
    if not texto:
        return None
    try:
        ingenua = datetime.fromisoformat(texto.strip())
    except ValueError:
        return None
    # fold=0 resuelve la hora repetida del cambio de horario eligiendo la
    # primera de las dos. Es una convención: lo importante es que no falle.
    con_zona = ingenua.replace(tzinfo=CHILE, fold=0)
    return con_zona.astimezone(timezone.utc).replace(tzinfo=None)


def utc_a_local(fecha_utc):
    if not fecha_utc:
        return None
    if fecha_utc.tzinfo is None:
        fecha_utc = fecha_utc.replace(tzinfo=timezone.utc)
    return fecha_utc.astimezone(CHILE)


def para_formulario(fecha_utc):
    """El formato que entiende <input type="datetime-local">."""
    local = utc_a_local(fecha_utc)
    return local.strftime("%Y-%m-%dT%H:%M") if local else ""


def largo(fecha_utc):
    """'jueves 20 de septiembre, 19:00'"""
    d = utc_a_local(fecha_utc)
    if not d:
        return ""
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}, {d:%H:%M}"


def corto(fecha_utc):
    """'20 sep · 19:00'"""
    d = utc_a_local(fecha_utc)
    if not d:
        return ""
    return f"{d.day} {MESES[d.month - 1][:3]} · {d:%H:%M}"


def dia_y_mes(fecha_utc):
    """Para el cuadradito de calendario: ('20', 'SEP')."""
    d = utc_a_local(fecha_utc)
    if not d:
        return ("", "")
    return (f"{d.day:02d}", MESES[d.month - 1][:3].upper())


def hora(fecha_utc):
    """'19:00' — para cuando la fecha ya se muestra aparte, en el
    encabezado de un grupo por día."""
    d = utc_a_local(fecha_utc)
    return f"{d:%H:%M}" if d else ""


def dia_relativo(fecha_utc):
    """
    'Hoy', 'Ayer', o 'jueves 25 de septiembre' — para el encabezado de un
    grupo de pedidos por día, sin obligar a leer la fecha completa cuando
    es reciente.
    """
    d = utc_a_local(fecha_utc)
    if not d:
        return ""
    hoy = utc_a_local(ahora_utc()).date()
    delta = (d.date() - hoy).days
    if delta == 0:
        return "Hoy"
    if delta == -1:
        return "Ayer"
    # Mañana lo usan las franjas de los pedidos para retiro, que miran
    # hacia adelante; los grupos de pedidos de la tienda nunca llegan acá.
    if delta == 1:
        return "Mañana"
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


# Los cuatro cortes con que el panel de pedidos deja mirar las ventas. El
# orden es el que se pinta en pantalla, de más fino a más grueso.
PERIODOS = ("dia", "semana", "mes", "anio")


def periodo_de(fecha_utc, periodo="dia"):
    """
    (clave, etiqueta) del período en que cae esa fecha, en hora de Chile.

    La CLAVE identifica el período sin ambigüedad —('mes', 2026, 9)— y es con
    lo que se agrupa; la ETIQUETA es solo lo que se muestra. Van separadas a
    propósito: agrupar por el texto se rompe solo, porque «25 de septiembre»
    se escribe igual en 2025 que en 2026 y los pedidos de los dos años
    terminarían sumados en la misma pila.

    Una fecha ilegible cae en su propia clave y sin etiqueta, para que no se
    mezcle con un período real.
    """
    d = utc_a_local(fecha_utc)
    if not d:
        return ("sin-fecha",), ""

    f = d.date()
    hoy = utc_a_local(ahora_utc()).date()

    if periodo == "semana":
        # La semana va de lunes a domingo, como el calendario de acá.
        lunes = f - timedelta(days=f.weekday())
        lunes_de_hoy = hoy - timedelta(days=hoy.weekday())
        semanas = (lunes_de_hoy - lunes).days // 7
        if semanas == 0:
            etiqueta = "Esta semana"
        elif semanas == 1:
            etiqueta = "Semana pasada"
        else:
            domingo = lunes + timedelta(days=6)
            if lunes.month == domingo.month:
                etiqueta = (f"Semana del {lunes.day} al {domingo.day} "
                            f"de {MESES[domingo.month - 1]}")
            else:
                etiqueta = (f"Semana del {lunes.day} de {MESES[lunes.month - 1]} "
                            f"al {domingo.day} de {MESES[domingo.month - 1]}")
        return ("semana", lunes.year, lunes.month, lunes.day), etiqueta

    if periodo == "mes":
        meses = (hoy.year - f.year) * 12 + (hoy.month - f.month)
        if meses == 0:
            etiqueta = "Este mes"
        elif meses == 1:
            etiqueta = "Mes pasado"
        elif f.year == hoy.year:
            etiqueta = MESES[f.month - 1]
        else:
            etiqueta = f"{MESES[f.month - 1]} {f.year}"
        return ("mes", f.year, f.month), etiqueta

    if periodo == "anio":
        return ("anio", f.year), ("Este año" if f.year == hoy.year else str(f.year))

    return ("dia", f.year, f.month, f.day), dia_relativo(fecha_utc)


def fecha(fecha_utc):
    """
    '10 de septiembre'. Sin hora: para el muro de deseos, donde importa
    cuándo se escribió pero no a qué minuto.
    """
    d = utc_a_local(fecha_utc)
    if not d:
        return ""
    return f"{d.day} de {MESES[d.month - 1]}"
