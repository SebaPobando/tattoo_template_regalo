# ==========================================================================
# vale_model.py — vales de regalo y gift cards
#
# Ver schema/vales.sql. Lo esencial:
#
# 1. DOS TIPOS, UNA TABLA. «regalo» lo emite el local y puede vencer;
#    «giftcard» la compra un cliente, se anota cuánto pagó y no vence.
#
# 2. SE CANJEA UNA VEZ, COMPLETO, Y SOLO EL PERSONAL. El canje va en una
#    transacción con FOR UPDATE sobre el vale: dos baristas que escanean el
#    mismo QR a la vez no lo canjean dos veces; el segundo ve «ya canjeado».
#
# 3. EL ESTADO SE CALCULA, NO SE GUARDA. No hay columna «estado»: sale de
#    las fechas (anulado, canjeado, vencido o vigente). Así un vale vence
#    solo, a medianoche, sin que nadie corra nada.
# ==========================================================================

import secrets

from flask_app import DB
from flask_app.config import tiempo
from flask_app.config.mysqlconnection import connectToMySQL, transaccion

TIPOS = ("regalo", "giftcard")
NOMBRE_TIPO = {"regalo": "Vale de regalo", "giftcard": "Gift card"}
ESTADOS = ("vigente", "canjeado", "vencido", "anulado")

MAX_POR_LOTE = 200

# Mismo alfabeto que los vouchers y la ruleta: sin I, O, 0 ni 1.
_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# El estado en SQL, para poder filtrar y contar en la base.
_ESTADO = """
    CASE
      WHEN v.anulado_at IS NOT NULL THEN 'anulado'
      WHEN v.canjeado_at IS NOT NULL THEN 'canjeado'
      WHEN v.vence_at IS NOT NULL AND v.vence_at < UTC_TIMESTAMP() THEN 'vencido'
      ELSE 'vigente'
    END
"""


class CanjeRechazado(Exception):
    """Un vale que no se puede canjear. El mensaje es para el barista."""


def _nuevo_codigo():
    bloque = lambda: "".join(secrets.choice(_ALFABETO) for _ in range(4))
    return f"VL-{bloque()}-{bloque()}"


def _codigo_libre(cur):
    for _ in range(6):
        c = _nuevo_codigo()
        cur.execute("SELECT id FROM vales WHERE codigo = %s", (c,))
        if not cur.fetchone():
            return c
    raise RuntimeError("No pude generar un código de vale libre.")


def fin_del_dia_utc(fecha):
    """El último segundo de ese día en Chile, en UTC. Un vale «hasta el 31
    de diciembre» vale todo el 31, hasta las 23:59:59 de acá."""
    if not fecha:
        return None
    return tiempo.local_a_utc(f"{fecha.isoformat()}T23:59:59")


_SELECT = f"""
    SELECT v.*, {_ESTADO} AS estado,
           l.nombre AS lote_nombre,
           ue.nombre AS emitido_nombre, ue.nickname AS emitido_nick,
           uc.nombre AS canjeado_nombre, uc.nickname AS canjeado_nick
    FROM vales v
    LEFT JOIN vale_lotes l ON l.id = v.lote_id
    LEFT JOIN usuarios ue  ON ue.id = v.emitido_por
    LEFT JOIN usuarios uc  ON uc.id = v.canjeado_por
"""


class Vale:

    # ---------------------------------------------------------- emitir

    @staticmethod
    def emitir(*, tipo, valido_por, emitido_por, para_nombre=None,
               para_telefono=None, motivo=None, comprador=None,
               monto_pagado_clp=None, vence=None):
        """Un vale. Devuelve su código. `vence` es una fecha (date) local."""
        if tipo not in TIPOS:
            raise ValueError(tipo)
        if tipo == "giftcard":
            vence = None            # pagada: no vence
            motivo = None
        else:
            comprador = None
            monto_pagado_clp = None
        with transaccion(DB) as cur:
            codigo = _codigo_libre(cur)
            cur.execute("""
                INSERT INTO vales
                  (codigo, tipo, valido_por, para_nombre, para_telefono,
                   motivo, comprador, monto_pagado_clp, emitido_por,
                   emitido_at, vence_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP(), %s)
            """, (codigo, tipo, valido_por, para_nombre, para_telefono, motivo,
                  comprador, monto_pagado_clp, emitido_por, fin_del_dia_utc(vence)))
        return codigo

    @staticmethod
    def emitir_lote(*, nombre, cantidad, valido_por, emitido_por, vence=None):
        """
        Varios vales de regalo iguales, para un evento. Todo o nada: un lote
        a medio crear dejaría una hoja de QR con huecos. Devuelve el id del
        lote.
        """
        cantidad = max(1, min(int(cantidad), MAX_POR_LOTE))
        with transaccion(DB) as cur:
            cur.execute("""
                INSERT INTO vale_lotes (nombre, creado_por, creado_at)
                VALUES (%s, %s, UTC_TIMESTAMP())
            """, (nombre, emitido_por))
            lote_id = cur.lastrowid
            vence_utc = fin_del_dia_utc(vence)
            for _ in range(cantidad):
                cur.execute("""
                    INSERT INTO vales
                      (codigo, tipo, valido_por, motivo, lote_id, emitido_por,
                       emitido_at, vence_at)
                    VALUES (%s, 'regalo', %s, %s, %s, %s, UTC_TIMESTAMP(), %s)
                """, (_codigo_libre(cur), valido_por, nombre, lote_id,
                      emitido_por, vence_utc))
        return lote_id

    # ---------------------------------------------------------- lectura

    @staticmethod
    def por_codigo(codigo):
        filas = connectToMySQL(DB).query_db(_SELECT + " WHERE v.codigo = %s", (codigo,))
        return filas[0] if filas else None

    @staticmethod
    def obtener(vale_id):
        filas = connectToMySQL(DB).query_db(_SELECT + " WHERE v.id = %s", (vale_id,))
        return filas[0] if filas else None

    @staticmethod
    def listar(tipo=None, estado=None, busca=None, limite=200):
        """Lo que muestra el panel: todos, de los dos tipos, con filtros."""
        patron = f"%{busca}%" if busca else None
        return connectToMySQL(DB).query_db(_SELECT + f"""
            WHERE (%(tipo)s IS NULL OR v.tipo = %(tipo)s)
              AND (%(estado)s IS NULL OR {_ESTADO} = %(estado)s)
              AND (%(patron)s IS NULL
                   OR v.codigo LIKE %(patron)s OR v.para_nombre LIKE %(patron)s
                   OR v.comprador LIKE %(patron)s OR v.motivo LIKE %(patron)s
                   OR v.valido_por LIKE %(patron)s)
            ORDER BY v.emitido_at DESC, v.id DESC
            LIMIT %(limite)s
        """, {"tipo": tipo, "estado": estado, "patron": patron, "limite": limite}) or []

    @staticmethod
    def del_lote(lote_id):
        lote = connectToMySQL(DB).query_db(
            "SELECT * FROM vale_lotes WHERE id = %s", (lote_id,))
        if not lote:
            return None, []
        vales = connectToMySQL(DB).query_db(
            _SELECT + " WHERE v.lote_id = %s ORDER BY v.id", (lote_id,)) or []
        return lote[0], vales

    @staticmethod
    def resumen():
        f = connectToMySQL(DB).query_db(f"""
            SELECT
              COALESCE(SUM({_ESTADO} = 'vigente'), 0)  AS vigentes,
              COALESCE(SUM({_ESTADO} = 'canjeado'), 0) AS canjeados,
              COALESCE(SUM(v.tipo = 'giftcard' AND v.anulado_at IS NULL), 0) AS giftcards,
              COALESCE(SUM(CASE WHEN v.tipo = 'giftcard' AND v.anulado_at IS NULL
                                THEN v.monto_pagado_clp ELSE 0 END), 0) AS vendido_clp,
              COALESCE(SUM(v.tipo = 'giftcard' AND {_ESTADO} = 'vigente'), 0) AS giftcards_vigentes,
              COALESCE(SUM(CASE WHEN v.tipo = 'giftcard' AND {_ESTADO} = 'vigente'
                                THEN v.monto_pagado_clp ELSE 0 END), 0) AS por_canjear_clp
            FROM vales v
        """)[0]
        return {k: int(v or 0) for k, v in f.items()}

    # ---------------------------------------------------------- canje

    @staticmethod
    def canjear(codigo, usuario_id):
        """
        Lo marca canjeado. Levanta CanjeRechazado con un mensaje para el
        barista si ya se usó, venció o fue anulado.
        """
        with transaccion(DB) as cur:
            cur.execute(f"""
                SELECT v.*, {_ESTADO} AS estado,
                       uc.nombre AS canjeado_nombre
                FROM vales v
                LEFT JOIN usuarios uc ON uc.id = v.canjeado_por
                WHERE v.codigo = %s
                FOR UPDATE
            """, (codigo,))
            v = cur.fetchone()
            if not v:
                raise CanjeRechazado("Ese vale no existe.")
            if v["estado"] == "canjeado":
                quien = f" por {v['canjeado_nombre']}" if v.get("canjeado_nombre") else ""
                raise CanjeRechazado(
                    f"Este vale ya se canjeó el {tiempo.largo(v['canjeado_at'])}{quien}.")
            if v["estado"] == "anulado":
                raise CanjeRechazado("Este vale fue anulado: no se puede canjear.")
            if v["estado"] == "vencido":
                raise CanjeRechazado(
                    f"Este vale venció el {tiempo.fecha(v['vence_at'])}.")
            cur.execute("""
                UPDATE vales SET canjeado_at = UTC_TIMESTAMP(), canjeado_por = %s
                WHERE id = %s
            """, (usuario_id, v["id"]))
        return True

    @staticmethod
    def anular(vale_id):
        """Solo uno que no se ha canjeado. Devuelve filas cambiadas."""
        return connectToMySQL(DB).query_db("""
            UPDATE vales SET anulado_at = UTC_TIMESTAMP()
            WHERE id = %s AND canjeado_at IS NULL AND anulado_at IS NULL
        """, (vale_id,))

    @staticmethod
    def revertir_canje(vale_id):
        """Para un canje hecho por error (se tocó el vale equivocado). Solo
        el admin; el vale vuelve a quedar vigente (si no venció)."""
        return connectToMySQL(DB).query_db("""
            UPDATE vales SET canjeado_at = NULL, canjeado_por = NULL
            WHERE id = %s AND canjeado_at IS NOT NULL
        """, (vale_id,))
