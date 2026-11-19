"""Pantalla de inicio de sesión y recuperación de contraseña de administrador.

Diseño: fondo con degradado verde corporativo y decoraciones, tarjeta flotante con
sombra, encabezado de marca, campos con iconos y un área de mensajes de altura fija
para que la tarjeta nunca cambie de tamaño al mostrar errores.
"""
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import auth_logic, empresa_logic
from logica.seguridad import ErrorValidacion
from ui import tema

ANCHO_FORM = 360          # ancho útil fijo del formulario (px)
ALTO_MENSAJE = 68         # alto reservado para mensajes (hasta 3 líneas sin crecer)

_COLORES_MENSAJE = {
    "error": ("#FEF2F2", "#B91C1C", "#FECACA", "⚠"),
    "exito": ("#ECFDF5", "#047857", "#A7F3D0", "✔"),
    "info": ("#F0F7F4", tema.VERDE_OSCURO, "#C7DDD3", "⏳"),
}


def _mezclar(c1: str, c2: str, t: float) -> str:
    """Interpola dos colores hex (t entre 0 y 1)."""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return "#{:02x}{:02x}{:02x}".format(
        int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t)
    )


class Login(ttk.Frame):
    def __init__(self, padre, al_ingresar):
        super().__init__(padre, style="Lateral.TFrame")
        self.al_ingresar = al_ingresar
        self.pack(fill=BOTH, expand=YES)
        self._timer_fondo = None
        self._emp = empresa_logic.obtener_empresa() or {}

        # ── Lienzo de fondo con degradado ───────────────────────────────
        self.lienzo = tk.Canvas(self, highlightthickness=0, bd=0, bg=tema.VERDE_PROFUNDO)
        self.lienzo.pack(fill=BOTH, expand=YES)

        # ── Tarjeta flotante ─────────────────────────────────────────────
        self.tarjeta = tk.Frame(self.lienzo, bg=tema.BLANCO)
        tk.Frame(self.tarjeta, bg=tema.DORADO, height=4).pack(fill=X)

        cab = tk.Frame(self.tarjeta, bg=tema.VERDE, padx=32, pady=18)
        cab.pack(fill=X)
        fila_logo = tk.Frame(cab, bg=tema.VERDE)
        fila_logo.pack(anchor=W)
        tk.Label(fila_logo, text="Bill", bg=tema.VERDE, fg=tema.BLANCO,
                 font=(tema.FUENTE, 24, "bold")).pack(side=LEFT)
        tk.Label(fila_logo, text=" Zen", bg=tema.VERDE, fg=tema.DORADO_CLARO,
                 font=(tema.FUENTE, 24, "bold")).pack(side=LEFT)
        razon = self._emp.get("razon_social") or "Sistema ERP para pymes"
        tk.Label(cab, text=razon, bg=tema.VERDE, fg="#D7E6DF", font=(tema.FUENTE, 10),
                 wraplength=ANCHO_FORM, justify=LEFT, anchor=W).pack(anchor=W, pady=(2, 0))

        self.c = tk.Frame(self.tarjeta, bg=tema.BLANCO, padx=32, pady=24)
        self.c.pack(fill=BOTH, expand=YES)

        self._id_tarjeta = self.lienzo.create_window(0, 0, window=self.tarjeta, anchor=CENTER)

        self.lienzo.bind("<Configure>", self._programar_fondo)
        self.tarjeta.bind("<Configure>", lambda _e: self._dibujar_sombra())

        self._mostrar_formulario_login()

    # ==================================================================
    # FONDO, DECORACIONES Y SOMBRA
    # ==================================================================
    def _programar_fondo(self, _e=None):
        if self._timer_fondo:
            try:
                self.after_cancel(self._timer_fondo)
            except Exception:
                pass
        self._timer_fondo = self.after(40, self._dibujar_fondo)

    def _dibujar_fondo(self):
        self._timer_fondo = None
        cv = self.lienzo
        if not cv.winfo_exists():
            return
        w, h = cv.winfo_width(), cv.winfo_height()
        if w < 10 or h < 10:
            return
        cv.delete("fondo")

        # Degradado diagonal suave en bandas (ligero para equipos de bajos recursos)
        paso = 6
        superior, inferior = tema.VERDE_PROFUNDO, "#15624B"
        for y in range(0, h, paso):
            cv.create_rectangle(0, y, w, y + paso, fill=_mezclar(superior, inferior, y / h),
                                outline="", tags="fondo")

        # Círculos decorativos
        cv.create_oval(-w * 0.15, -h * 0.35, w * 0.35, h * 0.45, outline="#1E7A5E", width=2, tags="fondo")
        cv.create_oval(-w * 0.08, -h * 0.25, w * 0.27, h * 0.33, outline="#196A52", width=1, tags="fondo")
        cv.create_oval(w * 0.70, h * 0.55, w * 1.20, h * 1.40, outline="#1E7A5E", width=2, tags="fondo")
        cv.create_oval(w * 0.78, h * 0.66, w * 1.10, h * 1.25, outline=tema.DORADO, width=1, tags="fondo")
        for (fx, fy, r) in ((0.12, 0.78, 5), (0.16, 0.84, 3), (0.86, 0.18, 6), (0.81, 0.13, 3), (0.91, 0.26, 2)):
            cv.create_oval(w * fx - r, h * fy - r, w * fx + r, h * fy + r,
                           fill=tema.DORADO, outline="", tags="fondo")

        # Pie de página
        cv.create_text(w / 2, h - 26, text="Bill Zen ERP  ·  Facturación, inventario y contabilidad en un solo lugar",
                       fill="#A9C9BC", font=(tema.FUENTE, 10), tags="fondo")
        cv.create_text(w / 2, h - 46, text="🔒  Tus datos se guardan de forma local y segura en este equipo",
                       fill="#7FAF9C", font=(tema.FUENTE, 9), tags="fondo")

        cv.tag_lower("fondo")
        cv.coords(self._id_tarjeta, w / 2, h / 2 - 12)
        self._dibujar_sombra()

    def _dibujar_sombra(self):
        cv = self.lienzo
        if not cv.winfo_exists():
            return
        cv.delete("sombra")
        caja = cv.bbox(self._id_tarjeta)
        if not caja:
            return
        x1, y1, x2, y2 = caja
        base = cv.winfo_height() / 2 if cv.winfo_height() > 1 else y2
        fondo_local = _mezclar(tema.VERDE_PROFUNDO, "#15624B", min(1.0, max(0.0, base / max(cv.winfo_height(), 1))))
        for i, t in enumerate((0.55, 0.40, 0.25, 0.12), start=1):
            color = _mezclar(fondo_local, "#03140F", t)
            cv.create_rectangle(x1 - i + 2, y1 + i + 2, x2 + i + 2, y2 + i * 2 + 2,
                                fill=color, outline="", tags="sombra")
        cv.tag_raise("sombra")
        cv.tag_lower("sombra")
        if cv.find_withtag("fondo"):
            cv.tag_lower("fondo")

    # ==================================================================
    # COMPONENTES VISUALES DEL FORMULARIO
    # ==================================================================
    def _limpiar_tarjeta(self):
        for w in self.c.winfo_children():
            w.destroy()

    def _titulo(self, texto: str, subtitulo: str = "", compacto: bool = False):
        # Separador invisible que fija el ancho del formulario
        tk.Frame(self.c, bg=tema.BLANCO, width=ANCHO_FORM, height=0).pack()
        tk.Label(self.c, text=texto, bg=tema.BLANCO, fg=tema.VERDE_OSCURO,
                 font=(tema.FUENTE, 15 if compacto else 17, "bold"), anchor=W).pack(fill=X)
        if subtitulo:
            tk.Label(self.c, text=subtitulo, bg=tema.BLANCO, fg=tema.GRIS, font=(tema.FUENTE, 10),
                     wraplength=ANCHO_FORM, justify=LEFT, anchor=W).pack(fill=X, pady=(2, 6 if compacto else 12))

    def _campo(self, etiqueta: str, icono: str, ocultar: bool = False, compacto: bool = False) -> tk.Entry:
        """Campo con etiqueta, icono y borde que se ilumina al enfocar."""
        tk.Label(self.c, text=etiqueta, bg=tema.BLANCO, fg=tema.TEXTO, font=(tema.FUENTE, 10, "bold"),
                 wraplength=ANCHO_FORM, justify=LEFT, anchor=W).pack(fill=X, pady=(3 if compacto else 6, 2 if compacto else 4))
        caja = tk.Frame(self.c, bg="#F8FAF9", highlightthickness=1,
                        highlightbackground=tema.BEIGE_OSCURO, highlightcolor=tema.VERDE)
        caja.pack(fill=X, pady=(0, 2 if compacto else 4))
        lbl_icono = tk.Label(caja, text=icono, bg="#F8FAF9", fg=tema.VERDE, font=(tema.FUENTE, 11 if compacto else 12), width=2)
        lbl_icono.pack(side=LEFT, padx=(10, 2))
        entrada = tk.Entry(caja, relief="flat", bd=0, bg="#F8FAF9", fg=tema.TEXTO,
                           insertbackground=tema.VERDE, font=(tema.FUENTE, 11),
                           show="●" if ocultar else "")
        entrada.pack(side=LEFT, fill=X, expand=YES, ipady=5 if compacto else 9, padx=(4, 10))

        widgets_fondo = [caja, lbl_icono, entrada]
        if ocultar:
            ojo = tk.Label(caja, text="👁", bg="#F8FAF9", fg=tema.GRIS, font=(tema.FUENTE, 11), cursor="hand2")
            ojo.pack(side=RIGHT, padx=(0, 10))
            widgets_fondo.append(ojo)

            def _alternar(_e=None):
                visible = entrada.cget("show") == ""
                entrada.configure(show="●" if visible else "")
                ojo.configure(fg=tema.GRIS if visible else tema.VERDE)

            ojo.bind("<Button-1>", _alternar)

        def _enfocar(_e=None):
            caja.configure(highlightbackground=tema.VERDE, highlightthickness=2)
            for wdg in widgets_fondo:
                wdg.configure(bg=tema.BLANCO)

        def _desenfocar(_e=None):
            caja.configure(highlightbackground=tema.BEIGE_OSCURO, highlightthickness=1)
            for wdg in widgets_fondo:
                wdg.configure(bg="#F8FAF9")

        entrada.bind("<FocusIn>", _enfocar, add="+")
        entrada.bind("<FocusOut>", _desenfocar, add="+")
        caja.bind("<Button-1>", lambda _e: entrada.focus_set())
        lbl_icono.bind("<Button-1>", lambda _e: entrada.focus_set())
        return entrada

    def _area_mensaje(self, compacto: bool = False):
        """Caja de mensajes de altura FIJA: mostrar un error nunca agranda la tarjeta."""
        alto = 52 if compacto else ALTO_MENSAJE
        self._caja_msg = tk.Frame(self.c, bg=tema.BLANCO, height=alto, width=ANCHO_FORM,
                                  highlightthickness=1, highlightbackground=tema.BLANCO)
        self._caja_msg.pack(fill=X, pady=(4 if compacto else 8, 4 if compacto else 6))
        self._caja_msg.pack_propagate(False)
        self.lbl_error = tk.Label(self._caja_msg, text="", bg=tema.BLANCO, fg=tema.ROJO,
                                  font=(tema.FUENTE, 10), wraplength=ANCHO_FORM - 24,
                                  justify=LEFT, anchor=W)
        self.lbl_error.pack(fill=BOTH, expand=YES, padx=10, pady=2)

    def _mostrar_mensaje(self, texto: str = "", tipo: str = "error"):
        if not texto:
            self._caja_msg.configure(bg=tema.BLANCO, highlightbackground=tema.BLANCO)
            self.lbl_error.configure(text="", bg=tema.BLANCO)
            return
        bg, fg, borde, icono = _COLORES_MENSAJE.get(tipo, _COLORES_MENSAJE["error"])
        self._caja_msg.configure(bg=bg, highlightbackground=borde)
        self.lbl_error.configure(text=f"{icono}  {texto}", bg=bg, fg=fg,
                                 font=(tema.FUENTE, 10, "bold" if tipo != "error" else "normal"))

    def _enlace(self, texto: str, comando):
        lbl = tk.Label(self.c, text=texto, bg=tema.BLANCO, fg=tema.VERDE, font=(tema.FUENTE, 10, "underline"),
                       cursor="hand2", wraplength=ANCHO_FORM)
        lbl.pack(pady=(10, 0))
        lbl.bind("<Button-1>", lambda _e: comando())
        lbl.bind("<Enter>", lambda _e: lbl.configure(fg=tema.DORADO))
        lbl.bind("<Leave>", lambda _e: lbl.configure(fg=tema.VERDE))
        return lbl

    # ==================================================================
    # PANTALLAS
    # ==================================================================
    def _mostrar_formulario_login(self, usuario_inicial="", mensaje_exito=""):
        self._limpiar_tarjeta()
        self._titulo("Bienvenido de nuevo", "Ingresa tus credenciales para continuar")
        self.e_user = self._campo("Usuario", "👤")
        if usuario_inicial:
            self.e_user.insert(0, usuario_inicial)
        self.e_pass = self._campo("Contraseña", "🔒", ocultar=True)

        self._area_mensaje()
        self.btn = ttk.Button(self.c, text="Ingresar  →", style="Zen.TButton", command=self.ingresar,
                              padding=(16, 12), cursor="hand2")
        self.btn.pack(fill=X)
        self._enlace("¿Olvidaste tu contraseña de administrador?",
                     lambda: self._mostrar_recuperacion_usuario(self.e_user.get()))

        if mensaje_exito:
            self._mostrar_mensaje(mensaje_exito, "exito")

        if usuario_inicial:
            self.e_pass.focus_set()
        else:
            self.e_user.focus_set()
        self.e_user.bind("<Return>", lambda e: self.e_pass.focus_set())
        self.e_pass.bind("<Return>", lambda e: self.ingresar())

    def _mostrar_recuperacion_usuario(self, usuario_inicial=""):
        self._limpiar_tarjeta()
        self._titulo("Recuperar clave de admin",
                     "Ingresa tu usuario administrador para responder tus preguntas de seguridad.")
        self.e_rec_user = self._campo("Usuario administrador", "👤")
        self.e_rec_user.insert(0, (usuario_inicial or "").strip() or auth_logic.USUARIO_ADMIN_DEFECTO)

        self._area_mensaje()
        ttk.Button(self.c, text="Continuar  →", style="Zen.TButton", command=self._validar_usuario_recuperacion,
                   padding=(16, 11)).pack(fill=X, pady=(0, 6))
        ttk.Button(self.c, text="← Volver al inicio de sesión", style="Suave.TButton",
                   command=lambda: self._mostrar_formulario_login(self.e_rec_user.get()),
                   padding=(16, 10)).pack(fill=X)

        self.e_rec_user.focus_set()
        self.e_rec_user.bind("<Return>", lambda e: self._validar_usuario_recuperacion())

    def _validar_usuario_recuperacion(self):
        username = self.e_rec_user.get().strip()
        try:
            preguntas = auth_logic.obtener_preguntas_recuperacion(username)
        except ErrorValidacion as e:
            self._mostrar_mensaje(str(e), "error")
            return
        self._mostrar_recuperacion_preguntas(username, preguntas)

    def _mostrar_recuperacion_preguntas(self, username: str, preguntas: list[str]):
        self._limpiar_tarjeta()
        self._titulo("Preguntas de seguridad",
                     f"Responde las preguntas de '{username}' y define tu nueva clave.",
                     compacto=True)

        self.e_r1 = self._campo(f"1. {preguntas[0]}", "💬", compacto=True)
        self.e_r2 = self._campo(f"2. {preguntas[1]}", "💬", compacto=True)
        self.e_nueva = self._campo("Nueva clave (mín. 5 caracteres, ej. 12345)", "🔑", ocultar=True, compacto=True)
        self.e_conf = self._campo("Confirmar nueva clave", "🔑", ocultar=True, compacto=True)

        self._area_mensaje(compacto=True)
        ttk.Button(self.c, text="Restablecer contraseña", style="Oro.TButton",
                   command=lambda: self._ejecutar_recuperacion(username), padding=(14, 8)).pack(fill=X, pady=(0, 5))
        ttk.Button(self.c, text="← Cancelar y volver", style="Suave.TButton",
                   command=lambda: self._mostrar_formulario_login(username), padding=(14, 7)).pack(fill=X)

        self.e_r1.focus_set()
        self.e_r1.bind("<Return>", lambda e: self.e_r2.focus_set())
        self.e_r2.bind("<Return>", lambda e: self.e_nueva.focus_set())
        self.e_nueva.bind("<Return>", lambda e: self.e_conf.focus_set())
        self.e_conf.bind("<Return>", lambda e: self._ejecutar_recuperacion(username))

    def _ejecutar_recuperacion(self, username: str):
        try:
            auth_logic.recuperar_password_admin(
                username,
                self.e_r1.get(),
                self.e_r2.get(),
                self.e_nueva.get(),
                self.e_conf.get(),
            )
        except ErrorValidacion as e:
            self._mostrar_mensaje(str(e), "error")
            return
        self._mostrar_formulario_login(
            usuario_inicial=username,
            mensaje_exito="¡Contraseña restablecida con éxito! Ya puedes ingresar.",
        )

    def ingresar(self):
        try:
            usuario = auth_logic.iniciar_sesion(self.e_user.get(), self.e_pass.get())
        except ErrorValidacion as e:
            self._mostrar_mensaje(str(e), "error")
            self.e_pass.delete(0, END)
            self.e_pass.focus_set()
            return

        self.btn.configure(state=DISABLED, text="Cargando...")
        self._mostrar_mensaje("Estamos preparando todo para ti...", "info")
        self.update_idletasks()

        def _proceder():
            padre = self.master
            self.destroy()
            if padre:
                padre.update_idletasks()
            self.al_ingresar(usuario)

        self.after(50, _proceder)

    def destroy(self):
        if self._timer_fondo:
            try:
                self.after_cancel(self._timer_fondo)
            except Exception:
                pass
            self._timer_fondo = None
        super().destroy()
