"""Asistente inicial simplificado: asigna la clave al usuario por defecto 'administrador' y sus preguntas de seguridad.

Los datos de la empresa (NIT, razón social, correo) ya fueron sincronizados automáticamente
en la tabla `empresa` de SQLite al validar las credenciales de `bill_zen_users`.
"""
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import auth_logic, empresa_logic, licencia
from logica.seguridad import ErrorPermiso, ErrorValidacion
from ui import componentes as cmp
from ui import tema


class AsistenteInicial(ttk.Frame):
    def __init__(self, padre, al_terminar):
        super().__init__(padre, style="Lateral.TFrame")
        self.al_terminar = al_terminar
        self.pack(fill=BOTH, expand=YES)

        # Garantizar que la tabla `empresa` tenga los datos sincronizados desde la licencia web
        if not empresa_logic.empresa_registrada():
            est = licencia.verificar_licencia_local()
            licencia._sincronizar_empresa_local(
                {"email": est.get("email") or ""},
                est.get("email") or "",
            )

        emp = empresa_logic.obtener_empresa() or {}

        izq = ttk.Frame(self, style="Lateral.TFrame", padding=40, width=380)
        izq.pack(side=LEFT, fill=Y)
        izq.pack_propagate(False)
        ttk.Label(izq, text="Bill", style="Logo.TLabel").pack(anchor=W, pady=(50, 0))
        ttk.Label(izq, text="Zen", style="LogoZen.TLabel").pack(anchor=W)
        ttk.Label(
            izq,
            text="Sistema ERP para pymes",
            style="Lateral.TLabel",
            font=(tema.FUENTE, 11),
        ).pack(anchor=W, pady=(8, 28))

        if emp.get("razon_social"):
            tarjeta_emp = tk.Frame(izq, bg=tema.VERDE, padx=14, pady=12)
            tarjeta_emp.pack(fill=X, pady=(0, 24))
            tk.Label(
                tarjeta_emp,
                text="EMPRESA VINCULADA",
                bg=tema.VERDE,
                fg=tema.DORADO_CLARO,
                font=(tema.FUENTE, 8, "bold"),
            ).pack(anchor=W)
            tk.Label(
                tarjeta_emp,
                text=emp.get("razon_social", ""),
                bg=tema.VERDE,
                fg=tema.BEIGE,
                font=(tema.FUENTE, 11, "bold"),
                wraplength=260,
                justify=LEFT,
            ).pack(anchor=W, pady=(2, 0))
            detalles_emp = f"NIT: {emp.get('nit', '')}"
            if emp.get("correo"):
                detalles_emp += f"\n{emp.get('correo')}"
            tk.Label(
                tarjeta_emp,
                text=detalles_emp,
                bg=tema.VERDE,
                fg=tema.BEIGE,
                font=(tema.FUENTE, 9),
                justify=LEFT,
            ).pack(anchor=W, pady=(2, 0))

        pasos = (
            ("1", "Cuenta Bill Zen vinculada", False),
            ("2", "Clave de administrador y preguntas", True),
        )
        for num, texto, activo in pasos:
            f = ttk.Frame(izq, style="Lateral.TFrame")
            f.pack(fill=X, pady=8)
            color = tema.DORADO_CLARO if activo else tema.BEIGE
            ttk.Label(
                f,
                text=num,
                style="Lateral.TLabel",
                foreground=color,
                font=(tema.FUENTE, 13, "bold"),
            ).pack(side=LEFT, padx=(0, 12))
            ttk.Label(
                f,
                text=texto,
                style="Lateral.TLabel",
                foreground=color,
                font=(tema.FUENTE, 11, "bold" if activo else "normal"),
            ).pack(side=LEFT)

        der = ttk.Frame(self, padding=(48, 28))
        der.pack(side=LEFT, fill=BOTH, expand=YES)
        card_der = cmp.tarjeta(der, padding=24)
        card_der.pack(fill=BOTH, expand=YES)
        self.contenedor = card_der.interior

        self._construir_formulario()

    def _construir_formulario(self):
        ttk.Label(
            self.contenedor,
            text="Configura el usuario Administrador",
            style="TarjetaTitulo.TLabel",
            font=(tema.FUENTE, 20, "bold"),
        ).pack(anchor=W)
        ttk.Label(
            self.contenedor,
            text=(
                "Los datos de tu empresa ya fueron cargados desde tu cuenta web de Bill Zen. "
                "Tu usuario de acceso principal será por defecto 'administrador': "
                "asígnale una contraseña local y elige 2 preguntas de seguridad por si llegas a olvidarla."
            ),
            style="Tarjeta.TLabel",
            foreground=tema.GRIS,
            font=(tema.FUENTE, 11),
            wraplength=680,
        ).pack(anchor=W, pady=(4, 12))

        # Recuadro informativo mostrando el usuario por defecto 'administrador'
        barra_user = tk.Frame(self.contenedor, bg=tema.BEIGE, padx=14, pady=10, highlightthickness=1, highlightbackground=tema.BEIGE_OSCURO)
        barra_user.pack(fill=X, pady=(0, 10))
        tk.Label(
            barra_user,
            text="Usuario administrador por defecto:",
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

        self.e_pass = cmp.campo(
            self.contenedor,
            "Clave de acceso para 'administrador' * (mínimo 5 dígitos / caracteres, ej. 12345)",
            show="●",
            estilo_label="Tarjeta.TLabel",
        )
        self.e_pass2 = cmp.campo(
            self.contenedor,
            "Confirmar clave *",
            show="●",
            estilo_label="Tarjeta.TLabel",
        )

        preguntas = auth_logic.PREGUNTAS_PREDEFINIDAS

        ttk.Label(
            self.contenedor,
            text="Pregunta de seguridad 1 *",
            style="FormLabel.TLabel",
        ).pack(anchor=W, pady=(8, 4))
        self.cb_preg1 = ttk.Combobox(self.contenedor, values=preguntas, state="readonly", font=(tema.FUENTE, 11))
        self.cb_preg1.current(0)
        self.cb_preg1.pack(fill=X, pady=(0, 4))
        self.e_resp1 = cmp.campo(self.contenedor, "Tu respuesta 1 *", estilo_label="Tarjeta.TLabel")

        ttk.Label(
            self.contenedor,
            text="Pregunta de seguridad 2 *",
            style="FormLabel.TLabel",
        ).pack(anchor=W, pady=(6, 4))
        self.cb_preg2 = ttk.Combobox(self.contenedor, values=preguntas, state="readonly", font=(tema.FUENTE, 11))
        self.cb_preg2.current(1)
        self.cb_preg2.pack(fill=X, pady=(0, 4))
        self.e_resp2 = cmp.campo(self.contenedor, "Tu respuesta 2 *", estilo_label="Tarjeta.TLabel")

        ttk.Button(
            self.contenedor,
            text="Guardar y comenzar",
            style="Oro.TButton",
            command=self._guardar_configuracion,
        ).pack(anchor=E, pady=(14, 0))

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
            cmp.mostrar_error(self, e)
            return

        cmp.mostrar_info(
            self,
            f"¡Listo! El usuario '{auth_logic.USUARIO_ADMIN_DEFECTO}' y sus preguntas de seguridad fueron configurados. Ahora inicia sesión.",
        )
        self.destroy()
        self.al_terminar()
