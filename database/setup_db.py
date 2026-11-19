"""Creación automática de la estructura de la base de datos.

Se ejecuta en cada arranque: si las tablas ya existen no hace nada,
si es la primera vez crea todo y carga los datos iniciales.
"""
import json

from database.conexion import transaccion

ESQUEMA = """
CREATE TABLE IF NOT EXISTS empresa (
    id_empresa      INTEGER PRIMARY KEY CHECK (id_empresa = 1),
    nit             TEXT NOT NULL,
    razon_social    TEXT NOT NULL,
    direccion       TEXT,
    telefono        TEXT,
    correo          TEXT,
    regimen         TEXT DEFAULT 'Responsable de IVA',
    prefijo_factura TEXT DEFAULT 'FV',
    creado_en       TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS roles (
    id_rol  INTEGER PRIMARY KEY,
    nombre  TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario        INTEGER PRIMARY KEY AUTOINCREMENT,
    username          TEXT UNIQUE NOT NULL COLLATE NOCASE,
    nombre_completo   TEXT NOT NULL,
    password_hash     TEXT NOT NULL,
    id_rol            INTEGER NOT NULL REFERENCES roles(id_rol),
    activo            INTEGER NOT NULL DEFAULT 1,
    intentos_fallidos INTEGER NOT NULL DEFAULT 0,
    bloqueado_hasta   TEXT,
    ultimo_acceso     TEXT,
    creado_en         TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS preguntas_seguridad (
    id_pregunta    INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario     INTEGER NOT NULL REFERENCES usuarios(id_usuario),
    orden          INTEGER NOT NULL CHECK (orden IN (1, 2)),
    pregunta       TEXT NOT NULL,
    respuesta_hash TEXT NOT NULL,
    UNIQUE(id_usuario, orden)
);

CREATE TABLE IF NOT EXISTS categorias (
    id_categoria    INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT UNIQUE NOT NULL COLLATE NOCASE,
    descripcion     TEXT,
    iva_porcentaje  REAL NOT NULL DEFAULT 19 CHECK (iva_porcentaje >= 0 AND iva_porcentaje <= 100)
);

CREATE TABLE IF NOT EXISTS productos (
    id_producto   INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo        TEXT UNIQUE NOT NULL,
    nombre        TEXT NOT NULL,
    id_categoria  INTEGER NOT NULL REFERENCES categorias(id_categoria),
    costo         REAL NOT NULL DEFAULT 0 CHECK (costo >= 0),
    precio        REAL NOT NULL CHECK (precio >= 0),
    stock         INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    stock_minimo  INTEGER NOT NULL DEFAULT 5 CHECK (stock_minimo >= 0),
    activo        INTEGER NOT NULL DEFAULT 1,
    creado_en     TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS movimientos_inventario (
    id_movimiento INTEGER PRIMARY KEY AUTOINCREMENT,
    id_producto   INTEGER NOT NULL REFERENCES productos(id_producto),
    tipo          TEXT NOT NULL CHECK (tipo IN ('ENTRADA','VENTA','ANULACION')),
    cantidad      INTEGER NOT NULL,
    stock_final   INTEGER NOT NULL,
    referencia    TEXT,
    id_usuario    INTEGER NOT NULL REFERENCES usuarios(id_usuario),
    fecha         TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id     INTEGER NOT NULL REFERENCES productos(id_producto),
    movement_type  TEXT NOT NULL CHECK (movement_type IN ('ENTRADA', 'SALIDA_MERMA', 'AJUSTE_CONTEO', 'VENTA', 'DEVOLUCION')),
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    previous_stock INTEGER NOT NULL,
    new_stock      INTEGER NOT NULL,
    reason         TEXT DEFAULT '',
    user_id        INTEGER NOT NULL REFERENCES usuarios(id_usuario),
    created_at     TEXT DEFAULT (datetime('now','localtime')),
    synced         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sync_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name  TEXT NOT NULL,
    record_id   INTEGER NOT NULL,
    operation   TEXT NOT NULL DEFAULT 'INSERT',
    payload     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'SYNCED', 'FAILED')),
    created_at  TEXT DEFAULT (datetime('now','localtime')),
    synced_at   TEXT
);

CREATE TABLE IF NOT EXISTS facturas (
    id_factura    INTEGER PRIMARY KEY AUTOINCREMENT,
    numero        TEXT UNIQUE NOT NULL,
    fecha         TEXT DEFAULT (datetime('now','localtime')),
    cliente_doc   TEXT DEFAULT '222222222222',
    cliente_nombre TEXT DEFAULT 'Consumidor final',
    subtotal      REAL NOT NULL,
    iva           REAL NOT NULL,
    total         REAL NOT NULL,
    metodo_pago   TEXT NOT NULL DEFAULT 'Efectivo',
    recibido      REAL NOT NULL DEFAULT 0,
    estado        TEXT NOT NULL DEFAULT 'EMITIDA' CHECK (estado IN ('EMITIDA','ANULADA')),
    id_usuario    INTEGER NOT NULL REFERENCES usuarios(id_usuario)
);

CREATE TABLE IF NOT EXISTS detalles_factura (
    id_detalle      INTEGER PRIMARY KEY AUTOINCREMENT,
    id_factura      INTEGER NOT NULL REFERENCES facturas(id_factura),
    id_producto     INTEGER NOT NULL REFERENCES productos(id_producto),
    descripcion     TEXT NOT NULL,
    cantidad        INTEGER NOT NULL CHECK (cantidad > 0),
    precio_unitario REAL NOT NULL,
    iva_porcentaje  REAL NOT NULL,
    costo_unitario  REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS gastos (
    id_gasto          INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha             TEXT NOT NULL,
    concepto          TEXT NOT NULL,
    categoria         TEXT NOT NULL,
    valor             REAL NOT NULL CHECK (valor > 0),
    proveedor         TEXT DEFAULT '',
    metodo_pago       TEXT DEFAULT 'Efectivo',
    comprobante       TEXT DEFAULT '',
    estado            TEXT NOT NULL DEFAULT 'PAGADO' CHECK (estado IN ('PAGADO', 'PENDIENTE')),
    fecha_vencimiento TEXT,
    id_usuario        INTEGER NOT NULL REFERENCES usuarios(id_usuario),
    creado_en         TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS gastos_fijos (
    id_gasto_fijo     INTEGER PRIMARY KEY AUTOINCREMENT,
    concepto          TEXT NOT NULL,
    descripcion       TEXT DEFAULT '',
    categoria         TEXT NOT NULL,
    proveedor         TEXT DEFAULT '',
    valor_estimado    REAL NOT NULL CHECK (valor_estimado > 0),
    dia_pago          INTEGER NOT NULL CHECK (dia_pago >= 1 AND dia_pago <= 31),
    dias_anticipacion INTEGER NOT NULL DEFAULT 5 CHECK (dias_anticipacion >= 1 AND dias_anticipacion <= 15),
    metodo_pago       TEXT DEFAULT 'Transferencia',
    ultimo_mes_pagado TEXT DEFAULT '',
    activo            INTEGER NOT NULL DEFAULT 1,
    creado_en         TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha        TEXT DEFAULT (datetime('now','localtime')),
    id_usuario   INTEGER,
    accion       TEXT NOT NULL,
    detalle      TEXT
);

CREATE TABLE IF NOT EXISTS licencia_sistema (
    id_licencia      INTEGER PRIMARY KEY CHECK (id_licencia = 1),
    email_cuenta     TEXT NOT NULL,
    hw_id_hash       TEXT NOT NULL,
    plan_adquirido   TEXT NOT NULL CHECK (plan_adquirido IN ('basico', 'standart', 'ultra', 'pro')),
    firma_integridad TEXT NOT NULL,
    activado_en      TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_facturas_fecha ON facturas(fecha);
CREATE INDEX IF NOT EXISTS idx_detalles_factura ON detalles_factura(id_factura);
CREATE INDEX IF NOT EXISTS idx_mov_producto ON movimientos_inventario(id_producto);
CREATE INDEX IF NOT EXISTS idx_inv_mov_product ON inventory_movements(product_id);
CREATE INDEX IF NOT EXISTS idx_inv_mov_created ON inventory_movements(created_at);
CREATE INDEX IF NOT EXISTS idx_inv_mov_created_desc ON inventory_movements(created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_inv_mov_type ON inventory_movements(movement_type);
CREATE INDEX IF NOT EXISTS idx_productos_activo_stock ON productos(activo, stock, stock_minimo);
CREATE INDEX IF NOT EXISTS idx_sync_queue_status ON sync_queue(status);
CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos(fecha);

INSERT OR IGNORE INTO roles (id_rol, nombre) VALUES (1, 'administrador'), (2, 'cajero');
"""

# Esquema equivalente en PostgreSQL (Neon.tech) para sincronización de Kardex
ESQUEMA_POSTGRES_NEON = """
CREATE TABLE IF NOT EXISTS inventory_movements (
    id             BIGSERIAL PRIMARY KEY,
    empresa_nit    TEXT,
    local_id       INTEGER,
    product_id     INTEGER NOT NULL,
    sku            TEXT,
    movement_type  TEXT NOT NULL CHECK (movement_type IN ('ENTRADA', 'SALIDA_MERMA', 'AJUSTE_CONTEO', 'VENTA', 'DEVOLUCION')),
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    previous_stock INTEGER NOT NULL,
    new_stock      INTEGER NOT NULL,
    reason         TEXT DEFAULT '',
    user_id        INTEGER NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pg_inv_mov_product ON inventory_movements(product_id);
CREATE INDEX IF NOT EXISTS idx_pg_inv_mov_created ON inventory_movements(created_at);
CREATE INDEX IF NOT EXISTS idx_pg_inv_mov_type ON inventory_movements(movement_type);
"""

# Categorías iniciales según el régimen de IVA colombiano.
CATEGORIAS_INICIALES = [
    ("Canasta familiar", "Leche, huevos, arroz, frutas, verduras y demás productos exentos", 0),
    ("Alimentos procesados", "Embutidos, café, chocolate, harinas y similares (tarifa diferencial)", 5),
    ("Abarrotes", "Productos de despensa con tarifa general", 19),
    ("Bebidas", "Gaseosas, jugos y bebidas en general", 19),
    ("Aseo y hogar", "Productos de limpieza y cuidado del hogar", 19),
    ("Cuidado personal", "Higiene y cuidado personal", 19),
    ("General", "Otros productos con tarifa general", 19),
]


def inicializar_base_datos():
    from logica.respaldo import restaurar_si_falta
    restaurar_si_falta()
    with transaccion() as con:
        con.executescript(ESQUEMA)
        # Migración automática si licencia_sistema tenía un CHECK antiguo sin 'ultra'
        info_lic = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='licencia_sistema'"
        ).fetchone()
        if info_lic and info_lic[0] and "'ultra'" not in info_lic[0]:
            fila_ant = con.execute("SELECT * FROM licencia_sistema WHERE id_licencia = 1").fetchone()
            con.execute("DROP TABLE licencia_sistema")
            con.executescript(
                """CREATE TABLE IF NOT EXISTS licencia_sistema (
                    id_licencia      INTEGER PRIMARY KEY CHECK (id_licencia = 1),
                    email_cuenta     TEXT NOT NULL,
                    hw_id_hash       TEXT NOT NULL,
                    plan_adquirido   TEXT NOT NULL CHECK (plan_adquirido IN ('basico', 'standart', 'ultra', 'pro')),
                    firma_integridad TEXT NOT NULL,
                    activado_en      TEXT DEFAULT (datetime('now','localtime'))
                );"""
            )
            if fila_ant:
                con.execute(
                    """INSERT INTO licencia_sistema (id_licencia, email_cuenta, hw_id_hash, plan_adquirido, firma_integridad, activado_en)
                       VALUES (1, ?, ?, ?, ?, ?)""",
                    (
                        fila_ant["email_cuenta"],
                        fila_ant["hw_id_hash"],
                        fila_ant["plan_adquirido"],
                        fila_ant["firma_integridad"],
                        fila_ant["activado_en"],
                    ),
                )

        # Migración automática de nuevas columnas contables en la tabla gastos
        cols_gastos = {
            r[1] for r in con.execute("PRAGMA table_info(gastos)").fetchall()
        }
        for col_sql, nombre_col in (
            ("ALTER TABLE gastos ADD COLUMN proveedor TEXT DEFAULT ''", "proveedor"),
            ("ALTER TABLE gastos ADD COLUMN metodo_pago TEXT DEFAULT 'Efectivo'", "metodo_pago"),
            ("ALTER TABLE gastos ADD COLUMN comprobante TEXT DEFAULT ''", "comprobante"),
            ("ALTER TABLE gastos ADD COLUMN estado TEXT NOT NULL DEFAULT 'PAGADO'", "estado"),
            ("ALTER TABLE gastos ADD COLUMN fecha_vencimiento TEXT", "fecha_vencimiento"),
        ):
            if nombre_col not in cols_gastos:
                con.execute(col_sql)

        # Migración automática de columnas en inventory_movements (por compatibilidad)
        cols_inv = {
            r[1] for r in con.execute("PRAGMA table_info(inventory_movements)").fetchall()
        }
        if "synced" not in cols_inv:
            con.execute("ALTER TABLE inventory_movements ADD COLUMN synced INTEGER NOT NULL DEFAULT 0")

        # Migración segura de movimientos históricos desde movimientos_inventario hacia inventory_movements (Kardex)
        if con.execute("SELECT COUNT(*) FROM inventory_movements").fetchone()[0] == 0:
            antiguos = con.execute(
                """SELECT m.id_movimiento, m.id_producto, m.tipo, m.cantidad, m.stock_final,
                          COALESCE(m.referencia, '') AS referencia, m.id_usuario, m.fecha,
                          COALESCE(p.codigo, '') AS sku
                   FROM movimientos_inventario m
                   LEFT JOIN productos p ON p.id_producto = m.id_producto
                   ORDER BY m.id_movimiento ASC"""
            ).fetchall()
            cola_vacia = con.execute("SELECT COUNT(*) FROM sync_queue").fetchone()[0] == 0
            for ant in antiguos:
                tipo_raw = (ant["tipo"] or "").strip().upper()
                if tipo_raw == "ANULACION":
                    m_type = "DEVOLUCION"
                elif tipo_raw in ("ENTRADA", "SALIDA_MERMA", "AJUSTE_CONTEO", "VENTA", "DEVOLUCION"):
                    m_type = tipo_raw
                else:
                    m_type = "AJUSTE_CONTEO"
                cant_raw = int(ant["cantidad"] or 0)
                qty = max(1, abs(cant_raw))
                new_stock = int(ant["stock_final"] or 0)
                prev_stock = max(0, new_stock - cant_raw)
                reason = ant["referencia"] or ""
                created_at = ant["fecha"]
                cur = con.execute(
                    """INSERT INTO inventory_movements
                       (product_id, movement_type, quantity, previous_stock, new_stock, reason, user_id, created_at, synced)
                       VALUES (?,?,?,?,?,?,?,?,0)""",
                    (
                        ant["id_producto"],
                        m_type,
                        qty,
                        prev_stock,
                        new_stock,
                        reason,
                        ant["id_usuario"],
                        created_at,
                    ),
                )
                mov_id = cur.lastrowid
                if cola_vacia:
                    payload = json.dumps(
                        {
                            "movement_id": mov_id,
                            "product_id": ant["id_producto"],
                            "sku": ant["sku"],
                            "movement_type": m_type,
                            "quantity": qty,
                            "previous_stock": prev_stock,
                            "new_stock": new_stock,
                            "reason": reason,
                            "user_id": ant["id_usuario"],
                            "created_at": created_at,
                        },
                        ensure_ascii=False,
                    )
                    con.execute(
                        """INSERT INTO sync_queue (table_name, record_id, operation, payload, status, created_at)
                           VALUES ('inventory_movements', ?, 'INSERT', ?, 'PENDING', ?)""",
                        (mov_id, payload, created_at),
                    )

        if con.execute("SELECT COUNT(*) FROM categorias").fetchone()[0] == 0:
            con.executemany(
                "INSERT INTO categorias (nombre, descripcion, iva_porcentaje) VALUES (?,?,?)",
                CATEGORIAS_INICIALES,
            )


if __name__ == "__main__":
    inicializar_base_datos()
    print("Base de datos lista.")