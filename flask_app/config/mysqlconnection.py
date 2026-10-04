# ==========================================================================
# mysqlconnection.py
# Conexión a MySQL — SQL crudo, sin ORM.
#
# Diferencias con el archivo de ejemplo, y por qué:
#
#   1. autocommit=False. El ejemplo traía autocommit=True, y con eso NO existen
#      las transacciones: cada consulta se confirma sola. Para una billetera eso
#      es fatal — si el descuento de saldo funciona y el registro de la orden
#      falla, el cliente pierde puntos y no queda registro de qué compró.
#
#   2. La conexión no se cierra dentro de query_db. El ejemplo la cerraba en el
#      finally, así que dos consultas nunca podían compartir transacción.
#
#   3. Los errores se relanzan. El ejemplo hacía `except: return False`, o sea
#      un INSERT fallido se veía igual que uno exitoso salvo que revisaras el
#      valor. En un ledger, eso es plata perdida en silencio.
#
#   4. Las credenciales salen del entorno, no del código fuente.
#
# REGLA: cualquier cosa que toque lp_movimientos va dentro de transaccion().
#        query_db() es solo para lecturas y escrituras sueltas sin riesgo.
# ==========================================================================

import os
from contextlib import contextmanager
from urllib.parse import unquote, urlparse

import pymysql.cursors


def datos_conexion():
    """
    Dónde está la base, sacado del entorno.

    Dos formas de decirlo, y gana la primera que exista:

      MYSQL_URL=mysql://usuario:clave@host:puerto/base
          Una sola variable. Es la que entrega el MySQL de Railway: en el
          servicio web basta con  MYSQL_URL=${{MySQL.MYSQL_URL}}

      DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
          Una por dato. Es lo cómodo en tu computador (ver .env.example).
    """
    url = os.environ.get("MYSQL_URL") or os.environ.get("DATABASE_URL") or ""
    if url.startswith("mysql"):
        u = urlparse(url)
        return {
            "host": u.hostname or "localhost",
            "port": u.port or 3306,
            "user": unquote(u.username or "root"),
            "password": unquote(u.password or ""),
            "db": (u.path or "/").lstrip("/") or "tatuaje_db",
        }
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 3306)),
        "user": os.environ.get("DB_USER", "root"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "db": os.environ.get("DB_NAME", "tatuaje_db"),
    }


def _conectar(db):
    d = datos_conexion()
    return pymysql.connect(
        host=d["host"],
        port=d["port"],
        user=d["user"],
        password=d["password"],
        database=db,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


class MySQLConnection:
    def __init__(self, db):
        self.connection = _conectar(db)

    def query_db(self, query, data=None):
        """
        Una consulta suelta, con su propio commit.

        Devuelve:
          SELECT / SHOW -> lista de diccionarios
          INSERT        -> id insertado
          resto         -> número de filas afectadas

        NO la uses para saldo ni para nada que deba ser atómico: para eso está
        transaccion().
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, data)
                limpia = query.strip().lower()
                if limpia.startswith(("select", "show")):
                    resultado = cursor.fetchall()
                elif limpia.startswith("insert"):
                    resultado = cursor.lastrowid
                else:
                    resultado = cursor.rowcount
            self.connection.commit()
            return resultado
        except Exception:
            self.connection.rollback()
            raise
        finally:
            self.connection.close()


def connectToMySQL(db):
    """Se conserva el nombre del ejemplo para no romper la costumbre."""
    return MySQLConnection(db)


@contextmanager
def transaccion(db):
    """
    Varias consultas, todo o nada. Si algo revienta se revierte entero.

        from flask_app.config.mysqlconnection import transaccion

        with transaccion(DB) as cur:
            # bloquea la fila del usuario: dos baristas cobrando a la vez
            # no pueden leer el mismo saldo y descontar dos veces
            cur.execute("SELECT id FROM usuarios WHERE id = %s FOR UPDATE", (uid,))

            cur.execute(
                "SELECT COALESCE(SUM(delta),0) AS saldo "
                "FROM lp_movimientos WHERE usuario_id = %s", (uid,))
            saldo = cur.fetchone()["saldo"]
            if saldo < costo:
                raise ValueError("saldo insuficiente")

            cur.execute("INSERT INTO ordenes (...) VALUES (...)", (...))
            orden_id = cur.lastrowid
            cur.execute("INSERT INTO lp_movimientos (...) VALUES (...)", (...))

    El FOR UPDATE solo sirve dentro de una transacción: con autocommit el
    bloqueo se suelta de inmediato y no protege de nada.
    """
    conexion = _conectar(db)
    try:
        with conexion.cursor() as cursor:
            yield cursor
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()
