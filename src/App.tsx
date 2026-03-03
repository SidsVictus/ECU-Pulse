import { useState, useCallback, useEffect, useRef } from 'react';
import { useEngineData }   from './hooks/useEngineData';
import { exportToCsv }     from './utils/exportCsv';
import OBDModal            from './components/OBDModal';
import RPMChart            from './components/RPMChart';
import TemperatureChart    from './components/TemperatureChart';
import EngineLoadChart     from './components/EngineLoadChart';
import RidingPieChart      from './components/RidingPieChart';
import HealthPanel         from './components/HealthPanel';

type AppMode = 'modal' | 'live' | 'demo';

const INTERVALS = [
  { label: '0.5s', value: 500  },
  { label: '1s',   value: 1000 },
  { label: '2s',   value: 2000 },
];

const BRIDGE_URL   = 'http://localhost:8765/data';
const FLASK_API_URL = 'http://localhost:5000/api';

function fmt(n: number | undefined, d = 1) {
  return n !== undefined ? n.toFixed(d) : '—';
}

/* ── Stat Card ─────────────────────────────────────────────────────── */
function StatCard({
  label, value, unit, icon, color, change, changeDir,
}: {
  label: string; value: string; unit: string; icon: string;
  color: 'blue'|'teal'|'amber'|'green'|'indigo'|'rose';
  change?: string; changeDir?: 'up'|'down'|'neutral';
}) {
  return (
    <div className={`stat-card ${color}`}>
      <div className="stat-icon">{icon}</div>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <div className="stat-unit">{unit}</div>
      {change && (
        <div className={`stat-change ${changeDir ?? 'neutral'}`}>{change}</div>
      )}
    </div>
  );
}

/* ── Alerts Bar ────────────────────────────────────────────────────── */
function AlertsBar({ alerts }: { alerts: string[] }) {
  if (!alerts.length) return null;
  return (
    <div className="alerts-bar">
      {alerts.map((a, i) => {
        const type =
          a.startsWith('✓') ? 'good'
          : a.toLowerCase().includes('critical') || a.toLowerCase().includes('redline')
          ? 'crit' : 'warn';
        return (
          <div key={i} className={`alert-chip ${type}`}>
            <div className="alert-dot" />
            {a}
          </div>
        );
      })}
    </div>
  );
}

/* ── Main App ──────────────────────────────────────────────────────── */
export default function App() {
  const [mode,          setMode]         = useState<AppMode>('modal');
  const [intervalMs,    setIntervalMs]   = useState(2000);
  const [settingsOpen,  setSettingsOpen] = useState(false);
  const [showSpeed,     setShowSpeed]    = useState(true);
  const [showAFR,       setShowAFR]      = useState(true);
  const [showVibration, setShowVibration]= useState(true);
  const [showFuel,      setShowFuel]     = useState(true);
  const [bridgeOnline,  setBridgeOnline] = useState(false);
  const [flaskOnline,   setFlaskOnline]  = useState(false);
  const [elapsed,       setElapsed]      = useState(0);
  const sessionStart = useRef(Date.now());

  const data = useEngineData(mode !== 'modal' ? intervalMs : 999999);

  /* Check Python services */
  useEffect(() => {
    if (mode === 'modal') return;
    const check = async () => {
      try {
        const r = await fetch(BRIDGE_URL, { signal: AbortSignal.timeout(800) });
        setBridgeOnline(r.ok);
      } catch { setBridgeOnline(false); }
      try {
        const r = await fetch(`${FLASK_API_URL}/status`, { signal: AbortSignal.timeout(800) });
        setFlaskOnline(r.ok);
      } catch { setFlaskOnline(false); }
    };
    check();
    const id = setInterval(check, 5000);
    return () => clearInterval(id);
  }, [mode]);

  /* Session clock */
  useEffect(() => {
    if (mode === 'modal') return;
    sessionStart.current = Date.now();
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - sessionStart.current) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [mode]);

  const handleExport = useCallback(() => {
    if (data.history.length > 0) exportToCsv(data.history, data.sessionStart);
  }, [data.history, data.sessionStart]);

  const c = data.current;
  const elapsedStr = `${String(Math.floor(elapsed / 60)).padStart(2,'0')}:${String(elapsed % 60).padStart(2,'0')}`;

  const connectionStatus =
    mode === 'live' && bridgeOnline ? 'OBD2 Bridge'
    : mode === 'live' && flaskOnline ? 'Flask API'
    : mode === 'live' ? 'Live (Sim)'
    : 'Demo Mode';

  const statusClass = mode === 'demo' ? 'demo' : (bridgeOnline || flaskOnline) ? '' : 'demo';

  /* ── Modal ─────────────────────────────────────────────────────── */
  if (mode === 'modal') {
    return (
      <OBDModal
        onLive={() => setMode('live')}
        onDemo={() => setMode('demo')}
      />
    );
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>

      {/* ── Top Bar ────────────────────────────────────────────────── */}
      <div className="topbar">
        <div className="topbar-left">
          <div className="logo-mark">⚙</div>
          <div>
            <div className="topbar-title">ECU Dashboard</div>
            <div className="topbar-sub">IC Engine Real-Time Monitor</div>
          </div>
        </div>

        <div className="topbar-right">
          {flaskOnline && (
            <div style={{
              fontSize: 10, fontWeight: 600, padding: '3px 9px', borderRadius: 10,
              background: 'rgba(61,170,111,0.1)', color: 'var(--green)',
              border: '1px solid var(--green-border)', whiteSpace: 'nowrap',
            }}>
              🐍 Flask API
            </div>
          )}
          {bridgeOnline && (
            <div style={{
              fontSize: 10, fontWeight: 600, padding: '3px 9px', borderRadius: 10,
              background: 'rgba(56,178,160,0.1)', color: 'var(--teal)',
              border: '1px solid var(--teal-border)', whiteSpace: 'nowrap',
            }}>
              🔌 Bridge
            </div>
          )}

          <div className="session-clock">⏱ {elapsedStr}</div>

          <div className="status-pill">
            <div className={`status-dot ${statusClass}`} />
            {connectionStatus}
          </div>

          <select
            className="interval-select"
            value={intervalMs}
            onChange={e => setIntervalMs(Number(e.target.value))}
          >
            {INTERVALS.map(iv => (
              <option key={iv.value} value={iv.value}>{iv.label} refresh</option>
            ))}
          </select>

          <button className="btn-export" onClick={handleExport} title="Export session to CSV">
            <span>⬇</span>
            <span>Export CSV</span>
          </button>

          <button
            className="btn-settings"
            onClick={() => setSettingsOpen(s => !s)}
            title="Dashboard settings"
          >
            ⚙
          </button>
        </div>
      </div>

      {/* ── Settings Drawer ─────────────────────────────────────────── */}
      <div className={`settings-drawer ${settingsOpen ? 'open' : ''}`}>
        <div className="settings-title">Dashboard Settings</div>

        <div className="settings-section">
          <div className="settings-label">Refresh Rate</div>
          {INTERVALS.map(iv => (
            <div
              key={iv.value}
              className={`settings-option ${intervalMs === iv.value ? 'active' : ''}`}
              onClick={() => setIntervalMs(iv.value)}
            >
              <span className="settings-option-label">{iv.label} interval</span>
              {intervalMs === iv.value && (
                <span style={{ fontSize: 11, color: 'var(--blue)' }}>✓</span>
              )}
            </div>
          ))}
        </div>

        <div className="settings-section">
          <div className="settings-label">Visible Metrics</div>
          {[
            { label: 'Speed (km/h)',  state: showSpeed,     set: setShowSpeed     },
            { label: 'AFR Sensor',    state: showAFR,       set: setShowAFR       },
            { label: 'Vibration',     state: showVibration, set: setShowVibration },
            { label: 'Fuel Level',    state: showFuel,      set: setShowFuel      },
          ].map(({ label, state, set }) => (
            <div key={label} className="settings-option" style={{ cursor: 'default' }}>
              <span className="settings-option-label">{label}</span>
              <button
                className={`toggle-switch ${state ? 'on' : ''}`}
                onClick={() => set(s => !s)}
              />
            </div>
          ))}
        </div>

        <div className="settings-section">
          <div className="settings-label">Mode</div>
          <div
            className={`settings-option ${mode === 'demo' ? 'active' : ''}`}
            onClick={() => setMode('demo')}
          >
            <span className="settings-option-label">🤖 Simulated Data</span>
          </div>
          <div
            className={`settings-option ${mode === 'live' ? 'active' : ''}`}
            onClick={() => setMode('live')}
          >
            <span className="settings-option-label">📡 Live OBD2 Data</span>
          </div>
        </div>

        <div className="settings-section">
          <div className="settings-label">Python Services</div>
          <div className="settings-option" style={{ cursor: 'default' }}>
            <span className="settings-option-label">🐍 Flask API (port 5000)</span>
            <span style={{
              fontSize: 10, fontWeight: 700,
              color: flaskOnline ? 'var(--green)' : 'var(--text-muted)',
            }}>
              {flaskOnline ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>
          <div className="settings-option" style={{ cursor: 'default' }}>
            <span className="settings-option-label">🔌 OBD2 Bridge (8765)</span>
            <span style={{
              fontSize: 10, fontWeight: 700,
              color: bridgeOnline ? 'var(--green)' : 'var(--text-muted)',
            }}>
              {bridgeOnline ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>
          <div style={{
            fontSize: 10.5, color: 'var(--text-muted)',
            padding: '6px 2px', lineHeight: 1.65,
          }}>
            Run <code style={{ color: 'var(--blue)', fontSize: 10 }}>python dashboard_server.py</code> or{' '}
            <code style={{ color: 'var(--teal)', fontSize: 10 }}>python obd2_bridge.py</code> to connect.
          </div>
        </div>

        <div className="settings-section">
          <button
            onClick={handleExport}
            style={{
              width: '100%', padding: '10px', borderRadius: 'var(--r-sm)',
              background: 'var(--bg-panel)', border: '1px solid var(--border-mid)',
              color: 'var(--teal)', fontSize: 12, fontWeight: 600,
              cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.2s',
            }}
          >
            ⬇ Export Session CSV
          </button>
        </div>
      </div>

      {/* ── Dashboard Body — scrollable wrapper ─────────────────────── */}
      <div className="dashboard-wrap">
        <div className={`dashboard-layout ${settingsOpen ? 'drawer-open' : ''}`}>

          {/* Alerts */}
          <AlertsBar alerts={data.alerts} />

          {/* ── Stat Cards ── */}
          <div className="stats-row">
            <StatCard
              label="RPM" icon="🔄"
              value={c ? c.rpm.toLocaleString() : '—'}
              unit="rev/min" color="blue"
              change={c ? `${((c.rpm / 9500) * 100).toFixed(0)}% of redline` : ''}
              changeDir={c && c.rpm > 8000 ? 'down' : 'neutral'}
            />
            <StatCard
              label="Engine Temp" icon="🌡️"
              value={c ? fmt(c.engineTemp) : '—'}
              unit="°C" color="amber"
              change={c ? (c.engineTemp > 100 ? '▲ Above safe' : '● Normal range') : ''}
              changeDir={c && c.engineTemp > 100 ? 'down' : 'neutral'}
            />
            <StatCard
              label="Exhaust Temp" icon="🔥"
              value={c ? fmt(c.exhaustTemp, 0) : '—'}
              unit="°C" color="rose"
              change={c ? (c.exhaustTemp > 700 ? '▲ High EGT' : '● Safe range') : ''}
              changeDir={c && c.exhaustTemp > 700 ? 'down' : 'neutral'}
            />
            <StatCard
              label="Engine Load" icon="📊"
              value={c ? fmt(c.engineLoad) : '—'}
              unit="%" color="indigo"
              change={c ? (c.engineLoad > 80 ? '▲ Heavy load' : '● Moderate') : ''}
              changeDir={c && c.engineLoad > 80 ? 'down' : 'neutral'}
            />
            {showSpeed && (
              <StatCard
                label="Speed" icon="🏍️"
                value={c ? fmt(c.speed) : '—'}
                unit="km/h" color="teal"
                change={c ? `Gear ${c.gear}` : ''}
                changeDir="neutral"
              />
            )}
            {showAFR && (
              <StatCard
                label="AFR" icon="⚗️"
                value={c ? fmt(c.afr, 2) : '—'}
                unit="λ ratio" color="green"
                change={c
                  ? (Math.abs(c.afr - 14.7) < 0.5 ? '● Stoichiometric'
                    : c.afr < 14.7 ? '▼ Running rich'
                    : '▲ Running lean') : ''}
                changeDir={c
                  ? (Math.abs(c.afr - 14.7) < 0.5 ? 'up' : 'down')
                  : 'neutral'}
              />
            )}
            {!showSpeed && !showAFR && (
              <StatCard
                label="Oil Pressure" icon="🛢️"
                value={c ? fmt(c.oilPressure, 2) : '—'}
                unit="bar" color="teal"
                change={c ? (c.oilPressure < 2 ? '▼ Low pressure' : '● Normal') : ''}
                changeDir={c && c.oilPressure < 2 ? 'down' : 'neutral'}
              />
            )}
          </div>

          {/* ── RPM Chart ── */}
          <div className="chart-card span-2">
            <div className="card-header">
              <div className="card-title-wrap">
                <div className="card-icon blue">📈</div>
                <div>
                  <div className="card-title">RPM Over Time</div>
                  <div className="card-desc">Redline at 9,500 RPM · hover for min / peak values</div>
                </div>
              </div>
              <div className={`card-badge ${c && c.rpm > 8000 ? 'crit' : c && c.rpm > 6000 ? 'warn' : 'live'}`}>
                {c ? c.rpm.toLocaleString() : '—'} RPM
              </div>
            </div>
            <RPMChart history={data.history} peakRpm={data.peakRpm} minRpm={data.minRpm} />
          </div>

          {/* ── Health Panel ── */}
          <div className="chart-card span-1">
            <div className="card-header">
              <div className="card-title-wrap">
                <div className="card-icon green">💚</div>
                <div>
                  <div className="card-title">Engine Health</div>
                  <div className="card-desc">5-factor diagnostic score</div>
                </div>
              </div>
              <div className={`card-badge ${data.health.overall >= 85 ? 'live' : data.health.overall >= 65 ? 'warn' : 'crit'}`}>
                {data.health.overall}/100
              </div>
            </div>
            <HealthPanel health={data.health} />
          </div>

          {/* ── Temperature Chart ── */}
          <div className="chart-card span-2">
            <div className="card-header">
              <div className="card-title-wrap">
                <div className="card-icon amber">🌡️</div>
                <div>
                  <div className="card-title">Temperature Profile</div>
                  <div className="card-desc">Engine · Exhaust · Coolant · hover for values</div>
                </div>
              </div>
              <div className={`card-badge ${c && c.engineTemp > 100 ? 'crit' : 'live'}`}>
                {c ? fmt(c.engineTemp) : '—'}°C engine
              </div>
            </div>
            <TemperatureChart history={data.history} peakTemp={data.peakTemp} />
          </div>

          {/* ── Riding Conditions Pie ── */}
          <div className="chart-card span-1">
            <div className="card-header">
              <div className="card-title-wrap">
                <div className="card-icon teal">🥧</div>
                <div>
                  <div className="card-title">Riding Conditions</div>
                  <div className="card-desc">Session breakdown by mode</div>
                </div>
              </div>
              <div className="card-badge live">{c ? c.mode : '—'}</div>
            </div>
            <RidingPieChart conditions={data.conditions} />
          </div>

          {/* ── Engine Load Chart ── */}
          <div className="chart-card span-2">
            <div className="card-header">
              <div className="card-title-wrap">
                <div className="card-icon indigo">📊</div>
                <div>
                  <div className="card-title">Engine Load &amp; Throttle</div>
                  <div className="card-desc">Load % and throttle position · hover for values</div>
                </div>
              </div>
              <div className={`card-badge ${c && c.engineLoad > 80 ? 'warn' : 'live'}`}>
                {c ? fmt(c.engineLoad) : '—'}% load
              </div>
            </div>
            <EngineLoadChart history={data.history} peakLoad={data.peakLoad} />
          </div>

          {/* ── Live Sensors ── */}
          <div className="chart-card span-1">
            <div className="card-header">
              <div className="card-title-wrap">
                <div className="card-icon blue">📟</div>
                <div>
                  <div className="card-title">Live Sensors</div>
                  <div className="card-desc">All ECU readings</div>
                </div>
              </div>
              <div className="card-badge live">LIVE</div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {[
                { label: 'Battery Voltage', value: c ? `${fmt(c.batteryVoltage, 2)} V`  : '—', cls: c && c.batteryVoltage < 12.2 ? 'warn' : '' },
                { label: 'Oil Pressure',    value: c ? `${fmt(c.oilPressure, 2)} bar`   : '—', cls: c && c.oilPressure < 2 ? 'warn' : '' },
                { label: 'Fuel Pressure',   value: c ? `${fmt(c.fuelPressure, 2)} bar`  : '—', cls: '' },
                { label: 'MAP Sensor',      value: c ? `${fmt(c.mapSensor, 1)} kPa`     : '—', cls: '' },
                { label: 'Intake Air Temp', value: c ? `${fmt(c.intakeAirTemp)} °C`     : '—', cls: '' },
                { label: 'Coolant Temp',    value: c ? `${fmt(c.coolantTemp)} °C`       : '—', cls: c && c.coolantTemp > 100 ? 'warn' : '' },
                ...(showVibration ? [{ label: 'Vibration',  value: c ? `${fmt(c.vibration, 2)} g`  : '—', cls: c && c.vibration > 5 ? 'warn' : '' }] : []),
                ...(showFuel      ? [{ label: 'Fuel Level', value: c ? `${fmt(c.fuelLevel, 1)} %`  : '—', cls: c && c.fuelLevel < 15 ? 'warn' : '' }] : []),
                { label: 'Throttle Pos',    value: c ? `${fmt(c.throttle)} %`           : '—', cls: '' },
                { label: 'Current Gear',    value: c ? `Gear ${c.gear}`                 : '—', cls: '' },
              ].map(row => (
                <div key={row.label} className="sensor-row">
                  <span className="sensor-label">{row.label}</span>
                  <span className={`sensor-value ${row.cls}`}>{row.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* ── Footer ── */}
          <div className="footer" style={{ gridColumn: '1 / -1' }}>
            <span>ECU Dashboard</span>
            <span className="footer-dot">·</span>
            <span>Mode: <strong style={{ color: 'var(--text-secondary)' }}>
              {mode === 'demo' ? 'Simulation'
                : bridgeOnline ? 'Live OBD2'
                : flaskOnline ? 'Flask API'
                : 'Live (Sim fallback)'}
            </strong></span>
            <span className="footer-dot">·</span>
            <span>Session: <strong style={{ color: 'var(--text-secondary)' }}>{elapsedStr}</strong></span>
            <span className="footer-dot">·</span>
            <span>Samples: <strong style={{ color: 'var(--text-secondary)' }}>{data.history.length}</strong></span>
            <span className="footer-dot">·</span>
            <span
              onClick={handleExport}
              style={{ color: 'var(--teal)', cursor: 'pointer', textDecoration: 'underline' }}
            >
              Export CSV
            </span>
            <span className="footer-dot">·</span>
            <span style={{ color: 'var(--text-muted)' }}>
              Python: {flaskOnline ? '🟢 Flask' : bridgeOnline ? '🟢 Bridge' : '⚫ Offline'}
            </span>
          </div>

        </div>
      </div>

    </div>
  );
}
