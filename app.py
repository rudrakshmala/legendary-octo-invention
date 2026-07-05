"""
Elite-Bot: Multi-Asset AI Trading Hub — API Server
Serves the React frontend with all trading data and bot controls.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import threading
import uvicorn
import time
import math
import os
import json
import datetime
import sys
import traceback

# ── Lazy imports (bots loaded after config is ready) ──
crypto_bot = None
forex_bot = None

bot_thread = None
bot_running = False
active_mode = None

# ── In-memory log buffer ──
MAX_LOG_LINES = 200
bot_logs = []

def add_log(msg, level="info"):
    """Thread-safe log append."""
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    bot_logs.append({"ts": ts, "msg": msg, "level": level})
    if len(bot_logs) > MAX_LOG_LINES:
        bot_logs.pop(0)

class LogInterceptor:
    def __init__(self, original_stdout):
        self.original_stdout = original_stdout
        self.buffer = ""

    def write(self, text):
        try:
            self.original_stdout.write(text.encode('cp1252', errors='replace').decode('cp1252'))
        except:
            pass # Failsafe
            
        self.buffer += text
        if '\n' in self.buffer:
            lines = self.buffer.split('\n')
            for line in lines[:-1]:
                if line.strip():
                    level = "info"
                    if "❌" in line or "error" in line.lower(): level = "error"
                    elif "🚀" in line or "success" in line.lower() or "WIN" in line: level = "success"
                    elif "💤" in line or "warning" in line.lower(): level = "warning"
                    add_log(line.strip(), level)
            self.buffer = lines[-1]

    def flush(self):
        try:
            self.original_stdout.flush()
        except:
            pass

    def isatty(self):
        try:
            return self.original_stdout.isatty()
        except:
            return False

sys.stdout = LogInterceptor(sys.stdout)
sys.stderr = LogInterceptor(sys.stderr)

# ── Dynamic Config Store ──
runtime_config = {
    "api_key": "",
    "secret_key": "",
    "base_url": "https://paper-api.alpaca.markets/v2",
    "paper": True
}

def load_initial_config():
    """Load keys from environment variables or fallback to config.py."""
    # Try to load .env file manually if it exists to populate os.environ
    if os.path.exists(".env"):
        try:
            with open(".env", "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and not os.environ.get(k):
                            os.environ[k] = v
        except Exception:
            pass

    # Ensure environment variables are populated on startup if they exist in config.py
    try:
        import config
        if not os.environ.get("ALPACA_API_KEY"):
            # This triggers __getattr__ and reads fallback from config.py
            os.environ["ALPACA_API_KEY"] = getattr(config, "API_KEY", "")
        if not os.environ.get("ALPACA_SECRET_KEY"):
            os.environ["ALPACA_SECRET_KEY"] = getattr(config, "SECRET_KEY", "")
        if not os.environ.get("ALPACA_PAPER"):
            # Determine paper mode from config
            url = getattr(config, "BASE_URL", "")
            os.environ["ALPACA_PAPER"] = "true" if "paper" in url else "false"
        if not os.environ.get("GROQ_API_KEY"):
            os.environ["GROQ_API_KEY"] = getattr(config, "GROQ_API_KEY", "")
            
        runtime_config["api_key"] = os.environ["ALPACA_API_KEY"]
        runtime_config["secret_key"] = os.environ["ALPACA_SECRET_KEY"]
        runtime_config["paper"] = os.environ["ALPACA_PAPER"].lower() == "true"
        runtime_config["base_url"] = getattr(config, "BASE_URL", "https://paper-api.alpaca.markets/v2")
    except Exception:
        pass

load_initial_config()

def get_trading_client():
    """Create a fresh Alpaca TradingClient with current runtime/env keys."""
    from alpaca.trading.client import TradingClient
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    paper_val = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
    
    if not api_key or not secret_key:
        raise HTTPException(status_code=400, detail="API keys not configured. Go to Settings.")
    return TradingClient(
        api_key,
        secret_key,
        paper=paper_val
    )

def get_crypto_data_client():
    """Create Alpaca CryptoHistoricalDataClient."""
    from alpaca.data.historical import CryptoHistoricalDataClient
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        return None
    return CryptoHistoricalDataClient(api_key, secret_key)

# ── Pydantic models ──
class ApiKeyPayload(BaseModel):
    paper_api_key: str = ""
    paper_secret_key: str = ""
    live_api_key: str = ""
    live_secret_key: str = ""
    paper: bool = True
    groq_key: str = ""

class FreezePayload(BaseModel):
    symbol: str
    action: str # "freeze" or "unfreeze"

class BacktestPayload(BaseModel):
    symbol_a: str
    symbol_b: str

class OwnerSettingsPayload(BaseModel):
    starting_capital_usd: float = 100.0
    daily_profit_target_pct: float = 5.0
    hard_stop_loss_pct: float = 2.0
    max_position_pct: float = 80.0
    trade_once_per_session: bool = True
    max_hold_hours: float = 6.0
    enable_goal_seeking: bool = False
    target_goal_usd: float = 72000.0
    deadline_days: int = 180
    start_date: str = ""


# ── App lifecycle ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    add_log("🦅 ELITE-BOT Backend Online", "success")
    yield
    add_log("🛑 Backend shutting down", "warning")

app = FastAPI(title="Elite-Bot Trading Hub", lifespan=lifespan)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════
# 1. CONFIG / API KEYS
# ═══════════════════════════════════════════

@app.get("/api/health-debug")
def health_debug():
    return {"ok": True, "service": "elite-bot", "time": datetime.datetime.utcnow().isoformat() + "Z"}


@app.get("/api/config")
def get_config():
    """Return masked keys + paper mode status."""
    def mask_key(k):
        return k[:4] + "****" + k[-4:] if k and len(k) > 8 else "Not Set"

    paper_key = os.environ.get("PAPER_API_KEY", "")
    live_key = os.environ.get("LIVE_API_KEY", "")
    
    # Fallback to initial ALPACA_API_KEY if we don't have separated keys yet
    if not paper_key and not live_key:
        curr_key = os.environ.get("ALPACA_API_KEY", runtime_config["api_key"])
        is_paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
        if is_paper:
            paper_key = curr_key
        else:
            live_key = curr_key
            
    groq = os.environ.get("GROQ_API_KEY", "")
    paper_val = os.environ.get("ALPACA_PAPER", "true").lower() == "true"

    # Load frozen tickers for UI display
    frozen = []
    if os.path.exists("blacklist.json"):
        with open("blacklist.json", "r") as f:
            frozen = json.load(f).get("frozen_tickers", [])

    return {
        "paper_api_key_masked": mask_key(paper_key),
        "live_api_key_masked": mask_key(live_key),
        "groq_key_masked": mask_key(groq),
        "paper": paper_val,
        "base_url": "https://paper-api.alpaca.markets/v2" if paper_val else "https://api.alpaca.markets/v2",
        "configured": bool(os.environ.get("ALPACA_API_KEY")),
        "frozen_tickers": frozen
    }

@app.post("/api/config")
def set_config(payload: ApiKeyPayload):
    """Update API keys at runtime."""
    os.environ["PAPER_API_KEY"] = payload.paper_api_key.strip()
    os.environ["PAPER_SECRET_KEY"] = payload.paper_secret_key.strip()
    os.environ["LIVE_API_KEY"] = payload.live_api_key.strip()
    os.environ["LIVE_SECRET_KEY"] = payload.live_secret_key.strip()
    
    os.environ["ALPACA_PAPER"] = str(payload.paper).lower()
    
    if payload.paper:
        os.environ["ALPACA_API_KEY"] = payload.paper_api_key.strip()
        os.environ["ALPACA_SECRET_KEY"] = payload.paper_secret_key.strip()
    else:
        os.environ["ALPACA_API_KEY"] = payload.live_api_key.strip()
        os.environ["ALPACA_SECRET_KEY"] = payload.live_secret_key.strip()
        
    if payload.groq_key.strip():
        os.environ["GROQ_API_KEY"] = payload.groq_key.strip()
    
    runtime_config["api_key"] = os.environ["ALPACA_API_KEY"]
    runtime_config["secret_key"] = os.environ["ALPACA_SECRET_KEY"]
    runtime_config["paper"] = payload.paper
    runtime_config["base_url"] = (
        "https://paper-api.alpaca.markets/v2" if payload.paper
        else "https://api.alpaca.markets/v2"
    )
    add_log(f"🔑 API keys updated (Paper: {payload.paper})", "success")
    return {"msg": "Config updated", "paper": payload.paper}


@app.post("/api/config/validate")
def validate_config():
    """Test if current keys can connect to Alpaca."""
    try:
        client = get_trading_client()
        account = client.get_account()
        return {
            "valid": True,
            "status": account.status,
            "buying_power": float(account.buying_power),
            "portfolio_value": float(account.portfolio_value),
            "cash": float(account.cash)
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}

# ═══════════════════════════════════════════
# 1.5. GLOBAL SETTINGS & BLACKLIST
# ═══════════════════════════════════════════

@app.get("/api/settings/blacklist")
def get_blacklist():
    """Return the current list of frozen tickers."""
    if not os.path.exists("blacklist.json"):
        return {"frozen_tickers": []}
    with open("blacklist.json", "r") as f:
        return json.load(f)

@app.post("/api/settings/blacklist")
def update_blacklist(payload: FreezePayload):
    """Freeze or unfreeze a ticker."""
    data = {"frozen_tickers": []}
    if os.path.exists("blacklist.json"):
        with open("blacklist.json", "r") as f:
            data = json.load(f)
    
    symbol = payload.symbol.upper().strip()
    if payload.action == "freeze":
        if symbol not in data["frozen_tickers"]:
            data["frozen_tickers"].append(symbol)
            add_log(f"❄️ Frozen ticker: {symbol}", "warning")
    else:
        if symbol in data["frozen_tickers"]:
            data["frozen_tickers"].remove(symbol)
            add_log(f"🔥 Unfrozen ticker: {symbol}", "success")
            
    with open("blacklist.json", "w") as f:
        json.dump(data, f, indent=4)
    return data

# ═══════════════════════════════════════════
# 1.7. OWNER (PERSONAL) TRADING RULES
# ═══════════════════════════════════════════

OWNER_SETTINGS_FILE = "owner_settings.json"
OWNER_SETTINGS_DEFAULTS = {
    "starting_capital_usd": 100.0,
    "daily_profit_target_pct": 5.0,
    "hard_stop_loss_pct": 2.0,
    "max_position_pct": 80.0,
    "trade_once_per_session": True,
    "max_hold_hours": 6.0,
    "enable_goal_seeking": False,
    "target_goal_usd": 72000.0,
    "deadline_days": 180,
    "start_date": ""
}

@app.get("/api/owner/settings")
def get_owner_settings():
    """Return the owner's personal trading rules (profit target, stop loss, capital)."""
    if os.path.exists(OWNER_SETTINGS_FILE):
        try:
            with open(OWNER_SETTINGS_FILE, "r") as f:
                saved = json.load(f)
                return {**OWNER_SETTINGS_DEFAULTS, **saved}
        except Exception:
            pass
    return OWNER_SETTINGS_DEFAULTS

@app.post("/api/owner/settings")
def save_owner_settings(payload: OwnerSettingsPayload):
    """Save the owner's personal trading rules to disk."""
    data = payload.dict()
    with open(OWNER_SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    add_log(
        f"⚙️ Owner rules updated: Target={payload.daily_profit_target_pct}% "
        f"Stop={payload.hard_stop_loss_pct}% Capital=${payload.starting_capital_usd:.2f}",
        "success"
    )
    return {"msg": "Owner settings saved", **data}

# ═══════════════════════════════════════════
# 2. ACCOUNT & PORTFOLIO
# ═══════════════════════════════════════════

@app.get("/api/account")
def get_account():
    """Full account info."""
    try:
        client = get_trading_client()
        acct = client.get_account()
        return {
            "status": acct.status,
            "buying_power": float(acct.buying_power),
            "cash": float(acct.cash),
            "portfolio_value": float(acct.portfolio_value),
            "equity": float(acct.equity),
            "last_equity": float(acct.last_equity),
            "long_market_value": float(acct.long_market_value),
            "short_market_value": float(acct.short_market_value),
            "initial_margin": float(acct.initial_margin),
            "maintenance_margin": float(acct.maintenance_margin),
            "daytrade_count": acct.daytrade_count,
            "trading_blocked": acct.trading_blocked,
            "paper": runtime_config["paper"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/account/portfolio-history")
def get_portfolio_history(period: str = "1M", timeframe: str = "1D"):
    """Portfolio equity history for charting."""
    try:
        from alpaca.trading.requests import GetPortfolioHistoryRequest
        client = get_trading_client()
        history = client.get_portfolio_history(
            GetPortfolioHistoryRequest(period=period, timeframe=timeframe)
        )
        return {
            "timestamps": [int(t) for t in (history.timestamp or [])],
            "equity": [float(e) for e in (history.equity or [])],
            "profit_loss": [float(p) for p in (history.profit_loss or [])],
            "profit_loss_pct": [float(p) for p in (history.profit_loss_pct or [])]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════
# 3. POSITIONS
# ═══════════════════════════════════════════

@app.get("/api/positions")
def get_positions():
    """All open positions with live P&L."""
    try:
        client = get_trading_client()
        positions = client.get_all_positions()
        result = []
        for p in positions:
            result.append({
                "symbol": p.symbol,
                "qty": float(p.qty),
                "side": p.side.value if hasattr(p.side, 'value') else str(p.side),
                "market_value": float(p.market_value),
                "cost_basis": float(p.cost_basis),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
                "current_price": float(p.current_price),
                "avg_entry_price": float(p.avg_entry_price),
                "change_today": float(p.change_today) if p.change_today else 0,
            })
        total_pnl = sum(r["unrealized_pl"] for r in result)
        return {"positions": result, "total_pnl": total_pnl, "count": len(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/positions/close-all")
def close_all_positions():
    """Emergency: close all open positions."""
    try:
        client = get_trading_client()
        client.close_all_positions(cancel_orders=True)
        add_log("🔴 ALL POSITIONS CLOSED (Emergency)", "warning")
        return {"msg": "All positions closed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════
# 4. ORDERS
# ═══════════════════════════════════════════

@app.get("/api/orders")
def get_orders(status: str = "all", limit: int = 50):
    """Recent order history."""
    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        status_map = {
            "all": QueryOrderStatus.ALL,
            "open": QueryOrderStatus.OPEN,
            "closed": QueryOrderStatus.CLOSED,
        }
        client = get_trading_client()
        orders = client.get_orders(GetOrdersRequest(
            status=status_map.get(status, QueryOrderStatus.ALL),
            limit=limit
        ))
        result = []
        for o in orders:
            result.append({
                "id": str(o.id),
                "symbol": o.symbol,
                "side": o.side.value if hasattr(o.side, 'value') else str(o.side),
                "qty": str(o.qty),
                "filled_qty": str(o.filled_qty) if o.filled_qty else "0",
                "type": o.type.value if hasattr(o.type, 'value') else str(o.type),
                "status": o.status.value if hasattr(o.status, 'value') else str(o.status),
                "filled_avg_price": str(o.filled_avg_price) if o.filled_avg_price else None,
                "submitted_at": str(o.submitted_at) if o.submitted_at else None,
                "filled_at": str(o.filled_at) if o.filled_at else None,
            })
        return {"orders": result, "count": len(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════
# 5. MARKET DATA
# ═══════════════════════════════════════════

@app.get("/api/market/chart/{symbol}")
def get_chart_data(symbol: str, period: str = "5d", interval: str = "1h"):
    """OHLCV candlestick data for charting."""
    try:
        import yfinance as yf
        import pandas as pd
        df = yf.download(symbol, period=period, interval=interval, progress=False)
        if df.empty:
            return {"candles": [], "symbol": symbol}
        
        # Flatten multi-level columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        candles = []
        for idx, row in df.iterrows():
            ts = int(idx.timestamp()) if hasattr(idx, 'timestamp') else 0
            try:
                o = float(row["Open"]) if not hasattr(row["Open"], '__len__') else float(row["Open"].iloc[0])
                h = float(row["High"]) if not hasattr(row["High"], '__len__') else float(row["High"].iloc[0])
                l = float(row["Low"]) if not hasattr(row["Low"], '__len__') else float(row["Low"].iloc[0])
                c = float(row["Close"]) if not hasattr(row["Close"], '__len__') else float(row["Close"].iloc[0])
                v = float(row["Volume"]) if not hasattr(row["Volume"], '__len__') else float(row["Volume"].iloc[0])
                candles.append({
                    "time": ts,
                    "open": round(o, 4),
                    "high": round(h, 4),
                    "low": round(l, 4),
                    "close": round(c, 4),
                    "volume": int(v),
                })
            except Exception:
                continue
        return {"candles": candles, "symbol": symbol, "period": period, "interval": interval}
    except Exception as e:
        return {"candles": [], "symbol": symbol, "error": str(e)}

@app.get("/api/market/quote/{symbol}")
def get_quote(symbol: str):
    """Latest price quote."""
    try:
        import yfinance as yf
        import pandas as pd
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2d")
        if hist.empty:
            return {"symbol": symbol, "price": 0, "change": 0, "change_pct": 0}
        
        # Flatten multi-level columns
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)
        
        current = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
        change = current - prev
        change_pct = (change / prev * 100) if prev != 0 else 0
        
        return {
            "symbol": symbol,
            "price": round(current, 4),
            "change": round(change, 4),
            "change_pct": round(change_pct, 2),
            "high": round(float(hist["High"].iloc[-1]), 4),
            "low": round(float(hist["Low"].iloc[-1]), 4),
            "volume": int(hist["Volume"].iloc[-1])
        }
    except Exception as e:
        return {"symbol": symbol, "price": 0, "change": 0, "change_pct": 0, "error": str(e)}

@app.get("/api/market/pairs")
def get_market_pairs():
    """All trading pair universes by market type."""
    stock_pairs = [
        {"a": "KO", "b": "PEP", "sector": "Consumer"},
        {"a": "XOM", "b": "CVX", "sector": "Energy"},
        {"a": "JPM", "b": "BAC", "sector": "Banks"},
        {"a": "F", "b": "GM", "sector": "Auto"},
        {"a": "MSFT", "b": "AAPL", "sector": "Tech"},
        {"a": "V", "b": "MA", "sector": "Finance"},
        {"a": "LMT", "b": "RTX", "sector": "Defense"},
        {"a": "GOOGL", "b": "META", "sector": "Tech"},
    ]
    crypto_pairs = [
        {"a": "BTC/USD", "b": "ETH/USD", "sector": "Large Cap"},
        {"a": "ETH/USD", "b": "SOL/USD", "sector": "Smart Contract"},
        {"a": "BTC/USD", "b": "LTC/USD", "sector": "Store of Value"},
        {"a": "DOGE/USD", "b": "SHIB/USD", "sector": "Meme"},
        {"a": "ETH/USD", "b": "AVAX/USD", "sector": "Layer 1"},
        {"a": "BCH/USD", "b": "LTC/USD", "sector": "Legacy"},
    ]
    return {"stocks": stock_pairs, "crypto": crypto_pairs}

@app.get("/api/market/scan")
def scan_market(market: str = "stocks"):
    """Run a market scan and return Z-scores for all pairs."""
    results = []
    try:
        if market == "stocks":
            import yfinance as yf
            import pandas as pd
            pairs = [("KO","PEP"),("XOM","CVX"),("JPM","BAC"),("F","GM"),("MSFT","AAPL"),("V","MA"),("LMT","RTX"),("GOOGL","META")]
            for sym_a, sym_b in pairs:
                try:
                    data_a = yf.download(sym_a, period="5d", interval="1h", progress=False)['Close'].squeeze()
                    data_b = yf.download(sym_b, period="5d", interval="1h", progress=False)['Close'].squeeze()
                    df = pd.DataFrame({sym_a: data_a, sym_b: data_b}).dropna()
                    if len(df) < 20:
                        results.append({"pair": f"{sym_a}/{sym_b}", "z": None, "signal": "NO DATA"})
                        continue
                    df['ratio'] = df[sym_a] / df[sym_b]
                    mean = df['ratio'].rolling(20).mean()
                    std = df['ratio'].rolling(20).std()
                    df['z'] = (df['ratio'] - mean) / std
                    z = float(df['z'].iloc[-1])
                    if pd.isna(z):
                        results.append({"pair": f"{sym_a}/{sym_b}", "z": None, "signal": "NO DATA"})
                    else:
                        signal = "BUY" if z < -1.5 else "SELL" if z > 1.5 else "HOLD"
                        results.append({"pair": f"{sym_a}/{sym_b}", "z": round(z, 3), "signal": signal})
                except:
                    results.append({"pair": f"{sym_a}/{sym_b}", "z": None, "signal": "ERROR"})
        elif market == "crypto":
            from alpaca.data.historical import CryptoHistoricalDataClient
            from alpaca.data.requests import CryptoBarsRequest
            from alpaca.data.timeframe import TimeFrame
            import pandas as pd
            
            data_client = get_crypto_data_client()
            if not data_client:
                return {"results": [], "error": "API keys not configured"}
            
            pairs = [("BTC/USD","ETH/USD"),("ETH/USD","SOL/USD"),("BTC/USD","LTC/USD"),("DOGE/USD","SHIB/USD"),("ETH/USD","AVAX/USD"),("BCH/USD","LTC/USD")]
            start_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=5)
            for sym_a, sym_b in pairs:
                try:
                    req_a = CryptoBarsRequest(symbol_or_symbols=[sym_a], timeframe=TimeFrame.Hour, limit=100, start=start_time)
                    req_b = CryptoBarsRequest(symbol_or_symbols=[sym_b], timeframe=TimeFrame.Hour, limit=100, start=start_time)
                    bars_a = data_client.get_crypto_bars(req_a).df
                    bars_b = data_client.get_crypto_bars(req_b).df
                    if bars_a.empty or bars_b.empty:
                        results.append({"pair": f"{sym_a}/{sym_b}", "z": None, "signal": "NO DATA"})
                        continue
                    close_a = bars_a.xs(sym_a)['close'] if sym_a in bars_a.index.get_level_values(0) else bars_a['close']
                    close_b = bars_b.xs(sym_b)['close'] if sym_b in bars_b.index.get_level_values(0) else bars_b['close']
                    df = pd.DataFrame({"a": close_a, "b": close_b}).dropna()
                    if len(df) < 20:
                        results.append({"pair": f"{sym_a}/{sym_b}", "z": None, "signal": "NO DATA"})
                        continue
                    df['ratio'] = df['a'] / df['b']
                    mean = df['ratio'].rolling(20).mean()
                    std = df['ratio'].rolling(20).std()
                    df['z'] = (df['ratio'] - mean) / std
                    z = float(df['z'].iloc[-1])
                    if pd.isna(z):
                        results.append({"pair": f"{sym_a}/{sym_b}", "z": None, "signal": "NO DATA"})
                    else:
                        signal = "BUY" if z < -1.5 else "SELL" if z > 1.5 else "HOLD"
                        results.append({"pair": f"{sym_a}/{sym_b}", "z": round(z, 3), "signal": signal})
                except Exception as ex:
                    results.append({"pair": f"{sym_a}/{sym_b}", "z": None, "signal": "ERROR"})
    except Exception as e:
        return {"results": [], "error": str(e)}
    
    return {"results": results, "market": market}

# ═══════════════════════════════════════════
# 6. BOT CONTROL
# ═══════════════════════════════════════════

engine_status = {
    "running": False,
    "mode": None,
    "started_at": None,
    "daily_pnl": 0.0
}

def run_bot_wrapper(mode: str):
    """Wrapper that runs a bot and captures its output."""
    global bot_running
    try:
        add_log(f"🚀 Starting {mode} engine...", "success")
        engine_status["running"] = True
        engine_status["mode"] = mode
        engine_status["started_at"] = datetime.datetime.now().isoformat()
        
        # Dynamically reload trading modules to ensure they bind the latest environment variables
        import importlib
        
        if mode == "elite":
            import crew_trader
            import elite_trader_ai
            importlib.reload(crew_trader)
            importlib.reload(elite_trader_ai)
            bot = elite_trader_ai.EliteBot()
            bot.run()
        elif mode == "crypto":
            import crypto_trader_ai
            importlib.reload(crypto_trader_ai)
            bot = crypto_trader_ai.CryptoBot()
            bot.run()
        elif mode == "sniper":
            import sniper
            importlib.reload(sniper)
            sniper.run_sniper_cycle()
        elif mode == "autopilot":
            import autopilot
            importlib.reload(autopilot)
            while bot_running:
                if autopilot.scan_and_trade():
                    break
                time.sleep(120)
        elif mode == "rl":
            import crew_trader
            import rl_brain
            import rl_autopilot
            importlib.reload(crew_trader)
            importlib.reload(rl_brain)
            importlib.reload(rl_autopilot)
            while bot_running:
                rl_autopilot.run_ai_cycle()
                time.sleep(60)
        elif mode == "smart":
            try:
                import crew_trader
                import smart_trader_ai
                importlib.reload(crew_trader)
                importlib.reload(smart_trader_ai)
                bot = smart_trader_ai.SmartBot()
                bot.run()
            except ImportError:
                add_log("❌ smart_trader_ai.py not found!", "error")
        elif mode == "indian":
            import crew_trader
            import agent_context
            import market_adapter
            import indian_market_adapter
            import dual_market_bot
            importlib.reload(crew_trader)
            importlib.reload(agent_context)
            importlib.reload(market_adapter)
            importlib.reload(indian_market_adapter)
            importlib.reload(dual_market_bot)
            bot = dual_market_bot.DualMarketBot(market="indian")
            bot.run()
        elif mode == "forex":
            import crew_trader
            import agent_context
            import market_adapter
            import forex_market_adapter
            import dual_market_bot
            importlib.reload(crew_trader)
            importlib.reload(agent_context)
            importlib.reload(market_adapter)
            importlib.reload(forex_market_adapter)
            importlib.reload(dual_market_bot)
            bot = dual_market_bot.DualMarketBot(market="forex")
            bot.run()
                
    except Exception as e:
        add_log(f"❌ Bot crashed: {str(e)}", "error")
        import traceback
        traceback.print_exc()
    finally:
        engine_status["running"] = False
        engine_status["mode"] = None
        bot_running = False
        add_log("💤 Bot engine stopped", "warning")


@app.post("/api/bot/start/{mode}")
def start_bot(mode: str):
    """Start a bot in the specified mode."""
    global bot_thread, bot_running
    
    valid_modes = ["elite", "crypto", "sniper", "autopilot", "rl", "smart", "indian", "forex"]
    if mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Choose from: {valid_modes}")
    
    if bot_running:
        return {"msg": f"Bot already running in {engine_status['mode']} mode", "running": True}
    
    bot_running = True
    bot_thread = threading.Thread(target=run_bot_wrapper, args=(mode,), daemon=True)
    bot_thread.start()
    
    return {"msg": f"{mode.title()} bot started", "mode": mode, "running": True}

@app.post("/api/bot/stop")
def stop_bot():
    """Stop the running bot."""
    global bot_running
    bot_running = False
    engine_status["running"] = False
    add_log("⏹️ Bot stop requested by user", "warning")
    return {"msg": "Stop signal sent", "running": False}

@app.get("/api/bot/status")
def get_bot_status():
    """Current bot status + live PnL."""
    live_pnl = 0.0
    try:
        if engine_status["running"]:
            client = get_trading_client()
            positions = client.get_all_positions()
            live_pnl = sum(float(p.unrealized_pl) for p in positions)
    except:
        pass
    
    return {
        "running": engine_status["running"],
        "mode": engine_status["mode"],
        "started_at": engine_status["started_at"],
        "live_pnl": round(live_pnl, 2),
    }

@app.get("/api/bot/logs")
def get_bot_logs(last: int = 50):
    """Return recent bot activity logs."""
    return {"logs": bot_logs[-last:], "total": len(bot_logs)}

@app.get("/api/quant/status")
def get_quant_status():
    """Returns the latest calculated Quant Brain signals from the dynamic JSON state file."""
    import os
    import json
    
    file_path = "quant_signals.json"
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
                return {**data, "active": True}
        except Exception:
            pass
            
    # Default fallback placeholder state
    return {
        "active": False,
        "sym_a": "N/A",
        "sym_b": "N/A",
        "z_score": 0.0,
        "approved": False,
        "regime": "N/A",
        "regime_prob": 0.0,
        "volatility_ok": True,
        "forecasted_vol": 0.0,
        "kelly_fraction": 0.10,
        "hedge_ratio": 1.0,
        "sentiment_score": 0.0,
        "fear_greed": 50,
        "reason": "Quant Brain is inactive. Start Elite Mode to begin scanning.",
        "updated_at": "Never"
    }


# ═══════════════════════════════════════════
# 7. BACKTEST
# ═══════════════════════════════════════════

@app.post("/api/backtest")
def run_backtest(payload: BacktestPayload):
    """Run a backtest on a trading pair."""
    try:
        import yfinance as yf
        import pandas as pd
        import numpy as np
        
        sym_a, sym_b = payload.symbol_a, payload.symbol_b
        
        # Download data
        df_a = yf.download(sym_a, period="1y", interval="1d", progress=False)
        df_b = yf.download(sym_b, period="1y", interval="1d", progress=False)
        
        if df_a.empty or df_b.empty:
            return {"error": "Could not fetch data for one or both symbols"}
        
        # Merge
        df = pd.merge(df_a['Close'], df_b['Close'], left_index=True, right_index=True, suffixes=('_a', '_b'))
        df.columns = ['close_a', 'close_b']
        df['spread'] = df['close_a'] / df['close_b']
        df['z'] = (df['spread'] - df['spread'].rolling(20).mean()) / df['spread'].rolling(20).std()
        df = df.dropna()
        
        # Simulate
        balance = 10000.0
        position = 0
        entry_spread = 0
        trades = []
        equity_curve = []
        
        for idx, row in df.iterrows():
            z = float(row['z'])
            spread = float(row['spread'])
            
            if position == 0:
                if z < -1.5:
                    position = 1
                    entry_spread = spread
                elif z > 1.5:
                    position = -1
                    entry_spread = spread
            elif position != 0:
                if abs(z) < 0.5 or (position == 1 and z > 1.5) or (position == -1 and z < -1.5):
                    pnl = (spread - entry_spread) * 5000 / entry_spread if position == 1 else (entry_spread - spread) * 5000 / entry_spread
                    balance += pnl
                    trades.append({
                        "date": str(idx.date()) if hasattr(idx, 'date') else str(idx),
                        "pnl": round(pnl, 2),
                        "result": "WIN" if pnl > 0 else "LOSS"
                    })
                    position = 0
            
            equity_curve.append({"date": str(idx.date()) if hasattr(idx, 'date') else str(idx), "equity": round(balance, 2)})
        
        wins = len([t for t in trades if t["pnl"] > 0])
        losses = len([t for t in trades if t["pnl"] <= 0])
        
        return {
            "symbol_a": sym_a,
            "symbol_b": sym_b,
            "initial_balance": 10000.0,
            "final_balance": round(balance, 2),
            "total_return_pct": round((balance - 10000) / 100, 2),
            "total_trades": len(trades),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / max(len(trades), 1) * 100, 1),
            "trades": trades[-20:],
            "equity_curve": equity_curve
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════
# SERVE FRONTEND (Production)
# ═══════════════════════════════════════════

# Serve static frontend build if it exists
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)