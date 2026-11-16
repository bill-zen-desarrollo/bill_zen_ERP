"""Inventario: solo lectura para cajero; el admin además registra entradas de mercancía."""
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import productos_logic as pl
from logica.seguridad import ErrorValidacion, Sesion
from ui import componentes as cmp
from ui import tema


class Vista(ttk.Frame):
    TODAS_CATS = "Todas las categorías"

    def __init__(self, padre, principal):
        super().__init__(padre)
        es_admin = Sesion.es_admin()
        self.categorias = pl.listar_categorias()
        self.cat_filtro_mapa = {c["nombre"]: c["id_categoria"] for c in self.categorias}

        cmp.encabezado(self, "Inventario",
                       "Existencias actuales y entradas de mercancía" if es_admin else "Consulta de existencias (solo lectura)").pack(anchor=W, pady=(0, 12))
        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill=BOTH, expand=YES)
        izq = ttk.Frame(cuerpo)
        izq.pack(side=LEFT, fill=BOTH, expand=YES, padx=(0, 16 if es_admin else 0))

        barra = ttk.Frame(izq)
        barra.pack(fill=X, pady=(0, 8))
        self.e_buscar = ttk.Entry(barra)
        self.e_buscar.pack(side=LEFT, fill=X, expand=YES)
        cmp.vincular_busqueda(self, self.e_buscar, self.refrescar)

        self.cb_filtro_cat = ttk.Combobox(
            barra,
            values=[self.TODAS_CATS] + list(self.cat_filtro_mapa.keys()),
            state="readonly",
            width=22,
        )
        self.cb_filtro_cat.set(self.TODAS_CATS)
        self.cb_filtro_cat.pack(side=LEFT, padx=(8, 0))
        self.cb_filtro_cat.bind("<<ComboboxSelected>>", lambda e: self.refrescar())

        self.var_bajo = ttk.BooleanVar(value=False)
        ttk.Checkbutton(barra, text="Solo stock bajo", variable=self.var_bajo, command=self.refrescar).pack(side=LEFT, padx=10)
        ttk.Button(barra, text="Ver movimientos", style="Suave.TButton", command=self.movimientos).pack(side=RIGHT, padx=(10, 0))
        
        cols = [("codigo", "Código", 105, W), ("nombre", "Producto", 245, W), ("cat", "Categoría", 145, W),
                ("costo", "Costo", 95, E), ("precio", "Precio", 95, E), ("stock", "Stock", 65, E), ("min", "Mínimo", 65, E)]
        marco, self.tv = cmp.tabla(izq, cols, altura=18)
        marco.pack(fill=BOTH, expand=YES)
        self.tv.bind("<<TreeviewSelect>>", lambda e: self._sel())

        if es_admin:
            borde = cmp.tarjeta(cuerpo, padding=24)
            borde.pack(side=LEFT, fill=Y)
            c = borde.interior
            ttk.Label(c, text="Entrada de mercancía", style="TarjetaTitulo.TLabel").pack(anchor=W, pady=(0, 10))
            self.lbl_prod = ttk.Label(c, text="Selecciona un producto de la lista", style="Tarjeta.TLabel", foreground=tema.GRIS, wraplength=240)
            self.lbl_prod.pack(anchor=W, pady=(4, 16))
            self.e_cant = cmp.campo(c, "Cantidad que llegó *", ancho=45)
            self.e_costo = cmp.campo(c, "Nuevo costo proveedor (opcional)", ancho=45)
            self.e_precio = cmp.campo(c, "Nuevo precio de venta (opcional)", ancho=45)
            self.e_ref = cmp.campo(c, "Referencia (factura proveedor)", ancho=45)
            
            ttk.Label(c, text="El stock solo aumenta aquí y solo disminuye al facturar.", style="Tarjeta.TLabel",
                      foreground=tema.GRIS, wraplength=350, font=(tema.FUENTE, 8)).pack(anchor=W, pady=(10, 10))
            
            ttk.Button(c, text="Registrar entrada", style="Zen.TButton", command=self.entrada).pack(fill=X, pady=(10, 0))
        self.refrescar()

    def refrescar(self):
        cat_sel = self.cb_filtro_cat.get()
        id_cat = self.cat_filtro_mapa.get(cat_sel)
        filas = pl.listar_productos(self.e_buscar.get().strip(), id_categoria=id_cat)
        if self.var_bajo.get():
            filas = [p for p in filas if p["stock"] <= p["stock_minimo"]]
        self.filas = {str(p["id_producto"]): p for p in filas}

        cmp.llenar_tabla(
            self.tv,
            [
                (
                    p["id_producto"],
                    (
                        p["codigo"],
                        p["nombre"],
                        p["categoria"],
                        tema.moneda(p["costo"]),
                        tema.moneda(p["precio"]),
                        p["stock"],
                        p["stock_minimo"],
                    ),
                )
                for p in filas
            ],
            lambda i, _v: ("alerta",) if self.filas[str(i)]["stock"] <= self.filas[str(i)]["stock_minimo"] else (),
        )

    def _sel(self):
        s = self.tv.selection()
        if s and Sesion.es_admin():
            self.lbl_prod.configure(text=f"{self.filas[s[0]]['nombre']}\nStock actual: {self.filas[s[0]]['stock']}", foreground=tema.VERDE)

    def entrada(self):
        s = self.tv.selection()
        if not s:
            return cmp.mostrar_error(self, "Selecciona un producto de la lista.")
        try:
            nuevo = pl.registrar_entrada(
                int(s[0]),
                self.e_cant.get(),
                self.e_ref.get(),
                self.e_costo.get() or None,
                self.e_precio.get() or None,
            )
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)
        cmp.toast(self, f"Entrada registrada. Nuevo stock: {nuevo}")
        for e in (self.e_cant, self.e_costo, self.e_precio, self.e_ref):
            e.delete(0, END)
        self.refrescar()

    def movimientos(self):
        s = self.tv.selection()
        v = ttk.Toplevel(title="Movimientos de inventario", master=self.winfo_toplevel())
        v.geometry("860x480")
        v.configure(background=tema.BEIGE)
        m = ttk.Frame(v, padding=16)
        m.pack(fill=BOTH, expand=YES)
        marco, tv = cmp.tabla(m, [("f", "Fecha", 140, W), ("p", "Producto", 190, W), ("t", "Tipo", 90, W), ("c", "Cant.", 60, E),
                                  ("s", "Stock final", 80, E), ("r", "Referencia", 160, W), ("u", "Usuario", 80, W)], altura=16)
        marco.pack(fill=BOTH, expand=YES)
        datos = pl.historial_movimientos(int(s[0]) if s else None)
        cmp.llenar_tabla(tv, [(i, (d["fecha"], d["nombre"], d["tipo"].capitalize(), d["cantidad"], d["stock_final"], d["referencia"], d["username"]))
                              for i, d in enumerate(datos)])
