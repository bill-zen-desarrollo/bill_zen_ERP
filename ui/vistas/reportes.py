"""Reportes con selector de fechas, rangos rápidos y exportación a CSV."""
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
        cmp.encabezado(
            self,
            "Reportes",
            "Analiza tus ventas y auditoría por rango de fechas, producto, categoría, método de pago, cajero y hora",
        ).pack(anchor=W, pady=(0, 12))

        hoy = date.today()
        ini_def = hoy - timedelta(days=30)

        card = cmp.tarjeta(self, padding=20)
        card.pack(fill=BOTH, expand=YES)
        cont = card.interior

        f = ttk.Frame(cont, style="Tarjeta.TFrame")
        f.pack(fill=X, pady=(0, 8))

        ttk.Label(f, text="Desde", style="FormLabel.TLabel").pack(side=LEFT)
        self.de_desde = ttk.DateEntry(f, dateformat="%Y-%m-%d", startdate=ini_def, width=11, bootstyle="success")
        self.de_desde.pack(side=LEFT, padx=(6, 12))
        self.e_desde = self.de_desde.entry

        ttk.Label(f, text="Hasta", style="FormLabel.TLabel").pack(side=LEFT)
        self.de_hasta = ttk.DateEntry(f, dateformat="%Y-%m-%d", startdate=hoy, width=11, bootstyle="success")
        self.de_hasta.pack(side=LEFT, padx=(6, 10))
        self.e_hasta = self.de_hasta.entry

        self.e_desde.bind("<Return>", lambda e: self.refrescar())
        self.e_hasta.bind("<Return>", lambda e: self.refrescar())
        self.de_desde.bind("<<DateEntrySelected>>", lambda e: self.refrescar())
        self.de_hasta.bind("<<DateEntrySelected>>", lambda e: self.refrescar())

        ttk.Button(f, text="Generar", style="Zen.TButton", command=self.refrescar, padding=(12, 7)).pack(side=LEFT, padx=(0, 8))

        # Accesos rápidos de rango de fechas para filtrar en un clic
        for etiqueta, fn in (
            ("Hoy", self._rango_hoy),
            ("7 días", lambda: self._rango_dias(6)),
            ("Este mes", self._rango_mes_actual),
            ("Mes anterior", self._rango_mes_anterior),
            ("30 días", lambda: self._rango_dias(30)),
        ):
            ttk.Button(f, text=etiqueta, style="Suave.TButton", command=fn, padding=(10, 7)).pack(side=LEFT, padx=2)

        ttk.Button(f, text="Exportar a CSV", style="Oro.TButton", command=self.exportar, padding=(14, 7)).pack(side=RIGHT)

        self.lbl_rango = ttk.Label(
            cont,
            text="",
            style="Tarjeta.TLabel",
            foreground=tema.GRIS,
            font=(tema.FUENTE, 10),
        )
        self.lbl_rango.pack(anchor=W, pady=(0, 8))

        self.nb = ttk.Notebook(cont)
        self.nb.pack(fill=BOTH, expand=YES)
        self.defs = {
            "Más vendidos": (
                [("nombre", "Producto", 280, W), ("unidades", "Unidades", 95, E), ("total", "Total vendido", 135, E)],
                lambda d, h: rl.top_productos(d, h, 50),
            ),
            "Por categoría": (
                [("nombre", "Categoría", 280, W), ("total", "Total vendido", 135, E)],
                rl.ventas_por_categoria,
            ),
            "Por método de pago": (
                [("metodo_pago", "Método", 220, W), ("n", "Facturas", 95, E), ("total", "Total", 135, E)],
                rl.ventas_por_metodo,
            ),
            "Por cajero": (
                [("cajero", "Cajero", 240, W), ("n", "Facturas", 95, E), ("total", "Total", 135, E)],
                rl.ventas_por_cajero,
            ),
            "Por hora": (
                [("hora", "Hora", 100, W), ("n", "Facturas", 95, E), ("total", "Total", 135, E)],
                rl.ventas_por_hora,
            ),
            "Auditoría": (
                [("fecha", "Fecha", 155, W), ("usuario", "Usuario", 105, W), ("accion", "Acción", 175, W), ("detalle", "Detalle", 320, W)],
                lambda d, h: rl.ultimas_auditorias(d, h),
            ),
        }
        self.tablas = {}
        self.datos = {}
        for nombre, (cols, _) in self.defs.items():
            fr = ttk.Frame(self.nb, style="Tarjeta.TFrame", padding=12)
            marco, tv = cmp.tabla(fr, cols, altura=14)
            marco.pack(fill=BOTH, expand=YES)
            self.nb.add(fr, text=nombre)
            self.tablas[nombre] = (tv, cols)
        self.refrescar()

    def _fijar_rango(self, desde: date, hasta: date):
        self.e_desde.delete(0, END)
        self.e_desde.insert(0, desde.isoformat())
        self.e_hasta.delete(0, END)
        self.e_hasta.insert(0, hasta.isoformat())
        self.refrescar()

    def _rango_hoy(self):
        hoy = date.today()
        self._fijar_rango(hoy, hoy)

    def _rango_dias(self, dias: int):
        hoy = date.today()
        self._fijar_rango(hoy - timedelta(days=dias), hoy)

    def _rango_mes_actual(self):
        hoy = date.today()
        self._fijar_rango(hoy.replace(day=1), hoy)

    def _rango_mes_anterior(self):
        primero_actual = date.today().replace(day=1)
        fin_ant = primero_actual - timedelta(days=1)
        ini_ant = fin_ant.replace(day=1)
        self._fijar_rango(ini_ant, fin_ant)

    def refrescar(self):
        d = self.e_desde.get().strip()
        h = self.e_hasta.get().strip()
        try:
            d_ini = date.fromisoformat(d)
            d_fin = date.fromisoformat(h)
        except ValueError:
            cmp.mostrar_error(self, "Formato de fecha inválido. Usa AAAA-MM-DD (por ejemplo 2026-11-16) o el calendario.")
            return

        if d_ini > d_fin:
            cmp.mostrar_error(self, "La fecha 'Desde' no puede ser posterior a la fecha 'Hasta'.")
            return

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

            cmp.llenar_tabla(
                tv,
                [(i, tuple(fmt(c[0], fila.get(c[0])) for c in cols)) for i, fila in enumerate(datos)],
            )

        self.lbl_rango.configure(text=f"Rango aplicado: {d} al {h}")

    def exportar(self):
        nombre = self.nb.tab(self.nb.select(), "text")
        cols = self.defs[nombre][0]
        ruta = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=f"reporte_{nombre.lower().replace(' ', '_')}.csv",
            filetypes=[("CSV (Excel)", "*.csv")],
        )
        if ruta:
            rl.exportar_csv(ruta, self.datos[nombre], [(c[0], c[1]) for c in cols])
            cmp.toast(self, "Reporte exportado")
