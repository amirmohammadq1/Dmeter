[app]

title = Dmeter
package.name = dmeter
package.domain = org.dmeter

source.dir = .
source.include_exts = py,png,jpg,jpeg
source.exclude_dirs = firmware,.github,.buildozer,bin,.git

version = 1.0

requirements = python3,kivy==2.3.1,pyjnius,pyserial,usb4a,usbserial4a

orientation = landscape
fullscreen = 1

# --------------------------------------------------------------------
# All android.* keys MUST stay under [app] - buildozer does NOT support
# a separate [app:android] section. (This mistake broke an earlier
# project's build - keeping everything under [app] here from the start.)
# --------------------------------------------------------------------
android.api = 34
android.minapi = 24
android.sdk = 34
android.ndk = 25b
android.archs = arm64-v8a

# --------------------------------------------------------------------
# Required for usb4a/usbserial4a to actually be able to READ from a USB
# serial device (not just detect it and ask for permission, which can
# work without these - reading silently fails without them). Per the
# libraries' own build instructions:
#   https://github.com/jacklinquan/usb4a
#   https://github.com/jacklinquan/usbserial4a
# --------------------------------------------------------------------

# termios.so is stripped from the APK by python-for-android's whitelist
# mechanism unless explicitly kept - pyserial/usbserial4a need it.
android.p4a_whitelist = lib-dynload/termios.so

# Declares <uses-feature android:name="android.hardware.usb.host" />
# inside <manifest> - without this, USB host access is unreliable on
# some devices/Android versions even if a permission dialog appears.
android.extra_manifest_xml = manifest/extra_manifest.xml

# Notifies the app when a USB device is attached, and points Android at
# device_filter.xml (below) to say which devices to offer to this app.
android.manifest.intent_filters = manifest/intent-filter.xml

# Copies device_filter.xml into res/xml/ where intent-filter.xml expects
# to find it (@xml/device_filter) - lists known Arduino/CH340/FTDI/etc.
# vendor and product IDs.
android.res_xml = manifest/device_filter.xml

# Only USB Host is needed (for OTG). Android shows its own permission
# dialog when the USB device is attached; usb4a/usbserial4a handle the
# necessary intent-filter themselves, so no extra manifest permission
# is required here.
android.permissions =

android.accept_sdk_license = True
android.release_artifact = apk

[buildozer]

log_level = 2
warn_on_root = 1
