"""Dashboard del administrador: KPIs + gráficos con la paleta Bill Zen."""
from datetime import date, timedelta

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import licencia, reportes_logic as rl
from logica.seguridad import Sesion
from ui import componentes as cmp
from ui import tema

PALETA = [tema.VERDE, tema.DORADO, tema.VERDE_CLARO, "#8C6D1F", "#5C8F7B", "#B5523B", "#A9A38F"]


def _corto(v, _pos=None):
    return f"{v/1_000_000:.1f}M" if v >= 1_000_000 else (f"{v/1_000:.0f}k" if v >= 1_000 else f"{v:.0f}")


def _lienzo(padre, ancho=6, alto=3):
    fig = Figure(figsize=(ancho, alto), dpi=92, facecolor=tema.BLANCO)
    ax = fig.add_subplot(111)
    ax.set_facecolor(tema.BLANCO)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(tema.BEIGE_OSCURO)
    ax.tick_params(colors=tema.GRIS, labelsize=8)
    canvas = FigureCanvasTkAgg(fig, master=padre)
    widget = canvas.get_tk_widget()

    # Evita que Matplotlib redibuje en cada píxel mientras el usuario arrastra el borde de la ventana
    timer_resize = [None]
    ultimo_tam = [0, 0]

    def _al_redimensionar(evento):
        if abs(evento.width - ultimo_tam[0]) < 4 and abs(evento.height - ultimo_tam[1]) < 4:
            return
        ultimo_tam[0], ultimo_tam[1] = evento.width, evento.height
        if timer_resize[0]:
            try:
                widget.after_cancel(timer_resize[0])
            except Exception:
                pass
        timer_resize[0] = widget.after(140, lambda e=evento: canvas.resize(e) if widget.winfo_exists() else None)

    widget.bind("<Configure>", _al_redimensionar)
    widget.pack(fill=BOTH, expand=YES)
    return fig, ax, canvas


class Vista(ttk.Frame):
    def __init__(self, padre, principal):
        super().__init__(padre)
        saludo = Sesion.usuario["nombre_completo"].split()[0]
        cab = ttk.Frame(self)
        cab.pack(fill=X, pady=(0, 12))
        ttk.Label(cab, text=f"Hola, {saludo}", style="Cursiva.TLabel").pack(side=LEFT)
        ttk.Label(cab, text="  Así va tu negocio hoy", style="Subtitulo.TLabel").pack(side=LEFT, pady=(12, 0))
        ttk.Button(cab, text="⟳ Actualizar", style="Suave.TButton", command=self.dibujar).pack(side=RIGHT)
        if principal and hasattr(principal, "ir_a"):
            if licencia.permite_modulo("auditoria_movil"):
                ttk.Button(
                    cab,
                    text="📱 Auditoría Móvil (QR)",
                    style="Oro.TButton",
                    command=lambda: principal.ir_a("auditoria_movil"),
                ).pack(side=RIGHT, padx=(0, 8))
            else:
                btn_qr_bloq = ttk.Button(
                    cab,
                    text="🔒 Auditoría Móvil (Plan Ultra)",
                    style="Suave.TButton",
                    state="disabled",
                )
                btn_qr_bloq.pack(side=RIGHT, padx=(0, 8))
                cmp.vincular_tooltip(
                    btn_qr_bloq,
                    "La Auditoría Remota Móvil por QR es exclusiva del Plan Ultra. Actualiza tu plan para activarla.",
                )

        self.fila_kpi = ttk.Frame(self)
        self.fila_kpi.pack(fill=X)
        self.kpis = {}
        defs = [("ventas_hoy", "Ventas de hoy", tema.VERDE), ("ventas_mes", "Ventas del mes", tema.DORADO),
                ("utilidad", "Utilidad del mes", tema.VERDE_CLARO), ("ticket", "Ticket promedio", "#8C6D1F"),
                ("stock", "Productos con stock bajo", tema.ROJO)]
        for i, (k, t, col) in enumerate(defs):
            self.fila_kpi.columnconfigure(i, weight=1, uniform="k")
            w = cmp.tarjeta_kpi(self.fila_kpi, t, acento=col)
            w.grid(row=0, column=i, sticky=NSEW, padx=(0 if i == 0 else 8, 0))
            self.kpis[k] = w

        graficos = ttk.Frame(self)
        graficos.pack(fill=BOTH, expand=YES, pady=(12, 0))
        graficos.columnconfigure(0, weight=3, uniform="g")
        graficos.columnconfigure(1, weight=2, uniform="g")
        graficos.rowconfigure((0, 1), weight=1, uniform="r")
        self.cont = {}
        for clave, titulo, f, c, cs in (("dias", "Ventas de los últimos 14 días", 0, 0, 1), ("cat", "Ventas por categoría (mes)", 0, 1, 1),
                                        ("top", "Productos más vendidos (mes)", 1, 0, 1), ("bajo", "Alertas de stock bajo", 1, 1, 1)):
            b = cmp.tarjeta(graficos, padding=12)
            b.grid(row=f, column=c, sticky=NSEW, padx=(0 if c == 0 else 8, 0), pady=(0 if f == 0 else 8, 0))
            ttk.Label(b.interior, text=titulo, style="TarjetaTitulo.TLabel").pack(anchor=W)
            self.cont[clave] = b.interior
        self.dibujar()

    def dibujar(self):
        k = rl.kpis_dashboard()
        var = k["variacion_mes"]
        self._kpi("ventas_hoy", tema.moneda(k["ventas_hoy"]), f"{k['facturas_hoy']} facturas")
        self._kpi("ventas_mes", tema.moneda(k["ventas_mes"]),
                  "Sin mes anterior" if var is None else f"{'▲' if var >= 0 else '▼'} {abs(var):.0f}% vs mes anterior")
        self._kpi("utilidad", tema.moneda(k["utilidad_mes"]), f"Gastos: {tema.moneda(k['gastos_mes'])}")
        self._kpi("ticket", tema.moneda(k["ticket_promedio"]), f"{k['facturas_mes']} facturas en el mes")
        self._kpi("stock", str(k["stock_bajo"]), f"de {k['productos']} productos")

        hoy = date.today()
        ini, fin = hoy.replace(day=1).isoformat(), hoy.isoformat()
        self._limpiar("dias")
        fig, ax, cv = _lienzo(self.cont["dias"], 6, 2.3)
        datos = rl.ventas_por_dia(14)
        x = list(range(len(datos)))
        ys = [v for _, v in datos]
        ax.fill_between(x, ys, color=tema.VERDE_CLARO, alpha=0.18)
        ax.plot(x, ys, color=tema.VERDE, linewidth=2.2, marker="o", markersize=4, markerfacecolor=tema.DORADO, markeredgecolor=tema.DORADO)
        ax.set_xticks(x[::2])
        ax.set_xticklabels([d.strftime("%d/%m") for d, _ in datos][::2])
        ax.yaxis.set_major_formatter(FuncFormatter(_corto))
        ax.grid(axis="y", color=tema.BEIGE_OSCURO, linewidth=0.6, alpha=0.7)
        fig.tight_layout(pad=1.2)
        cv.draw()

        self._limpiar("cat")
        fig, ax, cv = _lienzo(self.cont["cat"], 3.6, 2.3)
        cats = rl.ventas_por_categoria(ini, fin)
        if cats:
            ax.pie([c["total"] for c in cats], labels=[c["nombre"] for c in cats], colors=PALETA[:len(cats)], startangle=90,
                   wedgeprops={"width": 0.42, "edgecolor": "white"}, textprops={"fontsize": 8, "color": tema.TEXTO}, autopct="%1.0f%%", pctdistance=0.79)
        else:
            ax.text(0.5, 0.5, "Aún no hay ventas este mes", ha="center", va="center", color=tema.GRIS, transform=ax.transAxes)
            ax.axis("off")
        fig.tight_layout(pad=1)
        cv.draw()

        self._limpiar("top")
        fig, ax, cv = _lienzo(self.cont["top"], 6, 2.3)
        top = rl.top_productos(ini, fin, 6)[::-1]
        if top:
            ax.barh([t["nombre"][:22] for t in top], [t["total"] for t in top], color=tema.VERDE, height=0.58)
            for i, t in enumerate(top):
                ax.text(t["total"], i, f"  {_corto(t['total'])}", va="center", fontsize=8, color=tema.DORADO)
            ax.xaxis.set_major_formatter(FuncFormatter(_corto))
            ax.margins(x=0.15)
        else:
            ax.text(0.5, 0.5, "Aún no hay ventas este mes", ha="center", va="center", color=tema.GRIS, transform=ax.transAxes)
            ax.axis("off")
        fig.tight_layout(pad=1.2)
        cv.draw()

        self._limpiar("bajo")
        bajos = rl.productos_stock_bajo()
        if not bajos:
            ttk.Label(self.cont["bajo"], text="✔ Todo el inventario está en niveles saludables", style="Tarjeta.TLabel",
                      foreground=tema.VERDE_CLARO, font=(tema.FUENTE, 10, "bold")).pack(pady=30)
        else:
            m, tv = cmp.tabla(self.cont["bajo"], [("p", "Producto", 170, W), ("s", "Stock", 55, E), ("m", "Mín.", 50, E)], altura=6)
            m.pack(fill=BOTH, expand=YES, pady=(6, 0))
            cmp.llenar_tabla(tv, [(i, (b["nombre"], b["stock"], b["stock_minimo"])) for i, b in enumerate(bajos)], lambda i, v: ("alerta",))

    def _limpiar(self, clave):
        for w in self.cont[clave].winfo_children()[1:]:
            w.destroy()

    def destroy(self):
        import gc
        super().destroy()
        gc.collect()

    def _kpi(self, clave, valor, detalle):
        self.kpis[clave].valor.configure(text=valor)
        self.kpis[clave].detalle.configure(text=detalle)
