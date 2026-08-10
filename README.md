# Dmeter

A minimal digital meter: an Arduino UNO R3 + HC-SR04 ultrasonic sensor
mounted at a fixed 2-meter (200cm) distance measures how far something
intrudes into that 2-meter zone, and a phone app displays that single
number - big, white, on a black background - connected over USB/OTG.

**Formula (computed entirely on the Arduino, the phone only displays it):**

```
value_cm = 200 - measured_distance_cm      (clamped to 0..200)
```

- Nothing in the way (sensor reads ~200cm) -> displays `0.0`
- Something 20cm from the sensor -> displays `180.0`

A new value is measured and sent every 100ms, as a whole number of
millimeters over serial (e.g. `1800` for 180.0cm) - the phone divides by
10 and shows one decimal place in cm.

## Project structure

```
Dmeter/
├── app/
│   └── main.py             # the entire Kivy app (single file, on purpose)
├── firmware/
│   └── Dmeter.ino          # Arduino firmware (standalone, no phone required to run)
├── .github/workflows/build_apk.yml   # builds the APK automatically via GitHub Actions
├── buildozer.spec
├── requirements.txt
└── README.md
```

## Wiring

| HC-SR04 pin | Arduino pin |
|---|---|
| VCC | 5V |
| GND | GND |
| TRIG | D9 |
| ECHO | D10 |

## Building the APK

Same pipeline as any Buildozer/GitHub Actions project:

1. Push this repo to GitHub.
2. Go to the Actions tab -> "Build Dmeter APK" -> Run workflow (or just
   push to `main`, which triggers it automatically).
3. Once it finishes, download the `dmeter-apk` artifact from that run.
4. Copy the APK to the phone, enable "install from unknown sources", and
   install it.

## Note on testing in this sandbox

Both files were written and reviewed carefully, but this sandbox has no
internet access and no Arduino IDE / Kivy installed, so neither the
firmware nor the app could be compiled here. Verify the `.ino` in the
Arduino IDE before uploading, and let the GitHub Actions build confirm
the app compiles.
