"""Sistema de Licenciamiento Anti-Piratería (Hardware ID) y Feature Toggling por Plan Comercial.

Reglas de Arquitectura:
1. Offline-First con Candado Inicial: exige activación online únicamente en el primer uso
   o si se detecta que la base de datos fue copiada por USB a otro computador.
2. Huella Física (Hardware ID): combina la dirección MAC (`uuid.getnode()`) + serial físico
   de placa base / UUID del sistema en Windows + sal secreta, hasheado con SHA-256.
3. Validación Híbrida Anticlones: compara en cada arranque el `hw_id_hash` actual con el
   almacenado en `licencia_sistema` y verifica su `firma_integridad` HMAC-SHA256 para impedir
   que alguien edite el plan comercial manualmente abriendo el archivo SQLite.
4. Camaleón UI (Feature Toggling): habilita o bloquea módulos según el `plan_adquirido`
   (`'basico'`, `'standart'`, `'pro'`) en un único ejecutable `BillZen.exe`.
"""
import hashlib
import hmac
import json
import os
import subprocess
import urllib.error
import urllib.request
import uuid

from database.conexion import consultar_uno, transaccion
from logica.seguridad import ROL_ADMIN, ErrorPermiso, ErrorValidacion, auditar, hash_password

URL_API_LICENCIA = os.environ.get(
    "BILLZEN_LICENSE_API",
    "https://bill-zen-users.vercel.app/api/licencia/activar",
)
URL_API_LICENCIA_LOCAL = "http://127.0.0.1:8000/api/licencia/activar"
URL_PORTAL_PLANES = "https://bill-zen-users.vercel.app/#planes"

PLAN_BASICO = "basico"
PLAN_STANDART = "standart"
PLAN_PRO = "pro"
PLANES_VALIDOS = (PLAN_BASICO, PLAN_STANDART, PLAN_PRO)

NIVELES_PLAN = {
    PLAN_BASICO: 1,
    PLAN_STANDART: 2,
    PLAN_PRO: 3,
}

# Nivel mínimo requerido por cada módulo de la interfaz
PLAN_MINIMO_MODULO = {
    "dashboard": PLAN_BASICO,
    "facturacion": PLAN_BASICO,
    "facturas": PLAN_BASICO,
    "productos": PLAN_BASICO,
    "inventario": PLAN_BASICO,
    "configuracion": PLAN_BASICO,
    # Módulos bloqueados en plan 'basico' (requieren 'standart' o 'pro')
    "contabilidad": PLAN_STANDART,
    "reportes": PLAN_STANDART,
    "usuarios": PLAN_STANDART,
    # Módulo exclusivo del plan 'pro'
    "auditoria_movil": PLAN_PRO,
}

_SECRETO_HW = b"BillZen-ERP-HardwareLock-v1-2026-Salt"
_CLAVE_INTEGRIDAD_LICENCIA = b"BillZen-ERP-SQLite-PlanIntegrity-HMAC-Key-2026"
_CACHE_HW_ID: str | None = None


def _obtener_serial_windows() -> str:
    """Obtiene el identificador físico de la máquina en Windows de forma instantánea vía winreg."""
    if os.name != "nt":
        return "NON_WINDOWS_HOST"

    # 1. Lectura nativa instantánea (< 1 ms) del MachineGuid criptográfico del equipo en el Registro
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
        ) as k:
            val, _ = winreg.QueryValueEx(k, "MachineGuid")
            if val:
                return str(val).strip()
    except Exception:
        pass

    # 2. Respaldo por WMIC si el registro no estuviera accesible
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for cmd in (
        ["wmic", "csproduct", "get", "UUID"],
        ["wmic", "baseboard", "get", "serialnumber"],
    ):
        try:
            salida = subprocess.check_output(
                cmd,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
                creationflags=flags,
            )
            lineas = [
                l.strip()
                for l in salida.splitlines()
                if l.strip() and l.strip().upper() not in ("UUID", "SERIALNUMBER")
            ]
            if lineas and lineas[0] not in ("", "To be filled by O.E.M.", "Default string"):
                return lineas[0]
        except Exception:
            continue

    return "WIN_GENERIC_SERIAL"


def generar_hardware_id(forzar_recalculo: bool = False) -> str:
    """Construye una huella física única e inmutable del equipo combinando MAC + Serial físico + SHA-256."""
    global _CACHE_HW_ID
    if _CACHE_HW_ID is not None and not forzar_recalculo:
        return _CACHE_HW_ID

    mac_int = uuid.getnode()
    mac_hex = f"{mac_int:012x}"
    serial_fisico = _obtener_serial_windows()

    semilla = f"MAC:{mac_hex}|SER:{serial_fisico}".encode("utf-8")
    _CACHE_HW_ID = hmac.new(_SECRETO_HW, semilla, hashlib.sha256).hexdigest()
    return _CACHE_HW_ID


def _normalizar_plan(plan: str) -> str:
    limpio = (plan or "").strip().lower()
    if limpio in ("standard", "estandar", "estándar"):
        return PLAN_STANDART
    if limpio in ("básico",):
        return PLAN_BASICO
    return limpio if limpio in PLANES_VALIDOS else PLAN_BASICO


def _firmar_registro_licencia(email: str, hw_id_hash: str, plan: str) -> str:
    """Firma con HMAC-SHA256 los datos de licencia para impedir edición manual de `plan_adquirido` en SQLite."""
    mensaje = f"{email.strip().lower()}|{hw_id_hash}|{plan}".encode("utf-8")
    return hmac.new(_CLAVE_INTEGRIDAD_LICENCIA, mensaje, hashlib.sha256).hexdigest()


def guardar_licencia_local(email: str, hw_id: str, plan_adquirido: str) -> dict:
    """Guarda en SQLite el Hardware ID vinculado y el plan adquirido con su firma de integridad."""
    email_limpio = (email or "").strip().lower()
    plan_norm = _normalizar_plan(plan_adquirido)
    firma = _firmar_registro_licencia(email_limpio, hw_id, plan_norm)

    with transaccion() as con:
        con.execute("DELETE FROM licencia_sistema")
        con.execute(
            """INSERT INTO licencia_sistema (id_licencia, email_cuenta, hw_id_hash, plan_adquirido, firma_integridad)
               VALUES (1, ?, ?, ?, ?)""",
            (email_limpio, hw_id, plan_norm, firma),
        )
        auditar("ACTIVAR_LICENCIA_HARDWARE", f"email={email_limpio} plan={plan_norm}", con)

    return {
        "valido": True,
        "plan": plan_norm,
        "email": email_limpio,
        "hw_id": hw_id,
        "motivo": "OK",
    }


def verificar_licencia_local() -> dict:
    """Verifica en cada arranque si existe una licencia válida y si el Hardware ID coincide con esta máquina."""
    hw_actual = generar_hardware_id()
    try:
        fila = consultar_uno("SELECT * FROM licencia_sistema WHERE id_licencia = 1")
    except Exception:
        fila = None

    if not fila:
        return {
            "valido": False,
            "plan": None,
            "hw_id": hw_actual,
            "motivo": "PRIMER_USO",
            "mensaje": "Activación inicial requerida. Ingresa con tu cuenta de Bill Zen para vincular este equipo.",
        }

    hw_guardado = str(fila.get("hw_id_hash") or "")
    email_guardado = str(fila.get("email_cuenta") or "")
    plan_guardado = str(fila.get("plan_adquirido") or "")
    firma_guardada = str(fila.get("firma_integridad") or "")

    # 1. Comparación estricta en tiempo constante del Hardware ID físico (Anticlones USB)
    if not hmac.compare_digest(hw_guardado, hw_actual):
        try:
            auditar("BLOQUEO_CLONACION_USB", f"HW esperado={hw_guardado[:12]}... actual={hw_actual[:12]}...")
        except Exception:
            pass
        return {
            "valido": False,
            "plan": None,
            "hw_id": hw_actual,
            "motivo": "HARDWARE_DIFERENTE",
            "mensaje": (
                "Se detectó que el sistema fue copiado a un equipo diferente al autorizado. "
                "Por seguridad anti-piratería, debes validar tu licencia online."
            ),
        }

    # 2. Verificación de integridad contra manipulación manual de la tabla SQLite
    firma_esperada = _firmar_registro_licencia(email_guardado, hw_guardado, plan_guardado)
    if not hmac.compare_digest(firma_guardada, firma_esperada):
        try:
            auditar("BLOQUEO_LICENCIA_ADULTERADA", f"email={email_guardado} plan={plan_guardado}")
        except Exception:
            pass
        return {
            "valido": False,
            "plan": None,
            "hw_id": hw_actual,
            "motivo": "LICENCIA_ADULTERADA",
            "mensaje": "El registro local de licencia fue alterado. Por favor reactiva tu cuenta online.",
        }

    return {
        "valido": True,
        "plan": _normalizar_plan(plan_guardado),
        "email": email_guardado,
        "hw_id": hw_actual,
        "activado_en": fila.get("activado_en"),
        "motivo": "OK",
        "mensaje": "Licencia activa y verificada.",
    }


def _sincronizar_empresa_y_admin_local(datos_nube: dict, password_plana: str):
    """Sincroniza automáticamente en el SQLite local la empresa y el usuario administrador
    provenientes de Neon.tech para que el cliente pueda iniciar sesión en el ERP con sus mismas credenciales."""
    nit = str(datos_nube.get("nit") or "").strip()
    razon_social = str(datos_nube.get("razon_social") or "").strip()
    email = str(datos_nube.get("email") or "").strip()
    nombres = str(datos_nube.get("nombres_admin") or "Administrador").strip()
    apellidos = str(datos_nube.get("apellidos_admin") or "").strip()
    nombre_completo = f"{nombres} {apellidos}".strip() or razon_social or "Administrador"

    if not nit and not email:
        return

    with transaccion() as con:
        if nit and razon_social:
            emp_existente = con.execute("SELECT id_empresa FROM empresa WHERE id_empresa = 1").fetchone()
            if not emp_existente:
                con.execute(
                    """INSERT INTO empresa (id_empresa, nit, razon_social, correo, regimen, prefijo_factura)
                       VALUES (1, ?, ?, ?, 'Responsable de IVA', 'FV')""",
                    (nit, razon_social, email),
                )
            else:
                con.execute(
                    "UPDATE empresa SET nit = ?, razon_social = ?, correo = COALESCE(NULLIF(correo, ''), ?) WHERE id_empresa = 1",
                    (nit, razon_social, email),
                )

        if password_plana:
            pwd_hash_local = hash_password(password_plana)
            admin_fila = con.execute(
                "SELECT id_usuario, username FROM usuarios WHERE id_rol = ? ORDER BY id_usuario LIMIT 1",
                (ROL_ADMIN,),
            ).fetchone()
            username_preferido = email or nit or "admin"
            if not admin_fila:
                con.execute(
                    """INSERT INTO usuarios (username, nombre_completo, password_hash, id_rol, activo)
                       VALUES (?, ?, ?, ?, 1)""",
                    (username_preferido, nombre_completo, pwd_hash_local, ROL_ADMIN),
                )
            else:
                con.execute(
                    """UPDATE usuarios
                       SET password_hash = ?, activo = 1, intentos_fallidos = 0, bloqueado_hasta = NULL
                       WHERE id_usuario = ?""",
                    (pwd_hash_local, admin_fila["id_usuario"]),
                )


def _post_api_licencia(url: str, cuerpo: bytes) -> dict:
    req = urllib.request.Request(
        url,
        data=cuerpo,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "BillZenERP-Desktop/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def activar_licencia_online(email: str, password: str, hw_id: str | None = None) -> dict:
    """Envía `POST /api/licencia/activar` con `(email/nit, password, hardware_id)` a la API de `bill_zen_users`.
    El `.exe` jamás almacena credenciales de la base de datos en la nube (Neon.tech); toda validación
    ocurre en el backend."""
    identificador = (email or "").strip()
    if not identificador:
        raise ErrorValidacion("Ingresa el correo electrónico o NIT registrado en Bill Zen.")
    if not password:
        raise ErrorValidacion("Ingresa la contraseña de tu cuenta web.")

    hw_actual = hw_id or generar_hardware_id()
    cuerpo = json.dumps({
        "email": identificador,
        "nit": identificador,
        "password": password,
        "hardware_id": hw_actual,
    }).encode("utf-8")

    datos = None
    es_url_por_defecto = "bill-zen-users.vercel.app" in URL_API_LICENCIA

    try:
        datos = _post_api_licencia(URL_API_LICENCIA, cuerpo)
    except urllib.error.HTTPError as e:
        # En entorno de desarrollo local, si Vercel aún no tiene el último deploy (404),
        # intenta contra el backend FastAPI local en 127.0.0.1:8000 sin exponer credenciales de BD.
        if es_url_por_defecto and e.code == 404:
            try:
                datos = _post_api_licencia(URL_API_LICENCIA_LOCAL, cuerpo)
            except urllib.error.HTTPError as e_loc:
                e = e_loc
            except Exception:
                pass
        if datos is None:
            try:
                err_json = json.loads(e.read().decode("utf-8"))
                msg_srv = (
                    err_json.get("detail")
                    or err_json.get("error")
                    or err_json.get("message")
                    or err_json.get("mensaje")
                )
            except Exception:
                msg_srv = None
            if e.code in (401, 403):
                raise ErrorValidacion(msg_srv or "Credenciales incorrectas o licencia ya vinculada a otro computador.")
            if e.code == 404:
                raise ErrorValidacion(msg_srv or "No se encontró una suscripción activa asociada a esta cuenta.")
            raise ErrorValidacion(msg_srv or f"El servidor de licencias rechazó la solicitud (HTTP {e.code}).")
    except (urllib.error.URLError, TimeoutError, OSError):
        if es_url_por_defecto:
            try:
                datos = _post_api_licencia(URL_API_LICENCIA_LOCAL, cuerpo)
            except urllib.error.HTTPError as e_loc:
                try:
                    err_json = json.loads(e_loc.read().decode("utf-8"))
                    msg_srv = err_json.get("detail") or err_json.get("error")
                except Exception:
                    msg_srv = None
                raise ErrorValidacion(msg_srv or f"Error de validación (HTTP {e_loc.code}).")
            except Exception:
                raise ErrorValidacion(
                    "Necesitas conexión a internet para activar este equipo por primera vez. "
                    "Verifica tu red e inténtalo de nuevo."
                )
        else:
            raise ErrorValidacion(
                "Necesitas conexión a internet para activar este equipo por primera vez. "
                "Verifica tu red e inténtalo de nuevo."
            )
    except Exception:
        raise ErrorValidacion("Respuesta inválida del servidor de licencias.")

    if not datos.get("ok", True) and datos.get("status") != "ok" and "plan_adquirido" not in datos and "plan" not in datos:
        raise ErrorValidacion(datos.get("detail") or datos.get("error") or datos.get("mensaje") or "No se pudo activar la licencia.")

    plan_recibido = (
        datos.get("plan_adquirido")
        or datos.get("plan")
        or (datos.get("empresa") or {}).get("plan_adquirido")
        or PLAN_BASICO
    )
    email_guardar = str(datos.get("email") or identificador).strip().lower()
    _sincronizar_empresa_y_admin_local(datos, password)
    return guardar_licencia_local(email_guardar, hw_actual, plan_recibido)


# ==============================================================================
# FEATURE TOGGLING (CAMALEÓN UI)
# ==============================================================================
def obtener_plan_actual() -> str:
    """Devuelve el plan comercial activo en SQLite (`'basico'`, `'standart'` o `'pro'`)."""
    est = verificar_licencia_local()
    return est["plan"] if est["valido"] and est["plan"] else PLAN_BASICO


def permite_modulo(clave_modulo: str, plan_actual: str | None = None) -> bool:
    """Indica si el plan comercial activo tiene permiso para usar `clave_modulo`."""
    plan = _normalizar_plan(plan_actual or obtener_plan_actual())
    minimo = PLAN_MINIMO_MODULO.get(clave_modulo, PLAN_BASICO)
    return NIVELES_PLAN.get(plan, 1) >= NIVELES_PLAN.get(minimo, 1)


def plan_requerido_para(clave_modulo: str) -> str:
    """Devuelve el nombre legible del plan mínimo requerido para desbloquear un módulo."""
    minimo = PLAN_MINIMO_MODULO.get(clave_modulo, PLAN_BASICO)
    nombres = {
        PLAN_BASICO: "Básico",
        PLAN_STANDART: "Standart",
        PLAN_PRO: "Pro",
    }
    return nombres.get(minimo, "Pro")


def requiere_plan(plan_minimo: str):
    """Decorador para proteger funciones de negocio según el plan comercial adquirido."""
    nivel_req = NIVELES_PLAN.get(_normalizar_plan(plan_minimo), 3)

    def decorador(fn):
        def envoltura(*args, **kwargs):
            plan_act = obtener_plan_actual()
            if NIVELES_PLAN.get(plan_act, 1) < nivel_req:
                raise ErrorPermiso(
                    f"Esta funcionalidad requiere el Plan {plan_minimo.capitalize()} o superior "
                    f"(tu plan actual es {plan_act.capitalize()})."
                )
            return fn(*args, **kwargs)

        return envoltura

    return decorador
