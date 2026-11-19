"""Pantalla de Bloqueo y Activación Online de Primer Uso por Hardware ID.

Diseño alineado con Login: fondo con degradado verde corporativo y decoraciones,
tarjeta flotante con sombra, cabecera de marca, recuadro de Hardware ID, campos con
iconos y área de mensajes de altura fija para que el modal nunca cambie de tamaño
al mostrar errores de conexión o credenciales.
"""
import tkinter as tk
import webbrowser
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import licencia
from logica.seguridad import ErrorValidacion
from ui import componentes as cmp
from ui import tema

ANCHO_FORM = 400          # ancho útil fijo del formulario de activación (px)
ALTO_MENSAJE = 64         # alto reservado fijo para mensajes (hasta 3 líneas sin crecer)

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


class VistaActivacion(ttk.Frame):
    def __init__(self, padre, estado_licencia: dict, al_activar):
        super().__init__(padre, style="Lateral.TFrame")
        self.estado_licencia = estado_licencia or {}
        self.al_activar = al_activar
        self.hw_id = self.estado_licencia.get("hw_id") or licencia.generar_hardware_id()
        self._timer_fondo = None
        self.pack(fill=BOTH, expand=YES)

        # ── Lienzo de fondo con degradado ───────────────────────────────
        self.lienzo = tk.Canvas(self, highlightthickness=0, bd=0, bg=tema.VERDE_PROFUNDO)
        self.lienzo.pack(fill=BOTH, expand=YES)

        # ── Tarjeta flotante ─────────────────────────────────────────────
        self.tarjeta = tk.Frame(self.lienzo, bg=tema.BLANCO)
        tk.Frame(self.tarjeta, bg=tema.DORADO, height=4).pack(fill=X)

        cab = tk.Frame(self.tarjeta, bg=tema.VERDE, padx=32, pady=15)
        cab.pack(fill=X)
        fila_logo = tk.Frame(cab, bg=tema.VERDE)
        fila_logo.pack(fill=X)
        tk.Label(
            fila_logo,
            text="Bill",
            bg=tema.VERDE,
            fg=tema.BLANCO,
            font=(tema.FUENTE, 23, "bold"),
        ).pack(side=LEFT)
        tk.Label(
            fila_logo,
            text=" Zen",
            bg=tema.VERDE,
            fg=tema.DORADO_CLARO,
            font=(tema.FUENTE, 23, "bold"),
        ).pack(side=LEFT)

        badge_lic = tk.Label(
            fila_logo,
            text="🔐 ACTIVACIÓN DE LICENCIA",
            bg=tema.VERDE_PROFUNDO,
            fg=tema.DORADO_CLARO,
            font=(tema.FUENTE, 8, "bold"),
            padx=9,
            pady=3,
        )
        badge_lic.pack(side=RIGHT, pady=(4, 0))

        tk.Label(
            cab,
            text="Vinculación oficial del equipo con tu suscripción en la nube",
            bg=tema.VERDE,
            fg="#D7E6DF",
            font=(tema.FUENTE, 10),
            wraplength=ANCHO_FORM,
            justify=LEFT,
            anchor=W,
        ).pack(anchor=W, pady=(2, 0))

        self.c = tk.Frame(self.tarjeta, bg=tema.BLANCO, padx=32, pady=18)
        self.c.pack(fill=BOTH, expand=YES)

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

        # Degradado vertical suave en bandas
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

        # Círculos decorativos y puntos dorados
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

        # Pie de página
        cv.create_text(
            w / 2,
            h - 18,
            text="Bill Zen ERP  ·  Protección criptográfica por Hardware ID (SHA-256)",
            fill="#A9C9BC",
            font=(tema.FUENTE, 9),
            tags="fondo",
        )

        cv.tag_lower("fondo")
        cv.coords(self._id_tarjeta, w / 2, h / 2 - 8)
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
    # COMPONENTES DEL FORMULARIO DE ACTIVACIÓN
    # ==================================================================
    def _campo(self, etiqueta: str, icono: str, ocultar: bool = False) -> tk.Entry:
        """Campo con etiqueta, icono lateral, visor opcional y borde iluminado al enfocar."""
        tk.Label(
            self.c,
            text=etiqueta,
            bg=tema.BLANCO,
            fg=tema.TEXTO,
            font=(tema.FUENTE, 10, "bold"),
            wraplength=ANCHO_FORM,
            justify=LEFT,
            anchor=W,
        ).pack(fill=X, pady=(5, 3))
        caja = tk.Frame(
            self.c,
            bg="#F8FAF9",
            highlightthickness=1,
            highlightbackground=tema.BEIGE_OSCURO,
            highlightcolor=tema.VERDE,
        )
        caja.pack(fill=X, pady=(0, 3))
        lbl_icono = tk.Label(caja, text=icono, bg="#F8FAF9", fg=tema.VERDE, font=(tema.FUENTE, 12), width=2)
        lbl_icono.pack(side=LEFT, padx=(10, 2))
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
        entrada.pack(side=LEFT, fill=X, expand=YES, ipady=7, padx=(4, 10))

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

    def _area_mensaje(self):
        """Contenedor de mensajes de altura FIJA: mostrar un error nunca cambia el tamaño del modal."""
        self._caja_msg = tk.Frame(
            self.c,
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
        self.lbl_error.configure(
            text=f"{icono}  {texto}",
            bg=bg,
            fg=fg,
            font=(tema.FUENTE, 10, "bold" if tipo != "error" else "normal"),
        )

    def _construir_formulario(self):
        c = self.c
        # Espaciador invisible que fija el ancho exacto del formulario
        tk.Frame(c, bg=tema.BLANCO, width=ANCHO_FORM, height=0).pack()

        motivo = self.estado_licencia.get("motivo", "PRIMER_USO")
        es_alerta = motivo in ("HARDWARE_DIFERENTE", "LICENCIA_ADULTERADA")

        titulo = (
            "Verificación de Equipo Requerida"
            if es_alerta
            else "Ingresa con tu cuenta de Bill Zen"
        )
        tk.Label(
            c,
            text=titulo,
            bg=tema.BLANCO,
            fg=tema.ROJO if es_alerta else tema.VERDE_OSCURO,
            font=(tema.FUENTE, 16, "bold"),
            anchor=W,
        ).pack(fill=X)

        mensaje = self.estado_licencia.get("mensaje") if es_alerta else (
            "Ingresa las credenciales con las que te registraste en la web de Bill Zen "
            "para validar tu suscripción, vincular este equipo y cargar los datos de tu empresa."
        )
        tk.Label(
            c,
            text=mensaje,
            bg=tema.BLANCO,
            fg=tema.ROJO if es_alerta else tema.GRIS,
            wraplength=ANCHO_FORM,
            justify=LEFT,
            anchor=W,
            font=(tema.FUENTE, 10, "bold" if es_alerta else "normal"),
        ).pack(fill=X, pady=(2, 8))

        # Cuadro informativo del Hardware ID físico del equipo
        marco_hw = tk.Frame(
            c,
            bg=tema.BEIGE,
            padx=12,
            pady=7,
            highlightthickness=1,
            highlightbackground=tema.BEIGE_OSCURO,
        )
        marco_hw.pack(fill=X, pady=(0, 6))
        tk.Label(
            marco_hw,
            text="🖥  ID DE HARDWARE DE ESTE EQUIPO (SHA-256):",
            bg=tema.BEIGE,
            fg=tema.VERDE_OSCURO,
            font=(tema.FUENTE, 8, "bold"),
        ).pack(anchor=W)
        fila_hw = tk.Frame(marco_hw, bg=tema.BEIGE)
        fila_hw.pack(fill=X, pady=(2, 0))
        tk.Label(
            fila_hw,
            text=f"{self.hw_id[:20]}...{self.hw_id[-12:]}",
            bg=tema.BEIGE,
            fg=tema.TEXTO,
            font=("Consolas", 10),
        ).pack(side=LEFT)
        ttk.Button(
            fila_hw,
            text="Copiar ID",
            style="Suave.TButton",
            command=self._copiar_hw_id,
            padding=(10, 3),
        ).pack(side=RIGHT)

        self.e_nit = self._campo("NIT de la empresa (Cuenta Bill Zen) *", "🏢")
        self.e_email = self.e_nit
        self.e_pass = self._campo("Contraseña *", "🔒", ocultar=True)

        self._area_mensaje()

        self.btn_activar = ttk.Button(
            c,
            text="Activar y vincular este equipo  →",
            style="Zen.TButton",
            command=self.activar,
            padding=(16, 11),
            cursor="hand2",
        )
        self.btn_activar.pack(fill=X)

        lbl_portal = tk.Label(
            c,
            text="¿Aún no tienes una cuenta o deseas adquirir un plan? Ir a bill-zen-users.vercel.app",
            bg=tema.BLANCO,
            fg=tema.VERDE,
            font=(tema.FUENTE, 9, "underline"),
            cursor="hand2",
            wraplength=ANCHO_FORM,
        )
        lbl_portal.pack(pady=(8, 0))
        lbl_portal.bind("<Button-1>", lambda e: webbrowser.open(licencia.URL_PORTAL_PLANES))
        lbl_portal.bind("<Enter>", lambda _e: lbl_portal.configure(fg=tema.DORADO))
        lbl_portal.bind("<Leave>", lambda _e: lbl_portal.configure(fg=tema.VERDE))

        self.e_email.focus_set()
        self.e_email.bind("<Return>", lambda e: self.e_pass.focus_set())
        self.e_pass.bind("<Return>", lambda e: self.activar())

    def _copiar_hw_id(self):
        self.clipboard_clear()
        self.clipboard_append(self.hw_id)
        cmp.toast(self, "Hardware ID copiado al portapapeles")

    def activar(self):
        email = self.e_email.get().strip()
        password = self.e_pass.get()
        self._mostrar_mensaje("Conectando con el servidor de licencias Bill Zen...", "info")
        self.btn_activar.configure(state=DISABLED)
        self.update_idletasks()

        try:
            res = licencia.activar_licencia_online(email, password, self.hw_id)
        except ErrorValidacion as e:
            self.btn_activar.configure(state=NORMAL)
            self._mostrar_mensaje(str(e), "error")
            return

        plan_txt = (res.get("plan") or "basico").upper()
        cmp.toast(self, f"¡Equipo activado con éxito! Plan activo: {plan_txt}")
        padre = self.master
        self.destroy()
        if padre:
            padre.update_idletasks()
        self.al_activar()

    def destroy(self):
        if self._timer_fondo:
            try:
                self.after_cancel(self._timer_fondo)
            except Exception:
                pass
            self._timer_fondo = None
        super().destroy()
