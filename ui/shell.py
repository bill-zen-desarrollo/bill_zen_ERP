"""Ventana principal: menú lateral según rol + área de contenido.

La sesión permanece abierta hasta que el usuario la cierre manualmente
(en una tienda pueden pasar muchos minutos sin clientes)."""
import threading
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import licencia
from logica.empresa_logic import obtener_empresa
from logica.seguridad import ROL_ADMIN, ROL_CAJERO, ErrorPermiso, Sesion
from ui import componentes as cmp
from ui import tema


def _cargar(nombre):
    import importlib
    if False:  # pistas estáticas para que PyInstaller empaquete todas las vistas y sus dependencias
        import ui.vistas.auditoria_movil
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
        import qrcode
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
    ("auditoria_movil", "📱  Auditoría Móvil (QR)", "auditoria_movil", (ROL_ADMIN,)),
    ("configuracion", "⚙  Configuración", "configuracion", (ROL_ADMIN,)),
]


class Principal(ttk.Frame):
    def __init__(self, padre, al_cerrar_sesion):
        super().__init__(padre)
        self.al_cerrar_sesion = al_cerrar_sesion
        self.pack(fill=BOTH, expand=YES)
        self.usuario = Sesion.usuario
        self.plan_actual = licencia.obtener_plan_actual()
        self.botones = {}
        self._tooltips = []
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
                  font=(tema.FUENTE, 9)).pack(anchor=W, padx=24, pady=(0, 4))

        fila_plan = ttk.Frame(lateral, style="Lateral.TFrame", padding=(24, 0, 18, 12))
        fila_plan.pack(fill=X)
        self.lbl_plan = ttk.Label(
            fila_plan,
            text=f"★ PLAN {licencia.etiqueta_corta_plan(self.plan_actual)}",
            style="Lateral.TLabel",
            foreground=tema.DORADO_CLARO,
            font=(tema.FUENTE, 8, "bold"),
        )
        self.lbl_plan.pack(side=LEFT)

        btn_sync = tk.Label(
            fila_plan,
            text="⟳ Actualizar",
            bg=tema.VERDE_OSCURO,
            fg=tema.BEIGE,
            font=(tema.FUENTE, 8, "underline"),
            cursor="hand2",
        )
        btn_sync.pack(side=RIGHT)
        btn_sync.bind("<Button-1>", lambda e: self.sincronizar_plan_manual())
        cmp.vincular_tooltip(
            btn_sync,
            "¿Mejoraste tu plan en la web? Haz clic aquí para sincronizar tu licencia y desbloquear tus nuevos módulos al instante.",
        )

        self.marco_menu = ttk.Frame(lateral, style="Lateral.TFrame")
        self.marco_menu.pack(fill=X)
        self._construir_menu_lateral()

        pie = ttk.Frame(lateral, style="Lateral.TFrame", padding=18)
        pie.pack(side=BOTTOM, fill=X)
        ttk.Label(pie, text=self.usuario["nombre_completo"], style="Lateral.TLabel",
                  font=(tema.FUENTE, 10, "bold"), wraplength=200).pack(anchor=W)
        ttk.Label(pie, text=self.usuario["rol"].capitalize(), style="Lateral.TLabel",
                  foreground=tema.DORADO_CLARO, font=(tema.FUENTE, 9)).pack(anchor=W, pady=(0, 10))
        ttk.Button(pie, text="Cerrar sesión", style="Oro.TButton", command=self.cerrar_sesion).pack(fill=X)

        self.area = ttk.Frame(self, padding=(28, 22))
        self.area.pack(side=LEFT, fill=BOTH, expand=YES)

        self.seccion_activa = "dashboard" if self.usuario["id_rol"] == ROL_ADMIN else "facturacion"
        self.ir_a(self.seccion_activa)

        # Sincronizar silenciosamente con la nube al iniciar sesión por si el usuario mejoró su plan en la web
        threading.Thread(target=self._sincronizar_plan_bg, daemon=True).start()

    def _construir_menu_lateral(self):
        for w in self.marco_menu.winfo_children():
            w.destroy()
        self.botones.clear()
        self.lbl_plan.configure(text=f"★ PLAN {licencia.etiqueta_corta_plan(self.plan_actual)}")

        for clave, texto, modulo, roles in SECCIONES:
            if self.usuario["id_rol"] in roles:
                habilitado = licencia.permite_modulo(clave, self.plan_actual)
                if habilitado:
                    b = ttk.Button(
                        self.marco_menu,
                        text=texto,
                        style="Menu.TButton",
                        command=lambda c=clave: self.ir_a(c),
                    )
                    b.pack(fill=X)
                    self.botones[clave] = b
                else:
                    plan_req = licencia.plan_requerido_para(clave)
                    b = ttk.Button(
                        self.marco_menu,
                        text=f"🔒  {texto}",
                        style="Menu.TButton",
                        state="disabled",
                    )
                    b.pack(fill=X)
                    cmp.vincular_tooltip(
                        b,
                        f"Disponible desde el Plan {plan_req}.\n"
                        f"Tu plan actual es {licencia.nombre_legible_plan(self.plan_actual)}. "
                        "Actualiza en bill-zen-users.vercel.app para desbloquearlo.",
                    )

    def _sincronizar_plan_bg(self):
        res = licencia.sincronizar_plan_con_nube(timeout_seg=3.0)
        if res.get("actualizado") and self.winfo_exists():
            self.after(0, lambda: self._aplicar_cambio_plan(res["plan"]))

    def sincronizar_plan_manual(self):
        res = licencia.sincronizar_plan_con_nube(timeout_seg=4.0)
        if res.get("actualizado"):
            self._aplicar_cambio_plan(res["plan"])
        else:
            cmp.toast(self, f"Tu licencia está al día: {licencia.nombre_legible_plan(self.plan_actual)}")

    def _aplicar_cambio_plan(self, nuevo_plan: str):
        if not self.winfo_exists():
            return
        self.plan_actual = nuevo_plan
        self._construir_menu_lateral()
        if getattr(self, "seccion_activa", None) in self.botones:
            self.ir_a(self.seccion_activa)
        cmp.toast(self, f"¡Actualizado a {licencia.nombre_legible_plan(nuevo_plan)}! Módulos sincronizados.")

    def ir_a(self, clave):
        if clave not in self.botones or not licencia.permite_modulo(clave, self.plan_actual):
            return
        self.seccion_activa = clave
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
