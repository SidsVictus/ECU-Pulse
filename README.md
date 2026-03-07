# ECU Dashboard

A real-time engine monitoring dashboard for bikes and cars.
Connects to any ELM327 OBD2 adapter to display live engine
data, or runs in demo mode with simulated engine data.


## What it does

- Displays live RPM, speed, engine temperature, exhaust temperature,
  engine load, throttle position, gear, battery voltage and more
- RPM chart with redline marker
- Temperature profile for engine and exhaust
- Riding conditions breakdown
- Engine load over time
- Engine health score bars
- Exports all session data to CSV
- Adjustable refresh rate —> 0.5s, 1s, 2s
- Demo mode — no hardware required
- Live OBD2 mode — real bike or car data

---

## How it works:
The dashboard has two parts:

**Frontend** — React web app hosted online.
Anyone can open it in a browser with no installation.

**OBD2 Bridge** — A small Python program that runs on
the user's laptop. It reads the OBD2 adapter plugged
into the bike or car and streams data to the dashboard.
If no adapter is found it automatically switches to
simulation mode within 3 seconds of checking all the COMS of your system.

---

OBD2 Bridge
The bridge program reads your OBD2 adapter and
sends data to the dashboard.

Download: Available in
Releases

Steps:

Download ECU_OBD2_Bridge.exe
Plug OBD2 cable into your bike or car
Plug USB end into your laptop
Double-click ECU_OBD2_Bridge.exe
Open the dashboard and select Live OBD2 Mode
Windows SmartScreen:
Windows may show a warning when running the file.
Click More info then Run anyway.
This is normal for new applications without a
paid code signing certificate.
