const BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

async function request(url, options = {}) {
  try {
    const res = await fetch(`${BASE}${url}`, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Request failed');
    }
    return await res.json();
  } catch (err) {
    console.error(`API Error [${url}]:`, err);
    throw err;
  }
}

const api = {
  // Config
  getConfig: () => request('/api/config'),
  setConfig: (data) => request('/api/config', { method: 'POST', body: JSON.stringify(data) }),
  validateConfig: () => request('/api/config/validate', { method: 'POST' }),
  getBlacklist: () => request('/api/settings/blacklist'),
  updateBlacklist: (symbol, action) => request('/api/settings/blacklist', { 
    method: 'POST', body: JSON.stringify({ symbol, action }) 
  }),
  getRiskConfig: () => request('/api/risk-config'),
  setRiskConfig: (data) => request('/api/risk-config', { method: 'POST', body: JSON.stringify(data) }),


  // Account
  getAccount: () => request('/api/account'),
  getPortfolioHistory: (period = '1M', timeframe = '1D') =>
    request(`/api/account/portfolio-history?period=${period}&timeframe=${timeframe}`),

  // Positions
  getPositions: () => request('/api/positions'),
  closeAllPositions: () => request('/api/positions/close-all', { method: 'POST' }),

  // Orders
  getOrders: (status = 'all', limit = 50) =>
    request(`/api/orders?status=${status}&limit=${limit}`),

  // Market Data
  getChartData: (symbol, period = '5d', interval = '1h') =>
    request(`/api/market/chart/${encodeURIComponent(symbol)}?period=${period}&interval=${interval}`),
  getQuote: (symbol) => request(`/api/market/quote/${encodeURIComponent(symbol)}`),
  getPairs: () => request('/api/market/pairs'),
  scanMarket: (market = 'stocks') => request(`/api/market/scan?market=${market}`),

  // Bot
  startBot: (mode) => request(`/api/bot/start/${mode}`, { method: 'POST' }),
  stopBot: () => request('/api/bot/stop', { method: 'POST' }),
  getBotStatus: () => request('/api/bot/status'),
  getBotLogs: (last = 50) => request(`/api/bot/logs?last=${last}`),

  // Backtest
  runBacktest: (symbolA, symbolB) =>
    request('/api/backtest', { method: 'POST', body: JSON.stringify({ symbol_a: symbolA, symbol_b: symbolB }) }),
  runBacktestAll: () => request('/api/backtest/all'),
  runAccountBacktest: () => request('/api/backtest/account'),
};

export default api;
