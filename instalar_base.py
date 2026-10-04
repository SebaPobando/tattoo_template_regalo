"""
Arma (o pone al día) la base de datos. Se puede correr las veces que quieras:
nunca borra nada.

    python instalar_base.py              crea las tablas que falten
    python instalar_base.py --ejemplos   y además carga el catálogo de ejemplo

Lee los datos de conexión del archivo .env (o de las variables del servidor):
MYSQL_URL, o bien DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME.

NO hace falta correrlo en Railway: la app lo hace sola cada vez que arranca
(ver server.py). En tu computador tampoco es obligatorio —python server.py
también lo hace—, pero sirve para ver con calma si la conexión funciona.

Si en el entorno existen ADMIN_CORREO y ADMIN_CLAVE, además crea esa cuenta
de administrador (solo si ese correo todavía no existe). Es la forma cómoda de
tener el primer admin en Railway sin abrir ninguna consola.
"""
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pymysql
from pymysql.constants import CLIENT

AQUI = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(AQUI, "schema")

# El orden importa: cada archivo puede usar tablas de los anteriores.
ARCHIVOS = [
    "schema_mysql.sql",
    "muro.sql",
    "actividad_imagen.sql",
    "evento_voucher.sql",
    "producto_etiqueta.sql",
    "promos.sql",
    "pedidos_shopify.sql",
    "pedidos_shopify_detalle.sql",
    "carta_combos.sql",
    "barra_pedidos.sql",
    "ruleta.sql",
    "vales.sql",
    "tienda_destacados.sql",
]
EJEMPLOS = "seed_ejemplo.sql"


def _datos():
    sys.path.insert(0, AQUI)
    from flask_app.config.mysqlconnection import datos_conexion
    return datos_conexion()


def _conectar(d, con_base=True):
    return pymysql.connect(
        host=d["host"], port=d["port"], user=d["user"], password=d["password"],
        database=d["db"] if con_base else None, charset="utf8mb4", autocommit=True,
        client_flag=CLIENT.MULTI_STATEMENTS, connect_timeout=10,
    )


def _correr(cur, archivo):
    with open(os.path.join(SCHEMA, archivo), encoding="utf-8") as f:
        sql = f.read()
    cur.execute(sql)
    # Con varias sentencias en un archivo hay que recorrer cada resultado;
    # si no, los errores de las del medio quedan escondidos.
    while cur.nextset():
        pass


def _crear_admin_del_entorno(d, decir):
    correo = (os.environ.get("ADMIN_CORREO") or "").strip().lower()
    clave = os.environ.get("ADMIN_CLAVE") or ""
    if not correo or not clave:
        return
    if len(clave) < 10:
        decir("[!] ADMIN_CLAVE tiene menos de 10 caracteres: no se creó el admin.")
        return
    from flask_app.config.seguridad import hashear
    con = _conectar(d)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT id FROM usuarios WHERE email = %s", (correo,))
            if cur.fetchone():
                return          # ya existe: no se toca su clave ni su rol
            cur.execute(
                "INSERT INTO usuarios (email, password_hash, rol, estado, nombre) "
                "VALUES (%s, %s, 'admin', 'activo', 'Administración')",
                (correo, hashear(clave)))
            decir(f"[OK] Cuenta de administrador creada: {correo}")
    finally:
        con.close()


def instalar(ejemplos=False, decir=print, ejemplos_solo_si_vacia=False):
    """
    Devuelve True si todo salió bien. Nunca borra datos.

    ejemplos_solo_si_vacia: carga el catálogo de ejemplo SOLO la primera
    vez (queda anotado en la tabla `instalacion`) y solo si no hay productos.
    Es lo que usa el arranque automático (CARGAR_EJEMPLOS en Railway): si
    después borras los ejemplos, no vuelven a aparecer en el siguiente
    reinicio aunque la variable siga puesta.
    """
    d = _datos()
    decir(f"Base de datos: {d['db']} en {d['host']}:{d['port']} (usuario {d['user']})")

    # 1. La base. En tu computador hay que crearla; en Railway ya existe y
    #    el usuario quizás no tiene permiso para crear otra: por eso el error
    #    acá se ignora y se intenta entrar igual.
    try:
        con = _conectar(d, con_base=False)
        with con.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{d['db']}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
        con.close()
    except pymysql.err.OperationalError as e:
        if e.args and e.args[0] in (2003, 2005, 1045):
            raise           # no hay servidor, o la clave está mala: eso sí es grave
    except Exception:
        pass

    # 2. Las tablas, en orden.
    con = _conectar(d)
    try:
        with con.cursor() as cur:
            for archivo in ARCHIVOS:
                _correr(cur, archivo)
                decir(f"   ok  {archivo}")
            # Una tabla mínima para recordar qué se hizo una sola vez.
            cur.execute(
                "CREATE TABLE IF NOT EXISTS instalacion ("
                " clave VARCHAR(50) NOT NULL PRIMARY KEY,"
                " creado_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ") ENGINE=InnoDB")
            if ejemplos and ejemplos_solo_si_vacia:
                cur.execute("SELECT COUNT(*) FROM instalacion WHERE clave = 'ejemplos'")
                ya_cargados = cur.fetchone()[0] > 0
                cur.execute("SELECT COUNT(*) FROM productos")
                ejemplos = not ya_cargados and cur.fetchone()[0] == 0
            if ejemplos:
                _correr(cur, EJEMPLOS)
                cur.execute("INSERT IGNORE INTO instalacion (clave) VALUES ('ejemplos')")
                decir(f"   ok  {EJEMPLOS}  (catálogo de ejemplo)")
    finally:
        con.close()

    _crear_admin_del_entorno(d, decir)
    return True


def main():
    ejemplos = "--ejemplos" in sys.argv
    try:
        instalar(ejemplos=ejemplos)
    except pymysql.err.OperationalError as e:
        codigo = e.args[0] if e.args else None
        print(f"\n[X] No pude conectarme a MySQL: {e}")
        if codigo == 1045:
            print("    El usuario o la contraseña no calzan. Revisa DB_USER y DB_PASSWORD en el .env.")
        elif codigo in (2003, 2005):
            print("    No encontré el servidor. ¿Está MySQL encendido? ¿DB_HOST y DB_PORT están bien?")
        sys.exit(1)
    except pymysql.err.MySQLError as e:
        print(f"\n[X] MySQL rechazó una instrucción: {e}")
        sys.exit(1)
    print("\n[OK] Base de datos lista.")
    if ejemplos:
        print("     Con el catálogo de ejemplo cargado. Bórralo antes de abrir al público.")
    print("     Siguiente paso:  python crear_admin.py   (si todavía no tienes admin)")


if __name__ == "__main__":
    main()
