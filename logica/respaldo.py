"""Copias de seguridad automáticas semanales y bóveda de auto-recuperación.

Al cerrar el programa se verifica si ya existe el respaldo de la semana actual en
una bóveda oculta independiente (~\\.billzen_vault\\respaldos). Solo se genera un
archivo por semana (formato bill_zen_AAAA-S##.db) y se conservan las `MAX_COPIAS`
semanas más recientes. Si la base de datos principal llegara a borrarse por
accidente, el sistema la restaura automáticamente desde la copia más reciente.
"""
import os
import shutil
import sqlite3
from datetime import date

from database.conexion import _carpeta_boveda, _ocultar_en_windows, ruta_db

MAX_COPIAS = 4  # últimas 4 semanas


def carpeta_respaldos() -> str:
    base = os.path.dirname(ruta_db()) if os.environ.get("BILLZEN_DB") else _carpeta_boveda()
    carpeta = os.path.join(base, "respaldos")
    os.makedirs(carpeta, exist_ok=True)
    _ocultar_en_windows(carpeta)
    return carpeta


def restaurar_si_falta() -> bool:
    """Si la BD principal no existe pero hay copias en la bóveda, restaura la más reciente."""
    if os.environ.get("BILLZEN_DB"):
        return False
    db_actual = ruta_db()
    if os.path.exists(db_actual):
        return False
    copias = listar_copias()
    if not copias:
        return False
    origen = os.path.join(carpeta_respaldos(), copias[0])
    os.makedirs(os.path.dirname(db_actual), exist_ok=True)
    shutil.copy2(origen, db_actual)
    return True


def respaldar(forzar: bool = False) -> str | None:
    """Crea la copia semanal si aún no existe para la semana en curso (o si forzar=True).
    Usa la API de backup de SQLite: la copia es consistente aunque la BD esté en uso."""
    db_actual = ruta_db()
    if not os.path.exists(db_actual):
        return None
    iso = date.today().isocalendar()
    destino = os.path.join(carpeta_respaldos(), f"bill_zen_{iso.year}-S{iso.week:02d}.db")
    if os.path.exists(destino) and not forzar:
        return destino

    temporal = destino + ".tmp"
    with sqlite3.connect(db_actual) as origen, sqlite3.connect(temporal) as copia:
        origen.backup(copia)
    os.replace(temporal, destino)  # reemplazo atómico: nunca queda una copia a medias
    _limpiar_antiguas()
    return destino


def _limpiar_antiguas():
    carpeta = carpeta_respaldos()
    copias = sorted(f for f in os.listdir(carpeta) if f.startswith("bill_zen_") and f.endswith(".db"))
    for viejo in copias[:-MAX_COPIAS]:
        try:
            os.remove(os.path.join(carpeta, viejo))
        except OSError:
            pass


def listar_copias() -> list[str]:
    return sorted((f for f in os.listdir(carpeta_respaldos()) if f.endswith(".db")), reverse=True)
