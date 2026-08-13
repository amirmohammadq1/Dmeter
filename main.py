# -*- coding: utf-8 -*-

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
SERIAL_RECONNECT_DELAY = 2.0
UI_UPDATE_INTERVAL = 1 / 30.0


def _log_dir():
    try:
        if platform == "android":
            from android.storage import app_storage_path
            return app_storage_path()
    except Exception:
        pass

    return os.path.dirname(os.path.abspath(__file__))


_LOG_PATH = os.path.join(_log_dir(), "Dmeter_crash_log.txt")


def log_event(message):
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(
                f"[{datetime.datetime.now().isoformat(timespec='seconds')}] "
                f"{message}\n"
            )
    except Exception:
        pass


def log_exception(context):
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(
                f"[{datetime.datetime.now().isoformat(timespec='seconds')}] "
                f"EXCEPTION in {context}:\n"
            )
            f.write(traceback.format_exc())
            f.write("\n")
    except Exception:
        pass


class SerialReaderError(Exception):
    pass


class SerialReader:

    def __init__(self, on_value=None, on_status=None):
        self.on_value = on_value
        self.on_status = on_status

        self._is_android = platform == "android"

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
                "USB SERIAL LIBRARY ERROR"
            ) from exc

        try:

            devices = usb.get_usb_device_list()

            if not devices:
                self._notify_status("NO USB DEVICE")
                raise SerialReaderError("NO USB DEVICE")

            selected = None

            # Arduino UNO official USB identifiers
            arduino_vids = {
                0x2341,
                0x2A03,
                0x2341
            }

            # Common USB serial clone identifiers
            serial_vids = {
                0x1A86,  # CH340 / CH341
                0x10C4,  # CP210x
                0x0403,  # FTDI
                0x067B   # PL2303
            }

            # First try to find Arduino / USB-serial device
            for device in devices:

                try:
                    vid = device.getVendorId()

                    if vid in arduino_vids:
                        selected = device
                        break

                except Exception:
                    pass

            # If official Arduino VID wasn't found,
            # try common USB serial adapters.
            if selected is None:

                for device in devices:

                    try:
                        vid = device.getVendorId()

                        if vid in serial_vids:
                            selected = device
                            break

                    except Exception:
                        pass

            # Last fallback: use the first USB device.
            if selected is None:
                selected = devices[0]

            if not usb.has_usb_permission(selected):

                usb.request_usb_permission(selected)

                self._notify_status(
                    "WAITING FOR USB PERMISSION"
                )

                raise SerialReaderError(
                    "WAITING FOR USB PERMISSION"
                )

            device_name = selected.getDeviceName()

            self._connection = serial4a.get_serial_port(
                device_name,
                SERIAL_BAUDRATE,
                8,
                "N",
                1
            )

            if self._connection is None:
                raise SerialReaderError(
                    "SERIAL PORT ERROR"
                )

            # Try to activate DTR / RTS.
            try:
                self._connection.dtr = True
            except Exception:
                pass

            try:
                self._connection.rts = True
            except Exception:
                pass

            # Short timeout.
            try:
                self._connection.timeout = 0.1
            except Exception:
                pass

            self._notify_status("USB CONNECTED")

        except SerialReaderError:
            raise

        except Exception as exc:
            log_exception("USB OPEN")

            raise SerialReaderError(
                "USB CONNECTION FAILED"
            ) from exc

    def _open_desktop(self):

        try:
            import serial
        except ImportError as exc:

            raise SerialReaderError(
                "PYTHON SERIAL NOT INSTALLED"
            ) from exc

        try:

            self._serial_port = serial.Serial(
                "/dev/ttyUSB0",
                SERIAL_BAUDRATE,
                timeout=0.2
            )

            self._notify_status(
                "SERIAL CONNECTED"
            )

        except Exception as exc:

            raise SerialReaderError(
                "DESKTOP SERIAL ERROR"
            ) from exc

    def poll(self):

        raw = self._read_available_bytes()

        if not raw:
            return

        self._rx_buffer += raw

        while b"\n" in self._rx_buffer:

            line_bytes, self._rx_buffer = \
                self._rx_buffer.split(b"\n", 1)

            try:
                line = line_bytes.decode(
                    "ascii",
                    errors="ignore"
                ).strip()

            except Exception:
                continue

            if not line:
                continue

            try:

                value_mm = int(line)

            except ValueError:
                continue

            # Basic sanity check
            if value_mm < 0:
                continue

            if self.on_value is not None:
                self.on_value(value_mm)

    def _read_available_bytes(self):

        if self._is_android:

            if self._connection is None:
                return b""

            try:

                # usbserial4a normally exposes
                # pyserial-compatible in_waiting.

                waiting = getattr(
                    self._connection,
                    "in_waiting",
                    None
                )

                if callable(waiting):
                    waiting = waiting()

                if waiting is not None:

                    if waiting <= 0:
                        return b""

                    return self._connection.read(
                        waiting
                    ) or b""

                # Fallback
                return self._connection.read(
                    256
                ) or b""

            except Exception:

                if not self._read_error_logged:

                    self._read_error_logged = True

                    log_exception(
                        "ANDROID SERIAL READ"
                    )

                return b""

        else:

            if self._serial_port is None:
                return b""

            try:

                waiting = self._serial_port.in_waiting

                if waiting <= 0:
                    return b""

                return self._serial_port.read(
                    waiting
                ) or b""

            except Exception:

                if not self._read_error_logged:

                    self._read_error_logged = True

                    log_exception(
                        "DESKTOP SERIAL READ"
                    )

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

        Window.clearcolor = (
            0,
            0,
            0,
            1
        )

        self.root_layout = FloatLayout()

        self.value_label = Label(
            text="--.-",
            color=(
                1,
                1,
                1,
                1
            ),
            font_size="180sp",
            bold=True,
            size_hint=(
                1,
                1
            ),
            pos_hint={
                "center_x": 0.5,
                "center_y": 0.55
            },
            halign="center"
        )

        self.root_layout.add_widget(
            self.value_label
        )

        self.status_label = Label(
            text="CONNECTING...",
            color=(
                0.5,
                0.5,
                0.5,
                1
            ),
            font_size="18sp",
            size_hint=(
                1,
                None
            ),
            height="30dp",
            pos_hint={
                "center_x": 0.5,
                "y": 0.03
            }
        )

        self.root_layout.add_widget(
            self.status_label
        )

        self.reader = SerialReader(
            on_value=self._on_value,
            on_status=self._on_status
        )

        self._connected = False

        if platform == "android":
            self._request_android_permissions()

        Clock.schedule_once(
            self._try_connect,
            0.5
        )

        Clock.schedule_interval(
            self._poll_loop,
            UI_UPDATE_INTERVAL
        )

        return self.root_layout

    def _request_android_permissions(self):

        try:

            from android.permissions import request_permissions

            request_permissions([])

        except Exception:

            pass

    def _try_connect(self, dt):

        try:

            self.reader.open()

            self._connected = True

            self.status_label.text = \
                "USB CONNECTED - WAITING FOR DATA"

        except SerialReaderError as exc:

            self._connected = False

            self.status_label.text = str(
                exc
            )[:45]

            Clock.schedule_once(
                self._try_connect,
                SERIAL_RECONNECT_DELAY
            )

        except Exception:

            self._connected = False

            log_exception(
                "CONNECT"
            )

            self.status_label.text = \
                "CONNECTION ERROR"

            Clock.schedule_once(
                self._try_connect,
                SERIAL_RECONNECT_DELAY
            )

    def _on_status(self, message):
        pass

    def _on_value(self, value_mm):

        # Arduino sends millimeters.
        # Phone only converts mm to cm.

        value_cm = value_mm / 10.0

        self.value_label.text = \
            f"{value_cm:.1f}"

        self.status_label.text = \
            "LIVE"

    def _poll_loop(self, dt):

        try:

            if self._connected:
                self.reader.poll()

        except Exception:

            log_exception(
                "POLL LOOP"
            )

    def on_stop(self):

        try:

            self.reader.close()

        except Exception:

            log_exception(
                "CLOSE"
            )


if __name__ == "__main__":

    try:

        DmeterApp().run()

    except Exception:

        log_exception(
            "APP"
        )

        raise
