# ==========================================================================
# correo.py — envío de correos
#
# TODO el envío vive acá. Ningún otro archivo importa smtplib. La idea es la
# misma que en seguridad.py: si algún día cambiamos de proveedor, se toca
# este archivo y nada más.
#
# Dos modos, y los decide el entorno:
#
#   SIN SMTP_HOST  ->  buzón de desarrollo. El correo se escribe como archivo
#                      en la carpeta buzon/ y el enlace se imprime en el log.
#                      Abres el .html en el navegador y sigues el flujo sin
#                      necesitar credenciales de nada.
#
#   CON SMTP_HOST  ->  envío real por SMTP con STARTTLS.
#
# REGLA: enviar() NUNCA lanza excepción. Un correo que no sale no puede
# tumbar un registro ni devolver un 500. Devuelve True/False y deja el
# problema en el log. Quien llama decide qué le dice a la persona — y en los
# flujos de recuperación conviene que le diga lo mismo pase lo que pase, para
# no delatar qué correos existen.
# ==========================================================================

import os
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path


def _entorno():
    """
    Se lee en cada llamada y no una vez al importar: así los tests pueden
    cambiar el entorno, y en desarrollo no hay que reiniciar Flask para que
    tome un .env recién editado.
    """
    return {
        "host": (os.environ.get("SMTP_HOST") or "").strip(),
        "puerto": int(os.environ.get("SMTP_PORT") or 587),
        "usuario": os.environ.get("SMTP_USER") or "",
        "clave": os.environ.get("SMTP_PASSWORD") or "",
        "desde": os.environ.get("CORREO_DESDE") or "contacto@tunegocio.cl",
        "nombre": os.environ.get("CORREO_NOMBRE") or "la tienda",
        "buzon": Path(os.environ.get("CORREO_BUZON") or "buzon"),
    }


def hay_envio_real():
    """True si está configurado un SMTP. Útil para avisar en pantalla."""
    return bool(_entorno()["host"])


def _armar(destino, asunto, texto, html, cfg):
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = formataddr((cfg["nombre"], cfg["desde"]))
    msg["To"] = destino
    msg.set_content(texto)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def _nombre_archivo(destino, asunto):
    marca = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    limpio = re.sub(r"[^a-zA-Z0-9]+", "-", f"{destino}-{asunto}").strip("-").lower()
    return f"{marca}-{limpio[:60]}"


def _al_buzon(destino, asunto, texto, html, cfg, logger=None):
    """
    Escribe el correo en disco en vez de mandarlo. El .html se abre en el
    navegador; el .txt sirve para copiar el enlace a mano.
    """
    carpeta = cfg["buzon"]
    carpeta.mkdir(parents=True, exist_ok=True)
    base = carpeta / _nombre_archivo(destino, asunto)

    cabecera = (f"Para: {destino}\nDe: {cfg['nombre']} <{cfg['desde']}>\n"
                f"Asunto: {asunto}\n" + "-" * 60 + "\n\n")
    base.with_suffix(".txt").write_text(cabecera + texto, encoding="utf-8")
    if html:
        base.with_suffix(".html").write_text(html, encoding="utf-8")

    if logger:
        # El enlace al log: en desarrollo es lo único que uno quiere ver.
        enlaces = re.findall(r"https?://\S+", texto)
        logger.info("[correo] buzón -> %s", base.with_suffix(".txt"))
        for e in enlaces:
            logger.info("[correo] enlace -> %s", e)
    return True


def enviar(destino, asunto, texto, html=None, logger=None):
    """
    Manda un correo. Devuelve True si salió (o si quedó en el buzón de
    desarrollo) y False si falló. No lanza nunca.
    """
    cfg = _entorno()

    if not destino or "@" not in destino:
        if logger:
            logger.warning("[correo] destino inválido: %r", destino)
        return False

    if not cfg["host"]:
        return _al_buzon(destino, asunto, texto, html, cfg, logger)

    try:
        msg = _armar(destino, asunto, texto, html, cfg)
        contexto = ssl.create_default_context()
        if cfg["puerto"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["puerto"], context=contexto, timeout=15) as s:
                if cfg["usuario"]:
                    s.login(cfg["usuario"], cfg["clave"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["puerto"], timeout=15) as s:
                s.starttls(context=contexto)
                if cfg["usuario"]:
                    s.login(cfg["usuario"], cfg["clave"])
                s.send_message(msg)
        if logger:
            logger.info("[correo] enviado a %s (%s)", destino, asunto)
        return True
    except Exception as e:
        # A propósito atrapamos todo: DNS caído, credenciales malas, timeout,
        # el proveedor rechazando el remitente. Nada de eso justifica romperle
        # el registro a alguien.
        if logger:
            logger.error("[correo] falló el envío a %s: %s", destino, e)
        return False
