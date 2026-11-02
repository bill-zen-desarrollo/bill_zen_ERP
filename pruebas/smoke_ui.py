"""Prueba de humo de la interfaz: abre todas las vistas (admin y cajero) con una BD temporal."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["BILLZEN_DB"] = os.path.join(tempfile.mkdtemp(), "ui.db")

import ttkbootstrap as ttk

from database.setup_db import inicializar_base_datos
from logica import auth_logic, empresa_logic, facturacion_logic as fl, productos_logic as pl, reportes_logic as rl, usuarios_logic as ul
from logica.seguridad import Sesion
from ui import tema
from ui.shell import SECCIONES, Principal
from ui.login import Login
from ui.setup_wizard import AsistenteInicial

inicializar_base_datos()
root = ttk.Window(themename="flatly")
estilo = tema.registrar_tema()
tema.aplicar_estilos(estilo)
root.geometry("1280x760")

AsistenteInicial(root, lambda: None).destroy()
empresa_logic.registrar_empresa({"nit": "900.123.456-7", "razon_social": "Tienda Zen", "direccion": "Calle 1", "telefono": "3001234567"})
auth_logic.registrar_primer_admin("admin", "Ana Admin", "Clave1234", "Clave1234")
AsistenteInicial(root, lambda: None).destroy()
auth_logic.guardar_preguntas_admin(auth_logic.PREGUNTAS_PREDEFINIDAS[0], "Firulais", auth_logic.PREGUNTAS_PREDEFINIDAS[1], "Bogotá")
login_ui = Login(root, lambda u: None)
login_ui._mostrar_recuperacion_usuario("admin")
login_ui._validar_usuario_recuperacion()
login_ui.destroy()
auth_logic.iniciar_sesion("admin", "Clave1234")
cats = {c["nombre"]: c["id_categoria"] for c in pl.listar_categorias()}
for cod, nom, cat, costo, precio in (("1", "Leche 1L", "Canasta familiar", 2500, 3600), ("2", "Gaseosa 1.5L", "Bebidas", 3000, 5200), ("3", "Jabón", "Aseo y hogar", 1200, 2400)):
    pl.guardar_producto({"codigo": cod, "nombre": nom, "id_categoria": cats[cat], "costo": costo, "precio": precio, "stock_inicial": 20, "stock_minimo": 3})
pids = [p["id_producto"] for p in pl.listar_productos()]
fl.emitir_factura([{"id_producto": pids[0], "cantidad": 3}, {"id_producto": pids[1], "cantidad": 2}], "Efectivo", 50000)
rl.registrar_gasto("2026-10-09", "Arriendo", "Arriendo", "500.000")
ul.crear_usuario("caja1", "Carlos Caja", "Cajero123", "Cajero123")

ok = True
for rol, usuario in (("admin", ("admin", "Clave1234")), ("cajero", ("caja1", "Cajero123"))):
    auth_logic.iniciar_sesion(*usuario)
    p = Principal(root, lambda: None)
    for clave in list(p.botones):
        try:
            p.ir_a(clave)
            root.update()
            print(f"OK   {rol:7s} {clave}")
        except Exception as e:
            ok = False
            import traceback
            print(f"FAIL {rol:7s} {clave}: {e}")
            traceback.print_exc()
    print(rol, "menú:", list(p.botones))
    p.destroy()
root.destroy()
print("RESULTADO:", "TODO OK" if ok else "HAY ERRORES")
