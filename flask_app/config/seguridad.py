# ==========================================================================
# seguridad.py — hashing de contraseñas
#
# TODO el manejo de contraseñas vive acá. Ningún otro archivo importa bcrypt.
# Esa es la idea: si algún día cambiamos de algoritmo, se toca este archivo
# y nada más. Los hashes viejos siguen funcionando y se van actualizando
# solos a medida que cada persona inicia sesión (ver necesita_rehash).
#
# Hoy: bcrypt con cost 12.
#
# Nota honesta: OWASP hoy prefiere Argon2id y considera bcrypt una opción de
# sistemas heredados. bcrypt con cost 12 no es una vulnerabilidad — es una
# capa menos de resistencia frente a ataques con GPU. Si algún día quieres
# migrar, el cambio está acotado a este archivo.
# ==========================================================================

import bcrypt

COSTO = 12          # 10 es el mínimo que pide OWASP. 12 ≈ 280 ms por hash.
MAX_BYTES = 72      # límite duro de bcrypt


class ContrasenaMuyLarga(ValueError):
    """La contraseña excede lo que bcrypt puede procesar."""


# Hash de descarte, para gastar el mismo tiempo cuando el usuario no existe.
# Sin esto, un atacante mide cuánto demora la respuesta y deduce qué correos
# están registrados: si no hay usuario respondemos al instante, y si lo hay
# tardamos los 280 ms del bcrypt. Ese diferencial es el oráculo.
_DESCARTE = bcrypt.hashpw(b"no-existe", bcrypt.gensalt(COSTO))


def hashear(contrasena):
    """
    Devuelve el hash listo para guardar en usuarios.password_hash.

    Lanza ContrasenaMuyLarga si pasa de 72 BYTES. Ojo que son bytes y no
    caracteres: 'contraseña' × 8 son 80 caracteres pero 88 bytes, porque
    cada ñ ocupa dos. Valida el largo en bytes en el formulario.
    """
    crudo = contrasena.encode("utf-8")
    if len(crudo) > MAX_BYTES:
        raise ContrasenaMuyLarga(
            f"La contraseña ocupa {len(crudo)} bytes y el máximo es {MAX_BYTES}."
        )
    return bcrypt.hashpw(crudo, bcrypt.gensalt(COSTO)).decode("ascii")


def verificar(contrasena, hash_guardado):
    """
    True si la contraseña corresponde al hash. Nunca lanza excepción:
    ante cualquier problema devuelve False.

    Si el usuario no tiene hash (cuenta creada sin contraseña, invitado),
    igual gastamos el tiempo de un bcrypt para no delatarlo.
    """
    crudo = contrasena.encode("utf-8")[:MAX_BYTES]

    if not hash_guardado:
        bcrypt.checkpw(crudo, _DESCARTE)   # tiempo constante a propósito
        return False

    try:
        return bcrypt.checkpw(crudo, hash_guardado.encode("ascii"))
    except (ValueError, TypeError):
        # hash corrupto o con formato desconocido
        return False


def necesita_rehash(hash_guardado):
    """
    True si el hash quedó desactualizado: lo hizo otro algoritmo, o bcrypt
    con un cost menor al que usamos hoy.

    Se llama al iniciar sesión, que es el único momento en que tenemos la
    contraseña en claro y podemos rehashearla. Así la migración ocurre sola,
    sin obligar a nadie a cambiar su contraseña.
    """
    if not hash_guardado:
        return False
    try:
        partes = hash_guardado.split("$")       # ['', '2b', '12', 'sal+hash']
        if partes[1] not in ("2a", "2b", "2y"):
            return True                          # otro algoritmo
        return int(partes[2]) < COSTO            # cost antiguo
    except (IndexError, ValueError):
        return True
