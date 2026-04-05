"""Reactive 20-20-20 eye strain monitor for Windows.

Runs as a background .pyw service and uses Win32 events to track only
"active" screen time (unlocked + awake). Every 20 minutes of cumulative
active use, it shows a desktop notification and plays a TTS reminder.
"""

from __future__ import annotations

import threading  # Para ejecutar tareas (como síntesis de voz) en hilos separados sin bloquear el principal
import time  # Para medir intervalos de tiempo con precisión usando time.monotonic()
import ctypes  # Para llamar funciones de librerías del sistema operativo de Windows directamente

import pyttsx3  # Motor de síntesis de voz (text-to-speech) que convierte texto en audio
from plyer import notification  # Para mostrar notificaciones visuales de escritorio nativa
import win32api  # API de Windows para obtener handles de procesos e instancia de la aplicación
import win32con  # Constantes de mensajes y valores de Windows (WM_*, etc.)
import win32gui  # GUI de Windows para crear ventanas, registrar clases, y procesar mensajes
import win32ts  # API de Sesiones de Terminal de Windows para detectar bloqueos/desbloqueos

# WTS constants (wtsapi32)
WTS_SESSION_LOCK = 0x7  # Código de evento: sesión bloqueada
WTS_SESSION_UNLOCK = 0x8  # Código de evento: sesión desbloqueada
NOTIFY_FOR_THIS_SESSION = win32ts.NOTIFY_FOR_THIS_SESSION  # Filtro para recibir notificaciones solo de la sesión actual
WM_WTSSESSION_CHANGE = 0x02B1  # Código de mensaje de Windows: cambio en estado de sesión

# Power broadcast constants
PBT_APMSUSPEND = 0x0004  # Código de evento: equipo entra en suspensión
PBT_APMRESUMEAUTOMATIC = 0x0012  # Código de evento: equipo reanuda automáticamente

# App timing constants
ALERT_EVERY_SECONDS = 20 * 60  # 1200 segundos = 20 minutos, intervalo para mostrar alerta
UI_TIMER_INTERVAL_MS = 1000  # 1000 milisegundos = 1 segundo, frecuencia del timer de actualización

VISUAL_MESSAGE = "¡Aplica la regla 20-20-20! Mira a 6 metros durante 20 segundos."  # Texto de notificación visual
VOICE_MESSAGE = "Aplica la regla veinte veinte veinte."  # Texto que el motor TTS pronunciará


class EyeMonitorService:
    def __init__(self) -> None:
        # Inicializa el estado interno del servicio de monitoreo
        self.hwnd = None  # Identificador de la ventana oculta de Windows que recibe mensajes
        self._is_active = True  # Flag que indica si el tiempo debe contarse (True) o está pausado (False)
        self._last_active_start = time.monotonic()  # Marca temporal del inicio del tramo activo actual
        self._active_accumulated_seconds = 0.0  # Total de segundos de uso activo acumulados en este ciclo

    # Crea y configura una ventana oculta de Windows, establece timers y entra en el bucle de mensajes del sistema
    def run(self) -> None:
        class_name = "ReactiveEyeMonitorHiddenWindow"

        # Define la clase de ventana que usará la aplicación para recibir mensajes de Windows
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._wnd_proc  # Callback que procesará los mensajes del sistema
        wc.lpszClassName = class_name  # Nombre interno de la clase
        wc.hInstance = win32api.GetModuleHandle(None)  # Instancia del proceso actual
        win32gui.RegisterClass(wc)  # Registra la clase en el sistema operativo

        # Crea una ventana invisible que solo sirve para recibir mensajes del sistema
        self.hwnd = win32gui.CreateWindow(
            class_name,
            class_name,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            wc.hInstance,
            None,
        )

        # Subscribe to lock/unlock notifications for this session.
        # Se registra la ventana para recibir eventos de bloqueo/desbloqueo de la sesión
        win32ts.WTSRegisterSessionNotification(self.hwnd, NOTIFY_FOR_THIS_SESSION)

        # Use a Win32 timer message instead of polling loops.
        # Crea un timer del sistema que enviará un mensaje WM_TIMER cada 1000 ms a la ventana
        ctypes.windll.user32.SetTimer(self.hwnd, 1, UI_TIMER_INTERVAL_MS, 0)

        # Inicia el bucle de mensajes que mantiene el proceso vivo escuchando eventos del sistema
        win32gui.PumpMessages()

    # Cambia el estado de actividad del monitor: pausa o reanuda la acumulación de tiempo
    def _set_active_state(self, active: bool) -> None:
        now = time.monotonic()

        # Si estaba activo y ahora se vuelve inactivo, guarda el tiempo transcurrido
        if self._is_active and not active:
            self._active_accumulated_seconds += now - self._last_active_start
            self._is_active = False
            return

        # Si estaba inactivo y ahora se vuelve activo, reinicia el contador de tiempo
        if (not self._is_active) and active:
            self._last_active_start = now
            self._is_active = True

    # Acumula el tiempo transcurrido desde el último tick y verifica si debe lanzar alertas
    def _consume_elapsed_and_notify_if_needed(self) -> None:
        if not self._is_active:
            return

        # Calcula cuánto tiempo pasó desde la última revisión
        now = time.monotonic()
        elapsed_since_last = now - self._last_active_start
        self._last_active_start = now
        self._active_accumulated_seconds += elapsed_since_last

        # Si el tiempo acumulado superó nuestro límite
        if self._active_accumulated_seconds >= ALERT_EVERY_SECONDS:
            
            # 1. Lanzar UNA sola notificación
            self._notify_visual()
            self._notify_voice_async()
            
            # 2. Reiniciar el reloj a cero (sin acumular deuda)
            self._active_accumulated_seconds = 0.0

    # Muestra una notificación visual nativa de escritorio con el recordatorio de la regla 20-20-20
    @staticmethod
    def _notify_visual() -> None:
        notification.notify(
            title="Regla 20-20-20",
            message=VISUAL_MESSAGE,
            app_name="Reactive Eye Monitor",
            timeout=10,
        )

    # Ejecuta la síntesis de voz en un hilo separado para leer el recordatorio sin bloquear el programa
    @staticmethod
    def _notify_voice_async() -> None:
        # Función interna que ejecuta la síntesis de voz
        def speak() -> None:
            engine = pyttsx3.init()  # Inicializa el motor TTS del sistema
            engine.setProperty('rate', 170)  # Establece la velocidad de locución (170 palabras/minuto)
            engine.setProperty('volume', 1)  # Establece el volumen al máximo
            engine.say(VOICE_MESSAGE)  # Agrega el texto a pronunciar
            engine.runAndWait()  # Espera a que termine la reproducción de audio

        # Crea un hilo daemon para que la voz no bloquee el procesamiento de mensajes
        thread = threading.Thread(target=speak, daemon=True)
        thread.start()

    # Libera los recursos de Windows cuando la ventana se cierra (timer y notificaciones de sesión)
    def _shutdown(self) -> None:
        if self.hwnd is not None:
            try:
                ctypes.windll.user32.KillTimer(self.hwnd, 1)  # Detiene el timer del sistema
            except Exception:
                pass

            try:
                win32ts.WTSUnRegisterSessionNotification(self.hwnd)  # Deja de recibir notificaciones de sesión
            except Exception:
                pass

    # Procesa todos los mensajes de Windows que recibe la ventana (sesión, energía, timer, etc.)
    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_POWERBROADCAST:
            # Detecta cambios en el estado de energía del equipo
            if wparam == PBT_APMSUSPEND:
                self._set_active_state(False)  # Equipo entra en suspensión: pausa el contador
            elif wparam == PBT_APMRESUMEAUTOMATIC:
                self._set_active_state(True)  # Equipo se reanuda: reanuda el contador
            return 1

        if msg == WM_WTSSESSION_CHANGE:
            # Detecta bloqueos y desbloqueos de la sesión actual
            if wparam == WTS_SESSION_LOCK:
                self._set_active_state(False)  # Sesión bloqueada: pausa el contador
            elif wparam == WTS_SESSION_UNLOCK:
                self._set_active_state(True)  # Sesión desbloqueada: reanuda el contador
            return 0

        if msg == win32con.WM_TIMER:
            # Cada tick del timer (cada segundo) acumula tiempo y revisa si debe alertar
            self._consume_elapsed_and_notify_if_needed()
            return 0

        if msg == win32con.WM_DESTROY:
            # Cuando la ventana se destruye, limpia recursos y termina el programa
            self._shutdown()
            win32gui.PostQuitMessage(0)
            return 0

        # Cualquier mensaje no manejado se delega al comportamiento estándar de Windows
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


# Punto de entrada del programa: crea el servicio y lo ejecuta
def main() -> None:
    service = EyeMonitorService()
    service.run()


if __name__ == "__main__":
    main()
