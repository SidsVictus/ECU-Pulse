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

**OBD2 compatibility** - Works with any ELM327 based OBD2 adapter.
This covers the vast majority of adapters
available on Amazon and electronics shops.

**Compatible connection types:**
-USB (recommended)
-Bluetooth ELM327 v1.5

**Compatible vehicles:**
-Any bike or car with fuel injection (FI)
-Most vehicles manufactured after 2010
-Carburettor engines are not supported

Download: Available in
Releases as **Version 1.0.0**

Steps:

Download ECU_OBD2_Bridge.exe
Plug OBD2 cable into your bike or car
Plug USB end into your laptop
Double-click ECU_OBD2_Bridge.exe
Open the dashboard and select Live OBD2 Mode
*For devs who are interested in seeing obd2 working in python, 
open **obd2_bridge.py** in your system and the terminal will open.*

**Windows SmartScreen:**
Windows may show a warning when running the file.
Click More info then Run anyway.
This is normal for new applications without a
paid code signing certificate.




**License**
MIT License — free to use, modify and distribute.

*Built as an engineering project for real-time IC engine monitoring via OBD2 diagnostics.*
