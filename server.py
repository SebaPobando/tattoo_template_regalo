import os

from flask_app import app
from flask_app.controllers import main_controller   # noqa: F401  (registra las rutas)
from flask_app.controllers import admin_controller  # noqa: F401
from flask_app.controllers import actividad_controller  # noqa: F401
from flask_app.controllers import muro_controller  # noqa: F401
from flask_app.controllers import usuarios_controller  # noqa: F401
from flask_app.controllers import tienda_controller  # noqa: F401
from flask_app.controllers import promo_controller  # noqa: F401
from flask_app.controllers import barra_controller  # noqa: F401
from flask_app.controllers import ruleta_controller  # noqa: F401
from flask_app.controllers import vale_controller  # noqa: F401

# La base se arma (o se pone al día) sola al arrancar: así, en Railway, no hay
# que abrir ninguna consola para crear las tablas. Es seguro correrlo cada
# vez: instalar_base.py nunca borra nada, solo crea lo que falta.
#
# Si MySQL no responde, el sitio arranca igual (y lo dice en el log): las
# páginas que no necesitan la base siguen funcionando, y al reiniciar con la
# base arriba se completa solo. Para apagarlo: INSTALAR_AL_ARRANCAR=no.
if os.environ.get("INSTALAR_AL_ARRANCAR", "si").lower() not in ("no", "0", "false"):
    try:
        import instalar_base
        _lineas = []
        instalar_base.instalar(
            ejemplos=os.environ.get("CARGAR_EJEMPLOS", "").lower() in ("si", "sí", "1", "true"),
            decir=_lineas.append, ejemplos_solo_si_vacia=True)
        app.logger.warning("Base de datos al día. %s",
                           " | ".join(l for l in _lineas if not l.strip().startswith("ok")))
    except Exception as e:      # noqa: BLE001
        app.logger.error("No se pudo preparar la base de datos al arrancar: %s", e)

if __name__ == "__main__":
    # Esto corre SOLO cuando ejecutas `python server.py` en tu máquina. En
    # Railway arranca gunicorn (ver Procfile) y este bloque no se ejecuta.
    #
    # Aun así el debug se apaga con FLASK_ENV=production, por si algún día el
    # servidor lo levanta así: el depurador de Werkzeug deja ejecutar código
    # Python desde el navegador en cualquier página que reviente. En local es
    # comodísimo; abierto a internet es entregar el servidor.
    en_produccion = os.environ.get("FLASK_ENV") == "production"
    app.run(debug=not en_produccion,
            host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", 5000)))
