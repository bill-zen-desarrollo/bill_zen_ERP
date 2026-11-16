"""Punto de Venta (POS) ágil para Cajero: escaneo directo por lector de código de barras
con auto-agregado inmediato, buscador con autocompletado desplegable, control rápido de cantidades
y persistencia automática del carrito al cambiar de módulo."""
import time
import tkinter as tk

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import facturacion_logic as fl
from logica import productos_logic as pl
from logica.seguridad import ErrorValidacion, Sesion
from ui import componentes as cmp
from ui import tema
from ui.recibo import VentanaFactura


# Estado persistente en memoria de la factura en curso por usuario activo.
# Permite ir a Inventario o Facturas emitidas a consultar un dato y volver sin perder los productos agregados.
_BORRADOR_FACTURA: dict[int, dict] = {}


def limpiar_borrador_facturacion(id_usuario: int | None = None):
    """Limpia el borrador de facturación del usuario indicado (o de todos si es None, ej. al cerrar sesión)."""
    if id_usuario is None:
        _BORRADOR_FACTURA.clear()
    else:
        _BORRADOR_FACTURA.pop(id_usuario, None)


class Vista(ttk.Frame):
    def __init__(self, padre, principal):
        super().__init__(padre)
        self._uid = Sesion.id() or 0
        borrador = _BORRADOR_FACTURA.setdefault(
            self._uid,
            {
                "carrito": {},
                "metodo_pago": "Efectivo",
                "recibido": "",
                "cliente": "",
            },
        )
        # Referencia directa al diccionario persistente de este usuario
        self.carrito = borrador["carrito"]
        self._borrador = borrador

        self._catalogo_cache = []
        self._sugerencias_actuales = []
        self._timer_auto_scan = None
        self._ultimo_key_ts = 0.0
        self._rafaga_scanner = 0

        cmp.encabezado(
            self,
            "Facturación · Punto de Venta (POS)",
            "Escanea el código de barras (se agrega automáticamente) o escribe el nombre/código para autocompletar",
        ).pack(anchor=W, pady=(0, 10))

        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill=BOTH, expand=YES)

        # Panel izquierdo/central: Escáner + Autocompletado + Tabla principal de la factura
        izq = ttk.Frame(cuerpo)
        izq.pack(side=LEFT, fill=BOTH, expand=YES, padx=(0, 16))

        # Panel derecho: Totales y Cobro
        der = ttk.Frame(cuerpo, width=380)
        der.pack(side=LEFT, fill=Y)
        der.pack_propagate(False)

        # ================== 1. BARRA DE ESCANEO Y AUTOCOMPLETADO ==================
        card_scan = cmp.tarjeta(izq, padding=14)
        card_scan.pack(fill=X, pady=(0, 10))
        sc = card_scan.interior

        fila_tit_scan = ttk.Frame(sc, style="Tarjeta.TFrame")
        fila_tit_scan.pack(fill=X, pady=(0, 6))
        ttk.Label(
            fila_tit_scan,
            text="Código de Barras o Búsqueda con Autocompletado",
            style="TarjetaTitulo.TLabel",
        ).pack(side=LEFT)
        ttk.Label(
            fila_tit_scan,
            text="Lector USB: agrega al instante · Teclado: usa las flechas y Enter o clic en la sugerencia",
            style="Tarjeta.TLabel",
            foreground=tema.GRIS,
            font=(tema.FUENTE, 8),
        ).pack(side=RIGHT)

        fila_input = ttk.Frame(sc, style="Tarjeta.TFrame")
        fila_input.pack(fill=X)

        # Selector de cantidad previa antes de escanear o elegir producto
        marco_cant_prev = ttk.Frame(fila_input, style="Tarjeta.TFrame")
        marco_cant_prev.pack(side=LEFT, padx=(0, 10))
        ttk.Label(
            marco_cant_prev,
            text="Cant. a agregar:",
            style="Tarjeta.TLabel",
            font=(tema.FUENTE, 9, "bold"),
        ).pack(side=LEFT, padx=(0, 6))
        self.sp_cant_agregar = ttk.Spinbox(
            marco_cant_prev,
            from_=1,
            to=9999,
            width=6,
            justify=CENTER,
            font=(tema.FUENTE, 11, "bold"),
        )
        self.sp_cant_agregar.set("1")
        self.sp_cant_agregar.pack(side=LEFT)
        self.sp_cant_agregar.bind("<Return>", lambda e: self._confirmar_busqueda_o_sugerencia())

        # Campo principal de código de barras / autocompletar
        self.e_buscar = ttk.Entry(fila_input, font=(tema.FUENTE, 12))
        self.e_buscar.pack(side=LEFT, fill=X, expand=YES, padx=(0, 8))
        self.e_buscar.bind("<KeyRelease>", self._al_teclear_codigo)
        self.e_buscar.bind("<Return>", self._enter_buscar)
        self.e_buscar.bind("<Down>", self._mover_sugerencia_abajo)
        self.e_buscar.bind("<Up>", self._mover_sugerencia_arriba)
        self.e_buscar.bind("<Escape>", lambda e: self._ocultar_sugerencias())

        ttk.Button(
            fila_input,
            text="Agregar (Enter)",
            style="Zen.TButton",
            command=self._confirmar_busqueda_o_sugerencia,
        ).pack(side=RIGHT)

        # Lista desplegable de autocompletado (oculta cuando no se está escribiendo)
        self.marco_sugerencias = tk.Frame(sc, bg=tema.DORADO, padx=1, pady=1)
        self.lb_sugerencias = tk.Listbox(
            self.marco_sugerencias,
            height=6,
            font=(tema.FUENTE, 10),
            bg="#FBF8F1",
            fg=tema.TEXTO,
            selectbackground=tema.VERDE,
            selectforeground=tema.BLANCO,
            activestyle="none",
            relief="flat",
            borderwidth=0,
            cursor="hand2",
        )
        self.lb_sugerencias.pack(fill=X, expand=YES)
        self.lb_sugerencias.bind("<ButtonRelease-1>", self._clic_sugerencia)
        self.lb_sugerencias.bind("<Return>", self._clic_sugerencia)

        # ================== 2. TABLA PRINCIPAL DEL CARRITO / FACTURA ==================
        card_tabla = cmp.tarjeta(izq, padding=14)
        card_tabla.pack(fill=BOTH, expand=YES)
        ct = card_tabla.interior

        cab_car = ttk.Frame(ct, style="Tarjeta.TFrame")
        cab_car.pack(fill=X, pady=(0, 6))
        ttk.Label(cab_car, text="Detalle de Productos en la Factura Actual", style="TarjetaTitulo.TLabel").pack(side=LEFT)
        self.lbl_resumen_items = ttk.Label(
            cab_car,
            text="0 productos (0 unidades)",
            style="Tarjeta.TLabel",
            foreground=tema.VERDE,
            font=(tema.FUENTE, 9, "bold"),
        )
        self.lbl_resumen_items.pack(side=RIGHT)

        cols_carrito = [
            ("codigo", "Código", 115, W),
            ("n", "Producto / Descripción", 280, W),
            ("p", "Precio Unit.", 110, E),
            ("iva", "IVA", 65, E),
            ("c", "Cant.", 75, CENTER),
            ("t", "Subtotal Línea", 125, E),
        ]
        m2, self.tv_car = cmp.tabla(ct, cols_carrito, altura=14)
        m2.pack(fill=BOTH, expand=YES, pady=(0, 8))
        self.tv_car.bind("<<TreeviewSelect>>", lambda e: self._sincronizar_entry_cantidad())

        # Barra inferior de control de cantidades sobre el ítem seleccionado en la factura
        fb = ttk.Frame(ct, style="Tarjeta.TFrame")
        fb.pack(fill=X)

        ttk.Button(
            fb,
            text="+ Aumentar",
            style="Zen.TButton",
            command=lambda: self.cambiar(1),
            padding=(12, 6),
        ).pack(side=LEFT, padx=(0, 4))
        ttk.Button(
            fb,
            text="- Disminuir",
            style="Suave.TButton",
            command=lambda: self.cambiar(-1),
            padding=(12, 6),
        ).pack(side=LEFT, padx=(0, 12))

        ttk.Label(
            fb,
            text="Cantidad exacta:",
            style="Tarjeta.TLabel",
            font=(tema.FUENTE, 9, "bold"),
        ).pack(side=LEFT)
        self.e_cant_car = ttk.Entry(fb, width=6, justify=CENTER, font=(tema.FUENTE, 10, "bold"))
        self.e_cant_car.pack(side=LEFT, padx=6)
        self.e_cant_car.bind("<Return>", lambda e: self.fijar_cantidad_carrito())
        ttk.Button(
            fb,
            text="Aplicar",
            style="Oro.TButton",
            command=self.fijar_cantidad_carrito,
            padding=(10, 6),
        ).pack(side=LEFT, padx=(0, 8))

        ttk.Button(
            fb,
            text="Vaciar factura",
            style="Peligro.TButton",
            command=self.vaciar,
            padding=(10, 6),
        ).pack(side=RIGHT)
        ttk.Button(
            fb,
            text="Quitar producto",
            style="Suave.TButton",
            command=self.quitar,
            padding=(10, 6),
        ).pack(side=RIGHT, padx=(0, 6))

        # ================== 3. PANEL DERECHO: TOTALES Y COBRO ==================
        borde = cmp.tarjeta(der, padding=18)
        borde.pack(fill=BOTH, expand=YES)
        c = borde.interior
        ttk.Label(c, text="Resumen y Cobro", style="TarjetaTitulo.TLabel").pack(anchor=W, pady=(0, 8))

        self.lbl_sub = self._fila_total(c, "Subtotal (Base sin IVA)")
        self.lbl_iva = self._fila_total(c, "Impuesto IVA")
        ttk.Separator(c).pack(fill=X, pady=8)
        self.lbl_total = self._fila_total(c, "TOTAL A PAGAR", grande=True)
        ttk.Separator(c).pack(fill=X, pady=8)

        ttk.Label(c, text="Método de pago", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(anchor=W, pady=(6, 2))
        self.cb_pago = ttk.Combobox(c, values=fl.METODOS_PAGO, state="readonly", font=(tema.FUENTE, 10))
        metodo_guardado = self._borrador.get("metodo_pago", "Efectivo")
        self.cb_pago.set(metodo_guardado if metodo_guardado in fl.METODOS_PAGO else "Efectivo")
        self.cb_pago.pack(fill=X)
        self.cb_pago.bind("<<ComboboxSelected>>", lambda e: self._al_cambiar_datos_cobro())

        fr = ttk.Frame(c, style="Tarjeta.TFrame")
        fr.pack(fill=X, pady=(12, 0))
        ttk.Label(fr, text="Valor recibido ($)", style="Tarjeta.TLabel", font=(tema.FUENTE, 10, "bold")).pack(side=LEFT)
        self.e_recibido = ttk.Entry(fr, width=15, justify=RIGHT, font=(tema.FUENTE, 11, "bold"))
        if self._borrador.get("recibido"):
            self.e_recibido.insert(0, self._borrador["recibido"])
        self.e_recibido.pack(side=RIGHT)
        self.e_recibido.bind("<KeyRelease>", lambda e: self._al_cambiar_datos_cobro())
        self.e_recibido.bind("<Return>", lambda e: self.cobrar())

        self.lbl_cambio = ttk.Label(
            c,
            text="Cambio: $ 0",
            style="Tarjeta.TLabel",
            foreground=tema.VERDE_OSCURO,
            font=(tema.FUENTE_TITULO, 13, "bold"),
        )
        self.lbl_cambio.pack(anchor=E, pady=(6, 4))

        self.e_cliente = cmp.campo(c, "Cliente (opcional · Enter para Consumidor final)")
        if self._borrador.get("cliente"):
            self.e_cliente.insert(0, self._borrador["cliente"])
        self.e_cliente.bind("<KeyRelease>", lambda e: self._guardar_estado_borrador())
        self.e_cliente.bind("<Return>", lambda e: self.cobrar())

        ttk.Button(
            c,
            text="COBRAR Y EMITIR FACTURA",
            style="Oro.TButton",
            command=self.cobrar,
            padding=(14, 12),
        ).pack(fill=X, pady=(16, 0))

        self.productos = {}
        self.buscar()
        self._sincronizar_carrito_con_catalogo()
        self.refrescar_carrito()
        self.after(80, lambda: self.e_buscar.focus_set() if self.winfo_exists() else None)

    def _guardar_estado_borrador(self):
        if not hasattr(self, "_borrador"):
            return
        if hasattr(self, "cb_pago") and self.cb_pago.winfo_exists():
            self._borrador["metodo_pago"] = self.cb_pago.get()
        if hasattr(self, "e_recibido") and self.e_recibido.winfo_exists():
            self._borrador["recibido"] = self.e_recibido.get()
        if hasattr(self, "e_cliente") and self.e_cliente.winfo_exists():
            self._borrador["cliente"] = self.e_cliente.get()

    def _al_cambiar_datos_cobro(self):
        self._guardar_estado_borrador()
        self._actualizar_cambio()

    def _sincronizar_carrito_con_catalogo(self):
        """Actualiza stock y precios del carrito en curso si hubo cambios en Inventario/Productos."""
        if not self.carrito:
            return
        for pid, item in list(self.carrito.items()):
            fresco = self.productos.get(str(pid))
            if not fresco:
                # Si el producto fue desactivado mientras tanto, se retira
                self.carrito.pop(pid, None)
                continue
            item["stock"] = fresco["stock"]
            item["precio"] = fresco["precio"]
            item["nombre"] = fresco["nombre"]
            item["codigo"] = fresco.get("codigo", item.get("codigo", ""))
            item["iva_porcentaje"] = fresco.get("iva_porcentaje", item.get("iva_porcentaje", 0))
            if item["stock"] <= 0:
                self.carrito.pop(pid, None)
            elif item["cantidad"] > item["stock"]:
                item["cantidad"] = item["stock"]

    def _fila_total(self, padre, texto, grande=False):
        f = ttk.Frame(padre, style="Tarjeta.TFrame")
        f.pack(fill=X, pady=(4 if grande else 2, 0))
        ttk.Label(
            f,
            text=texto,
            style="Tarjeta.TLabel",
            font=(tema.FUENTE, 13 if grande else 10, "bold" if grande else "normal"),
        ).pack(side=LEFT)
        lbl = ttk.Label(
            f,
            text="$ 0",
            style="Tarjeta.TLabel",
            foreground=tema.VERDE if grande else tema.TEXTO,
            font=(tema.FUENTE_TITULO if grande else tema.FUENTE, 18 if grande else 10, "bold" if grande else "normal"),
        )
        lbl.pack(side=RIGHT)
        return lbl

    # ==================================================================
    # CATÁLOGO EN MEMORIA, ESCÁNER DE BARRAS Y AUTOCOMPLETADO
    # ==================================================================
    def buscar(self):
        """Recarga el catálogo activo en memoria para búsqueda instantánea y autocompletado."""
        filas = pl.listar_productos(solo_activos=True)
        self._catalogo_cache = filas
        self.productos = {str(p["id_producto"]): p for p in filas}
        self._codigos_exactos = {str(p["codigo"]).strip().lower(): p for p in filas}

    def _leer_cantidad_agregar(self) -> int:
        try:
            cant = pl._numero(self.sp_cant_agregar.get() or 1, "Cantidad", entero=True, minimo=1)
            return int(cant)
        except ErrorValidacion as e:
            cmp.mostrar_error(self, e)
            self.sp_cant_agregar.set("1")
            return 0

    def _al_teclear_codigo(self, evento=None):
        if evento and evento.keysym in ("Up", "Down", "Return", "Escape", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return

        if self._timer_auto_scan is not None:
            try:
                self.after_cancel(self._timer_auto_scan)
            except Exception:
                pass
            self._timer_auto_scan = None

        ahora = time.perf_counter()
        delta_ms = (ahora - self._ultimo_key_ts) * 1000.0
        self._ultimo_key_ts = ahora
        if delta_ms < 55:
            self._rafaga_scanner += 1
        else:
            self._rafaga_scanner = 0

        texto = self.e_buscar.get().strip()
        if not texto:
            self._ocultar_sugerencias()
            return

        t_low = texto.lower()
        match_exacto = self._codigos_exactos.get(t_low)

        # Verificar cuántos códigos comienzan con este texto (para saber si es un código único completo)
        codigos_prefijo = [
            p for p in self._catalogo_cache if str(p["codigo"]).strip().lower().startswith(t_low)
        ]

        # Si coincide exactamente con un código de barras y (vino de ráfaga de lector O es código único sin más prefijos):
        if match_exacto and (self._rafaga_scanner >= 2 or len(codigos_prefijo) == 1):
            espera = 90 if self._rafaga_scanner >= 2 else 180
            self._timer_auto_scan = self.after(
                espera,
                lambda p=match_exacto, txt=texto: self._auto_agregar_si_coincide(p, txt),
            )
            return

        # Mostrar autocompletado por código parcial o por nombre del producto
        coincidencias = [
            p
            for p in self._catalogo_cache
            if t_low in str(p["codigo"]).lower() or t_low in str(p["nombre"]).lower()
        ][:8]
        self._mostrar_sugerencias(coincidencias)

    def _auto_agregar_si_coincide(self, prod: dict, texto_esperado: str):
        self._timer_auto_scan = None
        if not self.winfo_exists():
            return
        if self.e_buscar.get().strip() != texto_esperado:
            return
        cant = self._leer_cantidad_agregar()
        if cant > 0:
            self._agregar_producto(prod, cantidad=cant)
            self.sp_cant_agregar.set("1")
            self.e_buscar.delete(0, END)
            self._ocultar_sugerencias()
            self.e_buscar.focus_set()

    def _mostrar_sugerencias(self, lista: list[dict]):
        self._sugerencias_actuales = lista
        self.lb_sugerencias.delete(0, END)
        if not lista:
            self._ocultar_sugerencias()
            return

        for p in lista:
            linea = f"  {p['codigo']}   —   {p['nombre']}   ·   {tema.moneda(p['precio'])}   (Stock: {p['stock']})"
            self.lb_sugerencias.insert(END, linea)

        self.lb_sugerencias.configure(height=min(len(lista), 6))
        self.lb_sugerencias.selection_set(0)
        if not self.marco_sugerencias.winfo_ismapped():
            self.marco_sugerencias.pack(fill=X, pady=(6, 0))

    def _ocultar_sugerencias(self):
        self._sugerencias_actuales = []
        if self.marco_sugerencias.winfo_ismapped():
            self.marco_sugerencias.pack_forget()

    def _mover_sugerencia_abajo(self, _e=None):
        if not self._sugerencias_actuales:
            return "break"
        sel = self.lb_sugerencias.curselection()
        idx = (sel[0] + 1) if sel else 0
        idx = min(idx, len(self._sugerencias_actuales) - 1)
        self.lb_sugerencias.selection_clear(0, END)
        self.lb_sugerencias.selection_set(idx)
        self.lb_sugerencias.see(idx)
        return "break"

    def _mover_sugerencia_arriba(self, _e=None):
        if not self._sugerencias_actuales:
            return "break"
        sel = self.lb_sugerencias.curselection()
        idx = (sel[0] - 1) if sel else 0
        idx = max(idx, 0)
        self.lb_sugerencias.selection_clear(0, END)
        self.lb_sugerencias.selection_set(idx)
        self.lb_sugerencias.see(idx)
        return "break"

    def _clic_sugerencia(self, _e=None):
        if not self._sugerencias_actuales:
            return
        sel = self.lb_sugerencias.curselection()
        idx = sel[0] if sel else 0
        if 0 <= idx < len(self._sugerencias_actuales):
            prod = self._sugerencias_actuales[idx]
            cant = self._leer_cantidad_agregar()
            if cant > 0:
                self._agregar_producto(prod, cantidad=cant)
                self.sp_cant_agregar.set("1")
                self.e_buscar.delete(0, END)
                self._ocultar_sugerencias()
                self.e_buscar.focus_set()

    def _enter_buscar(self, _e=None):
        self._confirmar_busqueda_o_sugerencia()
        return "break"

    def _confirmar_busqueda_o_sugerencia(self):
        if self._timer_auto_scan is not None:
            try:
                self.after_cancel(self._timer_auto_scan)
            except Exception:
                pass
            self._timer_auto_scan = None

        texto = self.e_buscar.get().strip()
        if not texto:
            return

        # 1. Buscar coincidencia exacta por código de barras
        prod = self._codigos_exactos.get(texto.lower()) or pl.buscar_por_codigo(texto)

        # 2. Si no es código exacto, tomar la sugerencia seleccionada en el autocompletado
        if not prod and self._sugerencias_actuales:
            sel = self.lb_sugerencias.curselection()
            idx = sel[0] if sel else 0
            if 0 <= idx < len(self._sugerencias_actuales):
                prod = self._sugerencias_actuales[idx]

        if not prod:
            cmp.mostrar_error(self, f"No se encontró ningún producto activo con el código o nombre «{texto}».")
            return

        cant = self._leer_cantidad_agregar()
        if cant <= 0:
            return
        self._agregar_producto(prod, cantidad=cant)
        self.sp_cant_agregar.set("1")
        self.e_buscar.delete(0, END)
        self._ocultar_sugerencias()
        self.e_buscar.focus_set()

    def agregar(self, codigo_o_id=None):
        """Método compatible para agregar el producto actual del buscador o por ID/código."""
        if codigo_o_id is not None:
            prod = self.productos.get(str(codigo_o_id)) or self._codigos_exactos.get(str(codigo_o_id).lower())
            if prod:
                cant = self._leer_cantidad_agregar()
                if cant > 0:
                    self._agregar_producto(prod, cantidad=cant)
                    self.sp_cant_agregar.set("1")
                return
        self._confirmar_busqueda_o_sugerencia()

    def _agregar_producto(self, p, cantidad: int = 1):
        pid = p["id_producto"]
        prod_fresco = self.productos.get(str(pid), p)
        stock_disp = prod_fresco["stock"]
        actual = self.carrito.get(pid, {"cantidad": 0})["cantidad"]
        if actual + cantidad > stock_disp:
            cmp.mostrar_error(
                self,
                f"Stock insuficiente de «{p['nombre']}». Disponible: {stock_disp} (en factura: {actual}).",
            )
            return
        iva = p.get("iva_porcentaje")
        if iva is None:
            iva = prod_fresco.get("iva_porcentaje", 0)
        self.carrito[pid] = {
            "id_producto": pid,
            "codigo": p.get("codigo") or prod_fresco.get("codigo", ""),
            "nombre": p["nombre"],
            "precio": p["precio"],
            "stock": stock_disp,
            "iva_porcentaje": iva,
            "cantidad": actual + cantidad,
        }
        self._guardar_estado_borrador()
        self.refrescar_carrito(seleccionar=pid)

    # ==================================================================
    # CONTROL DEL CARRITO Y CANTIDADES
    # ==================================================================
    def _sel_car(self):
        s = self.tv_car.selection()
        if s:
            return int(s[0])
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
        self._guardar_estado_borrador()
        self.refrescar_carrito(pid if pid in self.carrito else None)

    def fijar_cantidad_carrito(self):
        pid = self._sel_car()
        if pid is None or pid not in self.carrito:
            cmp.mostrar_error(self, "Selecciona un producto de la factura para cambiar su cantidad.")
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
        self._guardar_estado_borrador()
        self.refrescar_carrito(pid if pid in self.carrito else None)
        self.e_buscar.focus_set()

    def quitar(self):
        pid = self._sel_car()
        if pid is not None:
            self.carrito.pop(pid, None)
            self._guardar_estado_borrador()
            self.refrescar_carrito()
            self.e_buscar.focus_set()

    def vaciar(self):
        self.carrito.clear()
        self.e_recibido.delete(0, END)
        self.e_cliente.delete(0, END)
        self._guardar_estado_borrador()
        self.refrescar_carrito()
        self.e_buscar.focus_set()

    def refrescar_carrito(self, seleccionar=None):
        cmp.llenar_tabla(
            self.tv_car,
            [
                (
                    pid,
                    (
                        i.get("codigo", ""),
                        i["nombre"],
                        tema.moneda(i["precio"]),
                        f"{i.get('iva_porcentaje', 0):.0f}%",
                        i["cantidad"],
                        tema.moneda(i["precio"] * i["cantidad"]),
                    ),
                )
                for pid, i in self.carrito.items()
            ],
        )
        hijos = self.tv_car.get_children()
        if seleccionar is not None and str(seleccionar) in hijos:
            self.tv_car.selection_set(str(seleccionar))
        elif hijos and not self.tv_car.selection():
            self.tv_car.selection_set(hijos[-1])
        self._sincronizar_entry_cantidad()

        total_lineas = len(self.carrito)
        total_unidades = sum(i["cantidad"] for i in self.carrito.values())
        self.lbl_resumen_items.configure(text=f"{total_lineas} producto(s) ({total_unidades} unidades)")

        sub, iva, total = fl.calcular_totales(list(self.carrito.values()))
        self.total = total
        self.lbl_sub.configure(text=tema.moneda(sub))
        self.lbl_iva.configure(text=tema.moneda(iva))
        self.lbl_total.configure(text=tema.moneda(total))
        self._actualizar_cambio()

    def _actualizar_cambio(self):
        if self.cb_pago.get() != "Efectivo":
            self.lbl_cambio.configure(text="Pago exacto sin efectivo")
            return
        try:
            recibido = pl._numero(self.e_recibido.get() or 0, "Recibido")
        except ErrorValidacion:
            recibido = 0
        self.lbl_cambio.configure(text=f"Cambio: {tema.moneda(max(recibido - getattr(self, 'total', 0), 0))}")

    def cobrar(self):
        if not self.carrito:
            cmp.mostrar_error(self, "Escanea o agrega al menos un producto a la factura.")
            self.e_buscar.focus_set()
            return
        try:
            recibido = pl._numero(self.e_recibido.get() or 0, "Recibido") if self.cb_pago.get() == "Efectivo" else 0
            id_factura = fl.emitir_factura(
                [{"id_producto": i["id_producto"], "cantidad": i["cantidad"]} for i in self.carrito.values()],
                self.cb_pago.get(),
                recibido,
                cliente_nombre=self.e_cliente.get(),
            )
            factura = fl.obtener_factura(id_factura)
        except ErrorValidacion as e:
            cmp.mostrar_error(self, e)
            self.buscar()
            return
        self.carrito.clear()
        self.e_recibido.delete(0, END)
        self.e_cliente.delete(0, END)
        self._guardar_estado_borrador()
        self.refrescar_carrito()
        self.buscar()
        VentanaFactura(self, factura)
        self.e_buscar.focus_set()

    def destroy(self):
        self._guardar_estado_borrador()
        super().destroy()
