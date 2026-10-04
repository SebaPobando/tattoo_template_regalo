# ==========================================================================
# ruleta_model.py — la ruleta de premios
#
# Ver schema/ruleta.sql para el porqué de cada tabla. Las tres ideas:
#
# 1. CADA GIRO LO HABILITA ALGUIEN DEL LOCAL. La app no ve la boleta; el
#    barista sí. La página pública solo gira un giro que ya existe, y una
#    sola vez.
#
# 2. EL PREMIO LO SORTEA EL SERVIDOR, con `secrets.randbelow(n)`: cada gajo
#    tiene exactamente 1/n de probabilidad. El navegador recibe el resultado
#    y anima la ruleta hasta ese gajo. Cambiar el JavaScript cambia la
#    animación, no el premio.
#
# 3. GIRAR ES IDEMPOTENTE. Va en una transacción con FOR UPDATE sobre el
#    giro: dos toques seguidos, o recargar la página a mitad de la animación,
#    no sortean dos veces. La segunda vez se devuelve lo que ya salió.
# ==========================================================================

import json
import math
import secrets

from flask_app import DB
from flask_app.config import tiempo
from flask_app.config.mysqlconnection import connectToMySQL, transaccion
from flask_app.config.negocio import NEGOCIO

MIN_GAJOS = 4
MAX_GAJOS = 24
LARGO_PREMIO = 30   # = VARCHAR(30) de ruleta_gajos.premio

# Mismo alfabeto que los vouchers: sin I, O, 0 ni 1, porque se dicta.
_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class GiroNoValido(Exception):
    """Un giro que no se puede girar: no existe, venció o se anuló. El
    mensaje es para mostrarlo tal cual."""


class RuletaIncompleta(Exception):
    """Faltan premios: no se habilitan giros sobre una ruleta a medio
    escribir."""


def _nuevo_codigo():
    bloque = lambda: "".join(secrets.choice(_ALFABETO) for _ in range(4))
    return f"RL-{bloque()}-{bloque()}"


# ------------------------------------------------------------------ dibujo

def _color_texto(hexa):
    """Blanco o casi negro, el que se lea mejor sobre ese fondo (luminancia
    relativa de WCAG, simplificada)."""
    h = hexa.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return "#1A1A1A"
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return "#1A1A1A" if lum > 0.4 else "#FFFFFF"


# El dibujo vive en un viewBox de 400 × 470: la rueda arriba, con centro en
# (200, 210), y el pie triangular abajo.
CX, CY, R = 200, 210, 182


def _punto(grados, radio):
    a = math.radians(grados)
    return CX + radio * math.sin(a), CY - radio * math.cos(a)


def geometria(premios, colores=None):
    """
    Los gajos listos para pintar en SVG. Los ángulos se miden desde arriba
    (las 12 del reloj) en el sentido del reloj, que es como se lee una
    ruleta: el gajo 0 parte en el puntero y sigue hacia la derecha.

    Se calcula acá y no en la plantilla porque es trigonometría: en Jinja
    sería ilegible, y así la página del giro y la vista previa del panel
    dibujan exactamente lo mismo.
    """
    colores = colores or NEGOCIO["ruleta"]["colores"] or ["#1A1A1A", "#FFFFFF"]
    n = len(premios)
    if not n:
        return {"n": 0, "gajos": [], "clavos": [], "paso": 0}
    paso = 360 / n
    # Cuánto espacio hay para el texto: a lo ancho, la cuerda del gajo a
    # media altura; a lo largo, del eje al borde.
    cuerda = 2 * (R * 0.62) * math.sin(math.pi / n)
    gajos = []
    for i, premio in enumerate(premios):
        a0, a1 = i * paso, (i + 1) * paso
        x0, y0 = _punto(a0, R)
        x1, y1 = _punto(a1, R)
        grande = 1 if paso > 180 else 0
        fondo = colores[i % len(colores)]
        largo = max(len(premio), 1)
        fuente = min(17.0, cuerda * 0.42, 128 / (0.68 * largo))
        gajos.append({
            "indice": i,
            "premio": premio,
            "d": (f"M{CX},{CY} L{x0:.2f},{y0:.2f} "
                  f"A{R},{R} 0 {grande} 1 {x1:.2f},{y1:.2f} Z"),
            "fondo": fondo,
            "tinta": _color_texto(fondo),
            "centro": a0 + paso / 2,
            # El texto corre por el radio, del borde hacia el eje. En la
            # mitad derecha se gira hasta que el centro del gajo apunte a
            # +x y se escribe pegado al borde; en la izquierda quedaría de
            # cabeza, así que se gira media vuelta más y se ancla al revés.
            # Es como se rotulan las ruletas de verdad.
            "giro_texto": a0 + paso / 2 + (90 if 180 < a0 + paso / 2 < 360 else -90),
            "volteado": 180 < a0 + paso / 2 < 360,
            "fuente": round(max(fuente, 8.5), 1),
        })
    clavos = [dict(zip(("x", "y"), (round(v, 2) for v in _punto(i * paso, R + 6))))
              for i in range(n)]
    return {"n": n, "gajos": gajos, "clavos": clavos, "paso": paso,
            "cx": CX, "cy": CY, "r": R}


# -------------------------------------------------------------- la ruleta

class Ruleta:

    @staticmethod
    def config():
        filas = connectToMySQL(DB).query_db("SELECT * FROM ruleta_config WHERE id = 1")
        return filas[0] if filas else None

    @staticmethod
    def guardar_config(monto_minimo, vence_min):
        return connectToMySQL(DB).query_db(
            "UPDATE ruleta_config SET monto_minimo = %s, vence_min = %s WHERE id = 1",
            (monto_minimo, vence_min))

    @staticmethod
    def premios():
        """Los textos de los gajos, en orden."""
        filas = connectToMySQL(DB).query_db(
            "SELECT premio FROM ruleta_gajos ORDER BY posicion") or []
        return [f["premio"] for f in filas]

    @staticmethod
    def guardar_premios(premios):
        """
        Reemplaza la ruleta entera. Todo o nada: una ruleta guardada a
        medias tendría gajos con la posición repetida o saltada.

        Los giros ya hechos no se tocan: cada uno guardó su propia foto de
        la ruleta (gajos_json) y su premio en texto.
        """
        with transaccion(DB) as cur:
            cur.execute("DELETE FROM ruleta_gajos")
            for i, p in enumerate(premios):
                cur.execute("INSERT INTO ruleta_gajos (posicion, premio) VALUES (%s, %s)",
                            (i, p))

    @staticmethod
    def probabilidades(premios):
        """
        [{"premio", "gajos", "pct"}], del más probable al menos. Se agrupa por
        texto (sin distinguir mayúsculas ni espacios de más): tres gajos que
        dicen «Café gratis» son UN premio con 3/n de probabilidad.
        """
        n = len(premios)
        grupos = {}
        for p in premios:
            clave = " ".join(p.lower().split())
            g = grupos.setdefault(clave, {"premio": p, "gajos": 0})
            g["gajos"] += 1
        filas = sorted(grupos.values(), key=lambda g: (-g["gajos"], g["premio"].lower()))
        for g in filas:
            g["pct"] = round(100 * g["gajos"] / n, 1) if n else 0
        return filas

    # ------------------------------------------------------------- giros

    @staticmethod
    def habilitar(usuario_id, referencia=None):
        """Crea un giro de un solo uso. Devuelve su código."""
        premios = Ruleta.premios()
        if len(premios) < MIN_GAJOS:
            raise RuletaIncompleta(
                f"Primero escribe los premios de la ruleta (al menos {MIN_GAJOS} gajos).")
        cfg = Ruleta.config()
        vence = int(cfg["vence_min"]) if cfg else 30
        for _ in range(6):
            codigo = _nuevo_codigo()
            if not connectToMySQL(DB).query_db(
                    "SELECT id FROM ruleta_giros WHERE codigo = %s", (codigo,)):
                break
        else:
            raise RuntimeError("No pude generar un código de giro libre.")
        connectToMySQL(DB).query_db(f"""
            INSERT INTO ruleta_giros (codigo, habilitado_por, referencia, creado_at, vence_at)
            VALUES (%s, %s, %s, UTC_TIMESTAMP(),
                    DATE_ADD(UTC_TIMESTAMP(), INTERVAL {vence} MINUTE))
        """, (codigo, usuario_id, referencia))
        return codigo

    @staticmethod
    def _vista(g):
        """El giro con su estado en palabras y la ruleta que le corresponde:
        la foto guardada si ya se giró, la actual si todavía no."""
        if not g:
            return None
        g = dict(g)
        ahora = tiempo.ahora_utc()
        if g["anulado_at"]:
            g["estado"] = "anulado"
        elif g["girado_at"]:
            g["estado"] = "girado"
        elif g["vence_at"] <= ahora:
            g["estado"] = "vencido"
        else:
            g["estado"] = "pendiente"
        g["premios_ruleta"] = (json.loads(g["gajos_json"]) if g.get("gajos_json")
                               else None)
        return g

    @staticmethod
    def por_codigo(codigo):
        filas = connectToMySQL(DB).query_db(
            "SELECT * FROM ruleta_giros WHERE codigo = %s", (codigo,))
        return Ruleta._vista(filas[0]) if filas else None

    @staticmethod
    def obtener(giro_id):
        filas = connectToMySQL(DB).query_db(
            "SELECT * FROM ruleta_giros WHERE id = %s", (giro_id,))
        return Ruleta._vista(filas[0]) if filas else None

    @staticmethod
    def girar(codigo):
        """
        Sortea y guarda. Devuelve {"indice", "premio", "premios", "nuevo"}:
        `nuevo` es False cuando el giro ya se había girado y se devuelve lo
        que salió esa vez.
        """
        with transaccion(DB) as cur:
            cur.execute("""
                SELECT *, vence_at <= UTC_TIMESTAMP() AS vencido
                FROM ruleta_giros WHERE codigo = %s FOR UPDATE
            """, (codigo,))
            g = cur.fetchone()
            if not g:
                raise GiroNoValido("Ese giro no existe.")
            if g["girado_at"]:
                return {"indice": g["gajo_indice"], "premio": g["premio"],
                        "premios": json.loads(g["gajos_json"]), "nuevo": False}
            if g["anulado_at"]:
                raise GiroNoValido("Este giro fue anulado.")
            if g["vencido"]:
                raise GiroNoValido("Este giro venció. Pide que te habiliten otro en la caja.")

            cur.execute("SELECT premio FROM ruleta_gajos ORDER BY posicion")
            premios = [f["premio"] for f in cur.fetchall()]
            if len(premios) < MIN_GAJOS:
                raise GiroNoValido("La ruleta no está lista. Avísale a quien te atendió.")

            # EL SORTEO. randbelow(n) es uniforme en 0..n-1: cada gajo, 1/n.
            indice = secrets.randbelow(len(premios))
            cur.execute("""
                UPDATE ruleta_giros
                   SET girado_at = UTC_TIMESTAMP(), gajo_indice = %s,
                       premio = %s, gajos_json = %s
                 WHERE id = %s
            """, (indice, premios[indice], json.dumps(premios, ensure_ascii=False), g["id"]))
        return {"indice": indice, "premio": premios[indice], "premios": premios,
                "nuevo": True}

    @staticmethod
    def historial(limite=60):
        filas = connectToMySQL(DB).query_db("""
            SELECT g.*, u.nombre AS habilitado_nombre
            FROM ruleta_giros g
            LEFT JOIN usuarios u ON u.id = g.habilitado_por
            ORDER BY g.creado_at DESC, g.id DESC
            LIMIT %s
        """, (limite,)) or []
        return [Ruleta._vista(f) for f in filas]

    @staticmethod
    def marcar_entregado(giro_id, entregado):
        return connectToMySQL(DB).query_db(f"""
            UPDATE ruleta_giros
               SET entregado_at = {'COALESCE(entregado_at, UTC_TIMESTAMP())' if entregado else 'NULL'}
             WHERE id = %s AND girado_at IS NOT NULL
        """, (giro_id,))

    @staticmethod
    def anular(giro_id):
        """Solo uno que todavía no se gira. Uno girado ya tiene premio: si
        hubo un error, eso se conversa, no se borra."""
        return connectToMySQL(DB).query_db("""
            UPDATE ruleta_giros SET anulado_at = UTC_TIMESTAMP()
             WHERE id = %s AND girado_at IS NULL AND anulado_at IS NULL
        """, (giro_id,))

    @staticmethod
    def resumen():
        """Para la tarjeta del panel."""
        f = connectToMySQL(DB).query_db("""
            SELECT COUNT(*) AS gajos,
                   (SELECT COUNT(*) FROM ruleta_giros
                     WHERE girado_at IS NOT NULL AND entregado_at IS NULL) AS por_entregar
            FROM ruleta_gajos
        """)[0]
        return {"gajos": int(f["gajos"]), "por_entregar": int(f["por_entregar"] or 0)}
