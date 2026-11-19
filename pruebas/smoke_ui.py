"""Prueba de humo de la interfaz: abre todas las vistas (admin y cajero) con una BD temporal."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["BILLZEN_DB"] = os.path.join(tempfile.mkdtemp(), "ui.db")

import ttkbootstrap as ttk

from database.setup_db import inicializar_base_datos
from logica import auth_logic, empresa_logic, facturacion_logic as fl, licencia, productos_logic as pl, reportes_logic as rl, usuarios_logic as ul
from logica.seguridad import Sesion
from ui import tema
from ui.activacion import VistaActivacion
from ui.shell import SECCIONES, Principal
from ui.login import Login
from ui.setup_wizard import AsistenteInicial

inicializar_base_datos()
root = ttk.Window(themename="flatly")
estilo = tema.registrar_tema()
tema.aplicar_estilos(estilo)
root.geometry("1280x760")

# Verificar sistema de diseño global (Segoe UI sin serifa, rowheight=36) y luego vistas
assert tema.FUENTE == "Segoe UI"
assert tema.FUENTE_TITULO == "Segoe UI"
assert tema.FUENTE_CURSIVA == "Segoe UI"
assert int(estilo.configure("Treeview", "rowheight")) == 36

# Probar vista de activación inicial (tamaño fijo ante errores) y luego activar plan 'pro'
est_inicial = licencia.verificar_licencia_local()
assert not est_inicial["valido"]
va = VistaActivacion(root, est_inicial, lambda: None)
root.update()
tam_act_0 = (va.tarjeta.winfo_width(), va.tarjeta.winfo_height())
va.e_nit.insert(0, "correo_invalido@empresa.com")
va.e_pass.insert(0, "12345")
va.activar()
root.update()
tam_act_1 = (va.tarjeta.winfo_width(), va.tarjeta.winfo_height())
assert tam_act_0 == tam_act_1, f"El modal de activación cambió de tamaño al mostrar error: {tam_act_0} != {tam_act_1}"
va.destroy()
licencia._sincronizar_empresa_local(
    {"nit": "900.123.456-7", "razon_social": "Tienda Zen", "email": "admin@billzen.co"},
    "admin@billzen.co",
)
licencia.guardar_licencia_local("admin@billzen.co", licencia.generar_hardware_id(), "pro")

AsistenteInicial(root, lambda: None).destroy()
auth_logic.configurar_admin_inicial(
    "Clave1234",
    "Clave1234",
    auth_logic.PREGUNTAS_PREDEFINIDAS[0],
    "Firulais",
    auth_logic.PREGUNTAS_PREDEFINIDAS[1],
    "Bogotá",
)
login_ui = Login(root, lambda u: None)
root.update()
tam_antes = (login_ui.tarjeta.winfo_width(), login_ui.tarjeta.winfo_height())
login_ui.e_user.insert(0, "administrador")
login_ui.e_pass.insert(0, "clave_erronea")
login_ui.ingresar()
root.update()
tam_despues = (login_ui.tarjeta.winfo_width(), login_ui.tarjeta.winfo_height())
assert tam_antes == tam_despues, f"El modal de login cambió de tamaño al mostrar error: {tam_antes} != {tam_despues}"
login_ui._mostrar_recuperacion_usuario()
login_ui._validar_usuario_recuperacion()
login_ui.destroy()
auth_logic.iniciar_sesion("administrador", "Clave1234")
cats = {c["nombre"]: c["id_categoria"] for c in pl.listar_categorias()}
for cod, nom, cat, costo, precio in (("1", "Leche 1L", "Canasta familiar", 2500, 3600), ("2", "Gaseosa 1.5L", "Bebidas", 3000, 5200), ("3", "Jabón", "Aseo y hogar", 1200, 2400)):
    pl.guardar_producto({"codigo": cod, "nombre": nom, "id_categoria": cats[cat], "costo": costo, "precio": precio, "stock_inicial": 20, "stock_minimo": 3})
pids = [p["id_producto"] for p in pl.listar_productos()]
fl.emitir_factura([{"id_producto": pids[0], "cantidad": 3}, {"id_producto": pids[1], "cantidad": 2}], "Efectivo", 50000)
rl.registrar_gasto("2026-10-09", "Arriendo", "Arriendo", "500.000")
ul.crear_usuario("caja1", "Carlos Caja", "Cajero123", "Cajero123")

ok = True
for rol, usuario in (("admin", ("administrador", "Clave1234")), ("cajero", ("caja1", "Cajero123"))):
    auth_logic.iniciar_sesion(*usuario)
    p = Principal(root, al_cerrar_sesion=lambda: None)
    for clave in list(p.botones):
        try:
            p.ir_a(clave)
            root.update()
            if clave == "inventario" and rol == "admin":
                v = p.vista_actual
                # Verificar resolución mínima 1100x680 sin recortes
                root.geometry("1100x680")
                root.update()
                assert v.btn_registrar.winfo_height() > 0
                assert v.btn_limpiar.winfo_height() > 0
                assert v.btn_registrar.winfo_rooty() + v.btn_registrar.winfo_height() <= root.winfo_rooty() + root.winfo_height()
                root.geometry("1280x760")
                root.update()

                # Verificar 3 KPIs, paginación y Kardex inicial
                unidades_antes = int(v.kpi_unidades.valor.cget("text").replace(".", ""))
                assert len(v.tv.get_children()) >= 3
                assert v.cb_filtro_tipo.get() == "Todos"
                assert "Página 1" in v.lbl_paginacion.cget("text")
                assert "SQLite" in p.lbl_estado_sync.cget("text") or "Nube" in p.lbl_estado_sync.cget("text")

                # Escanear SKU "1" (Leche 1L, stock actual = 20) y registrar ajuste por conteo físico (20 -> 17)
                leche_prod = pl.buscar_por_codigo("1")
                v.e_sku_prod.insert(0, "1")
                v._confirmar_sku_form()
                assert v.producto_seleccionado_id == leche_prod["id_producto"]
                v.cb_tipo_mov.set("Ajuste conteo físico")
                v._actualizar_etiquetas_movimiento()
                v.e_cant.insert(0, "17")
                v.e_motivo.insert(0, "Conteo físico smoke test")
                v.registrar_movimiento()
                root.update()

                unidades_despues = int(v.kpi_unidades.valor.cget("text").replace(".", ""))
                assert unidades_despues == unidades_antes - 3
                primera_fila = v.tv.item(v.tv.get_children()[0])["values"]
                assert str(primera_fila[1]) == "1"
                assert primera_fila[3] == "Ajuste conteo"
                assert primera_fila[5] == "20 -> 17"

                # Probar filtros: Mermas/Ajustes, Ventas, Solo stock bajo, y regresar a Todos
                v.cb_filtro_tipo.set("Mermas/Ajustes")
                v.refrescar_kardex()
                assert len(v.tv.get_children()) >= 1
                v.cb_filtro_tipo.set("Ventas")
                v.refrescar_kardex()
                assert len(v.tv.get_children()) >= 2
                v._alternar_stock_bajo()
                assert v.var_bajo.get() is True
                v._alternar_stock_bajo()
                v.cb_filtro_tipo.set("Todos")
                v.refrescar_kardex()

                # Verificar que el stock actualizado se refleja inmediatamente en la vista Productos
                p.ir_a("productos")
                root.update()
                v_prod = p.vista_actual
                assert v_prod.filas[str(leche_prod["id_producto"])]["stock"] == 17
            elif clave == "facturacion":
                v = p.vista_actual
                primer_id = int(list(v.productos.keys())[0])
                primer_cod = v.productos[str(primer_id)]["codigo"]
                # 1. Probar agregar por código de barras con cantidad previa = 4
                v.sp_cant_agregar.set("4")
                v.e_buscar.insert(0, primer_cod)
                v._confirmar_busqueda_o_sugerencia()
                assert v.carrito[primer_id]["cantidad"] == 4
                # 2. Probar autocompletado por nombre parcial ("Leche") + clic/enter en sugerencia
                v.e_buscar.insert(0, "Leche")
                v._al_teclear_codigo()
                assert len(v._sugerencias_actuales) >= 1
                v._clic_sugerencia()
                # 3. Probar botón + y - sobre el primer producto
                v.tv_car.selection_set(str(primer_id))
                v.cambiar(1)
                assert v.carrito[primer_id]["cantidad"] == 5
                v.cambiar(-2)
                assert v.carrito[primer_id]["cantidad"] == 3
                # 4. Probar fijar cantidad directa en la factura
                v.e_cant_car.delete(0, "end")
                v.e_cant_car.insert(0, "7")
                v.fijar_cantidad_carrito()
                assert v.carrito[primer_id]["cantidad"] == 7
                # 5. Probar persistencia del carrito al cambiar a Inventario / Facturas emitidas y regresar
                v.e_cliente.delete(0, "end")
                v.e_cliente.insert(0, "Cliente Prueba Persistencia")
                v._guardar_estado_borrador()
                p.ir_a("inventario")
                root.update()
                p.ir_a("facturas")
                root.update()
                p.ir_a("facturacion")
                root.update()
                v2 = p.vista_actual
                assert primer_id in v2.carrito and v2.carrito[primer_id]["cantidad"] == 7
                assert v2.e_cliente.get() == "Cliente Prueba Persistencia"
                v2.vaciar()
                assert len(v2.carrito) == 0
            print(f"OK   {rol:7s} {clave}")
        except Exception as e:
            ok = False
            import traceback
            print(f"FAIL {rol:7s} {clave}: {e}")
            traceback.print_exc()
    print(rol, "menú:", list(p.botones))
    p.cerrar_sesion()

# Verificar Camaleón UI con plan 'basico' (oculta/deshabilita módulos premium con candado)
auth_logic.iniciar_sesion("administrador", "Clave1234")
licencia.guardar_licencia_local("admin@billzen.co", licencia.generar_hardware_id(), "basico")
p_basico = Principal(root, lambda: None)
assert "auditoria_movil" not in p_basico.botones
assert "contabilidad" not in p_basico.botones
assert "productos" in p_basico.botones
print("admin (plan basico) menú habilitado:", list(p_basico.botones))
p_basico.destroy()

# Probar vista previa de tirilla térmica POS 80mm (estilo D1 / Ara / Epson TM-T88V)
from ui.recibo import VentanaFactura, _formatear_texto_tirilla, _html
fac_prueba = fl.obtener_factura(1)
emp_prueba = empresa_logic.obtener_empresa()
txt_tirilla = _formatear_texto_tirilla(fac_prueba, emp_prueba)
html_tirilla = _html(fac_prueba, emp_prueba)
assert "DISCRIMINACION DE IMPUESTOS" in txt_tirilla
assert "size: 80mm auto" in html_tirilla
vf = VentanaFactura(root, fac_prueba)
root.update()
vf.destroy()

root.destroy()
print("RESULTADO:", "TODO OK" if ok else "HAY ERRORES")
