"""Reactive 20-20-20 eye strain monitor for Windows.

Runs as a background .pyw service and uses Win32 events to track only
"active" screen time (unlocked + awake). Every 20 minutes of cumulative
active use, it shows a desktop notification and plays a TTS reminder.
"""

from __future__ import annotations

import threading
import time
import ctypes

import pyttsx3
from plyer import notification
import win32api
import win32con
import win32gui
import win32ts

# WTS constants (wtsapi32)
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = win32ts.NOTIFY_FOR_THIS_SESSION
WM_WTSSESSION_CHANGE = 0x02B1

# Power broadcast constants
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMEAUTOMATIC = 0x0012

# App timing constants
ALERT_EVERY_SECONDS = 20 * 60
UI_TIMER_INTERVAL_MS = 1000

VISUAL_MESSAGE = "¡Aplica la regla 20-20-20! Mira a 6 metros durante 20 segundos."
VOICE_MESSAGE = "Aplica la regla veinte veinte veinte."


class EyeMonitorService:
    def __init__(self) -> None:
        self.hwnd = None
        self._is_active = True
        self._last_active_start = time.monotonic()
        self._active_accumulated_seconds = 0.0

    def run(self) -> None:
        class_name = "ReactiveEyeMonitorHiddenWindow"

        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._wnd_proc
        wc.lpszClassName = class_name
        wc.hInstance = win32api.GetModuleHandle(None)
        win32gui.RegisterClass(wc)

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
        win32ts.WTSRegisterSessionNotification(self.hwnd, NOTIFY_FOR_THIS_SESSION)

        # Use a Win32 timer message instead of polling loops.
        ctypes.windll.user32.SetTimer(self.hwnd, 1, UI_TIMER_INTERVAL_MS, 0)

        win32gui.PumpMessages()

    def _set_active_state(self, active: bool) -> None:
        now = time.monotonic()

        if self._is_active and not active:
            self._active_accumulated_seconds += now - self._last_active_start
            self._is_active = False
            return

        if (not self._is_active) and active:
            self._last_active_start = now
            self._is_active = True

    def _consume_elapsed_and_notify_if_needed(self) -> None:
        if not self._is_active:
            return

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

    @staticmethod
    def _notify_visual() -> None:
        notification.notify(
            title="Regla 20-20-20",
            message=VISUAL_MESSAGE,
            app_name="Reactive Eye Monitor",
            timeout=10,
        )

    @staticmethod
    def _notify_voice_async() -> None:
        def speak() -> None:
            engine = pyttsx3.init()
            engine.setProperty('rate', 170)
            engine.setProperty('volume', 1)
            engine.say(VOICE_MESSAGE)
            engine.runAndWait()

        thread = threading.Thread(target=speak, daemon=True)
        thread.start()

    def _shutdown(self) -> None:
        if self.hwnd is not None:
            try:
                ctypes.windll.user32.KillTimer(self.hwnd, 1)
            except Exception:
                pass

            try:
                win32ts.WTSUnRegisterSessionNotification(self.hwnd)
            except Exception:
                pass

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_POWERBROADCAST:
            if wparam == PBT_APMSUSPEND:
                self._set_active_state(False)
            elif wparam == PBT_APMRESUMEAUTOMATIC:
                self._set_active_state(True)
            return 1

        if msg == WM_WTSSESSION_CHANGE:
            if wparam == WTS_SESSION_LOCK:
                self._set_active_state(False)
            elif wparam == WTS_SESSION_UNLOCK:
                self._set_active_state(True)
            return 0

        if msg == win32con.WM_TIMER:
            self._consume_elapsed_and_notify_if_needed()
            return 0

        if msg == win32con.WM_DESTROY:
            self._shutdown()
            win32gui.PostQuitMessage(0)
            return 0

        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


def main() -> None:
    service = EyeMonitorService()
    service.run()


if __name__ == "__main__":
    main()
