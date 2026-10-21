"""Módulo de bloqueo de pantalla y notificaciones gráficas para Ubuntu Desktop (Wayland / X11)."""

import logging
import os
import queue
import subprocess
import threading
import time

logger = logging.getLogger(__name__)


class ScreenLocker:
    """Administra la ventana gráfica de bloqueo a pantalla completa.
    
    Se ejecuta en un hilo secundario con su propio ciclo de eventos de Tkinter
    para no congelar el bucle de comunicación HTTP del agente.
    """

    def __init__(self):
        self._queue = queue.Queue()
        self._thread = None
        self._is_locked = False
        self._lock_state_mutex = threading.Lock()

    def start(self):
        """Inicia el hilo de la interfaz de bloqueo."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_ui_loop, daemon=True)
        self._thread.start()

    def lock(self, message=None):
        """Ordena el bloqueo inmediato de la pantalla."""
        with self._lock_state_mutex:
            self._is_locked = True
        self._queue.put(("lock", message))

    def unlock(self):
        """Ordena el desbloqueo de la pantalla."""
        with self._lock_state_mutex:
            self._is_locked = False
        self._queue.put(("unlock", None))

    def show_message(self, message):
        """Muestra un mensaje emergente enviado por el profesor."""
        self._queue.put(("message", message))

    def is_locked(self):
        with self._lock_state_mutex:
            return self._is_locked

    def _run_ui_loop(self):
        try:
            import tkinter as tk
            from tkinter import messagebox
        except ImportError:
            logger.warning("Tkinter no está instalado. El bloqueo visual estará deshabilitado.")
            return

        # Comprobar si hay un servidor gráfico disponible (DISPLAY o WAYLAND_DISPLAY)
        if not os.getenv("DISPLAY") and not os.getenv("WAYLAND_DISPLAY"):
            logger.warning("No se detectó entorno gráfico ($DISPLAY o $WAYLAND_DISPLAY). El bloqueo visual no se puede proyectar.")
            return

        root = None
        current_window = None
        msg_label = None

        try:
            root = tk.Tk()
            root.withdraw()  # Raíz oculta que procesa la cola
        except Exception as exc:
            logger.warning("No se pudo inicializar Tkinter en este entorno: %s", exc)
            return

        def check_queue():
            nonlocal current_window, msg_label
            try:
                while True:
                    action, data = self._queue.get_nowait()

                    if action == "lock":
                        custom_msg = data or "La sesión ha sido suspendida temporalmente por el profesor."
                        if current_window is None or not tk.TclError:
                            # Crear ventana de bloqueo a pantalla completa
                            current_window = tk.Toplevel(root)
                            current_window.title("EQUIPO BLOQUEADO")
                            current_window.configure(bg="#0b0f19")
                            
                            # Configuración de pantalla completa siempre al frente
                            try:
                                current_window.attributes("-fullscreen", True)
                                current_window.attributes("-topmost", True)
                            except Exception:
                                pass

                            # Bloquear cierre con combinaciones habituales
                            current_window.protocol("WM_DELETE_WINDOW", lambda: None)
                            current_window.bind("<Alt-F4>", lambda e: "break")
                            current_window.bind("<Escape>", lambda e: "break")

                            # Contenido visual elegante
                            container = tk.Frame(current_window, bg="#0b0f19")
                            container.pack(expand=True, fill="both", padx=40, pady=40)

                            lock_icon = tk.Label(
                                container,
                                text="🔒",
                                font=("Inter, Arial, sans-serif", 64),
                                bg="#0b0f19",
                                fg="#ef4444",
                            )
                            lock_icon.pack(pady=(60, 20))

                            title_lbl = tk.Label(
                                container,
                                text="PANTALLA BLOQUEADA POR EL DOCENTE",
                                font=("Inter, Arial, sans-serif", 24, "bold"),
                                bg="#0b0f19",
                                fg="#f1f5f9",
                            )
                            title_lbl.pack(pady=10)

                            sub_lbl = tk.Label(
                                container,
                                text="Laboratorio de Sistemas Operativos — Control Centralizado",
                                font=("Inter, Arial, sans-serif", 13),
                                bg="#0b0f19",
                                fg="#94a3b8",
                            )
                            sub_lbl.pack(pady=5)

                            msg_label = tk.Label(
                                container,
                                text=custom_msg,
                                font=("Inter, Arial, sans-serif", 15, "italic"),
                                bg="#1e293b",
                                fg="#38bdf8",
                                padx=25,
                                pady=15,
                                wraplength=700,
                            )
                            msg_label.pack(pady=35)

                            try:
                                current_window.grab_set()
                                current_window.focus_force()
                            except Exception:
                                pass
                        else:
                            if msg_label:
                                msg_label.config(text=custom_msg)

                    elif action == "unlock":
                        if current_window is not None:
                            try:
                                current_window.grab_release()
                                current_window.destroy()
                            except Exception:
                                pass
                            current_window = None
                            msg_label = None

                    elif action == "message":
                        # Mostrar alerta modal de mensaje del profesor
                        try:
                            # Intentar notificación nativa primero si existe notify-send
                            subprocess.run(
                                ["notify-send", "-u", "critical", "-t", "10000", "Mensaje del Docente", str(data)],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                        except Exception:
                            pass

                        # Mensaje emergente Tkinter
                        try:
                            messagebox.showinfo("Aviso del Docente", str(data), parent=root)
                        except Exception:
                            pass

            except queue.Empty:
                pass

            root.after(200, check_queue)

        root.after(200, check_queue)
        root.mainloop()


# Instancia singleton para uso en el agente
locker = ScreenLocker()
