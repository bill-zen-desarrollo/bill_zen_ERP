"""Centro Contable y Financiero: Egresos, Cuentas por Pagar, Estado de Resultados (P&G),
Punto de Equilibrio, Arqueo de Flujo de Caja (Efectivo vs Bancos) y Liquidación de IVA DIAN."""
import calendar
import os
import tkinter as tk
from datetime import date
from tkinter import filedialog

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import reportes_logic as rl
from logica.seguridad import ErrorValidacion
from ui import componentes as cmp
from ui import tema


def _fin_mes_actual() -> str:
    hoy = date.today()
    ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]
    return date(hoy.year, hoy.month, ultimo_dia).isoformat()


class Vista(ttk.Frame):
    TODAS_CATS = "Todas las categorías"
    TODOS_ESTADOS = "Todos los estados"

    def __init__(self, padre, principal):
        super().__init__(padre)

        # ================== CABECERA Y FILTRO DE PERIODO ==================
        cab = ttk.Frame(self)
        cab.pack(fill=X, pady=(0, 10))
        cmp.encabezado(
            cab,
            "Contabilidad y Finanzas",
            "Control de egresos, cuentas por pagar, estado de resultados (P&G), flujo de caja e IVA DIAN",
        ).pack(side=LEFT)

        barra_fechas = ttk.Frame(cab)
        barra_fechas.pack(side=RIGHT, pady=(6, 0))
        ttk.Label(barra_fechas, text="Desde:", style="Fondo.TLabel", font=(tema.FUENTE, 9, "bold")).pack(side=LEFT)
        self.e_desde = ttk.Entry(barra_fechas, width=11)
        self.e_desde.insert(0, date.today().replace(day=1).isoformat())
        self.e_desde.pack(side=LEFT, padx=(4, 8))

        ttk.Label(barra_fechas, text="Hasta:", style="Fondo.TLabel", font=(tema.FUENTE, 9, "bold")).pack(side=LEFT)
        self.e_hasta = ttk.Entry(barra_fechas, width=11)
        self.e_hasta.insert(0, _fin_mes_actual())
        self.e_hasta.pack(side=LEFT, padx=(4, 8))

        ttk.Button(barra_fechas, text="Hoy", style="Suave.TButton", command=self._rango_hoy, padding=(8, 5)).pack(side=LEFT, padx=2)
        ttk.Button(barra_fechas, text="Mes", style="Suave.TButton", command=self._rango_mes, padding=(8, 5)).pack(side=LEFT, padx=2)
        ttk.Button(barra_fechas, text="Actualizar", style="Zen.TButton", command=self.refrescar, padding=(10, 5)).pack(side=LEFT, padx=(6, 4))
        ttk.Button(barra_fechas, text="Exportar CSV", style="Oro.TButton", command=self.exportar_contabilidad, padding=(10, 5)).pack(side=LEFT)

        # ================== FILA DE 5 TARJETAS KPI FINANCIERAS ==================
        self.fila_kpi = ttk.Frame(self)
        self.fila_kpi.pack(fill=X, pady=(0, 10))
        self.kpis = {}
        defs_kpi = [
            ("ventas_netas", "Ventas Netas (Sin IVA)", tema.VERDE),
            ("utilidad_bruta", "Utilidad Bruta", tema.VERDE_CLARO),
            ("gastos_totales", "Gastos Operativos", tema.DORADO),
            ("cuentas_por_pagar", "Cuentas por Pagar", tema.ROJO),
            ("utilidad_neta", "Utilidad Neta Real", tema.VERDE_OSCURO),
        ]
        for idx, (clave, titulo, color) in enumerate(defs_kpi):
            self.fila_kpi.columnconfigure(idx, weight=1, uniform="kpi_cont")
            w = cmp.tarjeta_kpi(self.fila_kpi, titulo, acento=color)
            w.grid(row=0, column=idx, sticky=NSEW, padx=(0 if idx == 0 else 8, 0))
            self.kpis[clave] = w

        # ================== BANNER DINÁMICO DE RECORDATORIO DE CUENTAS FIJAS ==================
        self.marco_alerta_fijos = tk.Frame(self, bg="#FDF0ED", highlightthickness=1, highlightbackground=tema.ROJO)
        self.lbl_alerta_fijos = tk.Label(
            self.marco_alerta_fijos,
            text="",
            bg="#FDF0ED",
            fg=tema.ROJO,
            font=(tema.FUENTE, 9, "bold"),
            anchor="w",
            justify="left",
        )
        self.lbl_alerta_fijos.pack(side=LEFT, padx=12, pady=6, fill=X, expand=YES)
        ttk.Button(
            self.marco_alerta_fijos,
            text="Ir a Cuentas Fijas",
            style="Peligro.TButton",
            command=lambda: self.notebook.select(self.tab_fijos),
            padding=(10, 3),
        ).pack(side=RIGHT, padx=10, pady=4)

        # ================== PESTAÑAS CONTABLES (4 MÓDULOS) ==================
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=BOTH, expand=YES)

        self.tab_egresos = ttk.Frame(self.notebook, padding=10)
        self.tab_fijos = ttk.Frame(self.notebook, padding=10)
        self.tab_flujo = ttk.Frame(self.notebook, padding=10)
        self.tab_impuestos = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.tab_egresos, text="  Egresos y Cuentas por Pagar  ")
        self.notebook.add(self.tab_fijos, text="  Cuentas Fijas Mensuales (Recordatorios)  ")
        self.notebook.add(self.tab_flujo, text="  Estado de Resultados (P&G) y Flujo de Caja  ")
        self.notebook.add(self.tab_impuestos, text="  Liquidación IVA (DIAN) y Gastos por Rubro  ")

        self._construir_tab_egresos()
        self._construir_tab_fijos()
        self._construir_tab_flujo()
        self._construir_tab_impuestos()

        self.refrescar()

    # ------------------------------------------------------------------
    # PESTAÑA 1: REGISTRO DE EGRESOS, SERVICIOS Y CUENTAS POR PAGAR
    # ------------------------------------------------------------------
    def _construir_tab_egresos(self):
        izq = ttk.Frame(self.tab_egresos)
        izq.pack(side=LEFT, fill=BOTH, expand=YES, padx=(0, 14))

        # Barra de filtros de egresos
        barra_f = ttk.Frame(izq)
        barra_f.pack(fill=X, pady=(0, 8))
        self.e_buscar_gasto = ttk.Entry(barra_f)
        self.e_buscar_gasto.pack(side=LEFT, fill=X, expand=YES)
        cmp.vincular_busqueda(self, self.e_buscar_gasto, self.refrescar_tabla_gastos)

        self.cb_filtro_cat = ttk.Combobox(
            barra_f,
            values=[self.TODAS_CATS] + list(rl.CATEGORIAS_GASTO_UI),
            state="readonly",
            width=26,
        )
        self.cb_filtro_cat.set(self.TODAS_CATS)
        self.cb_filtro_cat.pack(side=LEFT, padx=(8, 0))
        self.cb_filtro_cat.bind("<<ComboboxSelected>>", lambda e: self.refrescar_tabla_gastos())

        self.cb_filtro_est = ttk.Combobox(
            barra_f,
            values=[self.TODOS_ESTADOS, "PAGADO", "PENDIENTE"],
            state="readonly",
            width=16,
        )
        self.cb_filtro_est.set(self.TODOS_ESTADOS)
        self.cb_filtro_est.pack(side=LEFT, padx=(8, 0))
        self.cb_filtro_est.bind("<<ComboboxSelected>>", lambda e: self.refrescar_tabla_gastos())

        cols_gastos = [
            ("fecha", "Fecha", 90, W),
            ("concepto", "Concepto / Servicio", 185, W),
            ("proveedor", "Proveedor / Entidad", 140, W),
            ("categoria", "Categoría", 150, W),
            ("metodo_pago", "Medio Pago", 105, W),
            ("comprobante", "Soporte", 80, W),
            ("estado", "Estado", 85, W),
            ("valor", "Valor", 95, E),
        ]
        marco_tv, self.tv_gastos = cmp.tabla(izq, cols_gastos, altura=13)
        marco_tv.pack(fill=BOTH, expand=YES)

        acciones_inf = ttk.Frame(izq)
        acciones_inf.pack(fill=X, pady=(8, 0))
        ttk.Label(
            acciones_inf,
            text="Nota: Las filas resaltadas en rojo están PENDIENTES por pagar.",
            style="Subtitulo.TLabel",
        ).pack(side=LEFT)
        ttk.Button(
            acciones_inf,
            text="Eliminar seleccionado",
            style="Peligro.TButton",
            command=self.eliminar,
        ).pack(side=RIGHT)
        ttk.Button(
            acciones_inf,
            text="Marcar seleccionado como Pagado",
            style="Oro.TButton",
            command=self.marcar_pagado,
        ).pack(side=RIGHT, padx=(0, 8))

        # Formulario derecho para registrar egreso o cuenta por pagar
        borde = cmp.tarjeta(self.tab_egresos, padding=16)
        borde.pack(side=LEFT, fill=Y)
        c = borde.interior
        ttk.Label(c, text="Registrar Egreso o Recibo", style="TarjetaTitulo.TLabel").pack(anchor=W, pady=(0, 4))

        fila_f1 = ttk.Frame(c, style="Tarjeta.TFrame")
        fila_f1.pack(fill=X)
        fila_f1.columnconfigure((0, 1), weight=1)
        self.e_fecha = cmp.campo(fila_f1, "Fecha (AAAA-MM-DD) *", 0, 0, 14)
        self.e_fecha.insert(0, date.today().isoformat())
        self.e_comprobante = cmp.campo(fila_f1, "N° Recibo / Factura", 0, 1, 14)

        self.e_concepto = cmp.campo(c, "Concepto (ej. Recibo de Luz / Internet / Arriendo) *", ancho=34)
        self.e_proveedor = cmp.campo(c, "Proveedor o Beneficiario (ej. Enel / Acueducto)", ancho=34)

        ttk.Label(c, text="Categoría del egreso *", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(anchor=W, pady=(6, 2))
        self.cb_cat = ttk.Combobox(c, values=rl.CATEGORIAS_GASTO_UI, state="readonly", width=34)
        self.cb_cat.set(rl.CATEGORIAS_GASTO_UI[0])
        self.cb_cat.pack(fill=X, pady=(0, 6))

        fila_f2 = ttk.Frame(c, style="Tarjeta.TFrame")
        fila_f2.pack(fill=X, pady=(4, 4))
        fila_f2.columnconfigure((0, 1), weight=1)

        m_met = ttk.Frame(fila_f2, style="Tarjeta.TFrame")
        m_met.grid(row=0, column=0, sticky=EW, padx=(0, 4))
        ttk.Label(m_met, text="Medio de pago *", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(anchor=W)
        self.cb_metodo = ttk.Combobox(m_met, values=rl.METODOS_PAGO_GASTO, state="readonly", width=15)
        self.cb_metodo.set("Efectivo")
        self.cb_metodo.pack(fill=X, pady=(2, 0))

        m_est = ttk.Frame(fila_f2, style="Tarjeta.TFrame")
        m_est.grid(row=0, column=1, sticky=EW, padx=(4, 0))
        ttk.Label(m_est, text="Estado del pago *", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(anchor=W)
        self.cb_estado = ttk.Combobox(m_est, values=rl.ESTADOS_GASTO, state="readonly", width=15)
        self.cb_estado.set("PAGADO")
        self.cb_estado.pack(fill=X, pady=(2, 0))

        self.e_valor = cmp.campo(c, "Valor total ($) *", ancho=34)
        self.var_es_fijo = ttk.BooleanVar(value=False)
        ttk.Checkbutton(
            c,
            text="Es cuenta fija mensual (recordar cada mes)",
            variable=self.var_es_fijo,
        ).pack(anchor=W, pady=(2, 6))
        ttk.Button(c, text="Guardar egreso", style="Zen.TButton", command=self.guardar).pack(fill=X, pady=(4, 0))

    # ------------------------------------------------------------------
    # PESTAÑA 2: ESTADO DE RESULTADOS (P&G), PUNTO DE EQUILIBRIO Y CAJA
    # ------------------------------------------------------------------
    def _construir_tab_flujo(self):
        self.tab_flujo.columnconfigure(0, weight=2, uniform="flujo")
        self.tab_flujo.columnconfigure(1, weight=3, uniform="flujo")
        self.tab_flujo.rowconfigure(0, weight=1)

        card_pyg = cmp.tarjeta(self.tab_flujo, padding=18)
        card_pyg.grid(row=0, column=0, sticky=NSEW, padx=(0, 12))
        self.marco_pyg = card_pyg.interior

        card_arq = cmp.tarjeta(self.tab_flujo, padding=18)
        card_arq.grid(row=0, column=1, sticky=NSEW)
        arq = card_arq.interior
        ttk.Label(arq, text="Arqueo de Tesorería: Efectivo en Cajón vs Bancos", style="TarjetaTitulo.TLabel").pack(anchor=W)
        ttk.Label(
            arq,
            text="Cruza todas las facturas emitidas contra los gastos pagados según su medio de pago para cuadrar el cajón y las cuentas bancarias.",
            style="Tarjeta.TLabel",
            foreground=tema.GRIS,
            wraplength=520,
            font=(tema.FUENTE, 9),
        ).pack(anchor=W, pady=(2, 10))

        self.marco_resumen_caja = ttk.Frame(arq, style="Tarjeta.TFrame")
        self.marco_resumen_caja.pack(fill=X, pady=(0, 10))

        cols_flujo = [
            ("metodo_pago", "Medio de Pago", 160, W),
            ("ingresos", "(+) Ingresos Ventas", 130, E),
            ("egresos", "(−) Gastos Pagados", 130, E),
            ("saldo", "(=) Saldo Neto Disponible", 145, E),
        ]
        m_tv_f, self.tv_flujo = cmp.tabla(arq, cols_flujo, altura=7)
        m_tv_f.pack(fill=BOTH, expand=YES)

    # ------------------------------------------------------------------
    # PESTAÑA 3: LIQUIDACIÓN DE IVA (DIAN) Y GASTOS POR CATEGORÍA
    # ------------------------------------------------------------------
    def _construir_tab_impuestos(self):
        self.tab_impuestos.columnconfigure(0, weight=1, uniform="imp")
        self.tab_impuestos.columnconfigure(1, weight=1, uniform="imp")
        self.tab_impuestos.rowconfigure(0, weight=1)

        card_iva = cmp.tarjeta(self.tab_impuestos, padding=18)
        card_iva.grid(row=0, column=0, sticky=NSEW, padx=(0, 12))
        c_iva = card_iva.interior
        ttk.Label(c_iva, text="Liquidación de IVA Generado en Ventas (DIAN)", style="TarjetaTitulo.TLabel").pack(anchor=W)
        ttk.Label(
            c_iva,
            text="Desglose de bases gravables e impuesto IVA recaudado por tarifa (0%, 5%, 19%) sobre las facturas emitidas en el periodo.",
            style="Tarjeta.TLabel",
            foreground=tema.GRIS,
            wraplength=460,
            font=(tema.FUENTE, 9),
        ).pack(anchor=W, pady=(2, 10))

        cols_iva = [
            ("tarifa", "Tarifa IVA", 85, W),
            ("unidades", "Unidades", 80, E),
            ("base", "Base Gravable", 120, E),
            ("iva", "IVA Recaudado (DIAN)", 135, E),
            ("total", "Total Facturado", 125, E),
        ]
        m_iva, self.tv_iva = cmp.tabla(c_iva, cols_iva, altura=9)
        m_iva.pack(fill=BOTH, expand=YES)
        self.lbl_tot_iva = ttk.Label(
            c_iva,
            text="Total IVA recaudado para la DIAN: $ 0",
            style="Tarjeta.TLabel",
            foreground=tema.VERDE_OSCURO,
            font=(tema.FUENTE, 10, "bold"),
        )
        self.lbl_tot_iva.pack(anchor=E, pady=(8, 0))

        card_rubros = cmp.tarjeta(self.tab_impuestos, padding=18)
        card_rubros.grid(row=0, column=1, sticky=NSEW)
        c_rub = card_rubros.interior
        ttk.Label(c_rub, text="Distribución de Gastos por Rubro / Categoría", style="TarjetaTitulo.TLabel").pack(anchor=W)
        ttk.Label(
            c_rub,
            text="Identifica qué porcentaje de tus egresos se va en servicios públicos, arriendo, nómina, proveedores, etc.",
            style="Tarjeta.TLabel",
            foreground=tema.GRIS,
            wraplength=460,
            font=(tema.FUENTE, 9),
        ).pack(anchor=W, pady=(2, 10))

        cols_rub = [
            ("cat", "Categoría / Rubro", 200, W),
            ("n", "Recibos", 65, E),
            ("pagado", "Pagado", 105, E),
            ("pend", "Pendiente", 105, E),
            ("total", "Total", 105, E),
            ("pct", "% Peso", 70, E),
        ]
        m_rub, self.tv_rubros = cmp.tabla(c_rub, cols_rub, altura=10)
        m_rub.pack(fill=BOTH, expand=YES)

    # ------------------------------------------------------------------
    # PESTAÑA 4: CUENTAS FIJAS MENSUALES Y ALERTAS DE VENCIMIENTO
    # ------------------------------------------------------------------
    def _construir_tab_fijos(self):
        self.id_fijo_editando = None
        izq = ttk.Frame(self.tab_fijos)
        izq.pack(side=LEFT, fill=BOTH, expand=YES, padx=(0, 14))

        ttk.Label(
            izq,
            text="Calendario de Gastos Fijos Mensuales (Arriendo, Servicios, Internet, Nómina, etc.)",
            style="TarjetaTitulo.TLabel",
            background=tema.BEIGE,
        ).pack(anchor=W, pady=(0, 6))

        cols_fijos = [
            ("dia", "Día Pago", 75, CENTER),
            ("concepto", "Cuenta Fija", 165, W),
            ("descripcion", "Descripción / Nota", 180, W),
            ("proveedor", "Proveedor / Entidad", 130, W),
            ("categoria", "Categoría", 145, W),
            ("valor", "Valor Mensual", 100, E),
            ("estado_mes", "Estado Este Mes", 175, W),
        ]
        m_tv_fijos, self.tv_fijos = cmp.tabla(izq, cols_fijos, altura=12)
        m_tv_fijos.pack(fill=BOTH, expand=YES)
        self.tv_fijos.bind("<<TreeviewSelect>>", lambda e: self.cargar_fijo_seleccionado())

        barra_pago_fijo = ttk.Frame(izq)
        barra_pago_fijo.pack(fill=X, pady=(8, 0))
        ttk.Label(barra_pago_fijo, text="Valor real a pagar hoy ($):", style="Fondo.TLabel", font=(tema.FUENTE, 9, "bold")).pack(side=LEFT)
        self.e_valor_pago_fijo = ttk.Entry(barra_pago_fijo, width=14)
        self.e_valor_pago_fijo.pack(side=LEFT, padx=(6, 10))
        ttk.Button(
            barra_pago_fijo,
            text="Registrar pago de este mes",
            style="Oro.TButton",
            command=self.pagar_fijo_mes,
        ).pack(side=LEFT)
        ttk.Button(
            barra_pago_fijo,
            text="Eliminar cuenta fija",
            style="Peligro.TButton",
            command=self.eliminar_fijo,
        ).pack(side=RIGHT)

        # Formulario derecho para crear / editar cuenta fija mensual
        borde = cmp.tarjeta(self.tab_fijos, padding=16)
        borde.pack(side=LEFT, fill=Y)
        c = borde.interior
        self.lbl_modo_fijo = ttk.Label(c, text="Nueva Cuenta Fija Mensual", style="TarjetaTitulo.TLabel")
        self.lbl_modo_fijo.pack(anchor=W, pady=(0, 4))

        self.e_fijo_concepto = cmp.campo(c, "Nombre de la cuenta fija (ej. Arriendo Local / Luz) *", ancho=34)
        self.e_fijo_desc = cmp.campo(c, "Descripción adicional (ej. Contrato #102 / Medidor)", ancho=34)
        self.e_fijo_prov = cmp.campo(c, "Proveedor / Entidad (ej. Enel / Movistar)", ancho=34)

        ttk.Label(c, text="Categoría *", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(anchor=W, pady=(4, 2))
        self.cb_fijo_cat = ttk.Combobox(c, values=rl.CATEGORIAS_GASTO_UI, state="readonly", width=34)
        self.cb_fijo_cat.set(rl.CATEGORIAS_GASTO_UI[0])
        self.cb_fijo_cat.pack(fill=X, pady=(0, 6))

        fila_dias = ttk.Frame(c, style="Tarjeta.TFrame")
        fila_dias.pack(fill=X, pady=(4, 6))
        fila_dias.columnconfigure((0, 1), weight=1)

        m_dia = ttk.Frame(fila_dias, style="Tarjeta.TFrame")
        m_dia.grid(row=0, column=0, sticky=EW, padx=(0, 4))
        ttk.Label(m_dia, text="Día de pago (1-31) *", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(anchor=W)
        self.sp_fijo_dia = ttk.Spinbox(m_dia, from_=1, to=31, width=10)
        self.sp_fijo_dia.set("5")
        self.sp_fijo_dia.pack(fill=X, pady=(2, 0))

        m_aviso = ttk.Frame(fila_dias, style="Tarjeta.TFrame")
        m_aviso.grid(row=0, column=1, sticky=EW, padx=(4, 0))
        ttk.Label(m_aviso, text="Avisar antes (días) *", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(anchor=W)
        self.sp_fijo_aviso = ttk.Spinbox(m_aviso, from_=1, to=15, width=10)
        self.sp_fijo_aviso.set("5")
        self.sp_fijo_aviso.pack(fill=X, pady=(2, 0))

        ttk.Label(c, text="Medio de pago habitual", style="Tarjeta.TLabel", font=(tema.FUENTE, 9, "bold")).pack(anchor=W, pady=(4, 2))
        self.cb_fijo_metodo = ttk.Combobox(c, values=rl.METODOS_PAGO_GASTO, state="readonly", width=34)
        self.cb_fijo_metodo.set("Transferencia")
        self.cb_fijo_metodo.pack(fill=X, pady=(0, 4))

        self.e_fijo_valor = cmp.campo(c, "Valor mensual estimado ($) *", ancho=34)

        btns_fijo = ttk.Frame(c, style="Tarjeta.TFrame")
        btns_fijo.pack(fill=X, pady=(8, 0))
        self.btn_guardar_fijo = ttk.Button(btns_fijo, text="Guardar cuenta fija", style="Zen.TButton", command=self.guardar_fijo)
        self.btn_guardar_fijo.pack(side=LEFT, fill=X, expand=YES, padx=(0, 4))
        ttk.Button(btns_fijo, text="Limpiar", style="Suave.TButton", command=self.limpiar_fijo).pack(side=LEFT, padx=(4, 0))

    # ------------------------------------------------------------------
    # ACCIONES Y REFRESCO DE DATOS
    # ------------------------------------------------------------------
    def _rango_hoy(self):
        hoy = date.today().isoformat()
        self.e_desde.delete(0, END)
        self.e_desde.insert(0, hoy)
        self.e_hasta.delete(0, END)
        self.e_hasta.insert(0, hoy)
        self.refrescar()

    def _rango_mes(self):
        hoy = date.today()
        self.e_desde.delete(0, END)
        self.e_desde.insert(0, hoy.replace(day=1).isoformat())
        self.e_hasta.delete(0, END)
        self.e_hasta.insert(0, _fin_mes_actual())
        self.refrescar()

    def _kpi(self, clave, valor, detalle):
        self.kpis[clave].valor.configure(text=valor)
        self.kpis[clave].detalle.configure(text=detalle)

    def refrescar(self):
        d, h = self.e_desde.get().strip(), self.e_hasta.get().strip()
        r = rl.estado_resultados(d, h)
        flujo = rl.flujo_caja_y_bancos(d, h)
        ivas = rl.resumen_iva_dian(d, h)
        self._ultimo_resultado = r

        # 1. Actualizar las 5 tarjetas KPI superiores
        self._kpi(
            "ventas_netas",
            tema.moneda(r["ventas_netas"]),
            f"Bruto: {tema.moneda(r['ventas_brutas'])} ({r['facturas']} facturas)",
        )
        self._kpi(
            "utilidad_bruta",
            tema.moneda(r["utilidad_bruta"]),
            f"Margen bruto: {r['margen_bruto_pct']:.1f}% · Costo: {tema.moneda(r['costo_ventas'])}",
        )
        self._kpi(
            "gastos_totales",
            tema.moneda(r["gastos"]),
            f"Pagados: {tema.moneda(r['gastos_pagados'])}",
        )
        self._kpi(
            "cuentas_por_pagar",
            tema.moneda(r["gastos_pendientes"]),
            f"{r['conteo_pendientes']} recibos pendientes de pago",
        )
        self._kpi(
            "utilidad_neta",
            tema.moneda(r["utilidad_neta"]),
            f"Rentabilidad neta: {r['margen_neto_pct']:.1f}% · Equilibrio: {min(r['cobertura_equilibrio_pct'], 999):.0f}%",
        )

        # 2. Actualizar tabla de egresos (Pestaña 1) y cuentas fijas (Pestaña 4)
        self.refrescar_tabla_gastos()
        self.refrescar_gastos_fijos()

        # 3. Actualizar Estado de Resultados y Punto de Equilibrio (Pestaña 2)
        for w in self.marco_pyg.winfo_children():
            w.destroy()
        ttk.Label(
            self.marco_pyg,
            text="Estado de Resultados (P&G)",
            style="TarjetaTitulo.TLabel",
        ).grid(row=0, column=0, sticky=W, columnspan=2, pady=(0, 8))

        lineas_pyg = [
            ("(+) Ventas brutas facturadas", r["ventas_brutas"], False, tema.TEXTO),
            ("(−) IVA generado (DIAN)", r["iva"], False, tema.GRIS),
            ("(=) Ventas netas (sin IVA)", r["ventas_netas"], True, tema.VERDE_OSCURO),
            ("(−) Costo de mercancía vendida (CMV)", r["costo_ventas"], False, tema.TEXTO),
            ("(=) UTILIDAD BRUTA", r["utilidad_bruta"], True, tema.VERDE),
            ("(−) Gastos operativos pagados", r["gastos_pagados"], False, tema.TEXTO),
            ("(−) Cuentas por pagar causadas", r["gastos_pendientes"], False, tema.ROJO if r["gastos_pendientes"] > 0 else tema.TEXTO),
            ("(=) UTILIDAD NETA DEL PERIODO", r["utilidad_neta"], True, tema.VERDE if r["utilidad_neta"] >= 0 else tema.ROJO),
            ("Punto de equilibrio (meta ventas)", r["punto_equilibrio"], True, tema.DORADO),
        ]
        for idx, (texto, val, negrita, color) in enumerate(lineas_pyg, start=1):
            ttk.Label(
                self.marco_pyg,
                text=texto,
                style="Tarjeta.TLabel",
                font=(tema.FUENTE, 10, "bold" if negrita else "normal"),
            ).grid(row=idx, column=0, sticky=W, pady=3)
            ttk.Label(
                self.marco_pyg,
                text=tema.moneda(val),
                style="Tarjeta.TLabel",
                foreground=color,
                font=(tema.FUENTE, 10, "bold" if negrita else "normal"),
            ).grid(row=idx, column=1, sticky=E, padx=(24, 0), pady=3)
        self.marco_pyg.columnconfigure(0, weight=1)

        estado_eq = (
            "Meta de punto de equilibrio superada (estás en zona de ganancias)."
            if r["utilidad_neta"] >= 0 and r["ventas_netas"] >= r["punto_equilibrio"]
            else f"Faltan {tema.moneda(max(r['punto_equilibrio'] - r['ventas_netas'], 0))} en ventas netas para cubrir todos los gastos del periodo."
        )
        ttk.Label(
            self.marco_pyg,
            text=estado_eq,
            style="Tarjeta.TLabel",
            foreground=tema.VERDE_CLARO if r["utilidad_neta"] >= 0 else tema.ROJO,
            wraplength=340,
            font=(tema.FUENTE, 9, "bold"),
        ).grid(row=len(lineas_pyg) + 1, column=0, columnspan=2, sticky=W, pady=(12, 0))

        # 4. Actualizar Arqueo de Caja y Bancos (Pestaña 2 derecha)
        for w in self.marco_resumen_caja.winfo_children():
            w.destroy()
        for col_i, (tit, val, col_acento) in enumerate((
            ("Efectivo Neto en Cajón", flujo["saldo_efectivo"], tema.VERDE),
            ("Saldo Neto en Bancos / Digital", flujo["saldo_bancos"], tema.DORADO),
            ("Total Tesorería Disponible", flujo["saldo_total_tesoreria"], tema.VERDE_OSCURO),
        )):
            self.marco_resumen_caja.columnconfigure(col_i, weight=1, uniform="caja")
            box = ttk.Frame(self.marco_resumen_caja, style="Tarjeta.TFrame")
            box.grid(row=0, column=col_i, sticky=EW, padx=(0 if col_i == 0 else 8, 0))
            ttk.Label(box, text=tit, style="KPITexto.TLabel", font=(tema.FUENTE, 8, "bold")).pack(anchor=W)
            ttk.Label(
                box,
                text=tema.moneda(val),
                style="Tarjeta.TLabel",
                foreground=col_acento if val >= 0 else tema.ROJO,
                font=(tema.FUENTE_TITULO, 14, "bold"),
            ).pack(anchor=W)

        cmp.llenar_tabla(
            self.tv_flujo,
            [
                (
                    i,
                    (
                        m["metodo_pago"],
                        tema.moneda(m["ingresos"]),
                        tema.moneda(m["egresos"]),
                        tema.moneda(m["saldo_neto"]),
                    ),
                )
                for i, m in enumerate(flujo["desglose_por_metodo"])
            ],
            lambda _i, vals: ("alerta",) if "-" in str(vals[3]) else (),
        )

        # 5. Actualizar Liquidación de IVA y Rubros (Pestaña 3)
        cmp.llenar_tabla(
            self.tv_iva,
            [
                (
                    i,
                    (
                        fila["tarifa"],
                        fila["unidades"],
                        tema.moneda(fila["base_gravable"]),
                        tema.moneda(fila["iva_generado"]),
                        tema.moneda(fila["total_facturado"]),
                    ),
                )
                for i, fila in enumerate(ivas)
            ],
        )
        self.lbl_tot_iva.configure(text=f"Total IVA recaudado para la DIAN: {tema.moneda(r['iva'])}")

        cmp.llenar_tabla(
            self.tv_rubros,
            [
                (
                    i,
                    (
                        cat["categoria"],
                        cat["cantidad"],
                        tema.moneda(cat["pagado"]),
                        tema.moneda(cat["pendiente"]),
                        tema.moneda(cat["total"]),
                        f"{cat['porcentaje']:.1f}%",
                    ),
                )
                for i, cat in enumerate(r["gastos_por_categoria"])
            ],
            lambda _i, vals: ("alerta",) if vals[3] != "$ 0" else (),
        )

    def refrescar_tabla_gastos(self):
        d, h = self.e_desde.get().strip(), self.e_hasta.get().strip()
        cat = self.cb_filtro_cat.get() if hasattr(self, "cb_filtro_cat") else None
        est = self.cb_filtro_est.get() if hasattr(self, "cb_filtro_est") else None
        if est == self.TODOS_ESTADOS:
            est = None
        texto = self.e_buscar_gasto.get().strip() if hasattr(self, "e_buscar_gasto") else ""

        gastos = rl.listar_gastos(d, h, categoria=cat, estado=est, texto=texto)
        self.gastos_actuales = {str(g["id_gasto"]): g for g in gastos}
        cmp.llenar_tabla(
            self.tv_gastos,
            [
                (
                    g["id_gasto"],
                    (
                        g["fecha"],
                        g["concepto"],
                        g.get("proveedor") or "—",
                        g["categoria"],
                        g.get("metodo_pago") or "Efectivo",
                        g.get("comprobante") or "—",
                        g.get("estado") or "PAGADO",
                        tema.moneda(g["valor"]),
                    ),
                )
                for g in gastos
            ],
            lambda _iid, vals: ("alerta",) if vals[6] == "PENDIENTE" else (),
        )

    def guardar(self):
        try:
            rl.registrar_gasto(
                fecha=self.e_fecha.get().strip(),
                concepto=self.e_concepto.get(),
                categoria=self.cb_cat.get(),
                valor=self.e_valor.get(),
                proveedor=self.e_proveedor.get(),
                metodo_pago=self.cb_metodo.get(),
                comprobante=self.e_comprobante.get(),
                estado=self.cb_estado.get(),
                es_gasto_fijo=bool(self.var_es_fijo.get()),
            )
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)

        cmp.toast(self, "Egreso registrado correctamente")
        for e in (self.e_concepto, self.e_proveedor, self.e_comprobante, self.e_valor):
            e.delete(0, END)
        self.cb_estado.set("PAGADO")
        self.var_es_fijo.set(False)
        self.refrescar()

    def marcar_pagado(self):
        s = self.tv_gastos.selection()
        if not s:
            return cmp.mostrar_error(self, "Selecciona primero una cuenta por pagar de la tabla.")
        g = self.gastos_actuales.get(s[0], {})
        if g.get("estado") == "PAGADO":
            return cmp.mostrar_info(self, "Este egreso ya se encuentra marcado como PAGADO.")
        medio = self.cb_metodo.get() or "Efectivo"
        if not cmp.confirmar(
            self,
            f"¿Marcar «{g.get('concepto')}» ({tema.moneda(g.get('valor'))}) como PAGADO con {medio}?",
        ):
            return
        try:
            rl.marcar_gasto_pagado(int(s[0]), metodo_pago=medio)
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)
        cmp.toast(self, "Cuenta marcada como PAGADA")
        self.refrescar()

    def eliminar(self):
        s = self.tv_gastos.selection()
        if not s:
            return cmp.mostrar_error(self, "Selecciona un egreso de la tabla para eliminarlo.")
        if cmp.confirmar(self, "¿Eliminar el egreso seleccionado?"):
            rl.eliminar_gasto(int(s[0]))
            self.refrescar()

    def exportar_contabilidad(self):
        d, h = self.e_desde.get().strip(), self.e_hasta.get().strip()
        gastos = rl.listar_gastos(d, h)
        carpeta = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.isdir(carpeta):
            carpeta = os.path.expanduser("~")
        ruta = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            initialdir=carpeta,
            defaultextension=".csv",
            initialfile=f"contabilidad_egresos_{d}_a_{h}.csv",
            filetypes=[("Archivo CSV compatible con Excel", "*.csv")],
            title="Exportar reporte contable de egresos",
        )
        if not ruta:
            return
        columnas = [
            ("fecha", "Fecha"),
            ("concepto", "Concepto"),
            ("proveedor", "Proveedor / Entidad"),
            ("categoria", "Categoría"),
            ("metodo_pago", "Medio de Pago"),
            ("comprobante", "N° Comprobante"),
            ("estado", "Estado"),
            ("valor", "Valor"),
            ("username", "Registrado por"),
        ]
        rl.exportar_csv(ruta, gastos, columnas)
        cmp.toast(self, "Reporte contable exportado a CSV")

    # ------------------------------------------------------------------
    # MÉTODOS DE CUENTAS FIJAS MENSUALES Y RECORDATORIOS
    # ------------------------------------------------------------------
    def refrescar_gastos_fijos(self):
        fijos = rl.listar_gastos_fijos()
        self.fijos_actuales = {str(f["id_gasto_fijo"]): f for f in fijos}
        cmp.llenar_tabla(
            self.tv_fijos,
            [
                (
                    f["id_gasto_fijo"],
                    (
                        f"Día {f['dia_pago']}",
                        f["concepto"],
                        f.get("descripcion") or "—",
                        f.get("proveedor") or "—",
                        f["categoria"],
                        tema.moneda(f["valor_estimado"]),
                        f["etiqueta_estado"],
                    ),
                )
                for f in fijos
            ],
            lambda iid, _vals: ("alerta",)
            if self.fijos_actuales[str(iid)]["estado_mes"] in ("VENCIDO", "PROXIMO")
            else (),
        )

        info_alerta = rl.alertas_gastos_fijos()
        if info_alerta["hay_alertas"]:
            nombres = ", ".join(
                f"{x['concepto']} ({x['etiqueta_estado']})" for x in info_alerta["items"][:3]
            )
            extra = f" (+{len(info_alerta['items']) - 3} más)" if len(info_alerta["items"]) > 3 else ""
            self.lbl_alerta_fijos.configure(
                text=(
                    f"Recordatorio de Cuentas Fijas: Tienes {info_alerta['cantidad_alertas']} pago(s) próximo(s) o vencido(s) "
                    f"por {tema.moneda(info_alerta['total_estimado_alerta'])}: {nombres}{extra}"
                )
            )
            self.marco_alerta_fijos.pack(fill=X, pady=(0, 8), before=self.notebook)
        else:
            self.marco_alerta_fijos.pack_forget()

    def cargar_fijo_seleccionado(self):
        s = self.tv_fijos.selection()
        if not s:
            return
        f = self.fijos_actuales.get(s[0])
        if not f:
            return
        self.id_fijo_editando = f["id_gasto_fijo"]
        self.lbl_modo_fijo.configure(text=f"Editando: {f['concepto']}")
        self.btn_guardar_fijo.configure(text="Actualizar cuenta fija")

        for entry, val in (
            (self.e_fijo_concepto, f["concepto"]),
            (self.e_fijo_desc, f.get("descripcion") or ""),
            (self.e_fijo_prov, f.get("proveedor") or ""),
            (self.e_fijo_valor, f"{f['valor_estimado']:.0f}"),
            (self.e_valor_pago_fijo, f"{f['valor_estimado']:.0f}"),
        ):
            entry.delete(0, END)
            entry.insert(0, str(val))

        self.cb_fijo_cat.set(f["categoria"])
        self.sp_fijo_dia.set(str(f["dia_pago"]))
        self.sp_fijo_aviso.set(str(f.get("dias_anticipacion") or 5))
        self.cb_fijo_metodo.set(f.get("metodo_pago") or "Transferencia")

    def limpiar_fijo(self):
        self.id_fijo_editando = None
        self.lbl_modo_fijo.configure(text="Nueva Cuenta Fija Mensual")
        self.btn_guardar_fijo.configure(text="Guardar cuenta fija")
        for entry in (self.e_fijo_concepto, self.e_fijo_desc, self.e_fijo_prov, self.e_fijo_valor, self.e_valor_pago_fijo):
            entry.delete(0, END)
        self.sp_fijo_dia.set("5")
        self.sp_fijo_aviso.set("5")
        self.cb_fijo_metodo.set("Transferencia")
        self.tv_fijos.selection_remove(self.tv_fijos.selection())

    def guardar_fijo(self):
        try:
            rl.guardar_gasto_fijo(
                concepto=self.e_fijo_concepto.get(),
                categoria=self.cb_fijo_cat.get(),
                valor_estimado=self.e_fijo_valor.get(),
                dia_pago=self.sp_fijo_dia.get(),
                descripcion=self.e_fijo_desc.get(),
                proveedor=self.e_fijo_prov.get(),
                metodo_pago=self.cb_fijo_metodo.get(),
                dias_anticipacion=self.sp_fijo_aviso.get(),
                id_gasto_fijo=self.id_fijo_editando,
            )
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)

        cmp.toast(self, "Cuenta fija mensual guardada")
        self.limpiar_fijo()
        self.refrescar()

    def pagar_fijo_mes(self):
        s = self.tv_fijos.selection()
        if not s:
            return cmp.mostrar_error(self, "Selecciona primero una cuenta fija de la lista.")
        f = self.fijos_actuales.get(s[0], {})
        valor_real = self.e_valor_pago_fijo.get().strip() or f.get("valor_estimado")
        if not cmp.confirmar(
            self,
            f"¿Registrar el pago de este mes para «{f.get('concepto')}» por {tema.moneda(rl._numero(valor_real, 'Valor'))}?",
        ):
            return
        try:
            rl.pagar_gasto_fijo_mes(
                int(s[0]),
                valor_pagado=valor_real,
                metodo_pago=self.cb_fijo_metodo.get(),
            )
        except ErrorValidacion as e:
            return cmp.mostrar_error(self, e)

        cmp.toast(self, f"Pago mensual de «{f.get('concepto')}» registrado en Contabilidad")
        self.limpiar_fijo()
        self.refrescar()

    def eliminar_fijo(self):
        s = self.tv_fijos.selection()
        if not s:
            return cmp.mostrar_error(self, "Selecciona una cuenta fija de la lista para eliminarla.")
        f = self.fijos_actuales.get(s[0], {})
        if cmp.confirmar(self, f"¿Eliminar la cuenta fija mensual «{f.get('concepto')}»?"):
            rl.eliminar_gasto_fijo(int(s[0]))
            self.limpiar_fijo()
            self.refrescar()
