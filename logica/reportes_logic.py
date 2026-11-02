"""Contabilidad básica (gastos) y reportes / estadísticas para el dashboard."""
import csv
from datetime import date, timedelta

from database.conexion import consultar, consultar_uno, transaccion
from logica.productos_logic import _numero
from logica.seguridad import ROL_ADMIN, ROL_CAJERO, ErrorValidacion, Sesion, auditar, requiere_rol

CATEGORIAS_GASTO = ("Arriendo", "Servicios públicos", "Nómina", "Proveedores", "Transporte",
                    "Publicidad", "Impuestos", "Mantenimiento", "Otros")


# ---------- Gastos ----------
@requiere_rol(ROL_ADMIN)
def registrar_gasto(fecha, concepto, categoria, valor):
    concepto = concepto.strip()
    if not concepto:
        raise ErrorValidacion("Describe el concepto del gasto.")
    if categoria not in CATEGORIAS_GASTO:
        raise ErrorValidacion("Selecciona una categoría de gasto válida.")
    valor = _numero(valor, "Valor")
    if valor <= 0:
        raise ErrorValidacion("El valor debe ser mayor que cero.")
    with transaccion() as con:
        con.execute("INSERT INTO gastos (fecha, concepto, categoria, valor, id_usuario) VALUES (?,?,?,?,?)",
                    (fecha, concepto, categoria, valor, Sesion.id()))
        auditar("REGISTRAR_GASTO", f"{categoria}: {concepto} {valor:.0f}", con)


@requiere_rol(ROL_ADMIN)
def eliminar_gasto(id_gasto):
    with transaccion() as con:
        g = con.execute("SELECT concepto, valor FROM gastos WHERE id_gasto=?", (id_gasto,)).fetchone()
        if g:
            con.execute("DELETE FROM gastos WHERE id_gasto=?", (id_gasto,))
            auditar("ELIMINAR_GASTO", f"{g['concepto']} {g['valor']:.0f}", con)


@requiere_rol(ROL_ADMIN)
def listar_gastos(desde, hasta):
    return consultar("""SELECT g.*, u.username FROM gastos g JOIN usuarios u ON u.id_usuario=g.id_usuario
                        WHERE g.fecha BETWEEN ? AND ? ORDER BY g.fecha DESC, g.id_gasto DESC""", (desde, hasta))


@requiere_rol(ROL_ADMIN)
def estado_resultados(desde, hasta):
    v = consultar_uno(
        """SELECT COALESCE(SUM(f.subtotal),0) AS ventas_netas, COALESCE(SUM(f.iva),0) AS iva,
                  COALESCE(SUM(f.total),0) AS ventas_brutas, COUNT(*) AS facturas
           FROM facturas f WHERE f.estado='EMITIDA' AND date(f.fecha) BETWEEN ? AND ?""", (desde, hasta))
    c = consultar_uno(
        """SELECT COALESCE(SUM(d.costo_unitario * d.cantidad),0) AS costo
           FROM detalles_factura d JOIN facturas f ON f.id_factura=d.id_factura
           WHERE f.estado='EMITIDA' AND date(f.fecha) BETWEEN ? AND ?""", (desde, hasta))
    g = consultar("""SELECT categoria, SUM(valor) AS total FROM gastos WHERE fecha BETWEEN ? AND ?
                     GROUP BY categoria ORDER BY total DESC""", (desde, hasta))
    gastos = sum(x["total"] for x in g)
    utilidad_bruta = v["ventas_netas"] - c["costo"]
    return {**v, "costo_ventas": c["costo"], "utilidad_bruta": utilidad_bruta,
            "gastos": gastos, "gastos_por_categoria": g, "utilidad_neta": utilidad_bruta - gastos}


# ---------- Estadísticas / Dashboard ----------
@requiere_rol(ROL_ADMIN)
def kpis_dashboard():
    hoy = date.today()
    hoy_s = hoy.isoformat()
    ini_mes = hoy.replace(day=1).isoformat()
    fin_mes_ant_d = hoy.replace(day=1) - timedelta(days=1)
    ini_mes_ant, fin_mes_ant = fin_mes_ant_d.replace(day=1).isoformat(), fin_mes_ant_d.isoformat()

    resultado = estado_resultados(ini_mes, hoy_s)
    with transaccion() as con:
        v_hoy = con.execute(
            "SELECT COALESCE(SUM(total),0) AS t, COUNT(*) AS n FROM facturas WHERE estado='EMITIDA' AND date(fecha)=?",
            (hoy_s,),
        ).fetchone()
        v_ant = con.execute(
            "SELECT COALESCE(SUM(total),0) AS t FROM facturas WHERE estado='EMITIDA' AND date(fecha) BETWEEN ? AND ?",
            (ini_mes_ant, fin_mes_ant),
        ).fetchone()
        inv = con.execute(
            """SELECT COUNT(*) AS productos, COALESCE(SUM(stock*costo),0) AS valor,
                      COALESCE(SUM(CASE WHEN stock <= stock_minimo THEN 1 ELSE 0 END), 0) AS bajos
               FROM productos WHERE activo=1"""
        ).fetchone()

    v_mes_t, v_mes_n = resultado["ventas_brutas"], resultado["facturas"]
    variacion = ((v_mes_t - v_ant["t"]) / v_ant["t"] * 100) if v_ant["t"] else None
    return {
        "ventas_hoy": v_hoy["t"], "facturas_hoy": v_hoy["n"],
        "ventas_mes": v_mes_t, "facturas_mes": v_mes_n, "variacion_mes": variacion,
        "ticket_promedio": (v_mes_t / v_mes_n) if v_mes_n else 0,
        "utilidad_mes": resultado["utilidad_neta"], "gastos_mes": resultado["gastos"],
        "productos": inv["productos"], "valor_inventario": inv["valor"], "stock_bajo": inv["bajos"],
    }


@requiere_rol(ROL_ADMIN)
def ventas_por_dia(dias=14):
    desde = date.today() - timedelta(days=dias - 1)
    filas = {f["dia"]: f["total"] for f in consultar(
        """SELECT date(fecha) AS dia, SUM(total) AS total FROM facturas
           WHERE estado='EMITIDA' AND date(fecha) >= ? GROUP BY date(fecha)""", (desde.isoformat(),))}
    return [((desde + timedelta(days=i)), filas.get((desde + timedelta(days=i)).isoformat(), 0)) for i in range(dias)]


@requiere_rol(ROL_ADMIN)
def top_productos(desde, hasta, limite=7):
    return consultar(
        """SELECT d.descripcion AS nombre, SUM(d.cantidad) AS unidades, SUM(d.cantidad*d.precio_unitario) AS total
           FROM detalles_factura d JOIN facturas f ON f.id_factura=d.id_factura
           WHERE f.estado='EMITIDA' AND date(f.fecha) BETWEEN ? AND ?
           GROUP BY d.id_producto ORDER BY total DESC LIMIT ?""", (desde, hasta, limite))


@requiere_rol(ROL_ADMIN)
def ventas_por_categoria(desde, hasta):
    return consultar(
        """SELECT c.nombre, SUM(d.cantidad*d.precio_unitario) AS total
           FROM detalles_factura d JOIN facturas f ON f.id_factura=d.id_factura
           JOIN productos p ON p.id_producto=d.id_producto JOIN categorias c ON c.id_categoria=p.id_categoria
           WHERE f.estado='EMITIDA' AND date(f.fecha) BETWEEN ? AND ?
           GROUP BY c.id_categoria ORDER BY total DESC""", (desde, hasta))


@requiere_rol(ROL_ADMIN)
def ventas_por_metodo(desde, hasta):
    return consultar("""SELECT metodo_pago, COUNT(*) AS n, SUM(total) AS total FROM facturas
                        WHERE estado='EMITIDA' AND date(fecha) BETWEEN ? AND ? GROUP BY metodo_pago""", (desde, hasta))


@requiere_rol(ROL_ADMIN)
def ventas_por_hora(desde, hasta):
    return consultar("""SELECT CAST(strftime('%H', fecha) AS INTEGER) AS hora, COUNT(*) AS n, SUM(total) AS total
                        FROM facturas WHERE estado='EMITIDA' AND date(fecha) BETWEEN ? AND ?
                        GROUP BY hora ORDER BY hora""", (desde, hasta))


@requiere_rol(ROL_ADMIN)
def ventas_por_cajero(desde, hasta):
    return consultar("""SELECT u.nombre_completo AS cajero, COUNT(*) AS n, SUM(f.total) AS total
                        FROM facturas f JOIN usuarios u ON u.id_usuario=f.id_usuario
                        WHERE f.estado='EMITIDA' AND date(f.fecha) BETWEEN ? AND ?
                        GROUP BY u.id_usuario ORDER BY total DESC""", (desde, hasta))


@requiere_rol(ROL_ADMIN)
def productos_stock_bajo():
    return consultar("""SELECT codigo, nombre, stock, stock_minimo FROM productos
                        WHERE activo=1 AND stock <= stock_minimo ORDER BY stock ASC""")


@requiere_rol(ROL_ADMIN, ROL_CAJERO)
def resumen_cajero_hoy():
    hoy = date.today().isoformat()
    return consultar("""SELECT metodo_pago, COUNT(*) AS n, SUM(total) AS total FROM facturas
                        WHERE estado='EMITIDA' AND id_usuario=? AND date(fecha)=? GROUP BY metodo_pago""",
                     (Sesion.id(), hoy))


@requiere_rol(ROL_ADMIN)
def ultimas_auditorias(limite=200):
    return consultar("""SELECT a.fecha, COALESCE(u.username,'—') AS usuario, a.accion, a.detalle
                        FROM auditoria a LEFT JOIN usuarios u ON u.id_usuario=a.id_usuario
                        ORDER BY a.id_auditoria DESC LIMIT ?""", (limite,))


def _celda_csv_segura(valor):
    if isinstance(valor, str) and valor and valor[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + valor
    return valor


@requiere_rol(ROL_ADMIN)
def exportar_csv(ruta, filas, columnas):
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([c[1] for c in columnas])
        for fila in filas:
            w.writerow([_celda_csv_segura(fila.get(c[0], "")) for c in columnas])
    auditar("EXPORTAR_REPORTE", ruta)
