<p align="center">
  <a href="https://ecupulse.surge.sh">
    <img src="font/gear-wheel-readme.svg" alt="ECU Pulse" width="100">
  </a>
</p>

<h1 align="center">ECU Pulse</h1>

<p align="center">
  Real-time engine monitoring dashboard for bikes and cars.
</p>

<p align="center">
  <a href="https://ecupulse.surge.sh">Dashboard</a>
  &nbsp;&bull;&nbsp;
  <a href="https://github.com/SidsVictus/ECU-Pulse/blob/main/ECU-Pulse.pdf">Documentation</a>
  &nbsp;&bull;&nbsp;
  <a href="https://github.com/SidsVictus/ECU-Pulse/releases">Releases</a>
</p>

---

## About

ECU Pulse connects to any ELM327 OBD2 adapter and displays live engine data in a browser-based dashboard. It reads sensor data in real time. If no adapter is connected, it runs a physics-based simulation that mimics real engine behavior.

## Features

- **Live Sensor Data** — RPM, speed, engine temp, exhaust temp, throttle, battery, AFR, and more
- **Interactive Charts** — RPM timeline, temperature profile, load & throttle, riding mode breakdown
- **Engine Health Score** — Aggregated from engine, thermal, fueling, electrical, and mechanical subsystems
- **CSV Import & Export** — Record sessions and replay them later
- **Adjustable Speed** — 0.25x to 2x playback control
- **Mobile Responsive** — Works on phones, tablets, and desktops

## Getting Started

### Live Mode (OBD2)

1. Download [`ECU_OBD2_Bridge.exe`](https://github.com/SidsVictus/ECU-Pulse/releases/latest/download/ECU_OBD2_Bridge.exe) from releases
2. Plug the OBD2 adapter into your vehicle and connect the USB end to your laptop
3. Run `ECU_OBD2_Bridge.exe`
4. Open the [dashboard](https://ecupulse.surge.sh/dashboard) and select **Live OBD2**

### Simulation Mode

1. Open the [dashboard](https://ecupulse.surge.sh/dashboard)
2. Select **Simulation**
3. Feel the engineering visually without any hardware connected

## Compatibility

| | Details |
|---|---|
| **Adapter** | Any ELM327-based OBD2 adapter (USB recommended) |
| **Vehicles** | Fuel-injected bikes and cars, mostly post-2010 |
| **OS** | Windows (for the bridge), any OS for the dashboard |

## Note for Explorers
To see the cool ass backend running, download the [`obd2_bridge.py`], 
double click the file and voila~

## License

Distributed under the MIT License. 
