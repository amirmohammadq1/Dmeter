[app]

title = Dmeter
package.name = dmeter
package.domain = org.dmeter

source.dir = .
source.include_exts = py,png,jpg,jpeg
source.exclude_dirs = firmware,.github,.buildozer,bin,.git

version = 1.0

requirements = python3,kivy==2.3.1,pyserial,usb4a,usbserial4a

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
