import { useState, useEffect } from 'react';
import { KeyRound, Shield, Sliders, Info, Zap, Target } from 'lucide-react';
import api from '../api/client';

export default function SettingsPage() {
  const [paperApiKey, setPaperApiKey] = useState(() => localStorage.getItem('alpaca_paper_api_key') || '');
  const [paperSecretKey, setPaperSecretKey] = useState(() => localStorage.getItem('alpaca_paper_secret_key') || '');
  const [liveApiKey, setLiveApiKey] = useState(() => localStorage.getItem('alpaca_live_api_key') || '');
  const [liveSecretKey, setLiveSecretKey] = useState(() => localStorage.getItem('alpaca_live_secret_key') || '');
  
  const [paper, setPaper] = useState(() => {
    const val = localStorage.getItem('alpaca_paper');
    return val === null ? true : val === 'true';
  });
  const [groqKey, setGroqKey] = useState(() => localStorage.getItem('groq_api_key') || '');
  const [config, setConfig] = useState(null);
  const [validation, setValidation] = useState(null);
  const [saving, setSaving] = useState(false);

  // ── Risk Configuration ──
  const [riskConfig, setRiskConfig] = useState({
    HARD_STOP_LOSS: -150.0,
    SOFT_STOP_LOSS: -120.0,
    DAILY_PROFIT_TARGET: 2000.0,
    MAX_SECTOR_EXPOSURE: 0.25,
    TRAILING_STOP_PCT: 2.0,
    POSITION_RISK_PCT: 10.0,
    FEE_PCT: 0.1,
  });
  const [riskSaving, setRiskSaving] = useState(false);
  const [riskMsg, setRiskMsg] = useState(null);


  // ── Owner (Personal) Trading Rules ──
  const [ownerSettings, setOwnerSettings] = useState({
    starting_capital_usd: 100,
    daily_profit_target_pct: 5,
    hard_stop_loss_pct: 2,
    max_position_pct: 80,
    trade_once_per_session: true,
    max_hold_hours: 6,
    enable_goal_seeking: false,
    target_goal_usd: 72000,
    deadline_days: 180,
    start_date: '',
    engine_mode: 'hybrid'
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
    // Load risk configuration
    api.getRiskConfig().then(setRiskConfig).catch(() => {});
  }, []);

  async function handleSave() {
    setSaving(true);
    setValidation(null);
    try {
      await api.setConfig({ 
        paper_api_key: paperApiKey, 
        paper_secret_key: paperSecretKey, 
        live_api_key: liveApiKey, 
        live_secret_key: liveSecretKey, 
        paper, 
        groq_key: groqKey 
      });
      // Try to validate based on whichever mode is currently active
      const res = await api.validateConfig();
      if (res.valid) {
        localStorage.setItem('alpaca_paper_api_key', paperApiKey);
        localStorage.setItem('alpaca_paper_secret_key', paperSecretKey);
        localStorage.setItem('alpaca_live_api_key', liveApiKey);
        localStorage.setItem('alpaca_live_secret_key', liveSecretKey);
        localStorage.setItem('alpaca_paper', String(paper));
        localStorage.setItem('groq_api_key', groqKey);
        setValidation({ success: true, msg: `Connected! Portfolio: $${res.portfolio_value?.toLocaleString()}` });
        api.getConfig().then(setConfig);
      } else {
        setValidation({ success: false, msg: res.error || 'Invalid keys for the active mode' });
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

  async function handleRiskSave() {
    setRiskSaving(true);
    setRiskMsg(null);
    try {
      await api.setRiskConfig(riskConfig);
      setRiskMsg({ success: true, msg: 'Risk configuration saved successfully!' });
    } catch (e) {
      setRiskMsg({ success: false, msg: e.message });
    }
    setRiskSaving(false);
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
            <Info size={14} style={{ flexShrink: 0 }} />
            Keys are stored securely in your browser's local storage. Live keys are ONLY kept in memory while the bot runs and never saved to the server's disk.
          </div>
          
          <div className="toggle-row" style={{ background: paper ? 'rgba(38,166,154,0.05)' : 'rgba(239,83,80,0.05)', padding: '12px', borderRadius: '8px', border: `1px solid ${paper ? 'var(--accent-bull)' : 'var(--accent-bear)'}`, marginBottom: '20px' }}>
            <div>
              <label style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>Paper Trading Mode</label>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Turn OFF to trade with real money and Live keys</div>
            </div>
            <div className="toggle-switch">
              <input type="checkbox" checked={paper} onChange={(e) => setPaper(e.target.checked)} />
              <span className="toggle-slider" onClick={() => setPaper(!paper)} />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
            {/* PAPER KEYS */}
            <div style={{ padding: '12px', border: '1px solid var(--border-color)', borderRadius: '8px', opacity: paper ? 1 : 0.6 }}>
              <div style={{ fontSize: '13px', fontWeight: 600, marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                📄 Paper Credentials
                {paper && <span style={{ fontSize: '10px', background: 'var(--accent-bull)', color: '#000', padding: '2px 6px', borderRadius: '4px' }}>ACTIVE</span>}
              </div>
              <div className="form-group" style={{ marginBottom: '12px' }}>
                <label style={{ fontSize: '11px' }}>Paper API Key</label>
                <input type="text" placeholder="PK..." value={paperApiKey} onChange={(e) => setPaperApiKey(e.target.value)} autoComplete="off" />
              </div>
              <div className="form-group">
                <label style={{ fontSize: '11px' }}>Paper Secret Key</label>
                <input type="password" placeholder="..." value={paperSecretKey} onChange={(e) => setPaperSecretKey(e.target.value)} autoComplete="off" />
              </div>
            </div>

            {/* LIVE KEYS */}
            <div style={{ padding: '12px', border: '1px solid var(--border-color)', borderRadius: '8px', opacity: !paper ? 1 : 0.6 }}>
              <div style={{ fontSize: '13px', fontWeight: 600, marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                💵 Live Credentials
                {!paper && <span style={{ fontSize: '10px', background: 'var(--accent-bear)', color: '#fff', padding: '2px 6px', borderRadius: '4px' }}>ACTIVE</span>}
              </div>
              <div className="form-group" style={{ marginBottom: '12px' }}>
                <label style={{ fontSize: '11px' }}>Live API Key</label>
                <input type="text" placeholder="AK..." value={liveApiKey} onChange={(e) => setLiveApiKey(e.target.value)} autoComplete="off" />
              </div>
              <div className="form-group">
                <label style={{ fontSize: '11px' }}>Live Secret Key</label>
                <input type="password" placeholder="..." value={liveSecretKey} onChange={(e) => setLiveSecretKey(e.target.value)} autoComplete="off" />
              </div>
            </div>
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

          {!paper && (
            <div className="validation-result error" style={{ margin: '8px 0', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              ⚠️ LIVE MODE ACTIVE — You will be trading with REAL MONEY!
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
            disabled={saving}
            style={{ marginTop: '12px', width: '100%', justifyContent: 'center' }}
          >
            {saving ? 'Validating Active Keys...' : 'Save & Validate Keys'}
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

      {/* Risk Configuration (editable) */}
      <div className="card">
        <div className="card-header">
          <span className="card-title"><Sliders size={13} style={{ marginRight: 6 }} /> Risk Configuration</span>
        </div>
        <div style={{ padding: '8px 0' }}>
          <div style={{
            padding: '10px 14px', borderRadius: 'var(--radius-md)', marginBottom: '16px',
            background: 'rgba(239,83,80,0.06)', fontSize: '12px', color: 'var(--accent-bear)',
            display: 'flex', alignItems: 'center', gap: '8px'
          }}>
            <Info size={14} style={{ flexShrink: 0 }} />
            Changes take effect immediately in the running bot. Negative values for stop losses.
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div className="form-group">
              <label>Hard Stop Loss ($)</label>
              <input type="number" step="0.01"
                value={riskConfig.HARD_STOP_LOSS}
                onChange={e => setRiskConfig(c => ({ ...c, HARD_STOP_LOSS: parseFloat(e.target.value) || 0 }))}
              />
              <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Kill switch — instant liquidation</span>
            </div>

            <div className="form-group">
              <label>Soft Stop Loss ($)</label>
              <input type="number" step="0.01"
                value={riskConfig.SOFT_STOP_LOSS}
                onChange={e => setRiskConfig(c => ({ ...c, SOFT_STOP_LOSS: parseFloat(e.target.value) || 0 }))}
              />
              <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Warning — reduce position by 50%</span>
            </div>

            <div className="form-group">
              <label>Daily Profit Target ($)</label>
              <input type="number" step="0.01" min="0"
                value={riskConfig.DAILY_PROFIT_TARGET}
                onChange={e => setRiskConfig(c => ({ ...c, DAILY_PROFIT_TARGET: parseFloat(e.target.value) || 0 }))}
              />
              <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Lock-in — stop trading for the day</span>
            </div>

            <div className="form-group">
              <label>Max Sector Exposure (0–1)</label>
              <input type="number" step="0.01" min="0" max="1"
                value={riskConfig.MAX_SECTOR_EXPOSURE}
                onChange={e => setRiskConfig(c => ({ ...c, MAX_SECTOR_EXPOSURE: parseFloat(e.target.value) || 0 }))}
              />
              <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>e.g. 0.25 = max 25% in one sector</span>
            </div>

            <div className="form-group">
              <label>Trailing Stop (%)</label>
              <input type="number" step="0.1" min="0"
                value={riskConfig.TRAILING_STOP_PCT}
                onChange={e => setRiskConfig(c => ({ ...c, TRAILING_STOP_PCT: parseFloat(e.target.value) || 0 }))}
              />
            </div>

            <div className="form-group">
              <label>Position Risk (% of buying power)</label>
              <input type="number" step="0.1" min="0" max="100"
                value={riskConfig.POSITION_RISK_PCT}
                onChange={e => setRiskConfig(c => ({ ...c, POSITION_RISK_PCT: parseFloat(e.target.value) || 0 }))}
              />
            </div>

            <div className="form-group" style={{ gridColumn: 'span 2' }}>
              <label>Fee Per Side (%)</label>
              <input type="number" step="0.01" min="0"
                value={riskConfig.FEE_PCT}
                onChange={e => setRiskConfig(c => ({ ...c, FEE_PCT: parseFloat(e.target.value) || 0 }))}
              />
              <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>0.1 = 0.1% fee per trade side</span>
            </div>
          </div>

          {riskMsg && (
            <div className={`validation-result ${riskMsg.success ? 'success' : 'error'}`} style={{ marginTop: 8 }}>
              {riskMsg.success ? '✅' : '❌'} {riskMsg.msg}
            </div>
          )}

          <button className="btn btn-primary"
            onClick={handleRiskSave}
            disabled={riskSaving}
            style={{ marginTop: 12, width: '100%', justifyContent: 'center' }}
          >
            {riskSaving ? 'Saving...' : '🛡️ Save Risk Configuration'}
          </button>
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

            <div className="form-group" style={{ gridColumn: 'span 2' }}>
              <label>Trading Engine Mode</label>
              <select 
                value={ownerSettings.engine_mode || 'hybrid'} 
                onChange={e => setOwnerSettings(s => ({ ...s, engine_mode: e.target.value }))}
                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)' }}
              >
                <option value="hybrid">🤖 Hybrid (Pairs first, then Universal Stocks) - BEST</option>
                <option value="universal">🌎 Universal Single-Stock Only (Market Scanner)</option>
                <option value="pair">⚖️ Strict Pair Trading Only (Original Strategy)</option>
              </select>
            </div>
          </div>
          
          <hr style={{ border: 'none', borderTop: '1px solid var(--border-color)', margin: '20px 0' }} />
          
          {/* Goal-Seeking Urgency Engine */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--accent-bull)', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Zap size={14} /> Hyper-Aggressive Goal-Seeking Engine
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: 12 }}>
              If enabled, the bot will dynamically calculate the Required Daily Return (RDR) to hit your target by the deadline. 
              If it falls behind schedule, it enters <strong>High-Urgency Mode</strong>: overriding conservative AI filters, bypassing CrewAI validation, maximizing position sizing, and forcing trades mathematically. 
              <br/><br/>
              <em>⚠️ Extreme Risk of total capital loss. Applies to both Paper and Live modes.</em>
            </div>
            
            <div className="toggle-row" style={{ background: 'rgba(239,83,80,0.05)', border: '1px solid var(--accent-bear)', padding: 12, borderRadius: 8, marginBottom: 16 }}>
              <div>
                <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>Enable Goal-Seeking Engine</label>
              </div>
              <div className="toggle-switch">
                <input type="checkbox" checked={ownerSettings.enable_goal_seeking}
                  onChange={e => {
                    const enabled = e.target.checked;
                    setOwnerSettings(s => ({ 
                      ...s, 
                      enable_goal_seeking: enabled,
                      start_date: enabled && !s.start_date ? new Date().toISOString().split('T')[0] : s.start_date
                    }));
                  }} />
                <span className="toggle-slider"
                  onClick={() => {
                    const enabled = !ownerSettings.enable_goal_seeking;
                    setOwnerSettings(s => ({ 
                      ...s, 
                      enable_goal_seeking: enabled,
                      start_date: enabled && !s.start_date ? new Date().toISOString().split('T')[0] : s.start_date
                    }));
                  }} />
              </div>
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, opacity: ownerSettings.enable_goal_seeking ? 1 : 0.4, pointerEvents: ownerSettings.enable_goal_seeking ? 'auto' : 'none' }}>
              <div className="form-group">
                <label>Target Goal (USD)</label>
                <input type="number" min="10" step="10"
                  value={ownerSettings.target_goal_usd}
                  onChange={e => setOwnerSettings(s => ({ ...s, target_goal_usd: parseFloat(e.target.value) || 0 }))}
                />
                <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>₹60 Lakh ≈ $72,000 USD</span>
              </div>
              
              <div className="form-group">
                <label>Deadline (Days)</label>
                <input type="number" min="1" step="1"
                  value={ownerSettings.deadline_days}
                  onChange={e => setOwnerSettings(s => ({ ...s, deadline_days: parseInt(e.target.value, 10) || 1 }))}
                />
              </div>

              <div className="form-group">
                <label>Start Date</label>
                <input type="date"
                  value={ownerSettings.start_date}
                  onChange={e => setOwnerSettings(s => ({ ...s, start_date: e.target.value }))}
                />
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
