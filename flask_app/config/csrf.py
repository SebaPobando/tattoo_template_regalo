# ==========================================================================
# csrf.py — token anti-CSRF, sin dependencias
#
# Qué evita: que una página ajena haga que TU navegador envíe un formulario
# a esta app usando tu cookie de sesión. Sin protección, bastaría con que
# abrieras un enlace cualquiera estando logueado como admin para que alguien
# borrara productos de tu carta.
#
# Nota: la cookie de sesión ya va con SameSite=Lax, y eso por sí solo bloquea
# el ataque clásico. Esto es defensa en profundidad — barata, y acá hay un
# botón que borra.
# ==========================================================================

import secrets

from flask import session

CLAVE = "_csrf"


def token():
    """Devuelve el token de esta sesión, creándolo la primera vez."""
    if CLAVE not in session:
        session[CLAVE] = secrets.token_urlsafe(32)
    return session[CLAVE]


def valido(enviado):
    """
    Compara en tiempo constante con compare_digest: una comparación normal
    con == termina apenas encuentra el primer carácter distinto, y ese
    diferencial de tiempo se puede medir para adivinar el token byte a byte.
    """
    esperado = session.get(CLAVE)
    if not esperado or not enviado:
        return False
    return secrets.compare_digest(str(esperado), str(enviado))
