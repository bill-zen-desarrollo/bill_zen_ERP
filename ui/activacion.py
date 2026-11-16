"""Pantalla de Bloqueo y Activación Online de Primer Uso por Hardware ID."""
import tkinter as tk
import webbrowser
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import licencia
from logica.seguridad import ErrorValidacion
from ui import componentes as cmp
from ui import tema


class VistaActivacion(ttk.Frame):
    def __init__(self, padre, estado_licencia: dict, al_activar):
        super().__init__(padre, style="Lateral.TFrame")
        self.estado_licencia = estado_licencia or {}
        self.al_activar = al_activar
        self.hw_id = self.estado_licencia.get("hw_id") or licencia.generar_hardware_id()
        self.pack(fill=BOTH, expand=YES)

        centro = ttk.Frame(self, style="Lateral.TFrame")
        centro.place(relx=0.5, rely=0.5, anchor=CENTER)

        ttk.Label(centro, text="Bill", style="Logo.TLabel", font=(tema.FUENTE_TITULO, 32, "bold")).pack()
        ttk.Label(centro, text="Zen", style="LogoZen.TLabel", font=(tema.FUENTE_CURSIVA, 34)).pack(pady=(0, 14))

        borde = cmp.tarjeta(centro, padding=30)
        borde.pack()
        c = borde.interior

        motivo = self.estado_licencia.get("motivo", "PRIMER_USO")
        es_alerta = motivo in ("HARDWARE_DIFERENTE", "LICENCIA_ADULTERADA")

        titulo = (
            "⚠ Verificación de Equipo Requerida"
            if es_alerta
            else "🔐 Activación de Licencia Bill Zen"
        )
        ttk.Label(
            c,
            text=titulo,
            style="TarjetaTitulo.TLabel",
            foreground=tema.ROJO if es_alerta else tema.VERDE_OSCURO,
            font=(tema.FUENTE_TITULO, 15, "bold"),
        ).pack(anchor=W)

        mensaje = self.estado_licencia.get("mensaje") or (
            "Ingresa las credenciales de tu cuenta web de Bill Zen para vincular este computador. "
            "Después de esta activación inicial, el sistema funcionará 100% sin internet."
        )
        ttk.Label(
            c,
            text=mensaje,
            style="Tarjeta.TLabel",
            foreground=tema.ROJO if es_alerta else tema.GRIS,
            wraplength=380,
            font=(tema.FUENTE, 9, "bold" if es_alerta else "normal"),
        ).pack(anchor=W, pady=(4, 12))

        # Cuadro informativo del Hardware ID físico del equipo
        marco_hw = tk.Frame(c, bg=tema.BEIGE, padx=10, pady=8)
        marco_hw.pack(fill=X, pady=(0, 10))
        tk.Label(
            marco_hw,
            text="ID DE HARDWARE DE ESTE EQUIPO (SHA-256):",
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
            font=("Consolas", 9),
        ).pack(side=LEFT)
        ttk.Button(
            fila_hw,
            text="Copiar ID",
            style="Suave.TButton",
            command=self._copiar_hw_id,
            padding=(8, 2),
        ).pack(side=RIGHT)

        self.e_email = cmp.campo(c, "Correo electrónico o NIT (Cuenta Bill Zen) *", ancho=38)
        self.e_pass = cmp.campo(c, "Contraseña *", ancho=38, show="●")

        self.btn_activar = ttk.Button(
            c,
            text="🔐 Activar y vincular este equipo",
            style="Zen.TButton",
            command=self.activar,
        )
        self.btn_activar.pack(fill=X, pady=(16, 6))

        lbl_portal = tk.Label(
            c,
            text="¿Aún no tienes una cuenta o deseas adquirir un plan? Ir a bill-zen-users.vercel.app",
            bg=tema.BLANCO,
            fg=tema.VERDE,
            font=(tema.FUENTE, 8, "underline"),
            cursor="hand2",
        )
        lbl_portal.pack(pady=(6, 0))
        lbl_portal.bind("<Button-1>", lambda e: webbrowser.open(licencia.URL_PORTAL_PLANES))

        self.lbl_error = ttk.Label(
            c,
            text="",
            style="Tarjeta.TLabel",
            foreground=tema.ROJO,
            wraplength=380,
        )
        self.lbl_error.pack(pady=(10, 0))

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
        self.lbl_error.configure(
            text="Conectando con el servidor de licencias Bill Zen...",
            foreground=tema.VERDE_OSCURO,
        )
        self.btn_activar.configure(state=DISABLED)
        self.update_idletasks()

        try:
            res = licencia.activar_licencia_online(email, password, self.hw_id)
        except ErrorValidacion as e:
            self.btn_activar.configure(state=NORMAL)
            self.lbl_error.configure(text=str(e), foreground=tema.ROJO)
            return

        plan_txt = (res.get("plan") or "basico").upper()
        cmp.toast(self, f"¡Equipo activado con éxito! Plan activo: {plan_txt}")
        padre = self.master
        self.destroy()
        if padre:
            padre.update_idletasks()
        self.al_activar()
