"""Sistema de diseño global Bill Zen ERP: paleta corporativa, tipografía unificada y densidad SaaS."""

import ttkbootstrap as ttk
from ttkbootstrap.style import ThemeDefinition

# Paleta corporativa SaaS
VERDE = "#0F4C3A"           # Verde Pantone 349C
VERDE_HOVER = "#1B6B53"     # Hover / estados activos
VERDE_OSCURO = "#0F4C3A"    # Sidebar y títulos de énfasis
VERDE_PROFUNDO = "#0A3628"  # Fondos internos de badges sobre sidebar
VERDE_CLARO = "#1B6B53"     # Acento positivo y éxito
BEIGE = "#F7F5EE"           # Lienzo crema suave
BEIGE_OSCURO = "#DEDAD0"    # Borde sutil de tarjetas blancas
BLANCO = "#FFFFFF"          # Superficie de tarjetas
NEGRO = "#0F172A"
DORADO = "#C99A3E"          # Acento dorado
DORADO_CLARO = "#E5B85B"    # Dorado suave para selección/hover
TEXTO = "#1E293B"           # Texto principal oscuro
GRIS = "#64748B"            # Texto secundario legible
ROJO = "#DC2626"            # Alertas / mermas / peligro
AMBAR = "#D97706"           # Modo offline / advertencia

# Píldoras de estado de red / sincronización
SYNC_VERDE_BG = "#DCFCE7"
SYNC_VERDE_FG = "#15803D"
SYNC_VERDE_BORDE = "#86EFAC"
SYNC_AMBAR_BG = "#FEF3C7"
SYNC_AMBAR_FG = "#B45309"
SYNC_AMBAR_BORDE = "#FCD34D"

NOMBRE_TEMA = "billzen"

# Tipografía unificada sin serifa (Segoe UI) + toque cursivo de marca en "Zen" y saludo del Dashboard
FUENTE = "Segoe UI"
FUENTE_TITULO = "Segoe UI"
FUENTE_CURSIVA = "Segoe Script"


def registrar_tema():
    """Debe llamarse DESPUÉS de crear la ventana raíz (ttkbootstrap admite una sola raíz)."""
    colores = {
        "primary": VERDE,
        "secondary": GRIS,
        "success": VERDE_HOVER,
        "info": "#2563EB",
        "warning": DORADO,
        "danger": ROJO,
        "light": BEIGE,
        "dark": VERDE_OSCURO,
        "bg": BEIGE,
        "fg": TEXTO,
        "selectbg": VERDE,
        "selectfg": BLANCO,
        "border": BEIGE_OSCURO,
        "inputfg": TEXTO,
        "inputbg": BLANCO,
        "active": "#EBE7DC",
    }
    estilo = ttk.Style()
    estilo.register_theme(ThemeDefinition(NOMBRE_TEMA, colores, "light"))
    return estilo


def aplicar_estilos(estilo: ttk.Style):
    estilo.theme_use(NOMBRE_TEMA)
    if estilo.master:
        try:
            estilo.master.option_add("*TCombobox*Listbox.font", (FUENTE, 11))
            estilo.master.option_add("*TCombobox*Listbox.background", BLANCO)
            estilo.master.option_add("*TCombobox*Listbox.foreground", TEXTO)
            estilo.master.option_add("*TCombobox*Listbox.selectBackground", VERDE)
            estilo.master.option_add("*TCombobox*Listbox.selectForeground", BLANCO)
        except Exception:
            pass

    estilo.configure(".", font=(FUENTE, 11), foreground=TEXTO)
    estilo.configure("TFrame", background=BEIGE)
    estilo.configure("Tarjeta.TFrame", background=BLANCO, relief="flat")
    estilo.configure("Lateral.TFrame", background=VERDE_OSCURO)
    estilo.configure("Fondo.TLabel", background=BEIGE, foreground=TEXTO, font=(FUENTE, 11))
    estilo.configure("Tarjeta.TLabel", background=BLANCO, foreground=TEXTO, font=(FUENTE, 11))
    estilo.configure("FormLabel.TLabel", background=BLANCO, foreground=TEXTO, font=(FUENTE, 10, "bold"))
    estilo.configure("FormLabelFondo.TLabel", background=BEIGE, foreground=TEXTO, font=(FUENTE, 10, "bold"))

    # Jerarquía tipográfica SaaS de escritorio
    estilo.configure("Titulo.TLabel", background=BEIGE, foreground=VERDE_OSCURO, font=(FUENTE, 20, "bold"))
    estilo.configure("Subtitulo.TLabel", background=BEIGE, foreground=GRIS, font=(FUENTE, 11))
    estilo.configure("TarjetaTitulo.TLabel", background=BLANCO, foreground=VERDE_OSCURO, font=(FUENTE, 13, "bold"))
    estilo.configure("KPI.TLabel", background=BLANCO, foreground=VERDE, font=(FUENTE, 20, "bold"))
    estilo.configure("KPITexto.TLabel", background=BLANCO, foreground=GRIS, font=(FUENTE, 10))

    estilo.configure("Lateral.TLabel", background=VERDE_OSCURO, foreground=BEIGE, font=(FUENTE, 11))
    estilo.configure("Logo.TLabel", background=VERDE_OSCURO, foreground=BLANCO, font=(FUENTE, 20, "bold"))
    estilo.configure("LogoZen.TLabel", background=VERDE_OSCURO, foreground=DORADO, font=(FUENTE_CURSIVA, 22))
    estilo.configure("Cursiva.TLabel", background=BEIGE, foreground=DORADO, font=(FUENTE_CURSIVA, 26))

    # Checkbuttons sobre tarjetas y sobre fondo
    estilo.configure("TCheckbutton", background=BEIGE, foreground=TEXTO, font=(FUENTE, 10, "bold"))
    estilo.configure("Tarjeta.TCheckbutton", background=BLANCO, foreground=TEXTO, font=(FUENTE, 10, "bold"))
    estilo.configure("TSeparator", background=BEIGE_OSCURO)

    # Botones robustos con densidad táctil
    estilo.configure("TButton", font=(FUENTE, 11, "bold"), padding=(16, 10), borderwidth=0)
    estilo.configure("Zen.TButton", background=VERDE, foreground=BLANCO, bordercolor=VERDE, font=(FUENTE, 11, "bold"), padding=(16, 10))
    estilo.map("Zen.TButton", background=[("active", VERDE_HOVER), ("disabled", "#94B3A8")], foreground=[("disabled", "#F1F5F9")])

    estilo.configure("Oro.TButton", background=DORADO, foreground=NEGRO, bordercolor=DORADO, font=(FUENTE, 11, "bold"), padding=(16, 10))
    estilo.map("Oro.TButton", background=[("active", DORADO_CLARO), ("disabled", "#E5D3A7")])

    estilo.configure("Suave.TButton", background="#EFECE3", foreground=VERDE_OSCURO, bordercolor=BEIGE_OSCURO, font=(FUENTE, 11, "bold"), padding=(16, 10))
    estilo.map("Suave.TButton", background=[("active", BEIGE_OSCURO), ("disabled", "#F5F3EC")], foreground=[("disabled", "#94A3B8")])

    estilo.configure("Info.TButton", background="#1E40AF", foreground=BLANCO, bordercolor="#1E40AF", font=(FUENTE, 11, "bold"), padding=(16, 10))
    estilo.map("Info.TButton", background=[("active", "#2563EB")])

    estilo.configure("Peligro.TButton", background=ROJO, foreground=BLANCO, bordercolor=ROJO, font=(FUENTE, 11, "bold"), padding=(16, 10))
    estilo.map("Peligro.TButton", background=[("active", "#B91C1C"), ("disabled", "#FCA5A5")])

    # Botones del Sidebar (11pt, alineación limpia izquierda)
    estilo.configure(
        "Menu.TButton",
        background=VERDE_OSCURO,
        foreground=BEIGE,
        anchor="w",
        padding=(18, 11),
        font=(FUENTE, 11),
        bordercolor=VERDE_OSCURO,
    )
    estilo.map(
        "Menu.TButton",
        background=[("active", VERDE_HOVER), ("disabled", VERDE_OSCURO)],
        foreground=[("active", BLANCO), ("disabled", "#7EA395")],
    )
    estilo.configure(
        "MenuActivo.TButton",
        background=VERDE_HOVER,
        foreground=DORADO_CLARO,
        anchor="w",
        padding=(18, 11),
        font=(FUENTE, 11, "bold"),
        bordercolor=DORADO,
    )
    estilo.map(
        "MenuActivo.TButton",
        background=[("active", VERDE_HOVER)],
        foreground=[("active", BLANCO)],
    )

    # Entradas y selectores (>= 38px altura visual) con realce de foco nativo en C/Tcl
    estilo.configure("TEntry", padding=(10, 8), fieldbackground=BLANCO, foreground=TEXTO, bordercolor=BEIGE_OSCURO, lightcolor=BEIGE_OSCURO, darkcolor=BEIGE_OSCURO, font=(FUENTE, 11))
    estilo.map("TEntry", bordercolor=[("focus", VERDE), ("hover", VERDE_HOVER)], lightcolor=[("focus", VERDE)], darkcolor=[("focus", VERDE)])
    estilo.configure("TCombobox", padding=(10, 8), fieldbackground=BLANCO, foreground=TEXTO, bordercolor=BEIGE_OSCURO, lightcolor=BEIGE_OSCURO, darkcolor=BEIGE_OSCURO, font=(FUENTE, 11))
    estilo.map("TCombobox", fieldbackground=[("readonly", BLANCO)], foreground=[("readonly", TEXTO)], bordercolor=[("focus", VERDE), ("hover", VERDE_HOVER)], lightcolor=[("focus", VERDE)])
    estilo.configure("TSpinbox", padding=(8, 7), fieldbackground=BLANCO, foreground=TEXTO, bordercolor=BEIGE_OSCURO, lightcolor=BEIGE_OSCURO, darkcolor=BEIGE_OSCURO, font=(FUENTE, 11))
    estilo.map("TSpinbox", bordercolor=[("focus", VERDE), ("hover", VERDE_HOVER)], lightcolor=[("focus", VERDE)])

    # Botón rápido de denominaciones de billetes en el POS
    estilo.configure("Billete.TButton", background="#EFECE3", foreground=VERDE_OSCURO, bordercolor=BEIGE_OSCURO, font=(FUENTE, 9, "bold"), padding=(6, 5))
    estilo.map("Billete.TButton", background=[("active", DORADO_CLARO)], foreground=[("active", NEGRO)])

    # Tablas Treeview con alta densidad táctil y encabezados legibles
    estilo.configure(
        "Treeview",
        background=BLANCO,
        fieldbackground=BLANCO,
        foreground=TEXTO,
        rowheight=36,
        borderwidth=0,
        font=(FUENTE, 11),
    )
    estilo.configure(
        "Treeview.Heading",
        background=VERDE,
        foreground=BLANCO,
        font=(FUENTE, 10, "bold"),
        padding=(10, 10),
        relief="flat",
    )
    estilo.map("Treeview.Heading", background=[("active", VERDE_HOVER)])
    estilo.map("Treeview", background=[("selected", "#E9DFC4")], foreground=[("selected", NEGRO)])

    # Pestañas estilo Segmented Control SaaS (0 widgets extra, renderizado nativo)
    estilo.configure("TNotebook", background=BEIGE, borderwidth=0, tabmargins=(0, 0, 0, 6))
    estilo.configure(
        "TNotebook.Tab",
        background="#E6E2D6",
        foreground=TEXTO,
        padding=(18, 10),
        font=(FUENTE, 10, "bold"),
        borderwidth=0,
    )
    estilo.map(
        "TNotebook.Tab",
        background=[("selected", VERDE), ("active", VERDE_HOVER)],
        foreground=[("selected", BLANCO), ("active", BLANCO)],
    )


def moneda(valor) -> str:
    """Formato colombiano: $ 1.234.567"""
    return "$ " + f"{round(valor or 0):,}".replace(",", ".")
