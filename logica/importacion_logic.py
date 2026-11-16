import os
import shutil
import sys
from database.conexion import consultar
from logica.productos_logic import guardar_categoria, guardar_producto, listar_categorias
from logica.seguridad import ROL_ADMIN, ErrorValidacion, requiere_rol

_MAX_BYTES_EXCEL = 10 * 1024 * 1024  # 10 MB máx. para proteger equipos de baja RAM
_BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_RUTA_PLANTILLA_BASE = os.path.join(_BASE_DIR, "assets", "plantilla_productos.xlsx")


def _sanitizar_texto(texto: str) -> str:
    limpio = (texto or "").strip()
    while limpio and limpio[0] in ("=", "+", "-", "@", "\t", "\r"):
        limpio = limpio[1:].strip()
    return limpio[:150]


def generar_archivo_plantilla(destino: str):
    """Genera el archivo Excel de plantilla con formato claro, ejemplos y hoja de guía para el administrador."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    wb = openpyxl.Workbook()

    # Hoja 1: Plantilla Productos (la que lee el importador)
    ws = wb.active
    ws.title = "Plantilla Productos"
    cabeceras = ["codigo", "nombre", "categoria", "costo", "precio", "stock_minimo", "stock_inicial"]
    ws.append(cabeceras)

    relleno_cab = PatternFill(start_color="1F5C46", end_color="1F5C46", fill_type="solid")
    fuente_cab = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = relleno_cab
        cell.font = fuente_cab
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 24

    ejemplos = [
        ["7701001", "Arroz Diana 500g", "Canasta familiar", 2000, 2800, 10, 50],
        ["7701002", "Café Sello Rojo 250g", "Alimentos procesados", 6800, 9200, 5, 25],
        ["7701003", "Gaseosa 1.5L", "Bebidas", 3200, 5000, 6, 30],
        ["7701004", "Detergente en polvo 1kg", "Aseo y hogar", 5900, 8900, 4, 15],
    ]
    for fila in ejemplos:
        ws.append(fila)

    anchos = {"A": 18, "B": 32, "C": 24, "D": 16, "E": 16, "F": 16, "G": 16}
    for col_letra, ancho in anchos.items():
        ws.column_dimensions[col_letra].width = ancho

    # Hoja 2: Guía de uso para el administrador
    guia = wb.create_sheet(title="Instrucciones y Categorías")
    guia.append(["Campo", "Obligatorio", "Descripción"])
    for cell in guia[1]:
        cell.fill = PatternFill(start_color="C9A646", end_color="C9A646", fill_type="solid")
        cell.font = Font(name="Segoe UI", size=11, bold=True, color="121212")

    instrucciones = [
        ["codigo", "SÍ", "Código único o código de barras del producto (ej. 7701001)."],
        ["nombre", "SÍ", "Nombre comercial del producto."],
        ["categoria", "NO", "Categoría del producto (define el IVA automáticamente). Si se deja vacío usa 'General'."],
        ["costo", "SÍ", "Costo unitario al que te llega del proveedor (ej. 2000)."],
        ["precio", "SÍ", "Precio final de venta al público por unidad con IVA incluido (ej. 2800). Debe ser mayor o igual al costo."],
        ["stock_minimo", "NO", "Cantidad mínima para alerta de agotado (ej. 5)."],
        ["stock_inicial", "NO", "Unidades con las que inicia el inventario (solo aplica para productos nuevos)."],
        ["", "", ""],
        ["Categorías incluidas", "IVA %", "Ejemplos"],
        ["Canasta familiar", "0%", "Leche, huevos, arroz, frutas, verduras (exentos)"],
        ["Alimentos procesados", "5%", "Embutidos, café, chocolate, harinas"],
        ["Abarrotes", "19%", "Productos de despensa general"],
        ["Bebidas", "19%", "Gaseosas, jugos y bebidas"],
        ["Aseo y hogar", "19%", "Limpieza y cuidado del hogar"],
        ["Cuidado personal", "19%", "Jabón personal, shampoo, higiene"],
        ["General", "19%", "Cualquier otro producto con tarifa general"],
    ]
    for fila in instrucciones:
        guia.append(fila)
    guia.column_dimensions["A"].width = 24
    guia.column_dimensions["B"].width = 14
    guia.column_dimensions["C"].width = 68

    wb.save(destino)
    wb.close()


@requiere_rol(ROL_ADMIN)
def exportar_plantilla(ruta):
    if not os.path.exists(_RUTA_PLANTILLA_BASE):
        generar_archivo_plantilla(_RUTA_PLANTILLA_BASE)
    shutil.copy2(_RUTA_PLANTILLA_BASE, ruta)


@requiere_rol(ROL_ADMIN)
def importar_inventario(ruta):
    import openpyxl

    if not os.path.exists(ruta):
        raise ErrorValidacion("El archivo no existe.")
    if os.path.getsize(ruta) > _MAX_BYTES_EXCEL:
        raise ErrorValidacion("El archivo supera el tamaño máximo permitido (10 MB).")

    try:
        wb = openpyxl.load_workbook(ruta, data_only=True, read_only=True)
        try:
            ws = wb["Plantilla Productos"] if "Plantilla Productos" in wb.sheetnames else wb.worksheets[0]
            filas = list(ws.iter_rows(values_only=True))
        finally:
            wb.close()
    except Exception:
        raise ErrorValidacion("No se pudo abrir el archivo de Excel. Asegúrate de que tenga extensión .xlsx")

    if not filas:
        raise ErrorValidacion("El archivo está vacío.")

    cabeceras = [str(c).lower().strip() if c else "" for c in filas[0]]
    if "codigo" not in cabeceras or "nombre" not in cabeceras:
        raise ErrorValidacion("Formato incorrecto. Descargue la plantilla y no modifique los títulos de las columnas.")

    indices = {col: (cabeceras.index(col) if col in cabeceras else -1)
               for col in ("codigo", "nombre", "categoria", "costo", "precio", "stock_minimo", "stock_inicial")}

    categorias_existentes = {c["nombre"].lower(): c["id_categoria"] for c in listar_categorias()}
    codigos_existentes = {p["codigo"]: p["id_producto"] for p in consultar("SELECT codigo, id_producto FROM productos")}

    def _celda(fila, col, defecto=""):
        idx = indices[col]
        return str(fila[idx]).strip() if (idx != -1 and idx < len(fila) and fila[idx] is not None) else defecto

    for fila in filas[1:]:
        codigo = _sanitizar_texto(_celda(fila, "codigo"))[:50]
        nombre = _sanitizar_texto(_celda(fila, "nombre"))
        if not codigo or not nombre:
            continue

        cat_nombre = _sanitizar_texto(_celda(fila, "categoria")) or "General"
        clave_cat = cat_nombre.lower()
        id_cat = categorias_existentes.get(clave_cat)
        if not id_cat:
            guardar_categoria(cat_nombre, "Categoría importada", 0)
            categorias_existentes = {c["nombre"].lower(): c["id_categoria"] for c in listar_categorias()}
            id_cat = categorias_existentes[clave_cat]

        id_existente = codigos_existentes.get(codigo)
        costo_str = _celda(fila, "costo", "0")
        precio_str = _celda(fila, "precio", "") or costo_str
        datos = {
            "codigo": codigo,
            "nombre": nombre,
            "id_categoria": id_cat,
            "costo": costo_str,
            "precio": precio_str,
            "stock_minimo": _celda(fila, "stock_minimo", "0"),
            "stock_inicial": "0" if id_existente else _celda(fila, "stock_inicial", "0"),
        }
        codigos_existentes[codigo] = guardar_producto(datos, id_existente)
