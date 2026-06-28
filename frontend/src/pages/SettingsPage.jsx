import { useState, useEffect } from 'react';
import { KeyRound, Shield, Sliders, Info, Zap, Target } from 'lucide-react';
import api from '../api/client';

export default function SettingsPage() {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('alpaca_api_key') || '');
  const [secretKey, setSecretKey] = useState(() => localStorage.getItem('alpaca_secret_key') || '');
  const [paper, setPaper] = useState(() => {
    const val = localStorage.getItem('alpaca_paper');
    return val === null ? true : val === 'true';
  });
  const [groqKey, setGroqKey] = useState(() => localStorage.getItem('groq_api_key') || '');
  const [config, setConfig] = useState(null);
  const [validation, setValidation] = useState(null);
  const [saving, setSaving] = useState(false);

  // ── Owner (Personal) Trading Rules ──
  const [ownerSettings, setOwnerSettings] = useState({
    starting_capital_usd: 100,
    daily_profit_target_pct: 5,
    hard_stop_loss_pct: 2,
    max_position_pct: 80,
    trade_once_per_session: true,
    max_hold_hours: 6,
  });
  const [ownerSaving, setOwnerSaving] = useState(false);
  const [ownerMsg, setOwnerMsg] = useState(null);

  useEffect(() => {
    api.getConfig().then(setConfig).catch(() => {});
    // Load owner settings
    fetch('/api/owner/settings')
      .then(r => r.json())
      .then(d => setOwnerSettings(d))
      .catch(() => {});
  }, []);

  async function handleSave() {
    setSaving(true);
    setValidation(null);
    try {
      await api.setConfig({ api_key: apiKey, secret_key: secretKey, paper, groq_key: groqKey });
      const res = await api.validateConfig();
      if (res.valid) {
        localStorage.setItem('alpaca_api_key', apiKey);
        localStorage.setItem('alpaca_secret_key', secretKey);
        localStorage.setItem('alpaca_paper', String(paper));
        localStorage.setItem('groq_api_key', groqKey);
        setValidation({ success: true, msg: `Connected! Portfolio: $${res.portfolio_value?.toLocaleString()}` });
        api.getConfig().then(setConfig);
      } else {
        setValidation({ success: false, msg: res.error || 'Invalid keys' });
      }
    } catch (err) {
      setValidation({ success: false, msg: err.message });
    }
    setSaving(false);
  }

  async function handleOwnerSave() {
    setOwnerSaving(true);
    setOwnerMsg(null);
    try {
      const res = await fetch('/api/owner/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(ownerSettings),
      });
      if (res.ok) {
        setOwnerMsg({ success: true, msg: 'Personal trading rules saved!' });
      } else {
        setOwnerMsg({ success: false, msg: 'Save failed. Check backend.' });
      }
    } catch (e) {
      setOwnerMsg({ success: false, msg: e.message });
    }
    setOwnerSaving(false);
  }

  return (
    <div className="page-content" style={{ maxWidth: '700px' }}>
      {/* Connection Status */}
      <div className="card">
        <div className="card-header">
          <span className="card-title"><Shield size={13} style={{ marginRight: 6 }} /> Connection Status</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '8px 0' }}>
          <span className={`status-dot ${config?.configured ? 'online' : 'offline'}`} style={{ width: 12, height: 12 }} />
          <div>
            <div style={{ fontWeight: 600 }}>{config?.configured ? 'Connected to Alpaca' : 'Not Connected'}</div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              {config?.configured ? `Key: ${config.api_key_masked} | ${config.paper ? 'Paper' : 'LIVE'}` : 'Enter your API keys below'}
            </div>
          </div>
        </div>
      </div>

      {/* API Key Configuration */}
      <div className="card">
        <div className="card-header">
          <span className="card-title"><KeyRound size={13} style={{ marginRight: 6 }} /> Alpaca & Groq API Keys</span>
        </div>

        <div style={{ padding: '8px 0' }}>
          <div style={{
            padding: '10px 14px', borderRadius: 'var(--radius-md)', marginBottom: '16px',
            background: 'var(--accent-blue-dim)', fontSize: '12px', color: 'var(--accent-blue)',
            display: 'flex', alignItems: 'center', gap: '8px'
          }}>
            <Info size={14} />
            Keys are saved in your browser's local storage and synced to the backend service.
          </div>

          <div className="form-group">
            <label>Alpaca API Key ID</label>
            <input
              type="text"
              placeholder="PK..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              autoComplete="off"
            />
          </div>

          <div className="form-group">
            <label>Alpaca Secret Key</label>
            <input
              type="password"
              placeholder="Your secret key..."
              value={secretKey}
              onChange={(e) => setSecretKey(e.target.value)}
              autoComplete="off"
            />
          </div>

          <div className="form-group">
            <label>Groq API Key (For AI Agents - Optional)</label>
            <input
              type="password"
              placeholder="gsk_... (Leave blank to use server environment key)"
              value={groqKey}
              onChange={(e) => setGroqKey(e.target.value)}
              autoComplete="off"
            />
          </div>

          <div className="toggle-row">
            <div>
              <label style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>Paper Trading Mode</label>
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Use fake money for testing</div>
            </div>
            <div className="toggle-switch">
              <input type="checkbox" checked={paper} onChange={(e) => setPaper(e.target.checked)} />
              <span className="toggle-slider" onClick={() => setPaper(!paper)} />
            </div>
          </div>

          {!paper && (
            <div className="validation-result error" style={{ margin: '8px 0' }}>
              ⚠️ LIVE MODE — You will be trading with real money!
            </div>
          )}

          {validation && (
            <div className={`validation-result ${validation.success ? 'success' : 'error'}`}>
              {validation.success ? '✅' : '❌'} {validation.msg}
            </div>
          )}

          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={!apiKey || !secretKey || saving}
            style={{ marginTop: '12px', width: '100%', justifyContent: 'center' }}
          >
            {saving ? 'Validating...' : 'Save & Validate Keys'}
          </button>
        </div>
      </div>

      {/* Global Ticker Freeze */}
      <div className="card">
        <div className="card-header">
          <span className="card-title"><Zap size={13} style={{ marginRight: 6 }} /> Global Freeze List</span>
        </div>
        <div style={{ padding: '8px 0' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                Frozen stocks will be completely ignored by all bot modes (Elite, Crypto, and Smart Agent).
            </div>
            
            <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                <input 
                    type="text" 
                    placeholder="ENTER TICKER (e.g. TSLA)" 
                    id="freeze-input"
                    style={{ flex: 1, textTransform: 'uppercase' }}
                />
                <button 
                    className="btn btn-danger" 
                    style={{ padding: '0 16px' }}
                    onClick={async () => {
                        const input = document.getElementById('freeze-input');
                        const symbol = input.value.toUpperCase().trim();
                        if (symbol) {
                            await api.updateBlacklist(symbol, 'freeze');
                            input.value = '';
                            window.location.reload();
                        }
                    }}
                >
                    Freeze
                </button>
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {config?.frozen_tickers?.length > 0 ? (
                    config.frozen_tickers.map(sym => (
                        <div key={sym} className="badge" style={{ 
                            background: 'var(--bg-primary)', padding: '6px 12px',
                            borderRadius: '100px', display: 'flex', alignItems: 'center', gap: '8px',
                            border: '1px solid var(--border-color)'
                        }}>
                            <span style={{ fontWeight: 700, fontSize: '11px' }}>{sym}</span>
                            <button 
                                onClick={async () => {
                                    await api.updateBlacklist(sym, 'unfreeze');
                                    window.location.reload();
                                }}
                                style={{ 
                                    background: 'none', border: 'none', color: 'var(--accent-bull)',
                                    cursor: 'pointer', fontSize: '14px', padding: 0, display: 'flex'
                                }}
                            >
                                <Zap size={10} fill="currentColor" />
                            </button>
                        </div>
                    ))
                ) : (
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                        No tickers currently frozen.
                    </div>
                )}
            </div>
        </div>
      </div>

      {/* Risk Config Info */}
      <div className="card">
        <div className="card-header">
          <span className="card-title"><Sliders size={13} style={{ marginRight: 6 }} /> Risk Configuration</span>
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          <table className="data-table">
            <tbody>
              <tr>
                <td style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-primary)' }}>Hard Stop Loss</td>
                <td className="negative">-$100.00</td>
              </tr>
              <tr>
                <td style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-primary)' }}>Soft Stop Loss</td>
                <td className="negative">-$75.00</td>
              </tr>
              <tr>
                <td style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-primary)' }}>Daily Profit Target</td>
                <td className="positive">+$1,000.00</td>
              </tr>
              <tr>
                <td style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-primary)' }}>Max Sector Exposure</td>
                <td>25%</td>
              </tr>
              <tr>
                <td style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-primary)' }}>Fee Per Side</td>
                <td>0.1%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Owner Personal Trading Rules ── */}
      <div className="card" style={{ borderColor: 'var(--accent-bull)', borderWidth: 1, borderStyle: 'solid' }}>
        <div className="card-header">
          <span className="card-title"><Target size={13} style={{ marginRight: 6, color: 'var(--accent-bull)' }} /> Personal Trading Rules</span>
          <span style={{ fontSize: '10px', color: 'var(--accent-bull)', background: 'rgba(38,166,154,0.12)', padding: '2px 8px', borderRadius: 100 }}>OWNER ONLY</span>
        </div>

        <div style={{ padding: '8px 0' }}>
          {/* Live preview */}
          <div style={{
            padding: '10px 14px', borderRadius: 'var(--radius-md)', marginBottom: 16,
            background: 'rgba(38,166,154,0.08)', fontSize: '12px', color: 'var(--accent-bull)',
            display: 'flex', alignItems: 'center', gap: 8
          }}>
            <Target size={14} />
            On <strong>${ownerSettings.starting_capital_usd.toFixed(2)}</strong> capital →
            &nbsp;Target: <strong>+${(ownerSettings.starting_capital_usd * ownerSettings.daily_profit_target_pct / 100).toFixed(4)}</strong>
            &nbsp;| Stop: <strong>-${(ownerSettings.starting_capital_usd * ownerSettings.hard_stop_loss_pct / 100).toFixed(4)}</strong>
            &nbsp;| Min Z ≥ <strong>{ownerSettings.daily_profit_target_pct < 5 ? '1.5' : ownerSettings.daily_profit_target_pct < 15 ? '1.8' : ownerSettings.daily_profit_target_pct < 30 ? '2.0' : ownerSettings.daily_profit_target_pct < 50 ? '2.3' : '2.5'}</strong>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="form-group">
              <label>Starting Capital (USD)</label>
              <input type="number" min="1" step="0.01"
                value={ownerSettings.starting_capital_usd}
                onChange={e => setOwnerSettings(s => ({ ...s, starting_capital_usd: parseFloat(e.target.value) || 0 }))}
              />
              <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>₹1000 ≈ $11.90 USD</span>
            </div>

            <div className="form-group">
              <label>Max Position Size (%)</label>
              <input type="number" min="1" max="100" step="1"
                value={ownerSettings.max_position_pct}
                onChange={e => setOwnerSettings(s => ({ ...s, max_position_pct: parseFloat(e.target.value) || 10 }))}
              />
            </div>

            <div className="form-group">
              <label>Profit Target (%)</label>
              <input type="number" min="0.1" max="500" step="0.1"
                value={ownerSettings.daily_profit_target_pct}
                onChange={e => setOwnerSettings(s => ({ ...s, daily_profit_target_pct: parseFloat(e.target.value) || 1 }))}
              />
            </div>

            <div className="form-group">
              <label>Hard Stop Loss (%)</label>
              <input type="number" min="0.1" max="100" step="0.1"
                value={ownerSettings.hard_stop_loss_pct}
                onChange={e => setOwnerSettings(s => ({ ...s, hard_stop_loss_pct: parseFloat(e.target.value) || 1 }))}
              />
            </div>

            <div className="form-group">
              <label>Max Hold Time (hours)</label>
              <input type="number" min="0.5" max="24" step="0.5"
                value={ownerSettings.max_hold_hours}
                onChange={e => setOwnerSettings(s => ({ ...s, max_hold_hours: parseFloat(e.target.value) || 6 }))}
              />
            </div>

            <div className="form-group" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
              <div className="toggle-row" style={{ padding: 0 }}>
                <div>
                  <label style={{ fontSize: '13px', fontWeight: 500 }}>Trade Once Per Session</label>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Stop after 1 trade</div>
                </div>
                <div className="toggle-switch">
                  <input type="checkbox" checked={ownerSettings.trade_once_per_session}
                    onChange={e => setOwnerSettings(s => ({ ...s, trade_once_per_session: e.target.checked }))} />
                  <span className="toggle-slider"
                    onClick={() => setOwnerSettings(s => ({ ...s, trade_once_per_session: !s.trade_once_per_session }))} />
                </div>
              </div>
            </div>
          </div>

          {ownerMsg && (
            <div className={`validation-result ${ownerMsg.success ? 'success' : 'error'}`} style={{ marginTop: 8 }}>
              {ownerMsg.success ? '✅' : '❌'} {ownerMsg.msg}
            </div>
          )}

          <button className="btn btn-primary"
            onClick={handleOwnerSave}
            disabled={ownerSaving}
            style={{ marginTop: 12, width: '100%', justifyContent: 'center', background: 'var(--accent-bull)' }}
          >
            {ownerSaving ? 'Saving...' : '💾 Save Personal Trading Rules'}
          </button>
        </div>
      </div>
    </div>
  );
}
