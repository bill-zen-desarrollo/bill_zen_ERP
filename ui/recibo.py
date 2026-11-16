"""Recibo de factura: vista en pantalla con botón Imprimir (abre HTML en el navegador)."""
import hashlib
import os
import tempfile
import webbrowser
from html import escape

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import licencia
from logica.empresa_logic import obtener_empresa
from ui import tema


def _generar_cufe(f, emp) -> str:
    semilla = f"{emp.get('nit','')}|{f['numero']}|{f['fecha']}|{f['total']:.2f}|DIAN-BILLZEN"
    return hashlib.sha256(semilla.encode("utf-8")).hexdigest()


def _html(f, emp):
    es_electronica = licencia.tiene_facturacion_electronica()
    cufe = _generar_cufe(f, emp) if es_electronica else ""
    titulo_doc = (
        f"Factura Electrónica de Venta {escape(f['numero'])}"
        if es_electronica
        else f"Recibo POS de Venta {escape(f['numero'])} (Sin Facturación Electrónica DIAN)"
    )
    bloque_dian = (
        f"<div class='sub' style='margin-top:10px;word-break:break-all;'>"
        f"<b>✓ Factura Electrónica DIAN Validada</b><br>CUFE: {cufe}</div>"
        if es_electronica
        else "<div class='sub' style='margin-top:10px;'>Documento equivalente POS local (Plan Básico — No constituye Factura Electrónica DIAN)</div>"
    )
    filas = "".join(
        f"<tr><td>{escape(d['descripcion'])}</td><td class='r'>{d['cantidad']}</td>"
        f"<td class='r'>{tema.moneda(d['precio_unitario'])}</td>"
        f"<td class='r'>{d['iva_porcentaje']:.0f}%</td>"
        f"<td class='r'>{tema.moneda(d['precio_unitario'] * d['cantidad'])}</td></tr>"
        for d in f["detalles"])
    anulada = "<div class='anul'>FACTURA ANULADA</div>" if f["estado"] == "ANULADA" else ""
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>{escape(f['numero'])}</title>
<style>
body{{font-family:'Segoe UI',Arial,sans-serif;max-width:720px;margin:30px auto;color:#222}}
h1{{color:#1F5C46;margin:0}} .sub{{color:#666;font-size:13px}}
.cab{{border-bottom:3px solid #C9A646;padding-bottom:12px;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse;margin-top:12px}}
th{{background:#1F5C46;color:#fff;padding:8px;text-align:left}} td{{padding:7px 8px;border-bottom:1px solid #eee}}
.r{{text-align:right}} .tot td{{border:none;padding:4px 8px}} .gran{{font-size:18px;font-weight:bold;color:#1F5C46}}
.anul{{color:#B5523B;font-weight:bold;font-size:22px;text-align:center;margin:10px}}
.pie{{text-align:center;color:#888;font-size:12px;margin-top:26px}}
@media print{{.no-print{{display:none}}}}
</style></head><body>
<div class="cab"><h1>{escape(emp.get('razon_social',''))}</h1>
<div class="sub">NIT {escape(emp.get('nit',''))} · {escape(emp.get('regimen') or '')}<br>
{escape(emp.get('direccion') or '')} · Tel. {escape(emp.get('telefono') or '')}</div></div>
{anulada}
<b>{titulo_doc}</b><br>
<span class="sub">Fecha: {escape(f['fecha'])} · Cajero: {escape(f['cajero'])}<br>
Cliente: {escape(f['cliente_nombre'])} ({escape(f['cliente_doc'])}) · Pago: {escape(f['metodo_pago'])}</span>
<table><tr><th>Descripción</th><th class="r">Cant.</th><th class="r">Precio</th><th class="r">IVA</th><th class="r">Total</th></tr>{filas}</table>
<table class="tot" style="width:50%;margin-left:auto">
<tr><td>Subtotal</td><td class="r">{tema.moneda(f['subtotal'])}</td></tr>
<tr><td>IVA</td><td class="r">{tema.moneda(f['iva'])}</td></tr>
<tr class="gran"><td>TOTAL</td><td class="r">{tema.moneda(f['total'])}</td></tr>
<tr><td>Recibido</td><td class="r">{tema.moneda(f['recibido'])}</td></tr>
<tr><td>Cambio</td><td class="r">{tema.moneda(max(f['recibido'] - f['total'], 0))}</td></tr></table>
{bloque_dian}
<div class="pie">¡Gracias por tu compra!<br>Generado con Bill Zen ERP</div>
<script>window.onload=function(){{setTimeout(function(){{window.print()}},400)}}</script>
</body></html>"""


def imprimir(factura):
    emp = obtener_empresa() or {}
    ruta = os.path.join(tempfile.gettempdir(), f"billzen_{factura['numero']}.html")
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(_html(factura, emp))
    webbrowser.open("file:///" + ruta.replace("\\", "/"))


class VentanaFactura(ttk.Toplevel):
    def __init__(self, padre, factura):
        super().__init__(title=f"Factura {factura['numero']}", master=padre.winfo_toplevel())
        self.geometry("520x640")
        self.configure(background=tema.BEIGE)
        self.transient(padre.winfo_toplevel())
        emp = obtener_empresa() or {}
        self.factura = factura

        marco = ttk.Frame(self, padding=20)
        marco.pack(fill=BOTH, expand=YES)
        ttk.Label(marco, text=emp.get("razon_social", ""), style="Titulo.TLabel", font=(tema.FUENTE_TITULO, 16, "bold")).pack(anchor=W)
        ttk.Label(marco, text=f"NIT {emp.get('nit', '')}", style="Subtitulo.TLabel").pack(anchor=W)
        ttk.Separator(marco).pack(fill=X, pady=8)
        estado = "  (ANULADA)" if factura["estado"] == "ANULADA" else ""
        es_electronica = licencia.tiene_facturacion_electronica()
        tipo_lbl = "Factura Electrónica DIAN" if es_electronica else "Recibo POS Local (Sin DIAN)"
        ttk.Label(marco, text=f"{tipo_lbl} {factura['numero']}{estado}", style="Fondo.TLabel",
                  font=(tema.FUENTE, 12, "bold"), foreground=tema.ROJO if estado else tema.VERDE).pack(anchor=W)
        if es_electronica:
            cufe_corto = _generar_cufe(factura, emp)[:36] + "..."
            ttk.Label(marco, text=f"✓ CUFE DIAN: {cufe_corto}", style="Subtitulo.TLabel", foreground=tema.VERDE_CLARO, font=(tema.FUENTE, 8, "bold")).pack(anchor=W)
        else:
            ttk.Label(marco, text="Plan Básico: Tirilla POS local (Actualiza a Standard o Ultra para Facturación Electrónica DIAN)", style="Subtitulo.TLabel", font=(tema.FUENTE, 8)).pack(anchor=W)
        ttk.Label(marco, text=f"{factura['fecha']}  ·  Cajero: {factura['cajero']}\nCliente: {factura['cliente_nombre']}  ·  Pago: {factura['metodo_pago']}",
                  style="Subtitulo.TLabel").pack(anchor=W, pady=(2, 8))

        from ui import componentes as cmp
        t, tv = cmp.tabla(marco, [("d", "Descripción", 210, W), ("c", "Cant.", 50, E), ("p", "Precio", 90, E), ("t", "Total", 100, E)], altura=9)
        t.pack(fill=BOTH, expand=YES)
        cmp.llenar_tabla(tv, [(i, (d["descripcion"], d["cantidad"], tema.moneda(d["precio_unitario"]),
                                   tema.moneda(d["precio_unitario"] * d["cantidad"])))
                              for i, d in enumerate(factura["detalles"])])
        tot = ttk.Frame(marco)
        tot.pack(fill=X, pady=10)
        for etiqueta, valor, grande in (("Subtotal", factura["subtotal"], False), ("IVA", factura["iva"], False),
                                        ("TOTAL", factura["total"], True)):
            fila = ttk.Frame(tot)
            fila.pack(fill=X)
            ttk.Label(fila, text=etiqueta, style="Fondo.TLabel", font=(tema.FUENTE, 13 if grande else 10, "bold" if grande else "normal")).pack(side=LEFT)
            ttk.Label(fila, text=tema.moneda(valor), style="Fondo.TLabel", foreground=tema.VERDE if grande else tema.TEXTO,
                      font=(tema.FUENTE, 13 if grande else 10, "bold" if grande else "normal")).pack(side=RIGHT)
        if factura["metodo_pago"] == "Efectivo":
            ttk.Label(marco, text=f"Recibido {tema.moneda(factura['recibido'])}  ·  Cambio {tema.moneda(max(factura['recibido'] - factura['total'], 0))}",
                      style="Subtitulo.TLabel").pack(anchor=E)
        botones = ttk.Frame(marco)
        botones.pack(fill=X, pady=(14, 0))
        ttk.Button(botones, text="🖨  Imprimir", style="Oro.TButton", command=lambda: imprimir(factura)).pack(side=LEFT)
        ttk.Button(botones, text="Cerrar", style="Suave.TButton", command=self.destroy).pack(side=RIGHT)
