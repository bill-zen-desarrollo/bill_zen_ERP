"""Inventario operativo: KPIs de bodega, Kardex cronológico y registro de movimientos de stock."""
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import productos_logic as pl
from logica.seguridad import ErrorValidacion, Sesion
from ui import componentes as cmp
from ui import tema


class Vista(ttk.Frame):
    FILTROS_TIPO = ("Todos", "Entradas", "Mermas/Ajustes", "Ventas")
    TAMANO_PAGINA = 100

    OPCIONES_MOVIMIENTO = (
        ("Entrada por compra", "ENTRADA"),
        ("Ajuste conteo físico", "AJUSTE_CONTEO"),
        ("Salida por merma/daño", "SALIDA_MERMA"),
        ("Devolución", "DEVOLUCION"),
    )

    def __init__(self, padre, principal):
        super().__init__(padre)
        self.principal = principal
        self.es_admin = Sesion.es_admin()
        self.productos_activos = []
        self.productos_por_id = {}
        self.productos_por_etiqueta = {}
        self.producto_seleccionado_id = None
        self.filas_kardex = {}
        self.pagina_actual = 0
        self.total_registros = 0
        self._timer_sku_form = None

        # ── Encabezado ──────────────────────────────────────────────────────
        cab = ttk.Frame(self)
        cab.pack(fill=X, pady=(0, 8))
        subtitulo = (
            "Kardex operativo de movimientos, valorización y control de bodega"
            if self.es_admin
            else "Consulta de existencias y movimientos de Kardex (solo lectura)"
        )
        cmp.encabezado(self, "Inventario · Kardex", subtitulo).pack(in_=cab, side=LEFT, anchor=W)

        # ── Fila superior de KPIs (3 tarjetas resumen) ──────────────────────
        fila_kpi = ttk.Frame(self)
        fila_kpi.pack(fill=X, pady=(0, 10))
        for i in range(3):
            fila_kpi.columnconfigure(i, weight=1, uniform="kpi_inv")

        self.kpi_unidades = cmp.tarjeta_kpi(
            fila_kpi,
            "Total unidades en bodega",
            valor="0",
            detalle="en 0 productos activos",
            acento=tema.VERDE,
        )
        self.kpi_unidades.grid(row=0, column=0, sticky=NSEW, padx=(0, 8))

        self.kpi_valorizacion = cmp.tarjeta_kpi(
            fila_kpi,
            "Valorización del inventario ($)",
            valor="$ 0",
            detalle="Costo proveedor × existencias",
            acento=tema.DORADO,
        )
        self.kpi_valorizacion.grid(row=0, column=1, sticky=NSEW, padx=4)

        self.kpi_alertas = cmp.tarjeta_kpi(
            fila_kpi,
            "Alertas de stock bajo",
            valor="0",
            detalle="Sin productos en alerta",
            acento=tema.VERDE_CLARO,
        )
        self.kpi_alertas.grid(row=0, column=2, sticky=NSEW, padx=(8, 0))
        self._barra_alerta_kpi = self.kpi_alertas.winfo_children()[0].winfo_children()[0]

        # ── Cuerpo principal (Izquierda: Tarjeta Kardex | Derecha: Form) ────
        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill=BOTH, expand=YES)

        card_izq = cmp.tarjeta(cuerpo, padding=20)
        card_izq.pack(side=LEFT, fill=BOTH, expand=YES, padx=(0, 14 if self.es_admin else 0))
        izq = card_izq.interior

        # Barra de filtros sobre tarjeta blanca
        barra = ttk.Frame(izq, style="Tarjeta.TFrame")
        barra.pack(fill=X, pady=(0, 10))

        ttk.Label(barra, text="Buscar:", style="FormLabel.TLabel").pack(side=LEFT, padx=(0, 8))
        self.e_buscar = ttk.Entry(barra, font=(tema.FUENTE, 11))
        self.e_buscar.pack(side=LEFT, fill=X, expand=YES)
        cmp.vincular_busqueda(self, self.e_buscar, self._al_cambiar_filtro, espera=250)

        self.cb_filtro_tipo = ttk.Combobox(
            barra,
            values=list(self.FILTROS_TIPO),
            state="readonly",
            width=18,
            font=(tema.FUENTE, 11),
        )
        self.cb_filtro_tipo.set("Todos")
        self.cb_filtro_tipo.pack(side=LEFT, padx=(8, 0))
        self.cb_filtro_tipo.bind("<<ComboboxSelected>>", lambda _e: self._al_cambiar_filtro())

        self.var_bajo = ttk.BooleanVar(value=False)
        self.btn_stock_bajo = ttk.Button(
            barra,
            text="Solo stock bajo",
            style="Suave.TButton",
            command=self._alternar_stock_bajo,
            padding=(12, 8),
        )
        self.btn_stock_bajo.pack(side=LEFT, padx=(8, 0))

        # Tabla Kardex
        cols = [
            ("fecha", "Fecha y Hora", 145, W),
            ("codigo", "SKU", 80, W),
            ("nombre", "Producto", 160, W),
            ("tipo", "Tipo", 110, W),
            ("cant", "Cant.", 64, E),
            ("transicion", "Stock Ant. -> Nuevo", 135, CENTER),
            ("usuario", "Usuario", 90, W),
            ("motivo", "Motivo", 150, W),
        ]
        marco_tabla, self.tv = cmp.tabla(izq, cols, altura=12)
        scroll_x = ttk.Scrollbar(marco_tabla, orient=HORIZONTAL, command=self.tv.xview)
        self.tv.configure(xscrollcommand=scroll_x.set)
        scroll_x.pack(side=BOTTOM, fill=X)
        self.tv.tag_configure("entrada", foreground=tema.VERDE)
        self.tv.tag_configure("venta", foreground=tema.VERDE_OSCURO)
        marco_tabla.pack(fill=BOTH, expand=YES)
        self.tv.bind("<<TreeviewSelect>>", self._al_seleccionar_fila_kardex)

        # Barra inferior de paginación (máx. 100 registros por página)
        barra_pag = ttk.Frame(izq, style="Tarjeta.TFrame")
        barra_pag.pack(fill=X, pady=(10, 0))
        self.lbl_paginacion = ttk.Label(
            barra_pag,
            text="Mostrando 0 de 0 registros · Página 1 de 1",
            style="Tarjeta.TLabel",
            foreground=tema.GRIS,
            font=(tema.FUENTE, 10),
        )
        self.lbl_paginacion.pack(side=LEFT)

        controles_pag = ttk.Frame(barra_pag, style="Tarjeta.TFrame")
        controles_pag.pack(side=RIGHT)
        self.btn_ant_pag = ttk.Button(
            controles_pag,
            text="← Anterior",
            style="Suave.TButton",
            command=self.pagina_anterior,
            padding=(12, 6),
        )
        self.btn_ant_pag.pack(side=LEFT, padx=(0, 6))
        self.btn_sig_pag = ttk.Button(
            controles_pag,
            text="Siguiente →",
            style="Suave.TButton",
            command=self.pagina_siguiente,
            padding=(12, 6),
        )
        self.btn_sig_pag.pack(side=LEFT)

        # Panel derecho: Formulario "Registrar Movimiento"
        if self.es_admin:
            der = ttk.Frame(cuerpo, width=360)
            der.pack(side=LEFT, fill=Y)
            der.pack_propagate(False)

            borde = cmp.tarjeta(der, padding=(18, 12))
            borde.pack(fill=BOTH, expand=YES)
            c = borde.interior

            ttk.Label(c, text="Registrar Movimiento", style="TarjetaTitulo.TLabel").pack(anchor=W, pady=(0, 4))

            # Búsqueda / escaneo rápido por SKU o nombre (con debounce 250ms)
            ttk.Label(
                c,
                text="Escanear o buscar SKU / nombre",
                style="FormLabel.TLabel",
            ).pack(anchor=W, pady=(2, 2))
            self.e_sku_prod = ttk.Entry(c, font=(tema.FUENTE, 11))
            self.e_sku_prod.pack(fill=X, pady=(0, 4))
            self.e_sku_prod.bind("<KeyRelease>", self._al_buscar_producto_form)
            self.e_sku_prod.bind("<Return>", self._confirmar_sku_form)

            ttk.Label(
                c,
                text="Producto *",
                style="FormLabel.TLabel",
            ).pack(anchor=W, pady=(2, 2))
            self.cb_producto = ttk.Combobox(c, state="readonly", font=(tema.FUENTE, 11))
            self.cb_producto.pack(fill=X, pady=(0, 4))
            self.cb_producto.bind("<<ComboboxSelected>>", self._al_elegir_combo_producto)

            # Caja de stock actual en tiempo real
            self.marco_stock_info = tk.Frame(
                c,
                bg=tema.BEIGE,
                highlightthickness=1,
                highlightbackground=tema.BEIGE_OSCURO,
                padx=10,
                pady=4,
            )
            self.marco_stock_info.pack(fill=X, pady=(0, 4))
            self.lbl_prod = tk.Label(
                self.marco_stock_info,
                text="Selecciona o escanea un producto",
                bg=tema.BEIGE,
                fg=tema.GRIS,
                font=(tema.FUENTE, 10, "bold"),
                anchor="w",
                justify="left",
                wraplength=300,
            )
            self.lbl_prod.pack(fill=X)
            self.lbl_stock_actual = tk.Label(
                self.marco_stock_info,
                text="Stock actual: —",
                bg=tema.BEIGE,
                fg=tema.VERDE_OSCURO,
                font=(tema.FUENTE, 10),
                anchor="w",
            )
            self.lbl_stock_actual.pack(fill=X)

            # Tipo de movimiento
            ttk.Label(
                c,
                text="Tipo de movimiento *",
                style="FormLabel.TLabel",
            ).pack(anchor=W, pady=(2, 2))
            self.mapa_tipos_ui = {etiqueta: codigo for etiqueta, codigo in self.OPCIONES_MOVIMIENTO}
            self.mapa_tipos_ui["Ajuste de inventario (conteo físico)"] = "AJUSTE_CONTEO"
            self.cb_tipo_mov = ttk.Combobox(
                c,
                values=[etiqueta for etiqueta, _ in self.OPCIONES_MOVIMIENTO],
                state="readonly",
                font=(tema.FUENTE, 11),
            )
            self.cb_tipo_mov.set(self.OPCIONES_MOVIMIENTO[0][0])
            self.cb_tipo_mov.pack(fill=X, pady=(0, 4))
            self.cb_tipo_mov.bind("<<ComboboxSelected>>", lambda _e: self._actualizar_etiquetas_movimiento())

            # Cantidad / Conteo físico
            self.lbl_cant_titulo = ttk.Label(
                c,
                text="Cantidad *",
                style="FormLabel.TLabel",
            )
            self.lbl_cant_titulo.pack(anchor=W, pady=(2, 2))
            self.e_cant = ttk.Entry(c, font=(tema.FUENTE, 11))
            self.e_cant.pack(fill=X, pady=(0, 2))
            self.e_cant.bind("<KeyRelease>", lambda _e: self._actualizar_preview_movimiento())
            self.e_cant.bind("<Return>", lambda _e: self.registrar_movimiento())

            self.lbl_preview = ttk.Label(
                c,
                text="",
                style="Tarjeta.TLabel",
                foreground=tema.VERDE_CLARO,
                font=(tema.FUENTE, 9, "bold"),
                wraplength=310,
            )
            self.lbl_preview.pack(anchor=W, pady=(0, 2))

            # Motivo / Observación
            self.lbl_motivo_titulo = ttk.Label(
                c,
                text="Motivo / Observación (opcional)",
                style="FormLabel.TLabel",
            )
            self.lbl_motivo_titulo.pack(anchor=W, pady=(2, 2))
            self.e_motivo = ttk.Entry(c, font=(tema.FUENTE, 11))
            self.e_motivo.pack(fill=X, pady=(0, 8))
            self.e_motivo.bind("<Return>", lambda _e: self.registrar_movimiento())

            # Botones de acción
            btn_frame = ttk.Frame(c, style="Tarjeta.TFrame")
            btn_frame.pack(fill=X, pady=(2, 0))
            self.btn_registrar = ttk.Button(
                btn_frame,
                text="Registrar movimiento",
                style="Zen.TButton",
                command=self.registrar_movimiento,
                padding=(12, 8),
            )
            self.btn_registrar.pack(side=LEFT, fill=X, expand=YES, padx=(0, 6))
            self.btn_limpiar = ttk.Button(
                btn_frame,
                text="Limpiar",
                style="Suave.TButton",
                command=self.limpiar_formulario,
                padding=(12, 8),
            )
            self.btn_limpiar.pack(side=LEFT)

        self.refrescar()

    # ------------------------------------------------------------------
    # CARGA DE DATOS, KPIS, PAGINACIÓN Y TABLA KARDEX
    # ------------------------------------------------------------------
    def _cargar_catalogo_selector(self):
        self.productos_activos = pl.listar_productos(solo_activos=True)
        self.productos_por_id = {int(p["id_producto"]): p for p in self.productos_activos}
        if not self.es_admin:
            return
        etiquetas = []
        self.productos_por_etiqueta = {}
        for p in self.productos_activos:
            etq = f"{p['codigo']} — {p['nombre']}"
            self.productos_por_etiqueta[etq] = p
            etiquetas.append(etq)
        self.cb_producto.configure(values=etiquetas)
        if self.producto_seleccionado_id and self.producto_seleccionado_id in self.productos_por_id:
            self._seleccionar_producto_por_id(self.producto_seleccionado_id)

    def refrescar_kpis(self):
        k = pl.resumen_kpis_inventario()
        self.kpi_unidades.valor.configure(text=f"{k['total_unidades']:,}".replace(",", "."))
        self.kpi_unidades.detalle.configure(text=f"en {k['total_productos']} producto(s) activos")
        self.kpi_valorizacion.valor.configure(text=tema.moneda(k["valorizacion"]))

        alertas = k["alertas_stock_bajo"]
        self.kpi_alertas.valor.configure(text=str(alertas))
        if alertas > 0:
            self.kpi_alertas.configure(bg=tema.ROJO)
            self._barra_alerta_kpi.configure(bg=tema.ROJO)
            self.kpi_alertas.valor.configure(foreground=tema.ROJO)
            self.kpi_alertas.detalle.configure(
                text=f"{alertas} producto(s) por reabastecer",
                foreground=tema.ROJO,
            )
        else:
            self.kpi_alertas.configure(bg=tema.BEIGE_OSCURO)
            self._barra_alerta_kpi.configure(bg=tema.VERDE_CLARO)
            self.kpi_alertas.valor.configure(foreground=tema.VERDE)
            self.kpi_alertas.detalle.configure(
                text="Niveles de stock saludables",
                foreground=tema.GRIS,
            )

    def _al_cambiar_filtro(self):
        self.pagina_actual = 0
        self.refrescar_kardex()

    def pagina_anterior(self):
        if self.pagina_actual > 0:
            self.pagina_actual -= 1
            self.refrescar_kardex()

    def pagina_siguiente(self):
        total_pags = max(1, (self.total_registros + self.TAMANO_PAGINA - 1) // self.TAMANO_PAGINA)
        if self.pagina_actual + 1 < total_pags:
            self.pagina_actual += 1
            self.refrescar_kardex()

    def refrescar_kardex(self):
        texto = self.e_buscar.get().strip()
        filtro_tipo = self.cb_filtro_tipo.get()
        solo_bajo = self.var_bajo.get()

        self.total_registros = pl.contar_movimientos_kardex(
            texto=texto,
            filtro_tipo=filtro_tipo,
            solo_stock_bajo=solo_bajo,
        )
        total_pags = max(1, (self.total_registros + self.TAMANO_PAGINA - 1) // self.TAMANO_PAGINA)
        if self.pagina_actual >= total_pags:
            self.pagina_actual = total_pags - 1
        offset = self.pagina_actual * self.TAMANO_PAGINA

        filas = pl.listar_movimientos_kardex(
            texto=texto,
            filtro_tipo=filtro_tipo,
            solo_stock_bajo=solo_bajo,
            limite=self.TAMANO_PAGINA,
            offset=offset,
        )
        self.filas_kardex = {str(m["id"]): m for m in filas}

        datos_tv = []
        for m in filas:
            var = int(m["variacion"])
            if m["movement_type"] == "STOCK_BAJO":
                cant_txt = str(m["stock_actual"])
                trans_txt = f"{m['stock_actual']} (Mín: {m['stock_minimo']})"
            else:
                cant_txt = f"+{var}" if var > 0 else str(var)
                trans_txt = f"{m['previous_stock']} -> {m['new_stock']}"
            datos_tv.append(
                (
                    m["id"],
                    (
                        m["created_at"] or "",
                        m["codigo"],
                        m["nombre"],
                        m["etiqueta_tipo"],
                        cant_txt,
                        trans_txt,
                        m["username"] or "—",
                        m["reason"] or "—",
                    ),
                )
            )

        def _tags(iid, _vals):
            mov = self.filas_kardex.get(str(iid))
            if not mov:
                return ()
            if mov["movement_type"] in ("SALIDA_MERMA", "STOCK_BAJO"):
                return ("alerta",)
            if mov["movement_type"] == "AJUSTE_CONTEO":
                return ("alerta",) if mov["variacion"] < 0 else ("entrada",)
            if mov["movement_type"] in ("ENTRADA", "DEVOLUCION"):
                return ("entrada",)
            if mov["movement_type"] == "VENTA":
                return ("venta",)
            return ()

        cmp.llenar_tabla(self.tv, datos_tv, _tags)

        mostrados = len(filas)
        inicio_r = (offset + 1) if mostrados > 0 else 0
        fin_r = offset + mostrados
        total_vis = max(self.total_registros, fin_r)
        self.lbl_paginacion.configure(
            text=f"Mostrando {inicio_r}–{fin_r} de {total_vis} · Página {self.pagina_actual + 1} de {total_pags}"
        )
        self.btn_ant_pag.configure(state=NORMAL if self.pagina_actual > 0 else DISABLED)
        self.btn_sig_pag.configure(state=NORMAL if (self.pagina_actual + 1) < total_pags else DISABLED)

    def refrescar(self):
        self._cargar_catalogo_selector()
        self.refrescar_kpis()
        self.refrescar_kardex()

    def _alternar_stock_bajo(self):
        nuevo = not self.var_bajo.get()
        self.var_bajo.set(nuevo)
        self.btn_stock_bajo.configure(style="Peligro.TButton" if nuevo else "Suave.TButton")
        self._al_cambiar_filtro()

    # ------------------------------------------------------------------
    # FORMULARIO DE REGISTRO DE MOVIMIENTOS
    # ------------------------------------------------------------------
    def _al_seleccionar_fila_kardex(self, _e=None):
        if not self.es_admin:
            return
        s = self.tv.selection()
        if not s:
            return
        mov = self.filas_kardex.get(s[0])
        if mov and mov["product_id"] in self.productos_por_id:
            self._seleccionar_producto_por_id(mov["product_id"])

    def _seleccionar_producto_por_id(self, id_producto: int):
        p = self.productos_por_id.get(int(id_producto))
        if not p:
            return
        self.producto_seleccionado_id = int(p["id_producto"])
        etq = f"{p['codigo']} — {p['nombre']}"
        self.cb_producto.set(etq)
        bajo = p["stock"] <= p["stock_minimo"]
        self.lbl_prod.configure(text=f"[{p['codigo']}] {p['nombre']}", fg=tema.VERDE_OSCURO)
        self.lbl_stock_actual.configure(
            text=f"Stock actual: {p['stock']} ud(s)  ·  Mínimo: {p['stock_minimo']}" + ("  (STOCK BAJO)" if bajo else ""),
            fg=tema.ROJO if bajo else tema.VERDE,
        )
        self._actualizar_preview_movimiento()

    def _al_elegir_combo_producto(self, _e=None):
        etq = self.cb_producto.get()
        p = self.productos_por_etiqueta.get(etq)
        if p:
            self._seleccionar_producto_por_id(p["id_producto"])

    def _al_buscar_producto_form(self, evento=None):
        if evento and evento.keysym in ("Return", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return
        if self._timer_sku_form is not None:
            try:
                self.after_cancel(self._timer_sku_form)
            except Exception:
                pass
        self._timer_sku_form = self.after(250, self._filtrar_producto_form)

    def _filtrar_producto_form(self):
        self._timer_sku_form = None
        if not self.winfo_exists():
            return
        txt = self.e_sku_prod.get().strip().lower()
        if not txt:
            self.cb_producto.configure(values=list(self.productos_por_etiqueta.keys()))
            return
        exacto = next((p for p in self.productos_activos if p["codigo"].strip().lower() == txt), None)
        coincidencias = [
            f"{p['codigo']} — {p['nombre']}"
            for p in self.productos_activos
            if txt in p["codigo"].lower() or txt in p["nombre"].lower()
        ]
        self.cb_producto.configure(values=coincidencias)
        if exacto:
            self._seleccionar_producto_por_id(exacto["id_producto"])
        elif len(coincidencias) == 1:
            p = self.productos_por_etiqueta.get(coincidencias[0])
            if p:
                self._seleccionar_producto_por_id(p["id_producto"])

    def _confirmar_sku_form(self, _e=None):
        if self._timer_sku_form is not None:
            try:
                self.after_cancel(self._timer_sku_form)
            except Exception:
                pass
            self._timer_sku_form = None
        txt = self.e_sku_prod.get().strip().lower()
        if not txt:
            return
        exacto = next((p for p in self.productos_activos if p["codigo"].strip().lower() == txt), None)
        if not exacto:
            exacto = next(
                (p for p in self.productos_activos if txt in p["codigo"].lower() or txt in p["nombre"].lower()),
                None,
            )
        if exacto:
            self._seleccionar_producto_por_id(exacto["id_producto"])
            self.e_cant.focus_set()
        else:
            cmp.mostrar_error(self, f"No se encontró ningún producto activo con SKU o nombre «{self.e_sku_prod.get().strip()}».")

    def _tipo_actual_codigo(self) -> str:
        return self.mapa_tipos_ui.get(self.cb_tipo_mov.get(), "ENTRADA")

    def _actualizar_etiquetas_movimiento(self):
        tipo = self._tipo_actual_codigo()
        if tipo == "AJUSTE_CONTEO":
            self.lbl_cant_titulo.configure(text="Conteo físico real *")
        else:
            self.lbl_cant_titulo.configure(text="Cantidad *")

        if tipo in ("SALIDA_MERMA", "AJUSTE_CONTEO"):
            self.lbl_motivo_titulo.configure(text="Motivo / Observación * (obligatorio)")
        else:
            self.lbl_motivo_titulo.configure(text="Motivo / Observación (opcional)")
        self._actualizar_preview_movimiento()

    def _actualizar_preview_movimiento(self):
        if not self.es_admin:
            return
        if not self.producto_seleccionado_id or self.producto_seleccionado_id not in self.productos_por_id:
            self.lbl_preview.configure(text="", foreground=tema.GRIS)
            return

        p = self.productos_por_id[self.producto_seleccionado_id]
        stock_act = int(p["stock"])
        raw = self.e_cant.get().strip()
        if not raw:
            self.lbl_preview.configure(text="", foreground=tema.GRIS)
            return

        tipo = self._tipo_actual_codigo()
        try:
            minimo = 0 if tipo == "AJUSTE_CONTEO" else 1
            val = int(pl._numero(raw, "Cantidad", entero=True, minimo=minimo))
        except ErrorValidacion:
            self.lbl_preview.configure(text="Ingresa un número entero válido", foreground=tema.ROJO)
            return

        if tipo in ("ENTRADA", "DEVOLUCION"):
            nuevo = stock_act + val
            self.lbl_preview.configure(
                text=f"Efecto: +{val} ud(s)  |  Stock: {stock_act} → {nuevo}",
                foreground=tema.VERDE_CLARO,
            )
        elif tipo == "SALIDA_MERMA":
            if val > stock_act:
                self.lbl_preview.configure(
                    text=f"Alerta: supera el stock disponible ({stock_act})",
                    foreground=tema.ROJO,
                )
            else:
                nuevo = stock_act - val
                self.lbl_preview.configure(
                    text=f"Efecto: -{val} ud(s)  |  Stock: {stock_act} → {nuevo}",
                    foreground=tema.ROJO,
                )
        elif tipo == "AJUSTE_CONTEO":
            diff = val - stock_act
            if diff == 0:
                self.lbl_preview.configure(
                    text=f"Sin diferencia respecto al stock actual ({stock_act})",
                    foreground=tema.GRIS,
                )
            else:
                signo = "+" if diff > 0 else ""
                color = tema.VERDE_CLARO if diff > 0 else tema.ROJO
                self.lbl_preview.configure(
                    text=f"Diferencia: {signo}{diff} ud(s)  |  Stock: {stock_act} → {val}",
                    foreground=color,
                )

    def registrar_movimiento(self):
        if not self.es_admin:
            return
        if not self.producto_seleccionado_id:
            return cmp.mostrar_error(self, "Selecciona o escanea un producto primero.")

        tipo = self._tipo_actual_codigo()
        try:
            res = pl.registrar_movimiento_inventario(
                id_producto=self.producto_seleccionado_id,
                tipo_movimiento=tipo,
                cantidad=self.e_cant.get(),
                motivo=self.e_motivo.get(),
            )
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)

        diff = res["diferencia"]
        signo = "+" if diff > 0 else ""
        cmp.toast(
            self,
            f"Movimiento registrado ({signo}{diff}). Stock actualizado: {res['previous_stock']} → {res['new_stock']}",
        )
        self.e_cant.delete(0, END)
        self.e_motivo.delete(0, END)
        self.pagina_actual = 0
        self.refrescar()
        self._seleccionar_producto_por_id(res["product_id"])
        if self.principal and hasattr(self.principal, "disparar_sync_ahora"):
            self.principal.disparar_sync_ahora()
        self.e_cant.focus_set()

    def limpiar_formulario(self):
        if not self.es_admin:
            return
        self.producto_seleccionado_id = None
        self.e_sku_prod.delete(0, END)
        self.cb_producto.configure(values=list(self.productos_por_etiqueta.keys()))
        self.cb_producto.set("")
        self.cb_tipo_mov.set(self.OPCIONES_MOVIMIENTO[0][0])
        self.e_cant.delete(0, END)
        self.e_motivo.delete(0, END)
        self.lbl_prod.configure(text="Selecciona o escanea un producto", fg=tema.GRIS)
        self.lbl_stock_actual.configure(text="Stock actual: —", fg=tema.VERDE_OSCURO)
        self.lbl_preview.configure(text="", foreground=tema.GRIS)
        self._actualizar_etiquetas_movimiento()
        self.tv.selection_remove(self.tv.selection())
        self.e_sku_prod.focus_set()
