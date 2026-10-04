"""
Crea el archivo .env de tu computador, haciéndote dos o tres preguntas.

    python configurar.py

El .env guarda la contraseña de tu MySQL y una clave secreta para la app.
NO se sube a GitHub ni se comparte (ya está en .gitignore).

Solo es para tu computador. En Railway no hay .env: los datos van en la
pestaña «Variables» del servicio (ver README.md).
"""
import getpass
import os
import secrets
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(AQUI, ".env")


def preguntar(texto, por_defecto=""):
    extra = f" [{por_defecto}]" if por_defecto else ""
    valor = input(f"{texto}{extra}: ").strip()
    return valor or por_defecto


def probar(datos):
    try:
        import pymysql
    except ImportError:
        print("   (No pude probar la conexión: falta instalar los requisitos.")
        print("    Corre primero:  pip install -r requirements.txt )")
        return None
    try:
        con = pymysql.connect(host=datos["DB_HOST"], port=int(datos["DB_PORT"]),
                              user=datos["DB_USER"], password=datos["DB_PASSWORD"],
                              connect_timeout=5)
        con.close()
        return True
    except Exception as e:      # noqa: BLE001
        print(f"   No pude conectarme: {e}")
        return False


def main():
    print("\nVamos a crear el archivo .env (la configuración de tu computador).\n")
    if os.path.exists(ENV):
        if preguntar("Ya existe un .env. ¿Lo reemplazo? (s/n)", "n").lower() != "s":
            print("Listo, no toqué nada.")
            return

    print("Datos de tu MySQL. Si lo instalaste con las opciones normales, solo")
    print("cambia la contraseña: es la que elegiste para el usuario «root».\n")
    datos = {
        "DB_HOST": preguntar("Servidor", "localhost"),
        "DB_PORT": preguntar("Puerto", "3306"),
        "DB_USER": preguntar("Usuario", "root"),
    }
    datos["DB_PASSWORD"] = getpass.getpass("Contraseña de MySQL (no se ve mientras escribes): ")
    datos["DB_NAME"] = preguntar("Nombre de la base de datos", "tatuaje_db")

    print("\nProbando la conexión...")
    ok = probar(datos)
    if ok:
        print("   ¡Conectó!")
    elif ok is False:
        print("   Revisa que MySQL esté encendido y que la contraseña sea la correcta.")
        if preguntar("¿Guardo el .env igual? (s/n)", "s").lower() != "s":
            sys.exit(1)

    contenido = f"""# Archivo creado por configurar.py. NO lo subas a GitHub ni lo compartas.
# Para volver a crearlo:  python configurar.py

# Clave secreta de la app (firma las sesiones). Única para este computador.
SECRET_KEY={secrets.token_urlsafe(48)}

# En tu computador va vacío. En Railway se pone «production».
FLASK_ENV=
DETRAS_DE_PROXY=

# Tu MySQL
DB_HOST={datos['DB_HOST']}
DB_PORT={datos['DB_PORT']}
DB_USER={datos['DB_USER']}
DB_PASSWORD={datos['DB_PASSWORD']}
DB_NAME={datos['DB_NAME']}

SITIO_PUBLICO=/

# Correo: sin SMTP_HOST, los correos NO se envían: quedan como archivos en
# la carpeta buzon/ (cómodo para probar). Ver README.md para configurarlo.
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
CORREO_DESDE=hola@tunegocio.cl
CORREO_NOMBRE=Insumos Tattoo Ejemplo
CORREO_BUZON=buzon

# Tienda Shopify (opcional). Vacío = sin tienda online.
SHOPIFY_DOMINIO=
SHOPIFY_STOREFRONT_TOKEN=
SHOPIFY_COLECCION=tienda-web
SHOPIFY_CACHE_SEGUNDOS=300
SHOPIFY_WEBHOOK_SECRET=
"""
    with open(ENV, "w", encoding="utf-8") as f:
        f.write(contenido)
    print("\n[OK] Archivo .env creado.")
    print("     Siguiente paso:  python instalar_base.py --ejemplos")


if __name__ == "__main__":
    main()
