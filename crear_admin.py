"""
Crea o actualiza la contraseña de una cuenta.

    python crear_admin.py

Pide el correo y la contraseña por teclado. La contraseña NO se ve mientras
la escribes ni queda en el historial de la terminal — por eso no se pasa como
argumento del comando.

Si el correo ya existe le cambia la contraseña; si no existe, crea la cuenta.
"""
import getpass
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("[X] Falta python-dotenv. Corre:  pip install -r requirements.txt")
    sys.exit(1)

try:
    from flask_app.config.seguridad import MAX_BYTES, ContrasenaMuyLarga, hashear
    from flask_app.models.usuario_model import Usuario, normalizar_email
except ImportError as e:
    print(f"[X] No pude importar la app: {e}")
    print("    Corre este script desde la carpeta del proyecto, con el venv activado.")
    sys.exit(1)

MINIMO = 10


def pedir_contrasena():
    while True:
        clave = getpass.getpass("Contraseña (no se muestra): ")
        bytes_usados = len(clave.encode("utf-8"))

        if len(clave) < MINIMO:
            print(f"    Muy corta: mínimo {MINIMO} caracteres.\n")
            continue
        if bytes_usados > MAX_BYTES:
            # Son bytes, no caracteres: cada tilde o ñ ocupa dos.
            print(f"    Muy larga: ocupa {bytes_usados} bytes y el máximo es {MAX_BYTES}.")
            print("    (los acentos y las ñ cuentan doble)\n")
            continue
        if clave != getpass.getpass("Repítela: "):
            print("    No coinciden.\n")
            continue
        return clave


def main():
    email = normalizar_email(input("Correo: "))
    if "@" not in email:
        print("[X] Eso no parece un correo.")
        sys.exit(1)

    try:
        existente = Usuario.por_email(email)
    except Exception as e:
        print(f"[X] No pude consultar la base: {e}")
        print("    ¿Corriste antes  python instalar_base.py ?  Ese comando prueba la conexión")
        print("    y te dice qué está mal (MySQL apagado, clave equivocada, etc.).")
        sys.exit(1)

    if existente:
        print(f"    Cuenta encontrada: {existente['nombre'] or '(sin nombre)'} · rol {existente['rol']}")
        if existente["password_hash"]:
            if input("    Ya tiene contraseña. ¿Reemplazarla? (s/n): ").lower() != "s":
                print("    Cancelado.")
                return
    else:
        print("    No existe. Se va a crear como admin.")
        if input("    ¿Continuar? (s/n): ").lower() != "s":
            print("    Cancelado.")
            return

    clave = pedir_contrasena()

    try:
        hash_nuevo = hashear(clave)
    except ContrasenaMuyLarga as e:
        print(f"[X] {e}")
        sys.exit(1)

    if existente:
        Usuario.guardar_hash(existente["id"], hash_nuevo)
        print(f"\n[OK] Contraseña actualizada para {email}")
        if existente["rol"] != "admin":
            print(f"[!] Ojo: esta cuenta tiene rol '{existente['rol']}', no 'admin'.")
            if input("    ¿La dejo como administradora? (s/n): ").lower() == "s":
                from flask_app import DB
                from flask_app.config.mysqlconnection import connectToMySQL
                connectToMySQL(DB).query_db(
                    "UPDATE usuarios SET rol='admin', estado='activo' WHERE id=%(id)s",
                    {"id": existente["id"]})
                print("[OK] Ahora es administradora.")
    else:
        Usuario.crear(email, password_hash=hash_nuevo, rol="admin", estado="activo")
        print(f"\n[OK] Cuenta admin creada: {email}")

    print("     Ahora entra en  http://localhost:5000/login")


if __name__ == "__main__":
    main()
