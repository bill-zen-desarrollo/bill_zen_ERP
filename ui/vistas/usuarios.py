"""Administración de usuarios (solo admin)."""
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import licencia, usuarios_logic as ul
from logica.seguridad import ROL_ADMIN, ROL_CAJERO, ErrorValidacion
from ui import componentes as cmp
from ui import tema

ROLES = {"Cajero": ROL_CAJERO, "Administrador": ROL_ADMIN}


class Vista(ttk.Frame):
    def __init__(self, padre, principal):
        super().__init__(padre)
        self.id_sel = None
        max_caj = licencia.max_cajeros_permitidos()
        sub = (
            f"{licencia.nombre_legible_plan()}: permite hasta {max_caj} cajero activo (además del Administrador)"
            if max_caj is not None
            else f"{licencia.nombre_legible_plan()}: creación de cajeros ilimitada habilitada"
        )
        cmp.encabezado(self, "Usuarios", sub).pack(anchor=W, pady=(0, 12))
        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill=BOTH, expand=YES)
        marco, self.tv = cmp.tabla(cuerpo, [("u", "Usuario", 110, W), ("n", "Nombre", 200, W), ("r", "Rol", 110, W),
                                            ("e", "Estado", 80, W), ("a", "Último acceso", 150, W)], altura=17)
        marco.pack(side=LEFT, fill=BOTH, expand=YES, padx=(0, 16))
        self.tv.bind("<<TreeviewSelect>>", lambda e: self.cargar())

        borde = cmp.tarjeta(cuerpo, padding=24)
        borde.pack(side=LEFT, fill=Y)
        c = borde.interior
        self.lbl = ttk.Label(c, text="Nuevo usuario", style="TarjetaTitulo.TLabel")
        self.lbl.pack(anchor=W, pady=(0, 10))
        self.e_user = cmp.campo(c, "Usuario *", ancho=45)
        self.e_nombre = cmp.campo(c, "Nombre completo *", ancho=45)
        ttk.Label(c, text="Rol", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(anchor=W, pady=(12, 4))
        ttk.Label(c, text="Cajero (por defecto)", foreground=tema.GRIS).pack(anchor=W, pady=(0, 10))
        self.e_pass = cmp.campo(c, "Contraseña (mín. 8, letras y números)", ancho=45, show="●")
        self.e_pass2 = cmp.campo(c, "Confirmar contraseña", ancho=45, show="●")
        self.var_activo = ttk.BooleanVar(value=True)
        self.chk = ttk.Checkbutton(c, text="Cuenta activa", variable=self.var_activo)
        self.chk.pack(anchor=W, pady=(10, 0))
        
        btn_frame = ttk.Frame(c, style="Tarjeta.TFrame")
        btn_frame.pack(fill=X, pady=(20, 10))
        self.btn_guardar = ttk.Button(btn_frame, text="Crear usuario", style="Zen.TButton", command=self.guardar)
        self.btn_guardar.pack(side=LEFT, fill=X, expand=YES, padx=(0, 4))
        ttk.Button(btn_frame, text="Nuevo / Limpiar", style="Suave.TButton", command=self.limpiar).pack(side=LEFT, fill=X, expand=YES, padx=(4, 0))
        
        ttk.Button(c, text="Restablecer contraseña", style="Oro.TButton", command=self.resetear).pack(fill=X, pady=2)
        
        self.refrescar()

    def refrescar(self):
        self.filas = {str(u["id_usuario"]): u for u in ul.listar_usuarios()}
        cmp.llenar_tabla(self.tv, [(u["id_usuario"], (u["username"], u["nombre_completo"], u["rol"].capitalize(),
                                                      "Activo" if u["activo"] else "Inactivo", u["ultimo_acceso"] or "—")) for u in self.filas.values()],
                         lambda i, v: ("anulada",) if v[3] == "Inactivo" else ())

    def limpiar(self):
        self.id_sel = None
        self.lbl.configure(text="Nuevo usuario")
        self.btn_guardar.configure(text="Crear usuario")
        self.e_user.configure(state=NORMAL)
        for e in (self.e_user, self.e_nombre, self.e_pass, self.e_pass2):
            e.delete(0, END)
        self.var_activo.set(True)
        self.tv.selection_remove(self.tv.selection())

    def cargar(self):
        s = self.tv.selection()
        if not s:
            return
        u = self.filas[s[0]]
        self.id_sel = u["id_usuario"]
        self.lbl.configure(text=f"Editando: {u['username']}")
        self.btn_guardar.configure(text="Guardar cambios")
        self.e_user.configure(state=NORMAL)
        self.e_user.delete(0, END)
        self.e_user.insert(0, u["username"])
        self.e_user.configure(state=DISABLED)
        self.e_nombre.delete(0, END)
        self.e_nombre.insert(0, u["nombre_completo"])
        self.var_activo.set(bool(u["activo"]))
        for e in (self.e_pass, self.e_pass2):
            e.delete(0, END)

    def guardar(self):
        try:
            if self.id_sel:
                # No se envía el rol, para no permitir cambiar a un usuario
                ul.actualizar_usuario(self.id_sel, self.e_nombre.get(), self.var_activo.get())
            else:
                ul.crear_usuario(self.e_user.get(), self.e_nombre.get(), self.e_pass.get(), self.e_pass2.get())
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)
        cmp.toast(self, "Usuario guardado")
        self.refrescar()
        self.limpiar()

    def resetear(self):
        if not self.id_sel:
            return cmp.mostrar_error(self, "Selecciona un usuario de la lista.")
        try:
            ul.restablecer_password(self.id_sel, self.e_pass.get(), self.e_pass2.get())
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)
        cmp.toast(self, "Contraseña actualizada")
        for e in (self.e_pass, self.e_pass2):
            e.delete(0, END)
