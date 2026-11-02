"""Reportes con filtros por fecha y exportación a CSV."""
from datetime import date, timedelta
from tkinter import filedialog

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import reportes_logic as rl
from ui import componentes as cmp
from ui import tema


class Vista(ttk.Frame):
    def __init__(self, padre, principal):
        super().__init__(padre)
        cmp.encabezado(self, "Reportes", "Analiza tus ventas por producto, categoría, método de pago, cajero y hora").pack(anchor=W, pady=(0, 12))
        f = ttk.Frame(self)
        f.pack(fill=X, pady=(0, 8))
        ttk.Label(f, text="Desde", style="Fondo.TLabel").pack(side=LEFT)
        self.e_desde = ttk.Entry(f, width=12)
        self.e_desde.insert(0, (date.today() - timedelta(days=30)).isoformat())
        self.e_desde.pack(side=LEFT, padx=(4, 12))
        ttk.Label(f, text="Hasta", style="Fondo.TLabel").pack(side=LEFT)
        self.e_hasta = ttk.Entry(f, width=12)
        self.e_hasta.insert(0, date.today().isoformat())
        self.e_hasta.pack(side=LEFT, padx=(4, 12))
        ttk.Button(f, text="Generar", style="Zen.TButton", command=self.refrescar).pack(side=LEFT)
        ttk.Button(f, text="Exportar a CSV", style="Oro.TButton", command=self.exportar).pack(side=RIGHT)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=BOTH, expand=YES)
        self.defs = {
            "Más vendidos": ([("nombre", "Producto", 280, W), ("unidades", "Unidades", 90, E), ("total", "Total vendido", 130, E)], lambda d, h: rl.top_productos(d, h, 50)),
            "Por categoría": ([("nombre", "Categoría", 280, W), ("total", "Total vendido", 130, E)], rl.ventas_por_categoria),
            "Por método de pago": ([("metodo_pago", "Método", 220, W), ("n", "Facturas", 90, E), ("total", "Total", 130, E)], rl.ventas_por_metodo),
            "Por cajero": ([("cajero", "Cajero", 240, W), ("n", "Facturas", 90, E), ("total", "Total", 130, E)], rl.ventas_por_cajero),
            "Por hora": ([("hora", "Hora", 100, W), ("n", "Facturas", 90, E), ("total", "Total", 130, E)], rl.ventas_por_hora),
            "Auditoría": ([("fecha", "Fecha", 150, W), ("usuario", "Usuario", 100, W), ("accion", "Acción", 170, W), ("detalle", "Detalle", 320, W)], lambda d, h: rl.ultimas_auditorias()),
        }
        self.tablas = {}
        self.datos = {}
        for nombre, (cols, _) in self.defs.items():
            fr = ttk.Frame(self.nb, padding=10)
            marco, tv = cmp.tabla(fr, cols, altura=16)
            marco.pack(fill=BOTH, expand=YES)
            self.nb.add(fr, text=nombre)
            self.tablas[nombre] = (tv, cols)
        self.refrescar()

    def refrescar(self):
        d, h = self.e_desde.get(), self.e_hasta.get()
        for nombre, (cols, fn) in self.defs.items():
            datos = fn(d, h)
            self.datos[nombre] = datos
            tv, _ = self.tablas[nombre]

            def fmt(clave, valor):
                if clave == "total":
                    return tema.moneda(valor)
                if clave == "hora":
                    return f"{valor:02d}:00"
                return valor if valor is not None else ""
            cmp.llenar_tabla(tv, [(i, tuple(fmt(c[0], fila.get(c[0])) for c in cols)) for i, fila in enumerate(datos)])

    def exportar(self):
        nombre = self.nb.tab(self.nb.select(), "text")
        cols = self.defs[nombre][0]
        ruta = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"reporte_{nombre.lower().replace(' ', '_')}.csv",
                                            filetypes=[("CSV (Excel)", "*.csv")])
        if ruta:
            rl.exportar_csv(ruta, self.datos[nombre], [(c[0], c[1]) for c in cols])
            cmp.toast(self, "Reporte exportado")
