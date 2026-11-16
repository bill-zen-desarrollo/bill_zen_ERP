"""Componentes visuales reutilizables."""
import tkinter as tk
from tkinter import ttk as _ttk

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from ui import tema


def tarjeta(padre, padding=18, **kw):
    """Contenedor blanco con borde sutil."""
    borde = tk.Frame(padre, bg=tema.BEIGE_OSCURO)
    interior = ttk.Frame(borde, style="Tarjeta.TFrame", padding=padding)
    interior.pack(fill=BOTH, expand=YES, padx=1, pady=1)
    borde.interior = interior
    return borde


def tarjeta_kpi(padre, titulo, valor="—", detalle="", acento=tema.VERDE):
    borde = tk.Frame(padre, bg=tema.BEIGE_OSCURO)
    cuerpo = tk.Frame(borde, bg=tema.BLANCO)
    cuerpo.pack(fill=BOTH, expand=YES, padx=1, pady=1)
    tk.Frame(cuerpo, bg=acento, height=4).pack(fill=X)
    ttk.Label(cuerpo, text=titulo.upper(), style="KPITexto.TLabel", font=(tema.FUENTE, 8, "bold")).pack(anchor=W, padx=16, pady=(12, 0))
    lbl_valor = ttk.Label(cuerpo, text=valor, style="KPI.TLabel")
    lbl_valor.pack(anchor=W, padx=16)
    lbl_detalle = ttk.Label(cuerpo, text=detalle, style="KPITexto.TLabel")
    lbl_detalle.pack(anchor=W, padx=16, pady=(0, 12))
    borde.valor = lbl_valor
    borde.detalle = lbl_detalle
    return borde


def encabezado(padre, titulo, subtitulo=""):
    marco = ttk.Frame(padre)
    ttk.Label(marco, text=titulo, style="Titulo.TLabel").pack(anchor=W)
    if subtitulo:
        ttk.Label(marco, text=subtitulo, style="Subtitulo.TLabel").pack(anchor=W)
    return marco


def tabla(padre, columnas, altura=12):
    """columnas: [(clave, titulo, ancho, alineación)]. Devuelve (marco, treeview)."""
    marco = ttk.Frame(padre, style="Tarjeta.TFrame")
    tv = ttk.Treeview(marco, columns=[c[0] for c in columnas], show="headings", height=altura, selectmode="browse")
    cols_estirables = {"nombre", "n", "c", "d", "p", "detalle", "concepto", "cajero", "metodo_pago"}
    for i, (clave, titulo, ancho, alin) in enumerate(columnas):
        tv.heading(clave, text=titulo)
        estirar = (clave in cols_estirables) or (i == 1 and len(columnas) > 2)
        tv.column(clave, width=ancho, anchor=alin, minwidth=55, stretch=estirar)
    barra = ttk.Scrollbar(marco, orient=VERTICAL, command=tv.yview)
    tv.configure(yscrollcommand=barra.set)
    tv.pack(side=LEFT, fill=BOTH, expand=YES)
    barra.pack(side=RIGHT, fill=Y)
    tv.tag_configure("par", background="#FBF8F1")
    tv.tag_configure("impar", background=tema.BLANCO)
    tv.tag_configure("alerta", foreground=tema.ROJO)
    tv.tag_configure("anulada", foreground="#9a9a9a")
    return marco, tv


def llenar_tabla(tv, filas, etiquetas=None):
    """filas: lista de (iid, valores). etiquetas: función opcional(iid, valores)->tuple de tags."""
    tv.delete(*tv.get_children())
    for i, (iid, valores) in enumerate(filas):
        tags = ("par" if i % 2 else "impar",)
        if etiquetas:
            tags += tuple(etiquetas(iid, valores) or ())
        tv.insert("", END, iid=str(iid), values=valores, tags=tags)


def campo(padre, etiqueta, fila=None, columna=0, ancho=None, show=None, estilo_label="Tarjeta.TLabel"):
    """Etiqueta + Entry apilados. Devuelve el Entry."""
    marco = ttk.Frame(padre, style="Tarjeta.TFrame" if estilo_label == "Tarjeta.TLabel" else "TFrame")
    ttk.Label(marco, text=etiqueta, style=estilo_label, font=(tema.FUENTE, 9, "bold")).pack(anchor=W, pady=(12, 4))
    entrada = ttk.Entry(marco, show=show, width=ancho or 24)
    entrada.pack(fill=X, pady=(0, 10))
    if fila is not None:
        marco.grid(row=fila, column=columna, sticky=EW, padx=6)
    else:
        marco.pack(fill=X)
    entrada.marco = marco
    return entrada


def mostrar_error(padre, mensaje):
    from ttkbootstrap.dialogs import Messagebox
    Messagebox.show_error(str(mensaje), title="Bill Zen", parent=padre.winfo_toplevel())


def mostrar_info(padre, mensaje):
    from ttkbootstrap.dialogs import Messagebox
    Messagebox.show_info(str(mensaje), title="Bill Zen", parent=padre.winfo_toplevel())


def confirmar(padre, mensaje) -> bool:
    from ttkbootstrap.dialogs import Messagebox
    r = Messagebox.yesno(str(mensaje), title="Confirmar", parent=padre.winfo_toplevel())
    return r in ("Yes", "Sí", "Si")


def toast(padre, mensaje):
    from ttkbootstrap import ToastNotification
    ToastNotification(title="Bill Zen", message=mensaje, duration=2800, bootstyle="success", alert=False).show_toast()


def vincular_busqueda(widget_padre, entrada, callback, espera=250):
    """Ejecuta `callback` tras `espera` ms sin teclear para evitar consultas por cada tecla."""
    timer = [None]

    def _al_escribir(_e):
        if timer[0]:
            widget_padre.after_cancel(timer[0])
        timer[0] = widget_padre.after(espera, callback)

    entrada.bind("<KeyRelease>", _al_escribir)


def vincular_tooltip(widget, texto: str):
    """Muestra un Tooltip con la paleta corporativa Bill Zen al pasar el cursor (incluso en botones disabled)."""
    ventana_tt = [None]

    def _mostrar(_evento=None):
        if ventana_tt[0] is not None or not widget.winfo_exists():
            return
        x = widget.winfo_rootx() + 24
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        tw = tk.Toplevel(widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        borde = tk.Frame(tw, bg=tema.DORADO, padx=1, pady=1)
        borde.pack()
        tk.Label(
            borde,
            text=texto,
            bg=tema.VERDE_OSCURO,
            fg=tema.BEIGE,
            font=(tema.FUENTE, 9),
            justify="left",
            padx=10,
            pady=6,
            wraplength=280,
        ).pack()
        ventana_tt[0] = tw

    def _ocultar(_evento=None):
        if ventana_tt[0] is not None:
            try:
                ventana_tt[0].destroy()
            except Exception:
                pass
            ventana_tt[0] = None

    widget.bind("<Enter>", _mostrar, add="+")
    widget.bind("<Leave>", _ocultar, add="+")
    widget.bind("<Destroy>", _ocultar, add="+")

