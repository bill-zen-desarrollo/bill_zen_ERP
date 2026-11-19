"""Historial de facturas: ver, imprimir y (admin) anular."""
from datetime import date, timedelta

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import facturacion_logic as fl
from logica.seguridad import ErrorValidacion, Sesion
from ui import componentes as cmp
from ui import tema
from ui.recibo import VentanaFactura


class Vista(ttk.Frame):
    def __init__(self, padre, principal):
        super().__init__(padre)
        sub = "Todas las ventas del negocio" if Sesion.es_admin() else "Tus ventas"
        cmp.encabezado(self, "Facturas emitidas", sub).pack(anchor=W, pady=(0, 12))

        card = cmp.tarjeta(self, padding=20)
        card.pack(fill=BOTH, expand=YES)
        cont = card.interior

        hoy = date.today()
        ini_def = hoy - timedelta(days=30)

        f = ttk.Frame(cont, style="Tarjeta.TFrame")
        f.pack(fill=X, pady=(0, 12))
        ttk.Label(f, text="Desde", style="FormLabel.TLabel").pack(side=LEFT)
        self.de_desde = ttk.DateEntry(f, dateformat="%Y-%m-%d", startdate=ini_def, width=10, bootstyle="success")
        self.de_desde.pack(side=LEFT, padx=(6, 10))
        self.e_desde = self.de_desde.entry

        ttk.Label(f, text="Hasta", style="FormLabel.TLabel").pack(side=LEFT)
        self.de_hasta = ttk.DateEntry(f, dateformat="%Y-%m-%d", startdate=hoy, width=10, bootstyle="success")
        self.de_hasta.pack(side=LEFT, padx=(6, 10))
        self.e_hasta = self.de_hasta.entry

        self.e_desde.bind("<Return>", lambda _e: self.refrescar())
        self.e_hasta.bind("<Return>", lambda _e: self.refrescar())
        self.de_desde.bind("<<DateEntrySelected>>", lambda _e: self.refrescar())
        self.de_hasta.bind("<<DateEntrySelected>>", lambda _e: self.refrescar())

        for etiqueta, fn in (
            ("Hoy", self._rango_hoy),
            ("7 días", lambda: self._rango_dias(6)),
            ("Este mes", self._rango_mes_actual),
            ("Mes ant.", self._rango_mes_anterior),
            ("30 días", lambda: self._rango_dias(30)),
        ):
            ttk.Button(f, text=etiqueta, style="Suave.TButton", command=fn, padding=(8, 6)).pack(side=LEFT, padx=2)

        self.e_texto = ttk.Entry(f, width=18, font=(tema.FUENTE, 11))
        self.e_texto.pack(side=LEFT, fill=X, expand=YES, padx=(8, 6))
        cmp.vincular_busqueda(self, self.e_texto, self.refrescar, espera=250)
        ttk.Label(f, text="(N° o cliente)", style="Tarjeta.TLabel", foreground=tema.GRIS, font=(tema.FUENTE, 10)).pack(side=LEFT)
        ttk.Button(f, text="Buscar", style="Zen.TButton", command=self.refrescar, padding=(12, 7)).pack(side=LEFT, padx=(8, 0))

        marco, self.tv = cmp.tabla(
            cont,
            [
                ("n", "Número", 115, W),
                ("f", "Fecha", 155, W),
                ("c", "Cliente", 200, W),
                ("m", "Pago", 130, W),
                ("t", "Total", 115, E),
                ("e", "Estado", 95, W),
                ("u", "Cajero", 105, W),
            ],
            altura=14,
        )
        marco.pack(fill=BOTH, expand=YES)
        self.tv.bind("<Double-1>", lambda e: self.ver())

        b = ttk.Frame(cont, style="Tarjeta.TFrame")
        b.pack(fill=X, pady=(12, 0))
        ttk.Button(b, text="Ver / Imprimir", style="Oro.TButton", command=self.ver).pack(side=LEFT)
        if Sesion.es_admin():
            ttk.Button(b, text="Anular factura", style="Peligro.TButton", command=self.anular).pack(side=LEFT, padx=8)
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
        try:
            filas = fl.listar_facturas(self.e_desde.get(), self.e_hasta.get(), self.e_texto.get().strip())
        except Exception as e:
            cmp.mostrar_error(self, e)
            return
        cmp.llenar_tabla(self.tv, [(r["id_factura"], (r["numero"], r["fecha"], r["cliente_nombre"], r["metodo_pago"],
                                                      tema.moneda(r["total"]), r["estado"].capitalize(), r["username"])) for r in filas],
                         lambda iid, v: ("anulada",) if v[5] == "Anulada" else ())

    def _sel(self):
        s = self.tv.selection()
        return int(s[0]) if s else None

    def ver(self):
        i = self._sel()
        if i:
            try:
                VentanaFactura(self, fl.obtener_factura(i))
            except ErrorValidacion as e:
                cmp.mostrar_error(self, e)

    def anular(self):
        i = self._sel()
        if not i:
            return cmp.mostrar_error(self, "Selecciona una factura.")
        from ttkbootstrap.dialogs import Querybox
        motivo = Querybox.get_string("Motivo de la anulación (el stock se devolverá al inventario):", "Anular factura", parent=self.winfo_toplevel())
        if not motivo:
            return
        try:
            fl.anular_factura(i, motivo)
            cmp.toast(self, "Factura anulada y stock restituido")
            self.refrescar()
        except ErrorValidacion as e:
            cmp.mostrar_error(self, e)
