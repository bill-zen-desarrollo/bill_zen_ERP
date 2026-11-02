"""Pantalla de inicio de sesión y recuperación de contraseña de administrador."""
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import auth_logic, empresa_logic
from logica.seguridad import ErrorValidacion
from ui import componentes as cmp
from ui import tema


class Login(ttk.Frame):
    def __init__(self, padre, al_ingresar):
        super().__init__(padre, style="Lateral.TFrame")
        self.al_ingresar = al_ingresar
        self.pack(fill=BOTH, expand=YES)

        emp = empresa_logic.obtener_empresa() or {}
        centro = ttk.Frame(self, style="Lateral.TFrame")
        centro.place(relx=0.5, rely=0.5, anchor=CENTER)

        ttk.Label(centro, text="Bill", style="Logo.TLabel", font=(tema.FUENTE_TITULO, 34, "bold")).pack()
        ttk.Label(centro, text="Zen", style="LogoZen.TLabel", font=(tema.FUENTE_CURSIVA, 36)).pack(pady=(0, 4))
        ttk.Label(centro, text=emp.get("razon_social", ""), style="Lateral.TLabel",
                  font=(tema.FUENTE, 11)).pack(pady=(0, 22))

        borde = cmp.tarjeta(centro, padding=32)
        borde.pack()
        self.c = borde.interior
        self._mostrar_formulario_login()

    def _limpiar_tarjeta(self):
        for w in self.c.winfo_children():
            w.destroy()

    def _mostrar_formulario_login(self, usuario_inicial="", mensaje_exito=""):
        self._limpiar_tarjeta()
        c = self.c
        ttk.Label(c, text="Iniciar sesión", style="TarjetaTitulo.TLabel",
                  font=(tema.FUENTE_TITULO, 16, "bold")).pack(anchor=W)
        ttk.Label(c, text="Ingresa tus credenciales para continuar", style="Tarjeta.TLabel",
                  foreground=tema.GRIS).pack(anchor=W, pady=(0, 10))
        self.e_user = cmp.campo(c, "Usuario", ancho=34)
        if usuario_inicial:
            self.e_user.insert(0, usuario_inicial)
        self.e_pass = cmp.campo(c, "Contraseña", ancho=34, show="●")
        self.btn = ttk.Button(c, text="Ingresar", style="Zen.TButton", command=self.ingresar)
        self.btn.pack(fill=X, pady=(18, 0))

        lbl_olvido = tk.Label(
            c,
            text="¿Olvidaste tu contraseña de administrador?",
            bg=tema.BLANCO,
            fg=tema.VERDE,
            font=(tema.FUENTE, 9, "underline"),
            cursor="hand2",
        )
        lbl_olvido.pack(pady=(12, 0))
        lbl_olvido.bind("<Button-1>", lambda e: self._mostrar_recuperacion_usuario(self.e_user.get()))

        self.lbl_error = ttk.Label(c, text="", style="Tarjeta.TLabel", foreground=tema.ROJO, wraplength=320)
        self.lbl_error.pack(pady=(10, 0))
        if mensaje_exito:
            self.lbl_error.configure(text=mensaje_exito, foreground=tema.VERDE_CLARO, font=(tema.FUENTE, 9, "bold"))

        if usuario_inicial:
            self.e_pass.focus_set()
        else:
            self.e_user.focus_set()
        self.e_user.bind("<Return>", lambda e: self.e_pass.focus_set())
        self.e_pass.bind("<Return>", lambda e: self.ingresar())

    def _mostrar_recuperacion_usuario(self, usuario_inicial=""):
        self._limpiar_tarjeta()
        c = self.c
        ttk.Label(c, text="Recuperar clave de admin", style="TarjetaTitulo.TLabel",
                  font=(tema.FUENTE_TITULO, 15, "bold")).pack(anchor=W)
        ttk.Label(
            c,
            text="Ingresa tu usuario administrador para responder tus preguntas de seguridad.",
            style="Tarjeta.TLabel",
            foreground=tema.GRIS,
            wraplength=320,
        ).pack(anchor=W, pady=(2, 10))

        self.e_rec_user = cmp.campo(c, "Usuario administrador", ancho=34)
        if usuario_inicial:
            self.e_rec_user.insert(0, usuario_inicial)

        ttk.Button(c, text="Continuar  →", style="Zen.TButton", command=self._validar_usuario_recuperacion).pack(fill=X, pady=(14, 6))
        ttk.Button(c, text="← Volver al inicio de sesión", style="Suave.TButton",
                   command=lambda: self._mostrar_formulario_login(self.e_rec_user.get())).pack(fill=X)

        self.lbl_error = ttk.Label(c, text="", style="Tarjeta.TLabel", foreground=tema.ROJO, wraplength=320)
        self.lbl_error.pack(pady=(10, 0))

        self.e_rec_user.focus_set()
        self.e_rec_user.bind("<Return>", lambda e: self._validar_usuario_recuperacion())

    def _validar_usuario_recuperacion(self):
        username = self.e_rec_user.get().strip()
        try:
            preguntas = auth_logic.obtener_preguntas_recuperacion(username)
        except ErrorValidacion as e:
            self.lbl_error.configure(text=str(e), foreground=tema.ROJO)
            return
        self._mostrar_recuperacion_preguntas(username, preguntas)

    def _mostrar_recuperacion_preguntas(self, username: str, preguntas: list[str]):
        self._limpiar_tarjeta()
        c = self.c
        ttk.Label(c, text="Preguntas de seguridad", style="TarjetaTitulo.TLabel",
                  font=(tema.FUENTE_TITULO, 15, "bold")).pack(anchor=W)
        ttk.Label(
            c,
            text=f"Responde las preguntas personales de '{username}' y define tu nueva clave.",
            style="Tarjeta.TLabel",
            foreground=tema.GRIS,
            wraplength=340,
        ).pack(anchor=W, pady=(2, 8))

        self.e_r1 = cmp.campo(c, f"1. {preguntas[0]}", ancho=36)
        self.e_r2 = cmp.campo(c, f"2. {preguntas[1]}", ancho=36)
        self.e_nueva = cmp.campo(c, "Nueva contraseña (mín. 8, letras y números)", ancho=36, show="●")
        self.e_conf = cmp.campo(c, "Confirmar nueva contraseña", ancho=36, show="●")

        ttk.Button(
            c,
            text="Restablecer contraseña",
            style="Oro.TButton",
            command=lambda: self._ejecutar_recuperacion(username),
        ).pack(fill=X, pady=(14, 6))
        ttk.Button(
            c,
            text="← Cancelar y volver",
            style="Suave.TButton",
            command=lambda: self._mostrar_formulario_login(username),
        ).pack(fill=X)

        self.lbl_error = ttk.Label(c, text="", style="Tarjeta.TLabel", foreground=tema.ROJO, wraplength=340)
        self.lbl_error.pack(pady=(8, 0))

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
            self.lbl_error.configure(text=str(e), foreground=tema.ROJO)
            return
        self._mostrar_formulario_login(
            usuario_inicial=username,
            mensaje_exito="¡Contraseña restablecida con éxito! Ya puedes ingresar.",
        )

    def ingresar(self):
        try:
            usuario = auth_logic.iniciar_sesion(self.e_user.get(), self.e_pass.get())
        except ErrorValidacion as e:
            self.lbl_error.configure(text=str(e), foreground=tema.ROJO)
            self.e_pass.delete(0, END)
            return

        self.btn.configure(state=DISABLED, text="Cargando...")
        self.lbl_error.configure(text="Estamos preparando todo para ti...", foreground=tema.VERDE_OSCURO, font=(tema.FUENTE, 10, "bold"))
        self.update_idletasks()

        def _proceder():
            padre = self.master
            self.destroy()
            if padre:
                padre.update_idletasks()
            self.al_ingresar(usuario)

        self.after(50, _proceder)