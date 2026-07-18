"""
IC Engine Data Simulator — Python Terminal Dashboard
=====================================================
Simulates realistic IC engine behaviour for data analysis practice.
Physics-based state machine with smooth transitions between riding modes.

Usage:
    python simulate_engine.py                            # default 2s interval
    python simulate_engine.py --interval 0.5            # 0.5s fast mode
    python simulate_engine.py --interval 1 --mode highway
    python simulate_engine.py --duration 120 --output session.csv
    python simulate_engine.py --mode aggressive --duration 60
    python simulate_engine.py --no-csv                  # disable CSV output

Modes: idle | city | highway | aggressive | decel | auto (default)
"""

import argparse
import csv
import math
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# CLI Arguments
# ─────────────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="IC Engine Simulator — Terminal Dashboard")
parser.add_argument("--interval",  type=float,  default=2.0,  help="Tick interval in seconds (default: 2.0)")
parser.add_argument("--duration",  type=float,  default=0,    help="Session duration in seconds (0 = infinite)")
parser.add_argument("--mode",      default="auto",            help="Force engine mode: idle|city|highway|aggressive|decel|auto")
parser.add_argument("--output",    default="",                help="CSV output file (default: auto-named)")
parser.add_argument("--no-csv",    action="store_true",       help="Disable CSV saving")
parser.add_argument("--no-color",  action="store_true",       help="Disable ANSI colours")
args = parser.parse_args()

# ─────────────────────────────────────────────────────────────────────────────
# Security: Input Validation
# ─────────────────────────────────────────────────────────────────────────────
VALID_MODES = {"idle", "city", "highway", "aggressive", "decel", "auto"}

def validate_mode(mode: str) -> str:
    """Validate and sanitize mode argument."""
    return mode if mode in VALID_MODES else "auto"

def validate_interval(interval: float) -> float:
    """Validate tick interval (0.05s to 60s)."""
    return max(0.05, min(60.0, interval))

def validate_duration(duration: float) -> float:
    """Validate session duration (0 to 86400s = 24h)."""
    return max(0.0, min(86400.0, duration))

def validate_output_path(path: str, default_name: str) -> Path:
    """Validate and sanitize output path to prevent traversal."""
    if not path:
        return Path(default_name).resolve()
    # Resolve to absolute path and ensure it's in current directory or subdirectory
    try:
        resolved = Path(path).resolve()
        cwd = Path.cwd().resolve()
        # Allow files in cwd or subdirectories only
        if not str(resolved).startswith(str(cwd)):
            print(f"Warning: Output path outside working directory, using default")
            return Path(default_name).resolve()
        return resolved
    except (OSError, ValueError):
        return Path(default_name).resolve()

# Apply validation
args.mode = validate_mode(args.mode)
args.interval = validate_interval(args.interval)
args.duration = validate_duration(args.duration)

# ─────────────────────────────────────────────────────────────────────────────
# ANSI Colour Codes
# ─────────────────────────────────────────────────────────────────────────────
if args.no_color or not sys.stdout.isatty():
    RESET = BOLD = DIM = RED = GREEN = YELLOW = BLUE = CYAN = MAGENTA = TEAL = WHITE = ""
else:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    TEAL    = "\033[36m"

# ─────────────────────────────────────────────────────────────────────────────
# Engine Constants
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

MODE_EMOJIS = {
    "idle": "🅿", "city": "🏙", "highway": "🛣",
    "aggressive": "🔥", "decel": "🛑",
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def clamp(v, lo, hi):  return max(lo, min(hi, v))
def lerp(a, b, t):     return a + (b - a) * t
def jitter(v, rng):    return v + (random.random() - 0.5) * rng * 2

def bar(val, mx, width=28, fill="█", empty="░"):
    filled = int((val / mx) * width)
    return fill * filled + empty * (width - filled)

def color_for_pct(pct):
    if pct > 0.85: return RED
    if pct > 0.65: return YELLOW
    return GREEN

def color_temp(temp, warn=100, crit=110):
    if temp >= crit: return RED
    if temp >= warn: return YELLOW
    return TEAL

def health_color(score):
    if score >= 85: return GREEN
    if score >= 65: return YELLOW
    return RED

# ─────────────────────────────────────────────────────────────────────────────
# Secure Terminal Clear (no os.system)
# ─────────────────────────────────────────────────────────────────────────────
def clear():
    """Clear terminal without shell injection vulnerability."""
    # ANSI escape sequence - works on all modern terminals including Windows 10+
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

# ─────────────────────────────────────────────────────────────────────────────
# Engine Simulator Class
# ─────────────────────────────────────────────────────────────────────────────
class EngineSimulator:
    def __init__(self, forced_mode="auto"):
        self.forced_mode   = forced_mode if forced_mode != "auto" else None
        self.mode          = forced_mode if forced_mode != "auto" else "idle"
        self.mode_timer    = 0
        self.rpm           = 950.0
        self.engine_temp   = 65.0
        self.exhaust_temp  = 110.0
        self.engine_load   = 8.0
        self.throttle      = 4.0
        self.speed         = 0.0
        self.fuel_level    = 100.0
        self.coolant_temp  = 65.0
        self.intake_air    = 27.0

        # Peak tracking
        self.peak_rpm      = 0
        self.peak_egt      = 0
        self.peak_load     = 0
        self.peak_temp     = 0
        self.min_rpm       = float('inf')

        # Condition counters
        self.cond_counts   = {k: 0 for k in MODE_TARGETS}
        self.tick_count    = 0

    def _pick_mode(self):
        if self.forced_mode:
            return self.forced_mode
        return random.choice(MODE_TRANSITIONS[self.mode])

    def tick(self):
        self.mode_timer -= 1
        if self.mode_timer <= 0:
            self.mode       = self._pick_mode()
            self.mode_timer = random.randint(4, 12)

        t = MODE_TARGETS[self.mode]

        # Physics
        self.rpm         = clamp(lerp(self.rpm,         jitter(t["rpm"],      60), 0.18), 600, REDLINE)
        self.engine_load = clamp(lerp(self.engine_load, jitter(t["load"],      2),  0.15), 0, 100)
        self.throttle    = clamp(lerp(self.throttle,    jitter(t["throttle"],  2),  0.20), 0, 100)

        target_speed  = (self.rpm / REDLINE) * 160 * (t["load"] / 100) * 1.4
        self.speed    = clamp(lerp(self.speed, jitter(target_speed, 3), 0.12), 0, 180)

        heat_in          = self.engine_load * 0.012 + self.rpm * 0.00004
        heat_out         = (self.engine_temp - 22) * 0.025
        self.engine_temp = clamp(self.engine_temp + heat_in - heat_out + jitter(0, 0.3), 60, 130)
        self.coolant_temp= clamp(self.engine_temp - jitter(3, 1.5), 55, 125)

        egt_target       = 90 + self.engine_load * 7.5 + (self.rpm / REDLINE) * 300
        self.exhaust_temp= clamp(lerp(self.exhaust_temp, jitter(egt_target, 15), 0.10), 80, 900)

        self.intake_air  = clamp(self.intake_air + jitter(0, 0.05), 20, 55)
        self.fuel_level  = clamp(self.fuel_level - 0.0003 * (self.engine_load / 100), 0, 100)

        oil_pressure     = clamp(1.2 + (self.rpm / REDLINE) * 4.8 + jitter(0, 0.2), 0, 7)
        fuel_pressure    = clamp(2.8 + jitter(0, 0.15), 1, 5)
        battery_voltage  = clamp(13.8 + jitter(0, 0.12) - (0.4 if self.engine_load > 80 else 0), 10, 15)
        afr              = clamp(14.7 + (-0.8 if self.mode == "aggressive" else 0) + jitter(0, 0.3), 10, 20)
        vibration        = clamp(0.5 + (self.rpm / REDLINE) * 6 + jitter(0, 0.4), 0, 10)
        map_sensor       = clamp(30 + self.engine_load * 0.65 + jitter(0, 2), 15, 105)

        gear = 1
        spd  = self.speed
        if spd >= 110: gear = 6
        elif spd >= 80: gear = 5
        elif spd >= 55: gear = 4
        elif spd >= 30: gear = 3
        elif spd >= 15: gear = 2

        # Peak tracking
        self.peak_rpm  = max(self.peak_rpm,  self.rpm)
        self.peak_egt  = max(self.peak_egt,  self.exhaust_temp)
        self.peak_load = max(self.peak_load, self.engine_load)
        self.peak_temp = max(self.peak_temp, self.engine_temp)
        self.min_rpm   = min(self.min_rpm,   self.rpm)
        self.cond_counts[self.mode] += 1
        self.tick_count += 1

        return {
            "timestamp":       round(time.time() * 1000),
            "mode":            self.mode,
            "rpm":             round(self.rpm),
            "speed":           round(self.speed, 1),
            "gear":            gear,
            "engine_temp":     round(self.engine_temp, 1),
            "exhaust_temp":    round(self.exhaust_temp, 1),
            "coolant_temp":    round(self.coolant_temp, 1),
            "intake_air_temp": round(self.intake_air, 1),
            "engine_load":     round(self.engine_load, 1),
            "throttle":        round(self.throttle, 1),
            "oil_pressure":    round(oil_pressure, 2),
            "fuel_pressure":   round(fuel_pressure, 2),
            "battery_voltage": round(battery_voltage, 2),
            "afr":             round(afr, 2),
            "map_sensor":      round(map_sensor, 1),
            "vibration":       round(vibration, 2),
            "fuel_level":      round(self.fuel_level, 2),
        }

    def health_scores(self, recent_snaps):
        if not recent_snaps:
            return {"engine": 100, "thermal": 100, "fueling": 100, "electrical": 100, "mechanical": 100, "overall": 100}
        last     = recent_snaps[-1]
        avg_load = sum(s["engine_load"] for s in recent_snaps[-30:]) / min(30, len(recent_snaps))
        max_egt  = max(s["exhaust_temp"] for s in recent_snaps[-30:])
        engine     = clamp(100 - max(0, avg_load - 85) * 2 - (10 if last["rpm"] > 8500 else 0), 0, 100)
        thermal    = clamp(100 - max(0, last["engine_temp"] - 95) * 2 - max(0, max_egt - 680) * 0.15, 0, 100)
        fueling    = clamp(100 - abs(last["afr"] - 14.7) * 4 - (12 if last["fuel_pressure"] < 2.5 else 0), 0, 100)
        electrical = clamp(100 - (20 if last["battery_voltage"] < 12.0 else 8 if last["battery_voltage"] < 12.5 else 0), 0, 100)
        mechanical = clamp(100 - max(0, last["vibration"] - 5) * 6 - (15 if last["oil_pressure"] < 2 else 0), 0, 100)
        overall    = round((engine + thermal + fueling + electrical + mechanical) / 5)
        return {
            "engine": round(engine), "thermal": round(thermal),
            "fueling": round(fueling), "electrical": round(electrical),
            "mechanical": round(mechanical), "overall": overall,
        }

    def conditions_str(self):
        total = sum(self.cond_counts.values()) or 1
        return {k: round(v / total * 100) for k, v in self.cond_counts.items()}

# ─────────────────────────────────────────────────────────────────────────────
# Terminal Display
# ─────────────────────────────────────────────────────────────────────────────
def print_dashboard(snap, sim, session_start, history):
    clear()
    elapsed = int(time.time() - session_start)
    mm, ss  = divmod(elapsed, 60)
    health  = sim.health_scores(history)
    conds   = sim.conditions_str()

    W = 62
    print(f"{BOLD}{BLUE}╔{'═' * W}╗{RESET}")
    print(f"{BOLD}{BLUE}║{RESET}  {BOLD}{WHITE}⚙  IC ENGINE SIMULATOR — TERMINAL DASHBOARD{RESET}{'':>14}{BLUE}║{RESET}")
    print(f"{BOLD}{BLUE}║{RESET}  {DIM}Session {mm:02d}:{ss:02d}  │  Tick #{sim.tick_count:>4}  │  Mode: {snap['mode'].upper():<12}{RESET}   {BLUE}║{RESET}")
    print(f"{BOLD}{BLUE}╠{'═' * W}╣{RESET}")

    # RPM
    rpm_pct = snap["rpm"] / REDLINE
    rpm_col = color_for_pct(rpm_pct)
    rl_str  = f" {'◀ REDLINE!' if rpm_pct > 0.93 else ''}"
    print(f"{BLUE}║{RESET}  {CYAN}RPM      {RESET} {rpm_col}{bar(snap['rpm'], REDLINE, 24)}{RESET} {BOLD}{snap['rpm']:>5}{RESET}/{REDLINE}{rl_str:<12}{BLUE}║{RESET}")

    # Load
    load_pct = snap["engine_load"] / 100
    load_col = color_for_pct(load_pct)
    print(f"{BLUE}║{RESET}  {CYAN}LOAD     {RESET} {load_col}{bar(snap['engine_load'], 100, 24)}{RESET} {BOLD}{snap['engine_load']:>5.1f}%{RESET}         {BLUE}║{RESET}")

    # Throttle
    thr_col = color_for_pct(snap["throttle"] / 100)
    print(f"{BLUE}║{RESET}  {CYAN}THROTTLE {RESET} {thr_col}{bar(snap['throttle'], 100, 24)}{RESET} {BOLD}{snap['throttle']:>5.1f}%{RESET}         {BLUE}║{RESET}")

    # Fuel
    fuel_col = RED if snap["fuel_level"] < 10 else YELLOW if snap["fuel_level"] < 25 else GREEN
    print(f"{BLUE}║{RESET}  {CYAN}FUEL     {RESET} {fuel_col}{bar(snap['fuel_level'], 100, 24)}{RESET} {BOLD}{snap['fuel_level']:>5.1f}%{RESET}         {BLUE}║{RESET}")

    print(f"{BLUE}║{RESET}  {DIM}{'─' * (W - 2)}{RESET}  {BLUE}║{RESET}")

    # Temps
    tc = color_temp(snap["engine_temp"])
    ec = color_temp(snap["exhaust_temp"], 700, 780)
    print(f"{BLUE}║{RESET}  {CYAN}ENG TEMP {RESET} {tc}{BOLD}{snap['engine_temp']:>6.1f}°C{RESET}   {CYAN}EXHAUST{RESET} {ec}{BOLD}{snap['exhaust_temp']:>6.1f}°C{RESET}   {DIM}safe<100°{RESET}  {BLUE}║{RESET}")
    print(f"{BLUE}║{RESET}  {CYAN}COOLANT  {RESET} {TEAL}{snap['coolant_temp']:>6.1f}°C{RESET}   {CYAN}INTAKE {RESET} {TEAL}{snap['intake_air_temp']:>6.1f}°C{RESET}               {BLUE}║{RESET}")

    print(f"{BLUE}║{RESET}  {DIM}{'─' * (W - 2)}{RESET}  {BLUE}║{RESET}")

    # Drive
    print(f"{BLUE}║{RESET}  {CYAN}SPEED    {RESET} {BOLD}{snap['speed']:>6.1f} km/h{RESET}  {CYAN}GEAR{RESET} {BOLD}{snap['gear']}{RESET}   {MODE_EMOJIS.get(snap['mode'], '')} {BOLD}{snap['mode'].upper():<12}{RESET}     {BLUE}║{RESET}")

    print(f"{BLUE}║{RESET}  {DIM}{'─' * (W - 2)}{RESET}  {BLUE}║{RESET}")

    # Ancillaries
    afr_col = RED if abs(snap["afr"] - 14.7) > 1.5 else YELLOW if abs(snap["afr"] - 14.7) > 0.5 else GREEN
    bv_col  = RED if snap["battery_voltage"] < 12.0 else YELLOW if snap["battery_voltage"] < 12.5 else GREEN
    op_col  = RED if snap["oil_pressure"] < 1.8 else YELLOW if snap["oil_pressure"] < 2.5 else GREEN
    print(f"{BLUE}║{RESET}  {CYAN}AFR      {RESET} {afr_col}{BOLD}{snap['afr']:>5.2f}{RESET}  λ    {CYAN}BATTERY {RESET} {bv_col}{BOLD}{snap['battery_voltage']:>5.2f}{RESET} V      {BLUE}║{RESET}")
    print(f"{BLUE}║{RESET}  {CYAN}OIL PRES {RESET} {op_col}{BOLD}{snap['oil_pressure']:>5.2f}{RESET} bar  {CYAN}FUEL PR {RESET} {TEAL}{BOLD}{snap['fuel_pressure']:>5.2f}{RESET} bar    {BLUE}║{RESET}")
    print(f"{BLUE}║{RESET}  {CYAN}MAP SENS {RESET} {TEAL}{BOLD}{snap['map_sensor']:>5.1f}{RESET} kPa  {CYAN}VIBRAT  {RESET} {TEAL}{BOLD}{snap['vibration']:>5.2f}{RESET} g      {BLUE}║{RESET}")

    print(f"{BLUE}╠{'═' * W}╣{RESET}")
    print(f"{BLUE}║{RESET}  {BOLD}ENGINE HEALTH SCORES{RESET}                                       {BLUE}║{RESET}")
    print(f"{BLUE}║{RESET}  {DIM}{'─' * (W - 2)}{RESET}  {BLUE}║{RESET}")

    for name, key in [("Engine", "engine"), ("Thermal", "thermal"), ("Fueling", "fueling"),
                      ("Electrical", "electrical"), ("Mechanical", "mechanical")]:
        score = health[key]
        hcol  = health_color(score)
        hbar  = bar(score, 100, 20)
        print(f"{BLUE}║{RESET}  {CYAN}{name:<12}{RESET} {hcol}{hbar}{RESET} {BOLD}{score:>3}%{RESET}                  {BLUE}║{RESET}")

    overall_col = health_color(health["overall"])
    grade = "A" if health["overall"] >= 90 else "B" if health["overall"] >= 75 else "C" if health["overall"] >= 55 else "D"
    print(f"{BLUE}║{RESET}  {DIM}{'─' * (W - 2)}{RESET}  {BLUE}║{RESET}")
    print(f"{BLUE}║{RESET}  {CYAN}OVERALL{RESET}      {overall_col}{BOLD}{health['overall']:>3}% — Grade {grade}{RESET}                        {BLUE}║{RESET}")

    print(f"{BLUE}╠{'═' * W}╣{RESET}")
    print(f"{BLUE}║{RESET}  {BOLD}SESSION PEAKS & RIDING CONDITIONS{RESET}                         {BLUE}║{RESET}")
    print(f"{BLUE}║{RESET}  {CYAN}Peak RPM{RESET} {BOLD}{int(sim.peak_rpm):>6}{RESET}  {CYAN}Peak EGT{RESET} {BOLD}{sim.peak_egt:>7.1f}°C{RESET}  {CYAN}Peak Load{RESET} {BOLD}{sim.peak_load:>5.1f}%{RESET}  {BLUE}║{RESET}")
    cond_parts = "  ".join(f"{k[:4].title()} {v}%" for k, v in conds.items() if v > 0)
    print(f"{BLUE}║{RESET}  {DIM}{cond_parts:<(W-2)}{RESET}  {BLUE}║{RESET}")

    print(f"{BLUE}╠{'═' * W}╣{RESET}")
    if not args.no_csv:
        fname = args.output if args.output else f"ecu_session_{datetime.now().strftime('%Y%m%d')}.csv"
        print(f"{BLUE}║{RESET}  {DIM}Saving to: {fname}  │  Ctrl+C to stop{RESET}{' ' * (W - 38)}{BLUE}║{RESET}")
    else:
        print(f"{BLUE}║{RESET}  {DIM}CSV disabled  │  Ctrl+C to stop{RESET}{' ' * (W - 34)}{BLUE}║{RESET}")
    print(f"{BOLD}{BLUE}╚{'═' * W}╝{RESET}")

# ─────────────────────────────────────────────────────────────────────────────
# CSV Writer
# ─────────────────────────────────────────────────────────────────────────────
CSV_HEADERS = [
    "timestamp", "mode", "rpm", "speed", "gear",
    "engine_temp", "exhaust_gas_temp", "coolant_temp", "intake_air_temp",
    "engine_load", "throttle", "oil_pressure", "fuel_pressure",
    "battery_voltage", "air_fuel_ratio", "manifold_pressure", "vibration", "fuel_level",
]

def snap_to_row(s):
    ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s["timestamp"] / 1000))
    return [
        ts_str, s["mode"], s["rpm"], s["speed"], s["gear"],
        s["engine_temp"], s["exhaust_temp"], s["coolant_temp"], s["intake_air_temp"],
        s["engine_load"], s["throttle"], s["oil_pressure"], s["fuel_pressure"],
        s["battery_voltage"], s["afr"], s["map_sensor"], s["vibration"], s["fuel_level"],
    ]

# ─────────────────────────────────────────────────────────────────────────────
# Main Loop
# ─────────────────────────────────────────────────────────────────────────────
def main():
    forced = args.mode if args.mode != "auto" else "auto"

    sim           = EngineSimulator(forced_mode=forced)
    session_start = time.time()
    history       = []
    csv_file      = None
    csv_writer    = None

    # Setup CSV with validated path
    if not args.no_csv:
        default_name = f"ecu_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        output_path = validate_output_path(args.output, default_name)
        try:
            csv_file   = open(output_path, "w", newline="", encoding="utf-8")
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(CSV_HEADERS)
            print(f"\n{GREEN}✓{RESET} CSV logging to: {BOLD}{output_path}{RESET}")
        except IOError as e:
            print(f"\n{YELLOW}⚠ Could not open CSV: {e}{RESET}")

    print(f"{BOLD}{BLUE}")
    print("  ┌──────────────────────────────────────────────┐")
    print("  │  ECU Engine Simulator — Starting up...       │")
    print(f"  │  Mode: {forced:<12} Interval: {args.interval:.1f}s           │")
    print("  │  Press Ctrl+C to stop and save               │")
    print("  └──────────────────────────────────────────────┘")
    print(f"{RESET}")
    time.sleep(1.5)

    try:
        while True:
            snap = sim.tick()
            history.append(snap)

            if csv_writer:
                csv_writer.writerow(snap_to_row(snap))
                csv_file.flush()

            print_dashboard(snap, sim, session_start, history)

            if args.duration > 0 and (time.time() - session_start) >= args.duration:
                print(f"\n{GREEN}✓{RESET} Session duration {args.duration}s reached. Stopping.")
                break

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Simulation stopped by user.{RESET}")

    finally:
        if csv_file:
            csv_file.close()
            fname = args.output if args.output else "session CSV"
            print(f"{GREEN}✓{RESET} Data saved to {BOLD}{fname}{RESET}  ({len(history)} samples)")

        elapsed = int(time.time() - session_start)
        mm, ss  = divmod(elapsed, 60)
        health  = sim.health_scores(history)
        print(f"\n{BOLD}Session Summary:{RESET}")
        print(f"  Duration : {mm:02d}:{ss:02d}")
        print(f"  Samples  : {len(history)}")
        print(f"  Peak RPM : {int(sim.peak_rpm)}")
        print(f"  Peak EGT : {sim.peak_egt:.1f}°C")
        print(f"  Peak Load: {sim.peak_load:.1f}%")
        print(f"  Health   : {health['overall']}% ({['D','C','B','A'][min(3, health['overall'] // 25)]})")
        print()

if __name__ == "__main__":
    main()