# ==========================================================================
# usuarios_controller.py — el lado ADMIN de las cuentas
#
# Acá vive solo /admin/usuarios. El login, el registro, la recuperación de
# contraseña y el perfil siguen en main_controller: eso es lo que hace cada
# persona con su propia cuenta, y esto es lo que hace el admin con las de
# los demás.
#
# Qué se puede hacer hoy: mirar quién hay, bloquear o desbloquear, hacer
# barista a una cuenta (o devolverla a cliente), y CREAR la cuenta de un
# barista nuevo. El barista entra a lo que se usa en la barra —vales y
# ruleta— y a nada más.
#
# Crear un barista no le inventa una contraseña: la cuenta nace sin clave y
# el admin le manda un enlace (por WhatsApp, y además le llega por correo)
# para que la elija él. Así el admin nunca conoce la contraseña de nadie, y
# no hay claves «temporales» dando vueltas en un chat.
#
# Qué NO se puede, y es a propósito:
#
#   - Borrar. La columna `deleted_at` está lista para el borrado lógico,
#     pero borrar de verdad se lleva por delante los mensajes del muro (la
#     llave va con ON DELETE CASCADE), lo impiden las inscripciones a
#     actividades, y cuando exista el ledger, borrar una cuenta con saldo
#     prepago es destruir un pasivo contable: plata que esa persona pagó.
#     Bloquear cubre lo que hace falta hoy.
#
#   - Dar o quitar el rol de admin. Solo cliente ↔ barista. Así el panel
#     no puede dejar el sistema sin administradores, ni crear uno nuevo.
# ==========================================================================

from urllib.parse import quote

from flask import (abort, flash, redirect, render_template, request, session,
                   url_for)

from flask_app import app
from flask_app.config import csrf, tiempo
from flask_app.controllers.actividad_controller import _telefono, _whatsapp
from flask_app.controllers.main_controller import (enlace_invitacion,
                                                   enviar_invitacion,
                                                   requiere_admin)
from flask_app.config.enlaces import HORAS_INVITACION
from flask_app.config.negocio import NEGOCIO
from flask_app.models.usuario_model import Usuario, normalizar_email

ROLES = ("cliente", "barista", "admin")
ESTADOS = ("invitado", "activo", "bloqueado")


# ------------------------------------------------------------------ ayudas

def _protegido_csrf():
    if not csrf.valido(request.form.get("csrf")):
        abort(400, "Token de seguridad inválido. Recarga la página.")


def _filtro(nombre, validos):
    """Un filtro de la URL solo si es uno de los valores que existen."""
    valor = request.args.get(nombre)
    return valor if valor in validos else None


def _vista(fila):
    d = dict(fila)
    d["desde"] = tiempo.fecha(d["created_at"])
    d["verificado"] = bool(d["email_verificado_at"])
    # Cómo llamarla en pantalla, con el mismo criterio que para_sesion.
    d["etiqueta"] = (d.get("nickname") or "").strip() \
        or " ".join(p for p in [d.get("nombre"), d.get("apellido")] if p).strip() \
        or d["email"].split("@")[0]
    # Un admin no se puede tocar desde acá, y uno mismo tampoco.
    d["intocable"] = d["rol"] == "admin"
    # Un barista creado desde el panel que todavía no elige su contraseña.
    d["invitacion_pendiente"] = (d["rol"] == "barista" and d["estado"] == "invitado")
    return d


def _objetivo(usuario_id):
    """
    Resuelve el id a una cuenta que este panel pueda tocar.

    404 si no existe. Si es un admin, 400 con un mensaje claro: no es un
    error del sistema, es una regla — y la más importante de este archivo,
    porque es la que impide quedarse afuera del propio panel un domingo.
    """
    fila = Usuario.por_id(usuario_id)
    if not fila:
        abort(404)
    if fila["rol"] == "admin":
        abort(400, "Las cuentas de administrador no se bloquean desde acá.")
    return fila


# ------------------------------------------------------------------ vistas

@app.route("/admin/usuarios")
@requiere_admin
def admin_usuarios():
    busca = (request.args.get("busca") or "").strip()
    rol = _filtro("rol", ROLES)
    estado = _filtro("estado", ESTADOS)

    filas = Usuario.listar_para_admin(busca=busca or None, rol=rol, estado=estado)

    # La invitación recién creada (o pedida de nuevo): ?invitado=<id>. El
    # enlace se genera al mostrarlo y no se guarda en ningún lado.
    invitacion = None
    try:
        invitado_id = int(request.args.get("invitado") or 0)
    except ValueError:
        invitado_id = 0
    if invitado_id:
        fila = Usuario.por_id(invitado_id)
        if fila and fila["rol"] == "barista" and fila["estado"] == "invitado":
            enlace = enlace_invitacion(fila)
            texto = (f"Hola {fila['nombre'] or ''}, te creé tu cuenta del equipo en "
                     f"{NEGOCIO['nombre']}. Entra a este enlace para elegir tu "
                     f"contraseña (vence en {HORAS_INVITACION} horas): {enlace}")
            invitacion = {
                "nombre": fila["nombre"] or fila["email"], "email": fila["email"],
                "enlace": enlace, "horas": HORAS_INVITACION,
                "wsp": (_whatsapp(fila["telefono"], texto) if fila["telefono"]
                        else f"https://wa.me/?text={quote(texto)}"),
                "correo_enviado": request.args.get("correo") == "1",
            }

    return render_template(
        "admin_usuarios.html",
        invitacion=invitacion,
        usuarios=[_vista(u) for u in filas],
        busca=busca,
        rol=rol,
        estado=estado,
        # Si el listado llega justo al tope, puede haber más que no se ven.
        # Decirlo es mejor que mostrar un listado incompleto en silencio.
        topado=len(filas) >= Usuario.TOPE_LISTADO,
        tope=Usuario.TOPE_LISTADO,
        conteo=Usuario.resumen(),
        csrf_token=csrf.token(),
    )


@app.route("/admin/usuarios/<int:usuario_id>/bloquear", methods=["POST"])
@requiere_admin
def admin_usuarios_bloquear(usuario_id):
    _protegido_csrf()

    # Cinturón además del tirante: _objetivo ya rechaza a los admins, y el
    # UPDATE del modelo también. Esta comprobación existe para el día en que
    # alguien se pueda bloquear a sí mismo sin ser admin.
    if usuario_id == session["usuario"]["id"]:
        abort(400, "No puedes bloquear tu propia cuenta.")

    objetivo = _objetivo(usuario_id)
    if Usuario.bloquear(usuario_id):
        flash(f"{objetivo['email']} quedó bloqueada. No podrá entrar ni "
              "escribir en el muro.", "info")
    else:
        flash("Esa cuenta ya estaba bloqueada.", "info")
    return redirect(_volver())


@app.route("/admin/usuarios/<int:usuario_id>/desbloquear", methods=["POST"])
@requiere_admin
def admin_usuarios_desbloquear(usuario_id):
    _protegido_csrf()
    objetivo = _objetivo(usuario_id)
    if Usuario.desbloquear(usuario_id):
        flash(f"{objetivo['email']} vuelve a tener acceso.", "info")
    else:
        flash("Esa cuenta no estaba bloqueada.", "info")
    return redirect(_volver())


@app.route("/admin/usuarios/<int:usuario_id>/rol", methods=["POST"])
@requiere_admin
def admin_usuarios_rol(usuario_id):
    _protegido_csrf()
    rol = request.form.get("nuevo_rol")
    if rol not in ("cliente", "barista"):
        abort(400)
    objetivo = _objetivo(usuario_id)
    if Usuario.cambiar_rol_personal(usuario_id, rol):
        flash(f"{objetivo['email']} ahora es vendedor(a): entra al panel del mesón "
              "(vales, ruleta y pedidos) con su misma cuenta." if rol == "barista"
              else f"{objetivo['email']} vuelve a ser cliente.", "info")
    else:
        flash("No se pudo cambiar el rol: solo cuentas activas, y nunca la de "
              "un administrador.", "error")
    return redirect(_volver())


@app.route("/admin/usuarios/crear-barista", methods=["POST"])
@requiere_admin
def admin_usuarios_crear_barista():
    _protegido_csrf()
    volver = redirect(url_for("admin_usuarios") + "#crear")
    nombre = " ".join((request.form.get("nombre") or "").split())[:45]
    apellido = " ".join((request.form.get("apellido") or "").split())[:45] or None
    email = normalizar_email(request.form.get("email"))
    if not nombre:
        flash("Escribe el nombre de la persona.", "error")
        return volver
    if "@" not in email or "." not in email.split("@")[-1]:
        flash("Ese correo no parece válido.", "error")
        return volver

    telefono = None
    if (request.form.get("telefono") or "").strip():
        telefono, error = _telefono(request.form.get("telefono"))
        if error:
            flash(error.replace("por ahí te mandamos el voucher", "para mandarle el enlace"), "error")
            return volver

    existente = Usuario.por_email(email)
    if existente:
        # No se pisa nada: si ya tiene cuenta, se busca y se hace barista
        # con el botón de su fila (o se ve por qué no se puede).
        if existente["rol"] == "barista":
            flash(f"{email} ya es vendedor(a).", "info")
        elif existente["rol"] == "admin":
            flash(f"{email} es una cuenta de administrador.", "error")
        else:
            flash(f"{email} ya tiene cuenta en el sitio. Búscala abajo y toca "
                  "«Hacer vendedor(a)».", "info")
        return redirect(url_for("admin_usuarios", busca=email))

    # Nace sin contraseña y como 'invitado': así funcionan todas las reglas
    # que ya existen. Al crear su clave desde el enlace pasa a 'activo' (ver
    # Usuario.restablecer_password). Y como su rol no es 'cliente', nadie
    # puede «reclamarla» registrándose con su correo: la regla C1.
    Usuario.crear(email, password_hash=None, nombre=nombre, apellido=apellido,
                  rol="barista", estado="invitado", telefono=telefono)
    fila = Usuario.por_email(email)
    enviado = enviar_invitacion(fila, enlace_invitacion(fila))
    flash(f"Cuenta de vendedor(a) creada para {nombre}.", "success")
    return redirect(url_for("admin_usuarios", invitado=fila["id"],
                            correo="1" if enviado else None) + "#invitacion")


def _volver():
    """
    Vuelve al listado con la misma búsqueda y los mismos filtros.

    Se rearma desde campos ocultos del formulario y NUNCA desde una URL
    entera: aceptar una URL del formulario sería un redirect abierto.
    """
    return url_for("admin_usuarios",
                   busca=(request.form.get("busca") or "").strip() or None,
                   rol=request.form.get("rol") if request.form.get("rol") in ROLES else None,
                   estado=request.form.get("estado") if request.form.get("estado") in ESTADOS else None)
