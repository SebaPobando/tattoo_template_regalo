# ==========================================================================
# calendario.py — llevar un taller al calendario de la persona
#
# Dos formatos, porque la gente usa dos mundos:
#
#   google_url()  el enlace «Agregar a Google Calendar». Abre Google Calendar
#                 con el evento ya escrito; la persona toca Guardar. No pide
#                 clave de Google ni permisos: es una URL pública de Google.
#   ics()         el archivo .ics (iCalendar), para el calendario del iPhone,
#                 Outlook y cualquier otro. El teléfono lo abre directo.
#
# Las fechas entran en UTC (como vienen de MySQL) y salen en UTC con la «Z»:
# cada calendario las muestra en la hora de quien lo abre, así que una
# persona de vacaciones en otro país igual ve la hora correcta.
#
# Lo que NO hace: meter el evento solo en el calendario de nadie. Eso pide
# la API de Google Calendar con la cuenta del local autorizada; acá la
# persona toca un botón y listo.
# ==========================================================================

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

# Si el evento no tiene hora de término, se agenda con esta duración.
HORAS_POR_DEFECTO = 2

ZONA = "America/Santiago"


def _fin(inicio, fin):
    return fin if fin and fin > inicio else inicio + timedelta(hours=HORAS_POR_DEFECTO)


def _utc(fecha):
    """'20261024T220000Z' — el formato que piden Google y el .ics."""
    if fecha.tzinfo is not None:
        fecha = fecha.astimezone(timezone.utc).replace(tzinfo=None)
    return fecha.strftime("%Y%m%dT%H%M%SZ")


def google_url(titulo, inicio, fin=None, detalle="", lugar=""):
    """El enlace que abre Google Calendar con el evento listo para guardar."""
    params = {
        "action": "TEMPLATE",
        "text": titulo,
        "dates": f"{_utc(inicio)}/{_utc(_fin(inicio, fin))}",
        "details": detalle or "",
        "location": lugar or "",
        "ctz": ZONA,
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


# ----------------------------------------------------------------- el .ics

def _escapar(texto):
    """RFC 5545: la barra, el punto y coma, la coma y los saltos de línea."""
    return ((texto or "")
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\r\n", "\n")
            .replace("\n", "\\n"))


def _doblar(linea):
    """
    Las líneas de un .ics no pueden pasar de 75 BYTES: las largas se parten
    y la continuación empieza con un espacio. Se corta por bytes y nunca a
    la mitad de una letra con tilde, que en UTF-8 ocupa dos.
    """
    datos = linea.encode("utf-8")
    if len(datos) <= 75:
        return linea
    partes, actual, limite = [], b"", 75
    for letra in linea:
        b = letra.encode("utf-8")
        if len(actual) + len(b) > limite:
            partes.append(actual.decode("utf-8"))
            actual, limite = b"", 74      # la continuación lleva el espacio
        actual += b
    partes.append(actual.decode("utf-8"))
    return "\r\n ".join(partes)


def ics(uid, titulo, inicio, fin=None, detalle="", lugar="", url="",
        aviso_horas=24):
    """
    El archivo .ics de UN evento, como texto.

    `uid` tiene que ser estable (el código del voucher, por ejemplo): si la
    persona lo abre dos veces, su calendario actualiza el mismo evento en vez
    de duplicarlo. `aviso_horas` deja un recordatorio; 0 para no ponerlo.
    """
    lineas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Agenda de cursos//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_utc(datetime.now(timezone.utc))}",
        f"DTSTART:{_utc(inicio)}",
        f"DTEND:{_utc(_fin(inicio, fin))}",
        f"SUMMARY:{_escapar(titulo)}",
    ]
    if detalle:
        lineas.append(f"DESCRIPTION:{_escapar(detalle)}")
    if lugar:
        lineas.append(f"LOCATION:{_escapar(lugar)}")
    if url:
        lineas.append(f"URL:{url}")
    if aviso_horas:
        lineas += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_escapar(titulo)}",
            f"TRIGGER:-PT{int(aviso_horas)}H",
            "END:VALARM",
        ]
    lineas += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_doblar(l) for l in lineas) + "\r\n"
