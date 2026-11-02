"""Configuración: datos de la empresa, cambio de contraseña, preguntas de seguridad y copia de seguridad."""
import os
import shutil
import sqlite3
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
    def __init__(self, padre, principal):
        super().__init__(padre)
        cmp.encabezado(self, "Configuración", "Datos de la empresa, seguridad y copias de seguridad").pack(anchor=W, pady=(0, 12))
        cols = ttk.Frame(self)
        cols.pack(fill=BOTH, expand=YES)

        b1 = cmp.tarjeta(cols, padding=20)
        b1.pack(side=LEFT, fill=Y, padx=(0, 14))
        c = b1.interior
        ttk.Label(c, text="Datos de la empresa", style="TarjetaTitulo.TLabel").pack(anchor=W)
        emp = el.obtener_empresa()
        self.campos = {}
        for clave, etiqueta in (("nit", "NIT"), ("razon_social", "Razón social"), ("direccion", "Dirección"), ("telefono", "Teléfono"),
                                ("correo", "Correo"), ("regimen", "Régimen"), ("prefijo_factura", "Prefijo de factura")):
            e = cmp.campo(c, etiqueta, ancho=30)
            e.insert(0, emp.get(clave) or "")
            self.campos[clave] = e
        ttk.Button(c, text="Guardar cambios", style="Zen.TButton", command=self.guardar_empresa).pack(fill=X, pady=(16, 0))

        der = ttk.Frame(cols)
        der.pack(side=LEFT, fill=Y, padx=(0, 14))
        b2 = cmp.tarjeta(der, padding=20)
        b2.pack(fill=X)
        c2 = b2.interior
        ttk.Label(c2, text="Cambiar mi contraseña", style="TarjetaTitulo.TLabel").pack(anchor=W)
        self.p_actual = cmp.campo(c2, "Contraseña actual", ancho=28, show="●")
        self.p_nueva = cmp.campo(c2, "Nueva contraseña", ancho=28, show="●")
        self.p_conf = cmp.campo(c2, "Confirmar nueva contraseña", ancho=28, show="●")
        ttk.Button(c2, text="Actualizar contraseña", style="Oro.TButton", command=self.cambiar_pass).pack(fill=X, pady=(14, 0))

        b3 = cmp.tarjeta(der, padding=20)
        b3.pack(fill=X, pady=(14, 0))
        c3 = b3.interior
        ttk.Label(c3, text="Copia de seguridad", style="TarjetaTitulo.TLabel").pack(anchor=W)
        ttk.Label(c3, text="Guarda una copia de toda tu información en la ubicación que elijas (USB, nube, etc.).",
                  style="Tarjeta.TLabel", foreground=tema.GRIS, wraplength=280).pack(anchor=W, pady=6)
        ttk.Button(c3, text="Crear copia de seguridad", style="Zen.TButton", command=self.respaldo).pack(fill=X)
        ttk.Label(c3, text=f"Además, al cerrar el programa se guarda una copia automática semanal (se conservan las últimas {respaldo_auto.MAX_COPIAS} semanas).",
                  style="Tarjeta.TLabel", foreground=tema.VERDE_CLARO, wraplength=280, font=(tema.FUENTE, 9, "italic")).pack(anchor=W, pady=(10, 4))
        ttk.Button(c3, text="Abrir carpeta de copias automáticas", style="Suave.TButton",
                   command=lambda: os.startfile(respaldo_auto.carpeta_respaldos())).pack(fill=X)
        ttk.Label(c3, text=f"Base de datos: {ruta_db()}", style="Tarjeta.TLabel", foreground=tema.GRIS,
                  wraplength=280, font=(tema.FUENTE, 8)).pack(anchor=W, pady=(8, 0))

        if Sesion.es_admin():
            b4 = cmp.tarjeta(cols, padding=20)
            b4.pack(side=LEFT, fill=Y)
            c4 = b4.interior
            ttk.Label(c4, text="Preguntas de seguridad", style="TarjetaTitulo.TLabel").pack(anchor=W)
            ttk.Label(
                c4,
                text="Se usan para recuperar tu clave de administrador desde la pantalla de inicio de sesión.",
                style="Tarjeta.TLabel",
                foreground=tema.GRIS,
                wraplength=290,
            ).pack(anchor=W, pady=(4, 8))

            actuales = al.obtener_preguntas_admin_actual()
            preguntas = al.PREGUNTAS_PREDEFINIDAS

            ttk.Label(c4, text="Pregunta 1", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(anchor=W, pady=(8, 4))
            self.cb_preg1 = ttk.Combobox(c4, values=preguntas, state="readonly", width=32)
            self.cb_preg1.set(actuales[0] if len(actuales) >= 1 else preguntas[0])
            self.cb_preg1.pack(fill=X, pady=(0, 4))
            self.e_resp1 = cmp.campo(c4, "Nueva respuesta 1", ancho=30)

            ttk.Label(c4, text="Pregunta 2", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(anchor=W, pady=(8, 4))
            self.cb_preg2 = ttk.Combobox(c4, values=preguntas, state="readonly", width=32)
            self.cb_preg2.set(actuales[1] if len(actuales) >= 2 else preguntas[1])
            self.cb_preg2.pack(fill=X, pady=(0, 4))
            self.e_resp2 = cmp.campo(c4, "Nueva respuesta 2", ancho=30)

            ttk.Button(c4, text="Guardar preguntas", style="Zen.TButton",
                       command=self.guardar_preguntas).pack(fill=X, pady=(14, 0))

    def guardar_empresa(self):
        try:
            el.actualizar_empresa({k: e.get() for k, e in self.campos.items()})
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)
        cmp.toast(self, "Datos de la empresa actualizados")

    def cambiar_pass(self):
        try:
            ul.cambiar_mi_password(self.p_actual.get(), self.p_nueva.get(), self.p_conf.get())
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)
        for e in (self.p_actual, self.p_nueva, self.p_conf):
            e.delete(0, END)
        cmp.toast(self, "Contraseña actualizada")

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
        destino = filedialog.asksaveasfilename(defaultextension=".db", initialfile=f"bill_zen_respaldo_{datetime.now():%Y%m%d_%H%M}.db",
                                               filetypes=[("Copia Bill Zen", "*.db")])
        if not destino:
            return
        with sqlite3.connect(ruta_db()) as origen, sqlite3.connect(destino) as copia:
            origen.backup(copia)
        auditar("COPIA_SEGURIDAD", os.path.basename(destino))
        cmp.toast(self, "Copia de seguridad creada")
