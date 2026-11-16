"""Productos, categorías y entradas de inventario.

Reglas de negocio:
  * El stock SOLO aumenta mediante `registrar_entrada` (llegada de mercancía, admin).
  * El stock SOLO disminuye al emitir una factura (ver facturacion_logic).
  * Los productos no se eliminan, se desactivan, para conservar el histórico.
  * El precio de venta incluye IVA (precio final al público).
"""
import re

from database.conexion import consultar, consultar_uno, transaccion
from logica.seguridad import ROL_ADMIN, ROL_CAJERO, ErrorValidacion, Sesion, auditar, requiere_rol


def _numero(valor, nombre, entero=False, minimo=0):
    """Acepta formatos colombianos: 3500, 3.500, 3.500,50, $ 3.500."""
    texto = str(valor).replace("$", "").replace(" ", "").strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", texto):
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    try:
        n = float(texto)
        if entero:
            if n != int(n):
                raise ValueError
            n = int(n)
    except (TypeError, ValueError):
        raise ErrorValidacion(f"El campo «{nombre}» debe ser un número válido.")
    if n < minimo:
        raise ErrorValidacion(f"El campo «{nombre}» no puede ser menor que {minimo}.")
    return n


# ---------- Categorías ----------
@requiere_rol(ROL_ADMIN, ROL_CAJERO)
def listar_categorias():
    return consultar("SELECT * FROM categorias ORDER BY nombre")


@requiere_rol(ROL_ADMIN)
def guardar_categoria(nombre, descripcion, iva, id_categoria=None):
    nombre = nombre.strip()
    if not nombre:
        raise ErrorValidacion("El nombre de la categoría es obligatorio.")
    iva = _numero(iva, "IVA %")
    if iva > 100:
        raise ErrorValidacion("El IVA no puede superar el 100 %.")
    with transaccion() as con:
        if con.execute("SELECT 1 FROM categorias WHERE nombre=? AND id_categoria<>?", (nombre, id_categoria or -1)).fetchone():
            raise ErrorValidacion("Ya existe una categoría con ese nombre.")
        if id_categoria:
            con.execute("UPDATE categorias SET nombre=?, descripcion=?, iva_porcentaje=? WHERE id_categoria=?",
                        (nombre, descripcion.strip(), iva, id_categoria))
        else:
            con.execute("INSERT INTO categorias (nombre, descripcion, iva_porcentaje) VALUES (?,?,?)",
                        (nombre, descripcion.strip(), iva))
        auditar("GUARDAR_CATEGORIA", f"{nombre} IVA {iva}%", con)


# ---------- Productos ----------
@requiere_rol(ROL_ADMIN, ROL_CAJERO)
def listar_productos(texto="", solo_activos=True, id_categoria=None, solo_inactivos=False):
    sql = """SELECT p.*, c.nombre AS categoria, c.iva_porcentaje
             FROM productos p JOIN categorias c ON c.id_categoria = p.id_categoria WHERE 1=1"""
    params = []
    if solo_inactivos:
        sql += " AND p.activo = 0"
    elif solo_activos:
        sql += " AND p.activo = 1"
    if texto:
        sql += " AND (p.nombre LIKE ? OR p.codigo LIKE ? OR c.nombre LIKE ?)"
        params += [f"%{texto}%", f"%{texto}%", f"%{texto}%"]
    if id_categoria:
        sql += " AND p.id_categoria = ?"
        params.append(id_categoria)
    sql += " ORDER BY p.nombre"
    return consultar(sql, params)


@requiere_rol(ROL_ADMIN, ROL_CAJERO)
def buscar_por_codigo(codigo):
    return consultar_uno(
        """SELECT p.id_producto, p.codigo, p.nombre, p.precio, p.stock, c.iva_porcentaje
           FROM productos p JOIN categorias c ON c.id_categoria = p.id_categoria
           WHERE p.codigo = ? AND p.activo = 1""",
        (codigo.strip(),),
    )


@requiere_rol(ROL_ADMIN)
def guardar_producto(datos: dict, id_producto=None):
    codigo = (datos.get("codigo") or "").strip()
    nombre = (datos.get("nombre") or "").strip()
    if not codigo or not nombre:
        raise ErrorValidacion("El código y el nombre son obligatorios.")
    if not datos.get("id_categoria"):
        raise ErrorValidacion("Selecciona una categoría.")
    costo = _numero(datos.get("costo") or 0, "Costo del proveedor")
    precio_raw = datos.get("precio")
    if precio_raw in (None, ""):
        raise ErrorValidacion("Ingresa el precio de venta al público.")
    precio = _numero(precio_raw, "Precio de venta")
    if precio <= 0:
        raise ErrorValidacion("El precio de venta debe ser mayor que cero.")
    if costo > 0 and precio < costo:
        raise ErrorValidacion("El precio de venta no puede ser menor que el costo del proveedor.")
    stock_minimo = _numero(datos.get("stock_minimo") or 0, "Stock mínimo", entero=True)
    stock_inicial = _numero(datos.get("stock_inicial") or 0, "Stock inicial", entero=True)

    with transaccion() as con:
        if con.execute("SELECT 1 FROM productos WHERE codigo=? AND id_producto<>?",
                       (codigo, id_producto or -1)).fetchone():
            raise ErrorValidacion("Ya existe un producto con ese código.")
        if id_producto:
            anterior = con.execute("SELECT precio, costo FROM productos WHERE id_producto=?", (id_producto,)).fetchone()
            con.execute(
                """UPDATE productos SET codigo=?, nombre=?, id_categoria=?, costo=?, precio=?, stock_minimo=?
                   WHERE id_producto=?""",
                (codigo, nombre, datos["id_categoria"], costo, precio, stock_minimo, id_producto),
            )
            detalle = f"{codigo} {nombre}"
            if anterior and anterior["precio"] != precio:
                detalle += f" | precio {anterior['precio']:.0f} → {precio:.0f}"
            if anterior and anterior["costo"] != costo:
                detalle += f" | costo {anterior['costo']:.0f} → {costo:.0f}"
            auditar("EDITAR_PRODUCTO", detalle, con)
            return id_producto
        else:
            cur = con.execute(
                """INSERT INTO productos (codigo, nombre, id_categoria, costo, precio, stock, stock_minimo)
                   VALUES (?,?,?,?,?,0,?)""",
                (codigo, nombre, datos["id_categoria"], costo, precio, stock_minimo),
            )
            nuevo_id = cur.lastrowid
            auditar("CREAR_PRODUCTO", f"{codigo} {nombre}", con)
            if stock_inicial > 0:
                _entrada(con, nuevo_id, stock_inicial, "Inventario inicial")
            return nuevo_id


@requiere_rol(ROL_ADMIN)
def cambiar_estado_producto(id_producto, activo):
    with transaccion() as con:
        con.execute("UPDATE productos SET activo=? WHERE id_producto=?", (int(activo), id_producto))
        auditar("ESTADO_PRODUCTO", f"id={id_producto} activo={activo}", con)


def _entrada(con, id_producto, cantidad, referencia, costo=None, precio=None):
    fila = con.execute("SELECT stock, costo, precio FROM productos WHERE id_producto=?", (id_producto,)).fetchone()
    if fila is None:
        raise ErrorValidacion("El producto no existe.")
    nuevo = fila["stock"] + cantidad
    nuevo_costo = fila["costo"] if costo is None else costo
    nuevo_precio = fila["precio"] if precio is None else precio
    if nuevo_costo > 0 and nuevo_precio < nuevo_costo:
        raise ErrorValidacion("El precio de venta no puede quedar por debajo del costo del proveedor.")
    con.execute(
        "UPDATE productos SET stock=?, costo=?, precio=? WHERE id_producto=?",
        (nuevo, nuevo_costo, nuevo_precio, id_producto),
    )
    con.execute(
        """INSERT INTO movimientos_inventario (id_producto, tipo, cantidad, stock_final, referencia, id_usuario)
           VALUES (?, 'ENTRADA', ?, ?, ?, ?)""",
        (id_producto, cantidad, nuevo, referencia, Sesion.id()),
    )
    return nuevo


@requiere_rol(ROL_ADMIN)
def registrar_entrada(id_producto, cantidad, referencia="", costo=None, precio=None):
    """Suma stock cuando llega mercancía. Única vía para incrementar inventario."""
    cantidad = _numero(cantidad, "Cantidad", entero=True, minimo=1)
    costo = _numero(costo, "Costo proveedor unitario") if costo not in (None, "") else None
    precio = _numero(precio, "Nuevo precio de venta", minimo=1) if precio not in (None, "") else None
    with transaccion() as con:
        nuevo = _entrada(con, id_producto, cantidad, referencia.strip() or "Entrada de mercancía", costo, precio)
        auditar("ENTRADA_STOCK", f"id={id_producto} +{cantidad} → {nuevo}", con)
        return nuevo


@requiere_rol(ROL_ADMIN)
def historial_movimientos(id_producto=None, limite=300):
    sql = """SELECT m.fecha, p.codigo, p.nombre, m.tipo, m.cantidad, m.stock_final, m.referencia, u.username
             FROM movimientos_inventario m JOIN productos p ON p.id_producto = m.id_producto
             JOIN usuarios u ON u.id_usuario = m.id_usuario"""
    params = []
    if id_producto:
        sql += " WHERE m.id_producto = ?"
        params.append(id_producto)
    sql += " ORDER BY m.id_movimiento DESC LIMIT ?"
    params.append(limite)
    return consultar(sql, params)
