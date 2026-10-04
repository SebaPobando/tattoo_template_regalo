# ==========================================
# __init__.py — inicializa la aplicación Flask
# ==========================================
import os

from flask import Flask

# Carga el archivo .env antes de leer cualquier variable. Sin esto, todo lo que
# pongas en .env se ignora en silencio y la app usa los valores por defecto.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # si aún no instalaste requirements.txt
    pass

app = Flask(__name__)

# La clave de sesión sale del entorno. Si queda escrita en el código, cualquiera
# con acceso al repo puede firmar cookies de sesión y entrar como quien quiera.
#
# EN PRODUCCIÓN, SIN CLAVE PROPIA LA APP NO ARRANCA (auditoría 2026-09-16).
# Antes había un valor por defecto y listo: si te olvidabas de poner
# SECRET_KEY en el panel del servidor, el sitio levantaba igual, firmando las
# sesiones con una clave que está escrita en este archivo y publicada en el
# repositorio. Con esa clave cualquiera se fabrica una cookie de administrador
# —no hay que adivinar ninguna contraseña— y nada en pantalla delata que pasó.
#
# Un fallo ruidoso al arrancar es mucho más barato que ese silencio. En local
# sigue habiendo valor por defecto: ahí la comodidad gana y no hay nada que
# robar.
CLAVE_DE_MENTIRA = "dev-solo-para-local-cambiar-en-produccion"
_clave = os.environ.get("SECRET_KEY") or ""

if os.environ.get("FLASK_ENV") == "production" and (
        not _clave or _clave == CLAVE_DE_MENTIRA or len(_clave) < 32):
    raise RuntimeError(
        "Falta SECRET_KEY, o es la de ejemplo, o es muy corta. En producción "
        "firma las sesiones y los enlaces de correo: con una clave conocida "
        "cualquiera se fabrica una sesión de administrador. Genera una con:  "
        'python -c "import secrets; print(secrets.token_urlsafe(48))"  y '
        "guárdala en las variables del servicio."
    )

app.secret_key = _clave or CLAVE_DE_MENTIRA

# --- Detrás del proxy de Railway (o de cualquier PaaS) ----------------------
# Railway termina el HTTPS en su borde y le habla a la app por HTTP interno.
# Sin esto Flask cree que la petición fue http, y `url_for(..., _external=True)`
# —el enlace del voucher que va al correo y al WhatsApp— sale con http://.
# Funciona igual porque Railway redirige, pero es un salto de más y se ve mal
# pegado en un mensaje.
#
# Va detrás de una variable y NO siempre encendido a propósito: ProxyFix le
# CREE a las cabeceras X-Forwarded-*, y eso solo es seguro cuando de verdad
# hay un proxy adelante que las reescribe. En un servidor expuesto sin proxy,
# cualquiera podría mandarlas y hacerse pasar por otra IP.
if os.environ.get("DETRAS_DE_PROXY") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Cookie de sesión endurecida (ver Fase 2 del roadmap).
#
# CUÁNTO DURA LA SESIÓN. Con «Recordarme» marcado (viene marcado), 30 días
# desde la ÚLTIMA visita: Flask renueva la fecha en cada página
# (SESSION_REFRESH_EACH_REQUEST, encendido por defecto), así que quien usa el
# sitio seguido no vuelve a escribir su clave nunca. Sin «Recordarme», la
# sesión muere al cerrar el navegador, para un computador compartido.
#
# Una sesión larga no es una sesión sin control: cada página protegida
# relee la cuenta de la base (_sesion_vigente), así que bloquear a alguien
# o quitarle el rol sigue surtiendo efecto al tiro, aunque su cookie dure
# un mes. Y «Salir» la borra.
from datetime import timedelta

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

# Flask ordena alfabéticamente las claves de todo lo que serializa a JSON, y
# eso NO es inocuo acá: el catálogo de la tienda llega de Shopify con los
# tamaños en el orden en que están definidos en el producto («250 g», «1 kg»,
# de más chico a más grande) y ordenarlos alfabéticamente los deja como
# «1 kg», «250 g». El sitio terminaba ofreciendo el kilo por defecto.
#
# Vale para todo lo demás igual: el orden que eligió quien escribió los datos
# suele querer decir algo, y ordenarlo solo lo borra.
app.json.sort_keys = False

# Y esto NO es lo mismo ni sobra: el filtro |tojson de las plantillas no usa
# la configuración de arriba, usa una política propia de Jinja que trae
# sort_keys=True y pisa la del proveedor. Sin esta línea, jsonify devuelve el
# orden bueno y el mismo dato inyectado en el HTML sale ordenado alfabético.
app.jinja_env.policies["json.dumps_kwargs"] = {"sort_keys": False}

# Base de datos que usan los modelos.
from flask_app.config.mysqlconnection import datos_conexion  # noqa: E402
DB = datos_conexion()["db"]

# Hoy esta app sirve TODO en un solo origen (localhost:5000): la landing, la
# ficha de producto y el área de cuenta. Las plantillas enlazan con url_for.
#
# Cuando la landing vuelva a GitHub Pages, se cambia el cuerpo de la ruta "/"
# en main_controller.py por un redirect a esta variable. Mientras tanto queda
# apuntando a la raíz local.
SITIO_PUBLICO = os.environ.get("SITIO_PUBLICO", "/")


@app.after_request
def cabeceras_de_seguridad(respuesta):
    """
    Tres cabeceras que el navegador respeta y que no cuestan nada
    (auditoría 2026-09-16). No son un antivirus: cierran tres puertas
    conocidas.

      nosniff        — el navegador no adivina el tipo de un archivo. Sin
                       esto, algo subido como .txt puede terminar
                       ejecutándose como JavaScript.
      SAMEORIGIN     — nadie puede meter el panel de admin dentro de un
                       <iframe> en su sitio y engañar a quien hace clic
                       (clickjacking). SAMEORIGIN y no DENY para no romper
                       vistas previas del propio sitio.
      Referrer-Policy— al salir a otro sitio no se le regala la URL completa
                       de dónde venías. Importa en los enlaces del voucher,
                       que llevan el código en la dirección.

    Lo que NO hay acá es Content-Security-Policy, y es a propósito: las
    plantillas todavía traen estilos y scripts en línea, así que una CSP
    estricta rompería el sitio. Va cuando ese CSS salga a sus archivos.
    """
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    respuesta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return respuesta


@app.context_processor
def inyectar_globales():
    """Disponibles en todas las plantillas sin pasarlas en cada render."""
    from flask import session
    from flask_app.config import csrf, temporadas
    from flask_app.config.negocio import NEGOCIO, en_puntos
    from flask_app.models.barra_model import barra_activa
    return {
        # TODO lo que cambia de un cliente a otro entra por acá: nombre,
        # colores, contacto, puntos, segunda marca. Ninguna plantilla sabe
        # cómo se llama el negocio; se lo pregunta a esto.
        # Ver flask_app/config/negocio.py — ES el archivo que se edita al
        # instalar la plantilla para alguien nuevo.
        "negocio": NEGOCIO,
        "en_puntos": en_puntos,
        "sitio_publico": SITIO_PUBLICO,
        "usuario": session.get("usuario"),
        # Se pasa la FUNCIÓN, no el token. csrf.token() crea la sesión la
        # primera vez que se llama, y si lo evaluáramos acá le estaríamos
        # poniendo una cookie a todo el que abre la portada sin necesidad.
        # Así solo se crea en las plantillas que de verdad lo escriben.
        #
        # Nombre distinto a csrf_token a propósito: las vistas que ya pasan
        # csrf_token=csrf.token() como string siguen funcionando igual.
        "csrf_actual": csrf.token,
        # {{ mascota('archivo.png', 'lugar') }}: la mascota de hoy, que en
        # temporada (Halloween...) cambia sola. Ver config/temporadas.py.
        "mascota": temporadas.mascota,
        "temporada": temporadas.actual,
        # ¿Se están tomando pedidos para retiro? Se pasa la FUNCIÓN por lo
        # mismo que csrf_actual: solo la llaman las plantillas que muestran
        # el enlace, y la respuesta va cacheada un minuto (ver barra_model).
        "barra_activa": barra_activa,
    }
