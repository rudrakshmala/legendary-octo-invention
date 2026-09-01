import { useState, useEffect, useRef } from 'react';
import { FlaskConical, TrendingUp, TrendingDown, BarChart3, Globe, Trophy, AlertCircle } from 'lucide-react';
import { createChart, ColorType } from 'lightweight-charts';
import api from '../api/client';

/* ─────────────────────────────────────────────
   Reusable mini equity-curve chart
───────────────────────────────────────────── */
function EquityChart({ equityCurve, positive, height = 220 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!equityCurve?.length || !ref.current) return;

    // lightweight-charts requires strictly ascending unique timestamps.
    // Deduplicate: for same date keep the last (most recent) equity value,
    // then sort ascending by date string.
    const dedupMap = new Map();
    for (const p of equityCurve) {
      dedupMap.set(p.date, p.equity); // later values overwrite earlier ones for same date
    }
    const chartData = Array.from(dedupMap.entries())
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([date, equity]) => ({ time: date, value: equity }));

    if (chartData.length < 2) return; // nothing meaningful to plot

    const chart = createChart(ref.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#161b25' },
        textColor: '#8a8f9c',
        fontFamily: "'Inter', sans-serif",
        fontSize: 10,
      },
      grid: { vertLines: { color: '#1e2433' }, horzLines: { color: '#1e2433' } },
      rightPriceScale: { borderColor: '#2a3345' },
      timeScale: { borderColor: '#2a3345', timeVisible: false },
      width: ref.current.clientWidth,
      height,
    });
    const series = chart.addAreaSeries({
      topColor: positive ? 'rgba(38,166,154,0.35)' : 'rgba(239,83,80,0.35)',
      bottomColor: positive ? 'rgba(38,166,154,0.02)' : 'rgba(239,83,80,0.02)',
      lineColor: positive ? '#26a69a' : '#ef5350',
      lineWidth: 2,
    });
    series.setData(chartData);
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [equityCurve, positive, height]);
  return <div ref={ref} style={{ height }} />;
}


/* ─────────────────────────────────────────────
   Main Page
───────────────────────────────────────────── */
export default function BacktestPage() {
  const [tab, setTab] = useState('single');

  /* Single-pair */
  const [symbolA, setSymbolA] = useState('MSFT');
  const [symbolB, setSymbolB] = useState('AAPL');
  const [singleResult, setSingleResult] = useState(null);
  const [singleLoading, setSingleLoading] = useState(false);
  const chartRef = useRef(null);
  const chartInstanceRef = useRef(null);

  /* Overall */
  const [overallResult, setOverallResult] = useState(null);
  const [overallLoading, setOverallLoading] = useState(false);
  const [overallError, setOverallError] = useState(null);

  /* Account real trades */
  const [acctResult, setAcctResult] = useState(null);
  const [acctLoading, setAcctLoading] = useState(false);
  const [acctError, setAcctError] = useState(null);

  const pairs = [
    ['MSFT', 'AAPL'], ['KO', 'PEP'], ['XOM', 'CVX'], ['JPM', 'BAC'],
    ['F', 'GM'], ['V', 'MA'], ['LMT', 'RTX'], ['GOOGL', 'META'],
    ['BTC-USD', 'ETH-USD'],
  ];

  /* ── Single backtest ── */
  async function runSingle() {
    setSingleLoading(true);
    setSingleResult(null);
    try {
      const data = await api.runBacktest(symbolA, symbolB);
      setSingleResult(data);
    } catch (err) {
      alert('Backtest failed: ' + err.message);
    }
    setSingleLoading(false);
  }

  useEffect(() => {
    if (!singleResult?.equity_curve?.length || !chartRef.current) return;
    if (chartInstanceRef.current) chartInstanceRef.current.remove();

    // Deduplicate same-date entries, keep last value, sort ascending
    const dedupMap = new Map();
    for (const p of singleResult.equity_curve) dedupMap.set(p.date, p.equity);
    const chartData = Array.from(dedupMap.entries())
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([date, equity]) => ({ time: date, value: equity }));

    const chart = createChart(chartRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#161b25' },
        textColor: '#8a8f9c',
        fontFamily: "'Inter', sans-serif",
        fontSize: 10,
      },
      grid: { vertLines: { color: '#1e2433' }, horzLines: { color: '#1e2433' } },
      rightPriceScale: { borderColor: '#2a3345' },
      timeScale: { borderColor: '#2a3345' },
      width: chartRef.current.clientWidth,
      height: 300,
    });
    chartInstanceRef.current = chart;
    const series = chart.addAreaSeries({
      topColor: singleResult.final_balance >= 10000 ? 'rgba(38,166,154,0.35)' : 'rgba(239,83,80,0.35)',
      bottomColor: singleResult.final_balance >= 10000 ? 'rgba(38,166,154,0.02)' : 'rgba(239,83,80,0.02)',
      lineColor: singleResult.final_balance >= 10000 ? '#26a69a' : '#ef5350',
      lineWidth: 2,
    });
    series.setData(chartData);
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [singleResult]);

  /* ── Overall backtest ── */
  async function runOverall() {
    setOverallLoading(true);
    setOverallResult(null);
    setOverallError(null);
    try {
      const data = await api.runBacktestAll();
      setOverallResult(data);
    } catch (err) {
      setOverallError(err.message || 'Overall backtest failed');
    }
    setOverallLoading(false);
  }

  /* ── Account real-trade backtest ── */
  async function runAccount() {
    setAcctLoading(true);
    setAcctResult(null);
    setAcctError(null);
    try {
      const data = await api.runAccountBacktest();
      setAcctResult(data);
    } catch (err) {
      setAcctError(err.message || 'Account backtest failed. Check API keys.');
    }
    setAcctLoading(false);
  }

  const tabBtn = (id, label) => (
    <button
      onClick={() => setTab(id)}
      style={{
        padding: '6px 18px', borderRadius: '6px', border: 'none',
        cursor: 'pointer', fontWeight: 600, fontSize: '12px', transition: 'all 0.2s',
        background: tab === id ? 'var(--accent-blue)' : 'var(--bg-primary)',
        color: tab === id ? '#fff' : 'var(--text-secondary)',
      }}
    >{label}</button>
  );

  return (
    <div className="page-content">

      {/* ── Tab bar ── */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <FlaskConical size={14} style={{ marginRight: 6 }} />
            Backtester
          </span>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {tabBtn('single', '⚖️ Single Pair')}
            {tabBtn('overall', '🌐 Overall (All Pairs)')}
            {tabBtn('account', '📊 Account Trades')}
          </div>
        </div>
      </div>

      {/* ════════════ SINGLE PAIR ════════════ */}
      {tab === 'single' && (
        <>
          <div className="card">
            <div className="backtest-form" style={{ marginTop: '8px' }}>
              <div className="form-group" style={{ margin: 0 }}>
                <label style={{ fontSize: '10px' }}>Pair</label>
                <select
                  value={`${symbolA}|${symbolB}`}
                  onChange={(e) => {
                    const [a, b] = e.target.value.split('|');
                    setSymbolA(a); setSymbolB(b);
                  }}
                >
                  {pairs.map(([a, b]) => (
                    <option key={`${a}|${b}`} value={`${a}|${b}`}>{a} / {b}</option>
                  ))}
                </select>
              </div>
              <button className="btn btn-primary" onClick={runSingle} disabled={singleLoading}>
                {singleLoading
                  ? <><span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Running...</>
                  : <><FlaskConical size={14} /> Run Backtest</>}
              </button>
            </div>
          </div>

          {singleResult && (
            <>
              <div className="stat-cards">
                <div className="stat-card">
                  <div className="stat-icon blue"><BarChart3 size={18} /></div>
                  <div className="stat-label">Final Balance</div>
                  <div className={`stat-value ${singleResult.final_balance >= 10000 ? 'positive' : 'negative'}`}>
                    ${singleResult.final_balance?.toLocaleString()}
                  </div>
                </div>
                <div className="stat-card">
                  <div className={`stat-icon ${singleResult.total_return_pct >= 0 ? 'green' : 'red'}`}>
                    {singleResult.total_return_pct >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
                  </div>
                  <div className="stat-label">Total Return</div>
                  <div className={`stat-value ${singleResult.total_return_pct >= 0 ? 'positive' : 'negative'}`}>
                    {singleResult.total_return_pct >= 0 ? '+' : ''}{singleResult.total_return_pct}%
                  </div>
                </div>
                <div className="stat-card">
                  <div className="stat-icon purple"><FlaskConical size={18} /></div>
                  <div className="stat-label">Total Trades</div>
                  <div className="stat-value">{singleResult.total_trades}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-icon green"><TrendingUp size={18} /></div>
                  <div className="stat-label">Win Rate</div>
                  <div className="stat-value">{singleResult.win_rate}%</div>
                  <div className="stat-change" style={{ color: 'var(--text-secondary)' }}>
                    {singleResult.wins}W / {singleResult.losses}L
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <span className="card-title">Equity Curve — {symbolA} / {symbolB}</span>
                </div>
                <div ref={chartRef} style={{ height: 300 }} />
              </div>

              <div className="card">
                <div className="card-header">
                  <span className="card-title">Recent Trades</span>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table className="data-table">
                    <thead><tr><th>Date</th><th>Result</th><th>P&amp;L</th></tr></thead>
                    <tbody>
                      {singleResult.trades?.map((t, i) => (
                        <tr key={i}>
                          <td>{t.date}</td>
                          <td>
                            <span className={`signal-badge ${t.result === 'WIN' ? 'buy' : 'sell'}`}>{t.result}</span>
                          </td>
                          <td className={t.pnl >= 0 ? 'positive' : 'negative'}>
                            {t.pnl >= 0 ? '+' : ''}${t.pnl?.toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </>
      )}

      {/* ════════════ OVERALL (ALL PAIRS) ════════════ */}
      {tab === 'overall' && (
        <>
          <div className="card">
            <div style={{ padding: '8px 0' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: 14, lineHeight: 1.7 }}>
                Runs the <strong>Z-Score pairs strategy</strong> on <strong>3 stock pairs</strong> (MSFT/AAPL, KO/PEP, XOM/CVX)
                and <strong>3 crypto pairs</strong> (BTC/ETH, ETH/SOL, BTC/LTC) over the past 12 months.
                Results are aggregated into a single portfolio view — satisfying the hackathon 1–3 pairs requirement.
              </div>
              <button className="btn btn-primary" onClick={runOverall} disabled={overallLoading}
                style={{ justifyContent: 'center' }}>
                {overallLoading
                  ? <><span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Running all pairs (~20s)...</>
                  : <><Globe size={14} style={{ marginRight: 6 }} /> Run Overall Backtest</>}
              </button>
            </div>
          </div>

          {overallError && (
            <div className="card" style={{ border: '1px solid var(--accent-bear)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--accent-bear)', padding: '4px 0' }}>
                <AlertCircle size={16} />
                <span style={{ fontSize: '13px' }}>{overallError}</span>
              </div>
            </div>
          )}

          {overallResult && (() => {
            const s = overallResult.summary;
            const positive = s.total_return_pct >= 0;
            return (
              <>
                {/* Aggregate stat cards */}
                <div className="stat-cards">
                  {[
                    { icon: <Globe size={18} />, cls: 'blue', label: 'Pairs Tested', value: s.pairs_tested, sub: '3 Crypto + 3 Stocks' },
                    { icon: positive ? <TrendingUp size={18} /> : <TrendingDown size={18} />, cls: positive ? 'green' : 'red', label: 'Overall Return', value: `${positive ? '+' : ''}${s.total_return_pct}%`, cls2: positive ? 'positive' : 'negative' },
                    { icon: <FlaskConical size={18} />, cls: 'purple', label: 'Total Trades', value: s.total_trades, sub: `${s.total_wins}W / ${s.total_trades - s.total_wins}L` },
                    { icon: <TrendingUp size={18} />, cls: 'green', label: 'Win Rate', value: `${s.overall_win_rate}%` },
                  ].map((c, i) => (
                    <div className="stat-card" key={i}>
                      <div className={`stat-icon ${c.cls}`}>{c.icon}</div>
                      <div className="stat-label">{c.label}</div>
                      <div className={`stat-value ${c.cls2 || ''}`}>{c.value}</div>
                      {c.sub && <div className="stat-change" style={{ color: 'var(--text-secondary)' }}>{c.sub}</div>}
                    </div>
                  ))}
                </div>

                {/* Capital summary */}
                <div className="card" style={{ border: '1px solid var(--accent-bull)' }}>
                  <div className="card-header">
                    <span className="card-title">
                      <Trophy size={13} style={{ marginRight: 6, color: 'var(--accent-bull)' }} />
                      Portfolio Capital Summary
                    </span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10, padding: '8px 0' }}>
                    {[
                      { label: 'Starting Capital', value: `$${s.total_initial_capital?.toLocaleString()}`, cls: '' },
                      { label: 'Ending Capital',   value: `$${s.total_final_capital?.toLocaleString()}`,   cls: positive ? 'positive' : 'negative' },
                      { label: 'Net P&L',          value: `${positive ? '+' : ''}$${(s.total_final_capital - s.total_initial_capital).toFixed(2)}`, cls: positive ? 'positive' : 'negative' },
                      { label: 'Best Pair',        value: s.best_pair,  cls: 'positive' },
                      { label: 'Worst Pair',       value: s.worst_pair, cls: 'negative' },
                      { label: 'Avg Return/Pair',  value: `${s.avg_return_per_pair_pct?.toFixed(2) ?? s.total_return_pct}%`, cls: positive ? 'positive' : 'negative' },
                    ].map((item, i) => (
                      <div key={i} style={{ textAlign: 'center', padding: '10px 8px', background: 'var(--bg-primary)', borderRadius: 8 }}>
                        <div style={{ fontSize: '10px', color: 'var(--text-secondary)', marginBottom: 4 }}>{item.label}</div>
                        <div className={`stat-value ${item.cls}`} style={{ fontSize: '13px' }}>{item.value}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Per-pair table */}
                <div className="card">
                  <div className="card-header">
                    <span className="card-title">Per-Pair Breakdown</span>
                    <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Sorted best → worst return</span>
                  </div>
                  <div style={{ overflowX: 'auto' }}>
                    <table className="data-table">
                      <thead>
                        <tr><th>#</th><th>Pair</th><th>Market</th><th>Trades</th><th>W / L</th><th>Win Rate</th><th>Return</th><th>Final Balance</th></tr>
                      </thead>
                      <tbody>
                        {overallResult.pair_results?.map((r, i) => (
                          <tr key={i}>
                            <td style={{ color: 'var(--text-secondary)' }}>{i + 1}</td>
                            <td style={{ fontWeight: 600 }}>{r.pair}</td>
                            <td>
                              <span className="signal-badge" style={{
                                background: r.market === 'crypto' ? 'rgba(251,188,4,0.15)' : 'rgba(100,149,237,0.15)',
                                color: r.market === 'crypto' ? '#fbc004' : '#6495ed',
                              }}>
                                {r.market === 'crypto' ? '🪙 Crypto' : '📈 Stock'}
                              </span>
                            </td>
                            <td>{r.total_trades}</td>
                            <td style={{ color: 'var(--text-secondary)' }}>{r.wins}W / {r.losses}L</td>
                            <td>{r.win_rate}%</td>
                            <td className={r.total_return_pct >= 0 ? 'positive' : 'negative'}>
                              {r.total_return_pct >= 0 ? '+' : ''}{r.total_return_pct}%
                            </td>
                            <td className={r.final_balance >= 10000 ? 'positive' : 'negative'}>
                              ${r.final_balance?.toLocaleString()}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Per-pair equity curves */}
                {overallResult.pair_results?.map((r, i) => (
                  <div className="card" key={i}>
                    <div className="card-header">
                      <span className="card-title">
                        {r.market === 'crypto' ? '🪙' : '📈'} {r.pair} — Equity Curve
                      </span>
                      <span className={r.total_return_pct >= 0 ? 'positive' : 'negative'} style={{ fontWeight: 700, fontSize: '13px' }}>
                        {r.total_return_pct >= 0 ? '+' : ''}{r.total_return_pct}%
                      </span>
                    </div>
                    <EquityChart equityCurve={r.equity_curve} positive={r.final_balance >= 10000} />
                  </div>
                ))}
              </>
            );
          })()}
        </>
      )}
      {/* ════════════ ACCOUNT REAL TRADES ════════════ */}
      {tab === 'account' && (
        <>
          <div className="card">
            <div style={{ padding: '8px 0' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: 14, lineHeight: 1.7 }}>
                Fetches <strong>all real filled orders</strong> from your currently connected Alpaca account,
                matches BUY/SELL pairs using FIFO, and computes your <strong>actual realised P&amp;L</strong>.
                This is a true backtest of what the bot actually traded — not simulated data.
              </div>
              <button className="btn btn-primary" onClick={runAccount} disabled={acctLoading}
                style={{ justifyContent: 'center' }}>
                {acctLoading
                  ? <><span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Fetching account orders...</>
                  : <><BarChart3 size={14} style={{ marginRight: 6 }} /> Analyse Account Trades</>}
              </button>
            </div>
          </div>

          {acctError && (
            <div className="card" style={{ border: '1px solid var(--accent-bear)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--accent-bear)', padding: '4px 0' }}>
                <AlertCircle size={16} />
                <span style={{ fontSize: '13px' }}>{acctError}</span>
              </div>
            </div>
          )}

          {acctResult && (() => {
            const s = acctResult.account_summary;
            const positive = s.total_realised_pnl >= 0;
            return (
              <>
                {/* Stat cards */}
                <div className="stat-cards">
                  {[
                    { icon: <BarChart3 size={18} />, cls: 'blue',   label: 'Orders Found',    value: s.total_orders_found,  sub: `${s.matched_trades} matched round-trips` },
                    { icon: positive ? <TrendingUp size={18} /> : <TrendingDown size={18} />, cls: positive ? 'green' : 'red',
                      label: 'Realised P&L', value: `${positive ? '+' : ''}$${s.total_realised_pnl?.toFixed(2)}`,
                      cls2: positive ? 'positive' : 'negative' },
                    { icon: <FlaskConical size={18} />, cls: 'purple', label: 'Return %',
                      value: `${s.total_return_pct >= 0 ? '+' : ''}${s.total_return_pct}%`,
                      cls2: s.total_return_pct >= 0 ? 'positive' : 'negative' },
                    { icon: <TrendingUp size={18} />, cls: 'green', label: 'Win Rate',
                      value: `${s.win_rate}%`, sub: `${s.wins}W / ${s.losses}L` },
                  ].map((c, i) => (
                    <div className="stat-card" key={i}>
                      <div className={`stat-icon ${c.cls}`}>{c.icon}</div>
                      <div className="stat-label">{c.label}</div>
                      <div className={`stat-value ${c.cls2 || ''}`}>{c.value}</div>
                      {c.sub && <div className="stat-change" style={{ color: 'var(--text-secondary)' }}>{c.sub}</div>}
                    </div>
                  ))}
                </div>

                {/* Capital summary banner */}
                <div className="card" style={{ border: `1px solid ${positive ? 'var(--accent-bull)' : 'var(--accent-bear)'}` }}>
                  <div className="card-header">
                    <span className="card-title">
                      <Trophy size={13} style={{ marginRight: 6, color: positive ? 'var(--accent-bull)' : 'var(--accent-bear)' }} />
                      Account Capital Snapshot
                    </span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10, padding: '8px 0' }}>
                    {[
                      { label: 'Last Known Equity',  value: `$${s.starting_equity?.toLocaleString()}`,   cls: '' },
                      { label: 'After All Trades',   value: `$${s.ending_equity?.toLocaleString()}`,     cls: positive ? 'positive' : 'negative' },
                      { label: 'Net Realised P&L',   value: `${positive ? '+' : ''}$${s.total_realised_pnl?.toFixed(2)}`, cls: positive ? 'positive' : 'negative' },
                    ].map((item, i) => (
                      <div key={i} style={{ textAlign: 'center', padding: '12px 8px', background: 'var(--bg-primary)', borderRadius: 8 }}>
                        <div style={{ fontSize: '10px', color: 'var(--text-secondary)', marginBottom: 4 }}>{item.label}</div>
                        <div className={`stat-value ${item.cls}`} style={{ fontSize: '14px' }}>{item.value}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Equity curve */}
                {acctResult.equity_curve?.length > 1 && (
                  <div className="card">
                    <div className="card-header">
                      <span className="card-title">Realised P&amp;L Equity Curve</span>
                      <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Based on actual filled orders</span>
                    </div>
                    <EquityChart equityCurve={acctResult.equity_curve} positive={positive} />
                  </div>
                )}

                {/* Per-symbol breakdown */}
                {acctResult.by_symbol?.length > 0 && (
                  <div className="card">
                    <div className="card-header">
                      <span className="card-title">Per-Symbol Breakdown</span>
                      <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Best → Worst P&L</span>
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                      <table className="data-table">
                        <thead>
                          <tr><th>Symbol</th><th>Trades</th><th>W / L</th><th>Win Rate</th><th>Realised P&amp;L</th></tr>
                        </thead>
                        <tbody>
                          {acctResult.by_symbol.map((r, i) => (
                            <tr key={i}>
                              <td style={{ fontWeight: 700 }}>{r.symbol}</td>
                              <td>{r.trades}</td>
                              <td style={{ color: 'var(--text-secondary)' }}>{r.wins}W / {r.losses}L</td>
                              <td>{r.win_rate}%</td>
                              <td className={r.pnl >= 0 ? 'positive' : 'negative'}>
                                {r.pnl >= 0 ? '+' : ''}${r.pnl?.toFixed(2)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Detailed trade log */}
                {acctResult.trades?.length > 0 && (
                  <div className="card">
                    <div className="card-header">
                      <span className="card-title">Matched Trade Log</span>
                      <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Last 50 closed round-trips</span>
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                      <table className="data-table">
                        <thead>
                          <tr><th>Date</th><th>Symbol</th><th>Type</th><th>Qty</th><th>Entry</th><th>Exit</th><th>Result</th><th>P&amp;L</th></tr>
                        </thead>
                        <tbody>
                          {[...acctResult.trades].reverse().map((t, i) => (
                            <tr key={i}>
                              <td>{t.date}</td>
                              <td style={{ fontWeight: 600 }}>{t.symbol}</td>
                              <td>
                                <span className={`signal-badge ${t.side === 'LONG' ? 'buy' : 'sell'}`}>{t.side}</span>
                              </td>
                              <td style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{t.qty}</td>
                              <td style={{ fontFamily: 'var(--font-mono)' }}>${t.entry}</td>
                              <td style={{ fontFamily: 'var(--font-mono)' }}>${t.exit}</td>
                              <td>
                                <span className={`signal-badge ${t.result === 'WIN' ? 'buy' : 'sell'}`}>{t.result}</span>
                              </td>
                              <td className={t.pnl >= 0 ? 'positive' : 'negative'}>
                                {t.pnl >= 0 ? '+' : ''}${t.pnl?.toFixed(2)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {acctResult.trades?.length === 0 && (
                  <div className="card">
                    <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-secondary)', fontSize: '13px' }}>
                      💤 No matched round-trip trades found on this account yet.<br />
                      <span style={{ fontSize: '11px' }}>Orders are matched only when both a BUY and SELL have been filled for the same symbol.</span>
                    </div>
                  </div>
                )}
              </>
            );
          })()}
        </>
      )}
    </div>
  );
}
