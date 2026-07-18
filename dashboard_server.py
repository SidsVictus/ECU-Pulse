"""
ECU Live Dashboard — Python Flask Backend
==========================================
Serves the dashboard data API and bridges OBD2 adapter readings.
Can run in SIMULATION mode (no hardware needed) or LIVE OBD2 mode.

Usage:
    python dashboard_server.py                     # simulation mode, port 5000
    python dashboard_server.py --mode live         # live OBD2 mode
    python dashboard_server.py --port 8080         # custom port
    python dashboard_server.py --interval 0.5      # faster simulation

Install:
    pip install flask flask-cors obd flask-limiter
"""

import argparse
import json
import math
import os
import random
import secrets
import threading
import time
from collections import deque
from datetime import datetime
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ─────────────────────────────────────────────────────────────────────────────
# Security Configuration
# ─────────────────────────────────────────────────────────────────────────────
def get_secret_key():
    """Generate or load cryptographically secure secret key."""
    env_key = os.environ.get("ECU_DASHBOARD_SECRET_KEY")
    if env_key:
        return env_key
    # Generate persistent key file for consistency across restarts
    key_file = os.path.join(os.path.dirname(__file__), ".secret_key")
    try:
        with open(key_file, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        key = secrets.token_urlsafe(32)
        with open(key_file, "w") as f:
            f.write(key)
        os.chmod(key_file, 0o600)
        return key

def get_allowed_origins():
    """Parse allowed origins from environment variable."""
    origins = os.environ.get("ECU_ALLOWED_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000")
    return [o.strip() for o in origins.split(",") if o.strip()]

def get_rate_limits():
    """Parse rate limits from environment variable."""
    default = "200 per minute, 50 per second"
    limits = os.environ.get("ECU_RATE_LIMITS", default)
    return [l.strip() for l in limits.split(",")]

# ─────────────────────────────────────────────────────────────────────────────
# CLI Arguments
# ─────────────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="ECU Dashboard Python Server")
parser.add_argument("--mode", default="simulation", choices=["simulation", "live"],
                    help="Data source mode: simulation or live OBD2")
parser.add_argument("--port", type=int, default=5000, help="Server port")
parser.add_argument("--interval", type=float, default=1.0, help="Simulation tick interval (seconds)")
parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
parser.add_argument("--enable-debug", action="store_true", help="Enable debug mode (DANGEROUS in production)")
args, _ = parser.parse_known_args()

# ─────────────────────────────────────────────────────────────────────────────
# Flask App Setup — Hardened
# ─────────────────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="dist", static_url_path="/")
app.config.update(
    SECRET_KEY=get_secret_key(),
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=3600,
    MAX_CONTENT_LENGTH=1024 * 1024,  # 1MB max request
)

# CORS — Restrict to configured origins
CORS(app,
     origins=get_allowed_origins(),
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "OPTIONS"],
     supports_credentials=False,
     max_age=3600)

# Rate Limiter — Strict defaults
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=get_rate_limits(),
    storage_uri="memory://",
    strategy="fixed-window",
    headers_enabled=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Security Headers Middleware
# ─────────────────────────────────────────────────────────────────────────────
@app.after_request
def add_security_headers(response):
    """Apply comprehensive security headers to all responses."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self' ws: wss:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    # HSTS for HTTPS (only enforce if not localhost)
    if request.host.split(":")[0] not in ("localhost", "127.0.0.1"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    # Remove server fingerprinting
    response.headers.pop("Server", None)
    return response

# ─────────────────────────────────────────────────────────────────────────────
# Input Validation Helpers
# ─────────────────────────────────────────────────────────────────────────────
def validate_int_param(param_name: str, default: int, min_val: int, max_val: int) -> int:
    """Safely parse and validate integer query parameter."""
    try:
        value = int(request.args.get(param_name, default))
        return max(min_val, min(max_val, value))
    except (ValueError, TypeError):
        return default

def validate_float_param(param_name: str, default: float, min_val: float, max_val: float) -> float:
    """Safely parse and validate float query parameter."""
    try:
        value = float(request.args.get(param_name, default))
        return max(min_val, min(max_val, value))
    except (ValueError, TypeError):
        return default

# ─────────────────────────────────────────────────────────────────────────────
# Shared State (thread-safe)
# ─────────────────────────────────────────────────────────────────────────────
MAX_HISTORY = 500
session_start = time.time()
history = deque(maxlen=MAX_HISTORY)
history_lock = threading.Lock()
latest_snap = {}
peak_rpm = 0
min_rpm = float('inf')
peak_temp = 0
peak_load = 0
condition_counts = {"idle": 0, "city": 0, "highway": 0, "aggressive": 0, "decel": 0}

# ─────────────────────────────────────────────────────────────────────────────
# Engine Physics Simulation (unchanged logic)
# ─────────────────────────────────────────────────────────────────────────────
REDLINE = 9500

MODE_TARGETS = {
    "idle":       {"rpm": 950,  "load": 8,  "throttle": 4},
    "city":       {"rpm": 2800, "load": 38, "throttle": 30},
    "highway":    {"rpm": 4200, "load": 62, "throttle": 55},
    "aggressive": {"rpm": 7800, "load": 91, "throttle": 88},
    "decel":      {"rpm": 1200, "load": 5,  "throttle": 1},
}

MODE_TRANSITIONS = {
    "idle":       ["idle", "city", "city"],
    "city":       ["city", "city", "highway", "aggressive", "decel", "idle"],
    "highway":    ["highway", "highway", "city", "aggressive", "decel"],
    "aggressive": ["aggressive", "highway", "city", "decel"],
    "decel":      ["decel", "city", "idle"],
}

class EngineSimulator:
    def __init__(self):
        self.mode = "idle"
        self.mode_timer = 0
        self.rpm = 950.0
        self.engine_temp = 68.0
        self.exhaust_temp = 120.0
        self.engine_load = 8.0
        self.throttle = 4.0
        self.speed = 0.0
        self.fuel_level = 100.0
        self.coolant_temp = 68.0
        self.intake_air = 28.0

    def _clamp(self, v, lo, hi):
        return max(lo, min(hi, v))

    def _lerp(self, a, b, t):
        return a + (b - a) * t

    def _jitter(self, v, rng):
        return v + (random.random() - 0.5) * rng * 2

    def _pick_mode(self):
        opts = MODE_TRANSITIONS[self.mode]
        return random.choice(opts)

    def _compute_gear(self, speed):
        if speed < 15:  return 1
        if speed < 30:  return 2
        if speed < 55:  return 3
        if speed < 80:  return 4
        if speed < 110: return 5
        return 6

    def tick(self):
        self.mode_timer -= 1
        if self.mode_timer <= 0:
            self.mode = self._pick_mode()
            self.mode_timer = random.randint(4, 12)

        t = MODE_TARGETS[self.mode]

        self.rpm = self._clamp(self._lerp(self.rpm, self._jitter(t["rpm"], 60), 0.18), 600, REDLINE)
        self.engine_load = self._clamp(self._lerp(self.engine_load, self._jitter(t["load"], 2), 0.15), 0, 100)
        self.throttle = self._clamp(self._lerp(self.throttle, self._jitter(t["throttle"], 2), 0.20), 0, 100)

        target_speed = (self.rpm / REDLINE) * 160 * (t["load"] / 100) * 1.4
        self.speed = self._clamp(self._lerp(self.speed, self._jitter(target_speed, 3), 0.12), 0, 180)

        heat_in = self.engine_load * 0.012 + self.rpm * 0.00004
        heat_out = (self.engine_temp - 22) * 0.025
        self.engine_temp = self._clamp(self.engine_temp + heat_in - heat_out + self._jitter(0, 0.3), 60, 130)
        self.coolant_temp = self._clamp(self.engine_temp - self._jitter(3, 1.5), 55, 125)

        egt_target = 90 + self.engine_load * 7.5 + (self.rpm / REDLINE) * 300
        self.exhaust_temp = self._clamp(self._lerp(self.exhaust_temp, self._jitter(egt_target, 15), 0.10), 80, 900)

        self.intake_air = self._clamp(self.intake_air + self._jitter(0, 0.05), 20, 55)
        self.fuel_level = self._clamp(self.fuel_level - 0.0003 * (self.engine_load / 100), 0, 100)

        oil_pressure = self._clamp(1.2 + (self.rpm / REDLINE) * 4.8 + self._jitter(0, 0.2), 0, 7)
        fuel_pressure = self._clamp(2.8 + self._jitter(0, 0.15), 1, 5)
        battery_voltage = self._clamp(13.8 + self._jitter(0, 0.12) - (0.4 if self.engine_load > 80 else 0), 10, 15)
        afr = self._clamp(14.7 + (-0.8 if self.mode == "aggressive" else 0) + self._jitter(0, 0.3), 10, 20)
        vibration = self._clamp(0.5 + (self.rpm / REDLINE) * 6 + self._jitter(0, 0.4), 0, 10)
        map_sensor = self._clamp(30 + self.engine_load * 0.65 + self._jitter(0, 2), 15, 105)
        gear = self._compute_gear(self.speed)

        return {
            "timestamp": round(time.time() * 1000),
            "elapsed_s": round(time.time() - session_start, 2),
            "mode": self.mode,
            "rpm": round(self.rpm),
            "speed": round(self.speed, 1),
            "gear": gear,
            "engine_temp": round(self.engine_temp, 1),
            "exhaust_temp": round(self.exhaust_temp, 1),
            "coolant_temp": round(self.coolant_temp, 1),
            "intake_air_temp": round(self.intake_air, 1),
            "engine_load": round(self.engine_load, 1),
            "throttle": round(self.throttle, 1),
            "oil_pressure": round(oil_pressure, 2),
            "fuel_pressure": round(fuel_pressure, 2),
            "battery_voltage": round(battery_voltage, 2),
            "afr": round(afr, 2),
            "map_sensor": round(map_sensor, 1),
            "vibration": round(vibration, 2),
            "fuel_level": round(self.fuel_level, 2),
        }

# ─────────────────────────────────────────────────────────────────────────────
# Health Scoring (unchanged logic)
# ─────────────────────────────────────────────────────────────────────────────
def compute_health(snaps):
    if not snaps:
        return {"engine": 100, "thermal": 100, "fueling": 100, "electrical": 100, "mechanical": 100, "overall": 100}

    last = snaps[-1]
    recent = snaps[-30:]
    avg_load = sum(s["engine_load"] for s in recent) / len(recent)
    max_egt = max(s["exhaust_temp"] for s in recent)

    engine = max(0, min(100, 100 - (max(0, avg_load - 85) * 2) - (10 if last["rpm"] > 8500 else 0)))
    thermal = max(0, min(100, 100 - max(0, last["engine_temp"] - 95) * 2 - max(0, max_egt - 680) * 0.15))
    fueling = max(0, min(100, 100 - abs(last["afr"] - 14.7) * 4 - (12 if last["fuel_pressure"] < 2.5 else 0)))
    electrical = max(0, min(100, 100 - (20 if last["battery_voltage"] < 12.0 else 8 if last["battery_voltage"] < 12.5 else 0)))
    mechanical = max(0, min(100, 100 - (max(0, last["vibration"] - 5) * 6) - (15 if last["oil_pressure"] < 2 else 0)))
    overall = round((engine + thermal + fueling + electrical + mechanical) / 5)

    return {
        "engine": round(engine),
        "thermal": round(thermal),
        "fueling": round(fueling),
        "electrical": round(electrical),
        "mechanical": round(mechanical),
        "overall": overall,
    }

def compute_alerts(snap, health):
    alerts = []
    if snap["engine_temp"] > 105:       alerts.append({"type": "crit", "msg": "Engine temp critical — check coolant"})
    if snap["exhaust_temp"] > 750:      alerts.append({"type": "warn", "msg": "Exhaust temp high — ease throttle"})
    if snap["rpm"] > REDLINE * 0.93:    alerts.append({"type": "crit", "msg": "Approaching redline!"})
    if snap["battery_voltage"] < 12.0:  alerts.append({"type": "warn", "msg": "Low battery voltage"})
    if snap["oil_pressure"] < 1.8:      alerts.append({"type": "crit", "msg": "Low oil pressure"})
    if snap["afr"] < 12.5:              alerts.append({"type": "warn", "msg": "Rich mixture detected"})
    if snap["afr"] > 16.0:              alerts.append({"type": "warn", "msg": "Lean mixture detected"})
    if health["overall"] >= 90 and not alerts:
        alerts.append({"type": "good", "msg": "Engine operating normally"})
    return alerts

def compute_conditions():
    total = sum(condition_counts.values()) or 1
    return {k: round((v / total) * 100) for k, v in condition_counts.items()}

# ─────────────────────────────────────────────────────────────────────────────
# OBD2 Live Reader (unchanged logic)
# ─────────────────────────────────────────────────────────────────────────────
def try_obd2_read():
    """
    Attempt to read live data from an OBD2 adapter.
    Returns a dict of sensor values or None if not available.
    Install: pip install obd
    """
    try:
        import obd
        connection = obd.OBD()
        if not connection.is_connected():
            return None

        def q(cmd):
            r = connection.query(obd.commands[cmd])
            return r.value.magnitude if r and not r.is_null() else None

        rpm = q("RPM")
        speed = q("SPEED")
        engine_temp = q("COOLANT_TEMP")
        engine_load = q("ENGINE_LOAD")
        throttle = q("THROTTLE_POS")

        if rpm is None:
            return None

        return {
            "timestamp": round(time.time() * 1000),
            "elapsed_s": round(time.time() - session_start, 2),
            "mode": "live",
            "rpm": round(float(rpm)),
            "speed": round(float(speed), 1) if speed else 0,
            "gear": 1,
            "engine_temp": round(float(engine_temp), 1) if engine_temp else 0,
            "exhaust_temp": 0,
            "coolant_temp": round(float(engine_temp), 1) if engine_temp else 0,
            "intake_air_temp": 0,
            "engine_load": round(float(engine_load), 1) if engine_load else 0,
            "throttle": round(float(throttle), 1) if throttle else 0,
            "oil_pressure": 0,
            "fuel_pressure": 0,
            "battery_voltage": 0,
            "afr": 14.7,
            "map_sensor": 0,
            "vibration": 0,
            "fuel_level": 0,
        }
    except Exception:
        return None

# ─────────────────────────────────────────────────────────────────────────────
# Background Data Thread
# ─────────────────────────────────────────────────────────────────────────────
simulator = EngineSimulator()

def data_loop():
    global latest_snap, peak_rpm, min_rpm, peak_temp, peak_load

    while True:
        snap = None

        if args.mode == "live":
            snap = try_obd2_read()

        if snap is None:
            snap = simulator.tick()

        with history_lock:
            history.append(snap)
            latest_snap = snap
            condition_counts[snap["mode"]] = condition_counts.get(snap["mode"], 0) + 1

        peak_rpm = max(peak_rpm, snap["rpm"])
        min_rpm = min(min_rpm, snap["rpm"])
        peak_temp = max(peak_temp, snap["engine_temp"])
        peak_load = max(peak_load, snap["engine_load"])

        time.sleep(args.interval)

# ─────────────────────────────────────────────────────────────────────────────
# Flask API Routes — Rate Limited & Validated
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/current")
@limiter.limit("100 per minute")
def api_current():
    """Latest single snapshot"""
    with history_lock:
        snap = dict(latest_snap) if latest_snap else {}
    return jsonify(snap)

@app.route("/api/history")
@limiter.limit("60 per minute")
def api_history():
    """Recent history (last N samples) — validated input"""
    n = validate_int_param("n", 60, 1, MAX_HISTORY)
    with history_lock:
        snaps = list(history)[-n:]
    return jsonify(snaps)

@app.route("/api/health")
@limiter.limit("60 per minute")
def api_health():
    """Health scores computed from recent history"""
    with history_lock:
        snaps = list(history)
    health = compute_health(snaps)
    alerts = compute_alerts(latest_snap, health) if latest_snap else []
    return jsonify({"health": health, "alerts": alerts})

@app.route("/api/conditions")
@limiter.limit("60 per minute")
def api_conditions():
    """Riding conditions breakdown"""
    return jsonify(compute_conditions())

@app.route("/api/peaks")
@limiter.limit("60 per minute")
def api_peaks():
    """Session peak / min values"""
    return jsonify({
        "peak_rpm": peak_rpm,
        "min_rpm": min_rpm if min_rpm != float('inf') else 0,
        "peak_temp": peak_temp,
        "peak_load": peak_load,
        "session_start_ms": round(session_start * 1000),
        "elapsed_s": round(time.time() - session_start, 1),
        "samples": len(history),
    })

@app.route("/api/export")
@limiter.limit("10 per minute")
def api_export():
    """Export full history as CSV"""
    with history_lock:
        snaps = list(history)
    if not snaps:
        return "No data", 204

    headers = [
        "timestamp", "mode",
        "rpm", "speed", "gear",
        "engine_temp", "exhaust_gas_temp", "coolant_temp", "intake_air_temp",
        "engine_load", "throttle",
        "oil_pressure", "fuel_pressure",
        "battery_voltage", "air_fuel_ratio", "manifold_pressure",
        "vibration", "fuel_level",
    ]

    rows = []
    for s in snaps:
        ts_raw = s.get("timestamp", "")
        try:
            ts_str = datetime.fromtimestamp(int(ts_raw) / 1000).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError, OSError):
            ts_str = str(ts_raw)
        rows.append(",".join([
            ts_str,
            str(s.get("mode", "")),
            str(s.get("rpm", "")),
            str(s.get("speed", "")),
            str(s.get("gear", "")),
            str(s.get("engine_temp", "")),
            str(s.get("exhaust_temp", "")),
            str(s.get("coolant_temp", "")),
            str(s.get("intake_air_temp", "")),
            str(s.get("engine_load", "")),
            str(s.get("throttle", "")),
            str(s.get("oil_pressure", "")),
            str(s.get("fuel_pressure", "")),
            str(s.get("battery_voltage", "")),
            str(s.get("afr", "")),
            str(s.get("map_sensor", "")),
            str(s.get("vibration", "")),
            str(s.get("fuel_level", "")),
        ]))

    csv_content = "\n".join([",".join(headers)] + rows)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    from flask import Response
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=ecu_session_{ts}.csv"}
    )

@app.route("/api/status")
@limiter.limit("60 per minute")
def api_status():
    return jsonify({
        "server": "running",
        "mode": args.mode,
        "samples": len(history),
        "uptime_s": round(time.time() - session_start, 1),
        "interval": args.interval,
    })

# Serve React frontend from /dist
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    import os
    dist = os.path.join(os.path.dirname(__file__), "dist")
    # Path traversal protection
    if path:
        requested_path = os.path.join(dist, path)
        if not os.path.normpath(requested_path).startswith(os.path.normpath(dist)):
            return "Not found", 404
        if os.path.exists(requested_path):
            return send_from_directory(dist, path)
    return send_from_directory(dist, "index.html")

# ─────────────────────────────────────────────────────────────────────────────
# Terminal Status Display (unchanged)
# ─────────────────────────────────────────────────────────────────────────────
RESET = "\033[0m"
BOLD = "\033[1m"
BLUE = "\033[94m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
TEAL = "\033[36m"

def status_display():
    time.sleep(2)
    while True:
        with history_lock:
            snap = dict(latest_snap) if latest_snap else {}
            n = len(history)

        if not snap:
            time.sleep(1)
            continue

        elapsed = int(time.time() - session_start)
        mm, ss = divmod(elapsed, 60)
        health = compute_health(list(history))
        conds = compute_conditions()

        print(f"\n{BOLD}{BLUE}{'─'*60}{RESET}")
        print(f"{BOLD} ECU Dashboard  {DIM}│{RESET}{DIM}  {datetime.now().strftime('%H:%M:%S')}  │  Session {mm:02d}:{ss:02d}  │  {n} samples{RESET}")
        print(f"{BOLD}{BLUE}{'─'*60}{RESET}")

        rpm_pct = snap.get("rpm", 0) / REDLINE
        rpm_bar = int(rpm_pct * 30)
        rpm_col = RED if rpm_pct > 0.9 else YELLOW if rpm_pct > 0.7 else GREEN
        print(f" {CYAN}RPM{RESET}     {rpm_col}{'█' * rpm_bar}{'░' * (30 - rpm_bar)}{RESET}  {BOLD}{snap.get('rpm', 0):>5}{RESET} / {REDLINE}")

        load_pct = snap.get("engine_load", 0) / 100
        load_bar = int(load_pct * 30)
        load_col = RED if load_pct > 0.85 else YELLOW if load_pct > 0.6 else TEAL
        print(f" {CYAN}LOAD{RESET}    {load_col}{'█' * load_bar}{'░' * (30 - load_bar)}{RESET}  {BOLD}{snap.get('engine_load', 0):>5.1f}{RESET}%")

        temp = snap.get("engine_temp", 0)
        temp_col = RED if temp > 105 else YELLOW if temp > 95 else GREEN
        print(f" {CYAN}ENG T{RESET}   {temp_col}{temp:>5.1f}°C{RESET}   EGT {snap.get('exhaust_temp', 0):>6.1f}°C   COOLANT {snap.get('coolant_temp', 0):>5.1f}°C")
        print(f" {CYAN}SPEED{RESET}   {snap.get('speed', 0):>5.1f} km/h   GEAR {snap.get('gear', 1)}   MODE {BOLD}{snap.get('mode', '—').upper():<12}{RESET}")
        print(f" {CYAN}AFR{RESET}     {snap.get('afr', 0):>5.2f}   BATT {snap.get('battery_voltage', 0):.2f}V   OIL {snap.get('oil_pressure', 0):.2f} bar")
        print(f" {CYAN}HEALTH{RESET}  Overall {BOLD}{health['overall']:>3}%{RESET}  Engine {health['engine']}%  Thermal {health['thermal']}%  Fuel {health['fueling']}%")

        cond_str = "  ".join(f"{k.title()[:4]} {v}%" for k, v in conds.items() if v > 0)
        print(f" {CYAN}CONDS{RESET}   {DIM}{cond_str}{RESET}")
        print(f"{DIM}{'─'*60}{RESET}")

        time.sleep(5)

# ─────────────────────────────────────────────────────────────────────────────
# Start
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{BOLD}{BLUE}╔══════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{BLUE}║   ECU Dashboard — Python Flask Server   ║{RESET}")
    print(f"{BOLD}{BLUE}╚══════════════════════════════════════════╝{RESET}\n")
    print(f" {GREEN}●{RESET} Mode      : {BOLD}{args.mode.upper()}{RESET}")
    print(f" {GREEN}●{RESET} Interval  : {BOLD}{args.interval}s{RESET}")
    print(f" {GREEN}●{RESET} Dashboard : {BOLD}{CYAN}http://localhost:{args.port}{RESET}")
    print(f" {GREEN}●{RESET} API       : {BOLD}{CYAN}http://localhost:{args.port}/api/{RESET}")
    if args.enable_debug:
        print(f" {YELLOW}⚠ DEBUG MODE ENABLED — NOT FOR PRODUCTION{RESET}")
    print(f" {DIM}  Press Ctrl+C to stop{RESET}\n")

    # Start background threads
    data_thread = threading.Thread(target=data_loop, daemon=True)
    data_thread.start()

    status_thread = threading.Thread(target=status_display, daemon=True)
    status_thread.start()

    # Debug mode ONLY if explicitly enabled via flag
    debug_mode = args.enable_debug and os.environ.get("FLASK_ENV") != "production"
    app.run(host=args.host, port=args.port, debug=debug_mode, threaded=True)