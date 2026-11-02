"""Facturación: emisión atómica de facturas (única vía para descontar stock) y anulación."""
from database.conexion import consultar, consultar_uno, transaccion
from logica.seguridad import ROL_ADMIN, ROL_CAJERO, ErrorValidacion, Sesion, auditar, requiere_rol

METODOS_PAGO = ("Efectivo", "Tarjeta", "Transferencia", "Nequi / Daviplata")


def calcular_totales(items):
    """items: [{'precio','cantidad','iva_porcentaje'}]. El precio incluye IVA."""
    total = sum(i["precio"] * i["cantidad"] for i in items)
    base = sum(i["precio"] * i["cantidad"] / (1 + i["iva_porcentaje"] / 100) for i in items)
    return round(base, 2), round(total - base, 2), round(total, 2)


@requiere_rol(ROL_ADMIN, ROL_CAJERO)
def emitir_factura(items, metodo_pago="Efectivo", recibido=0, cliente_doc="", cliente_nombre=""):
    """items: [{'id_producto', 'cantidad'}]. Todo ocurre en una sola transacción:
    si un producto no tiene stock suficiente no se descuenta nada."""
    if not items:
        raise ErrorValidacion("La factura no tiene productos.")
    if metodo_pago not in METODOS_PAGO:
        raise ErrorValidacion("Método de pago inválido.")

    agrupados = {}
    for it in items:
        cantidad = int(it["cantidad"])
        if cantidad <= 0:
            raise ErrorValidacion("Las cantidades deben ser mayores que cero.")
        agrupados[it["id_producto"]] = agrupados.get(it["id_producto"], 0) + cantidad

    with transaccion() as con:
        con.execute("BEGIN IMMEDIATE")  # bloquea escritura concurrente mientras facturamos
        lineas = []
        for id_producto, cantidad in agrupados.items():
            p = con.execute(
                """SELECT p.id_producto, p.nombre, p.precio, p.costo, p.stock, p.activo, c.iva_porcentaje
                   FROM productos p JOIN categorias c ON c.id_categoria = p.id_categoria
                   WHERE p.id_producto = ?""", (id_producto,)).fetchone()
            if p is None or not p["activo"]:
                raise ErrorValidacion("Uno de los productos ya no está disponible.")
            if p["stock"] < cantidad:
                raise ErrorValidacion(f"Stock insuficiente de «{p['nombre']}». Disponible: {p['stock']}.")
            lineas.append({**dict(p), "cantidad": cantidad})

        subtotal, iva, total = calcular_totales([{"precio": l["precio"], "cantidad": l["cantidad"],
                                                 "iva_porcentaje": l["iva_porcentaje"]} for l in lineas])
        recibido = float(recibido or 0)
        if metodo_pago == "Efectivo" and recibido < total:
            raise ErrorValidacion("El valor recibido es menor que el total a pagar.")
        if metodo_pago != "Efectivo":
            recibido = total

        prefijo = (con.execute("SELECT prefijo_factura FROM empresa WHERE id_empresa=1").fetchone() or ["FV"])[0]
        siguiente = con.execute("SELECT COALESCE(MAX(id_factura), 0) + 1 FROM facturas").fetchone()[0]
        numero = f"{prefijo}-{siguiente:06d}"

        cur = con.execute(
            """INSERT INTO facturas (numero, cliente_doc, cliente_nombre, subtotal, iva, total, metodo_pago, recibido, id_usuario)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (numero, cliente_doc.strip() or "222222222222", cliente_nombre.strip() or "Consumidor final",
             subtotal, iva, total, metodo_pago, recibido, Sesion.id()))
        id_factura = cur.lastrowid

        for l in lineas:
            con.execute(
                """INSERT INTO detalles_factura (id_factura, id_producto, descripcion, cantidad, precio_unitario, iva_porcentaje, costo_unitario)
                   VALUES (?,?,?,?,?,?,?)""",
                (id_factura, l["id_producto"], l["nombre"], l["cantidad"], l["precio"], l["iva_porcentaje"], l["costo"]))
            nuevo = l["stock"] - l["cantidad"]
            con.execute("UPDATE productos SET stock=? WHERE id_producto=?", (nuevo, l["id_producto"]))
            con.execute(
                """INSERT INTO movimientos_inventario (id_producto, tipo, cantidad, stock_final, referencia, id_usuario)
                   VALUES (?, 'VENTA', ?, ?, ?, ?)""",
                (l["id_producto"], -l["cantidad"], nuevo, numero, Sesion.id()))
        auditar("EMITIR_FACTURA", f"{numero} total {total:.0f}", con)
    return id_factura


@requiere_rol(ROL_ADMIN)
def anular_factura(id_factura, motivo):
    if not motivo.strip():
        raise ErrorValidacion("Indica el motivo de la anulación.")
    with transaccion() as con:
        f = con.execute("SELECT numero, estado FROM facturas WHERE id_factura=?", (id_factura,)).fetchone()
        if f is None or f["estado"] == "ANULADA":
            raise ErrorValidacion("La factura no existe o ya fue anulada.")
        for d in con.execute("SELECT id_producto, cantidad FROM detalles_factura WHERE id_factura=?", (id_factura,)).fetchall():
            stock = con.execute("SELECT stock FROM productos WHERE id_producto=?", (d["id_producto"],)).fetchone()[0]
            nuevo = stock + d["cantidad"]
            con.execute("UPDATE productos SET stock=? WHERE id_producto=?", (nuevo, d["id_producto"]))
            con.execute(
                """INSERT INTO movimientos_inventario (id_producto, tipo, cantidad, stock_final, referencia, id_usuario)
                   VALUES (?, 'ANULACION', ?, ?, ?, ?)""",
                (d["id_producto"], d["cantidad"], nuevo, f["numero"], Sesion.id()))
        con.execute("UPDATE facturas SET estado='ANULADA' WHERE id_factura=?", (id_factura,))
        auditar("ANULAR_FACTURA", f"{f['numero']}: {motivo.strip()}", con)


@requiere_rol(ROL_ADMIN, ROL_CAJERO)
def obtener_factura(id_factura):
    f = consultar_uno(
        """SELECT f.*, u.nombre_completo AS cajero FROM facturas f
           JOIN usuarios u ON u.id_usuario = f.id_usuario WHERE f.id_factura = ?""", (id_factura,))
    if f is None:
        raise ErrorValidacion("Factura no encontrada.")
    if not Sesion.es_admin() and f["id_usuario"] != Sesion.id():
        raise ErrorValidacion("Solo puedes consultar tus propias facturas.")
    f["detalles"] = consultar("SELECT * FROM detalles_factura WHERE id_factura=?", (id_factura,))
    return f


@requiere_rol(ROL_ADMIN, ROL_CAJERO)
def listar_facturas(desde, hasta, texto=""):
    sql = """SELECT f.id_factura, f.numero, f.fecha, f.cliente_nombre, f.total, f.metodo_pago, f.estado,
                    u.username FROM facturas f JOIN usuarios u ON u.id_usuario = f.id_usuario
             WHERE date(f.fecha) BETWEEN ? AND ?"""
    params = [desde, hasta]
    if not Sesion.es_admin():
        sql += " AND f.id_usuario = ?"
        params.append(Sesion.id())
    if texto:
        sql += " AND (f.numero LIKE ? OR f.cliente_nombre LIKE ? OR f.cliente_doc LIKE ?)"
        params += [f"%{texto}%"] * 3
    return consultar(sql + " ORDER BY f.id_factura DESC", params)
