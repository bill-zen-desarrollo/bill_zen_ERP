"""Autenticación: primer administrador, inicio de sesión, preguntas de seguridad y recuperación de clave."""
import re
import unicodedata
from datetime import datetime, timedelta

from database.conexion import consultar, consultar_uno, transaccion
from logica.seguridad import (ROL_ADMIN, ErrorPermiso, ErrorValidacion, Sesion, auditar,
                              hash_password, validar_password, validar_username,
                              verificar_password, verificar_password_ficticio)

MAX_INTENTOS = 5
MINUTOS_BLOQUEO = 5
_FORMATO = "%Y-%m-%d %H:%M:%S"

PREGUNTAS_PREDEFINIDAS = [
    "¿Cuál fue el nombre de tu primera mascota?",
    "¿En qué ciudad naciste?",
    "¿Cuál es el segundo nombre de tu madre?",
    "¿Cuál fue el nombre de tu primer colegio?",
    "¿Cuál era tu comida favorita de la infancia?",
    "¿Cuál era el apodo de tu mejor amigo de la infancia?",
]


def _normalizar_respuesta(texto: str) -> str:
    """Normaliza una respuesta (minúsculas, sin tildes y sin espacios repetidos) para evitar fallos por formato."""
    limpio = " ".join((texto or "")[:120].strip().lower().split())
    return "".join(
        c for c in unicodedata.normalize("NFD", limpio)
        if unicodedata.category(c) != "Mn"
    )


def existe_admin() -> bool:
    fila = consultar_uno("SELECT COUNT(*) AS n FROM usuarios WHERE id_rol = ? AND activo = 1", (ROL_ADMIN,))
    return fila["n"] > 0


def tiene_preguntas_admin() -> bool:
    """Verifica si algún administrador activo ya tiene sus 2 preguntas de seguridad configuradas."""
    fila = consultar_uno(
        """SELECT COUNT(*) AS n FROM preguntas_seguridad p
           JOIN usuarios u ON u.id_usuario = p.id_usuario
           WHERE u.id_rol = ? AND u.activo = 1""",
        (ROL_ADMIN,),
    )
    return (fila["n"] if fila else 0) >= 2


def registrar_primer_admin(username, nombre, password, confirmacion):
    """Solo funciona si aún no existe ningún administrador (evita escalar privilegios)."""
    if existe_admin():
        raise ErrorValidacion("Ya existe un administrador registrado en el sistema.")
    username = username.strip()
    nombre = nombre.strip()
    validar_username(username)
    if not nombre:
        raise ErrorValidacion("El nombre completo es obligatorio.")
    validar_password(password, confirmacion)
    with transaccion() as con:
        con.execute(
            "INSERT INTO usuarios (username, nombre_completo, password_hash, id_rol) VALUES (?,?,?,?)",
            (username, nombre, hash_password(password), ROL_ADMIN),
        )
        auditar("CREAR_ADMIN_INICIAL", username, con)


def guardar_preguntas_admin(pregunta1: str, respuesta1: str, pregunta2: str, respuesta2: str, username: str | None = None):
    """Guarda o actualiza las 2 preguntas personales de seguridad del administrador.
    Solo permite configurarlas sin sesión durante el asistente inicial (cuando aún no existen)."""
    if tiene_preguntas_admin() and not Sesion.es_admin():
        auditar("INTENTO_SOBRESCRIBIR_PREGUNTAS", username or "")
        raise ErrorPermiso("Debes iniciar sesión como administrador para modificar tus preguntas de seguridad.")

    p1 = (pregunta1 or "").strip()
    p2 = (pregunta2 or "").strip()
    r1 = _normalizar_respuesta(respuesta1)
    r2 = _normalizar_respuesta(respuesta2)

    if not p1 or not p2:
        raise ErrorValidacion("Debes seleccionar ambas preguntas de seguridad.")
    if p1 not in PREGUNTAS_PREDEFINIDAS or p2 not in PREGUNTAS_PREDEFINIDAS:
        raise ErrorValidacion("Las preguntas seleccionadas no son válidas.")
    if p1 == p2:
        raise ErrorValidacion("Debes elegir dos preguntas de seguridad diferentes.")
    if len(r1) < 2 or len(r2) < 2:
        raise ErrorValidacion("Cada respuesta de seguridad debe tener al menos 2 caracteres.")

    with transaccion() as con:
        if Sesion.es_admin():
            id_admin = Sesion.id()
            uname = Sesion.usuario["username"]
        elif username:
            fila = con.execute(
                "SELECT id_usuario, username FROM usuarios WHERE username = ? AND id_rol = ? AND activo = 1",
                (username.strip(), ROL_ADMIN),
            ).fetchone()
            if not fila:
                raise ErrorValidacion("No se encontró el usuario administrador.")
            id_admin, uname = fila["id_usuario"], fila["username"]
        else:
            fila = con.execute(
                "SELECT id_usuario, username FROM usuarios WHERE id_rol = ? AND activo = 1 ORDER BY id_usuario LIMIT 1",
                (ROL_ADMIN,),
            ).fetchone()
            if not fila:
                raise ErrorValidacion("Primero debes registrar la cuenta de administrador.")
            id_admin, uname = fila["id_usuario"], fila["username"]

        con.execute("DELETE FROM preguntas_seguridad WHERE id_usuario = ?", (id_admin,))
        con.execute(
            "INSERT INTO preguntas_seguridad (id_usuario, orden, pregunta, respuesta_hash) VALUES (?, 1, ?, ?)",
            (id_admin, p1, hash_password(r1)),
        )
        con.execute(
            "INSERT INTO preguntas_seguridad (id_usuario, orden, pregunta, respuesta_hash) VALUES (?, 2, ?, ?)",
            (id_admin, p2, hash_password(r2)),
        )
        con.execute(
            "INSERT INTO auditoria (id_usuario, accion, detalle) VALUES (?, 'CONFIGURAR_PREGUNTAS_SEGURIDAD', ?)",
            (id_admin, uname),
        )


def obtener_preguntas_admin_actual() -> list[str]:
    """Devuelve las preguntas actuales del administrador en sesión (o lista vacía si aún no tiene)."""
    if not Sesion.es_admin():
        return []
    filas = consultar(
        "SELECT pregunta FROM preguntas_seguridad WHERE id_usuario = ? ORDER BY orden",
        (Sesion.id(),),
    )
    return [f["pregunta"] for f in filas]


def _error_si_bloqueado(usuario: dict, ahora: datetime) -> str | None:
    if not usuario.get("bloqueado_hasta"):
        return None
    hasta = datetime.strptime(usuario["bloqueado_hasta"], _FORMATO)
    if hasta > ahora:
        minutos = int((hasta - ahora).total_seconds() // 60) + 1
        return f"Cuenta bloqueada temporalmente. Intenta de nuevo en {minutos} min."
    return None


def _registrar_fallo(con, usuario: dict, ahora: datetime, accion: str, msg_base: str) -> str:
    intentos = usuario["intentos_fallidos"] + 1
    bloqueo = None
    if intentos >= MAX_INTENTOS:
        bloqueo = (ahora + timedelta(minutes=MINUTOS_BLOQUEO)).strftime(_FORMATO)
        intentos = 0
    con.execute(
        "UPDATE usuarios SET intentos_fallidos=?, bloqueado_hasta=? WHERE id_usuario=?",
        (intentos, bloqueo, usuario["id_usuario"]),
    )
    con.execute(
        "INSERT INTO auditoria (id_usuario, accion, detalle) VALUES (?, ?, ?)",
        (usuario["id_usuario"], accion, usuario["username"]),
    )
    if bloqueo:
        return f"Demasiados intentos. Cuenta bloqueada por {MINUTOS_BLOQUEO} minutos."
    return f"{msg_base} Intentos restantes: {MAX_INTENTOS - intentos}."


def obtener_preguntas_recuperacion(username: str) -> list[str]:
    """Devuelve las 2 preguntas configuradas para el administrador indicado."""
    username = (username or "").strip()
    if not username:
        raise ErrorValidacion("Ingresa tu nombre de usuario de administrador.")

    fila = consultar_uno("SELECT * FROM usuarios WHERE username = ?", (username,))
    if not fila:
        raise ErrorValidacion("No se encontró ningún administrador con ese usuario.")
    if fila["id_rol"] != ROL_ADMIN:
        raise ErrorValidacion("Solo el administrador puede recuperar su clave aquí. Si eres cajero, pídele al administrador que la restablezca.")
    if not fila["activo"]:
        raise ErrorValidacion("Esta cuenta está desactivada.")

    err_bloq = _error_si_bloqueado(fila, datetime.now())
    if err_bloq:
        raise ErrorValidacion(err_bloq)

    preguntas = consultar(
        "SELECT pregunta FROM preguntas_seguridad WHERE id_usuario = ? ORDER BY orden",
        (fila["id_usuario"],),
    )
    if len(preguntas) < 2:
        raise ErrorValidacion("Este administrador no tiene preguntas de seguridad configuradas.")
    return [p["pregunta"] for p in preguntas]


def recuperar_password_admin(username: str, respuesta1: str, respuesta2: str, nueva_password: str, confirmacion: str):
    """Valida las respuestas a las preguntas personales y actualiza la contraseña del administrador."""
    username = (username or "").strip()
    r1, r2 = _normalizar_respuesta(respuesta1), _normalizar_respuesta(respuesta2)
    if not username:
        raise ErrorValidacion("Ingresa el usuario administrador.")
    if not r1 or not r2:
        raise ErrorValidacion("Responde ambas preguntas de seguridad.")

    validar_password(nueva_password, confirmacion)

    error = None
    with transaccion() as con:
        fila = con.execute(
            "SELECT * FROM usuarios WHERE username = ? AND id_rol = ? AND activo = 1",
            (username, ROL_ADMIN),
        ).fetchone()
        if not fila:
            verificar_password_ficticio(r1)
            error = "No se encontró ningún administrador activo con ese usuario."
        else:
            usuario = dict(fila)
            ahora = datetime.now()
            error = _error_si_bloqueado(usuario, ahora)
            if not error:
                pregs = con.execute(
                    "SELECT respuesta_hash FROM preguntas_seguridad WHERE id_usuario = ? ORDER BY orden",
                    (usuario["id_usuario"],),
                ).fetchall()
                if len(pregs) < 2:
                    error = "Este administrador no tiene preguntas de seguridad configuradas."
                elif not (verificar_password(r1, pregs[0]["respuesta_hash"])
                          and verificar_password(r2, pregs[1]["respuesta_hash"])):
                    error = _registrar_fallo(
                        con, usuario, ahora, "RECUPERACION_FALLIDA", "Una o ambas respuestas no coinciden."
                    )
                else:
                    con.execute(
                        "UPDATE usuarios SET password_hash=?, intentos_fallidos=0, bloqueado_hasta=NULL WHERE id_usuario=?",
                        (hash_password(nueva_password), usuario["id_usuario"]),
                    )
                    con.execute(
                        "INSERT INTO auditoria (id_usuario, accion, detalle) VALUES (?, 'RECUPERAR_CLAVE_ADMIN', ?)",
                        (usuario["id_usuario"], username),
                    )

    if error:
        raise ErrorValidacion(error)


def iniciar_sesion(username, password) -> dict:
    username = (username or "").strip()
    if not username or not password:
        raise ErrorValidacion("Ingresa tu usuario y contraseña.")

    error = None
    usuario_ok = None
    mensaje_generico = "Usuario o contraseña incorrectos."

    with transaccion() as con:
        fila = con.execute(
            """SELECT u.*, r.nombre AS rol FROM usuarios u
               JOIN roles r ON r.id_rol = u.id_rol WHERE u.username = ?""",
            (username,),
        ).fetchone()

        if fila is None:
            verificar_password_ficticio(password)
            con.execute("INSERT INTO auditoria (accion, detalle) VALUES ('LOGIN_FALLIDO', ?)", (username[:40],))
            error = mensaje_generico
        else:
            usuario = dict(fila)
            ahora = datetime.now()
            error = _error_si_bloqueado(usuario, ahora)
            if not error:
                if not usuario["activo"]:
                    error = "Esta cuenta está desactivada. Contacta al administrador."
                elif not verificar_password(password, usuario["password_hash"]):
                    error = _registrar_fallo(con, usuario, ahora, "LOGIN_FALLIDO", mensaje_generico)
                else:
                    con.execute(
                        "UPDATE usuarios SET intentos_fallidos=0, bloqueado_hasta=NULL, ultimo_acceso=? WHERE id_usuario=?",
                        (ahora.strftime(_FORMATO), usuario["id_usuario"]),
                    )
                    usuario.pop("password_hash", None)
                    Sesion.iniciar(usuario)
                    auditar("LOGIN", username, con)
                    usuario_ok = usuario

    if error:
        raise ErrorValidacion(error)
    return usuario_ok