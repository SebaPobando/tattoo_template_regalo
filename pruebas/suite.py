"""
Suite de regresion de la plantilla.

    python3 pruebas/suite.py

Levanta nada: espera que la app YA este corriendo en el puerto de abajo y que
la base este creada. Lo normal es:

    python server.py                 # en una terminal
    python pruebas/suite.py          # en otra

Revisa 96 comportamientos que importan de verdad —105 si el .env de prueba
tiene SHOPIFY_WEBHOOK_SECRET configurado— los tres primeros bloques salieron
de agujeros reales encontrados en una auditoria, no de teoria—:

  C1  nadie puede quedarse con una cuenta ajena registrandose con su correo
  C2  bloquear o degradar a alguien surte efecto AHORA, no al cerrar sesion
  C3  el campo «volver» de los formularios del panel no lleva a otro sitio
  P   la promo de la portada aparece, se baja y su boton no sale del sitio
  K   la carta: las categorias se crean y renombran sin tocar el slug, y
      los combos salen en la carta, aceptan no tener fecha de termino,
      se apagan al tiro, no aceptan productos ajenos y el banner los lee
  B   pedidos para retiro: el precio lo pone el servidor, las franjas llenas
      o inventadas se rechazan, cancelar libera la franja, «estoy afuera»
      llega al panel y la direccion exacta solo la ve quien ya pidio
  R   la ruleta: solo el admin habilita giros, cada giro sirve una vez,
      el premio lo decide el servidor y queda guardado tal como salio
  E   el rol barista: el admin lo crea con un enlace para que elija su clave,
      entra solo a vales y ruleta, y perderlo surte efecto al tiro
  V   los vales: solo el personal canjea, una vez, y una gift card no vence
  D   los destacados de la tienda: primeros en su categoria, sin tocar la
      cache de Shopify, y sin aceptar productos inventados por POST
  G   agregar el taller al calendario: solo con voucher activo y taller por
      venir, enlace a Google Calendar, .ics valido y el link en el WhatsApp
  J   eliminar una actividad: con inscritos solo si esta cancelada, y
      entonces se van tambien sus inscripciones
  X   lo propio de la tienda de tatuaje: agotados a la vista, sin Shopify no
      hay tienda ni carrito, el personal atiende pedidos, instalar no borra
  M   las mascotas de temporada: el rango de fechas (con los extremos y
      cruzando el año) y la ruta normal cuando no hay temporada
  W   el manifest de la PWA sale con los datos del negocio y sus iconos estan
  T   el webhook de pedidos de Shopify rechaza firmas invalidas, guarda
      nombre y estado del comprador, no duplica pedidos, marca los
      reembolsos que llegan despues por orders/updated, y el panel
      responde en los cuatro cortes de tiempo (dia/semana/mes/anio)
  H   las paginas publicas responden y el panel no se abre sin rol

Escribe y borra filas de prueba en la base: NO la corras contra la base de un
negocio en produccion. Deja la app recien reiniciada antes de correrla: los
frenos anti fuerza bruta viven en memoria y una corrida anterior puede dejar
el contador arriba.
"""
import json, os, re, sys, http.cookiejar, urllib.request, urllib.parse
import pymysql

B = os.environ.get("PRUEBAS_URL", "http://127.0.0.1:5000")
# Los datos de conexion salen del .env, igual que la app.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

db = pymysql.connect(host=os.environ.get("DB_HOST", "localhost"),
                     port=int(os.environ.get("DB_PORT", 3306)),
                     user=os.environ.get("DB_USER", "root"),
                     password=os.environ.get("DB_PASSWORD", ""),
                     db=os.environ.get("DB_NAME", "tatuaje_db"),
                     charset="utf8mb4",
                     cursorclass=pymysql.cursors.DictCursor)


def sql(q, *a):
    with db.cursor() as c:
        # `a or None` y no `a`: con una tupla vacia PyMySQL igual pasa la
        # consulta por el `%` de Python, y cualquier % literal —un LIKE
        # 'algo%'— revienta con "not enough arguments for format string".
        # Con None no interpola nada y la consulta va tal cual.
        c.execute(q, a or None)
        db.commit()
        return c.fetchall() if c.description else None


class SinRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def nueva(seguir=True):
    cj = http.cookiejar.CookieJar()
    hs = [urllib.request.HTTPCookieProcessor(cj)]
    if not seguir:
        hs.append(SinRedirect)
    op = urllib.request.build_opener(*hs)
    op.cj = cj
    return op


def sin_redirect(op):
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(op.cj), SinRedirect)


def get(op, u):
    try:
        r = op.open(B + u)
        return r.status, r.read().decode("utf-8", "replace"), r.url
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), e.headers.get("Location") or u


def post(op, u, d):
    try:
        r = op.open(urllib.request.Request(B + u, data=urllib.parse.urlencode(d).encode()))
        return r.status, r.read().decode("utf-8", "replace"), r.url
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), e.headers.get("Location") or u


def tok(h):
    m = re.search(r'name="csrf"[^>]*value="([^"]+)"', h)
    return m.group(1) if m else None


def login(email, clave):
    op = nueva()
    _, h, _ = get(op, "/login")
    st, h, url = post(op, "/login", {"csrf": tok(h), "email": email, "password": clave})
    return op, st, url


def registrar(op, email, clave="Clave-Segura-123", nombre="Persona Prueba", nick=None):
    _, h, _ = get(op, "/registro")
    return post(op, "/registro", {
        "csrf": tok(h), "nombre_completo": nombre, "email": email,
        "nickname": nick or email.split("@")[0][:12], "password": clave,
        "password2": clave, "telefono": "+56911111111", "rut": "",
        "consentimiento": "1"})


# La cuenta de administrador de PRUEBA. La crea la propia suite si no existe,
# asi que no depende de como se llame el admin real del negocio.
ADMIN_EMAIL = "admin-de-prueba@example.com"
ADMIN_CLAVE = "Clave-De-Prueba-123"

def frenado(status):
    """
    429 en un registro significa que el freno anti-registros-masivos ya contó
    cinco intentos desde esta IP. Ese contador vive en la MEMORIA del proceso,
    así que lo gasta una corrida anterior de esta misma suite. Sin este aviso,
    la segunda corrida seguida muestra cuatro fallas rojas que no son fallas.
    """
    if status == 429:
        print("\n  El freno anti-registros ya está activo en la app (HTTP 429).")
        print("  Reinicia el servidor y vuelve a correr la suite:")
        print("      Ctrl+C en la terminal de la app, y  python server.py\n")
        sys.exit(2)


R = []


def chk(n, cond, det=""):
    R.append(("OK " if cond else "XX ", n, det))


def asegurar_admin():
    """
    El admin de prueba se crea acá y no se asume: la plantilla no siembra
    ninguna cuenta de administrador (esa es justamente la regla que C1
    protege), así que la suite tiene que traer la suya.
    """
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from flask_app.config.seguridad import hashear
    sql("""INSERT INTO usuarios (nombre, apellido, email, password_hash, rol,
                                 estado, nickname, email_verificado_at)
           VALUES ('Admin','De Prueba',%s,%s,'admin','activo','adminprueba',UTC_TIMESTAMP())
           ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash),
                                   rol='admin', estado='activo'""",
        ADMIN_EMAIL, hashear(ADMIN_CLAVE))


asegurar_admin()

# ---------------------------------------------------------------- C1
CORREOS = ('cebo-admin@x.cl', 'invitada@x.cl', 'normal@x.cl', 'cliente@x.cl')
sql("DELETE FROM muro_mensajes WHERE usuario_id IN (SELECT id FROM usuarios WHERE email IN %s)", CORREOS)
sql("DELETE FROM usuarios_en_actividad WHERE usuario_id IN (SELECT id FROM usuarios WHERE email IN %s)", CORREOS)
sql("DELETE FROM usuarios WHERE email IN %s", CORREOS)
sql("INSERT INTO usuarios (email,nombre,rol,estado,email_verificado_at) "
    "VALUES ('cebo-admin@x.cl','Duena','admin','activo',NOW())")
st, h, url = registrar(nueva(), "cebo-admin@x.cl")
frenado(st)
fila = sql("SELECT rol,nombre,password_hash FROM usuarios WHERE email='cebo-admin@x.cl'")[0]
chk("C1 no se puede reclamar una cuenta admin sin contrasena",
    st == 409 and fila["password_hash"] is None and fila["nombre"] == "Duena",
    f"status={st} rol={fila['rol']} nombre={fila['nombre']}")

# cuenta bloqueada sin contrasena: tampoco se reclama (seria desbloquearse)
sql("INSERT INTO usuarios (email,nombre,rol,estado) VALUES ('normal@x.cl','Vetada','cliente','bloqueado')")
st, h, url = registrar(nueva(), "normal@x.cl")
fila = sql("SELECT estado,password_hash FROM usuarios WHERE email='normal@x.cl'")[0]
chk("C1b una cuenta bloqueada sin clave no se reclama para desbloquearse",
    st == 409 and fila["estado"] == "bloqueado" and fila["password_hash"] is None,
    f"status={st} estado={fila['estado']}")

# el flujo legitimo sigue vivo: invitado de verdad -> cuenta
sql("INSERT INTO usuarios (email,nombre,telefono,rol,estado) "
    "VALUES ('invitada@x.cl','Invitada Taller','+56999888777','cliente','invitado')")
op = nueva()
_, hh, _ = get(op, "/registro")
st, h, url = post(op, "/registro", {"csrf": tok(hh), "nombre_completo": "Invitada Taller",
    "email": "invitada@x.cl", "nickname": "invitada", "password": "Clave-Segura-123",
    "password2": "Clave-Segura-123", "telefono": "", "rut": "", "consentimiento": "1"})
fila = sql("SELECT estado,telefono,password_hash FROM usuarios WHERE email='invitada@x.cl'")[0]
chk("C1c un invitado de verdad SI puede reclamar su cuenta",
    "dashboard" in str(url) and fila["estado"] == "activo" and fila["password_hash"] is not None,
    f"url={url} estado={fila['estado']}")
chk("C1d y conserva lo que ya tenia (el telefono del taller)",
    fila["telefono"] == "+56999888777", str(fila["telefono"]))

# ---------------------------------------------------------------- C2
op = nueva()
registrar(op, "cliente@x.cl")
st, h, url = get(op, "/dashboard")
chk("C2a el cliente recien registrado ve su dashboard", st == 200 and "/login" not in str(url), f"{st} {url}")
sql("UPDATE usuarios SET estado='bloqueado' WHERE email='cliente@x.cl'")
st, h, url = get(op, "/dashboard")
chk("C2b al bloquearlo, su sesion abierta cae al login",
    "/login" in str(url) or st in (302, 401), f"status={st} url={url}")
st, h, url = get(op, "/perfil")
chk("C2c y tampoco entra al perfil", "/login" in str(url), f"url={url}")

op2, st, url = login(ADMIN_EMAIL, ADMIN_CLAVE)
st, h, url = get(op2, "/admin")
chk("C2d la admin entra al panel", st == 200 and "/login" not in str(url), f"{st} {url}")
sql("UPDATE usuarios SET rol='cliente' WHERE email=%s", ADMIN_EMAIL)
st, h, url = get(op2, "/admin/usuarios")
chk("C2e al quitarle el rol, deja de entrar (404)", st == 404, f"status={st}")
sql("UPDATE usuarios SET rol='admin' WHERE email=%s", ADMIN_EMAIL)
st, h, url = get(op2, "/admin")
chk("C2f al devolverle el rol, vuelve a entrar sin reloguear", st == 200, f"status={st}")

# ---------------------------------------------------------------- C3
op3, st, url = login(ADMIN_EMAIL, ADMIN_CLAVE)
st, h, _ = get(op3, "/admin/actividades")
t = tok(h)
sql("DELETE FROM usuarios_en_actividad WHERE actividad_id IN (SELECT id FROM actividades WHERE slug='prueba-auditoria')")
sql("DELETE FROM actividades WHERE slug='prueba-auditoria'")
sql("""INSERT INTO actividades (marca_id,slug,nombre,descripcion,inicio_at,cupos,precio_clp,estado)
       VALUES (1,'prueba-auditoria','Prueba auditoria','x',DATE_ADD(UTC_TIMESTAMP(),INTERVAL 7 DAY),10,0,'publicada')""")
act = sql("SELECT id FROM actividades WHERE slug='prueba-auditoria'")[0]["id"]
sql("""INSERT INTO usuarios_en_actividad (actividad_id,usuario_id,estado,monto_clp)
       VALUES (%s,(SELECT id FROM usuarios WHERE email='invitada@x.cl'),'pendiente',0)""", act)
ins = sql("SELECT id FROM usuarios_en_actividad WHERE actividad_id=%s", act)[0]["id"]
nr = sin_redirect(op3)
st, h, loc = post(nr, f"/admin/inscripciones/{ins}/reenviar",
                  {"csrf": t, "volver": "https://sitio-falso.example/login"})
chk("C3a el campo volver no acepta una URL externa",
    not str(loc).startswith("http://sitio-falso") and "sitio-falso" not in str(loc),
    f"Location={loc}")
st, h, loc = post(nr, f"/admin/inscripciones/{ins}/reenviar",
                  {"csrf": t, "volver": "//sitio-falso.example/login"})
chk("C3b tampoco acepta el //otro-dominio", "sitio-falso" not in str(loc), f"Location={loc}")
st, h, loc = post(nr, f"/admin/inscripciones/{ins}/reenviar",
                  {"csrf": t, "volver": "/admin/actividades/%d/inscritos" % act})
chk("C3c pero sigue volviendo a la pantalla del panel",
    "/admin/actividades" in str(loc), f"Location={loc}")

# ---------------------------------------------------------------- G (calendario)
# «Agregar a mi calendario» en el voucher: solo con el pago confirmado y el
# taller por venir. El enlace es propio y redirige a Google Calendar.
sql("UPDATE usuarios_en_actividad SET voucher_codigo='LP-PRUE-BCAL', estado='pendiente' WHERE id=%s", ins)
sql("UPDATE usuarios SET telefono='+56911112222' WHERE email='invitada@x.cl'")
st, h, loc = get(nueva(seguir=False), "/inscripcion/LP-PRUE-BCAL/calendario")
chk("G1 sin pago confirmado, el calendario devuelve a la inscripcion",
    st in (301, 302) and "calendar.google.com" not in str(loc) and "/inscripcion/LP-PRUE-BCAL" in str(loc), f"Location={loc}")
st, h, u = get(nueva(), "/inscripcion/LP-PRUE-BCAL")
chk("G1b y el voucher pendiente no ofrece agendarlo", "Agrégalo a tu calendario" not in h, "")

sql("UPDATE usuarios_en_actividad SET estado='pagada' WHERE id=%s", ins)
st, h, u = get(nueva(), "/inscripcion/LP-PRUE-BCAL")
chk("G2 con el voucher activo aparecen los dos botones",
    "Agrégalo a tu calendario" in h and "/inscripcion/LP-PRUE-BCAL/calendario.ics" in h, f"status={st}")
st, h, loc = get(nueva(seguir=False), "/inscripcion/LP-PRUE-BCAL/calendario")
chk("G3 el enlace lleva a Google Calendar con nombre y fechas",
    st in (301, 302) and str(loc).startswith("https://calendar.google.com/calendar/render?")
    and "dates=" in str(loc) and "Prueba+auditoria" in str(loc), f"Location={str(loc)[:90]}")
try:
    r = nueva().open(B + "/inscripcion/LP-PRUE-BCAL/calendario.ics")
    cuerpo, tipo = r.read().decode("utf-8"), r.headers.get("Content-Type", "")
except urllib.error.HTTPError as e:
    cuerpo, tipo = "", str(e.code)
chk("G4 el .ics es un evento valido con UID estable",
    tipo.startswith("text/calendar") and "BEGIN:VEVENT" in cuerpo and "UID:LP-PRUE-BCAL@" in cuerpo
    and "DTSTART:" in cuerpo and "\r\n" in cuerpo, tipo)
st, h, u = get(op3, f"/admin/actividades/{act}/inscritos")
chk("G5 el WhatsApp del voucher trae el enlace al calendario",
    re.search(r"wa\.me/[^\"]*Agr%C3%A9galo[^\"]*LP-PRUE-BCAL/calendario", h) is not None, f"status={st}")
sql("UPDATE actividades SET inicio_at=DATE_SUB(UTC_TIMESTAMP(), INTERVAL 2 DAY) WHERE id=%s", act)
st, h, u = get(nueva(), "/inscripcion/LP-PRUE-BCAL")
chk("G6 un taller que ya paso no ofrece agendarlo", "Agrégalo a tu calendario" not in h, "")
sql("UPDATE actividades SET inicio_at=DATE_ADD(UTC_TIMESTAMP(), INTERVAL 7 DAY) WHERE id=%s", act)

# ---------------------------------------------------------------- J (eliminar actividad)
# Con gente inscrita no se borra mientras esté viva; ya cancelada, se borra
# con sus inscripciones.
sql("DELETE FROM usuarios_en_actividad WHERE actividad_id IN (SELECT id FROM actividades WHERE slug='prueba-borrar')")
sql("DELETE FROM actividades WHERE slug='prueba-borrar'")
sql("""INSERT INTO actividades (marca_id,slug,nombre,descripcion,inicio_at,cupos,precio_clp,estado)
       VALUES (1,'prueba-borrar','Prueba borrar','x',DATE_ADD(UTC_TIMESTAMP(),INTERVAL 7 DAY),10,0,'publicada')""")
actb = sql("SELECT id FROM actividades WHERE slug='prueba-borrar'")[0]["id"]
sql("""INSERT INTO usuarios_en_actividad (actividad_id,usuario_id,estado,monto_clp)
       VALUES (%s,(SELECT id FROM usuarios WHERE email='invitada@x.cl'),'pagada',0)""", actb)
_, h, _ = get(op3, "/admin/actividades")
post(op3, f"/admin/actividades/{actb}/eliminar", {"csrf": tok(h)})
chk("J1 una actividad publicada con inscritos no se elimina",
    bool(sql("SELECT id FROM actividades WHERE id=%s", actb)), "")
sql("UPDATE actividades SET estado='cancelada' WHERE id=%s", actb)
_, h, _ = get(op3, "/admin/actividades")
post(op3, f"/admin/actividades/{actb}/eliminar", {"csrf": tok(h)})
chk("J2 ya cancelada se elimina junto con sus inscripciones",
    not sql("SELECT id FROM actividades WHERE id=%s", actb)
    and not sql("SELECT id FROM usuarios_en_actividad WHERE actividad_id=%s", actb), "")

# ---------------------------------------------------------------- P (promos)
# La promo de la portada. Lo que se prueba no es el CRUD sino las tres cosas
# que el cliente va a usar: que aparezca, que el interruptor la baje al tiro,
# y que el boton no pueda sacar a nadie del sitio.
# La tabla llega en una migracion aparte (schema/promos.sql). Sin ella la
# suite reventaria con un error crudo de MySQL que no dice que hacer; asi dice.
if not sql("SHOW TABLES LIKE 'promos'"):
    print("\n  Falta la tabla `promos`. Cargala y vuelve a correr la suite:")
    print('      mysql -u root -p --default-character-set=utf8mb4 '
          '-e "source schema/promos.sql"\n')
    sys.exit(2)

sql("DELETE FROM promos WHERE nombre LIKE 'Prueba promo%'")

an0 = nueva()
st, h, u = get(an0, "/api/v1/promo")
chk("P1 sin promo vigente la API contesta 204 y no un error", st == 204, f"status={st}")
st, h, u = get(an0, "/")
chk("P1b y la portada no trae ningun banner", 'id="lpPromo"' not in h, "")

sql("""INSERT INTO promos (nombre, bajada, inicio_at, fin_at, activa, prioridad)
       VALUES ('Prueba promo vigente', 'letra chica de prueba',
               DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 HOUR),
               DATE_ADD(UTC_TIMESTAMP(), INTERVAL 3 HOUR), 1, 0)""")
st, h, u = get(nueva(), "/")
chk("P2 con una promo vigente el banner se pinta en la portada",
    'id="lpPromo"' in h and "Prueba promo vigente" in h, f"status={st}")
st, h, u = get(nueva(), "/api/v1/promo")
chk("P2b y la API la devuelve con los segundos que quedan",
    st == 200 and "Prueba promo vigente" in h and '"segundos"' in h, f"status={st}")

# El interruptor es el boton para cuando la promo se cae antes de la hora.
sql("UPDATE promos SET activa=0 WHERE nombre='Prueba promo vigente'")
st, h, u = get(nueva(), "/")
chk("P3 bajada de la portada, desaparece sin tocar el plazo",
    'id="lpPromo"' not in h, "")
sql("DELETE FROM promos WHERE nombre='Prueba promo vigente'")

# El destino del boton: mismo cuidado que el «volver» de C3. Una URL externa
# ahi seria un redirect abierto puesto en la portada.
op4, st, url = login(ADMIN_EMAIL, ADMIN_CLAVE)
st, h, _ = get(op4, "/admin/promos")
tp = tok(h)
post(op4, "/admin/promos/crear",
     {"csrf": tp, "nombre": "Prueba promo destino", "bajada": "",
      "inicio": "2030-01-01T10:00", "fin": "2030-01-02T10:00",
      "boton_texto": "Ir", "boton_destino": "https://sitio-falso.example",
      "prioridad": "0"})
# El detalle se imprime pase o falle, asi que dice lo que se ENCONTRO y no
# un veredicto: un "se guardo igual" junto a un OK se lee al reves.
guardada_mala = sql("SELECT boton_destino FROM promos WHERE nombre='Prueba promo destino'")
chk("P4 el destino del boton no acepta una URL externa",
    not guardada_mala,
    str(guardada_mala))
post(op4, "/admin/promos/crear",
     {"csrf": tp, "nombre": "Prueba promo destino", "bajada": "",
      "inicio": "2030-01-01T10:00", "fin": "2030-01-02T10:00",
      "boton_texto": "Ver la carta", "boton_destino": "#carta",
      "prioridad": "0"})
guardada = sql("SELECT boton_destino FROM promos WHERE nombre='Prueba promo destino'")
chk("P4b pero una seccion del propio sitio si se guarda",
    bool(guardada) and guardada[0]["boton_destino"] == "#carta",
    str(guardada))
sql("DELETE FROM promos WHERE nombre LIKE 'Prueba promo%'")

st, h, u = get(nueva(), "/admin/promos")
chk("P5 un anonimo no entra a las promos del panel", "/login" in str(u), str(u))

# ---------------------------------------------------------------- K (carta: categorias y combos)
# Lo que el dueno arma desde /admin/carta sin tocar SQL. Se prueba desde
# afuera, como lo veria un visitante: por /api/v1/menu y /api/v1/promo, no
# mirando la base. Si la carta publica no cambia, da igual lo que diga la
# tabla.
if not sql("SHOW TABLES LIKE 'carta_combos'"):
    print("\n  Falta la tabla `carta_combos`. Cargala y vuelve a correr la suite:")
    print('      mysql -u root -p --default-character-set=utf8mb4 '
          '-e "source schema/carta_combos.sql"\n')
    sys.exit(2)
_nulo = sql("""SELECT IS_NULLABLE AS n FROM information_schema.columns
               WHERE table_schema=DATABASE() AND table_name='carta_combos'
                 AND column_name='fin_at'""")
if not _nulo or _nulo[0]["n"] != "YES":
    print("\n  carta_combos.fin_at todavia no acepta NULL (combos sin fecha de")
    print("  termino). Vuelve a cargar schema/carta_combos.sql: trae el ALTER.\n")
    sys.exit(2)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime as _dt, timedelta as _td
from flask_app.config.negocio import NEGOCIO as _NEG
MARCA_K = _NEG["slug"]
marca_k_id = sql("SELECT id FROM marcas WHERE slug=%s", MARCA_K)[0]["id"]

def _limpiar_k():
    # Sin argumentos el helper no interpola, asi que va un solo %. Orden
    # importa: combos (arrastran sus items), despues productos, despues la
    # categoria — al reves lo bloquean las llaves foraneas.
    sql("DELETE FROM carta_combos WHERE nombre LIKE 'Prueba combo%'")
    sql("DELETE FROM productos WHERE slug LIKE 'prueba-producto-combo%'")
    sql("DELETE FROM categorias WHERE slug LIKE 'prueba-categoria%'")
_limpiar_k()

opk, _, _ = login(ADMIN_EMAIL, ADMIN_CLAVE)
_, h, _ = get(opk, f"/admin/carta/{MARCA_K}")
tk = tok(h)

# Categorias: el slug sale del nombre al crearla y NO cambia al renombrarla.
# Si cambiara, corregir una tilde romperia cualquier enlace a esa seccion.
post(opk, f"/admin/carta/{MARCA_K}/categorias/crear",
     {"csrf": tk, "nombre": "Prueba Categoría Uno", "orden": ""})
cat = sql("SELECT id, slug, orden FROM categorias WHERE marca_id=%s AND slug LIKE 'prueba-categoria%%'",
          marca_k_id)
chk("K1 crear una categoria desde el panel le calcula el slug",
    bool(cat) and cat[0]["slug"] == "prueba-categoria-uno", str(cat))

if cat:
    post(opk, f"/admin/carta/{MARCA_K}/categorias/{cat[0]['id']}",
         {"csrf": tk, "nombre": "Prueba Categoría Renombrada", "orden": "3"})
    cat2 = sql("SELECT slug, nombre, orden FROM categorias WHERE id=%s", cat[0]["id"])
    chk("K2 renombrarla cambia el nombre y el orden, pero no el slug",
        bool(cat2) and cat2[0]["nombre"] == "Prueba Categoría Renombrada"
        and cat2[0]["orden"] == 3 and cat2[0]["slug"] == "prueba-categoria-uno", str(cat2))
else:
    chk("K2 renombrarla cambia el nombre y el orden, pero no el slug", False, "no hubo K1")

post(opk, f"/admin/carta/{MARCA_K}/categorias/crear", {"csrf": tk, "nombre": "   ", "orden": ""})
chk("K3 una categoria sin nombre no se guarda",
    len(sql("SELECT id FROM categorias WHERE marca_id=%s AND TRIM(nombre)=''", marca_k_id)) == 0, "")

# Un producto propio para armar los combos, dentro de la categoria de prueba.
cat_id = cat[0]["id"] if cat else None
sql("""INSERT INTO productos (marca_id, categoria_id, slug, nombre, precio_clp, disponible, orden)
       VALUES (%s, %s, 'prueba-producto-combo', 'Prueba producto combo', 3990, 1, 0)""",
    marca_k_id, cat_id)
prod_id = sql("SELECT id FROM productos WHERE slug='prueba-producto-combo' AND marca_id=%s",
              marca_k_id)[0]["id"]

ahora = _dt.now()
inicio = (ahora - _td(days=1)).strftime("%Y-%m-%dT%H:%M")
fin = (ahora + _td(days=2)).strftime("%Y-%m-%dT%H:%M")
_, h, _ = get(opk, f"/admin/carta/{MARCA_K}/combos")
tc = tok(h)

def _combo(nombre, extra):
    base = [("csrf", tc), ("nombre", nombre), ("precio_clp", "6990"),
            ("inicio", inicio), ("orden", "0"), ("prioridad", "0"),
            ("disponible", "on"), ("producto_id", str(prod_id)),
            (f"cantidad_{prod_id}", "2")]
    return post(opk, f"/admin/carta/{MARCA_K}/combos/crear", base + extra)

def _en_la_carta(nombre):
    st, h, _ = get(nueva(), f"/api/v1/menu?marca={MARCA_K}")
    try:
        secciones = json.loads(h)
    except ValueError:
        return False, f"status={st}"
    promos = [s for s in secciones if s.get("id") == "packs"]
    nombres = [i["name"] for s in promos for i in s["items"]]
    return nombre in nombres, str(nombres)

_combo("Prueba combo con fecha", [("fin", fin)])
en, det = _en_la_carta("Prueba combo con fecha")
chk("K4 un pack vigente sale en el catalogo publico, en la seccion Packs", en, det)
# Se lee el JSON y no el texto crudo: Flask escapa los no-ASCII y el «×»
# llega como \u00d7, asi que buscarlo en el cuerpo daria falso siempre.
st, h, _ = get(nueva(), f"/api/v1/menu?marca={MARCA_K}")
try:
    _descs = [i.get("desc") or "" for sec in json.loads(h) if sec.get("id") == "packs"
              for i in sec["items"] if i["name"] == "Prueba combo con fecha"]
except ValueError:
    _descs = []
chk("K4b y dice lo que trae con el nombre real del producto",
    any("2× Prueba producto combo" in d for d in _descs), str(_descs))

_combo("Prueba combo sin termino", [("sin_termino", "on"), ("fin", fin)])
fila = sql("SELECT id, fin_at FROM carta_combos WHERE nombre='Prueba combo sin termino'")
en, det = _en_la_carta("Prueba combo sin termino")
chk("K5 sin fecha de termino se guarda fin_at NULL (aunque llegue una fecha) y sale en la carta",
    bool(fila) and fila[0]["fin_at"] is None and en, str(fila) + " " + det)

if fila:
    post(opk, f"/admin/carta/{MARCA_K}/combos/{fila[0]['id']}/interruptor", {"csrf": tc})
en, det = _en_la_carta("Prueba combo sin termino")
chk("K6 apagado con el interruptor desaparece de la carta al tiro", not en, det)

# Un id de producto que no es de esta marca (o no existe) no puede colarse
# en un combo mandandolo a mano por POST. Sin productos validos, no hay combo.
post(opk, f"/admin/carta/{MARCA_K}/combos/crear",
     [("csrf", tc), ("nombre", "Prueba combo ajeno"), ("precio_clp", "1000"),
      ("inicio", inicio), ("fin", fin), ("disponible", "on"),
      ("producto_id", "999999999")])
chk("K7 un combo con productos ajenos o inexistentes no se guarda",
    not sql("SELECT id FROM carta_combos WHERE nombre='Prueba combo ajeno'"), "")

# El banner LEE el combo marcado, sin copiarlo a la tabla promos.
_combo("Prueba combo banner", [("fin", fin), ("mostrar_en_banner", "on"), ("prioridad", "99")])
st, h, _ = get(nueva(), "/api/v1/promo")
chk("K8 un combo marcado para el banner sale en /api/v1/promo, sin copiarse a promos",
    st == 200 and "Prueba combo banner" in h
    and not sql("SELECT id FROM promos WHERE nombre='Prueba combo banner'"), f"status={st}")

_limpiar_k()

st, h, u = get(nueva(), f"/admin/carta/{MARCA_K}/combos")
chk("K9 un anonimo no entra a los combos del panel", "/login" in str(u), str(u))

# ---------------------------------------------------------------- B (pedidos para retiro)
# Un vecino pide desde /pedir, elige una franja y paga al retirar. Se prueba
# como lo haria el: por el formulario y la pagina de su pedido. La base se
# mira solo para lo que el navegador no muestra (el total que se guardo).
if not sql("SHOW TABLES LIKE 'barra_pedidos'"):
    print("\n  Falta la tabla `barra_pedidos`. Cargala y vuelve a correr la suite:")
    print('      mysql -u root -p --default-character-set=utf8mb4 '
          '-e "source schema/barra_pedidos.sql"\n')
    sys.exit(2)

TEL_B = ("+56900000001", "+56900000002", "+56900000003")
_conf_original = sql("SELECT * FROM barra_config WHERE id=1")[0]

def _limpiar_b():
    sql("DELETE FROM barra_pedidos WHERE telefono IN %s", TEL_B)

def _config_b(op_admin, **cambios):
    """Guarda la configuracion POR EL PANEL, no por SQL: es lo que borra el
    cache del interruptor y lo que hace el dueno de verdad."""
    _, h, _ = get(op_admin, "/admin/barra")
    cats = [str(c["id"]) for c in sql(
        "SELECT c.id FROM categorias c JOIN marcas m ON m.id=c.marca_id WHERE m.slug=%s",
        MARCA_K)]
    datos = {"activo": "1", "hora_inicio": "00:00", "hora_fin": "23:59",
             "intervalo_min": "15", "cupos_por_franja": "2", "max_items": "4",
             "anticipacion_min": "0", "dias_adelante": "1",
             "lugar_publico": "Barrio de prueba",
             "direccion_retiro": "Pasaje Secreto 742", "aviso": ""}
    datos.update(cambios)
    campos = [(k, v) for k, v in datos.items() if v is not None]
    campos += [("dias", str(d)) for d in range(1, 8)]
    campos += [("categorias", c) for c in cats] + [("incluir_combos", "1")]
    campos.append(("csrf", tok(h)))
    return post(op_admin, "/admin/barra/config", campos)

def _pedir(op, tel, franja, cant, extra=None):
    _, h, _ = get(op, "/pedir")
    datos = [("csrf", tok(h)), ("nombre", "Vecina Prueba"), ("telefono", tel),
             ("franja", franja), ("notas", "")]
    datos += [(f"cant_{k}", str(v)) for k, v in cant.items()]
    datos += list((extra or {}).items())
    return post(op, "/pedir", datos)

_limpiar_b()
adm_b, _, _ = login(ADMIN_EMAIL, ADMIN_CLAVE)
prod_b = sql("""SELECT p.id, p.precio_clp FROM productos p JOIN marcas m ON m.id=p.marca_id
                WHERE m.slug=%s AND p.disponible=1 AND p.categoria_id IS NOT NULL
                ORDER BY p.id LIMIT 1""", MARCA_K)[0]
P_B = f"p-{prod_b['id']}"

# Cerrada: ni enlace en la portada ni pedido que entre.
_config_b(adm_b, activo=None)
_, h_land, _ = get(nueva(), "/")
st, h, _ = get(nueva(), "/pedir")
chk("B1 con los pedidos cerrados la portada no ofrece el boton y /pedir lo dice",
    'href="/pedir"' not in h_land and "no estamos tomando pedidos" in h, f"status={st}")

# Abierta.
_config_b(adm_b)
_, h_land, _ = get(nueva(), "/")
op_v = nueva()
st, h, _ = get(op_v, "/pedir")
libres = re.findall(r'name="franja" value="([0-9T:\-]+)"(?![^>]*disabled)', h)
chk("B2 al abrirlos desde el panel aparece el boton y /pedir ofrece franjas",
    'href="/pedir"' in h_land and st == 200 and len(libres) >= 3,
    f"franjas={len(libres)}")
chk("B2b /pedir muestra el barrio pero NO la direccion exacta",
    "Barrio de prueba" in h and "Pasaje Secreto" not in h, "")

# El precio lo pone el servidor, aunque el formulario traiga otro.
st, h, url = _pedir(op_v, "9 0000 0001", libres[0], {P_B: 2},
                    extra={f"precio_{P_B}": "1", "total": "1"})
if st == 429:
    # Mismo caso que frenado(): el freno de 6 pedidos por hora vive en la
    # memoria de la app y lo gasto una corrida anterior de la suite.
    print("\n  El freno de pedidos por conexion ya esta activo (HTTP 429).")
    print("  Reinicia la app y vuelve a correr la suite.\n")
    sys.exit(2)
fila = sql("SELECT * FROM barra_pedidos WHERE telefono=%s", TEL_B[0])
chk("B3 el pedido entra y lleva a su pagina con codigo",
    st == 200 and "/pedido/PD-" in str(url) and len(fila) == 1, f"status={st} url={url}")
chk("B3b el total sale de la base, no del formulario",
    fila and fila[0]["total_clp"] == 2 * prod_b["precio_clp"],
    f"total={fila[0]['total_clp'] if fila else None}")
cod_a = fila[0]["codigo"] if fila else "PD-XXXX-XXXX"
chk("B3c la pagina del pedido SI muestra la direccion exacta",
    "Pasaje Secreto 742" in h and "Pagas al retirar" in h, "")
st, h, _ = get(nueva(), f"/api/v1/pedido/{cod_a}")
chk("B4 el JSON de seguimiento responde y no expone el telefono",
    st == 200 and '"recibido"' in h and "+569" not in h and "telefono" not in h, f"status={st}")

# Cupo: con 1 por franja, la franja ya tomada no acepta otro pedido.
sql("UPDATE barra_config SET cupos_por_franja=1 WHERE id=1")
op_w = nueva()
st, h, _ = _pedir(op_w, "9 0000 0002", libres[0], {P_B: 1})
chk("B5 una franja llena rechaza el pedido siguiente (409)",
    st == 409 and "Se llen" in h and not sql("SELECT id FROM barra_pedidos WHERE telefono=%s", TEL_B[1]),
    f"status={st}")
st, h, _ = _pedir(op_w, "9 0000 0002", "2020-01-01T10:00", {P_B: 1})
chk("B6 una franja inventada o pasada se rechaza", st == 409 and "ya no est" in h, f"status={st}")
st, h, _ = _pedir(op_w, "9 0000 0002", libres[1], {"p-999999999": 1})
chk("B7 un producto que no esta en la carta no arma pedido", st == 409, f"status={st}")
st, h, _ = _pedir(op_w, "9 0000 0002", libres[1], {P_B: 9})
chk("B8 mas unidades que el maximo se rechaza", st == 409 and "hasta 4" in h, f"status={st}")

# El cliente cancela mientras nadie lo toca, y eso libera la franja.
_, h, _ = get(op_v, f"/pedido/{cod_a}")
post(op_v, f"/pedido/{cod_a}/cancelar", {"csrf": tok(h)})
st, h, url = _pedir(op_w, "9 0000 0002", libres[0], {P_B: 1})
fila_b = sql("SELECT * FROM barra_pedidos WHERE telefono=%s", TEL_B[1])
chk("B9 cancelar desde la pagina del pedido libera la franja para otro",
    sql("SELECT estado FROM barra_pedidos WHERE codigo=%s", cod_a)[0]["estado"] == "cancelado"
    and len(fila_b) == 1, f"status={st}")
cod_b, id_b = (fila_b[0]["codigo"], fila_b[0]["id"]) if fila_b else ("PD-XXXX-XXXX", 0)

# Una vez que se empieza a preparar, el cliente ya no lo cancela solo.
_, h, _ = get(adm_b, "/admin/barra")
post(adm_b, f"/admin/barra/{id_b}/estado", {"csrf": tok(h), "estado": "preparando"})
_, h, _ = get(op_w, f"/pedido/{cod_b}")
post(op_w, f"/pedido/{cod_b}/cancelar", {"csrf": tok(h)})
chk("B10 un pedido en preparacion no se cancela desde la pagina del cliente",
    sql("SELECT estado FROM barra_pedidos WHERE id=%s", id_b)[0]["estado"] == "preparando", "")

# «Estoy afuera» llega al panel.
_, h, _ = get(op_w, f"/pedido/{cod_b}")
post(op_w, f"/pedido/{cod_b}/afuera", {"csrf": tok(h), "detalle": "auto de prueba"})
_, h_adm, _ = get(adm_b, "/admin/barra?dia=" + libres[0][:10])
chk("B11 «estoy afuera» queda marcado y el panel lo muestra",
    sql("SELECT afuera_at FROM barra_pedidos WHERE id=%s", id_b)[0]["afuera_at"] is not None
    and "auto de prueba" in h_adm, "")

# Entregar un pedido que se paga al retirar lo deja cobrado.
post(adm_b, f"/admin/barra/{id_b}/estado", {"csrf": tok(h_adm), "estado": "entregado"})
f = sql("SELECT estado, pagado_at FROM barra_pedidos WHERE id=%s", id_b)[0]
chk("B12 entregar lo deja entregado y cobrado en un solo paso",
    f["estado"] == "entregado" and f["pagado_at"] is not None, f["estado"])

# Un mismo celular no acapara la manana.
sql("UPDATE barra_config SET cupos_por_franja=3 WHERE id=1")
op_x = nueva()
_pedir(op_x, "9 0000 0003", libres[1], {P_B: 1})
_pedir(op_x, "9 0000 0003", libres[2], {P_B: 1})
st, h, _ = _pedir(op_x, "9 0000 0003", libres[2], {P_B: 1})
chk("B13 un tercer pedido en curso desde el mismo celular se rechaza",
    st == 409 and len(sql("SELECT id FROM barra_pedidos WHERE telefono=%s", TEL_B[2])) == 2,
    f"status={st}")

st, h, u = get(nueva(), "/admin/barra")
chk("B14 un anonimo no entra a la cola del panel", "/login" in str(u), str(u))

_limpiar_b()
# La configuracion vuelve a como estaba: la suite no le abre (ni le cierra)
# los pedidos al negocio.
_c = dict(_conf_original)
sql("""UPDATE barra_config SET activo=%s, dias=%s, hora_inicio=%s, hora_fin=%s,
         intervalo_min=%s, cupos_por_franja=%s, max_items=%s, anticipacion_min=%s,
         dias_adelante=%s, categorias=%s, incluir_combos=%s, lugar_publico=%s,
         direccion_retiro=%s, aviso=%s WHERE id=1""",
    _c["activo"], _c["dias"], _c["hora_inicio"], _c["hora_fin"], _c["intervalo_min"],
    _c["cupos_por_franja"], _c["max_items"], _c["anticipacion_min"], _c["dias_adelante"],
    _c["categorias"], _c["incluir_combos"], _c["lugar_publico"], _c["direccion_retiro"],
    _c["aviso"])

# ---------------------------------------------------------------- R (ruleta de premios)
# Cada giro lo habilita el admin y sirve una vez; el premio lo sortea el
# servidor. Se prueba como en la caja: el panel habilita, la pagina del giro
# gira. La base se mira para confirmar que lo guardado es lo que se mostro.
if not sql("SHOW TABLES LIKE 'ruleta_giros'"):
    print("\n  Falta la tabla `ruleta_giros`. Cargala y vuelve a correr la suite:")
    print('      mysql -u root -p --default-character-set=utf8mb4 '
          '-e "source schema/ruleta.sql"\n')
    sys.exit(2)

_premios_orig = [f["premio"] for f in sql("SELECT premio FROM ruleta_gajos ORDER BY posicion")]
REF_R = "Prueba suite ruleta"
PREMIOS_R = ["Cafe gratis", "Galleta", "Sigue participando", "Sigue participando"] * 3

def _token_giro(h):
    m = re.search(r'csrfToken = "([^"]+)"', h)
    return m.group(1) if m else None

st, h, u = get(nueva(), "/admin/ruleta")
chk("R1 un anonimo no entra a la ruleta del panel", "/login" in str(u), str(u))
op_anon = nueva()
_, h, _ = get(op_anon, "/")
antes = sql("SELECT COUNT(*) AS n FROM ruleta_giros")[0]["n"]
post(op_anon, "/admin/ruleta/habilitar", {"csrf": tok(h) or "x", "referencia": REF_R})
chk("R2 un anonimo no puede habilitar giros",
    sql("SELECT COUNT(*) AS n FROM ruleta_giros")[0]["n"] == antes, "")

adm_r, _, _ = login(ADMIN_EMAIL, ADMIN_CLAVE)
_, h, _ = get(adm_r, "/admin/ruleta")
post(adm_r, "/admin/ruleta/premios", [("csrf", tok(h))] + [("premio", p) for p in PREMIOS_R[:-1]] + [("premio", "  ")])
chk("R3 un gajo sin premio no se guarda",
    [f["premio"] for f in sql("SELECT premio FROM ruleta_gajos ORDER BY posicion")] == _premios_orig, "")
st, h, _ = post(adm_r, "/admin/ruleta/premios", [("csrf", tok(h))] + [("premio", p) for p in PREMIOS_R])
guardados = [f["premio"] for f in sql("SELECT premio FROM ruleta_gajos ORDER BY posicion")]
chk("R4 los 12 premios se guardan en orden y el panel muestra el % real de cada uno",
    guardados == PREMIOS_R and "50.0%" in h and "25.0%" in h, f"gajos={len(guardados)}")

st, h, url = post(adm_r, "/admin/ruleta/habilitar", {"csrf": tok(h), "referencia": REF_R})
m = re.search(r"nuevo=(RL-[A-Z2-9]{4}-[A-Z2-9]{4})", str(url))
cod_r = m.group(1) if m else "RL-XXXX-XXXX"
chk("R5 habilitar crea un giro y el panel muestra su QR",
    m is not None and "<svg" in h and "Girar en este dispositivo" in h, str(url))

op_c = nueva()
st, h, _ = get(op_c, f"/ruleta/{cod_r}")
chk("R6 la pagina del giro ofrece girar", st == 200 and 'id="btnGirar"' in h, f"status={st}")
st, j, _ = post(op_c, f"/ruleta/{cod_r}/girar", {"csrf": _token_giro(h)})
try:
    r1 = json.loads(j)
except ValueError:
    r1 = {}
fila = sql("SELECT gajo_indice, premio FROM ruleta_giros WHERE codigo=%s", cod_r)
chk("R7 girar sortea un gajo valido y guarda ese mismo premio",
    st == 200 and 0 <= r1.get("indice", -1) < 12 and r1.get("premio") == PREMIOS_R[r1["indice"]]
    and fila and fila[0]["premio"] == r1["premio"], f"status={st} {r1.get('premio')}")
st, j, _ = post(op_c, f"/ruleta/{cod_r}/girar", {"csrf": _token_giro(h)})
r2 = json.loads(j) if st == 200 else {}
chk("R8 girar otra vez NO vuelve a sortear: devuelve lo mismo",
    r2.get("indice") == r1.get("indice") and r2.get("nuevo") is False, f"status={st}")

# Cambiar los premios despues no reescribe lo que ya salio.
_, h, _ = get(adm_r, "/admin/ruleta")
post(adm_r, "/admin/ruleta/premios", [("csrf", tok(h))] + [("premio", f"Otro {i}") for i in range(12)])
st, h, _ = get(nueva(), f"/ruleta/{cod_r}")
chk("R9 un giro hecho sigue mostrando su ruleta y su premio aunque cambien los premios",
    r1.get("premio", "?") in h and "Otro 3" not in h and "btnGirar" not in h, "")

# El token de una pagina con formulario de la MISMA sesion: sin eso el
# rechazo seria por CSRF y no se estaria probando lo que importa.
def _token_sesion(op):
    _, hl, _ = get(op, "/login")
    return tok(hl)

st, _, _ = get(nueva(), "/ruleta/RL-AAAA-AAAA")
st2, _, _ = post(op_c, "/ruleta/RL-AAAA-AAAA/girar", {"csrf": _token_sesion(op_c)})
chk("R10 un codigo inventado no existe", st == 404 and st2 == 410, f"{st} {st2}")

# Vencido y anulado no giran.
_, h, _ = get(adm_r, "/admin/ruleta")
_, _, url = post(adm_r, "/admin/ruleta/habilitar", {"csrf": tok(h), "referencia": REF_R})
cod_v = re.search(r"nuevo=(RL-[A-Z2-9-]+)", str(url)).group(1)
sql("UPDATE ruleta_giros SET vence_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 MINUTE) WHERE codigo=%s", cod_v)
op_v = nueva()
_, hv, _ = get(op_v, f"/ruleta/{cod_v}")
st, _, _ = post(op_v, f"/ruleta/{cod_v}/girar", {"csrf": _token_sesion(op_v)})
chk("R11 un giro vencido no gira (410) y no guarda premio",
    st == 410 and sql("SELECT girado_at FROM ruleta_giros WHERE codigo=%s", cod_v)[0]["girado_at"] is None
    and "venci" in hv, f"status={st}")

_, h, _ = get(adm_r, "/admin/ruleta")
_, _, url = post(adm_r, "/admin/ruleta/habilitar", {"csrf": tok(h), "referencia": REF_R})
cod_n = re.search(r"nuevo=(RL-[A-Z2-9-]+)", str(url)).group(1)
op_n = nueva()
_, hn, _ = get(op_n, f"/ruleta/{cod_n}")
id_n = sql("SELECT id FROM ruleta_giros WHERE codigo=%s", cod_n)[0]["id"]
post(adm_r, f"/admin/ruleta/giros/{id_n}/anular", {"csrf": tok(h)})
st, _, _ = post(op_n, f"/ruleta/{cod_n}/girar", {"csrf": _token_giro(hn)})
chk("R12 un giro anulado no gira", st == 410
    and sql("SELECT girado_at FROM ruleta_giros WHERE id=%s", id_n)[0]["girado_at"] is None, f"status={st}")
st, _, _ = post(nueva(), f"/ruleta/{cod_n}/girar", {})
chk("R13 girar sin el token de la pagina se rechaza", st == 400, f"status={st}")

sql("DELETE FROM ruleta_giros WHERE referencia=%s", REF_R)
# Los premios vuelven a como estaban: la suite no le cambia la ruleta al negocio.
sql("DELETE FROM ruleta_gajos")
for _i, _p in enumerate(_premios_orig):
    sql("INSERT INTO ruleta_gajos (posicion, premio) VALUES (%s, %s)", _i, _p)

# ---------------------------------------------------------------- E (personal: el rol barista)
# El admin hace barista a una cuenta desde Cuentas. El barista entra a lo de
# la barra (vales, ruleta) y a nada mas; quitarle el rol surte efecto al tiro.
BAR_EMAIL, BAR_CLAVE = "barista-prueba@x.cl", "Clave-Barista-123"
def _limpiar_e():
    sql("DELETE FROM vales WHERE valido_por LIKE 'Prueba suite%%'")
    sql("DELETE FROM vale_lotes WHERE nombre LIKE 'Prueba suite%%'")
    sql("UPDATE ruleta_giros SET habilitado_por=NULL WHERE habilitado_por IN (SELECT id FROM usuarios WHERE email=%s)", BAR_EMAIL)
    sql("DELETE FROM usuarios WHERE email=%s", BAR_EMAIL)
if not sql("SHOW TABLES LIKE 'vales'"):
    print("\n  Falta la tabla `vales`. Cargala y vuelve a correr la suite:")
    print('      mysql -u root -p --default-character-set=utf8mb4 '
          '-e "source schema/vales.sql"\n')
    sys.exit(2)
_limpiar_e()
# Las cuentas de este bloque se crean por SQL y no por /registro: el freno
# anti-registros (5 por hora desde una IP) ya lo gastan los bloques C.
from flask_app.config.seguridad import hashear as _hashear
def _cuenta(email, clave, nombre, nick):
    sql("""INSERT INTO usuarios (nombre, email, password_hash, rol, estado, nickname, email_verificado_at)
           VALUES (%s, %s, %s, 'cliente', 'activo', %s, UTC_TIMESTAMP())""",
        nombre, email, _hashear(clave), nick)
_cuenta(BAR_EMAIL, BAR_CLAVE, "Barista", "baristaprueba")
bar_id = sql("SELECT id FROM usuarios WHERE email=%s", BAR_EMAIL)[0]["id"]
adm_e, _, _ = login(ADMIN_EMAIL, ADMIN_CLAVE)
_, h, _ = get(adm_e, "/admin/usuarios")
post(adm_e, f"/admin/usuarios/{bar_id}/rol", {"csrf": tok(h), "nuevo_rol": "barista"})
chk("E1 el admin hace barista a una cuenta desde Cuentas",
    sql("SELECT rol FROM usuarios WHERE id=%s", bar_id)[0]["rol"] == "barista", "")

op_bar, _, _ = login(BAR_EMAIL, BAR_CLAVE)
st, h, _ = get(op_bar, "/admin")
chk("E2 el barista entra al panel y ve solo vales y ruleta",
    st == 200 and "/admin/vales" in h and "/admin/ruleta" in h
    and "/admin/usuarios" not in h and "/admin/carta" not in h, f"status={st}")
st1, _, _ = get(op_bar, "/admin/usuarios")
st2, _, _ = get(op_bar, "/admin/carta")
st3, _, _ = get(op_bar, "/admin/ventas")
chk("E3 el barista no entra a cuentas, carta ni ventas (404)", (st1, st2, st3) == (404, 404, 404), f"{st1} {st2} {st3}")

admin_id = sql("SELECT id FROM usuarios WHERE email=%s", ADMIN_EMAIL)[0]["id"]
_, h, _ = get(adm_e, "/admin/usuarios")
st_a, _, _ = post(adm_e, f"/admin/usuarios/{bar_id}/rol", {"csrf": tok(h), "nuevo_rol": "admin"})
st_b, _, _ = post(adm_e, f"/admin/usuarios/{admin_id}/rol", {"csrf": tok(h), "nuevo_rol": "barista"})
chk("E4 desde Cuentas no se da el rol admin ni se toca a un admin",
    st_a == 400 and st_b == 400 and sql("SELECT rol FROM usuarios WHERE id=%s", bar_id)[0]["rol"] == "barista"
    and sql("SELECT rol FROM usuarios WHERE id=%s", admin_id)[0]["rol"] == "admin", f"{st_a} {st_b}")

# Crear la cuenta de un barista desde el panel: nace sin contrasena, con un
# enlace para que la elija el mismo.
NUEVO_BAR = "barista-nuevo@x.cl"
sql("DELETE FROM usuarios WHERE email=%s", NUEVO_BAR)
_, h, _ = get(adm_e, "/admin/usuarios")
st, h, url = post(adm_e, "/admin/usuarios/crear-barista", {"csrf": tok(h),
    "nombre": "Nueva", "apellido": "Barista", "email": NUEVO_BAR, "telefono": "9 8888 7777"})
f = sql("SELECT rol, estado, password_hash FROM usuarios WHERE email=%s", NUEVO_BAR)
m = re.search(r'/bienvenida\?token=([^"&\s<]+)', h)
chk("E6 el admin crea un barista: nace sin contrasena y con un enlace para crearla",
    bool(f) and f[0]["rol"] == "barista" and f[0]["estado"] == "invitado"
    and f[0]["password_hash"] is None and m is not None and "wa.me/56988887777" in h, str(url))
token_bv = m.group(1) if m else "x"
st_r, _, _ = get(nueva(), "/restablecer-password?token=" + token_bv)
chk("E7 el enlace de invitacion no sirve como enlace de recuperar contrasena", st_r == 400, f"status={st_r}")
op_nb = nueva()
st, h, _ = get(op_nb, "/bienvenida?token=" + token_bv)
st2, h2, url2 = post(op_nb, "/bienvenida", {"csrf": tok(h), "token": token_bv,
    "password": "Clave-Nueva-Barista-1", "password2": "Clave-Nueva-Barista-1"})
f = sql("SELECT estado, password_hash FROM usuarios WHERE email=%s", NUEVO_BAR)[0]
chk("E8 el barista crea su contrasena con el enlace y entra directo a la barra",
    st == 200 and "Crea tu contrase" in h and f["estado"] == "activo" and f["password_hash"]
    and "/admin" in str(url2) and "Vales" in h2, f"status={st} url={url2}")
st, _, _ = get(nueva(), "/bienvenida?token=" + token_bv)
chk("E9 el enlace de invitacion sirve una sola vez", st == 400, f"status={st}")
_, h, _ = get(adm_e, "/admin/usuarios")
post(adm_e, "/admin/usuarios/crear-barista", {"csrf": tok(h), "nombre": "Otra", "email": ADMIN_EMAIL})
chk("E10 crear un barista con el correo de una cuenta existente no la toca",
    sql("SELECT rol FROM usuarios WHERE email=%s", ADMIN_EMAIL)[0]["rol"] == "admin", "")
sql("DELETE FROM usuarios WHERE email=%s", NUEVO_BAR)

# ---------------------------------------------------------------- V (vales)
st, h, u = get(nueva(), "/admin/vales")
chk("V1 un anonimo no entra a los vales del panel", "/login" in str(u), str(u))

_, h, _ = get(op_bar, "/admin/vales")
manana = (_dt.utcnow() + _td(days=3)).date().isoformat()
st, h, url = post(op_bar, "/admin/vales/emitir", {"csrf": tok(h), "tipo": "regalo",
    "valido_por": "Prueba suite 1 cafe", "para_nombre": "Ana", "para_telefono": "9 1234 5678",
    "motivo": "Cortesia", "vence": manana})
m = re.search(r"/vale/(VL-[A-Z2-9]{4}-[A-Z2-9]{4})", str(url))
cod_v = m.group(1) if m else "VL-XXXX-XXXX"
f = sql("SELECT * FROM vales WHERE codigo=%s", cod_v)
chk("V2 el barista emite un vale de regalo con vencimiento y queda a su nombre",
    bool(f) and f[0]["tipo"] == "regalo" and f[0]["vence_at"] is not None
    and f[0]["emitido_por"] == bar_id and f[0]["para_telefono"] == "+56912345678"
    and "Enviar por WhatsApp" in h and "wa.me/56912345678" in h, str(url))

_, h, _ = get(op_bar, "/admin/vales")
st, h, url = post(op_bar, "/admin/vales/emitir", {"csrf": tok(h), "tipo": "giftcard",
    "valido_por": "Prueba suite gift", "comprador": "Pedro", "monto_pagado_clp": "15.000", "vence": manana})
mg = re.search(r"/vale/(VL-[A-Z2-9-]+)", str(url))
fg = sql("SELECT * FROM vales WHERE codigo=%s", mg.group(1)) if mg else []
chk("V3 una gift card se guarda con su monto y SIN vencimiento aunque llegue una fecha",
    bool(fg) and fg[0]["tipo"] == "giftcard" and fg[0]["monto_pagado_clp"] == 15000 and fg[0]["vence_at"] is None, str(url))
_, h, _ = get(op_bar, "/admin/vales")
antes = sql("SELECT COUNT(*) AS n FROM vales")[0]["n"]
post(op_bar, "/admin/vales/emitir", {"csrf": tok(h), "tipo": "giftcard", "valido_por": "Prueba suite sin monto"})
chk("V4 una gift card sin monto no se emite", sql("SELECT COUNT(*) AS n FROM vales")[0]["n"] == antes, "")

st, h, _ = get(nueva(), f"/vale/{cod_v}")
chk("V5 cualquiera ve el vale con su QR, pero sin el boton de canjear",
    st == 200 and "Prueba suite 1 cafe" in h and "<svg" in h and "Canjear vale" not in h, f"status={st}")

sql("DELETE FROM usuarios WHERE email='cliente-vales@x.cl'")
_cuenta("cliente-vales@x.cl", "Clave-Cliente-123", "Cliente", "clientevales")
op_cli, _, _ = login("cliente-vales@x.cl", "Clave-Cliente-123")
_, h, _ = get(op_cli, f"/vale/{cod_v}")
st, _, _ = post(op_cli, f"/vale/{cod_v}/canjear", {"csrf": _token_sesion(op_cli)})
chk("V6 un cliente con sesion no puede canjear (404) y el vale sigue vigente",
    st == 404 and sql("SELECT canjeado_at FROM vales WHERE codigo=%s", cod_v)[0]["canjeado_at"] is None
    and "Canjear vale" not in h, f"status={st}")

_, h, _ = get(op_bar, f"/vale/{cod_v}")
tiene_boton = "Canjear vale" in h
st, h, _ = post(op_bar, f"/vale/{cod_v}/canjear", {"csrf": tok(h)})
f = sql("SELECT canjeado_at, canjeado_por FROM vales WHERE codigo=%s", cod_v)[0]
chk("V7 el barista ve el boton, canjea, y queda quien y cuando",
    tiene_boton and f["canjeado_at"] is not None and f["canjeado_por"] == bar_id and "Vale canjeado" in h, "")
primero = f["canjeado_at"]
_, h, _ = get(op_bar, f"/vale/{cod_v}")
st, h, _ = post(op_bar, f"/vale/{cod_v}/canjear", {"csrf": _token_sesion(op_bar)})
chk("V8 un vale canjeado no se canjea dos veces",
    "ya se canje" in h and sql("SELECT canjeado_at FROM vales WHERE codigo=%s", cod_v)[0]["canjeado_at"] == primero, "")

_, h, _ = get(op_bar, "/admin/vales")
_, _, url = post(op_bar, "/admin/vales/emitir", {"csrf": tok(h), "tipo": "regalo", "valido_por": "Prueba suite vencido"})
cod_x = re.search(r"/vale/(VL-[A-Z2-9-]+)", str(url)).group(1)
sql("UPDATE vales SET vence_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 MINUTE) WHERE codigo=%s", cod_x)
_, h, _ = get(op_bar, f"/vale/{cod_x}")
st, h2, _ = post(op_bar, f"/vale/{cod_x}/canjear", {"csrf": _token_sesion(op_bar)})
chk("V9 un vale vencido no se canjea",
    "Canjear vale" not in h and "venci" in h2 and sql("SELECT canjeado_at FROM vales WHERE codigo=%s", cod_x)[0]["canjeado_at"] is None, "")

_, h, _ = get(op_bar, "/admin/vales")
st, h, url = post(op_bar, "/admin/vales/lote", {"csrf": tok(h), "nombre": "Prueba suite evento",
    "cantidad": "5", "valido_por": "Prueba suite lote cafe"})
n_lote = sql("SELECT COUNT(*) AS n FROM vales v JOIN vale_lotes l ON l.id=v.lote_id WHERE l.nombre='Prueba suite evento'")[0]["n"]
chk("V10 emitir para un evento crea los vales y la hoja trae un QR por cada uno",
    n_lote == 5 and len(re.findall(r'class="corte( corte--usado)?"', h)) == 5 and h.count("<svg") >= 5 and "Imprimir" in h, f"vales={n_lote}")

_, h, _ = get(adm_e, "/admin/vales?tipo=giftcard")
_, h_todos, _ = get(adm_e, "/admin/vales")
chk("V11 la lista del panel tiene los dos tipos y el filtro por tipo funciona",
    "Prueba suite gift" in h and "Prueba suite 1 cafe" not in h
    and "Prueba suite gift" in h_todos and "Prueba suite 1 cafe" in h_todos, "")

_, h, _ = get(op_bar, "/admin/vales")
vid = sql("SELECT id FROM vales WHERE valido_por='Prueba suite gift'")[0]["id"]
st, _, _ = post(op_bar, f"/admin/vales/{vid}/anular", {"csrf": tok(h)})
chk("V12 el barista no ve lo vendido ni puede anular (404)",
    "vendido en" not in h and st == 404
    and sql("SELECT anulado_at FROM vales WHERE id=%s", vid)[0]["anulado_at"] is None, f"status={st}")

# Quitarle el rol surte efecto al tiro, sin cerrar sesion.
_, h, _ = get(adm_e, "/admin/usuarios")
post(adm_e, f"/admin/usuarios/{bar_id}/rol", {"csrf": tok(h), "nuevo_rol": "cliente"})
st, _, _ = get(op_bar, "/admin/vales")
chk("E5 al quitarle el rol, el barista pierde el panel en su sesion abierta", st == 404, f"status={st}")

sql("DELETE FROM usuarios WHERE email='cliente-vales@x.cl'")
_limpiar_e()

# ---------------------------------------------------------------- M (mascotas de temporada)
# Las fechas se repiten cada año, incluyen los dos extremos y pueden cruzar
# el año. Se prueba la funcion de rango sin tocar la lista del negocio.
from datetime import date as _date
from flask_app.config import temporadas as _temp
chk("M1 una temporada del 1 al 31 de octubre incluye el 31 y no el 1 de noviembre",
    _temp._en_rango(_date(2026, 10, 31), (10, 1), (10, 31))
    and not _temp._en_rango(_date(2026, 11, 1), (10, 1), (10, 31))
    and _temp._en_rango(_date(2027, 10, 1), (10, 1), (10, 31)), "")
chk("M2 una temporada que cruza el año (15 dic al 6 ene)",
    _temp._en_rango(_date(2027, 1, 6), (12, 15), (1, 6))
    and not _temp._en_rango(_date(2027, 1, 7), (12, 15), (1, 6)), "")
st, h, u = get(nueva(), "/login")
from flask_app.config.negocio import NEGOCIO as _NEG
chk("M3 sin temporada la mascota sale de su ruta de siempre (o no sale si estan apagadas)",
    ("/static/img/mascotas/mano.png" in h) if _NEG["mascotas"] else ("img/mascotas/" not in h), "")

# ---------------------------------------------------------------- D (destacados de la tienda)
# El admin resalta productos de Shopify: borde de color, cinta, primeros en
# su categoria. Sin token de Shopify en el .env de prueba, el orden se prueba
# llamando al modelo con un catalogo armado aca.
if not sql("SHOW TABLES LIKE 'tienda_destacados'"):
    print("\n  Falta la tabla `tienda_destacados`. Cargala y vuelve a correr la suite:")
    print('      mysql -u root -p --default-character-set=utf8mb4 '
          '-e "source schema/tienda_destacados.sql"\n')
    sys.exit(2)
from flask_app.models.destacado_model import aplicar as _aplicar
_cat = [{"id": "a", "categoria": "Café"}, {"id": "f1", "categoria": "Filtros"},
        {"id": "b", "categoria": "Café"}, {"id": "c", "categoria": "Café"},
        {"id": "f2", "categoria": "Filtros"}]
_res = _aplicar(_cat, {"c": {"color": "dorado", "cinta": "Micro lote", "orden": 0},
                       "f2": {"color": "rojo", "cinta": "Nuevo", "orden": 0},
                       "b": {"color": "verde", "cinta": "x", "orden": 1}})
chk("D1 los destacados van primeros en su categoria y el orden de las categorias no cambia",
    [p["id"] for p in _res] == ["c", "b", "a", "f2", "f1"], str([p["id"] for p in _res]))
chk("D2 aplicar no toca el catalogo original (es la cache de Shopify)",
    "destacado" not in _cat[0] and [p["id"] for p in _cat] == ["a", "f1", "b", "c", "f2"], "")

# Un micro lote de una sola version (solo en grano) no tiene molienda, pero
# si ficha tecnica: es cafe, no accesorio. Unos filtros sin ficha siguen
# siendo accesorio. Con «Tipo de producto» escrito, manda lo escrito.
from flask_app.config import shopify as _shop
def _unico(ficha=None, tipo=""):
    crudo = {"handle": "x", "title": "x", "productType": tipo,
             "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/1", "availableForSale": True,
                                     "price": {"amount": "1000"},
                                     "selectedOptions": [{"name": "Title", "value": "Default Title"}]}]}}
    if ficha:
        crudo["marca"] = {"value": ficha}
    return _shop.normalizar(crudo)["categoria"]
chk("D2b un producto de una sola version con ficha tecnica es insumo; sin ficha, accesorio",
    _unico("Marca X") == _shop.CATEGORIA_CAFE and _unico() == _shop.CATEGORIA_OTROS
    and _unico("Marca X", "Tintas") == "Tintas", str((_unico("Marca X"), _unico())))

st, h, u = get(nueva(), "/admin/tienda")
chk("D3 un anonimo no entra a los destacados de la tienda", "/login" in str(u), str(u))

_orig_d = sql("SELECT * FROM tienda_destacados")
sql("DELETE FROM tienda_destacados")
sql("INSERT INTO tienda_destacados (handle, color, cinta, orden) VALUES ('prueba-suite-existente','verde','Vieja',3)")
adm_d, _, _ = login(ADMIN_EMAIL, ADMIN_CLAVE)
# Sin Shopify en el .env de prueba el panel no muestra formulario (no hay
# productos que elegir): el token sale de otra pagina de la misma sesion.
post(adm_d, "/admin/tienda", [("csrf", _token_sesion(adm_d)), ("destacar", "prueba-suite-inventado"),
     ("destacar", "prueba-suite-existente"), ("color__prueba-suite-existente", "fucsia"),
     ("cinta__prueba-suite-existente", "   "), ("orden__prueba-suite-existente", "9999")])
f = sql("SELECT * FROM tienda_destacados")
chk("D4 un producto inventado por POST no se destaca; color, cinta y orden raros caen a lo seguro",
    len(f) == 1 and f[0]["handle"] == "prueba-suite-existente" and f[0]["color"] == "dorado"
    and f[0]["cinta"] == "Edición especial" and f[0]["orden"] == 999, str(f))
sql("DELETE FROM tienda_destacados")
for _d in _orig_d:
    sql("INSERT INTO tienda_destacados (handle, color, cinta, orden) VALUES (%s,%s,%s,%s)",
        _d["handle"], _d["color"], _d["cinta"], _d["orden"])

# ---------------------------------------------------------------- humo general
sql("UPDATE usuarios SET estado='activo' WHERE email='cliente@x.cl'")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flask_app.config.negocio import NEGOCIO

publicas = ["/", "/login", "/registro", "/actividades", "/muro", "/producto", "/api/v1/menu", "/api/v1/agenda", "/api/v1/muro",
            "/health"]  # /api/v1/tienda da 503 sin Shopify configurado: es lo correcto
if NEGOCIO["segunda"]["activa"]:
    publicas.append("/" + NEGOCIO["segunda"]["slug"])
malas = []
an = nueva()
for r in publicas:
    st, h, u = get(an, r)
    if st != 200:
        malas.append(f"{r}={st}")
chk("H1 todas las rutas publicas responden 200", not malas, ", ".join(malas))
st, h, u = get(an, "/admin")
st, h, u = get(an, "/api/v1/tienda")
chk("H1b sin Shopify configurado la API de tienda avisa 503", st == 503, f"status={st}")
st, h, u = get(an, "/admin")
chk("H2 un anonimo no ve el panel", "/login" in str(u), str(u))

# ---------------------------------------------------------------- W (PWA)
# Lo instalable en el telefono. Lo que se prueba no es que Android lo acepte
# —eso no se puede desde aca— sino lo que de verdad se rompe al instalar la
# plantilla para otro cliente: que el manifest salga con SU nombre y no con
# el de la plantilla, y que los iconos que declara existan.
st, h, u = get(an, "/manifest.webmanifest")
try:
    manifiesto = json.loads(h)
except ValueError:
    manifiesto = None
chk("W1 el manifest responde y es JSON valido", st == 200 and manifiesto is not None,
    f"status={st}")
chk("W1b y lleva el nombre del negocio, no el de la plantilla",
    bool(manifiesto) and manifiesto.get("name") == NEGOCIO["nombre"],
    str(manifiesto.get("name") if manifiesto else None))

# Un icono declarado que da 404 deja la app instalada con el icono generico
# del navegador, y no se nota hasta que alguien la instala.
declarados = [i["src"] for i in (manifiesto or {}).get("icons", [])]
declarados.append("/static/img/pwa/apple-touch-icon.png")
faltan = [s for s in declarados if get(an, s)[0] != 200]
chk("W2 todos los iconos que declara existen", not faltan, ", ".join(faltan))

st, h, u = get(an, "/")
chk("W3 la portada enlaza el manifest y el icono de iOS",
    'rel="manifest"' in h and "apple-touch-icon" in h, "")

# ---------------------------------------------------------------- T (Shopify: webhook)
# El webhook que registra en /admin/pedidos lo que Shopify avisa que se
# pago. Lo que importa no es el CRUD sino que nadie pueda inventar un
# pedido golpeando el endpoint, y que un aviso repetido -Shopify reintenta
# si no contesta a tiempo- no duplique la fila.
if not sql("SHOW TABLES LIKE 'pedidos_shopify'"):
    print("\n  Falta la tabla `pedidos_shopify`. Cargala y vuelve a correr la suite:")
    print('      mysql -u root -p --default-character-set=utf8mb4 '
          '-e "source schema/pedidos_shopify.sql"\n')
    sys.exit(2)
if not sql("SHOW COLUMNS FROM pedidos_shopify LIKE 'estado'"):
    print("\n  Falta pedidos_shopify_detalle.sql (columnas nombre_comprador/estado).")
    print("  Cargala y vuelve a correr la suite:")
    print('      mysql -u root -p --default-character-set=utf8mb4 '
          '-e "source schema/pedidos_shopify_detalle.sql"\n')
    sys.exit(2)

import base64, hashlib, hmac as _hmac

IDS_PRUEBA_SHOPIFY = (999990001, 999990002)
sql("DELETE FROM pedidos_shopify WHERE shopify_order_id IN (%s, %s)", *IDS_PRUEBA_SHOPIFY)


def _pedido_shopify_falso(oid):
    return {
        "id": oid,
        "name": f"#{oid}",
        "email": "prueba-webhook@example.com",
        "customer": {"first_name": "Prueba", "last_name": "Webhook"},
        "total_price": "3500.00",
        "currency": "CLP",
        "created_at": "2026-01-01T10:00:00-04:00",
        "line_items": [{"title": "Cafe de prueba", "quantity": 1, "price": "3500.00"}],
    }


def _post_webhook_shopify(ruta, cuerpo_bytes, firma):
    req = urllib.request.Request(
        B + ruta, data=cuerpo_bytes, method="POST",
        headers={"Content-Type": "application/json", "X-Shopify-Hmac-Sha256": firma})
    try:
        r = nueva().open(req)
        return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


# Una firma que no calza con nada, sea cual sea el secreto configurado del
# lado de la app -incluido el caso de que no haya ninguno configurado.
cuerpo_malo = json.dumps(_pedido_shopify_falso(IDS_PRUEBA_SHOPIFY[0])).encode("utf-8")
st, h = _post_webhook_shopify("/webhooks/shopify/orders-paid", cuerpo_malo,
                              "firma-que-no-calza-con-nada==")
chk("T1 una firma invalida se rechaza con 401 y no guarda nada",
    st == 401 and not sql("SELECT id FROM pedidos_shopify WHERE shopify_order_id=%s",
                          IDS_PRUEBA_SHOPIFY[0]),
    f"status={st}")

SECRETO_WEBHOOK_PRUEBA = os.environ.get("SHOPIFY_WEBHOOK_SECRET", "").strip()
if not SECRETO_WEBHOOK_PRUEBA:
    print("\n  SHOPIFY_WEBHOOK_SECRET no esta configurado en este .env: T2 a T6 se")
    print("  omiten -no se puede firmar un aviso de verdad sin el secreto que usa la")
    print("  app en marcha. El resto de la suite sigue igual.\n")
else:
    def _firmar_webhook_prueba(cuerpo_bytes):
        firma = _hmac.new(SECRETO_WEBHOOK_PRUEBA.encode("utf-8"), cuerpo_bytes,
                          hashlib.sha256).digest()
        return base64.b64encode(firma).decode("utf-8")

    cuerpo = json.dumps(_pedido_shopify_falso(IDS_PRUEBA_SHOPIFY[1])).encode("utf-8")
    st, h = _post_webhook_shopify("/webhooks/shopify/orders-paid", cuerpo,
                                  _firmar_webhook_prueba(cuerpo))
    fila = sql("SELECT id, nombre_comprador, estado FROM pedidos_shopify WHERE shopify_order_id=%s",
              IDS_PRUEBA_SHOPIFY[1])
    chk("T2 un aviso bien firmado se acepta y el pedido queda guardado",
        st == 200 and bool(fila), f"status={st}")
    chk("T2b y guarda el nombre del comprador, no solo el correo",
        bool(fila) and fila[0]["nombre_comprador"] == "Prueba Webhook",
        str(fila[0]["nombre_comprador"] if fila else None))
    chk("T2c y arranca en estado 'pagado'",
        bool(fila) and fila[0]["estado"] == "pagado",
        str(fila[0]["estado"] if fila else None))

    # El mismo aviso otra vez -Shopify reintenta si no responde a tiempo- no
    # puede dejar dos filas del mismo pedido.
    st2, h2 = _post_webhook_shopify("/webhooks/shopify/orders-paid", cuerpo,
                                    _firmar_webhook_prueba(cuerpo))
    fila2 = sql("SELECT id FROM pedidos_shopify WHERE shopify_order_id=%s", IDS_PRUEBA_SHOPIFY[1])
    chk("T3 el mismo pedido entregado dos veces no se duplica",
        st2 == 200 and len(fila2) == 1, f"filas={len(fila2)}")

    op6, _, _ = login(ADMIN_EMAIL, ADMIN_CLAVE)
    st6, h6, _ = get(op6, "/admin/pedidos")
    chk("T4 el pedido de prueba aparece en /admin/pedidos",
        st6 == 200 and "Prueba Webhook" in h6, f"status={st6}")

    # orders/updated: un reembolso posterior tiene que marcar el pedido que
    # ya existia, sin inventar uno nuevo.
    orden_actualizada = _pedido_shopify_falso(IDS_PRUEBA_SHOPIFY[1])
    orden_actualizada["financial_status"] = "refunded"
    cuerpo_act = json.dumps(orden_actualizada).encode("utf-8")
    st5, h5 = _post_webhook_shopify("/webhooks/shopify/orders-updated", cuerpo_act,
                                    _firmar_webhook_prueba(cuerpo_act))
    fila5 = sql("SELECT estado FROM pedidos_shopify WHERE shopify_order_id=%s",
               IDS_PRUEBA_SHOPIFY[1])
    chk("T5 orders/updated marca como reembolsado un pedido que ya existia",
        st5 == 200 and bool(fila5) and fila5[0]["estado"] == "reembolsado",
        str(fila5[0]["estado"] if fila5 else None))

    # Una actualizacion de una orden que nunca paso por orders/paid no
    # inventa una fila.
    orden_fantasma = _pedido_shopify_falso(999990099)
    orden_fantasma["financial_status"] = "refunded"
    cuerpo_fantasma = json.dumps(orden_fantasma).encode("utf-8")
    st6, h6b = _post_webhook_shopify("/webhooks/shopify/orders-updated", cuerpo_fantasma,
                                     _firmar_webhook_prueba(cuerpo_fantasma))
    chk("T6 orders/updated de un pedido desconocido no crea una fila",
        st6 == 200 and not sql("SELECT id FROM pedidos_shopify WHERE shopify_order_id=999990099"),
        f"status={st6}")

    # El corte por periodo: los cuatro tienen que responder y marcar su
    # propia pastilla como la activa.
    ok_periodos, detalle = True, []
    for periodo in ("dia", "semana", "mes", "anio"):
        stp, hp, _ = get(op6, f"/admin/pedidos?periodo={periodo}")
        marcado = f'?periodo={periodo}" aria-current="page"' in hp.replace("\n", " ")
        if stp != 200 or "pedidos__tab" not in hp:
            ok_periodos = False
            detalle.append(f"{periodo}:status={stp}")
    chk("T7 el panel responde en los cuatro cortes (dia/semana/mes/anio)",
        ok_periodos, ",".join(detalle))

    # Un periodo inventado no puede reventar: es un parametro de la URL que
    # cualquiera escribe a mano.
    st8, h8, _ = get(op6, "/admin/pedidos?periodo=quincena")
    chk("T8 un periodo que no existe cae en el de por defecto y no revienta",
        st8 == 200 and "pedidos__tab" in h8, f"status={st8}")

sql("DELETE FROM pedidos_shopify WHERE shopify_order_id IN (%s, %s, 999990099)",
    *IDS_PRUEBA_SHOPIFY)

st, h, u = get(nueva(), "/admin/pedidos")
chk("T9 un anonimo no entra a los pedidos del panel", "/login" in str(u), str(u))

# ---------------------------------------------------------------- X (tienda de tatuaje)
# Lo que cambia respecto de la plantilla de cafeteria: lo agotado se ve en el
# catalogo, sin Shopify no hay tienda ni carrito, el personal atiende la cola
# de pedidos y la base se instala sola sin borrar nada.
MARCA_X = sql("SELECT slug FROM marcas WHERE id = (SELECT MIN(id) FROM marcas)")[0]["slug"]
_mx = sql("SELECT id FROM marcas WHERE slug=%s", MARCA_X)[0]["id"]
_cx = sql("SELECT id FROM categorias WHERE marca_id=%s ORDER BY orden LIMIT 1", _mx)[0]["id"]
sql("DELETE FROM productos WHERE slug='prueba-agotado-x'")
sql("""INSERT INTO productos (marca_id, categoria_id, slug, nombre, precio_clp, disponible, orden)
       VALUES (%s, %s, 'prueba-agotado-x', 'Prueba agotado X', 1000, 0, 99)""", _mx, _cx)
st, h, _ = get(nueva(), f"/api/v1/menu?marca={MARCA_X}")
try:
    _ag = [i for sec in json.loads(h) for i in sec["items"] if i["name"] == "Prueba agotado X"]
except ValueError:
    _ag = []
chk("X1 un producto agotado sigue en el catalogo, marcado como agotado",
    bool(_ag) and _ag[0].get("agotado") is True, str(_ag))
sql("DELETE FROM productos WHERE slug='prueba-agotado-x'")

if not os.environ.get("SHOPIFY_DOMINIO"):
    st, h, _ = get(nueva(), "/")
    chk("X2 sin Shopify no hay seccion de tienda online ni boton de carrito",
        'id="tienda"' not in h and "data-lp-carrito-abrir" not in h, f"status={st}")

X_EMAIL, X_CLAVE = "vendedor-x@x.cl", "Clave-Vendedor-123"
sql("DELETE FROM usuarios WHERE email=%s", X_EMAIL)
sql("""INSERT INTO usuarios (nombre, email, password_hash, rol, estado, nickname, email_verificado_at)
       VALUES ('Vendedor', %s, %s, 'barista', 'activo', 'vendedorx', UTC_TIMESTAMP())""",
    X_EMAIL, _hashear(X_CLAVE))
op_x, _, _ = login(X_EMAIL, X_CLAVE)
st, h, _ = get(op_x, "/admin/barra")
chk("X3 el personal del meson entra a la cola de pedidos, pero no a su configuracion",
    st == 200 and 'id="config"' not in h, f"status={st}")
sql("DELETE FROM usuarios WHERE email=%s", X_EMAIL)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import instalar_base as _ib
_antes = sql("SELECT COUNT(*) AS n FROM productos")[0]["n"]
try:
    _ib.instalar(ejemplos=False, decir=lambda *_: None)
    _ib.instalar(ejemplos=False, decir=lambda *_: None)
    _ok = True
except Exception as e:      # noqa: BLE001
    _ok = str(e)
chk("X4 instalar la base dos veces seguidas no falla ni borra nada",
    _ok is True and sql("SELECT COUNT(*) AS n FROM productos")[0]["n"] == _antes, str(_ok))

for m in R:
    print(m[0], m[1], ("  [" + m[2] + "]") if m[2] else "")
print("\nfallan:", sum(1 for m in R if m[0] == "XX "), "de", len(R))
sys.exit(1 if any(m[0] == "XX " for m in R) else 0)
