"""Administración de usuarios (solo administradores)."""
from database.conexion import consultar, consultar_uno, transaccion
from logica import licencia
from logica.seguridad import (ROL_ADMIN, ROL_CAJERO, ErrorValidacion, Sesion, auditar,
                              hash_password, requiere_rol, validar_password, validar_username)


@requiere_rol(ROL_ADMIN)
def listar_usuarios():
    return consultar(
        """SELECT u.id_usuario, u.username, u.nombre_completo, u.id_rol, r.nombre AS rol,
                  u.activo, u.ultimo_acceso FROM usuarios u JOIN roles r ON r.id_rol = u.id_rol
           ORDER BY u.activo DESC, u.username"""
    )


@requiere_rol(ROL_ADMIN)
def crear_usuario(username, nombre, password, confirmacion):
    username, nombre = username.strip(), nombre.strip()
    validar_username(username)
    if not nombre:
        raise ErrorValidacion("El nombre completo es obligatorio.")
    id_rol = ROL_CAJERO
    validar_password(password, confirmacion)
    if consultar_uno("SELECT 1 AS x FROM usuarios WHERE username = ?", (username,)):
        raise ErrorValidacion("Ese nombre de usuario ya existe.")
    with transaccion() as con:
        max_caj = licencia.max_cajeros_permitidos()
        if max_caj is not None:
            actuales = con.execute(
                "SELECT COUNT(*) FROM usuarios WHERE id_rol = ? AND activo = 1",
                (ROL_CAJERO,),
            ).fetchone()[0]
            if actuales >= max_caj:
                raise ErrorValidacion(
                    f"El Plan Básico permite máximo {max_caj} usuario cajero activo (aparte del Administrador). "
                    "Actualiza al Plan Standard o Plan Ultra para registrar cajeros ilimitados."
                )
        con.execute(
            "INSERT INTO usuarios (username, nombre_completo, password_hash, id_rol) VALUES (?,?,?,?)",
            (username, nombre, hash_password(password), id_rol),
        )
        auditar("CREAR_USUARIO", f"{username} (rol {id_rol})", con)


def _admins_activos(con, excluir=None):
    return con.execute(
        "SELECT COUNT(*) FROM usuarios WHERE id_rol=? AND activo=1 AND id_usuario<>?",
        (ROL_ADMIN, excluir or -1),
    ).fetchone()[0]


@requiere_rol(ROL_ADMIN)
def actualizar_usuario(id_usuario, nombre, activo):
    nombre = nombre.strip()
    if not nombre:
        raise ErrorValidacion("El nombre completo es obligatorio.")
    with transaccion() as con:
        u = con.execute("SELECT id_rol FROM usuarios WHERE id_usuario=?", (id_usuario,)).fetchone()
        if not u:
            raise ErrorValidacion("El usuario no existe.")
        id_rol = u["id_rol"]
        
        if id_usuario == Sesion.id() and (not activo or id_rol != ROL_ADMIN):
            raise ErrorValidacion("No puedes desactivarte a ti mismo.")
            
        if id_rol == ROL_ADMIN and not activo and _admins_activos(con, id_usuario) == 0:
            raise ErrorValidacion("Debe existir al menos un administrador activo.")
        if id_rol == ROL_CAJERO and activo:
            max_caj = licencia.max_cajeros_permitidos()
            if max_caj is not None:
                otros_cajeros = con.execute(
                    "SELECT COUNT(*) FROM usuarios WHERE id_rol = ? AND activo = 1 AND id_usuario <> ?",
                    (ROL_CAJERO, id_usuario),
                ).fetchone()[0]
                if otros_cajeros >= max_caj:
                    raise ErrorValidacion(
                        f"El Plan Básico permite máximo {max_caj} usuario cajero activo (aparte del Administrador). "
                        "Actualiza al Plan Standard o Plan Ultra para tener múltiples cajeros activos."
                    )
        con.execute("UPDATE usuarios SET nombre_completo=?, activo=? WHERE id_usuario=?",
                    (nombre, int(activo), id_usuario))
        auditar("EDITAR_USUARIO", f"id={id_usuario} activo={activo}", con)


@requiere_rol(ROL_ADMIN)
def restablecer_password(id_usuario, password, confirmacion):
    validar_password(password, confirmacion)
    with transaccion() as con:
        con.execute(
            "UPDATE usuarios SET password_hash=?, intentos_fallidos=0, bloqueado_hasta=NULL WHERE id_usuario=?",
            (hash_password(password), id_usuario),
        )
        auditar("RESTABLECER_CLAVE", f"id={id_usuario}", con)


@requiere_rol()
def cambiar_mi_password(actual, nueva, confirmacion):
    from logica.seguridad import verificar_password
    fila = consultar_uno("SELECT password_hash FROM usuarios WHERE id_usuario=?", (Sesion.id(),))
    if not fila or not verificar_password(actual, fila["password_hash"]):
        auditar("CAMBIO_CLAVE_FALLIDO", "")
        raise ErrorValidacion("La contraseña actual no es correcta.")
    validar_password(nueva, confirmacion)
    with transaccion() as con:
        con.execute("UPDATE usuarios SET password_hash=? WHERE id_usuario=?", (hash_password(nueva), Sesion.id()))
        auditar("CAMBIAR_MI_CLAVE", "", con)
