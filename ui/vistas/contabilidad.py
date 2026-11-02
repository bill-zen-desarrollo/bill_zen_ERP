"""Contabilidad: registro de gastos y estado de resultados (ingresos vs gastos)."""
from datetime import date

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import reportes_logic as rl
from logica.seguridad import ErrorValidacion
from ui import componentes as cmp
from ui import tema


class Vista(ttk.Frame):
    def __init__(self, padre, principal):
        super().__init__(padre)
        cmp.encabezado(self, "Contabilidad", "Registra tus gastos y conoce tu utilidad real").pack(anchor=W, pady=(0, 12))

        f = ttk.Frame(self)
        f.pack(fill=X, pady=(0, 8))
        ttk.Label(f, text="Desde", style="Fondo.TLabel").pack(side=LEFT)
        self.e_desde = ttk.Entry(f, width=12)
        self.e_desde.insert(0, date.today().replace(day=1).isoformat())
        self.e_desde.pack(side=LEFT, padx=(4, 12))
        ttk.Label(f, text="Hasta", style="Fondo.TLabel").pack(side=LEFT)
        self.e_hasta = ttk.Entry(f, width=12)
        self.e_hasta.insert(0, date.today().isoformat())
        self.e_hasta.pack(side=LEFT, padx=(4, 12))
        ttk.Button(f, text="Actualizar", style="Zen.TButton", command=self.refrescar).pack(side=LEFT)

        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill=BOTH, expand=YES)
        izq = ttk.Frame(cuerpo)
        izq.pack(side=LEFT, fill=BOTH, expand=YES, padx=(0, 16))

        self.res = cmp.tarjeta(izq, padding=16)
        self.res.pack(fill=X, pady=(0, 10))
        self.marco_res = self.res.interior
        marco, self.tv = cmp.tabla(izq, [("f", "Fecha", 90, W), ("c", "Concepto", 220, W), ("k", "Categoría", 130, W), ("v", "Valor", 100, E), ("u", "Usuario", 80, W)], altura=9)
        marco.pack(fill=BOTH, expand=YES)
        ttk.Button(izq, text="Eliminar gasto seleccionado", style="Peligro.TButton", command=self.eliminar).pack(anchor=E, pady=(8, 0))

        borde = cmp.tarjeta(cuerpo, padding=18)
        borde.pack(side=LEFT, fill=Y)
        c = borde.interior
        ttk.Label(c, text="Registrar gasto", style="TarjetaTitulo.TLabel").pack(anchor=W)
        self.e_fecha = cmp.campo(c, "Fecha (AAAA-MM-DD)", ancho=26)
        self.e_fecha.insert(0, date.today().isoformat())
        self.e_concepto = cmp.campo(c, "Concepto *", ancho=26)
        ttk.Label(c, text="Categoría *", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(anchor=W, pady=(8, 2))
        self.cb = ttk.Combobox(c, values=rl.CATEGORIAS_GASTO, state="readonly")
        self.cb.set(rl.CATEGORIAS_GASTO[0])
        self.cb.pack(fill=X)
        self.e_valor = cmp.campo(c, "Valor *", ancho=26)
        ttk.Button(c, text="Guardar gasto", style="Zen.TButton", command=self.guardar).pack(fill=X, pady=(16, 0))
        self.refrescar()

    def refrescar(self):
        d, h = self.e_desde.get(), self.e_hasta.get()
        r = rl.estado_resultados(d, h)
        for w in self.marco_res.winfo_children():
            w.destroy()
        ttk.Label(self.marco_res, text="Estado de resultados", style="TarjetaTitulo.TLabel").grid(row=0, column=0, sticky=W, columnspan=2)
        lineas = [("Ventas netas (sin IVA)", r["ventas_netas"], False), ("(−) Costo de lo vendido", r["costo_ventas"], False),
                  ("Utilidad bruta", r["utilidad_bruta"], True), ("(−) Gastos", r["gastos"], False),
                  ("UTILIDAD NETA", r["utilidad_neta"], True), ("IVA recaudado (informativo)", r["iva"], False)]
        for i, (t, v, neg) in enumerate(lineas, start=1):
            col = tema.TEXTO
            if t == "UTILIDAD NETA":
                col = tema.VERDE if v >= 0 else tema.ROJO
            ttk.Label(self.marco_res, text=t, style="Tarjeta.TLabel", font=(tema.FUENTE, 10, "bold" if neg else "normal")).grid(row=i, column=0, sticky=W, pady=1)
            ttk.Label(self.marco_res, text=tema.moneda(v), style="Tarjeta.TLabel", foreground=col,
                      font=(tema.FUENTE, 10, "bold" if neg else "normal")).grid(row=i, column=1, sticky=E, padx=(40, 0))
        self.marco_res.columnconfigure(0, weight=1)
        gastos = rl.listar_gastos(d, h)
        cmp.llenar_tabla(self.tv, [(g["id_gasto"], (g["fecha"], g["concepto"], g["categoria"], tema.moneda(g["valor"]), g["username"])) for g in gastos])

    def guardar(self):
        try:
            rl.registrar_gasto(self.e_fecha.get().strip(), self.e_concepto.get(), self.cb.get(), self.e_valor.get())
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)
        cmp.toast(self, "Gasto registrado")
        self.e_concepto.delete(0, END)
        self.e_valor.delete(0, END)
        self.refrescar()

    def eliminar(self):
        s = self.tv.selection()
        if s and cmp.confirmar(self, "¿Eliminar el gasto seleccionado?"):
            rl.eliminar_gasto(int(s[0]))
            self.refrescar()
