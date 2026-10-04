# ==========================================================================
# rut.py — RUT chileno: normalizar, validar y formatear
#
# Existe una versión de esto en account.js, y esa NO cuenta. La validación
# del navegador es una cortesía para el usuario: cualquiera puede desactivar
# JavaScript o mandar el POST con curl. Lo que decide es el servidor.
#
# El RUT se guarda SIEMPRE como '12345678-9': sin puntos, con guion, con el
# dígito verificador en mayúscula. Formatear con puntos es cosa de la vista.
# Y nunca como INT: el dígito puede ser K y hay RUTs con ceros a la izquierda.
# ==========================================================================

import re


class RutInvalido(ValueError):
    pass


def limpiar(valor):
    """Deja solo dígitos y la K final. '12.345.678-k' -> '123456789K'... no:
    devuelve ('12345678', 'K') separando cuerpo y dígito verificador."""
    crudo = re.sub(r"[^0-9kK]", "", valor or "").upper()
    if len(crudo) < 2:
        raise RutInvalido("El RUT está incompleto.")
    return crudo[:-1], crudo[-1]


def digito_esperado(cuerpo):
    """
    Módulo 11. Se recorre el cuerpo de derecha a izquierda multiplicando por
    la serie 2,3,4,5,6,7 que se repite, se suma, y el dígito es 11 menos el
    resto: 11 -> 0, 10 -> K.
    """
    suma, multiplicador = 0, 2
    for caracter in reversed(cuerpo):
        suma += int(caracter) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1

    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def normalizar(valor):
    """
    Devuelve el RUT en la forma que se guarda: '12345678-9'.
    Lanza RutInvalido si no calza el dígito verificador.
    """
    cuerpo, verificador = limpiar(valor)

    if not cuerpo.isdigit():
        raise RutInvalido("El RUT solo puede llevar números antes del guion.")

    # Los ceros a la izquierda se quitan ANTES de medir el largo. Si no,
    # '0011111111-1' se rechazaría por largo siendo el mismo RUT que
    # '11111111-1'. Además, guardarlos crearía dos filas para una persona.
    cuerpo = cuerpo.lstrip("0") or "0"

    # Un RUT chileno de una persona viva tiene entre 6 y 8 dígitos de cuerpo.
    # Menos de 6 es casi seguro un error de tipeo, no un RUT antiguo.
    if not 6 <= len(cuerpo) <= 8:
        raise RutInvalido("Ese RUT no tiene un largo válido.")

    if verificador != digito_esperado(cuerpo):
        raise RutInvalido("El RUT no es válido: revisa el dígito verificador.")

    return f"{cuerpo}-{verificador}"


def formatear(rut_guardado):
    """'12345678-9' -> '12.345.678-9'. Solo para mostrar."""
    if not rut_guardado or "-" not in rut_guardado:
        return rut_guardado or ""
    cuerpo, verificador = rut_guardado.split("-", 1)
    return f"{int(cuerpo):,}".replace(",", ".") + f"-{verificador}"


def es_valido(valor):
    try:
        normalizar(valor)
        return True
    except (RutInvalido, ValueError):
        return False
