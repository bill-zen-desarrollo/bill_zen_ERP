"""Tema visual Bill Zen: misma paleta que la landing (verde, beige, dorado, negro)."""

import ttkbootstrap as ttk
from ttkbootstrap.style import ThemeDefinition

# Paleta
VERDE = "#1F5C46"
VERDE_OSCURO = "#123829"
VERDE_CLARO = "#349C6B"
BEIGE = "#F5EFE3"
BEIGE_OSCURO = "#E8DCC4"
BLANCO = "#FFFFFF"
NEGRO = "#121212"
DORADO = "#C9A646"
DORADO_CLARO = "#E4C979"
TEXTO = "#2B2B2B"
GRIS = "#6B6B6B"
ROJO = "#B5523B"

NOMBRE_TEMA = "billzen"

FUENTE = "Segoe UI"
FUENTE_TITULO = "Georgia"
FUENTE_CURSIVA = "Segoe Script"


def registrar_tema():
    """Debe llamarse DESPUÉS de crear la ventana raíz (ttkbootstrap admite una sola raíz)."""
    colores = {
        "primary": VERDE, "secondary": "#8C8C8C", "success": VERDE_CLARO, "info": "#3B7EA1",
        "warning": DORADO, "danger": ROJO, "light": BEIGE, "dark": VERDE_OSCURO,
        "bg": BEIGE, "fg": TEXTO, "selectbg": VERDE, "selectfg": BLANCO,
        "border": BEIGE_OSCURO, "inputfg": TEXTO, "inputbg": BLANCO, "active": BEIGE_OSCURO,
    }
    estilo = ttk.Style()
    estilo.register_theme(ThemeDefinition(NOMBRE_TEMA, colores, "light"))
    return estilo


def aplicar_estilos(estilo: ttk.Style):
    estilo.theme_use(NOMBRE_TEMA)
    estilo.configure(".", font=(FUENTE, 10))
    estilo.configure("TFrame", background=BEIGE)
    estilo.configure("Tarjeta.TFrame", background=BLANCO, relief="flat")
    estilo.configure("Lateral.TFrame", background=VERDE_OSCURO)
    estilo.configure("Fondo.TLabel", background=BEIGE, foreground=TEXTO)
    estilo.configure("Tarjeta.TLabel", background=BLANCO, foreground=TEXTO)
    estilo.configure("Titulo.TLabel", background=BEIGE, foreground=VERDE_OSCURO, font=(FUENTE_TITULO, 20, "bold"))
    estilo.configure("Subtitulo.TLabel", background=BEIGE, foreground=GRIS, font=(FUENTE, 10))
    estilo.configure("TarjetaTitulo.TLabel", background=BLANCO, foreground=VERDE_OSCURO, font=(FUENTE_TITULO, 13, "bold"))
    estilo.configure("KPI.TLabel", background=BLANCO, foreground=VERDE, font=(FUENTE_TITULO, 22, "bold"))
    estilo.configure("KPITexto.TLabel", background=BLANCO, foreground=GRIS, font=(FUENTE, 9))
    estilo.configure("Lateral.TLabel", background=VERDE_OSCURO, foreground=BEIGE)
    estilo.configure("Logo.TLabel", background=VERDE_OSCURO, foreground=BLANCO, font=(FUENTE_TITULO, 20, "bold"))
    estilo.configure("LogoZen.TLabel", background=VERDE_OSCURO, foreground=DORADO, font=(FUENTE_CURSIVA, 22))
    estilo.configure("Cursiva.TLabel", background=BEIGE, foreground=DORADO, font=(FUENTE_CURSIVA, 26))

    # Botones
    estilo.configure("TButton", font=(FUENTE, 10, "bold"), padding=(14, 8), borderwidth=0)
    estilo.configure("Zen.TButton", background=VERDE, foreground=BLANCO, bordercolor=VERDE)
    estilo.map("Zen.TButton", background=[("active", VERDE_CLARO), ("disabled", "#9fb7ac")])
    estilo.configure("Oro.TButton", background=DORADO, foreground=NEGRO, bordercolor=DORADO)
    estilo.map("Oro.TButton", background=[("active", DORADO_CLARO)])
    estilo.configure("Suave.TButton", background=BEIGE_OSCURO, foreground=VERDE_OSCURO, bordercolor=BEIGE_OSCURO)
    estilo.map("Suave.TButton", background=[("active", "#DACDAF")])
    estilo.configure("Peligro.TButton", background=ROJO, foreground=BLANCO, bordercolor=ROJO)
    estilo.map("Peligro.TButton", background=[("active", "#c9674f")])
    estilo.configure("Menu.TButton", background=VERDE_OSCURO, foreground=BEIGE, anchor="w",
                     padding=(18, 11), font=(FUENTE, 10, "bold"), bordercolor=VERDE_OSCURO)
    estilo.map("Menu.TButton", background=[("active", VERDE)], foreground=[("active", BLANCO)])
    estilo.configure("MenuActivo.TButton", background=VERDE, foreground=DORADO_CLARO, anchor="w",
                     padding=(18, 11), font=(FUENTE, 10, "bold"), bordercolor=DORADO)

    # Entradas
    estilo.configure("TEntry", padding=7, fieldbackground=BLANCO, bordercolor=BEIGE_OSCURO)
    estilo.configure("TCombobox", padding=7, fieldbackground=BLANCO)

    # Tablas
    estilo.configure("Treeview", background=BLANCO, fieldbackground=BLANCO, foreground=TEXTO,
                     rowheight=30, borderwidth=0, font=(FUENTE, 10))
    estilo.configure("Treeview.Heading", background=VERDE, foreground=BLANCO,
                     font=(FUENTE, 10, "bold"), padding=(8, 8), relief="flat")
    estilo.map("Treeview.Heading", background=[("active", VERDE_CLARO)])
    estilo.map("Treeview", background=[("selected", DORADO_CLARO)], foreground=[("selected", NEGRO)])
    estilo.configure("TNotebook", background=BEIGE)
    estilo.configure("TNotebook.Tab", padding=(18, 8), font=(FUENTE, 10, "bold"))


def moneda(valor) -> str:
    """Formato colombiano: $ 1.234.567"""
    return "$ " + f"{round(valor or 0):,}".replace(",", ".")
