# ==========================================================================
# enlaces.py — los enlaces con token que van dentro de un correo
#
# Verificar el correo y restablecer la contraseña necesitan lo mismo: un
# enlace que pruebe que quien lo abre tiene acceso a esa casilla, que expire,
# y que no se pueda fabricar.
#
# NO hay tabla de tokens. El token es un dato firmado con SECRET_KEY
# (itsdangerous, que ya viene con Flask): lleva adentro a quién apunta y
# cuándo se emitió, y la firma impide tocarlo. Sin tabla no hay migración, no
# hay filas basura que limpiar, y no hay estado que se desincronice.
#
# El precio de no tener tabla es que un token no se puede "marcar como
# usado". Eso se resuelve con una HUELLA: el token guarda un resumen del
# estado que va a cambiar cuando se use.
#
#   - Restablecer contraseña: la huella es el hash actual de la contraseña.
#     Al cambiarla, el hash cambia y todos los enlaces viejos mueren solos.
#     Eso da un solo uso de verdad, y además invalida los enlaces pendientes
#     cuando alguien cambia su clave por otra vía.
#
#   - Verificar correo: la huella es el correo. Si la persona cambia de
#     correo, el enlace anterior deja de servir. Reusarlo es inofensivo:
#     verificar dos veces es lo mismo que verificar una.
#
#   - Invitación de personal: igual que restablecer (la huella es el hash,
#     que en una cuenta recién creada es NULL), pero dura días y no minutos:
#     se manda por WhatsApp y quizás se abre mañana. Muere al crear la
#     contraseña, igual que el de restablecer.
#
# Las tres cosas usan SALES distintas. Sin eso, un token de verificación
# serviría para restablecer una contraseña.
# ==========================================================================

import hashlib

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SAL_VERIFICACION = "lp-verificar-email-v1"
SAL_RESET = "lp-reset-password-v1"
SAL_INVITACION = "lp-invitacion-personal-v1"

# Cuánto vive cada enlace. El de contraseña dura poco a propósito: mientras
# está vivo, quien tenga acceso a esa casilla puede tomarse la cuenta.
HORAS_VERIFICACION = 48
MINUTOS_RESET = 30


def _serializador(sal):
    return URLSafeTimedSerializer(current_app.secret_key, salt=sal)


def _huella(valor):
    """Resumen corto y estable. No necesita ser reversible."""
    return hashlib.sha256((valor or "").encode("utf-8")).hexdigest()[:16]


# ----------------------------------------------------------- verificación

def token_verificacion(usuario_id, email):
    return _serializador(SAL_VERIFICACION).dumps(
        {"uid": int(usuario_id), "h": _huella(email)}
    )


def leer_verificacion(token):
    """
    Devuelve (usuario_id, huella_email) o (None, motivo).

    motivo es "expirado" o "invalido", para poder mostrar mensajes distintos:
    un enlace vencido se resuelve pidiendo otro, uno inválido no.
    """
    try:
        datos = _serializador(SAL_VERIFICACION).loads(
            token, max_age=HORAS_VERIFICACION * 3600)
    except SignatureExpired:
        return None, "expirado"
    except (BadSignature, Exception):
        return None, "invalido"
    if not isinstance(datos, dict) or "uid" not in datos:
        return None, "invalido"
    return datos["uid"], datos.get("h")


def verificacion_corresponde(datos_huella, email):
    return datos_huella == _huella(email)


# ------------------------------------------------------------------ reset

def token_reset(usuario_id, password_hash):
    """
    password_hash puede venir en None (un invitado que nunca creó clave).
    La huella de None es estable, así que el enlace igual funciona y muere
    en cuanto se cree la primera contraseña.
    """
    return _serializador(SAL_RESET).dumps(
        {"uid": int(usuario_id), "h": _huella(password_hash)}
    )


def leer_reset(token):
    """Devuelve (usuario_id, huella) o (None, motivo)."""
    try:
        datos = _serializador(SAL_RESET).loads(token, max_age=MINUTOS_RESET * 60)
    except SignatureExpired:
        return None, "expirado"
    except (BadSignature, Exception):
        return None, "invalido"
    if not isinstance(datos, dict) or "uid" not in datos:
        return None, "invalido"
    return datos["uid"], datos.get("h")


def reset_corresponde(datos_huella, password_hash):
    """
    False significa que la contraseña ya cambió desde que se emitió el
    enlace: o alguien lo usó, o la cambió por otro lado. En los dos casos
    este enlace ya no vale.
    """
    return datos_huella == _huella(password_hash)


# --- Invitación de personal -------------------------------------------------
# El admin crea la cuenta de un barista y le manda este enlace para que elija
# su contraseña. El admin nunca la conoce.

HORAS_INVITACION = 72


def token_invitacion(usuario_id, password_hash):
    return _serializador(SAL_INVITACION).dumps(
        {"uid": int(usuario_id), "h": _huella(password_hash)}
    )


def leer_invitacion(token):
    """Devuelve (usuario_id, huella) o (None, motivo). Como leer_reset."""
    try:
        datos = _serializador(SAL_INVITACION).loads(
            token, max_age=HORAS_INVITACION * 3600)
    except SignatureExpired:
        return None, "expirado"
    except (BadSignature, Exception):
        return None, "invalido"
    if not isinstance(datos, dict) or "uid" not in datos:
        return None, "invalido"
    return datos["uid"], datos.get("h")
