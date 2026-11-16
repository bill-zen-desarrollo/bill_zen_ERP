"""Vista exclusiva del Administrador: Auditoría Remota de Solo Lectura mediante Código QR y Túnel."""
import time
import tkinter as tk
from PIL import Image, ImageTk

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from database.conexion import consultar
from logica import mobile_server as ms
from logica.seguridad import ROL_ADMIN, ErrorPermiso, Sesion
from ui import componentes as cmp
from ui import tema


class Vista(ttk.Frame):
    def __init__(self, padre, principal):
        super().__init__(padre)
        if not Sesion.es_admin():
            raise ErrorPermiso("El módulo de Auditoría Móvil es exclusivo para el Administrador.")

        self.principal = principal
        self._qr_photo = None
        self._expira_ts = 0
        self._ultimo_remote_url = ""
        self._timer_id = None
        self._paquete_actual = None

        # Encabezado principal
        cab = ttk.Frame(self)
        cab.pack(fill=X, pady=(0, 12))
        cmp.encabezado(
            cab,
            "Auditoría Móvil (QR)",
            "Vinculación remota de solo lectura para el Administrador (Doble candado + SQLite Read-Only)",
        ).pack(side=LEFT)

        acciones_cab = ttk.Frame(cab)
        acciones_cab.pack(side=RIGHT)
        ttk.Button(
            acciones_cab,
            text="Nuevo QR",
            style="Zen.TButton",
            command=self.generar_nuevo_qr,
        ).pack(side=LEFT, padx=(0, 8))
        ttk.Button(
            acciones_cab,
            text="Cerrar sesiones móviles activas",
            style="Peligro.TButton",
            command=self.cerrar_sesiones_activas,
        ).pack(side=LEFT)

        # Contenedor principal en 2 columnas
        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill=BOTH, expand=YES)
        cuerpo.columnconfigure(0, weight=2, uniform="col")
        cuerpo.columnconfigure(1, weight=3, uniform="col")
        cuerpo.rowconfigure(0, weight=1)

        # ================== COLUMNA IZQUIERDA: TARJETA DEL CÓDIGO QR ==================
        card_qr = cmp.tarjeta(cuerpo, padding=20)
        card_qr.grid(row=0, column=0, sticky=NSEW, padx=(0, 14))
        izq = card_qr.interior

        ttk.Label(
            izq,
            text="Código QR de Emparejamiento Temporal",
            style="TarjetaTitulo.TLabel",
        ).pack(anchor=CENTER)
        ttk.Label(
            izq,
            text="Escanea este QR desde Bill Zen App (Kotlin). Si el celular no tiene la app instalada, será redirigido automáticamente a la página oficial de descarga.",
            style="Tarjeta.TLabel",
            foreground=tema.GRIS,
            wraplength=320,
            justify=CENTER,
            font=(tema.FUENTE, 9),
        ).pack(anchor=CENTER, pady=(4, 10))

        # Marco del QR con borde dorado corporativo
        marco_img = tk.Frame(izq, bg=tema.DORADO, padx=3, pady=3)
        marco_img.pack(anchor=CENTER, pady=4)
        self.lbl_qr = tk.Label(marco_img, bg=tema.BLANCO, width=250, height=250)
        self.lbl_qr.pack()

        # Cuenta regresiva de 5 minutos
        self.lbl_contador = ttk.Label(
            izq,
            text="Expira en: 05:00",
            style="Tarjeta.TLabel",
            foreground=tema.VERDE_OSCURO,
            font=(tema.FUENTE_TITULO, 14, "bold"),
        )
        self.lbl_contador.pack(anchor=CENTER, pady=(10, 2))

        self.lbl_nota_qr = ttk.Label(
            izq,
            text="Firma HMAC-SHA256 activa · Validez estricta de 5 minutos",
            style="Tarjeta.TLabel",
            foreground=tema.VERDE_CLARO,
            font=(tema.FUENTE, 8, "bold"),
        )
        self.lbl_nota_qr.pack(anchor=CENTER, pady=(0, 10))

        botones_qr = ttk.Frame(izq, style="Tarjeta.TFrame")
        botones_qr.pack(fill=X, pady=(4, 0))
        ttk.Button(
            botones_qr,
            text="Nuevo QR",
            style="Oro.TButton",
            command=self.generar_nuevo_qr,
        ).pack(fill=X, pady=(0, 6))
        ttk.Button(
            botones_qr,
            text="Copiar link de descarga de la App",
            style="Suave.TButton",
            command=self.copiar_enlace_descarga,
        ).pack(fill=X)

        # ================== COLUMNA DERECHA: ESTADO DEL TÚNEL Y BITÁCORA ==================
        der = ttk.Frame(cuerpo)
        der.grid(row=0, column=1, sticky=NSEW)
        der.rowconfigure(1, weight=1)
        der.columnconfigure(0, weight=1)

        # Tarjeta superior derecha: Estado del túnel y candados de seguridad
        card_estado = cmp.tarjeta(der, padding=18)
        card_estado.grid(row=0, column=0, sticky=EW, pady=(0, 12))
        est = card_estado.interior

        cab_est = ttk.Frame(est, style="Tarjeta.TFrame")
        cab_est.pack(fill=X)
        ttk.Label(cab_est, text="Estado del Túnel y Seguridad", style="TarjetaTitulo.TLabel").pack(side=LEFT)
        self.lbl_sesiones = ttk.Label(
            cab_est,
            text="Sesiones activas: 0",
            style="Tarjeta.TLabel",
            foreground=tema.VERDE,
            font=(tema.FUENTE, 9, "bold"),
        )
        self.lbl_sesiones.pack(side=RIGHT)

        self.lbl_tunel = self._fila_dato(est, "Estado del túnel HTTPS:", "Iniciando...")
        self.lbl_url_remota = self._fila_dato(est, "URL Remota (Cloudflare):", "Esperando asignación...")
        self.lbl_url_local = self._fila_dato(est, "URL Red Local (Wi-Fi):", "—")
        self._fila_dato(
            est,
            "Permisos de Base de Datos:",
            "100% SOLO LECTURA (sqlite3 mode=ro + query_only)",
            color_valor=tema.VERDE,
        )
        self._fila_dato(
            est,
            "Control de Acceso:",
            "Exclusivo Rol Administrador (id_rol == 1) · Cajeros bloqueados (HTTP 403)",
            color_valor=tema.VERDE_OSCURO,
        )

        barra_est = ttk.Frame(est, style="Tarjeta.TFrame")
        barra_est.pack(fill=X, pady=(10, 0))
        ttk.Button(
            barra_est,
            text="Reconectar túnel HTTPS",
            style="Suave.TButton",
            command=self.reconectar_tunel,
        ).pack(side=LEFT)
        ttk.Button(
            barra_est,
            text="Cerrar sesiones móviles activas",
            style="Peligro.TButton",
            command=self.cerrar_sesiones_activas,
        ).pack(side=RIGHT)

        # Tarjeta inferior derecha: Bitácora de eventos móviles recientes
        card_bit = cmp.tarjeta(der, padding=18)
        card_bit.grid(row=1, column=0, sticky=NSEW)
        bit = card_bit.interior

        cab_bit = ttk.Frame(bit, style="Tarjeta.TFrame")
        cab_bit.pack(fill=X, pady=(0, 8))
        ttk.Label(cab_bit, text="Bitácora de Accesos y Eventos Móviles", style="TarjetaTitulo.TLabel").pack(side=LEFT)
        ttk.Button(
            cab_bit,
            text="Refrescar",
            style="Suave.TButton",
            command=self.cargar_bitacora_movil,
        ).pack(side=RIGHT)

        cols_bit = [
            ("fecha", "Fecha / Hora", 135, W),
            ("usuario", "Usuario", 95, W),
            ("accion", "Evento", 180, W),
            ("detalle", "Detalle", 220, W),
        ]
        marco_tv, self.tv_bitacora = cmp.tabla(bit, cols_bit, altura=8)
        marco_tv.pack(fill=BOTH, expand=YES)

        # Inicializar QR y temporizador
        self.generar_nuevo_qr(silencioso=True)
        self.cargar_bitacora_movil()
        self._programar_tick()

    def _fila_dato(self, padre, etiqueta: str, valor_inicial: str, color_valor=tema.TEXTO) -> ttk.Label:
        fila = ttk.Frame(padre, style="Tarjeta.TFrame")
        fila.pack(fill=X, pady=3)
        ttk.Label(
            fila,
            text=etiqueta,
            style="Tarjeta.TLabel",
            foreground=tema.GRIS,
            font=(tema.FUENTE, 9, "bold"),
            width=26,
        ).pack(side=LEFT, anchor=W)
        lbl = ttk.Label(
            fila,
            text=valor_inicial,
            style="Tarjeta.TLabel",
            foreground=color_valor,
            font=(tema.FUENTE, 9),
            wraplength=420,
        )
        lbl.pack(side=LEFT, anchor=W, fill=X, expand=YES)
        return lbl

    def generar_nuevo_qr(self, silencioso: bool = False):
        paquete = ms.generar_paquete_qr_emparejamiento()
        self._paquete_actual = paquete
        self._expira_ts = paquete["expira_en_ts"]
        self._ultimo_remote_url = paquete["payload"]["remote_url"]

        img_pil = paquete["imagen_pil"].resize((246, 246), Image.Resampling.NEAREST)
        self._qr_photo = ImageTk.PhotoImage(img_pil)
        self.lbl_qr.configure(image=self._qr_photo, text="", width=246, height=246)
        self.lbl_nota_qr.configure(
            text="Firma HMAC-SHA256 activa · Validez estricta de 5 minutos",
            foreground=tema.VERDE_CLARO,
        )
        self._actualizar_etiquetas_estado()
        self._actualizar_reloj()
        if not silencioso:
            cmp.toast(self, "Nuevo código QR generado (válido por 5 minutos)")

    def _actualizar_etiquetas_estado(self):
        est = ms.estado_servidor_movil()
        self.lbl_tunel.configure(
            text=est["estado_tunel"],
            foreground=tema.VERDE if est["remote_url"] else tema.DORADO,
        )
        self.lbl_url_remota.configure(
            text=est["remote_url"] or f"Redirigiendo sin app a: {ms.URL_DESCARGA_APP}",
            foreground=tema.VERDE_OSCURO if est["remote_url"] else tema.GRIS,
        )
        self.lbl_url_local.configure(text=est["local_url"])
        self.lbl_sesiones.configure(text=f"Sesiones activas: {est['sesiones_activas']}")

    def _actualizar_reloj(self):
        restante = max(0, int(self._expira_ts - time.time()))
        mins, segs = divmod(restante, 60)
        if restante > 0:
            color = tema.VERDE_OSCURO if restante > 60 else tema.ROJO
            self.lbl_contador.configure(text=f"Expira en: {mins:02d}:{segs:02d}", foreground=color)
        else:
            self.lbl_contador.configure(text="Código QR expirado (00:00)", foreground=tema.ROJO)
            self.lbl_nota_qr.configure(
                text="Pulsa 'Nuevo QR' para generar otro token de 5 minutos",
                foreground=tema.ROJO,
            )

    def _programar_tick(self):
        if not self.winfo_exists():
            return
        self._actualizar_reloj()
        est = ms.estado_servidor_movil()
        # Si el túnel cloudflared acaba de publicar la URL remota, regeneramos el QR automáticamente
        if est["remote_url"] and est["remote_url"] != self._ultimo_remote_url:
            self.generar_nuevo_qr(silencioso=True)
        else:
            self._actualizar_etiquetas_estado()
        self._timer_id = self.after(1000, self._programar_tick)

    def reconectar_tunel(self):
        ms.iniciar_tunel_cloudflared(forzar_reinicio=True)
        self._actualizar_etiquetas_estado()
        cmp.toast(self, "Solicitando nuevo túnel HTTPS a Cloudflare...")

    def copiar_enlace_descarga(self):
        self.clipboard_clear()
        self.clipboard_append(ms.URL_DESCARGA_APP)
        cmp.toast(self, f"Link de descarga copiado: {ms.URL_DESCARGA_APP}")

    def cerrar_sesiones_activas(self):
        if not cmp.confirmar(
            self,
            "¿Deseas revocar inmediatamente todas las sesiones móviles activas y los códigos QR emitidos?",
        ):
            return
        revocadas = ms.revocar_sesiones_moviles()
        self.generar_nuevo_qr(silencioso=True)
        self.cargar_bitacora_movil()
        cmp.toast(self, f"Sesiones móviles cerradas ({revocadas} revocadas) y llave HMAC rotada")

    def cargar_bitacora_movil(self):
        filas = consultar(
            """SELECT a.id_auditoria, a.fecha, COALESCE(u.username, '—') AS usuario, a.accion, COALESCE(a.detalle, '') AS detalle
               FROM auditoria a
               LEFT JOIN usuarios u ON u.id_usuario = a.id_usuario
               WHERE a.accion LIKE '%MOVIL%'
               ORDER BY a.id_auditoria DESC
               LIMIT 25"""
        )
        cmp.llenar_tabla(
            self.tv_bitacora,
            [(f["id_auditoria"], (f["fecha"], f["usuario"], f["accion"], f["detalle"])) for f in filas],
            lambda _iid, vals: ("alerta",) if ("DENEGADO" in vals[2] or "FALLIDO" in vals[2] or "BLOQUEADO" in vals[2]) else (),
        )

    def destroy(self):
        if self._timer_id is not None:
            try:
                self.after_cancel(self._timer_id)
            except Exception:
                pass
            self._timer_id = None
        self._qr_photo = None
        super().destroy()
