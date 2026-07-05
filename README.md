# ⚙ ECU Dashboard — IC Engine Real-Time Monitor

A dashboard for monitoring IC engine data in real time
via OBD2 diagnostic adapter. Built with **Python (Flask)** backend and **React** frontend.

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  YOUR SYSTEM (connected to OBD2 adapter)                    │
│                                                             │
│  obd2_bridge.py  ←── reads OBD2 USB adapter (COM port)      │
│       │                                                     │
│       └──► streams JSON to ──► http://localhost:8765/data   │
│                                        │                    │
│  dashboard_server.py (Flask API)  ←────┘                    │
│       └──► serves data to ──► React dashboard (browser)     │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 File Structure

```
ecu-dashboard/
│
├── 🐍 PYTHON (core brain)
│   ├── dashboard_server.py     Flask API + engine simulation
│   ├── obd2_bridge.py          OBD2 reader + local HTTP bridge
│   ├── simulate_engine.py      Standalone terminal simulator
│   ├── requirements.txt        Python dependencies
│   ├── build_exe.bat           Build obd2_bridge.exe (Windows)
│   └── build_exe.sh            Build obd2_bridge binary (Mac/Linux)
│
├── ⚛️  REACT (visual layer)
│   ├── src/App.tsx              Main dashboard layout
│   ├── src/components/          Charts, gauges, health panels
│   ├── src/hooks/               Engine data hook (JS simulation)
│   └── src/index.css            Dark theme styles
│
└── 📄 OTHER
    ├── index.html               Entry point
    ├── package.json             Node dependencies
    └── vite.config.ts           Vite build config
```

---

## 🚀 Quick Start

### Option A — Full Python Backend (Recommended)

```bash
# 1. Install Python dependencies
pip install flask flask-cors obd

# 2. Start the Flask API server
python dashboard_server.py

# 3. Open browser
# http://localhost:5000
```

### Option B — Demo Mode (No Hardware)

```bash
# Just open the React dashboard in your browser
# Click "Demo Mode" in the popup — no Python needed
npm install && npm run dev
# http://localhost:5173
```

### Option C — Terminal Simulator

```bash
python simulate_engine.py                           # default 2s
python simulate_engine.py --interval 0.5            # fast mode
python simulate_engine.py --mode highway            # force mode
python simulate_engine.py --duration 120 --output session.csv
```

---

## 🔌 Real OBD2 Setup (Live Data)

### Step 1 — Hardware
- Plug OBD2 diagnostic cable into vehicle's OBD2 port
- Plug USB end into your laptop
- Turn ignition ON

### Step 2 — Run the Bridge

```bash
# Install python-obd
pip install obd

# Run bridge (auto-detects COM port)
python obd2_bridge.py

# Or force a specific port
python obd2_bridge.py --port COM4          # Windows
python obd2_bridge.py --port /dev/ttyUSB0  # Linux/Mac
```

### Step 3 — Open Dashboard
Open the dashboard in your browser and select **Live OBD2 Mode**.

---

## 📦 Build the OBD2 Bridge .exe (for Users)

Users don't need Python — give them the compiled `.exe`:

```bash
# Windows — double-click build_exe.bat
# OR run manually:
pip install pyinstaller
pyinstaller --onefile --noconsole --name ECU_OBD2_Bridge obd2_bridge.py

# Output: dist/ECU_OBD2_Bridge.exe
```

Upload `dist/ECU_OBD2_Bridge.exe` to **GitHub Releases**.
Update the download URL in `src/components/OBDModal.tsx`.

---

## 🌐 Deploying Online (GitHub Releases + Cloud)

```
Step 1: Push code to GitHub
        github.com/YOUR_USERNAME/ecu-dashboard

Step 2: Build and upload the bridge .exe
        GitHub → Releases → New Release → Upload ECU_OBD2_Bridge.exe

Step 3: Deploy the React frontend
        Any static host: Netlify / Cloudflare Pages / GitHub Pages
        npm run build → upload the /dist folder

Step 4: Deploy the Python backend (optional)
        Railway / Render / Fly.io — free tiers available
        python dashboard_server.py

Step 5: Users
        → Open your website URL
        → Download ECU_OBD2_Bridge.exe (one time, ~18MB)
        → Double-click it, plug in OBD2 cable, done ✅
```

---

## 📊 Dashboard Features

| Feature | Description |
|---------|-------------|
| RPM Chart | Real-time RPM with redline marker at 9500 RPM |
| Temperature Profile | Engine + Exhaust + Coolant temperatures |
| Riding Conditions | Pie chart — Idle / City / Highway / Aggressive / Decel |
| Engine Load | Load % + Throttle position over time |
| Health Scores | 5-factor scoring: Engine, Thermal, Fueling, Electrical, Mechanical |
| Live Sensors | All ECU readings — AFR, oil pressure, battery, vibration etc |
| Alerts Bar | Auto-detected warnings and critical alerts |
| CSV Export | Export full session data with one click |
| Refresh Rate | Choose 0.5s / 1s / 2s update interval |
| Settings | Toggle visible metrics, dark grid, mode switch |

---

## 🐍 Python API Endpoints (dashboard_server.py)

| Endpoint | Description |
|----------|-------------|
| `GET /api/current` | Latest single data snapshot |
| `GET /api/history?n=60` | Last N snapshots |
| `GET /api/health` | Health scores + alerts |
| `GET /api/conditions` | Riding conditions breakdown |
| `GET /api/peaks` | Session peak/min values |
| `GET /api/export` | Download CSV of full session |
| `GET /api/status` | Server status |

---

## ⚠️ Supported OBD2 PIDs

Standard OBD2 PIDs available on most vehicles (ISO 15765-4 / CAN):

- `RPM` — Engine revolutions per minute
- `SPEED` — Vehicle speed (km/h)
- `COOLANT_TEMP` — Engine coolant temperature
- `ENGINE_LOAD` — Calculated engine load %
- `THROTTLE_POS` — Throttle position %
- `INTAKE_TEMP` — Intake air temperature
- `MAF` — Mass air flow sensor
- `SHORT_FUEL_TRIM_1` / `LONG_FUEL_TRIM_1` — Fuel trim (for AFR)
- `FUEL_LEVEL` — Fuel tank level %
- `RUN_TIME` — Engine run time since start

> Note: Exhaust Gas Temperature (EGT), oil pressure, fuel pressure and
> vibration are not available via standard OBD2. These require proprietary
> manufacturer PIDs or additional sensors.

---

## 📄 License

MIT — Free to use, modify and distribute.
