"""Punto de entrada de Bill Zen ERP.

Flujo: crea la base de datos si no existe -> asistente (empresa + admin) la primera vez
-> login -> panel de administrador o panel de cajero según el rol.
Todo ocurre en UNA sola ventana.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ttkbootstrap as ttk
from tkinter import messagebox

def maneja_excepcion(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    try:
        from database.conexion import _carpeta_datos
        with open(os.path.join(_carpeta_datos(), "error.log"), "a", encoding="utf-8") as fh:
            fh.write(error_msg + "\n")
    except Exception:
        pass
    messagebox.showerror("Error inesperado", f"Ocurrió un problema inesperado:\n{exc_value}\n\nEl detalle técnico se guardó en el registro local.")

sys.excepthook = maneja_excepcion

from database.setup_db import inicializar_base_datos
from logica import auth_logic, empresa_logic, licencia, respaldo
from ui import tema
from ui.activacion import VistaActivacion
from ui.login import Login
from ui.setup_wizard import AsistenteInicial
from ui.shell import Principal


def _ruta_icono() -> str | None:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for rel in (
        ("assets", "logo.ico"),
        ("assets", "icono.ico"),
        ("ui", "images", "logo.ico"),
        ("ui", "images", "icono.ico"),
    ):
        ruta = os.path.join(base, *rel)
        if os.path.exists(ruta):
            return ruta
    return None


class BillZenApp:
    def __init__(self):
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("billzen.erp.app.1")
            except Exception:
                pass
        inicializar_base_datos()
        self.ventana = ttk.Window(themename="flatly", iconphoto=None)
        self.ventana.withdraw()
        self.ventana.report_callback_exception = maneja_excepcion
        estilo = tema.registrar_tema()
        tema.aplicar_estilos(estilo)
        self.ventana.title("Bill Zen ERP")
        self.ventana.minsize(1100, 680)
        self.ventana.configure(background=tema.BEIGE)
        icono = _ruta_icono()
        if icono:
            try:
                self.ventana.iconbitmap(default=icono)
                self.ventana.wm_iconbitmap(icono)
                from PIL import Image, ImageTk
                with Image.open(icono) as im:
                    rgba = im.convert("RGBA")
                    self._iconos_tk = [
                        ImageTk.PhotoImage(rgba.resize((sz, sz), Image.LANCZOS))
                        for sz in (16, 24, 32, 48, 64)
                    ]
                self.ventana.iconphoto(True, *self._iconos_tk)
            except Exception:
                pass

        self.iniciar()
        try:
            self.ventana.state("zoomed")
        except Exception:
            self.ventana.geometry("1280x760")
        self.ventana.update_idletasks()
        if icono and os.name == "nt":
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetParent(self.ventana.winfo_id())
                hicon_sm = ctypes.windll.user32.LoadImageW(0, icono, 1, 16, 16, 0x00000010)
                hicon_lg = ctypes.windll.user32.LoadImageW(0, icono, 1, 48, 48, 0x00000010)
                if hicon_sm:
                    ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hicon_sm)
                if hicon_lg:
                    ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hicon_lg)
            except Exception:
                pass
        self.ventana.deiconify()
        try:
            self.ventana.lift()
            self.ventana.attributes("-topmost", True)
            self.ventana.after(250, lambda: self.ventana.attributes("-topmost", False))
            self.ventana.focus_force()
        except Exception:
            pass

    def iniciar(self):
        estado_lic = licencia.verificar_licencia_local()
        if not estado_lic["valido"]:
            VistaActivacion(self.ventana, estado_lic, al_activar=self.iniciar)
            return

        # Sincronizar plan en segundo plano para que la ventana abra al instante sin congelarse
        import threading
        threading.Thread(
            target=lambda: licencia.sincronizar_plan_con_nube(timeout_seg=2.5),
            daemon=True,
        ).start()

        if (not empresa_logic.empresa_registrada()
                or not auth_logic.existe_admin()
                or not auth_logic.tiene_preguntas_admin()):
            AsistenteInicial(self.ventana, al_terminar=self.mostrar_login)
        else:
            self.mostrar_login()

    def mostrar_login(self):
        try:
            self.ventana.state("zoomed")
        except Exception:
            pass
        Login(self.ventana, al_ingresar=self.mostrar_principal)

    def mostrar_principal(self, _usuario):
        try:
            self.ventana.state("zoomed")
        except Exception:
            pass
        Principal(self.ventana, al_cerrar_sesion=self.mostrar_login)

    def cerrar(self):
        """Cierre de la tienda: guarda la copia de seguridad del día y sale."""
        try:
            respaldo.respaldar()
        except Exception as e:  # un fallo del respaldo nunca debe impedir cerrar
            print(f"No se pudo crear la copia de seguridad: {e}")
        self.ventana.destroy()

    def ejecutar(self):
        self.ventana.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.ventana.mainloop()


if __name__ == "__main__":
    BillZenApp().ejecutar()