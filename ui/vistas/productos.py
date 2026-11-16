"""Gestión de productos: lista + formulario lateral (crear / editar / activar)."""
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import productos_logic as pl
from logica.seguridad import ErrorValidacion
from ui import componentes as cmp
from ui import tema


class Vista(ttk.Frame):
    TODAS_CATS = "Todas las categorías"

    def __init__(self, padre, principal):
        super().__init__(padre)
        self.id_editando = None
        self.categorias = pl.listar_categorias()
        self.cat_por_nombre = {f"{c['nombre']}  (IVA {c['iva_porcentaje']:.0f}%)": c for c in self.categorias}
        self.cat_filtro_mapa = {c["nombre"]: c["id_categoria"] for c in self.categorias}

        cmp.encabezado(self, "Productos", "Crea y administra tu catálogo. El IVA se aplica según la categoría.").pack(anchor=W, pady=(0, 12))
        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill=BOTH, expand=YES)

        izq = ttk.Frame(cuerpo)
        izq.pack(side=LEFT, fill=BOTH, expand=YES, padx=(0, 16))
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

        self.var_inactivos = ttk.BooleanVar(value=False)
        ttk.Checkbutton(barra, text="Ver inactivos", variable=self.var_inactivos, command=self.refrescar).pack(side=LEFT, padx=10)
        ttk.Button(barra, text="📥 Subir Excel", style="Info.TButton", command=self.importar_excel).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(barra, text="📄 Bajar plantilla", style="Suave.TButton", command=self.descargar_plantilla).pack(side=RIGHT, padx=(8, 0))
        marco, self.tv = cmp.tabla(
            izq,
            [
                ("codigo", "Código", 105, W),
                ("nombre", "Producto", 240, W),
                ("cat", "Categoría", 145, W),
                ("precio", "Precio", 95, E),
                ("costo", "Costo", 95, E),
                ("stock", "Stock", 65, E),
            ],
            altura=17,
        )
        marco.pack(fill=BOTH, expand=YES)
        self.tv.bind("<<TreeviewSelect>>", lambda e: self.cargar_seleccion())

        # ---- Formulario ----
        borde = cmp.tarjeta(cuerpo, padding=24)
        borde.pack(side=LEFT, fill=Y)
        c = borde.interior
        self.lbl_modo = ttk.Label(c, text="Nuevo producto", style="TarjetaTitulo.TLabel")
        self.lbl_modo.pack(anchor=W, pady=(0, 10))
        self.e_codigo = cmp.campo(c, "Código de barras / SKU *", ancho=45)
        self.e_nombre = cmp.campo(c, "Nombre del producto *", ancho=45)
        
        ttk.Label(c, text="Categoría * (define el IVA)", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(anchor=W, pady=(12, 4))
        cat_frame = ttk.Frame(c, style="Tarjeta.TFrame")
        cat_frame.pack(fill=X, pady=(0, 10))
        self.cb_cat = ttk.Combobox(cat_frame, values=list(self.cat_por_nombre), state="readonly")
        self.cb_cat.pack(side=LEFT, fill=X, expand=YES, padx=(0, 8))
        ttk.Button(cat_frame, text="+ Cat", style="Oro.TButton", command=self.nueva_categoria, width=6).pack(side=RIGHT)
        
        self.cb_cat.bind("<<ComboboxSelected>>", lambda e: self._pista_iva())
        self.lbl_iva = ttk.Label(c, text="", style="Tarjeta.TLabel", foreground=tema.VERDE_CLARO, font=(tema.FUENTE, 9, "italic"))
        self.lbl_iva.pack(anchor=W, pady=(0, 10))
        
        fila = ttk.Frame(c, style="Tarjeta.TFrame")
        fila.pack(fill=X, pady=(0, 10))
        fila.columnconfigure((0, 1), weight=1)
        self.e_costo = cmp.campo(fila, "Costo proveedor *", 0, 0, 12)
        self.e_precio = cmp.campo(fila, "Precio de venta *", 0, 1, 12)
        self.e_costo.bind("<KeyRelease>", lambda e: self._pista_iva())
        self.e_precio.bind("<KeyRelease>", lambda e: self._pista_iva())
        
        fila2 = ttk.Frame(c, style="Tarjeta.TFrame")
        fila2.pack(fill=X, pady=(0, 10))
        fila2.columnconfigure((0, 1), weight=1)
        self.e_stock = cmp.campo(fila2, "Stock inicial", 0, 0, 12)
        self.e_minimo = cmp.campo(fila2, "Stock mínimo", 0, 1, 12)
        self.e_minimo.insert(0, "5")
        
        self.lbl_nota = ttk.Label(c, text="", style="Tarjeta.TLabel", foreground=tema.GRIS, wraplength=350, font=(tema.FUENTE, 8))
        self.lbl_nota.pack(anchor=W, pady=(6, 0))

        btn_frame = ttk.Frame(c, style="Tarjeta.TFrame")
        btn_frame.pack(fill=X, pady=(20, 10))
        self.btn_guardar = ttk.Button(btn_frame, text="Crear producto", style="Zen.TButton", command=self.guardar)
        self.btn_guardar.pack(side=LEFT, fill=X, expand=YES, padx=(0, 4))
        ttk.Button(btn_frame, text="Nuevo / Limpiar", style="Suave.TButton", command=self.limpiar).pack(side=LEFT, fill=X, expand=YES, padx=(4, 0))
        
        self.btn_estado = ttk.Button(c, text="Desactivar producto", style="Peligro.TButton", command=self.alternar_estado)
        self.btn_estado.pack(fill=X, pady=2)

        self.refrescar()
        self.limpiar()

    def descargar_plantilla(self):
        import os
        from tkinter import filedialog
        try:
            from logica.importacion_logic import exportar_plantilla
            carpeta_descargas = os.path.join(os.path.expanduser("~"), "Downloads")
            if not os.path.isdir(carpeta_descargas):
                carpeta_descargas = os.path.expanduser("~")
            ruta = filedialog.asksaveasfilename(
                parent=self.winfo_toplevel(),
                initialdir=carpeta_descargas,
                defaultextension=".xlsx",
                filetypes=[("Archivo de Excel", "*.xlsx")],
                initialfile="plantilla_productos.xlsx",
                title="Guardar plantilla de Excel",
            )
            if ruta:
                exportar_plantilla(ruta)
                cmp.toast(self, "Plantilla de Excel descargada")
        except Exception as e:
            cmp.mostrar_error(self, str(e))

    def importar_excel(self):
        import os
        from tkinter import filedialog
        try:
            from logica.importacion_logic import importar_inventario
            carpeta_descargas = os.path.join(os.path.expanduser("~"), "Downloads")
            if not os.path.isdir(carpeta_descargas):
                carpeta_descargas = os.path.expanduser("~")
            ruta = filedialog.askopenfilename(
                parent=self.winfo_toplevel(),
                initialdir=carpeta_descargas,
                filetypes=[("Archivo de Excel", "*.xlsx")],
                title="Seleccionar archivo de Excel a subir",
            )
            if ruta:
                importar_inventario(ruta)
                cmp.toast(self, "Inventario de Excel subido con éxito")
                self.refrescar()
        except Exception as e:
            cmp.mostrar_error(self, str(e))

    def _pista_iva(self):
        cat = self.cat_por_nombre.get(self.cb_cat.get())
        iva = cat["iva_porcentaje"] if cat else 0
        txt_iva = "Exento de IVA (0%)" if iva == 0 else f"IVA incluido del {iva:.0f}%"
        try:
            costo = pl._numero(self.e_costo.get() or 0, "Costo")
            precio = pl._numero(self.e_precio.get() or 0, "Precio")
        except ErrorValidacion:
            costo, precio = 0, 0

        if precio > 0 and costo > 0:
            if precio < costo:
                self.lbl_iva.configure(
                    text=f"⚠ El precio de venta ({tema.moneda(precio)}) es menor al costo ({tema.moneda(costo)})",
                    foreground=tema.ROJO,
                )
                return
            base_neta = precio / (1 + iva / 100)
            ganancia = base_neta - costo
            margen = (ganancia / costo * 100) if costo else 0
            color = tema.VERDE_CLARO if ganancia > 0 else tema.ROJO
            self.lbl_iva.configure(
                text=f"{txt_iva} · Ganancia neta/u: {tema.moneda(ganancia)} ({margen:.0f}%)",
                foreground=color,
            )
        elif cat:
            self.lbl_iva.configure(text=txt_iva, foreground=tema.VERDE_CLARO)
        else:
            self.lbl_iva.configure(text="", foreground=tema.VERDE_CLARO)

    def refrescar(self):
        cat_sel = self.cb_filtro_cat.get()
        id_cat = self.cat_filtro_mapa.get(cat_sel)
        ver_inactivos = self.var_inactivos.get()
        filas = pl.listar_productos(
            self.e_buscar.get().strip(),
            solo_activos=not ver_inactivos,
            id_categoria=id_cat,
            solo_inactivos=ver_inactivos,
        )
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
                        tema.moneda(p["precio"]),
                        tema.moneda(p["costo"]),
                        p["stock"],
                    ),
                )
                for p in filas
            ],
            lambda i, _v: ("anulada",)
            if not self.filas[str(i)]["activo"]
            else (("alerta",) if self.filas[str(i)]["stock"] <= self.filas[str(i)]["stock_minimo"] else ()),
        )

    def limpiar(self):
        self.id_editando = None
        self.lbl_modo.configure(text="Nuevo producto")
        self.btn_guardar.configure(text="Crear producto")
        for e in (self.e_codigo, self.e_nombre, self.e_costo, self.e_precio, self.e_stock):
            e.delete(0, END)
        self.e_minimo.delete(0, END)
        self.e_minimo.insert(0, "5")
        self.e_stock.configure(state=NORMAL)
        self.cb_cat.set("")
        self.lbl_iva.configure(text="")
        self.lbl_nota.configure(text="")
        self.btn_estado.configure(state=DISABLED)
        self.tv.selection_remove(self.tv.selection())
        self.e_codigo.focus_set()

    def cargar_seleccion(self):
        s = self.tv.selection()
        if not s:
            return
        p = self.filas[s[0]]
        self.id_editando = p["id_producto"]
        self.lbl_modo.configure(text=f"Editando: {p['nombre']}")
        self.btn_guardar.configure(text="Guardar cambios")
        for e, v in (
            (self.e_codigo, p["codigo"]),
            (self.e_nombre, p["nombre"]),
            (self.e_costo, f"{p['costo']:.0f}"),
            (self.e_precio, f"{p['precio']:.0f}"),
            (self.e_minimo, p["stock_minimo"]),
        ):
            e.delete(0, END)
            e.insert(0, v)
        self.e_stock.delete(0, END)
        self.e_stock.insert(0, p["stock"])
        self.e_stock.configure(state=DISABLED)
        self.lbl_nota.configure(text="El stock solo cambia con «Entrada de mercancía» (Inventario) o al facturar. Costo y precio de venta sí puedes actualizarlos aquí.")
        self.cb_cat.set(next(k for k, c in self.cat_por_nombre.items() if c["id_categoria"] == p["id_categoria"]))
        self._pista_iva()
        self.btn_estado.configure(state=NORMAL, text="Desactivar producto" if p["activo"] else "Reactivar producto")

    def guardar(self):
        cat = self.cat_por_nombre.get(self.cb_cat.get())
        datos = {
            "codigo": self.e_codigo.get(),
            "nombre": self.e_nombre.get(),
            "id_categoria": cat["id_categoria"] if cat else None,
            "costo": self.e_costo.get(),
            "precio": self.e_precio.get(),
            "stock_minimo": self.e_minimo.get(),
            "stock_inicial": self.e_stock.get() if not self.id_editando else 0,
        }
        try:
            pl.guardar_producto(datos, self.id_editando)
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)
        cmp.toast(self, "Producto guardado")
        self.refrescar()
        self.limpiar()

    def alternar_estado(self):
        if not self.id_editando:
            return
        p = self.filas.get(str(self.id_editando))
        nuevo = not p["activo"]
        if cmp.confirmar(self, f"¿{'Reactivar' if nuevo else 'Desactivar'} «{p['nombre']}»?"):
            pl.cambiar_estado_producto(self.id_editando, nuevo)
            self.refrescar()
            self.limpiar()

    def nueva_categoria(self):
        VentanaCategoria(self, self._tras_categoria)

    def _tras_categoria(self):
        self.categorias = pl.listar_categorias()
        self.cat_por_nombre = {f"{c['nombre']}  (IVA {c['iva_porcentaje']:.0f}%)": c for c in self.categorias}
        self.cat_filtro_mapa = {c["nombre"]: c["id_categoria"] for c in self.categorias}
        self.cb_cat.configure(values=list(self.cat_por_nombre))
        self.cb_filtro_cat.configure(values=[self.TODAS_CATS] + list(self.cat_filtro_mapa.keys()))


class VentanaCategoria(ttk.Toplevel):
    def __init__(self, padre, al_guardar):
        super().__init__(title="Nueva categoría", master=padre.winfo_toplevel())
        self.al_guardar = al_guardar
        self.configure(background=tema.BEIGE)
        self.geometry("380x330")
        self.transient(padre.winfo_toplevel())
        m = ttk.Frame(self, padding=22)
        m.pack(fill=BOTH, expand=YES)
        ttk.Label(m, text="Nueva categoría", style="Titulo.TLabel", font=(tema.FUENTE_TITULO, 15, "bold")).pack(anchor=W)
        self.e_n = cmp.campo(m, "Nombre *", estilo_label="Fondo.TLabel")
        self.e_d = cmp.campo(m, "Descripción", estilo_label="Fondo.TLabel")
        self.e_iva = cmp.campo(m, "IVA % (0 para canasta familiar, 5, 19)", estilo_label="Fondo.TLabel")
        self.e_iva.insert(0, "19")
        ttk.Button(m, text="Guardar", style="Zen.TButton", command=self.guardar).pack(anchor=E, pady=(18, 0))

    def guardar(self):
        try:
            pl.guardar_categoria(self.e_n.get(), self.e_d.get(), self.e_iva.get())
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)
        self.al_guardar()
        self.destroy()
