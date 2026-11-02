"""Datos de la empresa (se registran una única vez en el asistente inicial)."""
import re

from database.conexion import consultar_uno, transaccion
from logica.seguridad import ROL_ADMIN, ErrorValidacion, Sesion, auditar, requiere_rol


def empresa_registrada() -> bool:
    return consultar_uno("SELECT COUNT(*) AS n FROM empresa")["n"] > 0


def obtener_empresa() -> dict | None:
    return consultar_uno("SELECT * FROM empresa WHERE id_empresa = 1")


def _validar(datos: dict) -> dict:
    limpio = {k: (v or "").strip() for k, v in datos.items()}
    if not limpio.get("nit") or not limpio.get("razon_social"):
        raise ErrorValidacion("El NIT y la razón social son obligatorios.")
    if not re.fullmatch(r"[0-9.\-]{5,20}", limpio["nit"]):
        raise ErrorValidacion("El NIT solo puede contener números, puntos y guion (ej. 900.123.456-7).")
    if limpio.get("telefono") and not re.fullmatch(r"[0-9+ ()\-]{7,20}", limpio["telefono"]):
        raise ErrorValidacion("El teléfono no es válido.")
    if limpio.get("correo") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", limpio["correo"]):
        raise ErrorValidacion("El correo electrónico no es válido.")
    limpio["prefijo_factura"] = (limpio.get("prefijo_factura") or "FV").upper()[:5]
    return limpio


def registrar_empresa(datos: dict):
    if empresa_registrada():
        raise ErrorValidacion("La empresa ya fue registrada.")
    d = _validar(datos)
    with transaccion() as con:
        con.execute(
            """INSERT INTO empresa (id_empresa, nit, razon_social, direccion, telefono, correo, regimen, prefijo_factura)
               VALUES (1,?,?,?,?,?,?,?)""",
            (d["nit"], d["razon_social"], d.get("direccion"), d.get("telefono"),
             d.get("correo"), d.get("regimen") or "Responsable de IVA", d["prefijo_factura"]),
        )


@requiere_rol(ROL_ADMIN)
def actualizar_empresa(datos: dict):
    d = _validar(datos)
    with transaccion() as con:
        con.execute(
            """UPDATE empresa SET nit=?, razon_social=?, direccion=?, telefono=?, correo=?, regimen=?, prefijo_factura=?
               WHERE id_empresa = 1""",
            (d["nit"], d["razon_social"], d.get("direccion"), d.get("telefono"),
             d.get("correo"), d.get("regimen"), d["prefijo_factura"]),
        )
        auditar("ACTUALIZAR_EMPRESA", d["razon_social"], con)
