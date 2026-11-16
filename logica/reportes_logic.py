"""Contabilidad básica (gastos) y reportes / estadísticas para el dashboard."""
import csv
from datetime import date, timedelta

from database.conexion import consultar, consultar_uno, transaccion
from logica.productos_logic import _numero
from logica.seguridad import ROL_ADMIN, ROL_CAJERO, ErrorValidacion, Sesion, auditar, requiere_rol

CATEGORIAS_GASTO = (
    "Arriendo",
    "Servicios públicos (Agua/Luz/Gas/Internet)",
    "Servicios públicos",
    "Nómina y seguridad social",
    "Nómina",
    "Proveedores y mercancía",
    "Proveedores",
    "Transporte y fletes",
    "Transporte",
    "Publicidad y marketing",
    "Publicidad",
    "Impuestos y tasas",
    "Impuestos",
    "Mantenimiento y suministros",
    "Mantenimiento",
    "Gastos bancarios y comisiones",
    "Otros",
)

CATEGORIAS_GASTO_UI = (
    "Servicios públicos (Agua/Luz/Gas/Internet)",
    "Arriendo",
    "Nómina y seguridad social",
    "Proveedores y mercancía",
    "Transporte y fletes",
    "Mantenimiento y suministros",
    "Impuestos y tasas",
    "Publicidad y marketing",
    "Gastos bancarios y comisiones",
    "Otros",
)

METODOS_PAGO_GASTO = ("Efectivo", "Transferencia", "Nequi / Daviplata", "Tarjeta")
ESTADOS_GASTO = ("PAGADO", "PENDIENTE")


# ---------- Gastos y Cuentas por Pagar ----------
@requiere_rol(ROL_ADMIN)
def registrar_gasto(
    fecha,
    concepto,
    categoria,
    valor,
    proveedor="",
    metodo_pago="Efectivo",
    comprobante="",
    estado="PAGADO",
    fecha_vencimiento=None,
    es_gasto_fijo=False,
    dias_anticipacion=5,
):
    concepto = (concepto or "").strip()
    proveedor = (proveedor or "").strip()
    comprobante = (comprobante or "").strip()
    estado = (estado or "PAGADO").strip().upper()
    metodo_pago = (metodo_pago or "Efectivo").strip()

    if not concepto:
        raise ErrorValidacion("Describe el concepto del gasto o servicio.")
    if categoria not in CATEGORIAS_GASTO and categoria not in CATEGORIAS_GASTO_UI:
        raise ErrorValidacion("Selecciona una categoría de gasto válida.")
    if metodo_pago not in METODOS_PAGO_GASTO:
        metodo_pago = "Efectivo"
    if estado not in ESTADOS_GASTO:
        estado = "PAGADO"

    valor = _numero(valor, "Valor")
    if valor <= 0:
        raise ErrorValidacion("El valor debe ser mayor que cero.")

    with transaccion() as con:
        con.execute(
            """INSERT INTO gastos
               (fecha, concepto, categoria, valor, proveedor, metodo_pago, comprobante, estado, fecha_vencimiento, id_usuario)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                fecha,
                concepto,
                categoria,
                valor,
                proveedor,
                metodo_pago,
                comprobante,
                estado,
                (fecha_vencimiento or "").strip() or None,
                Sesion.id(),
            ),
        )
        auditar("REGISTRAR_GASTO", f"{categoria} [{estado}]: {concepto} {valor:.0f}", con)

        if es_gasto_fijo:
            try:
                dia_fijo = int(str(fecha).split("-")[2][:2])
            except Exception:
                dia_fijo = date.today().day
            dia_fijo = max(1, min(31, dia_fijo))
            mes_pagado = str(fecha)[:7] if estado == "PAGADO" else ""
            con.execute(
                """INSERT INTO gastos_fijos
                   (concepto, descripcion, categoria, proveedor, valor_estimado, dia_pago, dias_anticipacion, metodo_pago, ultimo_mes_pagado)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    concepto,
                    f"Soporte: {comprobante}" if comprobante else "",
                    categoria,
                    proveedor,
                    valor,
                    dia_fijo,
                    int(dias_anticipacion or 5),
                    metodo_pago,
                    mes_pagado,
                ),
            )


@requiere_rol(ROL_ADMIN)
def marcar_gasto_pagado(id_gasto, metodo_pago="Efectivo"):
    """Marca una cuenta por pagar ('PENDIENTE') como 'PAGADO' y actualiza su medio de pago."""
    if metodo_pago not in METODOS_PAGO_GASTO:
        metodo_pago = "Efectivo"
    with transaccion() as con:
        g = con.execute("SELECT concepto, valor, estado FROM gastos WHERE id_gasto=?", (id_gasto,)).fetchone()
        if not g:
            raise ErrorValidacion("El gasto seleccionado no existe.")
        if g["estado"] == "PAGADO":
            raise ErrorValidacion("Este gasto ya figura como PAGADO.")
        con.execute(
            "UPDATE gastos SET estado='PAGADO', metodo_pago=? WHERE id_gasto=?",
            (metodo_pago, id_gasto),
        )
        auditar("PAGAR_CUENTA_PENDIENTE", f"{g['concepto']} ({metodo_pago}) {g['valor']:.0f}", con)


@requiere_rol(ROL_ADMIN)
def eliminar_gasto(id_gasto):
    with transaccion() as con:
        g = con.execute("SELECT concepto, valor FROM gastos WHERE id_gasto=?", (id_gasto,)).fetchone()
        if g:
            con.execute("DELETE FROM gastos WHERE id_gasto=?", (id_gasto,))
            auditar("ELIMINAR_GASTO", f"{g['concepto']} {g['valor']:.0f}", con)


@requiere_rol(ROL_ADMIN)
def listar_gastos(desde, hasta, categoria=None, estado=None, texto=""):
    sql = """SELECT g.*, u.username
             FROM gastos g
             JOIN usuarios u ON u.id_usuario = g.id_usuario
             WHERE (g.fecha BETWEEN ? AND ? OR COALESCE(g.estado, 'PAGADO') = 'PENDIENTE')"""
    params = [desde, hasta]
    if categoria and categoria != "Todas las categorías":
        sql += " AND g.categoria = ?"
        params.append(categoria)
    if estado and estado in ESTADOS_GASTO:
        sql += " AND COALESCE(g.estado, 'PAGADO') = ?"
        params.append(estado)
    if texto:
        t = f"%{texto.strip()}%"
        sql += " AND (g.concepto LIKE ? OR COALESCE(g.proveedor,'') LIKE ? OR COALESCE(g.comprobante,'') LIKE ?)"
        params.extend([t, t, t])
    sql += " ORDER BY CASE WHEN COALESCE(g.estado,'PAGADO')='PENDIENTE' THEN 0 ELSE 1 END, g.fecha DESC, g.id_gasto DESC"
    return consultar(sql, params)


@requiere_rol(ROL_ADMIN)
def estado_resultados(desde, hasta):
    v = consultar_uno(
        """SELECT COALESCE(SUM(f.subtotal),0) AS ventas_netas,
                  COALESCE(SUM(f.iva),0) AS iva,
                  COALESCE(SUM(f.total),0) AS ventas_brutas,
                  COUNT(*) AS facturas
           FROM facturas f
           WHERE f.estado='EMITIDA' AND date(f.fecha) BETWEEN ? AND ?""",
        (desde, hasta),
    )
    c = consultar_uno(
        """SELECT COALESCE(SUM(d.costo_unitario * d.cantidad),0) AS costo
           FROM detalles_factura d
           JOIN facturas f ON f.id_factura=d.id_factura
           WHERE f.estado='EMITIDA' AND date(f.fecha) BETWEEN ? AND ?""",
        (desde, hasta),
    )
    g = consultar(
        """SELECT categoria,
                  COUNT(*) AS cantidad,
                  SUM(valor) AS total,
                  SUM(CASE WHEN COALESCE(estado,'PAGADO')='PAGADO' THEN valor ELSE 0 END) AS pagado,
                  SUM(CASE WHEN COALESCE(estado,'PAGADO')='PENDIENTE' THEN valor ELSE 0 END) AS pendiente
           FROM gastos
           WHERE (fecha BETWEEN ? AND ? OR COALESCE(estado,'PAGADO')='PENDIENTE')
           GROUP BY categoria
           ORDER BY total DESC""",
        (desde, hasta),
    )
    res_estados = consultar_uno(
        """SELECT COALESCE(SUM(CASE WHEN COALESCE(estado,'PAGADO')='PAGADO' THEN valor ELSE 0 END), 0) AS gastos_pagados,
                  COALESCE(SUM(CASE WHEN COALESCE(estado,'PAGADO')='PENDIENTE' THEN valor ELSE 0 END), 0) AS gastos_pendientes,
                  COALESCE(SUM(CASE WHEN COALESCE(estado,'PAGADO')='PENDIENTE' THEN 1 ELSE 0 END), 0) AS conteo_pendientes
           FROM gastos
           WHERE (fecha BETWEEN ? AND ? OR COALESCE(estado,'PAGADO')='PENDIENTE')""",
        (desde, hasta),
    )

    gastos = sum(x["total"] for x in g)
    ventas_netas = float(v["ventas_netas"] or 0)
    costo_ventas = float(c["costo"] or 0)
    utilidad_bruta = ventas_netas - costo_ventas
    utilidad_neta = utilidad_bruta - gastos

    margen_bruto_pct = (utilidad_bruta / ventas_netas * 100) if ventas_netas > 0 else 0.0
    margen_neto_pct = (utilidad_neta / ventas_netas * 100) if ventas_netas > 0 else 0.0

    # Punto de equilibrio: cuánto necesita vender (sin IVA) para cubrir sus gastos operativos con su margen actual
    if margen_bruto_pct > 0:
        punto_equilibrio = gastos / (margen_bruto_pct / 100.0)
    else:
        punto_equilibrio = gastos
    cobertura_equilibrio_pct = (
        (ventas_netas / punto_equilibrio * 100.0) if punto_equilibrio > 0 else (100.0 if gastos == 0 else 0.0)
    )

    for item in g:
        item["porcentaje"] = (item["total"] / gastos * 100.0) if gastos > 0 else 0.0

    return {
        **v,
        "costo_ventas": costo_ventas,
        "utilidad_bruta": utilidad_bruta,
        "margen_bruto_pct": margen_bruto_pct,
        "gastos": gastos,
        "gastos_pagados": float(res_estados["gastos_pagados"] or 0),
        "gastos_pendientes": float(res_estados["gastos_pendientes"] or 0),
        "conteo_pendientes": int(res_estados["conteo_pendientes"] or 0),
        "gastos_por_categoria": g,
        "utilidad_neta": utilidad_neta,
        "margen_neto_pct": margen_neto_pct,
        "punto_equilibrio": punto_equilibrio,
        "cobertura_equilibrio_pct": cobertura_equilibrio_pct,
    }


@requiere_rol(ROL_ADMIN)
def flujo_caja_y_bancos(desde, hasta) -> dict:
    """Cruza `facturas` ('EMITIDA') y `gastos` ('PAGADO') agrupados por `metodo_pago`
    para calcular el efectivo físico real en cajón vs saldo en cuentas bancarias / billeteras."""
    ing_filas = consultar(
        """SELECT metodo_pago, COUNT(*) AS facturas, COALESCE(SUM(total), 0) AS ingresos
           FROM facturas
           WHERE estado = 'EMITIDA' AND date(fecha) BETWEEN ? AND ?
           GROUP BY metodo_pago""",
        (desde, hasta),
    )
    egr_filas = consultar(
        """SELECT COALESCE(metodo_pago, 'Efectivo') AS metodo_pago,
                  COUNT(*) AS recibos,
                  COALESCE(SUM(valor), 0) AS egresos
           FROM gastos
           WHERE COALESCE(estado, 'PAGADO') = 'PAGADO' AND fecha BETWEEN ? AND ?
           GROUP BY COALESCE(metodo_pago, 'Efectivo')""",
        (desde, hasta),
    )

    ing_map = {r["metodo_pago"]: float(r["ingresos"] or 0) for r in ing_filas}
    egr_map = {r["metodo_pago"]: float(r["egresos"] or 0) for r in egr_filas}

    metodos = list(METODOS_PAGO_GASTO)
    for m in list(ing_map.keys()) + list(egr_map.keys()):
        if m not in metodos:
            metodos.append(m)

    desglose = []
    for m in metodos:
        ing = ing_map.get(m, 0.0)
        egr = egr_map.get(m, 0.0)
        desglose.append({
            "metodo_pago": m,
            "ingresos": ing,
            "egresos": egr,
            "saldo_neto": ing - egr,
        })

    ing_efectivo = ing_map.get("Efectivo", 0.0)
    egr_efectivo = egr_map.get("Efectivo", 0.0)
    saldo_efectivo = ing_efectivo - egr_efectivo

    ing_bancos = sum(v for k, v in ing_map.items() if k != "Efectivo")
    egr_bancos = sum(v for k, v in egr_map.items() if k != "Efectivo")
    saldo_bancos = ing_bancos - egr_bancos

    return {
        "ingresos_efectivo": ing_efectivo,
        "egresos_efectivo": egr_efectivo,
        "saldo_efectivo": saldo_efectivo,
        "ingresos_bancos": ing_bancos,
        "egresos_bancos": egr_bancos,
        "saldo_bancos": saldo_bancos,
        "saldo_total_tesoreria": saldo_efectivo + saldo_bancos,
        "desglose_por_metodo": desglose,
    }


@requiere_rol(ROL_ADMIN)
def resumen_iva_dian(desde, hasta) -> list[dict]:
    """Cruza `detalles_factura` con `facturas` ('EMITIDA') para desglosar la base gravable
    y el IVA generado por cada tarifa impositiva (0%, 5%, 19%)."""
    filas = consultar(
        """SELECT d.iva_porcentaje AS tarifa,
                  COALESCE(SUM(d.cantidad), 0) AS unidades,
                  COALESCE(SUM(d.precio_unitario * d.cantidad), 0) AS total_con_iva
           FROM detalles_factura d
           JOIN facturas f ON f.id_factura = d.id_factura
           WHERE f.estado = 'EMITIDA' AND date(f.fecha) BETWEEN ? AND ?
           GROUP BY d.iva_porcentaje
           ORDER BY d.iva_porcentaje ASC""",
        (desde, hasta),
    )
    resultado = []
    for r in filas:
        tarifa = float(r["tarifa"] or 0)
        total = float(r["total_con_iva"] or 0)
        base = total / (1.0 + tarifa / 100.0) if tarifa > 0 else total
        iva_gen = total - base
        resultado.append({
            "tarifa": f"{tarifa:.0f}%",
            "unidades": int(r["unidades"] or 0),
            "base_gravable": round(base, 2),
            "iva_generado": round(iva_gen, 2),
            "total_facturado": round(total, 2),
        })
    return resultado


# ---------- Cuentas Fijas Mensuales y Recordatorios de Pago ----------
def _calcular_estado_gasto_fijo(fila: dict, hoy: date | None = None) -> dict:
    """Calcula el estado del gasto fijo en el mes actual (PAGADO_MES, VENCIDO, PROXIMO, PROGRAMADO)."""
    import calendar

    hoy = hoy or date.today()
    mes_actual = hoy.strftime("%Y-%m")
    ultimo_dia_mes = calendar.monthrange(hoy.year, hoy.month)[1]
    dia_efectivo = min(int(fila["dia_pago"]), ultimo_dia_mes)
    fecha_pago_mes = date(hoy.year, hoy.month, dia_efectivo)
    dias_restantes = (fecha_pago_mes - hoy).days
    anticipacion = int(fila.get("dias_anticipacion") or 5)

    pagado_este_mes = (fila.get("ultimo_mes_pagado") or "") == mes_actual
    if pagado_este_mes:
        estado_mes = "PAGADO_MES"
        etiqueta = f"Pagado ({mes_actual})"
        urgencia = 3
    elif dias_restantes < 0:
        estado_mes = "VENCIDO"
        etiqueta = f"Vencido hace {abs(dias_restantes)} día(s) (Día {dia_efectivo})"
        urgencia = 0
    elif dias_restantes == 0:
        estado_mes = "PROXIMO"
        etiqueta = f"Vence HOY (Día {dia_efectivo})"
        urgencia = 1
    elif dias_restantes <= anticipacion:
        estado_mes = "PROXIMO"
        etiqueta = f"Vence en {dias_restantes} día(s) (Día {dia_efectivo})"
        urgencia = 1
    else:
        estado_mes = "PROGRAMADO"
        etiqueta = f"Faltan {dias_restantes} días (Día {dia_efectivo})"
        urgencia = 2

    return {
        **fila,
        "fecha_pago_mes": fecha_pago_mes.isoformat(),
        "dias_restantes": dias_restantes,
        "estado_mes": estado_mes,
        "etiqueta_estado": etiqueta,
        "urgencia": urgencia,
    }


@requiere_rol(ROL_ADMIN)
def guardar_gasto_fijo(
    concepto: str,
    categoria: str,
    valor_estimado,
    dia_pago,
    descripcion: str = "",
    proveedor: str = "",
    metodo_pago: str = "Transferencia",
    dias_anticipacion=5,
    id_gasto_fijo: int | None = None,
) -> int:
    concepto = (concepto or "").strip()
    descripcion = (descripcion or "").strip()
    proveedor = (proveedor or "").strip()
    metodo_pago = (metodo_pago or "Transferencia").strip()

    if not concepto:
        raise ErrorValidacion("Ingresa el nombre o concepto de la cuenta fija (ej. Arriendo, Internet, Luz).")
    if categoria not in CATEGORIAS_GASTO and categoria not in CATEGORIAS_GASTO_UI:
        raise ErrorValidacion("Selecciona una categoría válida para la cuenta fija.")
    if metodo_pago not in METODOS_PAGO_GASTO:
        metodo_pago = "Transferencia"

    valor = _numero(valor_estimado, "Valor mensual estimado")
    if valor <= 0:
        raise ErrorValidacion("El valor estimado debe ser mayor que cero.")
    dia = int(_numero(dia_pago, "Día de pago del mes", entero=True, minimo=1))
    if dia > 31:
        raise ErrorValidacion("El día de pago del mes debe estar entre 1 y 31.")
    anticip = int(_numero(dias_anticipacion or 5, "Días de aviso previo", entero=True, minimo=1))
    if anticip > 15:
        raise ErrorValidacion("Los días de aviso previo deben estar entre 1 y 15.")

    with transaccion() as con:
        if id_gasto_fijo:
            con.execute(
                """UPDATE gastos_fijos
                   SET concepto=?, descripcion=?, categoria=?, proveedor=?, valor_estimado=?,
                       dia_pago=?, dias_anticipacion=?, metodo_pago=?
                   WHERE id_gasto_fijo=?""",
                (concepto, descripcion, categoria, proveedor, valor, dia, anticip, metodo_pago, id_gasto_fijo),
            )
            auditar("EDITAR_GASTO_FIJO", f"{concepto} (día {dia})", con)
            return int(id_gasto_fijo)
        else:
            cur = con.execute(
                """INSERT INTO gastos_fijos
                   (concepto, descripcion, categoria, proveedor, valor_estimado, dia_pago, dias_anticipacion, metodo_pago)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (concepto, descripcion, categoria, proveedor, valor, dia, anticip, metodo_pago),
            )
            nuevo_id = int(cur.lastrowid)
            auditar("CREAR_GASTO_FIJO", f"{concepto} (día {dia}, ${valor:.0f})", con)
            return nuevo_id


@requiere_rol(ROL_ADMIN)
def listar_gastos_fijos(hoy: date | None = None) -> list[dict]:
    filas = consultar("SELECT * FROM gastos_fijos WHERE activo = 1 ORDER BY dia_pago ASC, id_gasto_fijo ASC")
    enriquecidas = [_calcular_estado_gasto_fijo(f, hoy=hoy) for f in filas]
    enriquecidas.sort(key=lambda x: (x["urgencia"], x["dia_pago"]))
    return enriquecidas


@requiere_rol(ROL_ADMIN)
def alertas_gastos_fijos(hoy: date | None = None) -> dict:
    """Devuelve las cuentas fijas y cuentas por pagar ('PENDIENTE') que están VENCIDAS o PRÓXIMAS a vencer."""
    hoy = hoy or date.today()
    todas = listar_gastos_fijos(hoy=hoy)
    vencidas = [f for f in todas if f["estado_mes"] == "VENCIDO"]
    proximas = [f for f in todas if f["estado_mes"] == "PROXIMO"]

    # También incluir recibos registrados en `gastos` con estado = 'PENDIENTE' cuya fecha esté cerca (<= 10 días) o vencida
    pendientes_bd = consultar("SELECT * FROM gastos WHERE COALESCE(estado, 'PAGADO') = 'PENDIENTE'")
    nombres_fijos = {f["concepto"].strip().lower() for f in todas}
    for p in pendientes_bd:
        if p["concepto"].strip().lower() in nombres_fijos:
            continue
        try:
            f_pago = date.fromisoformat(str(p["fecha"])[:10])
            dias_rest = (f_pago - hoy).days
        except Exception:
            dias_rest = 0
        if dias_rest < 0:
            vencidas.append({
                "concepto": p["concepto"],
                "valor_estimado": p["valor"],
                "estado_mes": "VENCIDO",
                "etiqueta_estado": f"Vencido ({p['fecha']})",
            })
        elif dias_rest <= 10:
            proximas.append({
                "concepto": p["concepto"],
                "valor_estimado": p["valor"],
                "estado_mes": "PROXIMO",
                "etiqueta_estado": f"Vence en {dias_rest} día(s) ({p['fecha']})" if dias_rest > 0 else "Vence HOY",
            })

    alertas = vencidas + proximas
    total_alerta = sum(float(x["valor_estimado"] or 0) for x in alertas)
    return {
        "hay_alertas": len(alertas) > 0,
        "cantidad_alertas": len(alertas),
        "vencidas": len(vencidas),
        "proximas": len(proximas),
        "total_estimado_alerta": total_alerta,
        "items": alertas,
    }


@requiere_rol(ROL_ADMIN)
def pagar_gasto_fijo_mes(id_gasto_fijo: int, valor_pagado=None, metodo_pago: str | None = None, comprobante: str = ""):
    """Registra el pago del mes actual de una cuenta fija:
    1) Inserta el egreso como 'PAGADO' en la tabla `gastos`.
    2) Actualiza `ultimo_mes_pagado = 'YYYY-MM'` en `gastos_fijos`."""
    hoy = date.today()
    mes_actual = hoy.strftime("%Y-%m")

    fijo = consultar_uno("SELECT * FROM gastos_fijos WHERE id_gasto_fijo = ? AND activo = 1", (id_gasto_fijo,))
    if not fijo:
        raise ErrorValidacion("La cuenta fija seleccionada no existe.")
    if (fijo.get("ultimo_mes_pagado") or "") == mes_actual:
        raise ErrorValidacion(f"La cuenta fija «{fijo['concepto']}» ya fue pagada en {mes_actual}.")

    monto = _numero(valor_pagado if valor_pagado not in (None, "") else fijo["valor_estimado"], "Valor pagado")
    if monto <= 0:
        raise ErrorValidacion("El valor pagado debe ser mayor que cero.")

    medio = (metodo_pago or fijo.get("metodo_pago") or "Transferencia").strip()
    if medio not in METODOS_PAGO_GASTO:
        medio = "Transferencia"

    detalle_concepto = fijo["concepto"]
    if fijo.get("descripcion"):
        detalle_concepto = f"{fijo['concepto']} ({fijo['descripcion']})"

    with transaccion() as con:
        con.execute(
            """INSERT INTO gastos
               (fecha, concepto, categoria, valor, proveedor, metodo_pago, comprobante, estado, id_usuario)
               VALUES (?,?,?,?,?,?,?,'PAGADO',?)""",
            (
                hoy.isoformat(),
                detalle_concepto,
                fijo["categoria"],
                monto,
                fijo.get("proveedor") or "",
                medio,
                (comprobante or "").strip() or f"FIJO-{mes_actual}",
                Sesion.id(),
            ),
        )
        con.execute(
            "UPDATE gastos_fijos SET ultimo_mes_pagado = ? WHERE id_gasto_fijo = ?",
            (mes_actual, id_gasto_fijo),
        )
        auditar("PAGAR_GASTO_FIJO_MES", f"{fijo['concepto']} ({mes_actual}) ${monto:.0f}", con)


@requiere_rol(ROL_ADMIN)
def eliminar_gasto_fijo(id_gasto_fijo: int):
    with transaccion() as con:
        f = con.execute("SELECT concepto FROM gastos_fijos WHERE id_gasto_fijo = ?", (id_gasto_fijo,)).fetchone()
        if f:
            con.execute("DELETE FROM gastos_fijos WHERE id_gasto_fijo = ?", (id_gasto_fijo,))
            auditar("ELIMINAR_GASTO_FIJO", f["concepto"], con)


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
