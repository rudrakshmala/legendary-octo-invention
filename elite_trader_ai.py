import time
import math
import os
import datetime
import json
import re
import yfinance as yf
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
import config

# 🚨 IMPORT AI TEAM
from crew_trader import evaluate_opportunity

JOURNAL_FILE = "trade_journal.txt"
OWNER_SETTINGS_FILE = "owner_settings.json"

PAIRS_UNIVERSE = [
    ("KO", "PEP"), ("XOM", "CVX"), ("JPM", "BAC"),
    ("F", "GM"), ("MSFT", "AAPL"), ("V", "MA"),
    ("LMT", "RTX"), ("GOOGL", "META")
]

print("--- 🧠 ELITE TRADER: CAPITAL-AWARE EDITION ---")

# ── Dynamic paper/live mode from env ──
is_paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
client = TradingClient(config.API_KEY, config.SECRET_KEY, paper=is_paper)
print(f"   📡 Mode: {'📄 PAPER' if is_paper else '💵 LIVE TRADING'}")


# ─────────────────────────────────────────────────
# OWNER SETTINGS LOADER
# ─────────────────────────────────────────────────
def load_owner_settings() -> dict:
    """Load personal trading rules from owner_settings.json."""
    defaults = {
        "starting_capital_usd": 100.0,
        "daily_profit_target_pct": 5.0,
        "hard_stop_loss_pct": 2.0,
        "max_position_pct": 80.0,
        "trade_once_per_session": True,
        "max_hold_hours": 6.0
    }
    try:
        if os.path.exists(OWNER_SETTINGS_FILE):
            with open(OWNER_SETTINGS_FILE, "r") as f:
                saved = json.load(f)
                return {**defaults, **saved}
    except Exception as e:
        print(f"   ⚠️ Could not load owner_settings.json: {e}")
    return defaults


# ─────────────────────────────────────────────────
# DYNAMIC Z-SCORE THRESHOLD (based on profit target)
# ─────────────────────────────────────────────────
def get_min_z_threshold(profit_target_pct: float) -> float:
    """
    Higher profit targets require larger spread divergence.
    Returns the minimum absolute Z-score required to enter a trade.
    """
    if profit_target_pct < 5:
        return 1.5
    elif profit_target_pct < 15:
        return 1.8
    elif profit_target_pct < 30:
        return 2.0
    elif profit_target_pct < 50:
        return 2.3
    else:
        return 2.5


# ─────────────────────────────────────────────────
# Z-SCORE ENGINE
# ─────────────────────────────────────────────────
def calculate_z_score(sym_a, sym_b, window=20):
    try:
        data_a = yf.download(sym_a, period="5d", interval="1h", progress=False)['Close'].squeeze()
        data_b = yf.download(sym_b, period="5d", interval="1h", progress=False)['Close'].squeeze()

        df = pd.DataFrame({sym_a: data_a, sym_b: data_b}).dropna()
        if len(df) < window:
            return None, "HOLD"

        df['ratio'] = df[sym_a] / df[sym_b]
        mean = df['ratio'].rolling(window=window).mean()
        std  = df['ratio'].rolling(window=window).std()
        df['z_score'] = (df['ratio'] - mean) / std

        last_z = float(df['z_score'].iloc[-1])
        signal = "HOLD"
        if last_z < -1.5:
            signal = "BUY_PAIR"
        elif last_z > 1.5:
            signal = "SELL_PAIR"

        return last_z, signal
    except:
        return None, "HOLD"


# ─────────────────────────────────────────────────
# AI JSON PARSER
# ─────────────────────────────────────────────────
def parse_ai_decision(crew_output):
    """Safely extracts JSON from CrewAI output."""
    try:
        clean_text = re.sub(r"```json\s*", "", str(crew_output))
        clean_text = re.sub(r"```\s*", "", clean_text)
        data = json.loads(clean_text)
        final_action = data.get("final_action", "WAIT").upper()
        should_trade = final_action in ("BUY", "SELL")
        signal = "BUY_PAIR" if final_action == "BUY" else "SELL_PAIR" if final_action == "SELL" else None
        return data, should_trade, signal
    except Exception as e:
        print(f"      ⚠️ Failed to parse AI JSON: {e}")
        return {"final_action": "WAIT"}, False, None


# ─────────────────────────────────────────────────
# ELITE BOT
# ─────────────────────────────────────────────────
class EliteBot:
    def __init__(self):
        self.settings          = load_owner_settings()
        self.capital           = self.settings["starting_capital_usd"]
        self.profit_target     = round(self.capital * self.settings["daily_profit_target_pct"] / 100, 4)
        self.hard_stop         = round(self.capital * self.settings["hard_stop_loss_pct"] / 100 * -1, 4)
        self.min_z             = get_min_z_threshold(self.settings["daily_profit_target_pct"])
        self.max_position_pct  = self.settings["max_position_pct"] / 100
        self.once_per_session  = self.settings["trade_once_per_session"]
        self.max_hold_secs     = self.settings["max_hold_hours"] * 3600

        self.live_pnl    = 0.0
        self.daily_profit = self.load_daily_profit()
        self.cooldowns   = {}

        print(f"\n   💰 Capital      : ${self.capital:.2f}")
        print(f"   🎯 Profit Target: +${self.profit_target:.4f}  ({self.settings['daily_profit_target_pct']}%)")
        print(f"   🛑 Hard Stop    : ${self.hard_stop:.4f}  ({self.settings['hard_stop_loss_pct']}%)")
        print(f"   📐 Min Z-Score  : |Z| ≥ {self.min_z}")
        print(f"   ⏱️  Max Hold Time: {self.settings['max_hold_hours']}h")
        print(f"   🔂 Once-per-session: {self.once_per_session}")
        print(f"   📅 Session Profit so far: ${self.daily_profit:.4f}\n")

    # ── Journal ──
    def load_daily_profit(self):
        if not os.path.exists(JOURNAL_FILE):
            return 0.0
        try:
            with open(JOURNAL_FILE, "r") as f:
                line = f.read().strip()
                date, profit = line.split("|")
                if date == str(datetime.date.today()):
                    return float(profit)
        except:
            pass
        return 0.0

    def save_daily_profit(self):
        with open(JOURNAL_FILE, "w") as f:
            f.write(f"{datetime.date.today()}|{self.daily_profit}")

    # ── Account helpers ──
    def get_account_equity(self):
        try:
            return float(client.get_account().equity)
        except:
            return self.capital   # fallback to configured capital

    def get_buying_power(self):
        try:
            return float(client.get_account().buying_power)
        except:
            return 0.0

    def get_price(self, sym):
        try:
            df = yf.download(sym, period="1d", interval="1m", progress=False)
            if not df.empty:
                return float(df['Close'].iloc[-1].squeeze())
        except Exception as e:
            print(f"      ⚠️ Price fetch failed for {sym}: {e}")
        return 0.0

    def close_all(self):
        try:
            client.close_all_positions(cancel_orders=True)
        except:
            pass

    def is_active_trade(self, sym_a, sym_b):
        try:
            positions = client.get_all_positions()
            for p in positions:
                if p.symbol in [sym_a, sym_b]:
                    return True
        except:
            pass
        return False

    # ─────────────────────────────────────────
    # CAPITAL-AWARE TRADE LOOP
    # ─────────────────────────────────────────
    def trailing_stop_loop(self) -> str:
        """
        Monitor open position. Exit on:
          - Profit target hit  → return "TARGET_HIT"
          - Hard stop hit      → return "STOP_HIT"
          - Max hold time      → return "TIME_EXIT"
          - Position gone      → return "CLOSED"
        """
        trade_start = time.time()
        print(f"   🚀 TRADE RUNNING | Target: +${self.profit_target:.4f} | Stop: ${self.hard_stop:.4f}")

        while True:
            try:
                positions = client.get_all_positions()
                if not positions:
                    return "CLOSED"

                curr_pnl = sum(float(p.unrealized_pl) for p in positions)
                self.live_pnl = curr_pnl
                elapsed_h = (time.time() - trade_start) / 3600

                print(
                    f"\r      💎 PnL: ${curr_pnl:+.4f} | "
                    f"Target: +${self.profit_target:.4f} | "
                    f"Stop: ${self.hard_stop:.4f} | "
                    f"Elapsed: {elapsed_h:.1f}h   ",
                    end=""
                )

                # ── TAKE PROFIT ──
                if curr_pnl >= self.profit_target:
                    self.close_all()
                    self.daily_profit += curr_pnl
                    self.save_daily_profit()
                    print(f"\n\n   🏆 PROFIT TARGET HIT! +${curr_pnl:.4f} | Session Total: ${self.daily_profit:.4f}")
                    self.live_pnl = 0.0
                    return "TARGET_HIT"

                # ── HARD STOP ──
                if curr_pnl <= self.hard_stop:
                    self.close_all()
                    self.daily_profit += curr_pnl
                    self.save_daily_profit()
                    print(f"\n\n   🛑 HARD STOP HIT! ${curr_pnl:.4f} | Session Total: ${self.daily_profit:.4f}")
                    self.live_pnl = 0.0
                    return "STOP_HIT"

                # ── MAX HOLD TIME ──
                if (time.time() - trade_start) > self.max_hold_secs:
                    self.close_all()
                    self.daily_profit += curr_pnl
                    self.save_daily_profit()
                    print(f"\n\n   ⏰ MAX HOLD TIME ({self.settings['max_hold_hours']}h) REACHED. PnL: ${curr_pnl:.4f}")
                    self.live_pnl = 0.0
                    return "TIME_EXIT"

                time.sleep(3)

            except Exception:
                time.sleep(5)

    # ─────────────────────────────────────────
    # MAIN RUN LOOP
    # ─────────────────────────────────────────
    def run(self):
        print("   ⏳ Warming up market scanners...")
        time.sleep(3)

        while True:
            # ── Daily guards ──
            if self.daily_profit >= self.profit_target:
                print(f"\n🏆 SESSION GOAL ALREADY HIT (${self.daily_profit:.4f}). Shutting down.")
                break
            if self.daily_profit <= self.hard_stop:
                print(f"\n🛑 SESSION STOP ALREADY HIT (${self.daily_profit:.4f}). Shutting down.")
                break

            print(f"\n[{time.strftime('%H:%M:%S')}] 🔭 SCANNING MARKET... (Min Z ≥ {self.min_z})")
            best_opp = None
            best_z   = 0.0

            for sym_a, sym_b in PAIRS_UNIVERSE:
                # ── Blacklist check ──
                try:
                    if os.path.exists("blacklist.json"):
                        with open("blacklist.json") as f:
                            frozen = json.load(f).get("frozen_tickers", [])
                            if sym_a in frozen or sym_b in frozen:
                                continue
                except:
                    pass

                pair_key = f"{sym_a}/{sym_b}"

                # ── Cooldown check ──
                if pair_key in self.cooldowns:
                    if time.time() - self.cooldowns[pair_key] < 3600:
                        continue

                z, signal = calculate_z_score(sym_a, sym_b)
                if z is None:
                    continue

                # ── Target-driven Z filter ──
                if abs(z) >= self.min_z and abs(z) > abs(best_z):
                    best_z, best_opp = z, (sym_a, sym_b, signal)

            if best_opp:
                sym_a, sym_b, signal = best_opp
                pair_key = f"{sym_a}/{sym_b}"

                if self.is_active_trade(sym_a, sym_b):
                    print(f"   ⚠️ Already in {sym_a}/{sym_b}. Waiting...")
                    time.sleep(10)
                    continue

                print(f"\n   🚨 SIGNAL: {sym_a}/{sym_b}  Z={best_z:.2f} (threshold {self.min_z})")
                print("   📞 Calling CrewAI team for validation...")

                try:
                    # ── Quant Brain ──
                    qs_context  = ""
                    kelly_fraction = self.max_position_pct  # default to owner's max

                    try:
                        from quant.quant_brain import get_quant_signal
                        print(f"   🧠 Quant Brain analysing {sym_a}/{sym_b}...")
                        qs = get_quant_signal(sym_a, sym_b, best_z)

                        print(f"      🟢 Regime: {qs.regime} ({qs.regime_prob:.0%}) | Vol: {'OK' if qs.volatility_ok else 'HIGH'} ({qs.forecasted_vol:.1%})")
                        print(f"      🟢 Kelly: {qs.kelly_fraction:.1%} | Sentiment: {qs.sentiment_score:.2f}")

                        # Save for dashboard
                        try:
                            with open("quant_signals.json", "w") as jf:
                                json.dump({
                                    "sym_a": sym_a, "sym_b": sym_b,
                                    "z_score": round(best_z, 2),
                                    "approved": qs.approved,
                                    "regime": qs.regime,
                                    "regime_prob": round(qs.regime_prob, 2),
                                    "volatility_ok": qs.volatility_ok,
                                    "forecasted_vol": round(qs.forecasted_vol, 4),
                                    "kelly_fraction": round(qs.kelly_fraction, 4),
                                    "hedge_ratio": round(qs.hedge_ratio, 4),
                                    "sentiment_score": round(qs.sentiment_score, 4),
                                    "fear_greed": qs.fear_greed,
                                    "reason": qs.reason,
                                    "updated_at": time.strftime("%H:%M:%S")
                                }, jf)
                        except:
                            pass

                        if not qs.approved:
                            print(f"   🛑 Quant Brain rejected: {qs.reason}")
                            self.cooldowns[pair_key] = time.time()
                            time.sleep(15)
                            continue

                        qs_context = (
                            f"Kalman Hedge Ratio: {qs.hedge_ratio:.4f}\n"
                            f"GARCH Predicted Volatility: {qs.forecasted_vol:.1%}\n"
                            f"Global Market HMM Regime: {qs.regime} (confidence: {qs.regime_prob:.0%})\n"
                            f"Sizing (Kelly Fraction): {qs.kelly_fraction:.1%}\n"
                            f"Micro News Sentiment Score: {qs.sentiment_score:.2f}\n"
                            f"CNN Macro Fear & Greed Index: {qs.fear_greed}/100"
                        )
                        # Use the SMALLER of Kelly and owner's max position size
                        kelly_fraction = min(qs.kelly_fraction, self.max_position_pct)

                    except Exception as q_err:
                        print(f"      ⚠️ Quant Brain failed (using owner max-position fallback): {q_err}")

                    # ── CrewAI Validation ──
                    crew_output = evaluate_opportunity(sym_a, sym_b, best_z, qs_context)
                    data, should_trade, signal = parse_ai_decision(crew_output)

                    print(f"\n   📋 TRADER AGENT OUTPUT:")
                    print(json.dumps(data, indent=2))

                    if not should_trade:
                        print(f"   🛑 AI rejected trade (action: {data.get('final_action', 'WAIT')}). Cooldown 1h.")
                        self.cooldowns[pair_key] = time.time()
                        time.sleep(15)
                        continue

                    # ── CAPITAL-AWARE POSITION SIZING ──
                    equity = self.get_account_equity()
                    budget = round(equity * kelly_fraction, 2)  # e.g. $12 * 0.8 = $9.60

                    if budget < 1.0:
                        print(f"   ⚠️ Budget ${budget:.2f} is below Alpaca's $1 minimum. Skipping.")
                        continue

                    print(f"\n   💰 Equity: ${equity:.2f} | Budget per leg: ${budget:.2f} ({kelly_fraction:.0%})")
                    print(f"   ⚡ EXECUTING: {signal} | {sym_a} vs {sym_b} | ${budget:.2f} notional each")

                    side_a = OrderSide.BUY  if signal == "BUY_PAIR" else OrderSide.SELL
                    side_b = OrderSide.SELL if signal == "BUY_PAIR" else OrderSide.BUY

                    # ── Fractional / Notional orders ──
                    client.submit_order(MarketOrderRequest(
                        symbol=sym_a, notional=budget, side=side_a,
                        time_in_force=TimeInForce.DAY
                    ))
                    client.submit_order(MarketOrderRequest(
                        symbol=sym_b, notional=budget, side=side_b,
                        time_in_force=TimeInForce.DAY
                    ))

                    time.sleep(5)

                    # ── Monitor trade until exit condition ──
                    result = self.trailing_stop_loop()
                    print(f"\n   📊 Trade result: {result}")

                    # ── Once-per-session mode ──
                    if self.once_per_session:
                        print("\n✅ Session complete (once-per-session mode). Restart bot to trade again.")
                        return

                except Exception as e:
                    print(f"   ❌ Error during execution: {e}")
                    print("   ⏳ Sleeping 60s before retrying...")
                    time.sleep(60)

            else:
                print(f"   💤 No pairs with |Z| ≥ {self.min_z} found. Retrying in 60s...")
                time.sleep(60)


if __name__ == "__main__":
    try:
        EliteBot().run()
    except KeyboardInterrupt:
        print("\n👋 Exiting Bot.")