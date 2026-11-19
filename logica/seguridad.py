"""Seguridad: hash de contraseñas, sesión activa blindada con HMAC, control de permisos y auditoría."""
import hashlib
import hmac
import re
import secrets
from functools import wraps

from database.conexion import transaccion

ROL_ADMIN = 1
ROL_CAJERO = 2

_ITERACIONES = 240_000
_MAX_LEN_PASS = 128
_CLAVE_SESION = secrets.token_bytes(32)


class ErrorPermiso(Exception):
    """Se lanza cuando un usuario intenta una acción que su rol no permite."""


class ErrorValidacion(Exception):
    """Datos de entrada inválidos (mensaje apto para mostrar al usuario)."""


# ---------- Contraseñas ----------
def hash_password(password: str) -> str:
    sal = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(sal), _ITERACIONES)
    return f"pbkdf2_sha256${_ITERACIONES}${sal}${digest.hex()}"


# Hash precalculado al arranque para igualar tiempos de respuesta cuando el usuario no existe (anti-timing attack)
_HASH_FICTICIO = hash_password("BillZen_Timing_Protection_99")


def verificar_password(password: str, almacenado: str) -> bool:
    if not password or len(password) > _MAX_LEN_PASS:
        return False
    try:
        algoritmo, iteraciones, sal, digest = almacenado.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        iters = int(iteraciones)
        if iters < 100_000 or iters > 1_000_000:
            return False
        calculado = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(sal), iters)
        return hmac.compare_digest(calculado.hex(), digest)
    except (ValueError, AttributeError, TypeError):
        return False


def verificar_password_ficticio(password: str):
    """Ejecuta PBKDF2 en vacío para evitar enumeración de usuarios por tiempo de respuesta."""
    verificar_password((password or "")[:_MAX_LEN_PASS], _HASH_FICTICIO)


def validar_password(password: str, confirmacion: str | None = None):
    if not password:
        raise ErrorValidacion("La clave es obligatoria.")
    if len(password) > _MAX_LEN_PASS:
        raise ErrorValidacion(f"La clave no puede superar los {_MAX_LEN_PASS} caracteres.")
    if confirmacion is not None and password != confirmacion:
        raise ErrorValidacion("Las claves no coinciden.")
    if len(password) < 5:
        raise ErrorValidacion("La clave de acceso debe tener al menos 5 caracteres (puede ser solo numérica, ej. 12345).")


def validar_username(username: str):
    if not re.fullmatch(r"[A-Za-z0-9_.]{3,20}", username or ""):
        raise ErrorValidacion("El usuario debe tener de 3 a 20 caracteres (letras, números, punto o guion bajo).")


# ---------- Sesión blindada con HMAC ----------
class Sesion:
    usuario: dict | None = None
    _firma: str | None = None

    @classmethod
    def _calcular_firma(cls, u: dict) -> str:
        mensaje = f"{u.get('id_usuario')}:{u.get('username')}:{u.get('id_rol')}".encode("utf-8")
        return hmac.new(_CLAVE_SESION, mensaje, hashlib.sha256).hexdigest()

    @classmethod
    def iniciar(cls, usuario: dict):
        copia = dict(usuario)
        copia.pop("password_hash", None)
        cls.usuario = copia
        cls._firma = cls._calcular_firma(copia)

    @classmethod
    def verificar_integridad(cls) -> bool:
        if not cls.usuario or not cls._firma:
            return False
        esperada = cls._calcular_firma(cls.usuario)
        return hmac.compare_digest(cls._firma, esperada)

    @classmethod
    def cerrar(cls):
        if cls.usuario:
            try:
                auditar("CIERRE_SESION", cls.usuario.get("username", ""))
            except Exception:
                pass
        cls.usuario = None
        cls._firma = None

    @classmethod
    def id(cls):
        return cls.usuario["id_usuario"] if cls.verificar_integridad() else None

    @classmethod
    def es_admin(cls):
        return cls.verificar_integridad() and cls.usuario["id_rol"] == ROL_ADMIN


def requiere_rol(*roles):
    """Decorador: valida en la capa lógica que exista sesión íntegra (HMAC) y que el rol esté permitido.
    Así la seguridad no depende solo de ocultar botones en la interfaz ni permite alterar el rol en memoria."""
    def decorador(funcion):
        @wraps(funcion)
        def envoltura(*args, **kwargs):
            if not Sesion.usuario:
                raise ErrorPermiso("Debes iniciar sesión.")
            if not Sesion.verificar_integridad():
                Sesion.cerrar()
                raise ErrorPermiso("Sesión inválida por motivos de seguridad. Inicia sesión nuevamente.")
            if roles and Sesion.usuario["id_rol"] not in roles:
                auditar("ACCESO_DENEGADO", funcion.__name__)
                raise ErrorPermiso("No tienes permisos para realizar esta acción.")
            return funcion(*args, **kwargs)
        return envoltura
    return decorador


def auditar(accion: str, detalle: str = "", con=None):
    sql = "INSERT INTO auditoria (id_usuario, accion, detalle) VALUES (?,?,?)"
    uid = Sesion.usuario["id_usuario"] if (Sesion.usuario and Sesion._firma) else None
    params = (uid, (accion or "")[:80], (detalle or "")[:300])
    if con is not None:
        con.execute(sql, params)
    else:
        with transaccion() as c:
            c.execute(sql, params)
