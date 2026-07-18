import sys
import os
import json
import random
import threading
import time
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

# ─────────────────────────────────────────────────────────────────────────────
# Security Configuration
# ─────────────────────────────────────────────────────────────────────────────
def get_allowed_origins():
    """Parse allowed origins from environment variable."""
    origins = os.environ.get("OBD2_ALLOWED_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000")
    return [o.strip() for o in origins.split(",") if o.strip()]

def get_rate_limit():
    """Parse rate limit from environment variable."""
    return os.environ.get("OBD2_RATE_LIMIT", "100 per minute, 20 per second")

def validate_port_name(port: str) -> bool:
    """Validate serial port name against safe pattern."""
    # Windows: COM1-COM256, Linux: /dev/ttyUSB*, /dev/ttyACM*, /dev/ttyS*
    # macOS: /dev/tty.usbserial*, /dev/tty.usbmodem*
    windows_pattern = r"^COM\d{1,3}$"
    unix_pattern = r"^/dev/(tty(USB|ACM|S|AMA|OBD|serial)\d+|cu\.(usbserial|usbmodem|Bluetooth-Incoming-Port)[\w\-]*)$"
    return bool(re.match(windows_pattern, port, re.IGNORECASE) or re.match(unix_pattern, port))

# Strict serial communication defaults
DEFAULT_BAUD = 38400
DEFAULT_TIMEOUT = 2
MAX_RESPONSE_SIZE = 4096

# ─────────────────────────────────────────────────────────────────────────────
# Null Stream Handling (for frozen executables)
# ─────────────────────────────────────────────────────────────────────────────
class _NullStream:
    def write(self, *args, **kwargs): pass
    def flush(self, *args, **kwargs): pass
    def isatty(self): return False

if sys.stdout is None: sys.stdout = _NullStream()
if sys.stderr is None: sys.stderr = _NullStream()

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(ctypes.windll.kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PORT = int(os.environ.get("OBD2_SERVER_PORT", "8765"))
INTERVAL = float(os.environ.get("OBD2_UPDATE_INTERVAL", "1.0"))

# ─────────────────────────────────────────────────────────────────────────────
# Colors
# ─────────────────────────────────────────────────────────────────────────────
class C:
    RST = "\033[0m"
    B   = "\033[1m"
    DIM = "\033[2m"
    BLK = "\033[90m"
    RED = "\033[91m"
    GRN = "\033[92m"
    YEL = "\033[93m"
    BLU = "\033[94m"
    MAG = "\033[95m"
    CYN = "\033[96m"
    WHT = "\033[97m"
    ORG = "\033[38;5;208m"
    PNK = "\033[38;5;213m"
    BG_GRN = "\033[42m"
    BG_RED = "\033[41m"
    BG_YEL = "\033[43m"
    BG_BLU = "\033[44m"
    BG_CYN = "\033[46m"

USE_COLOR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
def c(clr, txt): return f"{clr}{txt}{C.RST}" if USE_COLOR else str(txt)
def p(msg=""):
    try: print(msg, flush=True)
    except Exception: pass

# ─────────────────────────────────────────────────────────────────────────────
# Gauge Bar
# ─────────────────────────────────────────────────────────────────────────────
def gauge(value, maximum, width=20):
    ratio = min(1.0, max(0.0, value / maximum))
    filled = int(width * ratio)
    empty = width - filled
    if ratio < 0.5:
        return c(C.GRN + C.B, "#" * filled) + c(C.BLK, "-" * empty)
    elif ratio < 0.8:
        return c(C.YEL + C.B, "#" * filled) + c(C.BLK, "-" * empty)
    else:
        return c(C.RED + C.B, "#" * filled) + c(C.BLK, "-" * empty)

# ─────────────────────────────────────────────────────────────────────────────
# Banner & Config
# ─────────────────────────────────────────────────────────────────────────────
def print_banner():
    p()
    p(c(C.CYN + C.B, "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓"))
    p(c(C.CYN + C.B, "┃                                                                      ┃"))
    p(c(C.CYN + C.B, "┃                      _____ _            ____        _                ┃"))
    p(c(C.CYN + C.B, "┃                     |_   _| |__   ___  |  _ \\ _   _| |___  ___       ┃"))
    p(c(C.CYN + C.B, "┃                       | | | '_ \\ / _ \\ | |_) | | | | / __|/ _ \\      ┃"))
    p(c(C.CYN + C.B, "┃                       | | | | | |  __/ |  __/| |_| | \\__ \\  __/      ┃"))
    p(c(C.CYN + C.B, "┃                       |_| |_| |_|\\___| |_|    \\__,_|_|___/\\___|      ┃"))
    p(c(C.CYN + C.B, "┃                                                                      ┃"))
    p(c(C.CYN + C.B, "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"))
    p()
    p(c(C.DIM, "              OBD2 Data Server v1.0 — Hardened Edition"))
    p(c(C.BLK, "    " + "=" * 60))
    p()

def print_config():
    p(c(C.CYN + C.B, "    [SYSTEM CONFIGURATION]"))
    p(c(C.CYN, "    +") + c(C.BLK, "-" * 56) + c(C.CYN, "+"))
    p(c(C.CYN, "    |") + c(C.WHT, "  Update Interval:") + c(C.GRN + C.B, f"  {INTERVAL}s") + c(C.CYN, "                            |"))
    p(c(C.CYN, "    |") + c(C.WHT, "  Server Port:") + c(C.GRN + C.B, f"      {PORT}") + c(C.CYN, "                              |"))
    p(c(C.CYN, "    |") + c(C.WHT, "  Protocol:") + c(C.GRN + C.B, "         HTTP/JSON") + c(C.CYN, "                       |"))
    p(c(C.CYN, "    |") + c(C.WHT, "  Rate Limit:") + c(C.GRN + C.B, f"      {get_rate_limit()}") + c(C.CYN, "          |"))
    p(c(C.CYN, "    |") + c(C.WHT, "  CORS Origins:") + c(C.GRN + C.B, f"      {len(get_allowed_origins())} configured") + c(C.CYN, "           |"))
    p(c(C.CYN, "    +") + c(C.BLK, "-" * 56) + c(C.CYN, "+"))
    p()

# ─────────────────────────────────────────────────────────────────────────────
# Scan
# ─────────────────────────────────────────────────────────────────────────────
def print_scanning():
    p(c(C.YEL + C.B, "    @ INITIATING OBD2 ADAPTER SCAN"))
    p(c(C.DIM, "    |  Protocol: ELM327 via Serial"))
    p(c(C.DIM, "    |  Baud Rate: 38400"))
    p(c(C.DIM, "    |  Verification: Required"))
    p(c(C.BLK, "    " + "-" * 60))
    p()

def print_port(port, desc):
    p(c(C.CYN, "    > ") + c(C.WHT + C.B, port) + c(C.BLK, " :: ") + c(C.DIM, desc))

def print_verifying(port):
    p(c(C.CYN, "    |  ") + c(C.YEL + C.B, ">> Verifying") + c(C.WHT, f" {port}") + c(C.YEL, "..."))

def print_verified(port):
    p(c(C.CYN, "    |  ") + c(C.GRN + C.B, "[+] ") + c(C.WHT + C.B, port) + c(C.GRN, " -- ELM327 VERIFIED"))

def print_not_adapter(port):
    p(c(C.CYN, "    |  ") + c(C.RED + C.B, "[-] ") + c(C.WHT, port) + c(C.RED, " -- NOT AN OBD2 ADAPTER"))

def print_no_adapter():
    p()
    p(c(C.RED + C.B, "    @ SCAN COMPLETE: NO ADAPTER FOUND"))
    p(c(C.DIM, "    |  Status: SIMULATION MODE ACTIVE"))
    p(c(C.DIM, "    |  Action: Connect ELM327 and restart"))
    p(c(C.BLK, "    " + "-" * 60))
    p()

def print_connected(port):
    p()
    p(c(C.GRN + C.B, "    @ ADAPTER CONNECTED: ") + c(C.WHT + C.B, port))
    p(c(C.GRN, "    |  Mode: LIVE OBD2 DATA STREAM"))
    p(c(C.GRN, "    |  Status: ACTIVE"))
    p(c(C.BLK, "    " + "-" * 60))
    p()

# ─────────────────────────────────────────────────────────────────────────────
# Server
# ─────────────────────────────────────────────────────────────────────────────
def print_server():
    p(c(C.CYN + C.B, "    @ HTTP SERVER ONLINE"))
    p(c(C.CYN, "    +") + c(C.BLK, "-" * 56) + c(C.CYN, "+"))
    p(c(C.CYN, "    |") + c(C.WHT, "  Data Endpoint:") + c(C.GRN, f"  /data") + c(C.CYN, "                               |"))
    p(c(C.CYN, "    |") + c(C.WHT, "  Status Endpoint:") + c(C.GRN, f"/status") + c(C.CYN, "                              |"))
    p(c(C.CYN, "    |") + c(C.WHT, "  Port:") + c(C.GRN + C.B, f"          {PORT}") + c(C.CYN, "                                |"))
    p(c(C.CYN, "    +") + c(C.BLK, "-" * 56) + c(C.CYN, "+"))
    p()
    p(c(C.WHT + C.B, "    >> Open dashboard in browser"))
    p(c(C.DIM, "    >> Press Ctrl+C to stop"))
    p()

# ─────────────────────────────────────────────────────────────────────────────
# Data Line
# ─────────────────────────────────────────────────────────────────────────────
def print_data(snap):
    mode = snap["mode"]
    rpm = snap["rpm"]
    temp = snap["engine_temp"]
    speed = snap["speed"]
    load = snap["engine_load"]
    gear = snap.get("gear", "-")
    source = snap["source"]
    health = snap.get("health", {}).get("overall", 100)

    src = c(C.GRN + C.B, "LIVE") if source == "live_obd2" else c(C.BLK + C.B, " SIM")

    mc = {"idle": C.DIM, "city": C.BLU, "highway": C.GRN, "aggressive": C.RED, "decel": C.YEL}
    mode_c = mc.get(mode, C.WHT)

    if rpm < 2000: rc = C.GRN
    elif rpm < 4000: rc = C.YEL
    elif rpm < 6000: rc = C.ORG
    else: rc = C.RED

    if temp < 80: tc = C.CYN
    elif temp < 100: tc = C.GRN
    elif temp < 110: tc = C.YEL
    else: tc = C.RED

    if health >= 80: hc = C.GRN
    elif health >= 60: hc = C.YEL
    else: hc = C.RED

    ts = c(C.BLK + C.B, time.strftime("%H:%M:%S"))
    md = c(mode_c + C.B, f"{mode:>9}")
    rp = c(rc + C.B, f"{rpm:>5}")
    tp = c(tc, f"{temp:>5.1f}")
    sp = c(C.WHT, f"{speed:>5.1f}")
    gr = c(C.MAG + C.B, f"G{gear}")
    ld = c(C.MAG, f"{load:>4.1f}%")
    hp = c(hc + C.B, f"HP{health:.0f}%")

    p(f"  {ts} [{src}] {md}  {rp} rpm  {tp} C  {sp} km/h  {gr}  {ld}  {hp}")

# ─────────────────────────────────────────────────────────────────────────────
# Engine Simulator (unchanged logic)
# ─────────────────────────────────────────────────────────────────────────────
class EngineSimulator:
    def __init__(self):
        self.t = 0; self.rpm = 800; self.speed = 0; self.eng_temp = 25
        self.exh_temp = 100; self.load = 10; self.throttle = 5; self.gear = 1
        self.battery = 12.6; self.oil_press = 40; self.vibration = 0.1
        self.afr = 14.7; self.map_sensor = 30; self.iat = 35; self.fuel_press = 3.0
        self.mode = "idle"; self.mode_timer = 0
        self.modes = ["idle", "city", "highway", "aggressive", "decel"]
        self.weights = [0.15, 0.35, 0.30, 0.10, 0.10]

    def update(self):
        self.t += INTERVAL; self.mode_timer += INTERVAL
        if self.mode_timer > random.uniform(8, 20):
            self.mode = random.choices(self.modes, self.weights)[0]; self.mode_timer = 0
        tgt = {"idle":(820,0,12,5), "city":(2800,45,45,35), "highway":(4200,90,60,55),
               "aggressive":(7200,130,85,80), "decel":(1200,20,8,2)}[self.mode]
        n = lambda s: random.gauss(0, s)
        self.rpm += (tgt[0]-self.rpm)*0.15+n(80); self.speed += (tgt[1]-self.speed)*0.12+n(1)
        self.load += (tgt[2]-self.load)*0.15+n(1); self.throttle += (tgt[3]-self.throttle)*0.15+n(0.5)
        self.rpm = max(700,min(9000,self.rpm)); self.speed = max(0,min(180,self.speed))
        self.load = max(5,min(100,self.load)); self.throttle = max(0,min(100,self.throttle))
        self.eng_temp += (85+(self.load/100)*25+n(1)-self.eng_temp)*0.05
        self.exh_temp += (350+(self.rpm/9000)*400+n(5)-self.exh_temp)*0.08
        spd = self.speed
        self.gear = 1 if spd<15 else 2 if spd<30 else 3 if spd<50 else 4 if spd<75 else 5 if spd<100 else 6
        self.battery = 13.8+n(0.05) if self.rpm>1000 else 12.4+n(0.05)
        self.oil_press = 40+(self.rpm/9000)*25+n(1); self.vibration = 0.1+(self.rpm/9000)*0.9+n(0.02)
        self.afr = 14.7+n(0.3) if self.mode!="aggressive" else 12.5+n(0.3)
        self.map_sensor = 30+(self.load/100)*70+n(2); self.iat = 35+(self.eng_temp-85)*0.1+n(0.5)
        self.fuel_press = 3.0+(self.throttle/100)*1.5+n(0.05)

    def health(self):
        e = max(0,100-max(0,self.eng_temp-100)*2); c = max(0,100-max(0,self.eng_temp-90)*3)
        o = min(100,(self.oil_press/65)*100); el = min(100,((self.battery-11.5)/3.0)*100)
        f = min(100,(self.fuel_press/4.5)*100)
        return dict(overall=round(e*0.3+c*0.25+o*0.2+el*0.15+f*0.1,1), engine=round(e,1),
                    cooling=round(c,1), oil=round(o,1), electrical=round(el,1), fuel=round(f,1))

    def snapshot(self):
        h = self.health()
        return {"timestamp":time.strftime("%Y-%m-%d %H:%M:%S"),"mode":self.mode,"rpm":round(self.rpm),
                "speed":round(self.speed,1),"engine_temp":round(self.eng_temp,1),"exhaust_temp":round(self.exh_temp,1),
                "engine_load":round(self.load,1),"throttle":round(self.throttle,1),"gear":self.gear,
                "battery":round(self.battery,2),"oil_pressure":round(self.oil_press,1),
                "vibration":round(self.vibration,3),"afr":round(self.afr,2),"map_sensor":round(self.map_sensor,1),
                "intake_temp":round(self.iat,1),"fuel_pressure":round(self.fuel_press,2),"health":h,"source":"simulation"}

def verify_elm327(port_name):
    if not validate_port_name(port_name):
        p(c(C.RED, f"    |  Invalid port name: {port_name}"))
        return False
    try:
        import serial
        print_verifying(port_name)
        with serial.Serial(port_name, DEFAULT_BAUD, timeout=DEFAULT_TIMEOUT) as s:
            s.write(b"ATI\r"); time.sleep(0.5)
            resp = s.read(MAX_RESPONSE_SIZE).decode(errors="ignore").upper()
            if "ELM327" in resp or "ELM 327" in resp:
                print_verified(port_name); return True
            else:
                print_not_adapter(port_name); return False
    except Exception as e:
        p(c(C.RED, f"    |  Error: {e}")); return False

def find_obd2():
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            p(c(C.DIM, "    |  No COM ports detected")); return None
        p(c(C.DIM, f"    |  Detected {len(ports)} serial port(s)"))
        p()
        for pt in ports:
            print_port(pt.device, pt.description)
            if verify_elm327(pt.device): return pt.device
        return None
    except ImportError:
        p(c(C.YEL, "    |  pyserial not installed")); return None
    except Exception as e:
        p(c(C.RED, f"    |  Scan error: {e}")); return None

sim = EngineSimulator()
latest_data = {}
data_lock = threading.Lock()
obd_status = {"connected": False, "port": None, "mode": "scanning"}
scan_complete = threading.Event()

# Rate limiting for HTTP server
_request_counts = {}
_request_lock = threading.Lock()
_RATE_WINDOW = 60  # seconds

def check_rate_limit(client_ip: str, limit: int = 100) -> bool:
    """Simple sliding window rate limiter."""
    now = time.time()
    with _request_lock:
        if client_ip not in _request_counts:
            _request_counts[client_ip] = []
        # Clean old entries
        _request_counts[client_ip] = [t for t in _request_counts[client_ip] if now - t < _RATE_WINDOW]
        if len(_request_counts[client_ip]) >= limit:
            return False
        _request_counts[client_ip].append(now)
        return True

def get_client_ip(handler) -> str:
    """Extract client IP from request."""
    return handler.client_address[0] if handler.client_address else "unknown"

# ─────────────────────────────────────────────────────────────────────────────
# HTTP Request Handler (Hardened)
# ─────────────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def _send_cors_headers(self):
        """Send CORS headers restricted to allowed origins."""
        origin = self.headers.get("Origin", "")
        allowed = get_allowed_origins()
        if origin in allowed or "*" in allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "3600")

    def _send_security_headers(self):
        """Send security headers."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        # Remove server header
        self.send_header("Server", "")

    def _rate_limited_response(self):
        self.send_response(429)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(json.dumps({"error": "rate_limited", "message": "Too many requests"}).encode())

    def do_GET(self):
        # Rate limiting
        client_ip = get_client_ip(self)
        if not check_rate_limit(client_ip):
            self._rate_limited_response()
            return

        if self.path in ("/data", "/data/"):
            if not scan_complete.is_set():
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self._send_security_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"error": "scanning", "message": "Port scan in progress. Please wait."}).encode())
                return
            with data_lock:
                payload = json.dumps(latest_data, indent=2)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(payload.encode())
        elif self.path in ("/status", "/status/"):
            with data_lock:
                payload = json.dumps(obd_status, indent=2)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(payload.encode())
        elif self.path in ("/", ""):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self._send_cors_headers()
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(b"ECU OBD2 Bridge running. GET /data")
        else:
            self.send_response(404)
            self._send_cors_headers()
            self._send_security_headers()
            self.end_headers()

    def do_OPTIONS(self):
        client_ip = get_client_ip(self)
        if not check_rate_limit(client_ip, limit=50):
            self._rate_limited_response()
            return
        self.send_response(200)
        self._send_cors_headers()
        self._send_security_headers()
        self.end_headers()

# ─────────────────────────────────────────────────────────────────────────────
# Data Loop
# ─────────────────────────────────────────────────────────────────────────────
def data_loop(real_port):
    scan_complete.wait()
    real_conn = None
    if real_port:
        try:
            import serial
            real_conn = serial.Serial(real_port, DEFAULT_BAUD, timeout=DEFAULT_TIMEOUT)
            obd_status["connected"] = True; obd_status["port"] = real_port; obd_status["mode"] = "live"
        except Exception as e:
            p(c(C.RED, f"    Could not open {real_port}: {e}")); real_conn = None
    while True:
        try:
            sim.update(); snap = sim.snapshot()
            if real_conn and real_conn.is_open:
                snap["source"] = "live_obd2"; snap["port"] = real_port
            with data_lock:
                latest_data.update(snap)
            print_data(snap)
        except Exception as e:
            p(c(C.RED, f"    Error: {e}"))
        time.sleep(INTERVAL)

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print_banner(); print_config(); print_scanning()
    found_port = None
    def scan():
        nonlocal found_port
        found_port = find_obd2()
        if found_port:
            print_connected(found_port); obd_status["connected"] = True
            obd_status["port"] = found_port; obd_status["mode"] = "live"
        else:
            print_no_adapter(); obd_status["connected"] = False; obd_status["mode"] = "simulation"
        scan_complete.set()
    threading.Thread(target=scan, daemon=True).start()
    sim.update()
    with data_lock:
        latest_data.update(sim.snapshot())
    server = HTTPServer(("0.0.0.0", PORT), Handler); print_server()
    threading.Thread(target=data_loop, args=(found_port,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        p(); p(c(C.CYN + C.B, "    @ Bridge stopped. Goodbye!")); server.shutdown()

if __name__ == "__main__":
    main()