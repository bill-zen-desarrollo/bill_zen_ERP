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
    reportes_logic as rl,
    usuarios_logic as ul,
)
from logica.seguridad import ErrorPermiso, ErrorValidacion, Sesion


class PruebasBillZen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inicializar_base_datos()
        licencia.guardar_licencia_local("admin@tiendazen.co", licencia.generar_hardware_id(), "ultra")
        empresa_logic.registrar_empresa({"nit": "900.123.456-7", "razon_social": "Tienda Zen"})
        auth_logic.registrar_primer_admin(password="Clave1234", confirmacion="Clave1234")
        auth_logic.iniciar_sesion("administrador", "Clave1234")
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
        # Tampoco permite iniciar sesión con NIT ni correo, solo con el username 'administrador'
        with self.assertRaises(ErrorValidacion):
            auth_logic.iniciar_sesion("900.123.456-7", "Clave1234")
        with self.assertRaises(ErrorValidacion):
            auth_logic.iniciar_sesion("admin@tiendazen.co", "Clave1234")

    def test_recuperacion_password_admin_con_preguntas(self):
        p1, p2 = auth_logic.PREGUNTAS_PREDEFINIDAS[0], auth_logic.PREGUNTAS_PREDEFINIDAS[1]
        # No permite elegir dos veces la misma pregunta
        with self.assertRaises(ErrorValidacion):
            auth_logic.guardar_preguntas_admin(p1, "Firulais", p1, "Medellín")

        auth_logic.guardar_preguntas_admin(p1, "Firulais", p2, "Bogotá D.C.")
        self.assertTrue(auth_logic.tiene_preguntas_admin())
        self.assertEqual(auth_logic.obtener_preguntas_recuperacion("administrador"), [p1, p2])

        # Un cajero no puede recuperar clave por preguntas de admin
        with self.assertRaises(ErrorValidacion):
            auth_logic.obtener_preguntas_recuperacion("caja1")

        # Respuesta incorrecta lanza ErrorValidacion
        with self.assertRaises(ErrorValidacion):
            auth_logic.recuperar_password_admin("administrador", "Incorrecta", "Bogota D.C.", "Nueva1234", "Nueva1234")

        # Respuesta correcta (incluso sin tildes y en minúsculas) restablece la clave con 5 dígitos numéricos
        auth_logic.recuperar_password_admin("administrador", "  firulais ", "bogota d.c.", "12345", "12345")
        auth_logic.iniciar_sesion("administrador", "12345")
        # Devolver a la clave original para el resto de pruebas
        auth_logic.recuperar_password_admin("administrador", "Firulais", "Bogotá D.C.", "Clave1234", "Clave1234")
        # Sin sesión activa no permite sobrescribir las preguntas ya existentes
        Sesion.cerrar()
        with self.assertRaises(ErrorPermiso):
            auth_logic.guardar_preguntas_admin(p1, "Otro", p2, "Otra", username="administrador")
        auth_logic.iniciar_sesion("administrador", "Clave1234")

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
        g = pl.listar_productos("G1")[0]
        gastos_antes = sum(x["valor"] for x in rl.listar_gastos("2000-01-01", "2099-12-31"))
        nuevo = pl.registrar_entrada(g["id_producto"], 4, "Compra")
        self.assertEqual(nuevo, g["stock"] + 4)
        gastos_despues = sum(x["valor"] for x in rl.listar_gastos("2000-01-01", "2099-12-31"))
        self.assertEqual(gastos_despues - gastos_antes, g["costo"] * 4)

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

        auth_logic.iniciar_sesion("administrador", "Clave1234")

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
            {"pairing_token": tok_qr, "username": "administrador", "password": "Clave1234"},
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
                    json.dumps({
                        "ok": True,
                        "plan_adquirido": "basico",
                        "nit": "900.123.456-7",
                        "razon_social": "Tienda Zen",
                        "email": "cliente@empresa.com",
                    }).encode("utf-8")
                )

        srv = HTTPServer(("127.0.0.1", 0), _MockVercelHandler)
        hilo = threading.Thread(target=srv.serve_forever, daemon=True)
        hilo.start()
        url_original = licencia.URL_API_LICENCIA
        try:
            licencia.URL_API_LICENCIA = f"http://127.0.0.1:{srv.server_address[1]}/api/licencia/activar"
            # No permite activar con correo electrónico, únicamente con NIT
            with self.assertRaises(ErrorValidacion):
                licencia.activar_licencia_online("cliente@empresa.com", "ClaveWeb123", hw1)
            with self.assertRaises(ErrorValidacion):
                licencia.activar_licencia_online("900.123.456-7", "ClaveIncorrecta", hw1)

            res_ok = licencia.activar_licencia_online("900.123.456-7", "ClaveWeb123", hw1)
            self.assertTrue(res_ok["valido"])
            self.assertEqual(res_ok["plan"], "basico")
            self.assertEqual(recibidos[-1]["hardware_id"], hw1)
            self.assertEqual(recibidos[-1]["nit"], "900.123.456-7")
            self.assertNotIn("email", recibidos[-1])
            emp_sinc = empresa_logic.obtener_empresa()
            self.assertEqual(emp_sinc["nit"], "900.123.456-7")
            self.assertEqual(emp_sinc["razon_social"], "Tienda Zen")
            self.assertEqual(emp_sinc["correo"], "cliente@empresa.com")
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

    def test_contabilidad_egresos_cuentas_por_pagar_flujo_caja_e_iva(self):
        from datetime import date

        auth_logic.iniciar_sesion("administrador", "Clave1234")
        hoy = date.today().isoformat()
        pyg_base = rl.estado_resultados(hoy, hoy)
        flujo_base = rl.flujo_caja_y_bancos(hoy, hoy)

        # 1. Registrar recibo de servicio público PENDIENTE por pagar
        rl.registrar_gasto(
            fecha=hoy,
            concepto="Recibo de Energía Enel",
            categoria="Servicios públicos (Agua/Luz/Gas/Internet)",
            valor="180.000",
            proveedor="Enel Codensa",
            metodo_pago="Transferencia",
            comprobante="ENEL-9921",
            estado="PENDIENTE",
        )
        pendientes = rl.listar_gastos(hoy, hoy, estado="PENDIENTE", texto="Enel")
        self.assertEqual(len(pendientes), 1)
        id_gasto = pendientes[0]["id_gasto"]

        # 2. Estado de resultados refleja cuentas por pagar y punto de equilibrio
        pyg_antes = rl.estado_resultados(hoy, hoy)
        self.assertEqual(pyg_antes["gastos_pendientes"] - pyg_base["gastos_pendientes"], 180000)
        self.assertEqual(pyg_antes["conteo_pendientes"] - pyg_base["conteo_pendientes"], 1)
        self.assertGreaterEqual(pyg_antes["punto_equilibrio"], 0)

        # 3. Marcar como PAGADO actualiza estado y alimenta el flujo de caja/bancos
        rl.marcar_gasto_pagado(id_gasto, metodo_pago="Efectivo")
        pyg_despues = rl.estado_resultados(hoy, hoy)
        self.assertEqual(pyg_despues["gastos_pendientes"] - pyg_base["gastos_pendientes"], 0)
        self.assertEqual(pyg_despues["gastos_pagados"] - pyg_base["gastos_pagados"], 180000)

        flujo = rl.flujo_caja_y_bancos(hoy, hoy)
        self.assertEqual(flujo["egresos_efectivo"] - flujo_base["egresos_efectivo"], 180000)
        self.assertIn("desglose_por_metodo", flujo)

        # 4. Pedido de stock (460.000) vs Facturación (500.000) => Utilidad neta = +40.000 (sin doble descuento)
        cats = {c["nombre"]: c["id_categoria"] for c in pl.listar_categorias()}
        pl.guardar_producto({
            "codigo": "PED460",
            "nombre": "Producto Pedido 460k",
            "id_categoria": cats["Canasta familiar"],
            "costo": "4.600",
            "precio": "5.000",
            "stock_inicial": 0,
            "stock_minimo": 1,
        })
        prod_ped = pl.listar_productos("PED460")[0]
        pyg_pre_ped = rl.estado_resultados(hoy, hoy)
        flujo_pre_ped = rl.flujo_caja_y_bancos(hoy, hoy)
        pl.registrar_entrada(prod_ped["id_producto"], 100, "Pedido proveedor #1")
        fl.emitir_factura([{"id_producto": prod_ped["id_producto"], "cantidad": 100}], "Efectivo", 500000)
        pyg_post_ped = rl.estado_resultados(hoy, hoy)
        flujo_post_ped = rl.flujo_caja_y_bancos(hoy, hoy)
        self.assertEqual(pyg_post_ped["utilidad_neta"] - pyg_pre_ped["utilidad_neta"], 40000)
        self.assertEqual(flujo_post_ped["saldo_efectivo"] - flujo_pre_ped["saldo_efectivo"], 40000)

        ivas = rl.resumen_iva_dian(hoy, hoy)
        self.assertIsInstance(ivas, list)

        # 4. Cuentas Fijas Mensuales y alertas de vencimiento
        dia_hoy = date.today().day
        id_fijo = rl.guardar_gasto_fijo(
            concepto="Internet Fibra Óptica",
            categoria="Servicios públicos (Agua/Luz/Gas/Internet)",
            valor_estimado="120.000",
            dia_pago=dia_hoy,
            descripcion="Contrato #88412",
            proveedor="Movistar Empresas",
            metodo_pago="Transferencia",
            dias_anticipacion=5,
        )
        alertas = rl.alertas_gastos_fijos()
        self.assertTrue(alertas["hay_alertas"])
        self.assertEqual(alertas["cantidad_alertas"], 1)

        # Pagar la cuenta fija del mes la registra automáticamente en gastos y apaga la alerta del mes
        rl.pagar_gasto_fijo_mes(id_fijo, valor_pagado="122.000", metodo_pago="Transferencia")
        alertas_post = rl.alertas_gastos_fijos()
        self.assertFalse(alertas_post["hay_alertas"])
        gastos_hoy = rl.listar_gastos(hoy, hoy, texto="Internet Fibra")
        self.assertEqual(len(gastos_hoy), 1)
        self.assertEqual(gastos_hoy[0]["valor"], 122000)

    def test_kardex_movimientos_validaciones_kpis_y_sync(self):
        import json

        auth_logic.iniciar_sesion("administrador", "Clave1234")
        cats = {c["nombre"]: c["id_categoria"] for c in pl.listar_categorias()}
        pid = pl.guardar_producto({
            "codigo": "KARDEX01",
            "nombre": "Producto Kardex",
            "id_categoria": cats["Abarrotes"],
            "costo": "1.000",
            "precio": "2.000",
            "stock_inicial": "10",
            "stock_minimo": "4",
        })

        # 1. Validaciones de obligatoriedad de motivo y stock máximo en SALIDA_MERMA
        with self.assertRaises(ErrorValidacion):
            pl.registrar_movimiento_inventario(pid, "SALIDA_MERMA", 2, "")
        with self.assertRaises(ErrorValidacion):
            pl.registrar_movimiento_inventario(pid, "SALIDA_MERMA", 15, "Producto vencido")
        self.assertEqual(pl.buscar_por_codigo("KARDEX01")["stock"], 10)

        # 2. Salida por merma válida (10 -> 7)
        res_merma = pl.registrar_movimiento_inventario(pid, "SALIDA_MERMA", 3, "Empaque roto")
        self.assertEqual(res_merma["previous_stock"], 10)
        self.assertEqual(res_merma["new_stock"], 7)
        self.assertEqual(res_merma["quantity"], 3)
        self.assertEqual(res_merma["diferencia"], -3)

        # 3. Ajuste por conteo físico: obligatorio motivo y no permite conteo igual al actual
        with self.assertRaises(ErrorValidacion):
            pl.registrar_movimiento_inventario(pid, "AJUSTE_CONTEO", 5, "")
        with self.assertRaises(ErrorValidacion):
            pl.registrar_movimiento_inventario(pid, "AJUSTE_CONTEO", 7, "Igual al sistema")

        # Ajuste negativo (7 -> 3, por debajo del mínimo 4 para activar alerta)
        res_aj_neg = pl.registrar_movimiento_inventario(pid, "AJUSTE_CONTEO", 3, "Conteo físico bodega")
        self.assertEqual(res_aj_neg["previous_stock"], 7)
        self.assertEqual(res_aj_neg["new_stock"], 3)
        self.assertEqual(res_aj_neg["quantity"], 4)
        self.assertEqual(res_aj_neg["diferencia"], -4)

        # 4. Devolución (+2: 3 -> 5) y Entrada por compra (+5: 5 -> 10)
        res_dev = pl.registrar_movimiento_inventario(pid, "DEVOLUCION", 2, "Devolución cliente")
        self.assertEqual(res_dev["new_stock"], 5)
        res_ent = pl.registrar_movimiento_inventario(pid, "ENTRADA", 5, "Factura prov 901")
        self.assertEqual(res_ent["new_stock"], 10)

        # 5. Ajuste positivo (10 -> 12)
        res_aj_pos = pl.registrar_movimiento_inventario(pid, "AJUSTE_CONTEO", 12, "Sobrante en conteo")
        self.assertEqual(res_aj_pos["previous_stock"], 10)
        self.assertEqual(res_aj_pos["new_stock"], 12)
        self.assertEqual(res_aj_pos["quantity"], 2)
        self.assertEqual(res_aj_pos["diferencia"], 2)

        # 6. Venta e anulación también generan movimientos Kardex VENTA y DEVOLUCION
        id_fac = fl.emitir_factura([{"id_producto": pid, "cantidad": 9}], "Efectivo", 20000)
        self.assertEqual(pl.buscar_por_codigo("KARDEX01")["stock"], 3)  # ahora en stock bajo (<= 4)

        # 7. KPIs y filtros de Kardex
        kpis = pl.resumen_kpis_inventario()
        self.assertGreaterEqual(kpis["total_unidades"], 3)
        self.assertGreater(kpis["valorizacion"], 0)
        self.assertGreaterEqual(kpis["alertas_stock_bajo"], 1)

        todos = pl.listar_movimientos_kardex(texto="KARDEX01", filtro_tipo="Todos")
        self.assertEqual(len(todos), 7)  # 1 inicial + 5 manuales + 1 venta
        self.assertEqual(pl.contar_movimientos_kardex(texto="KARDEX01", filtro_tipo="Todos"), 7)
        pag1 = pl.listar_movimientos_kardex(texto="KARDEX01", limite=4, offset=0)
        pag2 = pl.listar_movimientos_kardex(texto="KARDEX01", limite=4, offset=4)
        self.assertEqual(len(pag1), 4)
        self.assertEqual(len(pag2), 3)
        self.assertTrue({m["id"] for m in pag1}.isdisjoint({m["id"] for m in pag2}))

        indices_inv = {
            r["name"]
            for r in consultar("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='inventory_movements'")
        }
        self.assertIn("idx_inv_mov_product", indices_inv)
        self.assertIn("idx_inv_mov_created_desc", indices_inv)
        entradas = pl.listar_movimientos_kardex(texto="KARDEX01", filtro_tipo="Entradas")
        self.assertTrue(all(m["movement_type"] in ("ENTRADA", "DEVOLUCION") for m in entradas))
        mermas_aj = pl.listar_movimientos_kardex(texto="KARDEX01", filtro_tipo="Mermas/Ajustes")
        self.assertEqual(len(mermas_aj), 3)
        ventas = pl.listar_movimientos_kardex(texto="KARDEX01", filtro_tipo="Ventas")
        self.assertEqual(len(ventas), 1)
        bajos = pl.listar_movimientos_kardex(texto="KARDEX01", solo_stock_bajo=True)
        self.assertTrue(len(bajos) >= 1 and all(m["es_stock_bajo"] for m in bajos))

        # 8. Cola de sincronización hacia Neon.tech (sync_queue) y marcado como SYNCED
        cola = pl.obtener_cola_sincronizacion("PENDING")
        ids_mov = {m["id"] for m in todos}
        cola_kardex = [q for q in cola if q["table_name"] == "inventory_movements" and q["record_id"] in ids_mov]
        self.assertEqual(len(cola_kardex), 7)
        payload_sample = json.loads(cola_kardex[0]["payload"])
        self.assertEqual(payload_sample["sku"], "KARDEX01")
        self.assertIn("previous_stock", payload_sample)
        self.assertIn("new_stock", payload_sample)

        pl.marcar_movimiento_sincronizado(cola_kardex[0]["id"], exitoso=True)
        mov_sync = consultar("SELECT synced FROM inventory_movements WHERE id = ?", (cola_kardex[0]["record_id"],))[0]
        self.assertEqual(mov_sync["synced"], 1)

        # Limpiar impacto de venta anulando la factura (genera DEVOLUCION)
        fl.anular_factura(id_fac, "Prueba Kardex")
        self.assertEqual(pl.buscar_por_codigo("KARDEX01")["stock"], 12)

    def test_migracion_kardex_sin_perdida_de_datos(self):
        import sqlite3

        ruta_ant = os.environ["BILLZEN_DB"]
        ruta_mig = os.path.join(tempfile.mkdtemp(), "legacy_mig.db")
        try:
            # Crear BD con esquema legado previo (solo movimientos_inventario, sin inventory_movements)
            con = sqlite3.connect(ruta_mig)
            con.executescript(
                """
                CREATE TABLE roles (id_rol INTEGER PRIMARY KEY, nombre TEXT UNIQUE NOT NULL);
                INSERT INTO roles VALUES (1, 'administrador'), (2, 'cajero');
                CREATE TABLE usuarios (
                    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    id_rol INTEGER NOT NULL REFERENCES roles(id_rol),
                    activo INTEGER NOT NULL DEFAULT 1,
                    intentos_fallidos INTEGER NOT NULL DEFAULT 0,
                    bloqueado_hasta TEXT,
                    ultimo_acceso TEXT,
                    creado_en TEXT
                );
                INSERT INTO usuarios (username, nombre_completo, password_hash, id_rol) VALUES ('admin', 'Admin', 'h', 1);
                CREATE TABLE categorias (
                    id_categoria INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT UNIQUE NOT NULL,
                    descripcion TEXT,
                    iva_porcentaje REAL NOT NULL DEFAULT 19
                );
                INSERT INTO categorias (nombre, iva_porcentaje) VALUES ('General', 19);
                CREATE TABLE productos (
                    id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT UNIQUE NOT NULL,
                    nombre TEXT NOT NULL,
                    id_categoria INTEGER NOT NULL REFERENCES categorias(id_categoria),
                    costo REAL NOT NULL DEFAULT 0,
                    precio REAL NOT NULL,
                    stock INTEGER NOT NULL DEFAULT 0,
                    stock_minimo INTEGER NOT NULL DEFAULT 5,
                    activo INTEGER NOT NULL DEFAULT 1,
                    creado_en TEXT
                );
                INSERT INTO productos (codigo, nombre, id_categoria, costo, precio, stock)
                VALUES ('LEG1', 'Producto Legado', 1, 1000, 1500, 12);
                CREATE TABLE movimientos_inventario (
                    id_movimiento INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_producto INTEGER NOT NULL REFERENCES productos(id_producto),
                    tipo TEXT NOT NULL CHECK (tipo IN ('ENTRADA','VENTA','ANULACION')),
                    cantidad INTEGER NOT NULL,
                    stock_final INTEGER NOT NULL,
                    referencia TEXT,
                    id_usuario INTEGER NOT NULL REFERENCES usuarios(id_usuario),
                    fecha TEXT DEFAULT '2026-11-01 10:00:00'
                );
                INSERT INTO movimientos_inventario (id_producto, tipo, cantidad, stock_final, referencia, id_usuario)
                VALUES (1, 'ENTRADA', 15, 15, 'Inicial', 1),
                       (1, 'VENTA', -3, 12, 'FV-000001', 1);
                """
            )
            con.commit()
            con.close()

            os.environ["BILLZEN_DB"] = ruta_mig
            inicializar_base_datos()

            migrados = consultar("SELECT * FROM inventory_movements ORDER BY id ASC")
            self.assertEqual(len(migrados), 2)
            self.assertEqual(migrados[0]["movement_type"], "ENTRADA")
            self.assertEqual(migrados[0]["previous_stock"], 0)
            self.assertEqual(migrados[0]["new_stock"], 15)
            self.assertEqual(migrados[0]["quantity"], 15)
            self.assertEqual(migrados[1]["movement_type"], "VENTA")
            self.assertEqual(migrados[1]["previous_stock"], 15)
            self.assertEqual(migrados[1]["new_stock"], 12)
            self.assertEqual(migrados[1]["quantity"], 3)

            encolados = consultar("SELECT * FROM sync_queue WHERE status = 'PENDING'")
            self.assertEqual(len(encolados), 2)
        finally:
            os.environ["BILLZEN_DB"] = ruta_ant


if __name__ == "__main__":
    unittest.main()
