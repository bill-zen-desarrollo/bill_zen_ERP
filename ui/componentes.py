"""Componentes visuales reutilizables."""
import tkinter as tk
from tkinter import ttk as _ttk

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from ui import tema


def tarjeta(padre, padding=20, **kw):
    """Contenedor blanco con borde sutil (#DEDAD0) y padding interno SaaS."""
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
    lbl_titulo = ttk.Label(
        cuerpo,
        text=titulo.upper(),
        style="KPITexto.TLabel",
        font=(tema.FUENTE, 9, "bold"),
        anchor=W,
        justify=LEFT,
    )
    lbl_titulo.pack(fill=X, padx=16, pady=(10, 2))
    lbl_valor = ttk.Label(cuerpo, text=valor, style="KPI.TLabel")
    lbl_valor.pack(anchor=W, padx=16)
    lbl_detalle = ttk.Label(
        cuerpo,
        text=detalle,
        style="KPITexto.TLabel",
        font=(tema.FUENTE, 10),
        anchor=W,
        justify=LEFT,
    )
    lbl_detalle.pack(fill=X, padx=16, pady=(2, 12))

    def _ajustar_wrap(evento):
        ancho_disp = max(120, evento.width - 32)
        lbl_titulo.configure(wraplength=ancho_disp)
        lbl_detalle.configure(wraplength=ancho_disp)

    cuerpo.bind("<Configure>", _ajustar_wrap, add="+")
    borde.valor = lbl_valor
    borde.detalle = lbl_detalle
    return borde


def encabezado(padre, titulo, subtitulo=""):
    marco = ttk.Frame(padre)
    ttk.Label(marco, text=titulo, style="Titulo.TLabel").pack(anchor=W)
    if subtitulo:
        ttk.Label(marco, text=subtitulo, style="Subtitulo.TLabel", font=(tema.FUENTE, 11)).pack(anchor=W, pady=(2, 0))
    return marco


def tabla(padre, columnas, altura=12):
    """columnas: [(clave, titulo, ancho, alineación)]. Devuelve (marco, treeview).
    Ajusta los anchos mínimos al texto de cada encabezado y reparte proporcionalmente
    el espacio disponible al redimensionar para evitar recortes."""
    marco = ttk.Frame(padre, style="Tarjeta.TFrame")
    tv = ttk.Treeview(marco, columns=[c[0] for c in columnas], show="headings", height=altura, selectmode="browse")

    pesos = {}
    minimos = {}
    for clave, titulo, ancho, alin in columnas:
        tv.heading(clave, text=titulo)
        min_encabezado = max(62, len(titulo) * 8 + 26)
        ancho_inicial = max(int(ancho), min_encabezado)
        pesos[clave] = ancho_inicial
        minimos[clave] = min_encabezado
        tv.column(clave, width=ancho_inicial, anchor=alin, minwidth=min_encabezado, stretch=True)

    barra = ttk.Scrollbar(marco, orient=VERTICAL, command=tv.yview)
    tv.configure(yscrollcommand=barra.set)
    tv.pack(side=LEFT, fill=BOTH, expand=YES)
    barra.pack(side=RIGHT, fill=Y)

    tv.tag_configure("par", background="#FAF9F5")
    tv.tag_configure("impar", background=tema.BLANCO)
    tv.tag_configure("alerta", foreground=tema.ROJO)
    tv.tag_configure("anulada", foreground="#94A3B8")

    # Distribución proporcional automática sin recortar encabezados
    suma_pesos = max(1, sum(pesos.values()))
    timer_cols = [None]
    ultimo_ancho = [0]

    def _distribuir_columnas(ancho_total: int):
        if ancho_total <= 40 or not tv.winfo_exists():
            return
        disponible = ancho_total - 6
        if disponible <= sum(minimos.values()):
            for clave, _, _, _ in columnas:
                tv.column(clave, width=minimos[clave])
            return
        asignado = 0
        for idx, (clave, _, _, _) in enumerate(columnas):
            if idx == len(columnas) - 1:
                w_col = max(minimos[clave], disponible - asignado)
            else:
                w_col = max(minimos[clave], int(disponible * pesos[clave] / suma_pesos))
                asignado += w_col
            tv.column(clave, width=w_col)

    def _al_configurar(evento):
        if abs(evento.width - ultimo_ancho[0]) < 8:
            return
        ultimo_ancho[0] = evento.width
        if timer_cols[0]:
            try:
                tv.after_cancel(timer_cols[0])
            except Exception:
                pass
        timer_cols[0] = tv.after(60, lambda w=evento.width: _distribuir_columnas(w))

    tv.bind("<Configure>", _al_configurar, add="+")
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
    """Etiqueta (10pt bold) + Entry (11pt) apilados. Devuelve el Entry."""
    es_tarjeta = estilo_label == "Tarjeta.TLabel"
    marco = ttk.Frame(padre, style="Tarjeta.TFrame" if es_tarjeta else "TFrame")
    st_lbl = "FormLabel.TLabel" if es_tarjeta else "FormLabelFondo.TLabel"
    ttk.Label(marco, text=etiqueta, style=st_lbl, font=(tema.FUENTE, 10, "bold")).pack(anchor=W, pady=(6, 3))
    entrada = ttk.Entry(marco, show=show, width=ancho or 24, font=(tema.FUENTE, 11))
    entrada.pack(fill=X, pady=(0, 6))
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

