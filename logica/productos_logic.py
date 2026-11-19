"""Productos, categorías y Kardex de inventario.

Reglas de negocio:
  * El catálogo maestro (precios, costos, categorías/IVA, creación y desactivación) vive en Productos.
  * El stock se registra y audita en `inventory_movements` (Kardex) y se encola en `sync_queue`
    para sincronización local-first hacia PostgreSQL (Neon.tech).
  * Las ventas en Facturación descuentan stock registrando movimientos `VENTA`; las anulaciones
    restituyen con `DEVOLUCION`.
  * Los productos no se eliminan, se desactivan, para conservar el histórico.
  * El precio de venta incluye IVA (precio final al público).
"""
import json
import os
import re
import threading
import urllib.error
import urllib.request
from datetime import date

from database.conexion import consultar, consultar_uno, transaccion
from logica.seguridad import ROL_ADMIN, ROL_CAJERO, ErrorValidacion, Sesion, auditar, requiere_rol

TIPOS_MOVIMIENTO_KARDEX = ("ENTRADA", "SALIDA_MERMA", "AJUSTE_CONTEO", "VENTA", "DEVOLUCION")

ETIQUETAS_TIPO_MOVIMIENTO = {
    "ENTRADA": "Entrada",
    "SALIDA_MERMA": "Salida / Merma",
    "AJUSTE_CONTEO": "Ajuste conteo",
    "VENTA": "Venta",
    "DEVOLUCION": "Devolución",
}

_MAPA_TIPO_MOVIMIENTO_UI = {
    "ENTRADA": "ENTRADA",
    "ENTRADA POR COMPRA": "ENTRADA",
    "SALIDA_MERMA": "SALIDA_MERMA",
    "SALIDA POR MERMA/DAÑO": "SALIDA_MERMA",
    "SALIDA POR MERMA": "SALIDA_MERMA",
    "MERMA": "SALIDA_MERMA",
    "AJUSTE_CONTEO": "AJUSTE_CONTEO",
    "AJUSTE CONTEO FÍSICO": "AJUSTE_CONTEO",
    "AJUSTE CONTEO FISICO": "AJUSTE_CONTEO",
    "AJUSTE DE INVENTARIO (CONTEO FÍSICO)": "AJUSTE_CONTEO",
    "AJUSTE DE INVENTARIO": "AJUSTE_CONTEO",
    "AJUSTE": "AJUSTE_CONTEO",
    "DEVOLUCION": "DEVOLUCION",
    "DEVOLUCIÓN": "DEVOLUCION",
}

_SYNC_LOCK = threading.Lock()
_ESTADO_SYNC = {
    "online": False,
    "sincronizando": False,
    "pendientes": 0,
    "ultimo_error": "",
    "modo": "offline",
}


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


def _normalizar_tipo_movimiento(tipo_movimiento: str) -> str:
    clave = (tipo_movimiento or "").strip().upper()
    normalizado = _MAPA_TIPO_MOVIMIENTO_UI.get(clave)
    if not normalizado:
        raise ErrorValidacion("Tipo de movimiento de inventario inválido.")
    return normalizado


def _registrar_kardex_y_sync(
    con,
    id_producto: int,
    movement_type: str,
    quantity: int,
    previous_stock: int,
    new_stock: int,
    reason: str,
    user_id: int | None = None,
) -> int:
    """Inserta en `inventory_movements`, replica en `movimientos_inventario` y encola en `sync_queue`
    dentro de la misma transacción SQLite."""
    if movement_type not in TIPOS_MOVIMIENTO_KARDEX:
        raise ErrorValidacion(f"Tipo de movimiento no soportado: {movement_type}")
    qty = int(quantity)
    if qty <= 0:
        raise ErrorValidacion("La cantidad del movimiento en Kardex debe ser mayor que cero.")

    uid = user_id if user_id is not None else Sesion.id()
    if uid is None:
        raise ErrorValidacion("No hay un usuario autenticado para registrar el movimiento.")

    reason_limpia = (reason or "").strip()
    cur = con.execute(
        """INSERT INTO inventory_movements
           (product_id, movement_type, quantity, previous_stock, new_stock, reason, user_id, synced)
           VALUES (?,?,?,?,?,?,?,0)""",
        (id_producto, movement_type, qty, int(previous_stock), int(new_stock), reason_limpia, uid),
    )
    mov_id = int(cur.lastrowid)

    fila_mov = con.execute(
        "SELECT created_at FROM inventory_movements WHERE id = ?",
        (mov_id,),
    ).fetchone()
    created_at = fila_mov["created_at"] if fila_mov else ""

    # Compatibilidad retroactiva con tabla legada `movimientos_inventario` (CHECK tipo IN ENTRADA/VENTA/ANULACION)
    delta = int(new_stock) - int(previous_stock)
    if movement_type == "ENTRADA":
        tipo_legado, cant_legado = "ENTRADA", qty
    elif movement_type == "VENTA":
        tipo_legado, cant_legado = "VENTA", -qty
    elif movement_type == "DEVOLUCION":
        tipo_legado, cant_legado = "ANULACION", qty
    else:
        tipo_legado = "ENTRADA" if delta >= 0 else "ANULACION"
        cant_legado = delta if delta != 0 else -qty

    con.execute(
        """INSERT INTO movimientos_inventario (id_producto, tipo, cantidad, stock_final, referencia, id_usuario)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (id_producto, tipo_legado, cant_legado, int(new_stock), reason_limpia, uid),
    )

    sku_row = con.execute("SELECT codigo FROM productos WHERE id_producto = ?", (id_producto,)).fetchone()
    sku = sku_row["codigo"] if sku_row else ""
    payload = json.dumps(
        {
            "movement_id": mov_id,
            "product_id": int(id_producto),
            "sku": sku,
            "movement_type": movement_type,
            "quantity": qty,
            "previous_stock": int(previous_stock),
            "new_stock": int(new_stock),
            "reason": reason_limpia,
            "user_id": int(uid),
            "created_at": created_at,
        },
        ensure_ascii=False,
    )
    con.execute(
        """INSERT INTO sync_queue (table_name, record_id, operation, payload, status)
           VALUES ('inventory_movements', ?, 'INSERT', ?, 'PENDING')""",
        (mov_id, payload),
    )
    return mov_id


def _entrada(con, id_producto, cantidad, referencia, costo=None, precio=None, registrar_egreso=False):
    fila = con.execute("SELECT nombre, stock, costo, precio FROM productos WHERE id_producto=?", (id_producto,)).fetchone()
    if fila is None:
        raise ErrorValidacion("El producto no existe.")
    anterior = int(fila["stock"])
    nuevo = anterior + int(cantidad)
    nuevo_costo = fila["costo"] if costo is None else costo
    nuevo_precio = fila["precio"] if precio is None else precio
    if nuevo_costo > 0 and nuevo_precio < nuevo_costo:
        raise ErrorValidacion("El precio de venta no puede quedar por debajo del costo del proveedor.")
    con.execute(
        "UPDATE productos SET stock=?, costo=?, precio=? WHERE id_producto=?",
        (nuevo, nuevo_costo, nuevo_precio, id_producto),
    )
    _registrar_kardex_y_sync(
        con,
        id_producto=id_producto,
        movement_type="ENTRADA",
        quantity=int(cantidad),
        previous_stock=anterior,
        new_stock=nuevo,
        reason=referencia,
    )
    if registrar_egreso and float(nuevo_costo or 0) > 0:
        valor_compra = round(float(nuevo_costo) * int(cantidad), 2)
        con.execute(
            """INSERT INTO gastos
               (fecha, concepto, categoria, valor, proveedor, metodo_pago, comprobante, estado, id_usuario)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                date.today().isoformat(),
                f"Ingreso de stock: {fila['nombre']} (x{cantidad})",
                "Proveedores y mercancía",
                valor_compra,
                "",
                "Efectivo",
                referencia if referencia != "Entrada de mercancía" else "",
                "PAGADO",
                Sesion.id(),
            ),
        )
    return nuevo


@requiere_rol(ROL_ADMIN)
def registrar_entrada(id_producto, cantidad, referencia="", costo=None, precio=None):
    """Suma stock cuando llega mercancía y registra el egreso correspondiente en Contabilidad."""
    cantidad = _numero(cantidad, "Cantidad", entero=True, minimo=1)
    costo = _numero(costo, "Costo proveedor unitario") if costo not in (None, "") else None
    precio = _numero(precio, "Nuevo precio de venta", minimo=1) if precio not in (None, "") else None
    with transaccion() as con:
        nuevo = _entrada(
            con,
            id_producto,
            cantidad,
            referencia.strip() or "Entrada de mercancía",
            costo,
            precio,
            registrar_egreso=True,
        )
        auditar("ENTRADA_STOCK", f"id={id_producto} +{cantidad} → {nuevo}", con)
        return nuevo


@requiere_rol(ROL_ADMIN)
def registrar_movimiento_inventario(
    id_producto,
    tipo_movimiento: str,
    cantidad,
    motivo: str = "",
    costo=None,
    precio=None,
    registrar_egreso: bool = True,
) -> dict:
    """Registra de forma atómica un movimiento de inventario en Kardex (`inventory_movements`),
    actualiza `productos.stock` y encola la sincronización hacia Neon.tech (`sync_queue`)."""
    if not id_producto:
        raise ErrorValidacion("Selecciona un producto.")

    tipo = _normalizar_tipo_movimiento(tipo_movimiento)
    motivo_limpio = (motivo or "").strip()

    if tipo in ("SALIDA_MERMA", "AJUSTE_CONTEO") and not motivo_limpio:
        raise ErrorValidacion("El motivo u observación es obligatorio para salidas por merma o ajustes de conteo.")

    if tipo == "AJUSTE_CONTEO":
        valor_num = int(_numero(cantidad, "Conteo físico real", entero=True, minimo=0))
    else:
        valor_num = int(_numero(cantidad, "Cantidad", entero=True, minimo=1))

    costo_num = _numero(costo, "Costo proveedor unitario") if costo not in (None, "") else None
    precio_num = _numero(precio, "Nuevo precio de venta", minimo=1) if precio not in (None, "") else None

    with transaccion() as con:
        con.execute("BEGIN IMMEDIATE")
        fila = con.execute(
            "SELECT id_producto, codigo, nombre, stock, costo, precio FROM productos WHERE id_producto=?",
            (int(id_producto),),
        ).fetchone()
        if fila is None:
            raise ErrorValidacion("El producto no existe.")

        previous_stock = int(fila["stock"])
        nuevo_costo = fila["costo"] if costo_num is None else costo_num
        nuevo_precio = fila["precio"] if precio_num is None else precio_num
        if nuevo_costo > 0 and nuevo_precio < nuevo_costo:
            raise ErrorValidacion("El precio de venta no puede quedar por debajo del costo del proveedor.")

        if tipo == "ENTRADA":
            quantity_kardex = valor_num
            new_stock = previous_stock + valor_num
            reason_final = motivo_limpio or "Entrada por compra"
        elif tipo == "DEVOLUCION":
            quantity_kardex = valor_num
            new_stock = previous_stock + valor_num
            reason_final = motivo_limpio or "Devolución"
        elif tipo == "SALIDA_MERMA":
            if valor_num > previous_stock:
                raise ErrorValidacion(
                    f"Stock insuficiente de «{fila['nombre']}». Disponible: {previous_stock} unidad(es), "
                    f"intentas dar de baja {valor_num}."
                )
            quantity_kardex = valor_num
            new_stock = previous_stock - valor_num
            reason_final = motivo_limpio
        elif tipo == "AJUSTE_CONTEO":
            diferencia = valor_num - previous_stock
            if diferencia == 0:
                raise ErrorValidacion(
                    f"El conteo físico ({valor_num}) coincide con el stock actual ({previous_stock}). No hay diferencia para ajustar."
                )
            quantity_kardex = abs(diferencia)
            new_stock = valor_num
            reason_final = motivo_limpio
        else:
            raise ErrorValidacion("Tipo de movimiento no permitido en registro manual.")

        con.execute(
            "UPDATE productos SET stock=?, costo=?, precio=? WHERE id_producto=?",
            (new_stock, nuevo_costo, nuevo_precio, int(id_producto)),
        )

        mov_id = _registrar_kardex_y_sync(
            con,
            id_producto=int(id_producto),
            movement_type=tipo,
            quantity=quantity_kardex,
            previous_stock=previous_stock,
            new_stock=new_stock,
            reason=reason_final,
        )

        if tipo == "ENTRADA" and registrar_egreso and float(nuevo_costo or 0) > 0:
            valor_compra = round(float(nuevo_costo) * quantity_kardex, 2)
            con.execute(
                """INSERT INTO gastos
                   (fecha, concepto, categoria, valor, proveedor, metodo_pago, comprobante, estado, id_usuario)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    date.today().isoformat(),
                    f"Ingreso de stock: {fila['nombre']} (x{quantity_kardex})",
                    "Proveedores y mercancía",
                    valor_compra,
                    "",
                    "Efectivo",
                    reason_final if reason_final != "Entrada por compra" else "",
                    "PAGADO",
                    Sesion.id(),
                ),
            )

        auditar(
            "MOVIMIENTO_INVENTARIO",
            f"{tipo} {fila['codigo']} ({previous_stock} -> {new_stock}) | {reason_final}",
            con,
        )

    return {
        "id_movimiento": mov_id,
        "product_id": int(id_producto),
        "movement_type": tipo,
        "quantity": quantity_kardex,
        "previous_stock": previous_stock,
        "new_stock": new_stock,
        "diferencia": new_stock - previous_stock,
        "reason": reason_final,
    }


@requiere_rol(ROL_ADMIN, ROL_CAJERO)
def resumen_kpis_inventario() -> dict:
    """Devuelve métricas agregadas de bodega sobre los productos activos."""
    fila = consultar_uno(
        """SELECT COALESCE(SUM(stock), 0) AS total_unidades,
                  COALESCE(SUM(costo * stock), 0) AS valorizacion,
                  COALESCE(SUM(CASE WHEN stock <= stock_minimo THEN 1 ELSE 0 END), 0) AS alertas_stock_bajo,
                  COUNT(*) AS total_productos
           FROM productos
           WHERE activo = 1"""
    ) or {}
    return {
        "total_unidades": int(fila.get("total_unidades") or 0),
        "valorizacion": float(fila.get("valorizacion") or 0.0),
        "alertas_stock_bajo": int(fila.get("alertas_stock_bajo") or 0),
        "total_productos": int(fila.get("total_productos") or 0),
    }


def _construir_filtros_kardex(
    texto: str = "",
    filtro_tipo: str = "Todos",
    solo_stock_bajo: bool = False,
    id_producto: int | None = None,
) -> tuple[str, list]:
    """Construye la cláusula WHERE compartida entre listado paginado y conteo SQL del Kardex."""
    clausulas = []
    params = []

    t = (texto or "").strip()
    if t:
        like = f"%{t}%"
        clausulas.append("(p.codigo LIKE ? OR p.nombre LIKE ? OR COALESCE(m.reason, '') LIKE ?)")
        params.extend([like, like, like])

    ft = (filtro_tipo or "Todos").strip()
    if ft == "Entradas":
        clausulas.append("m.movement_type IN ('ENTRADA', 'DEVOLUCION')")
    elif ft == "Mermas/Ajustes":
        clausulas.append("m.movement_type IN ('SALIDA_MERMA', 'AJUSTE_CONTEO')")
    elif ft == "Ventas":
        clausulas.append("m.movement_type = 'VENTA'")
    elif ft in TIPOS_MOVIMIENTO_KARDEX:
        clausulas.append("m.movement_type = ?")
        params.append(ft)

    if solo_stock_bajo:
        clausulas.append("p.activo = 1 AND p.stock <= p.stock_minimo")

    if id_producto:
        clausulas.append("m.product_id = ?")
        params.append(int(id_producto))

    where_sql = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
    return where_sql, params


@requiere_rol(ROL_ADMIN, ROL_CAJERO)
def contar_movimientos_kardex(
    texto: str = "",
    filtro_tipo: str = "Todos",
    solo_stock_bajo: bool = False,
    id_producto: int | None = None,
) -> int:
    """Cuenta en SQL puro el total de movimientos del Kardex que cumplen los filtros."""
    where_sql, params = _construir_filtros_kardex(texto, filtro_tipo, solo_stock_bajo, id_producto)
    fila = consultar_uno(
        f"""SELECT COUNT(*) AS total
            FROM inventory_movements m
            JOIN productos p ON p.id_producto = m.product_id
            {where_sql}""",
        params,
    )
    return int((fila or {}).get("total") or 0)


@requiere_rol(ROL_ADMIN, ROL_CAJERO)
def listar_movimientos_kardex(
    texto: str = "",
    filtro_tipo: str = "Todos",
    solo_stock_bajo: bool = False,
    id_producto: int | None = None,
    limite: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Consulta paginada del historial cronológico del Kardex (`inventory_movements`, máx. 100 por página)."""
    where_sql, params = _construir_filtros_kardex(texto, filtro_tipo, solo_stock_bajo, id_producto)
    limite_seguro = max(1, min(int(limite or 100), 100))
    offset_seguro = max(0, int(offset or 0))

    sql = f"""SELECT m.id,
                     m.product_id,
                     p.codigo,
                     p.codigo AS sku,
                     p.nombre,
                     p.stock AS stock_actual,
                     p.stock_minimo,
                     p.activo,
                     m.movement_type,
                     m.quantity,
                     m.previous_stock,
                     m.new_stock,
                     COALESCE(m.reason, '') AS reason,
                     m.user_id,
                     u.username,
                     u.nombre_completo AS usuario_nombre,
                     m.created_at,
                     m.synced
              FROM inventory_movements m
              JOIN productos p ON p.id_producto = m.product_id
              JOIN usuarios u ON u.id_usuario = m.user_id
              {where_sql}
              ORDER BY m.created_at DESC, m.id DESC
              LIMIT ? OFFSET ?"""
    params.extend([limite_seguro, offset_seguro])

    filas = consultar(sql, params)
    resultado = []
    pids_vistos = set()
    for f in filas:
        pids_vistos.add(f["product_id"])
        variacion = int(f["new_stock"]) - int(f["previous_stock"])
        resultado.append({
            **f,
            "etiqueta_tipo": ETIQUETAS_TIPO_MOVIMIENTO.get(f["movement_type"], f["movement_type"]),
            "variacion": variacion,
            "es_stock_bajo": bool(f["activo"] and f["stock_actual"] <= f["stock_minimo"]),
        })

    t = (texto or "").strip()
    ft = (filtro_tipo or "Todos").strip()
    if solo_stock_bajo and offset_seguro == 0 and ft in ("Todos", "", None) and id_producto is None and len(resultado) < limite_seguro:
        sql_bajos = """SELECT id_producto, codigo, nombre, stock, stock_minimo, creado_en
                       FROM productos
                       WHERE activo = 1 AND stock <= stock_minimo"""
        params_bajos = []
        if t:
            like = f"%{t}%"
            sql_bajos += " AND (codigo LIKE ? OR nombre LIKE ?)"
            params_bajos.extend([like, like])
        sql_bajos += " ORDER BY stock ASC, nombre ASC LIMIT ?"
        params_bajos.append(limite_seguro - len(resultado))
        for pb in consultar(sql_bajos, params_bajos):
            if pb["id_producto"] not in pids_vistos:
                resultado.append({
                    "id": -int(pb["id_producto"]),
                    "product_id": pb["id_producto"],
                    "codigo": pb["codigo"],
                    "sku": pb["codigo"],
                    "nombre": pb["nombre"],
                    "stock_actual": pb["stock"],
                    "stock_minimo": pb["stock_minimo"],
                    "activo": 1,
                    "movement_type": "STOCK_BAJO",
                    "etiqueta_tipo": "Alerta stock",
                    "quantity": pb["stock"],
                    "variacion": 0,
                    "previous_stock": pb["stock"],
                    "new_stock": pb["stock"],
                    "reason": f"Sin movimientos · Stock ({pb['stock']}) <= mínimo ({pb['stock_minimo']})",
                    "user_id": None,
                    "username": "Sistema",
                    "usuario_nombre": "Sistema",
                    "created_at": pb["creado_en"],
                    "synced": 1,
                    "es_stock_bajo": True,
                })

    return resultado


@requiere_rol(ROL_ADMIN, ROL_CAJERO)
def historial_movimientos(id_producto=None, limite=300):
    sql = """SELECT m.id,
                    m.created_at AS fecha,
                    p.codigo,
                    p.nombre,
                    m.movement_type AS tipo,
                    m.quantity AS cantidad,
                    m.previous_stock,
                    m.new_stock AS stock_final,
                    COALESCE(m.reason, '') AS referencia,
                    u.username
             FROM inventory_movements m
             JOIN productos p ON p.id_producto = m.product_id
             JOIN usuarios u ON u.id_usuario = m.user_id"""
    params = []
    if id_producto:
        sql += " WHERE m.product_id = ?"
        params.append(id_producto)
    sql += " ORDER BY m.id DESC LIMIT ?"
    params.append(limite)
    return consultar(sql, params)


@requiere_rol(ROL_ADMIN, ROL_CAJERO)
def obtener_cola_sincronizacion(estado: str = "PENDING", limite: int = 500) -> list[dict]:
    """Lista los registros pendientes o procesados en la cola de sincronización hacia Neon.tech."""
    sql = "SELECT * FROM sync_queue WHERE 1=1"
    params = []
    if estado:
        sql += " AND status = ?"
        params.append(estado)
    sql += " ORDER BY id ASC LIMIT ?"
    params.append(int(limite))
    return consultar(sql, params)


@requiere_rol(ROL_ADMIN)
def marcar_movimiento_sincronizado(id_sync: int, exitoso: bool = True):
    """Marca un elemento de `sync_queue` como sincronizado (o fallido) y actualiza `inventory_movements.synced`."""
    nuevo_estado = "SYNCED" if exitoso else "FAILED"
    with transaccion() as con:
        fila = con.execute("SELECT table_name, record_id FROM sync_queue WHERE id = ?", (int(id_sync),)).fetchone()
        if not fila:
            raise ErrorValidacion("Elemento de sincronización no encontrado.")
        con.execute(
            "UPDATE sync_queue SET status = ?, synced_at = datetime('now','localtime') WHERE id = ?",
            (nuevo_estado, int(id_sync)),
        )
        if exitoso and fila["table_name"] == "inventory_movements":
            con.execute("UPDATE inventory_movements SET synced = 1 WHERE id = ?", (fila["record_id"],))


def _contar_pendientes_sync() -> int:
    try:
        fila = consultar_uno("SELECT COUNT(*) AS n FROM sync_queue WHERE status = 'PENDING'")
        return int((fila or {}).get("n") or 0)
    except Exception:
        return 0


def obtener_estado_sincronizacion() -> dict:
    """Devuelve el estado actual de la cola local SQLite y la conectividad hacia la nube."""
    pendientes = _contar_pendientes_sync()
    with _SYNC_LOCK:
        estado = dict(_ESTADO_SYNC)
    estado["pendientes"] = pendientes
    if estado["online"] and pendientes == 0:
        estado["etiqueta"] = "● Sincronizado con Nube"
        estado["modo"] = "cloud"
    elif estado["online"] and pendientes > 0:
        estado["etiqueta"] = f"● Sincronizando ({pendientes})" if estado["sincronizando"] else f"● Pendiente Nube ({pendientes})"
        estado["modo"] = "syncing" if estado["sincronizando"] else "offline"
    else:
        estado["etiqueta"] = "● Modo Offline (SQLite)" if pendientes == 0 else f"● Modo Offline (SQLite · {pendientes})"
        estado["modo"] = "offline"
    return estado


def _trabajador_sync_bg(callback_ui=None):
    url_sync = (os.environ.get("BILLZEN_NEON_SYNC_URL") or "").strip()
    online_ok = False
    error_txt = ""

    try:
        if url_sync:
            pendientes = consultar(
                "SELECT id, table_name, record_id, operation, payload FROM sync_queue WHERE status = 'PENDING' ORDER BY id ASC LIMIT 50"
            )
            if pendientes:
                cuerpo = json.dumps({"items": pendientes}, ensure_ascii=False).encode("utf-8")
                req = urllib.request.Request(
                    url_sync,
                    data=cuerpo,
                    headers={"Content-Type": "application/json", "User-Agent": "BillZenERP-Desktop/1.0"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    if 200 <= resp.status < 300:
                        online_ok = True
                        with transaccion() as con:
                            for it in pendientes:
                                con.execute(
                                    "UPDATE sync_queue SET status = 'SYNCED', synced_at = datetime('now','localtime') WHERE id = ?",
                                    (it["id"],),
                                )
                                if it["table_name"] == "inventory_movements":
                                    con.execute("UPDATE inventory_movements SET synced = 1 WHERE id = ?", (it["record_id"],))
            else:
                req = urllib.request.Request(url_sync, headers={"User-Agent": "BillZenERP-Desktop/1.0"}, method="GET")
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    online_ok = 200 <= resp.status < 400
        else:
            # Sin endpoint Neon directo configurado, verifica conectividad general de forma no bloqueante
            # sin alterar `sync_queue` (modo Offline-First SQLite).
            pendientes_n = _contar_pendientes_sync()
            if pendientes_n == 0:
                from logica.licencia import URL_API_LICENCIA
                base_api = URL_API_LICENCIA.rsplit("/licencia/activar", 1)[0] + "/plan/estado"
                req = urllib.request.Request(base_api, headers={"User-Agent": "BillZenERP-Desktop/1.0"}, method="GET")
                try:
                    with urllib.request.urlopen(req, timeout=2.0) as resp:
                        online_ok = 200 <= resp.status < 500
                except urllib.error.HTTPError as err:
                    online_ok = 200 <= err.code < 500
    except Exception as exc:
        online_ok = False
        error_txt = str(exc)

    with _SYNC_LOCK:
        _ESTADO_SYNC["online"] = online_ok
        _ESTADO_SYNC["sincronizando"] = False
        _ESTADO_SYNC["ultimo_error"] = error_txt

    if callback_ui:
        try:
            callback_ui(obtener_estado_sincronizacion())
        except Exception:
            pass


def disparar_sincronizacion_bg(callback_ui=None):
    """Lanza la sincronización o verificación de red en segundo plano sin bloquear el hilo de Tkinter."""
    with _SYNC_LOCK:
        if _ESTADO_SYNC["sincronizando"]:
            return
        _ESTADO_SYNC["sincronizando"] = True
    threading.Thread(target=_trabajador_sync_bg, args=(callback_ui,), daemon=True).start()
