import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["BILLZEN_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from database.conexion import consultar, transaccion
from database.setup_db import inicializar_base_datos
from logica import (
    auth_logic,
    empresa_logic,
    facturacion_logic as fl,
    licencia,
    mobile_server as ms,
    productos_logic as pl,
    usuarios_logic as ul,
)
from logica.seguridad import ErrorPermiso, ErrorValidacion, Sesion


class PruebasBillZen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inicializar_base_datos()
        licencia.guardar_licencia_local("admin@tiendazen.co", licencia.generar_hardware_id(), "ultra")
        empresa_logic.registrar_empresa({"nit": "900.123.456-7", "razon_social": "Tienda Zen"})
        auth_logic.registrar_primer_admin("admin", "Administrador", "Clave1234", "Clave1234")
        auth_logic.iniciar_sesion("admin", "Clave1234")
        cats = {c["nombre"]: c for c in pl.listar_categorias()}
        pl.guardar_producto({"codigo": "L1", "nombre": "Leche", "id_categoria": cats["Canasta familiar"]["id_categoria"],
                             "costo": "2.000", "precio": "3.000", "stock_inicial": "10", "stock_minimo": "2"})
        pl.guardar_producto({"codigo": "G1", "nombre": "Gaseosa", "id_categoria": cats["Bebidas"]["id_categoria"],
                             "costo": "1.500", "precio": "2.380", "stock_inicial": "5"})
        ul.crear_usuario("caja1", "Cajero Uno", "Cajero123", "Cajero123")
        ul.crear_usuario("caja2", "Cajero Dos", "Cajero123", "Cajero123")

    def test_segundo_admin_bloqueado(self):
        with self.assertRaises(ErrorValidacion):
            auth_logic.registrar_primer_admin("otro", "X", "Clave1234", "Clave1234")

    def test_recuperacion_password_admin_con_preguntas(self):
        p1, p2 = auth_logic.PREGUNTAS_PREDEFINIDAS[0], auth_logic.PREGUNTAS_PREDEFINIDAS[1]
        # No permite elegir dos veces la misma pregunta
        with self.assertRaises(ErrorValidacion):
            auth_logic.guardar_preguntas_admin(p1, "Firulais", p1, "Medellín")

        auth_logic.guardar_preguntas_admin(p1, "Firulais", p2, "Bogotá D.C.")
        self.assertTrue(auth_logic.tiene_preguntas_admin())
        self.assertEqual(auth_logic.obtener_preguntas_recuperacion("admin"), [p1, p2])

        # Un cajero no puede recuperar clave por preguntas de admin
        with self.assertRaises(ErrorValidacion):
            auth_logic.obtener_preguntas_recuperacion("caja1")

        # Respuesta incorrecta lanza ErrorValidacion
        with self.assertRaises(ErrorValidacion):
            auth_logic.recuperar_password_admin("admin", "Incorrecta", "Bogota D.C.", "Nueva1234", "Nueva1234")

        # Respuesta correcta (incluso sin tildes y en minúsculas) restablece la contraseña
        auth_logic.recuperar_password_admin("admin", "  firulais ", "bogota d.c.", "Nueva1234", "Nueva1234")
        auth_logic.iniciar_sesion("admin", "Nueva1234")
        # Devolver a la clave original para el resto de pruebas
        auth_logic.recuperar_password_admin("admin", "Firulais", "Bogotá D.C.", "Clave1234", "Clave1234")
        # Sin sesión activa no permite sobrescribir las preguntas ya existentes
        Sesion.cerrar()
        with self.assertRaises(ErrorPermiso):
            auth_logic.guardar_preguntas_admin(p1, "Otro", p2, "Otra", username="admin")
        auth_logic.iniciar_sesion("admin", "Clave1234")

    def test_factura_descuenta_stock_e_iva(self):
        leche = pl.buscar_por_codigo("L1")
        gaseosa = pl.buscar_por_codigo("G1")
        self.assertEqual(leche["precio"], 3000)
        self.assertEqual(gaseosa["precio"], 2380)
        # No permite guardar un producto con precio menor al costo del proveedor
        with self.assertRaises(ErrorValidacion):
            pl.guardar_producto({
                "codigo": "PERDIDA",
                "nombre": "Producto a pérdida",
                "id_categoria": 1,
                "costo": "3.000",
                "precio": "2.500",
            })
        antes = leche["stock"]
        idf = fl.emitir_factura([{"id_producto": leche["id_producto"], "cantidad": 2},
                                 {"id_producto": gaseosa["id_producto"], "cantidad": 1}], "Efectivo", 10000)
        f = fl.obtener_factura(idf)
        self.assertEqual(pl.buscar_por_codigo("L1")["stock"], antes - 2)

    def test_stock_insuficiente_hace_rollback(self):
        leche = pl.buscar_por_codigo("L1")
        gaseosa = pl.buscar_por_codigo("G1")
        with self.assertRaises(ErrorValidacion):
            fl.emitir_factura([{"id_producto": leche["id_producto"], "cantidad": 1},
                               {"id_producto": gaseosa["id_producto"], "cantidad": 999}], "Tarjeta")
        self.assertEqual(pl.buscar_por_codigo("L1")["stock"], leche["stock"])

    def test_cajero_sin_permisos_admin(self):
        admin = Sesion.usuario
        auth_logic.iniciar_sesion("caja1", "Cajero123")
        with self.assertRaises(ErrorPermiso):
            ul.listar_usuarios()
        with self.assertRaises(ErrorPermiso):
            pl.registrar_entrada(1, 5)
        self.assertIn("costo", pl.listar_productos()[0])  # puede ver el costo...
        with self.assertRaises(ErrorPermiso):              # ...pero no modificar productos
            pl.guardar_producto({"codigo": "X", "nombre": "X", "id_categoria": 1, "precio": "100"})
        with self.assertRaises(ErrorPermiso):
            pl.cambiar_estado_producto(1, False)
        # Si alguien intenta escalar privilegios en memoria alterando id_rol, el HMAC invalida la sesión
        Sesion.usuario["id_rol"] = 1
        with self.assertRaises(ErrorPermiso):
            ul.listar_usuarios()
        Sesion.iniciar(admin)

    def test_entrada_suma_stock(self):
        g = pl.buscar_por_codigo("G1")
        nuevo = pl.registrar_entrada(g["id_producto"], 4, "Compra")
        self.assertEqual(nuevo, g["stock"] + 4)

    def test_filtro_productos_por_categoria_e_inactivos(self):
        cats = {c["nombre"]: c["id_categoria"] for c in pl.listar_categorias()}
        bebidas = pl.listar_productos(id_categoria=cats["Bebidas"])
        self.assertEqual(len(bebidas), 1)
        self.assertEqual(bebidas[0]["codigo"], "G1")

        # Desactivar y filtrar inactivos
        id_g1 = bebidas[0]["id_producto"]
        pl.cambiar_estado_producto(id_g1, False)
        self.assertEqual(len(pl.listar_productos(id_categoria=cats["Bebidas"], solo_activos=True)), 0)
        inactivos = pl.listar_productos(solo_inactivos=True)
        self.assertEqual(len(inactivos), 1)
        self.assertEqual(inactivos[0]["id_producto"], id_g1)
        pl.cambiar_estado_producto(id_g1, True)

    def test_bloqueo_por_intentos(self):
        admin = Sesion.usuario
        for _ in range(4):
            with self.assertRaises(ErrorValidacion):
                auth_logic.iniciar_sesion("caja2", "mala")
        with self.assertRaises(ErrorValidacion) as e:
            auth_logic.iniciar_sesion("caja2", "mala")
        self.assertIn("bloqueada", str(e.exception))
        Sesion.iniciar(admin)

    def test_auditoria_movil_qr_seguridad_y_readonly(self):
        import json
        import sqlite3
        import time
        import urllib.error
        import urllib.request

        auth_logic.iniciar_sesion("admin", "Clave1234")

        # 1. El QR solo contiene el JSON de descubrimiento y pairing_token que expira en 5 min
        paquete = ms.generar_paquete_qr_emparejamiento()
        payload = paquete["payload"]
        self.assertEqual(
            set(payload.keys()),
            {"nit", "empresa", "remote_url", "local_url", "pairing_token"},
        )
        self.assertEqual(payload["nit"], "900.123.456-7")
        self.assertEqual(payload["empresa"], "Tienda Zen")

        t_base = time.time()
        tok_qr, _ = ms.generar_pairing_token(ahora=t_base)
        self.assertTrue(ms.validar_pairing_token(tok_qr, ahora=t_base + 299))
        self.assertFalse(ms.validar_pairing_token(tok_qr, ahora=t_base + 301))
        self.assertFalse(ms.validar_pairing_token(tok_qr + "x", ahora=t_base + 10))

        # 2. Conexión SQLite del túnel 100% Read-Only (bloquea INSERT, UPDATE, DELETE a nivel motor)
        con_ro = ms.conectar_ro()
        try:
            with self.assertRaises(sqlite3.OperationalError):
                con_ro.execute("DELETE FROM productos")
            with self.assertRaises(sqlite3.OperationalError):
                con_ro.execute("UPDATE empresa SET razon_social = 'Hack'")
            with self.assertRaises(sqlite3.OperationalError):
                con_ro.execute("INSERT INTO categorias (nombre) VALUES ('Ilegal')")
        finally:
            con_ro.close()

        # 3. Doble candado en POST /api/movil/login: Cajero (id_rol == 2) rechazado con HTTP 403 + auditoría
        puerto = ms.iniciar_servidor_movil()
        base_http = f"http://127.0.0.1:{puerto}"

        # Si un dispositivo sin la app Kotlin abre GET / en el navegador, redirige a #descargar
        with urllib.request.urlopen(f"{base_http}/", timeout=5) as r_root:
            html_root = r_root.read().decode("utf-8")
            self.assertIn("https://bill-zen-users.vercel.app/#descargar", html_root)
            self.assertIn("https://bill-zen-users.vercel.app/login.html", html_root)

        def _post_json(ruta, datos):
            req = urllib.request.Request(
                f"{base_http}{ruta}",
                data=json.dumps(datos).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                return err.code, json.loads(err.read().decode("utf-8"))

        status_caj, resp_caj = _post_json(
            "/api/movil/login",
            {"pairing_token": tok_qr, "username": "caja1", "password": "Cajero123"},
        )
        self.assertEqual(status_caj, 403)
        self.assertFalse(resp_caj["ok"])
        eventos_denegados = consultar(
            "SELECT * FROM auditoria WHERE accion = 'ACCESO_MOVIL_DENEGADO_ROL' ORDER BY id_auditoria DESC LIMIT 1"
        )
        self.assertEqual(len(eventos_denegados), 1)
        self.assertIn("caja1", eventos_denegados[0]["detalle"])

        # 4. Login exitoso como Administrador (id_rol == 1) -> devuelve session_token de 12 horas
        status_adm, resp_adm = _post_json(
            "/api/movil/login",
            {"pairing_token": tok_qr, "username": "admin", "password": "Clave1234"},
        )
        self.assertEqual(status_adm, 200)
        self.assertTrue(resp_adm["ok"])
        self.assertEqual(resp_adm["expires_in"], 43200)
        session_token = resp_adm["session_token"]

        # 5. GET /api/movil/auditoria-dia devuelve JSON consolidado en modo READ_ONLY
        req_aud = urllib.request.Request(
            f"{base_http}/api/movil/auditoria-dia",
            headers={"Authorization": f"Bearer {session_token}"},
            method="GET",
        )
        with urllib.request.urlopen(req_aud, timeout=5) as r_aud:
            self.assertEqual(r_aud.status, 200)
            aud_json = json.loads(r_aud.read().decode("utf-8"))

        self.assertTrue(aud_json["ok"])
        self.assertEqual(aud_json["modo_conexion"], "READ_ONLY")
        for seccion in ("kpis_dia", "ventas_por_cajero", "movimientos_stock_hoy", "bitacora_seguridad"):
            self.assertIn(seccion, aud_json)
        self.assertIn("ultimos_movimientos", aud_json["movimientos_stock_hoy"])
        self.assertIn("alertas_stock_bajo", aud_json["movimientos_stock_hoy"])

        # 6. Revocación inmediata de sesiones móviles
        self.assertGreaterEqual(ms.contar_sesiones_activas(), 1)
        ms.revocar_sesiones_moviles()
        self.assertEqual(ms.contar_sesiones_activas(), 0)
        with self.assertRaises(urllib.error.HTTPError) as err_rev:
            urllib.request.urlopen(req_aud, timeout=5)
        self.assertEqual(err_rev.exception.code, 401)

    def test_licencia_hardware_id_anticlones_y_feature_toggling(self):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        # 1. Hardware ID determinista de 64 caracteres hex (SHA-256)
        hw1 = licencia.generar_hardware_id()
        hw2 = licencia.generar_hardware_id(forzar_recalculo=True)
        self.assertEqual(len(hw1), 64)
        self.assertEqual(hw1, hw2)

        # 2. Sin licencia en SQLite -> PRIMER_USO bloqueado
        with transaccion() as con:
            con.execute("DELETE FROM licencia_sistema")
        est_vacio = licencia.verificar_licencia_local()
        self.assertFalse(est_vacio["valido"])
        self.assertEqual(est_vacio["motivo"], "PRIMER_USO")

        # 3. Activación online contra endpoint simulado POST /api/licencia/activar
        recibidos = []

        class _MockVercelHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def do_POST(self):
                largo = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(largo).decode("utf-8"))
                recibidos.append(body)
                if body.get("password") != "ClaveWeb123":
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False, "error": "Credenciales inválidas"}).encode("utf-8"))
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"ok": True, "plan_adquirido": "basico"}).encode("utf-8")
                )

        srv = HTTPServer(("127.0.0.1", 0), _MockVercelHandler)
        hilo = threading.Thread(target=srv.serve_forever, daemon=True)
        hilo.start()
        url_original = licencia.URL_API_LICENCIA
        try:
            licencia.URL_API_LICENCIA = f"http://127.0.0.1:{srv.server_address[1]}/api/licencia/activar"
            with self.assertRaises(ErrorValidacion):
                licencia.activar_licencia_online("cliente@empresa.com", "ClaveIncorrecta", hw1)

            res_ok = licencia.activar_licencia_online("cliente@empresa.com", "ClaveWeb123", hw1)
            self.assertTrue(res_ok["valido"])
            self.assertEqual(res_ok["plan"], "basico")
            self.assertEqual(recibidos[-1]["hardware_id"], hw1)
        finally:
            licencia.URL_API_LICENCIA = url_original
            srv.shutdown()
            srv.server_close()

        # 4. Feature Toggling según plan ('basico' vs 'standart' vs 'ultra')
        self.assertTrue(licencia.permite_modulo("facturacion", "basico"))
        self.assertTrue(licencia.permite_modulo("usuarios", "basico"))
        self.assertFalse(licencia.permite_modulo("contabilidad", "basico"))
        self.assertFalse(licencia.permite_modulo("reportes", "basico"))
        self.assertFalse(licencia.permite_modulo("auditoria_movil", "basico"))
        self.assertFalse(licencia.tiene_facturacion_electronica("basico"))
        self.assertEqual(licencia.max_cajeros_permitidos("basico"), 1)

        # En Plan Básico ya hay cajeros activos, por lo que no permite crear otro más
        with self.assertRaises(ErrorValidacion):
            ul.crear_usuario("caja_extra", "Cajero Extra", "Cajero123", "Cajero123")

        self.assertTrue(licencia.permite_modulo("contabilidad", "standart"))
        self.assertTrue(licencia.permite_modulo("reportes", "standart"))
        self.assertTrue(licencia.tiene_facturacion_electronica("standart"))
        self.assertIsNone(licencia.max_cajeros_permitidos("standart"))
        self.assertFalse(licencia.permite_modulo("auditoria_movil", "standart"))
        self.assertTrue(licencia.permite_modulo("auditoria_movil", "ultra"))

        # 5. Anticlones USB: si el hw_id_hash en SQLite pertenece a otro PC, bloquea de inmediato
        with transaccion() as con:
            con.execute("UPDATE licencia_sistema SET hw_id_hash = ?", ("0" * 64,))
        est_clon = licencia.verificar_licencia_local()
        self.assertFalse(est_clon["valido"])
        self.assertEqual(est_clon["motivo"], "HARDWARE_DIFERENTE")

        # 6. Anti-tampering SQLite: si alguien edita plan_adquirido='ultra' en SQLite manualmente, invalida firma
        licencia.guardar_licencia_local("cliente@empresa.com", hw1, "basico")
        with transaccion() as con:
            con.execute("UPDATE licencia_sistema SET plan_adquirido = 'ultra' WHERE id_licencia = 1")
        est_tamper = licencia.verificar_licencia_local()
        self.assertFalse(est_tamper["valido"])
        self.assertEqual(est_tamper["motivo"], "LICENCIA_ADULTERADA")

        # Restaurar licencia Ultra válida
        licencia.guardar_licencia_local("cliente@empresa.com", hw1, "ultra")
        self.assertTrue(licencia.verificar_licencia_local()["valido"])


if __name__ == "__main__":
    unittest.main()
