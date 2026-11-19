"""Configuración: datos locales de la empresa (con bloqueo de NIT/Razón Social/Correo de Neon.tech),
cambio de clave de administrador, preguntas de seguridad y copia de seguridad."""
import os
import sqlite3
import tkinter as tk
from datetime import datetime
from tkinter import filedialog

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from database.conexion import ruta_db
from logica import auth_logic as al
from logica import empresa_logic as el
from logica import respaldo as respaldo_auto
from logica import usuarios_logic as ul
from logica.seguridad import ErrorValidacion, Sesion, auditar
from ui import componentes as cmp
from ui import tema


class Vista(ttk.Frame):
    CAMPOS_LOCALES = (
        ("direccion", "Dirección"),
        ("telefono", "Teléfono"),
        ("regimen", "Régimen"),
        ("prefijo_factura", "Prefijo de factura"),
    )

    def __init__(self, padre, principal):
        super().__init__(padre)
        cmp.encabezado(
            self,
            "Configuración",
            "Completa la información local de la empresa, gestiona la clave de administrador y tus copias de seguridad",
        ).pack(anchor=W, pady=(0, 12))

        cols = ttk.Frame(self)
        cols.pack(fill=BOTH, expand=YES)
        for i in range(3 if Sesion.es_admin() else 2):
            cols.columnconfigure(i, weight=1, uniform="cfg")
        cols.rowconfigure(0, weight=1)

        # ================== COLUMNA 1: DATOS DE LA EMPRESA ==================
        b1 = cmp.tarjeta(cols, padding=20)
        b1.grid(row=0, column=0, sticky=NSEW, padx=(0, 12))
        c = b1.interior
        ttk.Label(c, text="Datos de la empresa", style="TarjetaTitulo.TLabel").pack(anchor=W, pady=(0, 6))

        emp = el.obtener_empresa() or {}

        # Recuadro de solo lectura para datos sincronizados con Neon.tech
        marco_nube = tk.Frame(
            c,
            bg=tema.BEIGE,
            padx=12,
            pady=8,
            highlightthickness=1,
            highlightbackground=tema.BEIGE_OSCURO,
        )
        marco_nube.pack(fill=X, pady=(0, 8))
        tk.Label(
            marco_nube,
            text="🔒 SINCRONIZADOS CON TU CUENTA (NEON.TECH)",
            bg=tema.BEIGE,
            fg=tema.VERDE_OSCURO,
            font=(tema.FUENTE, 8, "bold"),
        ).pack(anchor=W, pady=(0, 4))

        for etq_nube, val_nube in (
            ("Razón social:", emp.get("razon_social") or "—"),
            ("NIT:", emp.get("nit") or "—"),
            ("Correo:", emp.get("correo") or "—"),
        ):
            fila_n = tk.Frame(marco_nube, bg=tema.BEIGE)
            fila_n.pack(fill=X, pady=1)
            tk.Label(
                fila_n,
                text=etq_nube,
                bg=tema.BEIGE,
                fg=tema.GRIS,
                font=(tema.FUENTE, 9, "bold"),
                width=12,
                anchor="w",
            ).pack(side=LEFT)
            tk.Label(
                fila_n,
                text=val_nube,
                bg=tema.BEIGE,
                fg=tema.TEXTO,
                font=(tema.FUENTE, 10, "bold"),
                anchor="w",
            ).pack(side=LEFT, fill=X, expand=YES)

        # Banner dinámico de datos pendientes ("Termina de completar la información")
        self.marco_pendientes = tk.Frame(
            c,
            bg=tema.SYNC_AMBAR_BG,
            padx=12,
            pady=8,
            highlightthickness=1,
            highlightbackground=tema.SYNC_AMBAR_BORDE,
        )
        self.marco_pendientes.pack(fill=X, pady=(0, 6))
        self.lbl_titulo_pend = tk.Label(
            self.marco_pendientes,
            text="",
            bg=tema.SYNC_AMBAR_BG,
            fg=tema.SYNC_AMBAR_FG,
            font=(tema.FUENTE, 10, "bold"),
            anchor="w",
            justify=LEFT,
        )
        self.lbl_titulo_pend.pack(fill=X)
        self.lbl_detalle_pend = tk.Label(
            self.marco_pendientes,
            text="",
            bg=tema.SYNC_AMBAR_BG,
            fg=tema.SYNC_AMBAR_FG,
            font=(tema.FUENTE, 9),
            anchor="w",
            justify=LEFT,
            wraplength=280,
        )
        self.lbl_detalle_pend.pack(fill=X, pady=(2, 0))

        # Campos locales editables
        self.campos = {}
        self.etiquetas_campos = {}
        for clave, etiqueta in self.CAMPOS_LOCALES:
            e = cmp.campo(c, etiqueta, ancho=26)
            e.insert(0, emp.get(clave) or "")
            self.campos[clave] = e
            # Guardar referencia al Label del campo para resaltar si está pendiente
            for hijo in e.marco.winfo_children():
                if isinstance(hijo, ttk.Label):
                    self.etiquetas_campos[clave] = (hijo, etiqueta)
                    break

        self._actualizar_estado_pendientes(emp)

        ttk.Button(
            c,
            text="Guardar información local",
            style="Zen.TButton",
            command=self.guardar_empresa,
            padding=(12, 9),
        ).pack(fill=X, pady=(10, 0))

        # ================== COLUMNA 2: CLAVE DE ADMIN Y RESPALDO ==================
        der = ttk.Frame(cols)
        der.grid(row=0, column=1, sticky=NSEW, padx=(0, 12 if Sesion.es_admin() else 0))
        b2 = cmp.tarjeta(der, padding=20)
        b2.pack(fill=X)
        c2 = b2.interior
        ttk.Label(c2, text="Cambiar clave de administrador", style="TarjetaTitulo.TLabel").pack(anchor=W)
        ttk.Label(
            c2,
            text="Actualiza la clave local del rol Administrador ('administrador') en este equipo.",
            style="Tarjeta.TLabel",
            foreground=tema.GRIS,
            wraplength=280,
            font=(tema.FUENTE, 9),
        ).pack(anchor=W, pady=(2, 6))
        self.p_actual = cmp.campo(c2, "Clave actual de administrador", ancho=26, show="●")
        self.p_nueva = cmp.campo(c2, "Nueva clave de administrador", ancho=26, show="●")
        self.p_conf = cmp.campo(c2, "Confirmar nueva clave", ancho=26, show="●")
        ttk.Button(
            c2,
            text="Cambiar clave de administrador",
            style="Oro.TButton",
            command=self.cambiar_pass,
            padding=(12, 9),
        ).pack(fill=X, pady=(8, 0))

        b3 = cmp.tarjeta(der, padding=20)
        b3.pack(fill=BOTH, expand=YES, pady=(12, 0))
        c3 = b3.interior
        ttk.Label(c3, text="Copia de seguridad", style="TarjetaTitulo.TLabel").pack(anchor=W)
        ttk.Label(
            c3,
            text="Guarda una copia de toda tu información en la ubicación que elijas (USB, nube, etc.).",
            style="Tarjeta.TLabel",
            foreground=tema.GRIS,
            wraplength=280,
            font=(tema.FUENTE, 10),
        ).pack(anchor=W, pady=6)
        ttk.Button(c3, text="Crear copia de seguridad", style="Zen.TButton", command=self.respaldo, padding=(12, 9)).pack(fill=X)
        ttk.Label(
            c3,
            text=f"Además, al cerrar el programa se guarda una copia automática semanal (se conservan las últimas {respaldo_auto.MAX_COPIAS} semanas).",
            style="Tarjeta.TLabel",
            foreground=tema.VERDE_CLARO,
            wraplength=280,
            font=(tema.FUENTE, 9, "italic"),
        ).pack(anchor=W, pady=(8, 4))
        ttk.Button(
            c3,
            text="Abrir carpeta de copias automáticas",
            style="Suave.TButton",
            command=lambda: os.startfile(respaldo_auto.carpeta_respaldos()),
            padding=(12, 8),
        ).pack(fill=X)
        ttk.Label(
            c3,
            text=f"Base de datos: {ruta_db()}",
            style="Tarjeta.TLabel",
            foreground=tema.GRIS,
            wraplength=280,
            font=(tema.FUENTE, 8),
        ).pack(anchor=W, pady=(6, 0))

        # ================== COLUMNA 3: PREGUNTAS DE SEGURIDAD ==================
        if Sesion.es_admin():
            b4 = cmp.tarjeta(cols, padding=20)
            b4.grid(row=0, column=2, sticky=NSEW)
            c4 = b4.interior
            ttk.Label(c4, text="Preguntas de seguridad", style="TarjetaTitulo.TLabel").pack(anchor=W)
            ttk.Label(
                c4,
                text="Se usan para recuperar tu clave de administrador desde la pantalla de inicio de sesión.",
                style="Tarjeta.TLabel",
                foreground=tema.GRIS,
                wraplength=290,
                font=(tema.FUENTE, 10),
            ).pack(anchor=W, pady=(4, 8))

            actuales = al.obtener_preguntas_admin_actual()
            preguntas = al.PREGUNTAS_PREDEFINIDAS

            ttk.Label(c4, text="Pregunta 1", style="FormLabel.TLabel").pack(anchor=W, pady=(6, 3))
            self.cb_preg1 = ttk.Combobox(c4, values=preguntas, state="readonly", width=28, font=(tema.FUENTE, 11))
            self.cb_preg1.set(actuales[0] if len(actuales) >= 1 else preguntas[0])
            self.cb_preg1.pack(fill=X, pady=(0, 4))
            self.e_resp1 = cmp.campo(c4, "Nueva respuesta 1", ancho=26)

            ttk.Label(c4, text="Pregunta 2", style="FormLabel.TLabel").pack(anchor=W, pady=(6, 3))
            self.cb_preg2 = ttk.Combobox(c4, values=preguntas, state="readonly", width=28, font=(tema.FUENTE, 11))
            self.cb_preg2.set(actuales[1] if len(actuales) >= 2 else preguntas[1])
            self.cb_preg2.pack(fill=X, pady=(0, 4))
            self.e_resp2 = cmp.campo(c4, "Nueva respuesta 2", ancho=26)

            ttk.Button(
                c4,
                text="Guardar preguntas",
                style="Zen.TButton",
                command=self.guardar_preguntas,
                padding=(12, 9),
            ).pack(fill=X, pady=(10, 0))

    def _actualizar_estado_pendientes(self, emp: dict | None = None):
        datos = emp if emp is not None else {k: e.get() for k, e in self.campos.items()}
        pendientes = el.campos_pendientes_empresa(datos)

        for clave, (lbl_w, etq_base) in self.etiquetas_campos.items():
            falta = not str(datos.get(clave) or "").strip()
            if falta:
                lbl_w.configure(text=f"{etq_base}  (Pendiente *)", foreground=tema.AMBAR)
            else:
                lbl_w.configure(text=etq_base, foreground=tema.TEXTO)

        if pendientes:
            bg, fg, borde = tema.SYNC_AMBAR_BG, tema.SYNC_AMBAR_FG, tema.SYNC_AMBAR_BORDE
            self.marco_pendientes.configure(bg=bg, highlightbackground=borde)
            self.lbl_titulo_pend.configure(
                text="⚠ Termina de completar la información",
                bg=bg,
                fg=fg,
            )
            self.lbl_detalle_pend.configure(
                text=f"Datos pendientes: {', '.join(pendientes)}",
                bg=bg,
                fg=fg,
            )
        else:
            bg, fg, borde = tema.SYNC_VERDE_BG, tema.SYNC_VERDE_FG, tema.SYNC_VERDE_BORDE
            self.marco_pendientes.configure(bg=bg, highlightbackground=borde)
            self.lbl_titulo_pend.configure(
                text="✓ Información de la empresa completa",
                bg=bg,
                fg=fg,
            )
            self.lbl_detalle_pend.configure(
                text="Todos los datos para el encabezado de tus facturas y tirillas están configurados.",
                bg=bg,
                fg=fg,
            )

    def guardar_empresa(self):
        datos_locales = {k: e.get() for k, e in self.campos.items()}
        try:
            el.actualizar_empresa(datos_locales)
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)
        self._actualizar_estado_pendientes(el.obtener_empresa() or datos_locales)
        cmp.toast(self, "Información local de la empresa actualizada")

    def cambiar_pass(self):
        try:
            ul.cambiar_mi_password(self.p_actual.get(), self.p_nueva.get(), self.p_conf.get())
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)
        for e in (self.p_actual, self.p_nueva, self.p_conf):
            e.delete(0, END)
        cmp.toast(self, "Clave de administrador actualizada")

    def guardar_preguntas(self):
        try:
            al.guardar_preguntas_admin(
                self.cb_preg1.get(),
                self.e_resp1.get(),
                self.cb_preg2.get(),
                self.e_resp2.get(),
            )
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)
        for e in (self.e_resp1, self.e_resp2):
            e.delete(0, END)
        cmp.toast(self, "Preguntas de seguridad actualizadas")

    def respaldo(self):
        destino = filedialog.asksaveasfilename(
            defaultextension=".db",
            initialfile=f"bill_zen_respaldo_{datetime.now():%Y%m%d_%H%M}.db",
            filetypes=[("Copia Bill Zen", "*.db")],
        )
        if not destino:
            return
        with sqlite3.connect(ruta_db()) as origen, sqlite3.connect(destino) as copia:
            origen.backup(copia)
        auditar("COPIA_SEGURIDAD", os.path.basename(destino))
        cmp.toast(self, "Copia de seguridad creada")
