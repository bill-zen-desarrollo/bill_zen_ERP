"""Punto de venta: buscar producto, armar carrito y cobrar."""
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import facturacion_logic as fl
from logica import productos_logic as pl
from logica.seguridad import ErrorValidacion
from ui import componentes as cmp
from ui import tema
from ui.recibo import VentanaFactura


class Vista(ttk.Frame):
    TODAS_CATS = "Todas las categorías"

    def __init__(self, padre, principal):
        super().__init__(padre)
        self.carrito = {}  # id_producto -> dict
        self.categorias = pl.listar_categorias()
        self.cat_filtro_mapa = {c["nombre"]: c["id_categoria"] for c in self.categorias}

        cmp.encabezado(self, "Facturación", "Busca productos por nombre o código de barras y agrégalos al carrito").pack(anchor=W, pady=(0, 12))

        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill=BOTH, expand=YES)
        izq = ttk.Frame(cuerpo)
        izq.pack(side=LEFT, fill=BOTH, expand=YES, padx=(0, 14))
        der = ttk.Frame(cuerpo, width=420)
        der.pack(side=LEFT, fill=Y)
        der.pack_propagate(False)

        # --- Catálogo ---
        barra = ttk.Frame(izq)
        barra.pack(fill=X, pady=(0, 8))
        ttk.Label(barra, text="🔍", style="Fondo.TLabel", font=(tema.FUENTE, 13)).pack(side=LEFT, padx=(0, 6))
        self.e_buscar = ttk.Entry(barra, font=(tema.FUENTE, 12))
        self.e_buscar.pack(side=LEFT, fill=X, expand=YES)
        cmp.vincular_busqueda(self, self.e_buscar, self.buscar)
        self.e_buscar.bind("<Return>", self._enter_buscar)
        self.e_buscar.focus_set()

        self.cb_filtro_cat = ttk.Combobox(
            barra,
            values=[self.TODAS_CATS] + list(self.cat_filtro_mapa.keys()),
            state="readonly",
            width=20,
        )
        self.cb_filtro_cat.set(self.TODAS_CATS)
        self.cb_filtro_cat.pack(side=LEFT, padx=(8, 0))
        self.cb_filtro_cat.bind("<<ComboboxSelected>>", lambda e: self.buscar())

        marco, self.tv = cmp.tabla(
            izq,
            [
                ("codigo", "Código", 110, W),
                ("nombre", "Producto", 230, W),
                ("cat", "Categoría", 130, W),
                ("precio", "Precio", 100, E),
                ("stock", "Stock", 70, E),
            ],
            altura=15,
        )
        marco.pack(fill=BOTH, expand=YES)
        self.tv.bind("<Double-1>", lambda e: self.agregar())

        # Barra inferior del catálogo: selector de cantidad + botón Agregar al carrito
        barra_agregar = ttk.Frame(izq)
        barra_agregar.pack(fill=X, pady=(8, 0))
        ttk.Label(
            barra_agregar,
            text="Doble clic en un producto o elige la cantidad a agregar:",
            style="Subtitulo.TLabel",
        ).pack(side=LEFT)
        ttk.Button(
            barra_agregar,
            text="➕ Agregar al carrito",
            style="Zen.TButton",
            command=self.agregar,
        ).pack(side=RIGHT)
        self.sp_cant_agregar = ttk.Spinbox(
            barra_agregar,
            from_=1,
            to=9999,
            width=7,
            justify=CENTER,
        )
        self.sp_cant_agregar.set("1")
        self.sp_cant_agregar.pack(side=RIGHT, padx=(6, 10))
        self.sp_cant_agregar.bind("<Return>", lambda e: self.agregar())
        ttk.Label(
            barra_agregar,
            text="Cantidad:",
            style="Fondo.TLabel",
            font=(tema.FUENTE, 10, "bold"),
        ).pack(side=RIGHT)

        # --- Carrito ---
        borde = cmp.tarjeta(der, padding=14)
        borde.pack(fill=BOTH, expand=YES)
        c = borde.interior
        ttk.Label(c, text="Carrito", style="TarjetaTitulo.TLabel").pack(anchor=W)
        m2, self.tv_car = cmp.tabla(c, [("n", "Producto", 160, W), ("c", "Cant.", 50, E), ("t", "Total", 95, E)], altura=7)
        m2.pack(fill=BOTH, expand=YES, pady=6)
        self.tv_car.bind("<<TreeviewSelect>>", lambda e: self._sincronizar_entry_cantidad())

        fb = ttk.Frame(c, style="Tarjeta.TFrame")
        fb.pack(fill=X)
        ttk.Button(fb, text="＋", style="Zen.TButton", command=lambda: self.cambiar(1), padding=(10, 4)).pack(side=LEFT, padx=(0, 4))
        ttk.Button(fb, text="－", style="Suave.TButton", command=lambda: self.cambiar(-1), padding=(10, 4)).pack(side=LEFT, padx=(0, 6))

        ttk.Label(fb, text="Cant:", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(side=LEFT)
        self.e_cant_car = ttk.Entry(fb, width=5, justify=CENTER)
        self.e_cant_car.pack(side=LEFT, padx=4)
        self.e_cant_car.bind("<Return>", lambda e: self.fijar_cantidad_carrito())
        ttk.Button(fb, text="Aplicar", style="Oro.TButton", command=self.fijar_cantidad_carrito, padding=(8, 4)).pack(side=LEFT, padx=(0, 4))

        ttk.Button(fb, text="Vaciar", style="Peligro.TButton", command=self.vaciar, padding=(8, 4)).pack(side=RIGHT)
        ttk.Button(fb, text="Quitar", style="Suave.TButton", command=self.quitar, padding=(8, 4)).pack(side=RIGHT, padx=(0, 4))

        self.lbl_sub = self._fila_total(c, "Subtotal")
        self.lbl_iva = self._fila_total(c, "IVA")
        self.lbl_total = self._fila_total(c, "TOTAL", grande=True)

        ttk.Label(c, text="Método de pago", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(anchor=W, pady=(8, 2))
        self.cb_pago = ttk.Combobox(c, values=fl.METODOS_PAGO, state="readonly")
        self.cb_pago.set("Efectivo")
        self.cb_pago.pack(fill=X)
        self.cb_pago.bind("<<ComboboxSelected>>", lambda e: self._actualizar_cambio())
        fr = ttk.Frame(c, style="Tarjeta.TFrame")
        fr.pack(fill=X, pady=(8, 0))
        ttk.Label(fr, text="Recibido", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(side=LEFT)
        self.e_recibido = ttk.Entry(fr, width=14, justify=RIGHT)
        self.e_recibido.pack(side=RIGHT)
        self.e_recibido.bind("<KeyRelease>", lambda e: self._actualizar_cambio())
        self.lbl_cambio = ttk.Label(c, text="Cambio: $ 0", style="Tarjeta.TLabel", foreground=tema.GRIS)
        self.lbl_cambio.pack(anchor=E, pady=(2, 0))
        self.e_cliente = cmp.campo(c, "Cliente (opcional)")
        ttk.Button(c, text="COBRAR Y FACTURAR", style="Oro.TButton", command=self.cobrar).pack(fill=X, pady=(12, 0))

        self.productos = {}
        self.buscar()

    def _fila_total(self, padre, texto, grande=False):
        f = ttk.Frame(padre, style="Tarjeta.TFrame")
        f.pack(fill=X, pady=(8 if grande else 0, 0))
        ttk.Label(f, text=texto, style="Tarjeta.TLabel", font=(tema.FUENTE, 13 if grande else 10, "bold" if grande else "normal")).pack(side=LEFT)
        lbl = ttk.Label(f, text="$ 0", style="Tarjeta.TLabel", foreground=tema.VERDE if grande else tema.TEXTO,
                        font=(tema.FUENTE, 15 if grande else 10, "bold" if grande else "normal"))
        lbl.pack(side=RIGHT)
        return lbl

    # ---- Catálogo ----
    def buscar(self):
        cat_sel = self.cb_filtro_cat.get() if hasattr(self, "cb_filtro_cat") else self.TODAS_CATS
        id_cat = self.cat_filtro_mapa.get(cat_sel)
        filas = pl.listar_productos(self.e_buscar.get().strip(), id_categoria=id_cat)
        self.productos = {str(p["id_producto"]): p for p in filas}
        cmp.llenar_tabla(
            self.tv,
            [(p["id_producto"], (p["codigo"], p["nombre"], p["categoria"], tema.moneda(p["precio"]), p["stock"])) for p in filas],
            lambda _iid, v: ("alerta",) if v[4] <= 0 else (),
        )

    def _leer_cantidad_agregar(self) -> int:
        try:
            cant = pl._numero(self.sp_cant_agregar.get() or 1, "Cantidad", entero=True, minimo=1)
            return int(cant)
        except ErrorValidacion as e:
            cmp.mostrar_error(self, e)
            self.sp_cant_agregar.set("1")
            return 0

    def _enter_buscar(self, _e=None):
        """Enter con un código exacto (lector de barras) agrega directo."""
        texto = self.e_buscar.get().strip()
        p = pl.buscar_por_codigo(texto) if texto else None
        if p:
            cant = self._leer_cantidad_agregar()
            if cant > 0:
                self._agregar_producto(p, cantidad=cant)
                self.sp_cant_agregar.set("1")
                self.e_buscar.delete(0, END)
                self.buscar()
        elif len(self.tv.get_children()) == 1:
            self.tv.selection_set(self.tv.get_children()[0])
            self.agregar()

    def agregar(self):
        sel = self.tv.selection()
        if not sel:
            cmp.mostrar_error(self, "Selecciona primero un producto del catálogo.")
            return
        cant = self._leer_cantidad_agregar()
        if cant <= 0:
            return
        self._agregar_producto(self.productos[sel[0]], cantidad=cant)
        self.sp_cant_agregar.set("1")

    def _agregar_producto(self, p, cantidad: int = 1):
        pid = p["id_producto"]
        actual = self.carrito.get(pid, {"cantidad": 0})["cantidad"]
        if actual + cantidad > p["stock"]:
            cmp.mostrar_error(self, f"Stock insuficiente de «{p['nombre']}». Disponible: {p['stock']} (en carrito: {actual}).")
            return
        iva = p.get("iva_porcentaje")
        if iva is None:
            iva = next((x["iva_porcentaje"] for x in [self.productos.get(str(pid), {})] if x), 0)
        self.carrito[pid] = {
            "id_producto": pid,
            "nombre": p["nombre"],
            "precio": p["precio"],
            "stock": p["stock"],
            "iva_porcentaje": iva,
            "cantidad": actual + cantidad,
        }
        self.refrescar_carrito(seleccionar=pid)

    # ---- Carrito ----
    def _sel_car(self):
        s = self.tv_car.selection()
        if s:
            return int(s[0])
        # Si no hay fila seleccionada en la tabla del carrito pero el producto seleccionado en el catálogo está en el carrito
        sel_cat = self.tv.selection()
        if sel_cat and int(sel_cat[0]) in self.carrito:
            return int(sel_cat[0])
        # Si hay elementos en el carrito, operar sobre el último agregado
        if self.carrito:
            return list(self.carrito.keys())[-1]
        return None

    def _sincronizar_entry_cantidad(self):
        pid = self._sel_car()
        self.e_cant_car.delete(0, END)
        if pid is not None and pid in self.carrito:
            self.e_cant_car.insert(0, str(self.carrito[pid]["cantidad"]))

    def cambiar(self, delta):
        pid = self._sel_car()
        if pid is None or pid not in self.carrito:
            return
        item = self.carrito[pid]
        nueva = item["cantidad"] + delta
        if nueva <= 0:
            del self.carrito[pid]
        elif nueva > item["stock"]:
            cmp.mostrar_error(self, f"Stock insuficiente de «{item['nombre']}». Disponible: {item['stock']}.")
            return
        else:
            item["cantidad"] = nueva
        self.refrescar_carrito(pid if pid in self.carrito else None)

    def fijar_cantidad_carrito(self):
        pid = self._sel_car()
        if pid is None or pid not in self.carrito:
            cmp.mostrar_error(self, "Selecciona un producto del carrito para cambiar su cantidad.")
            return
        try:
            nueva = int(pl._numero(self.e_cant_car.get(), "Cantidad", entero=True, minimo=0))
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)

        item = self.carrito[pid]
        if nueva == 0:
            del self.carrito[pid]
        elif nueva > item["stock"]:
            cmp.mostrar_error(self, f"Stock insuficiente de «{item['nombre']}». Disponible: {item['stock']}.")
            self._sincronizar_entry_cantidad()
            return
        else:
            item["cantidad"] = nueva
        self.refrescar_carrito(pid if pid in self.carrito else None)

    def quitar(self):
        pid = self._sel_car()
        if pid is not None:
            self.carrito.pop(pid, None)
            self.refrescar_carrito()

    def vaciar(self):
        self.carrito.clear()
        self.refrescar_carrito()

    def refrescar_carrito(self, seleccionar=None):
        cmp.llenar_tabla(self.tv_car, [(pid, (i["nombre"], i["cantidad"], tema.moneda(i["precio"] * i["cantidad"])))
                                       for pid, i in self.carrito.items()])
        hijos = self.tv_car.get_children()
        if seleccionar is not None and str(seleccionar) in hijos:
            self.tv_car.selection_set(str(seleccionar))
        elif hijos and not self.tv_car.selection():
            self.tv_car.selection_set(hijos[-1])
        self._sincronizar_entry_cantidad()
        sub, iva, total = fl.calcular_totales(list(self.carrito.values()))
        self.total = total
        self.lbl_sub.configure(text=tema.moneda(sub))
        self.lbl_iva.configure(text=tema.moneda(iva))
        self.lbl_total.configure(text=tema.moneda(total))
        self._actualizar_cambio()

    def _actualizar_cambio(self):
        if self.cb_pago.get() != "Efectivo":
            self.lbl_cambio.configure(text="Pago sin efectivo")
            return
        try:
            recibido = pl._numero(self.e_recibido.get() or 0, "Recibido")
        except ErrorValidacion:
            recibido = 0
        self.lbl_cambio.configure(text=f"Cambio: {tema.moneda(max(recibido - getattr(self, 'total', 0), 0))}")

    def cobrar(self):
        if not self.carrito:
            cmp.mostrar_error(self, "Agrega al menos un producto al carrito.")
            return
        try:
            recibido = pl._numero(self.e_recibido.get() or 0, "Recibido") if self.cb_pago.get() == "Efectivo" else 0
            id_factura = fl.emitir_factura(
                [{"id_producto": i["id_producto"], "cantidad": i["cantidad"]} for i in self.carrito.values()],
                self.cb_pago.get(), recibido, cliente_nombre=self.e_cliente.get())
            factura = fl.obtener_factura(id_factura)
        except ErrorValidacion as e:
            cmp.mostrar_error(self, e)
            self.buscar()
            return
        self.carrito.clear()
        self.e_recibido.delete(0, END)
        self.e_cliente.delete(0, END)
        self.refrescar_carrito()
        self.buscar()
        VentanaFactura(self, factura)
