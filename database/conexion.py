"""Gestión centralizada de la conexión a la base de datos SQLite embebida.

La base de datos principal se aloja en %PROGRAMDATA%\\BillZen con atributo oculto
del sistema (fuera de cachés temporales y oculta en el Explorador de archivos),
mientras que las copias semanales se resguardan en una bóveda oculta independiente.
Se puede cambiar la ruta con la variable de entorno BILLZEN_DB (útil para pruebas).
"""
import ctypes
import os
import sqlite3
from contextlib import contextmanager


def _ocultar_en_windows(ruta: str):
    """Aplica el atributo FILE_ATTRIBUTE_HIDDEN (0x02) en Windows para proteger la carpeta de curiosos."""
    if os.name == "nt" and os.path.exists(ruta):
        try:
            atributos = ctypes.windll.kernel32.GetFileAttributesW(ruta)
            if atributos != -1 and not (atributos & 0x02):
                ctypes.windll.kernel32.SetFileAttributesW(ruta, atributos | 0x02)
        except Exception:
            pass


def _carpeta_datos() -> str:
    base = os.environ.get("PROGRAMDATA") or os.path.expanduser("~")
    carpeta = os.path.join(base, "BillZen")
    try:
        os.makedirs(carpeta, exist_ok=True)
    except OSError:
        carpeta = os.path.join(os.path.expanduser("~"), ".billzen_sys")
        os.makedirs(carpeta, exist_ok=True)
    _ocultar_en_windows(carpeta)
    return carpeta


def _carpeta_boveda() -> str:
    """Segunda ubicación oculta e independiente para las copias de seguridad semanales."""
    boveda = os.path.join(os.path.expanduser("~"), ".billzen_vault")
    os.makedirs(boveda, exist_ok=True)
    _ocultar_en_windows(boveda)
    return boveda


def ruta_db() -> str:
    return os.environ.get("BILLZEN_DB") or os.path.join(_carpeta_datos(), "bill_zen.db")


def conectar():
    """Abre una conexión con claves foráneas activas, modo WAL optimizado y filas tipo diccionario."""
    conexion = sqlite3.connect(ruta_db(), timeout=10)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA journal_mode = WAL")
    conexion.execute("PRAGMA synchronous = NORMAL")
    conexion.execute("PRAGMA temp_store = MEMORY")
    conexion.execute("PRAGMA cache_size = -4000")  # máx. ~4 MB de RAM en caché por conexión
    return conexion


@contextmanager
def transaccion():
    """Context manager: confirma si todo sale bien, revierte ante cualquier error
    y siempre cierra la conexión para no dejar el archivo bloqueado."""
    conexion = conectar()
    try:
        yield conexion
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def consultar(sql, parametros=()):
    with transaccion() as con:
        return [dict(f) for f in con.execute(sql, parametros).fetchall()]


def consultar_uno(sql, parametros=()):
    filas = consultar(sql, parametros)
    return filas[0] if filas else None
