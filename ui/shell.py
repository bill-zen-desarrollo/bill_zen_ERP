"""Ventana principal: menú lateral según rol + área de contenido.

La sesión permanece abierta hasta que el usuario la cierre manualmente
(en una tienda pueden pasar muchos minutos sin clientes)."""
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica.empresa_logic import obtener_empresa
from logica.seguridad import ROL_ADMIN, ROL_CAJERO, ErrorPermiso, Sesion
from ui import componentes as cmp
from ui import tema


def _cargar(nombre):
    import importlib
    if False:  # pistas estáticas para que PyInstaller empaquete todas las vistas y sus dependencias
        import ui.vistas.configuracion
        import ui.vistas.contabilidad
        import ui.vistas.dashboard
        import ui.vistas.facturacion
        import ui.vistas.facturas
        import ui.vistas.inventario
        import ui.vistas.productos
        import ui.vistas.reportes
        import ui.vistas.usuarios
        import openpyxl
    modulo = importlib.import_module(f"ui.vistas.{nombre}")
    return modulo.Vista


# (clave, texto del menú, módulo, roles permitidos)
SECCIONES = [
    ("dashboard", "▦  Dashboard", "dashboard", (ROL_ADMIN,)),
    ("facturacion", "🧾  Facturación", "facturacion", (ROL_CAJERO,)),
    ("facturas", "📄  Facturas emitidas", "facturas", (ROL_ADMIN, ROL_CAJERO)),
    ("productos", "📦  Productos", "productos", (ROL_ADMIN,)),
    ("inventario", "▤  Inventario", "inventario", (ROL_ADMIN, ROL_CAJERO)),
    ("contabilidad", "＄  Contabilidad", "contabilidad", (ROL_ADMIN,)),
    ("reportes", "📈  Reportes", "reportes", (ROL_ADMIN,)),
    ("usuarios", "👥  Usuarios", "usuarios", (ROL_ADMIN,)),
    ("configuracion", "⚙  Configuración", "configuracion", (ROL_ADMIN,)),
]


class Principal(ttk.Frame):
    def __init__(self, padre, al_cerrar_sesion):
        super().__init__(padre)
        self.al_cerrar_sesion = al_cerrar_sesion
        self.pack(fill=BOTH, expand=YES)
        self.usuario = Sesion.usuario
        self.botones = {}
        self.vista_actual = None

        lateral = ttk.Frame(self, style="Lateral.TFrame", width=240)
        lateral.pack(side=LEFT, fill=Y)
        lateral.pack_propagate(False)

        logo = ttk.Frame(lateral, style="Lateral.TFrame", padding=(22, 24, 22, 4))
        logo.pack(fill=X)
        ttk.Label(logo, text="Bill ", style="Logo.TLabel").pack(side=LEFT)
        ttk.Label(logo, text="Zen", style="LogoZen.TLabel").pack(side=LEFT)
        emp = obtener_empresa() or {}
        ttk.Label(lateral, text=emp.get("razon_social", ""), style="Lateral.TLabel", wraplength=200,
                  font=(tema.FUENTE, 9)).pack(anchor=W, padx=24, pady=(0, 18))

        for clave, texto, modulo, roles in SECCIONES:
            if self.usuario["id_rol"] in roles:
                b = ttk.Button(lateral, text=texto, style="Menu.TButton", command=lambda c=clave: self.ir_a(c))
                b.pack(fill=X)
                self.botones[clave] = b

        pie = ttk.Frame(lateral, style="Lateral.TFrame", padding=18)
        pie.pack(side=BOTTOM, fill=X)
        ttk.Label(pie, text=self.usuario["nombre_completo"], style="Lateral.TLabel",
                  font=(tema.FUENTE, 10, "bold"), wraplength=200).pack(anchor=W)
        ttk.Label(pie, text=self.usuario["rol"].capitalize(), style="Lateral.TLabel",
                  foreground=tema.DORADO_CLARO, font=(tema.FUENTE, 9)).pack(anchor=W, pady=(0, 10))
        ttk.Button(pie, text="Cerrar sesión", style="Oro.TButton", command=self.cerrar_sesion).pack(fill=X)

        self.area = ttk.Frame(self, padding=(28, 22))
        self.area.pack(side=LEFT, fill=BOTH, expand=YES)

        primera = "dashboard" if self.usuario["id_rol"] == ROL_ADMIN else "facturacion"
        self.ir_a(primera)

    def ir_a(self, clave):
        if clave not in self.botones:
            return
        for k, b in self.botones.items():
            b.configure(style="MenuActivo.TButton" if k == clave else "Menu.TButton")
        if self.vista_actual is not None:
            self.vista_actual.destroy()
        for c, texto, modulo, roles in SECCIONES:
            if c == clave:
                try:
                    self.vista_actual = _cargar(modulo)(self.area, self)
                    self.vista_actual.pack(fill=BOTH, expand=YES)
                except ErrorPermiso as e:
                    cmp.mostrar_error(self, e)
                break

    def cerrar_sesion(self):
        if not cmp.confirmar(self, "¿Deseas cerrar tu sesión?"):
            return
        Sesion.cerrar()
        self.destroy()
        self.al_cerrar_sesion()
