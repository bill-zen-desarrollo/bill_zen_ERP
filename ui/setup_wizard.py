"""Asistente de primera ejecución: 1) datos de la empresa  2) cuenta del administrador  3) preguntas de seguridad."""
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import auth_logic, empresa_logic
from logica.seguridad import ErrorValidacion
from ui import componentes as cmp
from ui import tema


class AsistenteInicial(ttk.Frame):
    def __init__(self, padre, al_terminar):
        super().__init__(padre, style="Lateral.TFrame")
        self.al_terminar = al_terminar
        self.pack(fill=BOTH, expand=YES)

        izq = ttk.Frame(self, style="Lateral.TFrame", padding=40, width=380)
        izq.pack(side=LEFT, fill=Y)
        izq.pack_propagate(False)
        ttk.Label(izq, text="Bill", style="Logo.TLabel").pack(anchor=W, pady=(60, 0))
        ttk.Label(izq, text="Zen", style="LogoZen.TLabel").pack(anchor=W)
        ttk.Label(izq, text="Sistema ERP para pymes", style="Lateral.TLabel",
                  font=(tema.FUENTE, 11)).pack(anchor=W, pady=(8, 40))
        self.lbl_pasos = []
        pasos = ("Datos de tu empresa", "Cuenta de administrador", "Preguntas de seguridad")
        for i, texto in enumerate(pasos):
            f = ttk.Frame(izq, style="Lateral.TFrame")
            f.pack(fill=X, pady=8)
            ttk.Label(f, text=f"{i + 1}", style="Lateral.TLabel", font=(tema.FUENTE, 13, "bold")).pack(side=LEFT, padx=(0, 12))
            lbl = ttk.Label(f, text=texto, style="Lateral.TLabel", font=(tema.FUENTE, 11))
            lbl.pack(side=LEFT)
            self.lbl_pasos.append(lbl)

        der = ttk.Frame(self, padding=(60, 50))
        der.pack(side=LEFT, fill=BOTH, expand=YES)
        self.contenedor = ttk.Frame(der)
        self.contenedor.pack(fill=BOTH, expand=YES)
        self.datos_empresa = {}
        self.admin_username = None
        if not empresa_logic.empresa_registrada():
            self.paso_empresa()
        elif not auth_logic.existe_admin():
            self.paso_admin()
        else:
            self.paso_preguntas()

    def _resaltar(self, n):
        for i, lbl in enumerate(self.lbl_pasos):
            lbl.configure(foreground=tema.DORADO_CLARO if i == n else tema.BEIGE)

    def _limpiar(self):
        for w in self.contenedor.winfo_children():
            w.destroy()

    def paso_empresa(self):
        self._limpiar()
        self._resaltar(0)
        ttk.Label(self.contenedor, text="Bienvenido a Bill Zen", style="Titulo.TLabel").pack(anchor=W)
        ttk.Label(self.contenedor, text="Cuéntanos sobre tu empresa. Estos datos aparecerán en tus facturas.",
                  style="Subtitulo.TLabel").pack(anchor=W, pady=(0, 15))
        self.e_nit = cmp.campo(self.contenedor, "NIT *", estilo_label="Fondo.TLabel")
        self.e_razon = cmp.campo(self.contenedor, "Razón social / Nombre del negocio *", estilo_label="Fondo.TLabel")
        self.e_dir = cmp.campo(self.contenedor, "Dirección", estilo_label="Fondo.TLabel")
        self.e_tel = cmp.campo(self.contenedor, "Teléfono", estilo_label="Fondo.TLabel")
        self.e_correo = cmp.campo(self.contenedor, "Correo electrónico", estilo_label="Fondo.TLabel")
        ttk.Button(self.contenedor, text="Continuar  →", style="Zen.TButton",
                   command=self._guardar_empresa).pack(anchor=E, pady=(28, 0))
        self.e_nit.focus_set()

    def _guardar_empresa(self):
        self.datos_empresa = {"nit": self.e_nit.get(), "razon_social": self.e_razon.get(),
                              "direccion": self.e_dir.get(), "telefono": self.e_tel.get(),
                              "correo": self.e_correo.get()}
        try:
            empresa_logic._validar(self.datos_empresa)
            empresa_logic.registrar_empresa(self.datos_empresa)
        except ErrorValidacion as e:
            cmp.mostrar_error(self, e)
            return
        self.paso_admin()

    def paso_admin(self):
        self._limpiar()
        self._resaltar(1)
        ttk.Label(self.contenedor, text="Crea tu cuenta de administrador", style="Titulo.TLabel").pack(anchor=W)
        ttk.Label(self.contenedor, text="Este usuario tendrá control total del sistema. Guarda bien su contraseña.",
                  style="Subtitulo.TLabel").pack(anchor=W, pady=(0, 15))
        self.e_nombre = cmp.campo(self.contenedor, "Nombre completo *", estilo_label="Fondo.TLabel")
        self.e_user = cmp.campo(self.contenedor, "Nombre de usuario *", estilo_label="Fondo.TLabel")
        self.e_pass = cmp.campo(self.contenedor, "Contraseña * (mínimo 8 caracteres, letras y números)", show="●", estilo_label="Fondo.TLabel")
        self.e_pass2 = cmp.campo(self.contenedor, "Confirmar contraseña *", show="●", estilo_label="Fondo.TLabel")
        ttk.Button(self.contenedor, text="Continuar  →", style="Zen.TButton",
                   command=self._guardar_admin).pack(anchor=E, pady=(28, 0))
        self.e_nombre.focus_set()

    def _guardar_admin(self):
        username = self.e_user.get()
        try:
            auth_logic.registrar_primer_admin(username, self.e_nombre.get(),
                                              self.e_pass.get(), self.e_pass2.get())
        except ErrorValidacion as e:
            cmp.mostrar_error(self, e)
            return
        self.admin_username = username.strip()
        self.paso_preguntas()

    def paso_preguntas(self):
        self._limpiar()
        self._resaltar(2)
        ttk.Label(self.contenedor, text="Preguntas de seguridad", style="Titulo.TLabel").pack(anchor=W)
        ttk.Label(
            self.contenedor,
            text="Elige 2 preguntas personales que solo tú conozcas. Te permitirán recuperar el acceso si olvidas tu contraseña.",
            style="Subtitulo.TLabel",
            wraplength=620,
        ).pack(anchor=W, pady=(0, 15))

        preguntas = auth_logic.PREGUNTAS_PREDEFINIDAS

        ttk.Label(self.contenedor, text="Pregunta de seguridad 1 *", style="Fondo.TLabel",
                  font=(tema.FUENTE, 9, "bold")).pack(anchor=W, pady=(10, 4))
        self.cb_preg1 = ttk.Combobox(self.contenedor, values=preguntas, state="readonly")
        self.cb_preg1.current(0)
        self.cb_preg1.pack(fill=X, pady=(0, 6))
        self.e_resp1 = cmp.campo(self.contenedor, "Tu respuesta 1 *", estilo_label="Fondo.TLabel")

        ttk.Label(self.contenedor, text="Pregunta de seguridad 2 *", style="Fondo.TLabel",
                  font=(tema.FUENTE, 9, "bold")).pack(anchor=W, pady=(10, 4))
        self.cb_preg2 = ttk.Combobox(self.contenedor, values=preguntas, state="readonly")
        self.cb_preg2.current(1)
        self.cb_preg2.pack(fill=X, pady=(0, 6))
        self.e_resp2 = cmp.campo(self.contenedor, "Tu respuesta 2 *", estilo_label="Fondo.TLabel")

        ttk.Button(self.contenedor, text="Guardar y comenzar", style="Oro.TButton",
                   command=self._guardar_preguntas).pack(anchor=E, pady=(24, 0))
        self.e_resp1.focus_set()

    def _guardar_preguntas(self):
        try:
            auth_logic.guardar_preguntas_admin(
                self.cb_preg1.get(),
                self.e_resp1.get(),
                self.cb_preg2.get(),
                self.e_resp2.get(),
                username=self.admin_username,
            )
        except ErrorValidacion as e:
            cmp.mostrar_error(self, e)
            return
        cmp.mostrar_info(self, "¡Listo! Tu cuenta de administrador y preguntas de seguridad fueron configuradas. Ahora inicia sesión.")
        self.destroy()
        self.al_terminar()
