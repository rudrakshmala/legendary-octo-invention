"""
indian_market_adapter.py — Indian NSE Market Adapter
======================================================
Data:      yfinance with .NS suffix (free, no API key)
Execution: Upstox Sandbox (paper trading with sandbox=True)
Context:   Indian macroeconomic data, SEBI, RBI, Nifty 50

SETUP INSTRUCTIONS:
  1. pip install upstox-python-sdk
  2. Go to https://developer.upstox.com
  3. Create a Sandbox App → Generate Sandbox Access Token
  4. Paste token in config.py → UPSTOX_ACCESS_TOKEN
"""

import yfinance as yf
import config
from market_adapter import BaseMarketAdapter


class IndianMarketAdapter(BaseMarketAdapter):
    """
    Adapter for Indian NSE market.
    - Auto-appends .NS to ticker symbols for yfinance data
    - Uses Upstox Sandbox for paper trade execution
    - CrewAI context focused on Indian economy
    """

    def __init__(self):
        self._upstox_api = None
        self._init_upstox()

    def _init_upstox(self):
        """Initialize Upstox client if keys are configured."""
        token = getattr(config, 'UPSTOX_ACCESS_TOKEN', '')
        if not token:
            print("   ⚠️ Upstox token not set. Indian execution disabled (data-only mode).")
            print("   ℹ️  Set UPSTOX_ACCESS_TOKEN in config.py to enable paper trading.")
            return

        try:
            import upstox_client
            configuration = upstox_client.Configuration(sandbox=True)
            configuration.access_token = token
            self._upstox_api = upstox_client.OrderApiV3(
                upstox_client.ApiClient(configuration)
            )
            self._upstox_user_api = upstox_client.UserApi(
                upstox_client.ApiClient(configuration)
            )
            print("   ✅ Upstox Sandbox connected (Paper Mode)")
        except ImportError:
            print("   ⚠️ upstox-python-sdk not installed. Run: pip install upstox-python-sdk")
            self._upstox_api = None
        except Exception as e:
            print(f"   ⚠️ Upstox init failed: {e}")
            self._upstox_api = None

    # ── Properties ──

    @property
    def market_name(self) -> str:
        return "Indian NSE"

    @property
    def currency_symbol(self) -> str:
        return "₹"

    # ── Ticker Universe ──

    def get_pairs_universe(self) -> list:
        """
        Indian blue-chip pairs for statistical arbitrage.
        All tickers use .NS suffix for yfinance NSE data.
        """
        return [
            ("RELIANCE.NS", "TCS.NS"),         # Market Cap Leaders
            ("HDFCBANK.NS", "ICICIBANK.NS"),    # Banking Giants
            ("INFY.NS", "WIPRO.NS"),            # IT Sector
            ("HINDUNILVR.NS", "ITC.NS"),        # FMCG
            ("SBIN.NS", "AXISBANK.NS"),         # PSU vs Private Bank
            ("TATAMOTORS.NS", "MARUTI.NS"),     # Auto Sector
            ("BAJFINANCE.NS", "BAJAJFINSV.NS"), # Bajaj Twins
            ("SUNPHARMA.NS", "DRREDDY.NS"),     # Pharma
        ]

    def get_single_universe(self) -> list:
        """Top NSE stocks for momentum scanning."""
        return [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
            "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
            "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "TITAN.NS",
            "SUNPHARMA.NS", "TATAMOTORS.NS", "WIPRO.NS", "ULTRACEMCO.NS", "BAJFINANCE.NS",
            "NESTLEIND.NS", "POWERGRID.NS", "NTPC.NS", "ONGC.NS", "TATASTEEL.NS",
            "ADANIENT.NS", "ADANIPORTS.NS", "JSWSTEEL.NS", "TECHM.NS", "HCLTECH.NS"
        ]

    # ── Data Methods ──

    def get_price(self, symbol: str) -> float:
        """Fetch latest price from yfinance (.NS tickers work natively)."""
        try:
            df = yf.download(symbol, period="1d", interval="1m", progress=False)
            if not df.empty:
                return float(df['Close'].iloc[-1].squeeze())
        except Exception as e:
            print(f"      ⚠️ Price fetch failed for {symbol}: {e}")
        return 0.0

    # ── Execution Methods (Upstox Sandbox) ──

    def submit_order(self, symbol: str, qty, side: str, **kwargs) -> bool:
        """
        Place order via Upstox Sandbox.
        symbol: NSE symbol like 'RELIANCE.NS' — we strip .NS for Upstox format
        side: 'BUY' or 'SELL'
        """
        if not self._upstox_api:
            print(f"      ⚠️ Upstox not connected. Simulating {side} {qty} {symbol}")
            return False

        try:
            import upstox_client

            # Convert yfinance .NS format to Upstox format
            clean_symbol = symbol.replace(".NS", "")
            trading_symbol = f"NSE_EQ|{clean_symbol}"

            order_request = upstox_client.PlaceOrderV3Request(
                quantity=int(qty),
                product="I",  # Intraday
                validity="DAY",
                price=0,  # Market order
                tag="elite_bot",
                trading_symbol=trading_symbol,
                transaction_type=side.upper(),
                order_type="MARKET",
                instrument_token=kwargs.get('instrument_token', trading_symbol)
            )
            response = self._upstox_api.place_order(body=order_request, api_version="2.0")
            print(f"      ✅ Upstox Order: {side} {qty} {clean_symbol} | ID: {response}")
            return True
        except Exception as e:
            print(f"      ❌ Upstox order failed: {e}")
            return False

    def get_positions(self) -> list:
        """Get open positions from Upstox."""
        if not self._upstox_api:
            return []
        try:
            import upstox_client
            portfolio_api = upstox_client.PortfolioApi(
                upstox_client.ApiClient(
                    upstox_client.Configuration(sandbox=True)
                )
            )
            response = portfolio_api.get_positions(api_version="2.0")
            return response.data if response.data else []
        except Exception:
            return []

    def close_all_positions(self) -> bool:
        """Close all Upstox positions."""
        if not self._upstox_api:
            print("      ⚠️ Upstox not connected. Cannot close positions.")
            return False
        try:
            positions = self.get_positions()
            for pos in positions:
                reverse_side = "SELL" if pos.get("buy_quantity", 0) > 0 else "BUY"
                net_qty = abs(pos.get("net_quantity", 0))
                if net_qty > 0:
                    self.submit_order(
                        pos.get("trading_symbol", ""),
                        net_qty,
                        reverse_side
                    )
            print("      ✂️ All Indian positions closed")
            return True
        except Exception as e:
            print(f"      ❌ Error closing positions: {e}")
            return False

    def get_buying_power(self) -> float:
        """Get available margin from Upstox."""
        if not self._upstox_api:
            return 100000.0  # Default ₹1L for simulation mode
        try:
            if self._upstox_user_api:
                funds = self._upstox_user_api.get_user_fund_margin(api_version="2.0")
                if funds and funds.data:
                    equity = funds.data.get("equity", {})
                    return float(equity.get("available_margin", 100000.0))
        except Exception:
            pass
        return 100000.0  # Fallback

    # ── CrewAI Context ──

    def get_crew_context(self) -> str:
        return (
            "You are analyzing the INDIAN STOCK MARKET (NSE). "
            "Focus on: Indian macroeconomic data, SEBI regulations, "
            "RBI monetary policy announcements, Nifty 50 index movements, "
            "India GDP growth, INR exchange rate fluctuations, "
            "Indian corporate earnings season, FII/DII flow data, "
            "and India-specific geopolitical risks. "
            "All prices are in Indian Rupees (₹). "
            "Trading hours: 09:15 AM to 03.30PM IST."
        )
