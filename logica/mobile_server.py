import base64
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from database.conexion import consultar_uno, ruta_db, transaccion
from logica.auth_logic import _error_si_bloqueado, _registrar_fallo
from logica.seguridad import (
    ROL_ADMIN,
    Sesion,
    auditar,
    requiere_rol,
    verificar_password,
    verificar_password_ficticio,
)

PUERTO_DEFECTO = 8765
TTL_PAIRING_SEG = 300     
TTL_SESION_MOVIL_SEG = 43200 
URL_DESCARGA_APP = "https://bill-zen-users.vercel.app/#descargar"
URL_LOGIN_PORTAL = "https://bill-zen-users.vercel.app/login.html"
_FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"

# Claves efímeras en RAM y control de revocación
_LOCK = threading.RLock()
_CLAVE_HMAC_MOVIL = secrets.token_bytes(32)
_GENERACION_SESION = 1
_SESIONES_ACTIVAS: dict[str, dict] = {}

# Estado del micro-servidor y túnel cloudflared
_SERVIDOR_HTTP: ThreadingHTTPServer | None = None
_HILO_SERVIDOR: threading.Thread | None = None
_PUERTO_ACTIVO: int = PUERTO_DEFECTO

_PROCESO_TUNEL: subprocess.Popen | None = None
_HILO_TUNEL: threading.Thread | None = None
_URL_REMOTA: str = ""
_ESTADO_TUNEL: str = "Detenido"



def conectar_ro() -> sqlite3.Connection:
    ruta_absoluta = str(Path(ruta_db()).resolve()).replace("\\", "/")
    uri_ro = f"file:{ruta_absoluta}?mode=ro"
    con = sqlite3.connect(uri_ro, uri=True, timeout=5.0, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON;")
    return con




def _firmar_payload(datos: dict) -> str:
    cuerpo = base64.urlsafe_b64encode(
        json.dumps(datos, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii").rstrip("=")
    firma = hmac.new(_CLAVE_HMAC_MOVIL, cuerpo.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{cuerpo}.{firma}"


def _verificar_token_firmado(token: str, tipo_esperado: str) -> dict | None:
    if not token or not isinstance(token, str) or "." not in token:
        return None
    partes = token.split(".")
    if len(partes) != 2:
        return None
    cuerpo, firma_recibida = partes
    firma_esperada = hmac.new(_CLAVE_HMAC_MOVIL, cuerpo.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(firma_recibida, firma_esperada):
        return None
    try:
        padding = "=" * (-len(cuerpo) % 4)
        datos = json.loads(base64.urlsafe_b64decode(cuerpo + padding).decode("utf-8"))
    except Exception:
        return None

    if not isinstance(datos, dict) or datos.get("typ") != tipo_esperado:
        return None

    ahora = time.time()
    exp = datos.get("exp", 0)
    iat = datos.get("iat", 0)
    if not isinstance(exp, (int, float)) or ahora > exp or iat > ahora + 5:
        return None
    return datos


def generar_pairing_token(ahora: float | None = None) -> tuple[str, int]:
    """Genera un `pairing_token` firmado con HMAC-SHA256 que expira estrictamente en 5 minutos."""
    ts = int(ahora if ahora is not None else time.time())
    exp = ts + TTL_PAIRING_SEG
    with _LOCK:
        gen = _GENERACION_SESION
    payload = {
        "typ": "pairing",
        "iat": ts,
        "exp": exp,
        "gen": gen,
        "jti": secrets.token_hex(8),
    }
    return _firmar_payload(payload), exp


def validar_pairing_token(token: str, ahora: float | None = None) -> bool:
    """Valida firma HMAC-SHA256 y expiración estricta de 5 minutos (300 s)."""
    datos = _verificar_token_firmado(token, "pairing")
    if not datos:
        return False
    ts = ahora if ahora is not None else time.time()
    if ts > datos["exp"] or (datos["exp"] - datos["iat"]) > TTL_PAIRING_SEG:
        return False
    return True


def _emitir_session_token(id_usuario: int, username: str) -> str:
    ts = int(time.time())
    exp = ts + TTL_SESION_MOVIL_SEG
    jti = secrets.token_hex(12)
    with _LOCK:
        gen = _GENERACION_SESION
        token = _firmar_payload({
            "typ": "session",
            "uid": id_usuario,
            "usr": username,
            "rol": ROL_ADMIN,
            "iat": ts,
            "exp": exp,
            "gen": gen,
            "jti": jti,
        })
        _SESIONES_ACTIVAS[jti] = {
            "id_usuario": id_usuario,
            "username": username,
            "creado": datetime.now().strftime(_FORMATO_FECHA),
            "exp": exp,
        }
    return token


def validar_session_token(token: str) -> dict | None:
    """Valida que el `session_token` sea auténtico, no haya expirado (12 h) ni haya sido revocado."""
    datos = _verificar_token_firmado(token, "session")
    if not datos:
        return None
    if datos.get("rol") != ROL_ADMIN:
        return None
    with _LOCK:
        if datos.get("gen") != _GENERACION_SESION:
            return None
        jti = datos.get("jti")
        if not jti or jti not in _SESIONES_ACTIVAS:
            return None
    return datos


def revocar_sesiones_moviles() -> int:
    """Invalida inmediatamente todos los `session_token` y `pairing_token` emitidos."""
    global _CLAVE_HMAC_MOVIL, _GENERACION_SESION
    with _LOCK:
        cantidad = len(_SESIONES_ACTIVAS)
        _SESIONES_ACTIVAS.clear()
        _GENERACION_SESION += 1
        _CLAVE_HMAC_MOVIL = secrets.token_bytes(32)
    try:
        auditar("REVOCAR_SESIONES_MOVILES", f"Sesiones revocadas: {cantidad}")
    except Exception:
        pass
    return cantidad


def contar_sesiones_activas() -> int:
    ahora = time.time()
    with _LOCK:
        expiradas = [k for k, v in _SESIONES_ACTIVAS.items() if v["exp"] < ahora]
        for k in expiradas:
            _SESIONES_ACTIVAS.pop(k, None)
        return len(_SESIONES_ACTIVAS)


# ==============================================================================
# 3. LÓGICA DE NEGOCIO DE LOS 2 ENDPOINTS MÓVILES
# ==============================================================================
def autenticar_login_movil(pairing_token: str, username: str, password: str, ip_origen: str = "") -> tuple[int, dict]:
    """Lógica del Endpoint 1 (`POST /api/movil/login`).
    Devuelve `(status_code_http, diccionario_respuesta)`."""
    if not validar_pairing_token(pairing_token):
        return int(HTTPStatus.UNAUTHORIZED), {
            "ok": False,
            "error": "El código QR de vinculación es inválido o ya expiró (máx. 5 min). Genera un nuevo QR en Bill Zen.",
        }

    username = (username or "").strip()
    if not username or not password:
        return int(HTTPStatus.BAD_REQUEST), {
            "ok": False,
            "error": "Debes enviar usuario y contraseña.",
        }

    mensaje_generico = "Usuario o contraseña incorrectos."
    status_http = int(HTTPStatus.UNAUTHORIZED)
    respuesta: dict = {"ok": False, "error": mensaje_generico}

    with transaccion() as con:
        fila = con.execute(
            """SELECT u.*, r.nombre AS rol FROM usuarios u
               JOIN roles r ON r.id_rol = u.id_rol WHERE u.username = ?""",
            (username,),
        ).fetchone()

        if fila is None:
            verificar_password_ficticio(password)
            con.execute(
                "INSERT INTO auditoria (accion, detalle) VALUES ('LOGIN_MOVIL_FALLIDO', ?)",
                (f"{username[:40]} ({ip_origen or 'remoto'})",),
            )
            return int(HTTPStatus.UNAUTHORIZED), {"ok": False, "error": mensaje_generico}

        usuario = dict(fila)
        ahora = datetime.now()
        err_bloq = _error_si_bloqueado(usuario, ahora)
        if err_bloq:
            con.execute(
                "INSERT INTO auditoria (id_usuario, accion, detalle) VALUES (?, 'LOGIN_MOVIL_BLOQUEADO', ?)",
                (usuario["id_usuario"], f"{username} ({ip_origen or 'remoto'})"),
            )
            return int(HTTPStatus.FORBIDDEN), {"ok": False, "error": err_bloq}

        if not usuario["activo"]:
            verificar_password_ficticio(password)
            con.execute(
                "INSERT INTO auditoria (id_usuario, accion, detalle) VALUES (?, 'LOGIN_MOVIL_INACTIVO', ?)",
                (usuario["id_usuario"], f"{username} ({ip_origen or 'remoto'})"),
            )
            return int(HTTPStatus.FORBIDDEN), {
                "ok": False,
                "error": "Esta cuenta está desactivada.",
            }

        if not verificar_password(password, usuario["password_hash"]):
            msg_fallo = _registrar_fallo(con, usuario, ahora, "LOGIN_MOVIL_FALLIDO", mensaje_generico)
            return int(HTTPStatus.UNAUTHORIZED), {"ok": False, "error": msg_fallo}

        # Contraseña válida -> Verificar obligatoriamente id_rol == 1 (ROL_ADMIN)
        if usuario["id_rol"] != ROL_ADMIN:
            con.execute(
                "INSERT INTO auditoria (id_usuario, accion, detalle) VALUES (?, 'ACCESO_MOVIL_DENEGADO_ROL', ?)",
                (
                    usuario["id_usuario"],
                    f"Cajero/rol={usuario['id_rol']} ({username}) rechazado con 403 desde {ip_origen or 'remoto'}",
                ),
            )
            return int(HTTPStatus.FORBIDDEN), {
                "ok": False,
                "error": "Acceso prohibido (403): la auditoría remota es exclusiva para el Administrador.",
            }

        # Login exitoso de Administrador
        con.execute(
            "UPDATE usuarios SET intentos_fallidos=0, bloqueado_hasta=NULL, ultimo_acceso=? WHERE id_usuario=?",
            (ahora.strftime(_FORMATO_FECHA), usuario["id_usuario"]),
        )
        con.execute(
            "INSERT INTO auditoria (id_usuario, accion, detalle) VALUES (?, 'LOGIN_MOVIL_ADMIN', ?)",
            (usuario["id_usuario"], f"{username} ({ip_origen or 'remoto'})"),
        )
        token_sesion = _emitir_session_token(usuario["id_usuario"], usuario["username"])
        status_http = int(HTTPStatus.OK)
        respuesta = {
            "ok": True,
            "session_token": token_sesion,
            "token_type": "Bearer",
            "expires_in": TTL_SESION_MOVIL_SEG,
            "usuario": {
                "id_usuario": usuario["id_usuario"],
                "username": usuario["username"],
                "nombre_completo": usuario["nombre_completo"],
                "id_rol": usuario["id_rol"],
            },
        }

    return status_http, respuesta


def obtener_auditoria_dia_ro() -> dict:
    """Lógica del Endpoint 2 (`GET /api/movil/auditoria-dia`).
    Ejecuta todas las consultas sobre una conexión SQLite `mode=ro`."""
    hoy = date.today().isoformat()
    con = conectar_ro()
    try:
        emp = con.execute(
            "SELECT nit, razon_social FROM empresa WHERE id_empresa = 1"
        ).fetchone()

        # a) KPIs del día
        emitidas = con.execute(
            """SELECT COALESCE(SUM(total), 0) AS total_vendido,
                      COALESCE(SUM(subtotal), 0) AS ventas_netas,
                      COALESCE(SUM(iva), 0) AS iva_total,
                      COUNT(*) AS conteo
               FROM facturas
               WHERE estado = 'EMITIDA' AND date(fecha) = ?""",
            (hoy,),
        ).fetchone()

        anuladas = con.execute(
            """SELECT COALESCE(SUM(total), 0) AS monto_anulado,
                      COUNT(*) AS conteo
               FROM facturas
               WHERE estado = 'ANULADA' AND date(fecha) = ?""",
            (hoy,),
        ).fetchone()

        costo_hoy = con.execute(
            """SELECT COALESCE(SUM(d.costo_unitario * d.cantidad), 0) AS costo
               FROM detalles_factura d
               JOIN facturas f ON f.id_factura = d.id_factura
               WHERE f.estado = 'EMITIDA' AND date(f.fecha) = ?""",
            (hoy,),
        ).fetchone()

        gastos_hoy = con.execute(
            """SELECT COALESCE(SUM(valor), 0) AS total_gastos,
                      COUNT(*) AS conteo_gastos
               FROM gastos
               WHERE date(fecha) = ?""",
            (hoy,),
        ).fetchone()

        ventas_netas_hoy = float(emitidas["ventas_netas"] or 0)
        costo_ventas_hoy = float(costo_hoy["costo"] or 0)
        total_gastos_hoy = float(gastos_hoy["total_gastos"] or 0)
        utilidad_neta_hoy = ventas_netas_hoy - costo_ventas_hoy - total_gastos_hoy

        kpis_dia = {
            "fecha": hoy,
            "total_vendido_hoy": float(emitidas["total_vendido"] or 0),
            "ventas_netas_hoy": ventas_netas_hoy,
            "iva_hoy": float(emitidas["iva_total"] or 0),
            "facturas_emitidas_hoy": int(emitidas["conteo"] or 0),
            "facturas_anuladas_hoy": int(anuladas["conteo"] or 0),
            "monto_anulado_hoy": float(anuladas["monto_anulado"] or 0),
            "costo_ventas_hoy": costo_ventas_hoy,
            "gastos_hoy": total_gastos_hoy,
            "utilidad_neta_hoy": utilidad_neta_hoy,
        }

        # b) Ventas por cajero hoy
        filas_cajeros = con.execute(
            """SELECT u.username,
                      u.nombre_completo AS usuario,
                      COUNT(f.id_factura) AS facturas_emitidas,
                      COALESCE(SUM(f.total), 0) AS monto_total
               FROM facturas f
               JOIN usuarios u ON u.id_usuario = f.id_usuario
               WHERE f.estado = 'EMITIDA' AND date(f.fecha) = ?
               GROUP BY u.id_usuario
               ORDER BY monto_total DESC""",
            (hoy,),
        ).fetchall()
        ventas_por_cajero = [
            {
                "username": r["username"],
                "usuario": r["usuario"],
                "facturas_emitidas": int(r["facturas_emitidas"] or 0),
                "monto_total": float(r["monto_total"] or 0),
            }
            for r in filas_cajeros
        ]

        # c) Movimientos de stock hoy (últimos 30) + alertas de stock bajo
        filas_movs = con.execute(
            """SELECT m.id_movimiento,
                      m.fecha,
                      m.tipo,
                      p.codigo,
                      p.nombre AS producto,
                      m.cantidad,
                      m.stock_final,
                      COALESCE(m.referencia, '') AS referencia,
                      COALESCE(u.nombre_completo, u.username, 'Sistema') AS usuario
               FROM movimientos_inventario m
               JOIN productos p ON p.id_producto = m.id_producto
               LEFT JOIN usuarios u ON u.id_usuario = m.id_usuario
               WHERE date(m.fecha) = ? AND m.tipo IN ('ENTRADA', 'VENTA', 'ANULACION')
               ORDER BY m.id_movimiento DESC
               LIMIT 30""",
            (hoy,),
        ).fetchall()

        filas_alertas = con.execute(
            """SELECT id_producto, codigo, nombre, stock, stock_minimo
               FROM productos
               WHERE activo = 1 AND stock <= stock_minimo
               ORDER BY stock ASC, nombre ASC"""
        ).fetchall()

        movimientos_stock_hoy = {
            "ultimos_movimientos": [
                {
                    "id_movimiento": r["id_movimiento"],
                    "fecha": r["fecha"],
                    "tipo": r["tipo"],
                    "codigo": r["codigo"],
                    "producto": r["producto"],
                    "cantidad": float(r["cantidad"] or 0),
                    "stock_final": float(r["stock_final"] or 0),
                    "referencia": r["referencia"],
                    "usuario": r["usuario"],
                }
                for r in filas_movs
            ],
            "alertas_stock_bajo": [
                {
                    "id_producto": r["id_producto"],
                    "codigo": r["codigo"],
                    "producto": r["nombre"],
                    "stock": float(r["stock"] or 0),
                    "stock_minimo": float(r["stock_minimo"] or 0),
                }
                for r in filas_alertas
            ],
        }

        # d) Bitácora de seguridad (últimos 20 eventos del día en auditoria)
        filas_auditoria = con.execute(
            """SELECT a.id_auditoria,
                      a.fecha,
                      COALESCE(u.username, '—') AS usuario,
                      a.accion,
                      COALESCE(a.detalle, '') AS detalle
               FROM auditoria a
               LEFT JOIN usuarios u ON u.id_usuario = a.id_usuario
               WHERE date(a.fecha) = ?
               ORDER BY a.id_auditoria DESC
               LIMIT 20""",
            (hoy,),
        ).fetchall()

        bitacora_seguridad = [
            {
                "id_auditoria": r["id_auditoria"],
                "fecha": r["fecha"],
                "usuario": r["usuario"],
                "accion": r["accion"],
                "detalle": r["detalle"],
            }
            for r in filas_auditoria
        ]

        return {
            "ok": True,
            "modo_conexion": "READ_ONLY",
            "empresa": {
                "nit": emp["nit"] if emp else "",
                "razon_social": emp["razon_social"] if emp else "Bill Zen ERP",
            },
            "generado_en": datetime.now().strftime(_FORMATO_FECHA),
            "kpis_dia": kpis_dia,
            "ventas_por_cajero": ventas_por_cajero,
            "movimientos_stock_hoy": movimientos_stock_hoy,
            "bitacora_seguridad": bitacora_seguridad,
        }
    finally:
        con.close()


# ==============================================================================
# 4. REDIRECCIÓN AUTOMÁTICA SI EL DISPOSITIVO NO TIENE LA APP KOTLIN INSTALADA
# ==============================================================================
_HTML_REDIRECCION_DESCARGA = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<meta http-equiv="refresh" content="2;url={URL_DESCARGA_APP}">
<title>Bill Zen · Descargar App Móvil</title>
<style>
  :root {{
    --verde: #1F5C46; --verde-osc: #123829; --beige: #F5EFE3;
    --beige-osc: #E8DCC4; --dorado: #C9A646; --blanco: #FFFFFF;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; }}
  body {{ background: var(--beige); color: #2B2B2B; min-height: 100vh; display: flex; flex-direction: column; }}
  header {{ background: var(--verde-osc); color: var(--blanco); padding: 16px 20px; border-bottom: 3px solid var(--dorado); text-align: center; }}
  header h1 {{ font-family: Georgia, serif; font-size: 1.3rem; }}
  header span.zen {{ color: var(--dorado); font-style: italic; }}
  .wrap {{ max-width: 460px; margin: auto; padding: 24px 18px; width: 100%; }}
  .card {{ background: var(--blanco); border: 1px solid var(--beige-osc); border-top: 4px solid var(--dorado); border-radius: 12px; padding: 24px 20px; text-align: center; box-shadow: 0 4px 14px rgba(0,0,0,0.06); }}
  .card h2 {{ font-family: Georgia, serif; color: var(--verde-osc); font-size: 1.15rem; margin-bottom: 10px; }}
  .card p {{ font-size: 0.9rem; color: #555; line-height: 1.45; margin-bottom: 16px; }}
  .spinner {{ width: 34px; height: 34px; border: 4px solid var(--beige-osc); border-top-color: var(--verde); border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 14px; }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  .btn {{ display: block; width: 100%; padding: 12px 16px; border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 0.95rem; margin-top: 10px; }}
  .btn-primario {{ background: var(--verde); color: var(--blanco); }}
  .btn-secundario {{ background: var(--dorado); color: #121212; }}
</style>
</head>
<body>
<header>
  <h1>Bill <span class="zen">Zen</span> · Auditoría Móvil</h1>
</header>
<div class="wrap">
  <div class="card">
    <div class="spinner"></div>
    <h2>Requiere la App Oficial Bill Zen</h2>
    <p>
      Este código QR es exclusivo para vincular la aplicación móvil <b>Bill Zen App (Android / Kotlin)</b>.
      No se detectó la aplicación en tu dispositivo; te estamos redirigiendo al portal oficial de descarga...
    </p>
    <a class="btn btn-primario" href="{URL_DESCARGA_APP}">⬇ Ir a Descargar Bill Zen App</a>
    <a class="btn btn-secundario" href="{URL_LOGIN_PORTAL}">🔑 Iniciar sesión en Bill Zen Web</a>
  </div>
</div>
<script>
  // Intenta despertar la app nativa en Kotlin mediante deep-link; si no está instalada,
  // redirige automáticamente a la sección #descargar del portal (que valida sesión o envía a registro/login).
  (function() {{
    setTimeout(function() {{
      window.location.replace("{URL_DESCARGA_APP}");
    }}, 1200);
  }})();
</script>
</body>
</html>
"""


# ==============================================================================
# 5. MANEJADOR HTTP NATIVO (SOLO LECTURA + 2 ENDPOINTS DE API)
# ==============================================================================
class _ManejadorMovilHTTP(BaseHTTPRequestHandler):
    server_version = "BillZenMobileAudit/1.0"

    def log_message(self, format, *args):
        # Silencia logs en consola para no penalizar I/O ni ensuciar salida en Windows
        return

    def _enviar_json(self, status: int, payload: dict):
        cuerpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_OPTIONS(self):
        self._enviar_json(int(HTTPStatus.OK), {"ok": True})

    def do_GET(self):
        parsed = urlparse(self.path)
        ruta = parsed.path.rstrip("/") or "/"

        if ruta == "/":
            cuerpo = _HTML_REDIRECCION_DESCARGA.encode("utf-8")
            self.send_response(int(HTTPStatus.OK))
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cuerpo)
            return

        if ruta == "/api/movil/auditoria-dia":
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                self._enviar_json(
                    int(HTTPStatus.UNAUTHORIZED),
                    {"ok": False, "error": "Falta el encabezado Authorization: Bearer <session_token>."},
                )
                return
            token = auth[7:].strip()
            sesion = validar_session_token(token)
            if not sesion:
                self._enviar_json(
                    int(HTTPStatus.UNAUTHORIZED),
                    {"ok": False, "error": "Sesión móvil inválida, expirada o revocada."},
                )
                return
            try:
                datos = obtener_auditoria_dia_ro()
                self._enviar_json(int(HTTPStatus.OK), datos)
            except Exception as exc:
                self._enviar_json(
                    int(HTTPStatus.INTERNAL_SERVER_ERROR),
                    {"ok": False, "error": f"Error consultando auditoría en modo solo lectura: {exc}"},
                )
            return

        self._enviar_json(
            int(HTTPStatus.NOT_FOUND),
            {"ok": False, "error": "Endpoint no encontrado. Solo lectura habilitada."},
        )

    def do_POST(self):
        parsed = urlparse(self.path)
        ruta = parsed.path.rstrip("/")

        if ruta != "/api/movil/login":
            self._enviar_json(
                int(HTTPStatus.METHOD_NOT_ALLOWED),
                {"ok": False, "error": "Operación no permitida. El módulo móvil es estrictamente de solo lectura."},
            )
            return

        try:
            largo = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            largo = 0
        if largo <= 0 or largo > 16384:
            self._enviar_json(
                int(HTTPStatus.BAD_REQUEST),
                {"ok": False, "error": "Cuerpo de solicitud inválido."},
            )
            return

        try:
            raw = self.rfile.read(largo)
            datos = json.loads(raw.decode("utf-8"))
        except Exception:
            self._enviar_json(
                int(HTTPStatus.BAD_REQUEST),
                {"ok": False, "error": "JSON mal formado."},
            )
            return

        ip_remota = self.headers.get("CF-Connecting-IP") or self.client_address[0]
        status, resp = autenticar_login_movil(
            pairing_token=str(datos.get("pairing_token") or ""),
            username=str(datos.get("username") or ""),
            password=str(datos.get("password") or ""),
            ip_origen=ip_remota,
        )
        self._enviar_json(status, resp)

    def do_PUT(self):
        self._enviar_json(int(HTTPStatus.FORBIDDEN), {"ok": False, "error": "Modo solo lectura: escritura prohibida."})

    def do_DELETE(self):
        self._enviar_json(int(HTTPStatus.FORBIDDEN), {"ok": False, "error": "Modo solo lectura: eliminación prohibida."})

    def do_PATCH(self):
        self._enviar_json(int(HTTPStatus.FORBIDDEN), {"ok": False, "error": "Modo solo lectura: edición prohibida."})


# ==============================================================================
# 6. GESTIÓN DEL MICRO-SERVIDOR EN HILO SECUNDARIO Y TÚNEL CLOUDFLARED
# ==============================================================================
def obtener_ip_local() -> str:
    """Detecta la IP privada LAN del equipo para acceso por Wi-Fi local como respaldo."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


class _ServidorExclusivoHTTP(ThreadingHTTPServer):
    """Evita que en Windows dos procesos hagan bind simultáneo al mismo puerto (SO_REUSEADDR)."""
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except OSError:
                pass
        super().server_bind()


def iniciar_servidor_movil(puerto: int = PUERTO_DEFECTO) -> int:
    """Inicia el micro-servidor HTTP en un hilo daemon si aún no está corriendo."""
    global _SERVIDOR_HTTP, _HILO_SERVIDOR, _PUERTO_ACTIVO
    with _LOCK:
        if _SERVIDOR_HTTP is not None and _HILO_SERVIDOR is not None and _HILO_SERVIDOR.is_alive():
            return _PUERTO_ACTIVO

        for p in (puerto, 0):
            try:
                srv = _ServidorExclusivoHTTP(("0.0.0.0", p), _ManejadorMovilHTTP)
                _SERVIDOR_HTTP = srv
                _PUERTO_ACTIVO = srv.server_address[1]
                _HILO_SERVIDOR = threading.Thread(
                    target=srv.serve_forever,
                    name="BillZenMobileHTTP",
                    daemon=True,
                )
                _HILO_SERVIDOR.start()
                break
            except OSError:
                continue
        return _PUERTO_ACTIVO


def _buscar_binario_cloudflared() -> str | None:
    """Busca `cloudflared` en PATH o en la carpeta `assets/` del proyecto."""
    en_path = shutil.which("cloudflared") or shutil.which("cloudflared.exe")
    if en_path:
        return en_path
    base = Path(__file__).resolve().parent.parent
    for candidato in (
        base / "assets" / "cloudflared.exe",
        base / "cloudflared.exe",
    ):
        if candidato.is_file():
            return str(candidato)
    return None


def iniciar_tunel_cloudflared(forzar_reinicio: bool = False) -> None:
    """Ejecuta `cloudflared tunnel --url http://127.0.0.1:<puerto>` oculto (`CREATE_NO_WINDOW`)
    en un hilo daemon y captura automáticamente la URL `https://*.trycloudflare.com`."""
    global _PROCESO_TUNEL, _HILO_TUNEL, _URL_REMOTA, _ESTADO_TUNEL
    puerto = iniciar_servidor_movil()

    with _LOCK:
        if _PROCESO_TUNEL is not None and _PROCESO_TUNEL.poll() is None and not forzar_reinicio:
            return
        if _PROCESO_TUNEL is not None:
            try:
                _PROCESO_TUNEL.terminate()
            except Exception:
                pass
            _PROCESO_TUNEL = None
        _URL_REMOTA = ""

    binario = _buscar_binario_cloudflared()
    if not binario:
        with _LOCK:
            _ESTADO_TUNEL = "Solo Red Local (instala cloudflared para acceso fuera de la red Wi-Fi)"
        return

    with _LOCK:
        _ESTADO_TUNEL = "Conectando túnel HTTPS..."

    def _worker_tunel():
        global _PROCESO_TUNEL, _URL_REMOTA, _ESTADO_TUNEL
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        cmd = [binario, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{puerto}"]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=flags,
            )
            with _LOCK:
                _PROCESO_TUNEL = proc

            patron = re.compile(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com")
            if proc.stdout:
                for linea in proc.stdout:
                    m = patron.search(linea)
                    if m:
                        with _LOCK:
                            _URL_REMOTA = m.group(0)
                            _ESTADO_TUNEL = "Conectado (Túnel HTTPS activo)"
            if proc.poll() is not None and not _URL_REMOTA:
                with _LOCK:
                    _ESTADO_TUNEL = "Solo Red Local (túnel remoto desconectado)"
        except Exception:
            with _LOCK:
                _ESTADO_TUNEL = "Solo Red Local (no se pudo iniciar cloudflared)"

    _HILO_TUNEL = threading.Thread(target=_worker_tunel, name="BillZenCloudflared", daemon=True)
    _HILO_TUNEL.start()


def estado_servidor_movil() -> dict:
    """Devuelve el estado actual del servidor HTTP, túnel remoto, URLs y sesiones activas."""
    puerto = iniciar_servidor_movil()
    ip_lan = obtener_ip_local()
    local_url = f"http://{ip_lan}:{puerto}"
    with _LOCK:
        remota = _URL_REMOTA
        estado = _ESTADO_TUNEL
    return {
        "puerto": puerto,
        "local_url": local_url,
        "remote_url": remota,
        "estado_tunel": estado,
        "sesiones_activas": contar_sesiones_activas(),
    }


@requiere_rol(ROL_ADMIN)
def generar_paquete_qr_emparejamiento() -> dict:
    """Genera el payload JSON estricto del QR (sin iniciar sesión) y su imagen PIL en memoria.
    Si un dispositivo sin la app Kotlin escanea el QR con su cámara nativa, tanto la URL de
    respaldo como el endpoint raíz `GET /` del servidor lo redirigen automáticamente a
    `https://bill-zen-users.vercel.app/#descargar`."""
    import qrcode
    from PIL import Image

    iniciar_servidor_movil()
    if _ESTADO_TUNEL == "Detenido":
        iniciar_tunel_cloudflared()

    est = estado_servidor_movil()
    emp = consultar_uno("SELECT nit, razon_social FROM empresa WHERE id_empresa = 1") or {}
    token_qr, exp_ts = generar_pairing_token()

    payload_qr = {
        "nit": emp.get("nit") or "",
        "empresa": emp.get("razon_social") or "Bill Zen ERP",
        "remote_url": est["remote_url"] or URL_DESCARGA_APP,
        "local_url": est["local_url"],
        "pairing_token": token_qr,
    }
    contenido_json = json.dumps(payload_qr, ensure_ascii=False, separators=(",", ":"))

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=7,
        border=2,
    )
    qr.add_data(contenido_json)
    qr.make(fit=True)
    img_pil: Image.Image = qr.make_image(fill_color="#123829", back_color="#FFFFFF").convert("RGB")

    buf = io.BytesIO()
    img_pil.save(buf, format="PNG")

    return {
        "payload": payload_qr,
        "json_str": contenido_json,
        "imagen_pil": img_pil,
        "png_bytes": buf.getvalue(),
        "expira_en_ts": exp_ts,
        "ttl_segundos": TTL_PAIRING_SEG,
        "estado_tunel": est["estado_tunel"],
        "sesiones_activas": est["sesiones_activas"],
    }
