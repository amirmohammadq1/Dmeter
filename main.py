# -*- coding: utf-8 -*-

"""
Dmeter - main.py

Android app:
Arduino -> USB/OTG -> Android -> big digital meter

Arduino sends one integer per line in millimeters.
Example:
1800
1801
1799

The phone converts:
1800 mm -> 180.0 cm
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


# ============================================================
# CONFIG
# ============================================================

SERIAL_BAUDRATE = 9600

SERIAL_RECONNECT_DELAY = 2.0

UI_UPDATE_INTERVAL = 1 / 30.0


# ============================================================
# LOGGING
# ============================================================

def _log_dir():
    try:
        if platform == "android":
            from android.storage import app_storage_path
            return app_storage_path()
    except Exception:
        pass

    return os.path.dirname(
        os.path.abspath(__file__)
    )


_LOG_PATH = os.path.join(
    _log_dir(),
    "Dmeter_crash_log.txt"
)


def log_event(message):
    try:
        with open(
            _LOG_PATH,
            "a",
            encoding="utf-8"
        ) as f:

            f.write(
                f"[{datetime.datetime.now().isoformat(timespec='seconds')}] "
                f"{message}\n"
            )

    except Exception:
        pass


def log_exception(context):
    try:
        with open(
            _LOG_PATH,
            "a",
            encoding="utf-8"
        ) as f:

            f.write(
                f"[{datetime.datetime.now().isoformat(timespec='seconds')}] "
                f"EXCEPTION in {context}:\n"
            )

            f.write(
                traceback.format_exc()
            )

            f.write("\n")

    except Exception:
        pass


log_event(
    "=== Dmeter starting ==="
)


# ============================================================
# SERIAL ERROR
# ============================================================

class SerialReaderError(Exception):
    pass


# ============================================================
# SERIAL READER
# ============================================================

class SerialReader:

    def __init__(
        self,
        on_value=None,
        on_status=None
    ):

        self.on_value = on_value
        self.on_status = on_status

        self._is_android = (
            platform == "android"
        )

        self._connection = None
        self._serial_port = None

        self._rx_buffer = b""

        self._read_error_logged = False

    # --------------------------------------------------------
    # OPEN
    # --------------------------------------------------------

    def open(self):

        if self._is_android:
            self._open_android()

        else:
            self._open_desktop()

    # --------------------------------------------------------
    # ANDROID USB
    # --------------------------------------------------------

    def _open_android():

        try:

            from usb4a import usb
            from usbserial4a import serial4a

        except ImportError as exc:

            raise SerialReaderError(
                "USB SERIAL LIBRARY ERROR"
            ) from exc

        try:

            device_list = (
                usb.get_usb_device_list()
            )

            if not device_list:

                self._notify_status(
                    "NO USB DEVICE"
                )

                raise SerialReaderError(
                    "NO USB DEVICE"
                )

            selected_device = None

            # Official Arduino USB VIDs
            arduino_vids = {
                0x2341,
                0x2A03
            }

            # Common USB-Serial clone VIDs
            serial_vids = {
                0x1A86,   # CH340 / CH341
                0x10C4,   # CP210x
                0x0403,   # FTDI
                0x067B    # PL2303
            }

            # ------------------------------------------------
            # Prefer Arduino
            # ------------------------------------------------

            for device in device_list:

                try:

                    vid = (
                        device.getVendorId()
                    )

                    if vid in arduino_vids:

                        selected_device = device

                        break

                except Exception:

                    pass

            # ------------------------------------------------
            # Then common USB serial chips
            # ------------------------------------------------

            if selected_device is None:

                for device in device_list:

                    try:

                        vid = (
                            device.getVendorId()
                        )

                        if vid in serial_vids:

                            selected_device = device

                            break

                    except Exception:

                        pass

            # ------------------------------------------------
            # Fallback
            # ------------------------------------------------

            if selected_device is None:

                selected_device = (
                    device_list[0]
                )

            # ------------------------------------------------
            # USB permission
            # ------------------------------------------------

            if not usb.has_usb_permission(
                selected_device
            ):

                usb.request_usb_permission(
                    selected_device
                )

                self._notify_status(
                    "WAITING FOR USB PERMISSION"
                )

                raise SerialReaderError(
                    "WAITING FOR USB PERMISSION"
                )

            # ------------------------------------------------
            # OPEN SERIAL
            # ------------------------------------------------

            device_name = (
                selected_device.getDeviceName()
            )

            self._connection = (
                serial4a.get_serial_port(
                    device_name,
                    SERIAL_BAUDRATE,
                    8,
                    "N",
                    1
                )
            )

            if self._connection is None:

                raise SerialReaderError(
                    "SERIAL PORT ERROR"
                )

            # ------------------------------------------------
            # DTR / RTS
            # ------------------------------------------------

            try:

                self._connection.dtr = True

            except Exception:

                pass

            try:

                self._connection.rts = True

            except Exception:

                pass

            # ------------------------------------------------
            # Serial timeout
            # ------------------------------------------------

            try:

                self._connection.timeout = 0.1

            except Exception:

                pass

            self._notify_status(
                "USB CONNECTED"
            )

        except SerialReaderError:

            raise

        except Exception as exc:

            log_exception(
                "ANDROID USB OPEN"
            )

            raise SerialReaderError(
                f"USB CONNECTION FAILED: {exc}"
            ) from exc

    # --------------------------------------------------------
    # DESKTOP SERIAL
    # --------------------------------------------------------

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
                f"DESKTOP SERIAL ERROR: {exc}"
            ) from exc

    # --------------------------------------------------------
    # POLL
    # --------------------------------------------------------

    def poll(self):

        raw_bytes = (
            self._read_available_bytes()
        )

        if not raw_bytes:

            return

        self._rx_buffer += raw_bytes

        while b"\n" in self._rx_buffer:

            line_bytes, self._rx_buffer = (
                self._rx_buffer.split(
                    b"\n",
                    1
                )
            )

            try:

                line = (
                    line_bytes
                    .decode(
                        "ascii",
                        errors="ignore"
                    )
                    .strip()
                )

            except Exception:

                continue

            if not line:

                continue

            # --------------------------------------------
            # Arduino sends INTEGER millimeters
            # --------------------------------------------

            try:

                value_mm = int(line)

            except ValueError:

                continue

            if value_mm < 0:

                continue

            if self.on_value is not None:

                self.on_value(
                    value_mm
                )

    # --------------------------------------------------------
    # READ BYTES
    # --------------------------------------------------------

    def _read_available_bytes(self):

        # ====================================================
        # ANDROID
        # ====================================================

        if self._is_android:

            if self._connection is None:

                return b""

            try:

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

                    return (
                        self._connection
                        .read(waiting)
                        or b""
                    )

                return (
                    self._connection
                    .read(256)
                    or b""
                )

            except Exception:

                if not self._read_error_logged:

                    self._read_error_logged = True

                    log_exception(
                        "ANDROID SERIAL READ"
                    )

                return b""

        # ====================================================
        # DESKTOP
        # ====================================================

        if self._serial_port is None:

            return b""

        try:

            waiting = (
                self._serial_port.in_waiting
            )

            if waiting <= 0:

                return b""

            return (
                self._serial_port.read(
                    waiting
                )
                or b""
            )

        except Exception:

            if not self._read_error_logged:

                self._read_error_logged = True

                log_exception(
                    "DESKTOP SERIAL READ"
                )

            return b""

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    def _notify_status(
        self,
        message
    ):

        if self.on_status is not None:

            self.on_status(
                message
            )

    # --------------------------------------------------------
    # CLOSE
    # --------------------------------------------------------

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


# ============================================================
# DMETER APP
# ============================================================

class DmeterApp(App):

    title = "Dmeter"

    # --------------------------------------------------------
    # BUILD
    # --------------------------------------------------------

    def build(self):

        log_event(
            "build() started"
        )

        Window.clearcolor = (
            0,
            0,
            0,
            1
        )

        self.root_layout = (
            FloatLayout()
        )

        # ====================================================
        # AMIRMEDK WATERMARK
        # ====================================================

        self.watermark_label = Label(

            text=(
                "[b]"
                "\u25B6  AmirMEDK"
                "[/b]"
            ),

            markup=True,

            color=(
                1,
                1,
                1,
                0.14
            ),

            font_size="60sp",

            bold=True,

            size_hint=(
                0.6,
                None
            ),

            height="110dp",

            pos_hint={
                "center_x": 0.5,
                "top": 0.98
            },

            halign="center",

            valign="middle"
        )

        self.watermark_label.bind(

            size=lambda instance, size:
                setattr(
                    instance,
                    "text_size",
                    size
                )

        )

        self.root_layout.add_widget(
            self.watermark_label
        )

        self._resize_watermark_font()

        Window.bind(
            size=lambda *args:
                self._resize_watermark_font()
        )

        # ====================================================
        # BIG NUMBER
        # ====================================================

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

            halign="center",

            valign="middle"
        )

        self.root_layout.add_widget(
            self.value_label
        )

        # ====================================================
        # STATUS
        # ====================================================

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

        # ====================================================
        # SERIAL READER
        # ====================================================

        self.reader = SerialReader(

            on_value=self._on_value,

            on_status=self._on_status
        )

        self._connected = False

        # ====================================================
        # ANDROID PERMISSIONS
        # ====================================================

        if platform == "android":

            self._request_android_permissions()

        # ====================================================
        # START CONNECTION
        # ====================================================

        Clock.schedule_once(
            self._try_connect,
            0.3
        )

        # ====================================================
        # POLLING
        # ====================================================

        Clock.schedule_interval(
            self._poll_loop,
            UI_UPDATE_INTERVAL
        )

        log_event(
            "build() finished"
        )

        return self.root_layout

    # --------------------------------------------------------
    # WATERMARK SIZE
    # --------------------------------------------------------

    def _resize_watermark_font(
        self
    ):

        try:

            self.watermark_label.font_size = max(
                24,
                Window.width * 0.055
            )

        except Exception:

            pass

    # --------------------------------------------------------
    # ANDROID PERMISSION
    # --------------------------------------------------------

    def _request_android_permissions(
        self
    ):

        try:

            from android.permissions import (
                request_permissions
            )

            request_permissions([])

        except Exception:

            pass

    # --------------------------------------------------------
    # CONNECT
    # --------------------------------------------------------

    def _try_connect(
        self,
        dt
    ):

        try:

            self.reader.open()

            self._connected = True

            self.status_label.text = (
                "USB OPEN - WAITING FOR DATA"
            )

            log_event(
                "reader.open() succeeded"
            )

        except SerialReaderError as exc:

            self._connected = False

            self.status_label.text = str(
                exc
            )[:48]

            Clock.schedule_once(
                self._try_connect,
                SERIAL_RECONNECT_DELAY
            )

        except Exception:

            self._connected = False

            log_exception(
                "CONNECT"
            )

            self.status_label.text = (
                "CONNECTION ERROR"
            )

            Clock.schedule_once(
                self._try_connect,
                SERIAL_RECONNECT_DELAY
            )

    # --------------------------------------------------------
    # STATUS CALLBACK
    # --------------------------------------------------------

    def _on_status(
        self,
        message
    ):

        pass

    # --------------------------------------------------------
    # VALUE CALLBACK
    # --------------------------------------------------------

    def _on_value(
        self,
        value_mm
    ):

        # Arduino sends millimeters.
        # Phone only converts mm -> cm.

        value_cm = (
            value_mm / 10.0
        )

        self.value_label.text = (
            f"{value_cm:.1f}"
        )

        self.status_label.text = (
            "LIVE"
        )

    # --------------------------------------------------------
    # POLL LOOP
    # --------------------------------------------------------

    def _poll_loop(
        self,
        dt
    ):

        try:

            if self._connected:

                self.reader.poll()

        except Exception:

            log_exception(
                "POLL LOOP"
            )

    # -------------------
