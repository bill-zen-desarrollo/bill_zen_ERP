"""Tirilla de venta formato térmico 80mm (estilo D1 / Tiendas Ara / Epson TM-T88V):
vista previa vertical en pantalla e impresión ajustada a rollo de papel térmico de 80mm."""
import hashlib
import os
import tempfile
import tkinter as tk
import webbrowser
from html import escape

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from logica import licencia
from logica.empresa_logic import obtener_empresa
from ui import tema

ANCHO_CHARS = 42  # Ancho estándar de caracteres en impresora térmica de 80mm (Epson TM-T88V)


def _generar_cufe(f, emp) -> str:
    semilla = f"{emp.get('nit','')}|{f['numero']}|{f['fecha']}|{f['total']:.2f}|DIAN-BILLZEN"
    return hashlib.sha256(semilla.encode("utf-8")).hexdigest()


def _discriminar_impuestos(detalles: list[dict]) -> list[dict]:
    """Agrupa las líneas de la factura por tarifa de IVA (0%, 5%, 19%) estilo tirilla D1 / Ara."""
    grupos: dict[float, dict] = {}
    for d in detalles:
        t = float(d.get("iva_porcentaje") or 0)
        total_linea = float(d["precio_unitario"]) * int(d["cantidad"])
        base_linea = total_linea / (1.0 + t / 100.0) if t > 0 else total_linea
        iva_linea = total_linea - base_linea
        if t not in grupos:
            grupos[t] = {"tarifa": t, "compra": 0.0, "base": 0.0, "iva": 0.0}
        grupos[t]["compra"] += total_linea
        grupos[t]["base"] += base_linea
        grupos[t]["iva"] += iva_linea
    return [grupos[k] for k in sorted(grupos.keys())]


def _formatear_texto_tirilla(f: dict, emp: dict) -> str:
    """Construye la tirilla en texto monoespaciado de 42 columnas idéntica a una impresora Epson TM-T88V."""
    es_elec = licencia.tiene_facturacion_electronica()
    sep = "-" * ANCHO_CHARS
    sep_doble = "=" * ANCHO_CHARS

    def _centrar(txt: str) -> str:
        return txt.strip()[:ANCHO_CHARS].center(ANCHO_CHARS)

    def _par(izq: str, der: str) -> str:
        espacio = max(1, ANCHO_CHARS - len(izq) - len(der))
        return f"{izq}{' ' * espacio}{der}"

    lineas = []
    razon = (emp.get("razon_social") or "BILL ZEN ERP").upper()
    lineas.append(_centrar(razon))
    lineas.append(_centrar(f"NIT: {emp.get('nit') or '—'}"))
    if emp.get("regimen"):
        lineas.append(_centrar(str(emp["regimen"])))
    if emp.get("direccion"):
        lineas.append(_centrar(str(emp["direccion"])))
    if emp.get("telefono"):
        lineas.append(_centrar(f"Tel: {emp['telefono']}"))
    lineas.append(sep)

    if f.get("estado") == "ANULADA":
        lineas.append(_centrar("*** FACTURA ANULADA ***"))
        lineas.append(sep)

    titulo_doc = "FACTURA ELECTRONICA DE VENTA" if es_elec else "TIRILLA POS DE VENTA"
    lineas.append(_centrar(titulo_doc))
    lineas.append(_centrar(f"No. {f['numero']}"))
    lineas.append(sep)
    lineas.append(f"FECHA   : {f['fecha']}")
    lineas.append(f"CAJERO  : {str(f.get('cajero') or '')[:30]}")
    lineas.append(f"CLIENTE : {str(f.get('cliente_nombre') or 'Consumidor final')[:30]}")
    lineas.append(f"DOC/NIT : {str(f.get('cliente_doc') or '222222222222')}")
    lineas.append(sep)
    lineas.append("CANT  DESCRIPCION              IVA   TOTAL")
    lineas.append(sep)

    total_unidades = 0
    for d in f["detalles"]:
        cant = int(d["cantidad"])
        total_unidades += cant
        p_unit = float(d["precio_unitario"])
        sub_l = p_unit * cant
        iva_s = f"{float(d.get('iva_porcentaje') or 0):.0f}%".rjust(3)
        tot_s = tema.moneda(sub_l).replace("$ ", "$").rjust(9)
        desc = str(d["descripcion"])[:21].ljust(21)
        cant_s = str(cant).rjust(3)
        lineas.append(f"{cant_s}   {desc} {iva_s} {tot_s}")
        if cant > 1:
            lineas.append(f"      ({cant} x {tema.moneda(p_unit)} c/u)")

    lineas.append(sep_doble)
    lineas.append(_par("SUBTOTAL (BASE):", tema.moneda(f["subtotal"])))
    lineas.append(_par("TOTAL IVA:", tema.moneda(f["iva"])))
    lineas.append(_par("TOTAL A PAGAR:", tema.moneda(f["total"])))
    lineas.append(sep)
    lineas.append(_par(f"PAGO ({f['metodo_pago'].upper()}):", tema.moneda(f["recibido"])))
    cambio = max(float(f["recibido"] or 0) - float(f["total"] or 0), 0)
    lineas.append(_par("CAMBIO / VUELTAS:", tema.moneda(cambio)))
    lineas.append(sep)
    lineas.append(f"Lineas: {len(f['detalles'])}   Articulos totales: {total_unidades}")
    lineas.append(sep)

    # Discriminación de impuestos estilo D1 / Ara
    lineas.append(_centrar("DISCRIMINACION DE IMPUESTOS"))
    lineas.append("TARIFA       COMPRA        BASE        IVA")
    for imp in _discriminar_impuestos(f["detalles"]):
        t_s = f"IVA {imp['tarifa']:.0f}%".ljust(8)
        c_s = tema.moneda(imp["compra"]).replace("$ ", "$").rjust(10)
        b_s = tema.moneda(imp["base"]).replace("$ ", "$").rjust(11)
        i_s = tema.moneda(imp["iva"]).replace("$ ", "$").rjust(10)
        lineas.append(f"{t_s} {c_s} {b_s} {i_s}")

    lineas.append(sep)
    if es_elec:
        cufe = _generar_cufe(f, emp)
        lineas.append(_centrar("FACTURA ELECTRONICA DIAN"))
        lineas.append("CUFE (SHA-256):")
        lineas.append(cufe[:ANCHO_CHARS])
        lineas.append(cufe[ANCHO_CHARS:])
    else:
        lineas.append(_centrar("DOCUMENTO POS LOCAL (PLAN BASICO)"))
        lineas.append(_centrar("No constituye Factura Electronica DIAN"))

    lineas.append(sep)
    lineas.append(_centrar("GRACIAS POR SU COMPRA"))
    lineas.append(_centrar("Software POS: BillZen ERP"))
    return "\n".join(lineas)


def _html(f, emp):
    """Genera HTML optimizado específicamente para impresoras térmicas de 80mm (Epson TM-T88V)."""
    es_electronica = licencia.tiene_facturacion_electronica()
    cufe = _generar_cufe(f, emp) if es_electronica else ""
    titulo_doc = "FACTURA ELECTRÓNICA DE VENTA" if es_electronica else "TIRILLA POS DE VENTA"
    anulada = "<div class='anul'>*** FACTURA ANULADA ***</div>" if f["estado"] == "ANULADA" else ""

    filas_items = []
    total_unidades = 0
    for d in f["detalles"]:
        cant = int(d["cantidad"])
        total_unidades += cant
        p_unit = float(d["precio_unitario"])
        sub_l = p_unit * cant
        sub_detalle = (
            f"<div class='unit-sub'>{cant} x {tema.moneda(p_unit)} c/u</div>"
            if cant > 1
            else ""
        )
        filas_items.append(
            f"<tr>"
            f"<td class='c-cant'>{cant}</td>"
            f"<td class='c-desc'>{escape(d['descripcion'])}{sub_detalle}</td>"
            f"<td class='c-iva'>{d['iva_porcentaje']:.0f}%</td>"
            f"<td class='c-tot'>{tema.moneda(sub_l)}</td>"
            f"</tr>"
        )

    filas_imp = "".join(
        f"<tr>"
        f"<td>IVA {imp['tarifa']:.0f}%</td>"
        f"<td class='r'>{tema.moneda(imp['compra'])}</td>"
        f"<td class='r'>{tema.moneda(imp['base'])}</td>"
        f"<td class='r'>{tema.moneda(imp['iva'])}</td>"
        f"</tr>"
        for imp in _discriminar_impuestos(f["detalles"])
    )

    bloque_dian = (
        f"<div class='cufe'><b>FACTURA ELECTRÓNICA DIAN</b><br>"
        f"CUFE (SHA-256):<br>{cufe}</div>"
        if es_electronica
        else "<div class='cufe'>DOCUMENTO EQUIVALENTE POS LOCAL<br>(Plan Básico — Sin Facturación Electrónica DIAN)</div>"
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{escape(f['numero'])}</title>
<style>
  @page {{
    size: 80mm auto;
    margin: 2mm 3mm;
  }}
  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}
  body {{
    font-family: 'Consolas', 'Courier New', monospace;
    width: 72mm;
    max-width: 72mm;
    margin: 8px auto;
    color: #000000;
    background: #ffffff;
    font-size: 11px;
    line-height: 1.28;
  }}
  .center {{ text-align: center; }}
  .bold {{ font-weight: bold; }}
  .empresa {{ font-size: 14px; font-weight: bold; text-transform: uppercase; margin-bottom: 2px; }}
  .sep {{ border-top: 1px dashed #000; margin: 6px 0; }}
  .sep-doble {{ border-top: 2px solid #000; margin: 6px 0; }}
  .anul {{ border: 2px solid #000; padding: 4px; text-align: center; font-weight: bold; font-size: 13px; margin: 6px 0; }}
  .meta {{ font-size: 10.5px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ font-size: 10px; text-align: left; border-bottom: 1px dashed #000; padding: 3px 0; }}
  td {{ padding: 3px 0; vertical-align: top; font-size: 10.5px; }}
  .c-cant {{ width: 12%; text-align: left; }}
  .c-desc {{ width: 50%; padding-right: 4px; }}
  .c-iva {{ width: 12%; text-align: right; }}
  .c-tot {{ width: 26%; text-align: right; font-weight: bold; }}
  .unit-sub {{ font-size: 9.5px; color: #333; }}
  .r {{ text-align: right; }}
  .tot-row td {{ padding: 2px 0; }}
  .gran-total td {{ font-size: 13.5px; font-weight: bold; padding-top: 4px; }}
  .imp-title {{ text-align: center; font-weight: bold; font-size: 10px; margin-bottom: 3px; }}
  .imp-table th, .imp-table td {{ font-size: 9.5px; padding: 1.5px 0; }}
  .cufe {{ font-size: 9px; word-break: break-all; text-align: center; margin-top: 4px; }}
  .pie {{ text-align: center; font-size: 10px; margin-top: 8px; padding-bottom: 12px; }}
</style>
</head>
<body>
  <div class="center">
    <div class="empresa">{escape(emp.get('razon_social') or 'BILL ZEN ERP')}</div>
    <div>NIT: {escape(emp.get('nit') or '—')}</div>
    <div>{escape(emp.get('regimen') or '')}</div>
    <div>{escape(emp.get('direccion') or '')}</div>
    <div>Tel: {escape(emp.get('telefono') or '')}</div>
  </div>
  <div class="sep"></div>
  {anulada}
  <div class="center bold">{titulo_doc}<br>No. {escape(f['numero'])}</div>
  <div class="sep"></div>
  <div class="meta">
    FECHA   : {escape(f['fecha'])}<br>
    CAJERO  : {escape(f.get('cajero') or '')}<br>
    CLIENTE : {escape(f.get('cliente_nombre') or 'Consumidor final')}<br>
    DOC/NIT : {escape(f.get('cliente_doc') or '222222222222')}
  </div>
  <div class="sep"></div>
  <table>
    <thead>
      <tr>
        <th class="c-cant">CANT</th>
        <th class="c-desc">DESCRIPCIÓN</th>
        <th class="c-iva">IVA</th>
        <th class="c-tot">TOTAL</th>
      </tr>
    </thead>
    <tbody>
      {''.join(filas_items)}
    </tbody>
  </table>
  <div class="sep-doble"></div>
  <table>
    <tr class="tot-row"><td>SUBTOTAL (BASE):</td><td class="r">{tema.moneda(f['subtotal'])}</td></tr>
    <tr class="tot-row"><td>TOTAL IVA:</td><td class="r">{tema.moneda(f['iva'])}</td></tr>
    <tr class="gran-total"><td>TOTAL A PAGAR:</td><td class="r">{tema.moneda(f['total'])}</td></tr>
  </table>
  <div class="sep"></div>
  <table>
    <tr class="tot-row"><td>PAGO ({escape(f['metodo_pago'].upper())}):</td><td class="r">{tema.moneda(f['recibido'])}</td></tr>
    <tr class="tot-row bold"><td>CAMBIO / VUELTAS:</td><td class="r">{tema.moneda(max(f['recibido'] - f['total'], 0))}</td></tr>
  </table>
  <div class="sep"></div>
  <div class="meta center">Líneas: {len(f['detalles'])} &middot; Artículos totales: {total_unidades}</div>
  <div class="sep"></div>
  <div class="imp-title">DISCRIMINACIÓN DE IMPUESTOS</div>
  <table class="imp-table">
    <thead>
      <tr><th>TARIFA</th><th class="r">COMPRA</th><th class="r">BASE</th><th class="r">IVA</th></tr>
    </thead>
    <tbody>
      {filas_imp}
    </tbody>
  </table>
  <div class="sep"></div>
  {bloque_dian}
  <div class="sep"></div>
  <div class="pie">
    <b>¡GRACIAS POR SU COMPRA!</b><br>
    Software POS: BillZen ERP
  </div>
  <script>window.onload=function(){{setTimeout(function(){{window.print()}},350)}}</script>
</body>
</html>"""


def imprimir(factura):
    emp = obtener_empresa() or {}
    ruta = os.path.join(tempfile.gettempdir(), f"billzen_tirilla_{factura['numero']}.html")
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(_html(factura, emp))
    webbrowser.open("file:///" + ruta.replace("\\", "/"))


class VentanaFactura(ttk.Toplevel):
    """Vista previa vertical con formato de rollo térmico de 80mm (estilo D1 / Ara / Epson TM-T88V)."""

    def __init__(self, padre, factura):
        super().__init__(title=f"Tirilla de Venta {factura['numero']}", master=padre.winfo_toplevel())
        self.geometry("430x720")
        self.resizable(False, True)
        self.configure(background=tema.BEIGE)
        self.transient(padre.winfo_toplevel())
        emp = obtener_empresa() or {}
        self.factura = factura

        contenedor = ttk.Frame(self, padding=(18, 14))
        contenedor.pack(fill=BOTH, expand=YES)

        ttk.Label(
            contenedor,
            text="Tirilla POS (Formato Térmico 80mm · Epson TM-T88V)",
            style="Subtitulo.TLabel",
            font=(tema.FUENTE, 9, "bold"),
        ).pack(anchor=CENTER, pady=(0, 8))

        # Papel térmico blanco con borde sutil y sombra
        borde_papel = tk.Frame(contenedor, bg=tema.BEIGE_OSCURO, padx=1, pady=1)
        borde_papel.pack(fill=BOTH, expand=YES)

        interior_papel = tk.Frame(borde_papel, bg="#FFFFFF", padx=12, pady=12)
        interior_papel.pack(fill=BOTH, expand=YES)

        scroll = ttk.Scrollbar(interior_papel, orient=VERTICAL)
        txt_tirilla = tk.Text(
            interior_papel,
            width=44,
            font=("Consolas", 10),
            bg="#FFFFFF",
            fg="#111111",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            yscrollcommand=scroll.set,
            wrap="none",
        )
        scroll.configure(command=txt_tirilla.yview)
        txt_tirilla.pack(side=LEFT, fill=BOTH, expand=YES)
        scroll.pack(side=RIGHT, fill=Y)

        contenido = _formatear_texto_tirilla(factura, emp)
        txt_tirilla.insert("1.0", contenido)
        txt_tirilla.configure(state=DISABLED)

        botones = ttk.Frame(contenedor)
        botones.pack(fill=X, pady=(12, 0))
        ttk.Button(
            botones,
            text="Imprimir tirilla (80mm)",
            style="Oro.TButton",
            command=lambda: imprimir(factura),
        ).pack(side=LEFT, fill=X, expand=YES, padx=(0, 6))
        ttk.Button(
            botones,
            text="Cerrar",
            style="Suave.TButton",
            command=self.destroy,
        ).pack(side=RIGHT)
