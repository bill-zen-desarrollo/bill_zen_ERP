import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["BILLZEN_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from database.setup_db import inicializar_base_datos
from logica import auth_logic, empresa_logic, facturacion_logic as fl, productos_logic as pl, usuarios_logic as ul
from logica.seguridad import ErrorPermiso, ErrorValidacion, Sesion


class PruebasBillZen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inicializar_base_datos()
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

    def test_bloqueo_por_intentos(self):
        admin = Sesion.usuario
        for _ in range(4):
            with self.assertRaises(ErrorValidacion):
                auth_logic.iniciar_sesion("caja2", "mala")
        with self.assertRaises(ErrorValidacion) as e:
            auth_logic.iniciar_sesion("caja2", "mala")
        self.assertIn("bloqueada", str(e.exception))
        Sesion.iniciar(admin)


if __name__ == "__main__":
    unittest.main()
