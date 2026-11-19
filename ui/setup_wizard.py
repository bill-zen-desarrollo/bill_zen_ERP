"""Asistente inicial simplificado: asigna la clave al usuario por defecto 'administrador' y sus preguntas de seguridad.

Diseño unificado con Login y Activación: fondo con degradado verde corporativo y
decoraciones, tarjeta flotante con sombra, cabecera de marca con datos de la empresa
vinculada, campos en 2 columnas con iconos y un área de mensajes de altura fija
para que el modal nunca cambie de tamaño al mostrar errores.
"""
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import auth_logic, empresa_logic, licencia
from logica.seguridad import ErrorPermiso, ErrorValidacion
from ui import componentes as cmp
from ui import tema

ANCHO_FORM = 620          # ancho útil fijo del formulario de configuración inicial (px)
ALTO_MENSAJE = 48         # alto reservado fijo para mensajes de validación

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


class AsistenteInicial(ttk.Frame):
    def __init__(self, padre, al_terminar):
        super().__init__(padre, style="Lateral.TFrame")
        self.al_terminar = al_terminar
        self._timer_fondo = None
        self.pack(fill=BOTH, expand=YES)

        # Garantizar que la tabla `empresa` tenga los datos sincronizados desde la licencia web
        if not empresa_logic.empresa_registrada():
            est = licencia.verificar_licencia_local()
            licencia._sincronizar_empresa_local(
                {"email": est.get("email") or ""},
                est.get("email") or "",
            )

        self.emp = empresa_logic.obtener_empresa() or {}

        # ── Lienzo de fondo con degradado ───────────────────────────────
        self.lienzo = tk.Canvas(self, highlightthickness=0, bd=0, bg=tema.VERDE_PROFUNDO)
        self.lienzo.pack(fill=BOTH, expand=YES)

        # ── Tarjeta flotante ─────────────────────────────────────────────
        self.tarjeta = tk.Frame(self.lienzo, bg=tema.BLANCO)
        tk.Frame(self.tarjeta, bg=tema.DORADO, height=4).pack(fill=X)

        cab = tk.Frame(self.tarjeta, bg=tema.VERDE, padx=32, pady=14)
        cab.pack(fill=X)
        fila_logo = tk.Frame(cab, bg=tema.VERDE)
        fila_logo.pack(fill=X)
        tk.Label(
            fila_logo,
            text="Bill",
            bg=tema.VERDE,
            fg=tema.BLANCO,
            font=(tema.FUENTE, 22, "bold"),
        ).pack(side=LEFT)
        tk.Label(
            fila_logo,
            text=" Zen",
            bg=tema.VERDE,
            fg=tema.DORADO_CLARO,
            font=(tema.FUENTE_CURSIVA, 22),
        ).pack(side=LEFT)

        tk.Label(
            fila_logo,
            text="PASO 2 DE 2  ·  CUENTA ADMINISTRADOR",
            bg=tema.VERDE_PROFUNDO,
            fg=tema.DORADO_CLARO,
            font=(tema.FUENTE, 8, "bold"),
            padx=10,
            pady=3,
        ).pack(side=RIGHT, pady=(4, 0))

        razon = self.emp.get("razon_social") or "Mi Empresa Bill Zen"
        nit_txt = f"NIT: {self.emp.get('nit')}" if self.emp.get("nit") else ""
        sub_emp = f"🏢 {razon}   {('·   ' + nit_txt) if nit_txt else ''}"
        tk.Label(
            cab,
            text=sub_emp,
            bg=tema.VERDE,
            fg="#D7E6DF",
            font=(tema.FUENTE, 10),
            wraplength=ANCHO_FORM,
            justify=LEFT,
            anchor=W,
        ).pack(anchor=W, pady=(2, 0))

        self.contenedor = tk.Frame(self.tarjeta, bg=tema.BLANCO, padx=32, pady=18)
        self.contenedor.pack(fill=BOTH, expand=YES)

        self._id_tarjeta = self.lienzo.create_window(0, 0, window=self.tarjeta, anchor=CENTER)

        self.lienzo.bind("<Configure>", self._programar_fondo)
        self.tarjeta.bind("<Configure>", lambda _e: self._dibujar_sombra())

        self._construir_formulario()

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

        paso = 6
        superior, inferior = tema.VERDE_PROFUNDO, "#15624B"
        for y in range(0, h, paso):
            cv.create_rectangle(
                0,
                y,
                w,
                y + paso,
                fill=_mezclar(superior, inferior, y / h),
                outline="",
                tags="fondo",
            )

        cv.create_oval(-w * 0.15, -h * 0.35, w * 0.35, h * 0.45, outline="#1E7A5E", width=2, tags="fondo")
        cv.create_oval(-w * 0.08, -h * 0.25, w * 0.27, h * 0.33, outline="#196A52", width=1, tags="fondo")
        cv.create_oval(w * 0.70, h * 0.55, w * 1.20, h * 1.40, outline="#1E7A5E", width=2, tags="fondo")
        cv.create_oval(w * 0.78, h * 0.66, w * 1.10, h * 1.25, outline=tema.DORADO, width=1, tags="fondo")
        for (fx, fy, r) in ((0.12, 0.78, 5), (0.16, 0.84, 3), (0.86, 0.18, 6), (0.81, 0.13, 3), (0.91, 0.26, 2)):
            cv.create_oval(
                w * fx - r,
                h * fy - r,
                w * fx + r,
                h * fy + r,
                fill=tema.DORADO,
                outline="",
                tags="fondo",
            )

        cv.create_text(
            w / 2,
            h - 18,
            text="Bill Zen ERP  ·  Configuración inicial única de seguridad local",
            fill="#A9C9BC",
            font=(tema.FUENTE, 9),
            tags="fondo",
        )

        cv.tag_lower("fondo")
        cv.coords(self._id_tarjeta, w / 2, h / 2 - 6)
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
        fondo_local = _mezclar(
            tema.VERDE_PROFUNDO,
            "#15624B",
            min(1.0, max(0.0, base / max(cv.winfo_height(), 1))),
        )
        for i, t in enumerate((0.55, 0.40, 0.25, 0.12), start=1):
            color = _mezclar(fondo_local, "#03140F", t)
            cv.create_rectangle(
                x1 - i + 2,
                y1 + i + 2,
                x2 + i + 2,
                y2 + i * 2 + 2,
                fill=color,
                outline="",
                tags="sombra",
            )
        cv.tag_raise("sombra")
        cv.tag_lower("sombra")
        if cv.find_withtag("fondo"):
            cv.tag_lower("fondo")

    # ==================================================================
    # COMPONENTES DEL FORMULARIO
    # ==================================================================
    def _campo_en(self, padre, etiqueta: str, icono: str, ocultar: bool = False) -> tk.Entry:
        """Campo estilizado con icono y foco iluminado dentro del contenedor indicado."""
        tk.Label(
            padre,
            text=etiqueta,
            bg=tema.BLANCO,
            fg=tema.TEXTO,
            font=(tema.FUENTE, 10, "bold"),
            anchor=W,
        ).pack(fill=X, pady=(4, 2))
        caja = tk.Frame(
            padre,
            bg="#F8FAF9",
            highlightthickness=1,
            highlightbackground=tema.BEIGE_OSCURO,
            highlightcolor=tema.VERDE,
        )
        caja.pack(fill=X, pady=(0, 2))
        lbl_icono = tk.Label(caja, text=icono, bg="#F8FAF9", fg=tema.VERDE, font=(tema.FUENTE, 11), width=2)
        lbl_icono.pack(side=LEFT, padx=(8, 2))
        entrada = tk.Entry(
            caja,
            relief="flat",
            bd=0,
            bg="#F8FAF9",
            fg=tema.TEXTO,
            insertbackground=tema.VERDE,
            font=(tema.FUENTE, 11),
            show="●" if ocultar else "",
        )
        entrada.pack(side=LEFT, fill=X, expand=YES, ipady=6, padx=(4, 8))

        widgets_fondo = [caja, lbl_icono, entrada]
        if ocultar:
            ojo = tk.Label(caja, text="👁", bg="#F8FAF9", fg=tema.GRIS, font=(tema.FUENTE, 11), cursor="hand2")
            ojo.pack(side=RIGHT, padx=(0, 8))
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

    def _area_mensaje(self):
        """Contenedor de mensajes de altura FIJA para evitar que el modal cambie de tamaño."""
        self._caja_msg = tk.Frame(
            self.contenedor,
            bg=tema.BLANCO,
            height=ALTO_MENSAJE,
            width=ANCHO_FORM,
            highlightthickness=1,
            highlightbackground=tema.BLANCO,
        )
        self._caja_msg.pack(fill=X, pady=(6, 6))
        self._caja_msg.pack_propagate(False)
        self.lbl_error = tk.Label(
            self._caja_msg,
            text="",
            bg=tema.BLANCO,
            fg=tema.ROJO,
            font=(tema.FUENTE, 10),
            wraplength=ANCHO_FORM - 24,
            justify=LEFT,
            anchor=W,
        )
        self.lbl_error.pack(fill=BOTH, expand=YES, padx=10, pady=2)

    def _mostrar_mensaje(self, texto: str = "", tipo: str = "error"):
        if not texto:
            self._caja_msg.configure(bg=tema.BLANCO, highlightbackground=tema.BLANCO)
            self.lbl_error.configure(text="", bg=tema.BLANCO)
            return
        bg, fg, borde, icono = _COLORES_MENSAJE.get(tipo, _COLORES_MENSAJE["error"])
        self._caja_msg.configure(bg=bg, highlightbackground=borde)
        self.lbl_error.configure(text=f"{icono}  {texto}", bg=bg, fg=fg)

    def _construir_formulario(self):
        c = self.contenedor
        tk.Frame(c, bg=tema.BLANCO, width=ANCHO_FORM, height=0).pack()

        tk.Label(
            c,
            text="Configura el usuario Administrador",
            bg=tema.BLANCO,
            fg=tema.VERDE_OSCURO,
            font=(tema.FUENTE, 16, "bold"),
            anchor=W,
        ).pack(fill=X)
        tk.Label(
            c,
            text=(
                "Define tu contraseña de acceso local y 2 preguntas personales de recuperación. "
                "Tus datos de empresa ya fueron sincronizados desde tu cuenta web."
            ),
            bg=tema.BLANCO,
            fg=tema.GRIS,
            font=(tema.FUENTE, 10),
            wraplength=ANCHO_FORM,
            justify=LEFT,
            anchor=W,
        ).pack(fill=X, pady=(2, 8))

        # Recuadro informativo mostrando el usuario por defecto 'administrador'
        barra_user = tk.Frame(
            c,
            bg=tema.BEIGE,
            padx=12,
            pady=7,
            highlightthickness=1,
            highlightbackground=tema.BEIGE_OSCURO,
        )
        barra_user.pack(fill=X, pady=(0, 6))
        tk.Label(
            barra_user,
            text="👤  Usuario administrador principal:",
            bg=tema.BEIGE,
            fg=tema.GRIS,
            font=(tema.FUENTE, 10),
        ).pack(side=LEFT)
        tk.Label(
            barra_user,
            text=auth_logic.USUARIO_ADMIN_DEFECTO,
            bg=tema.BEIGE,
            fg=tema.VERDE_OSCURO,
            font=(tema.FUENTE, 11, "bold"),
        ).pack(side=LEFT, padx=(8, 0))
        tk.Label(
            barra_user,
            text="✓ Licencia verificada",
            bg=tema.BEIGE,
            fg=tema.VERDE,
            font=(tema.FUENTE, 9, "bold"),
        ).pack(side=RIGHT)

        # Fila 1 (2 columnas): Clave y Confirmación
        fila_claves = tk.Frame(c, bg=tema.BLANCO)
        fila_claves.pack(fill=X)
        fila_claves.columnconfigure((0, 1), weight=1, uniform="clv")
        col_c1 = tk.Frame(fila_claves, bg=tema.BLANCO)
        col_c1.grid(row=0, column=0, sticky=EW, padx=(0, 8))
        col_c2 = tk.Frame(fila_claves, bg=tema.BLANCO)
        col_c2.grid(row=0, column=1, sticky=EW, padx=(8, 0))

        self.e_pass = self._campo_en(col_c1, "Clave de acceso * (mín. 5 caracteres)", "🔒", ocultar=True)
        self.e_pass2 = self._campo_en(col_c2, "Confirmar clave *", "🔒", ocultar=True)

        preguntas = auth_logic.PREGUNTAS_PREDEFINIDAS

        # Fila 2 (2 columnas): Pregunta 1 y Respuesta 1
        fila_p1 = tk.Frame(c, bg=tema.BLANCO)
        fila_p1.pack(fill=X, pady=(4, 0))
        fila_p1.columnconfigure(0, weight=3, uniform="p1")
        fila_p1.columnconfigure(1, weight=2, uniform="p1")
        col_p1 = tk.Frame(fila_p1, bg=tema.BLANCO)
        col_p1.grid(row=0, column=0, sticky=EW, padx=(0, 8))
        col_r1 = tk.Frame(fila_p1, bg=tema.BLANCO)
        col_r1.grid(row=0, column=1, sticky=EW, padx=(8, 0))

        tk.Label(col_p1, text="Pregunta de seguridad 1 *", bg=tema.BLANCO, fg=tema.TEXTO, font=(tema.FUENTE, 10, "bold"), anchor=W).pack(fill=X, pady=(4, 2))
        self.cb_preg1 = ttk.Combobox(col_p1, values=preguntas, state="readonly", font=(tema.FUENTE, 10))
        self.cb_preg1.current(0)
        self.cb_preg1.pack(fill=X, pady=(0, 2))
        self.e_resp1 = self._campo_en(col_r1, "Tu respuesta 1 *", "💬")

        # Fila 3 (2 columnas): Pregunta 2 y Respuesta 2
        fila_p2 = tk.Frame(c, bg=tema.BLANCO)
        fila_p2.pack(fill=X, pady=(4, 0))
        fila_p2.columnconfigure(0, weight=3, uniform="p2")
        fila_p2.columnconfigure(1, weight=2, uniform="p2")
        col_p2 = tk.Frame(fila_p2, bg=tema.BLANCO)
        col_p2.grid(row=0, column=0, sticky=EW, padx=(0, 8))
        col_r2 = tk.Frame(fila_p2, bg=tema.BLANCO)
        col_r2.grid(row=0, column=1, sticky=EW, padx=(8, 0))

        tk.Label(col_p2, text="Pregunta de seguridad 2 *", bg=tema.BLANCO, fg=tema.TEXTO, font=(tema.FUENTE, 10, "bold"), anchor=W).pack(fill=X, pady=(4, 2))
        self.cb_preg2 = ttk.Combobox(col_p2, values=preguntas, state="readonly", font=(tema.FUENTE, 10))
        self.cb_preg2.current(1)
        self.cb_preg2.pack(fill=X, pady=(0, 2))
        self.e_resp2 = self._campo_en(col_r2, "Tu respuesta 2 *", "💬")

        self._area_mensaje()

        ttk.Button(
            c,
            text="Guardar y comenzar  →",
            style="Oro.TButton",
            command=self._guardar_configuracion,
            padding=(18, 11),
            cursor="hand2",
        ).pack(fill=X)

        self.e_pass.focus_set()
        self.e_pass.bind("<Return>", lambda e: self.e_pass2.focus_set())
        self.e_pass2.bind("<Return>", lambda e: self.e_resp1.focus_set())
        self.e_resp1.bind("<Return>", lambda e: self.e_resp2.focus_set())
        self.e_resp2.bind("<Return>", lambda e: self._guardar_configuracion())

    def _guardar_configuracion(self):
        try:
            auth_logic.configurar_admin_inicial(
                self.e_pass.get(),
                self.e_pass2.get(),
                self.cb_preg1.get(),
                self.e_resp1.get(),
                self.cb_preg2.get(),
                self.e_resp2.get(),
            )
        except (ErrorValidacion, ErrorPermiso) as e:
            self._mostrar_mensaje(str(e), "error")
            return

        cmp.toast(
            self,
            f"¡Listo! Usuario '{auth_logic.USUARIO_ADMIN_DEFECTO}' configurado correctamente.",
        )
        self.destroy()
        self.al_terminar()

    def destroy(self):
        if self._timer_fondo:
            try:
                self.after_cancel(self._timer_fondo)
            except Exception:
                pass
            self._timer_fondo = None
        super().destroy()
