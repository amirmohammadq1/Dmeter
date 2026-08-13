# -*- coding: utf-8 -*-
"""
Dmeter - main.py
A single-purpose digital meter: connects to an Arduino over USB/OTG,
reads one integer (millimeters) per line, and shows it on screen as a
big white number in centimeters with one decimal place (e.g. "180.0")
on a plain black background.

This app does zero calculation of its own beyond the mm -> cm display
conversion (divide by 10, one decimal place) - the 200cm-baseline math
lives entirely on the Arduino (see firmware/Dmeter.ino). The phone is
purely a display.

Kept as a single file (no separate .kv) on purpose: this app is simple
enough that one file is easier to maintain and impossible to break by a
copy/paste mismatch between files.
"""

import os
import traceback
import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.utils import platform

SERIAL_BAUDRATE = 9600
SERIAL_RECONNECT_DELAY = 2.0   # seconds between reconnect attempts
UI_UPDATE_INTERVAL = 1 / 30.0


# ---------------------------------------------------------------------
# Crash logging - writes to Dmeter_crash_log.txt in the app's own private
# storage, so a failure is always readable afterwards instead of just
# silently closing the app.
# ---------------------------------------------------------------------
def _log_dir():
    try:
        if platform == "android":
            from android.storage import app_storage_path  # noqa
            return app_storage_path()
    except Exception:
        pass
    return os.path.dirname(os.path.abspath(__file__))


_LOG_PATH = os.path.join(_log_dir(), "Dmeter_crash_log.txt")


def log_event(message):
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {message}\n")
    except Exception:
        pass


def log_exception(context):
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().isoformat(timespec='seconds')}] EXCEPTION in {context}:\n")
            f.write(traceback.format_exc())
            f.write("\n")
    except Exception:
        pass


log_event("=== Dmeter starting ===")


class SerialReaderError(Exception):
    pass


class SerialReader:
    """
    Reads Dmeter's one-value-per-line protocol over USB/OTG (Android,
    via usb4a/usbserial4a) or a regular serial port (desktop testing,
    via pyserial). Every failure mode - missing package, no device, no
    permission yet, a raw pyjnius/Java exception - is turned into a
    SerialReaderError so the caller's retry loop can handle it safely
    and never crashes the app.
    """

    def __init__(self, on_value=None, on_status=None):
        self.on_value = on_value       # callback(int millimeters)
        self.on_status = on_status     # callback(str)
        self._is_android = (platform == "android")
        self._connection = None
        self._serial_port = None
        self._rx_buffer = b""
        self._read_error_logged = False

    def open(self):
        if self._is_android:
            self._open_android()
        else:
            self._open_desktop()

    def _open_android(self):
        try:
            from usb4a import usb
            from usbserial4a import serial4a
        except ImportError as exc:
            raise SerialReaderError(
                "usb4a / usbserial4a not installed (Android-only packages)."
            ) from exc

        try:
            device_list = usb.get_usb_device_list()
            if not device_list:
                self._notify_status("NO USB DEVICE")
                raise SerialReaderError("No USB device connected.")

            usb_device = device_list[0]
            if not usb.has_usb_permission(usb_device):
                usb.request_usb_permission(usb_device)
                self._notify_status("WAITING FOR USB PERMISSION")
                raise SerialReaderError("Waiting for USB permission to be granted.")

            self._connection = serial4a.get_serial_port(
                usb_device.getDeviceName(),
                SERIAL_BAUDRATE,
                8,      # data bits
                "N",    # parity - must be 'N'/'E'/'O'/'M'/'S' (a string), not an int
                1,      # stop bits
            )
            self._notify_status("USB CONNECTED")
        except SerialReaderError:
            raise
        except Exception as exc:
            raise SerialReaderError(f"USB connection failed: {exc}") from exc

    def _open_desktop(self):
        try:
            import serial as pyserial
        except ImportError as exc:
            raise SerialReaderError(
                "pyserial not installed - for desktop testing: pip install pyserial"
            ) from exc
        try:
            self._serial_port = pyserial.Serial("/dev/ttyUSB0", SERIAL_BAUDRATE, timeout=0.2)
            self._notify_status("SERIAL CONNECTED (desktop)")
        except Exception as exc:
            raise SerialReaderError(f"Desktop serial connection failed: {exc}") from exc

    def poll(self):
        raw_bytes = self._read_available_bytes()
        if not raw_bytes:
            return
        self._rx_buffer += raw_bytes
        while b"\n" in self._rx_buffer:
            line_bytes, self._rx_buffer = self._rx_buffer.split(b"\n", 1)
            try:
                line = line_bytes.decode("utf-8", errors="ignore").strip()
            except Exception:
                continue
            if not line:
                continue
            try:
                value_mm = int(line)
            except ValueError:
                continue   # a torn/garbled line - skip it, not a crash
            if self.on_value is not None:
                self.on_value(value_mm)

    def _read_available_bytes(self):
        if self._is_android:
            if self._connection is None:
                return b""
            try:
                return self._connection.read(4096) or b""
            except Exception:
                if not self._read_error_logged:
                    self._read_error_logged = True
                    log_exception("SerialReader._read_available_bytes (android) "
                                   "- further occurrences are suppressed")
                return b""
        else:
            if self._serial_port is None:
                return b""
            try:
                n = self._serial_port.in_waiting
                return self._serial_port.read(n) if n else b""
            except Exception:
                if not self._read_error_logged:
                    self._read_error_logged = True
                    log_exception("SerialReader._read_available_bytes (desktop) "
                                   "- further occurrences are suppressed")
                return b""

    def _notify_status(self, message):
        if self.on_status is not None:
            self.on_status(message)

    def close(self):
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None
        if self._serial_port is not None:
            try:
                self._serial_port.close()
            except Exception:
                pass
            self._serial_port = None


class DmeterApp(App):
    title = "Dmeter"

    def build(self):
        log_event("build() started")
        Window.clearcolor = (0, 0, 0, 1)   # black background

        self.root_layout = FloatLayout()

        # ------------------------------------------------------------
        # Watermark - a faint credit mark behind the main display, the
        # way a PDF watermarks its pages. Uses a generic play-triangle
        # (not YouTube's actual trademarked logo asset) plus a name.
        #
        # size_hint_x=0.6 caps its width at 60% of the screen no matter
        # what device this runs on, so it can never spill off-screen; the
        # font size is also recalculated from the window's own width
        # (not a fixed sp value) for the same reason. It's added to the
        # layout FIRST, before the number/status labels, which is what
        # keeps it visually "behind" everything else - and it's written
        # directly into this same build() method, not a separate
        # optional file/asset, so removing it means actually editing
        # this core display code, not just deleting an image.
        # (Being fully honest: since this is open Python source, anyone
        # with the code technically *can* still edit it out - there's no
        # way to make Python source truly tamper-proof from someone who
        # has the source. This just avoids it being a one-click delete.)
        # ------------------------------------------------------------
        self.watermark_label = Label(
            text="[b]\u25B6  AmirMEDK[/b]",
            markup=True,
            color=(1, 1, 1, 0.14),
            font_size="60sp",
            bold=True,
            size_hint=(0.6, None),
            height="110dp",
            pos_hint={"center_x": 0.5, "top": 0.98},
            halign="center",
            valign="middle",
        )
        self.watermark_label.bind(
            size=lambda inst, sz: setattr(inst, "text_size", sz)
        )
        self.root_layout.add_widget(self.watermark_label)
        self._resize_watermark_font()
        Window.bind(size=lambda *args: self._resize_watermark_font())

        self.value_label = Label(
            text="--.-",
            color=(1, 1, 1, 1),             # white text
            font_size="180sp",
            bold=True,
            size_hint=(1, 1),
            pos_hint={"center_x": 0.5, "center_y": 0.55},
            halign="center",
        )
        self.root_layout.add_widget(self.value_label)

        self.status_label = Label(
            text="CONNECTING...",
            color=(0.5, 0.5, 0.5, 1),       # dim gray, unobtrusive
            font_size="18sp",
            size_hint=(1, None),
            height="30dp",
            pos_hint={"center_x": 0.5, "y": 0.03},
        )
        self.root_layout.add_widget(self.status_label)

        self.reader = SerialReader(on_value=self._on_value, on_status=self._on_status)
        self._connected = False
        self._got_first_value = False

        if platform == "android":
            self._request_android_permissions()

        Clock.schedule_once(self._try_connect, 0.3)
        Clock.schedule_interval(self._poll_loop, UI_UPDATE_INTERVAL)
        log_event("build() finished successfully")
        return self.root_layout

    def _resize_watermark_font(self):
        # scaled from the window's actual width, not a fixed sp value, so
        # it stays proportional (and never overflows) on any screen size
        try:
            self.watermark_label.font_size = max(24, Window.width * 0.055)
        except Exception:
            pass

    def _request_android_permissions(self):
        try:
            from android.permissions import request_permissions
            request_permissions([])
        except Exception:
            log_exception("_request_android_permissions (non-fatal)")

    def _try_connect(self, dt):
        try:
            self.reader.open()
            self._connected = True
            # "USB OPEN" here, not "LIVE" yet - LIVE only shows once a value
            # has actually been received, so a device that connects but
            # never sends usable data is visibly distinguishable on screen
            self.status_label.text = "USB OPEN - WAITING FOR DATA"
            log_event("reader.open() succeeded")
        except SerialReaderError as exc:
            self._connected = False
            self.status_label.text = str(exc)[:48]
            Clock.schedule_once(self._try_connect, SERIAL_RECONNECT_DELAY)
        except Exception:
            self._connected = False
            log_exception("reader.open() - unexpected error")
            self.status_label.text = "SENSOR LINK ERROR"
            Clock.schedule_once(self._try_connect, SERIAL_RECONNECT_DELAY)

    def _on_status(self, message):
        pass

    def _on_value(self, value_mm):
        self._got_first_value = True
        self.status_label.text = "LIVE"
        value_cm = value_mm / 10.0
        self.value_label.text = f"{value_cm:.1f}"

    def _poll_loop(self, dt):
        try:
            if self._connected:
                self.reader.poll()
        except Exception:
            log_exception("_poll_loop")

    def on_stop(self):
        try:
            self.reader.close()
        except Exception:
            log_exception("on_stop / reader.close()")


if __name__ == "__main__":
    try:
        DmeterApp().run()
    except Exception:
        log_exception("top-level app.run()")
        raise
