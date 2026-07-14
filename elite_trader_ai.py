import time
import math
import os
import datetime
import json
import re
import yfinance as yf
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce
import config

# 🚨 IMPORT AI TEAM
from crew_trader import evaluate_opportunity

# 🛡️ IMPORT RISK GUARDS ENGINE (Additive — does not change existing logic)
from risk_guards import (
    is_safe_trading_hours,
    is_too_late_to_enter,
    has_earnings_soon,
    is_liquid_enough,
    is_drawdown_safe,
    record_equity_snapshot,
    get_mtf_z_score,
    send_telegram_alert,
    run_monte_carlo
)

JOURNAL_FILE    = "trade_journal.txt"
OWNER_SETTINGS_FILE = "owner_settings.json"

PAIRS_UNIVERSE = [
    ("KO", "PEP"), ("XOM", "CVX"), ("JPM", "BAC"),
    ("F", "GM"), ("MSFT", "AAPL"), ("V", "MA"),
    ("LMT", "RTX"), ("GOOGL", "META")
]

UNIVERSAL_STOCKS = [
    "TSLA", "NVDA", "AMD", "META", "AMZN", "NFLX", 
    "COIN", "PLTR", "ROKU", "SNOW", "SQ", "UBER"
]

# ── Dynamic paper/live mode from env ──
is_paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
client   = TradingClient(config.API_KEY, config.SECRET_KEY, paper=is_paper)

print("--- 🧠 ELITE TRADER: MULTIMODAL CREW AI EDITION ---")
print(f"   📡 Mode: {'📄 PAPER TRADING (original behaviour)' if is_paper else '💵 LIVE TRADING (capital-aware mode)'}")


# ─────────────────────────────────────────────────
# PAPER MODE: original fixed settings from config
# ─────────────────────────────────────────────────
DAILY_PROFIT_GOAL = config.DAILY_PROFIT_TARGET   # $1000 default
DAILY_STOP_LOSS   = config.DAILY_STOP_LOSS        # -$100 default
BASE_TARGET       = 150.0
TRAILING_STEP     = 50.0


# ─────────────────────────────────────────────────
# LIVE MODE: load personal trading rules
# ─────────────────────────────────────────────────
def load_owner_settings() -> dict:
    """Load personal trading rules from owner_settings.json (live mode only)."""
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
# DYNAMIC Z-SCORE THRESHOLD (live mode)
# ─────────────────────────────────────────────────
def get_min_z_threshold(profit_target_pct: float) -> float:
    """Higher profit targets require larger spread divergence."""
    if profit_target_pct < 5:    return 1.5
    elif profit_target_pct < 15: return 1.8
    elif profit_target_pct < 30: return 2.0
    elif profit_target_pct < 50: return 2.3
    else:                        return 2.5


# ─────────────────────────────────────────────────
# Z-SCORE ENGINE (shared by both modes)
# ─────────────────────────────────────────────────
def calculate_z_score(sym_a, sym_b, window=20):
    try:
        data_a = yf.download(sym_a, period="5d", interval="1h", progress=False)['Close'].squeeze()
        data_b = yf.download(sym_b, period="5d", interval="1h", progress=False)['Close'].squeeze()

        df = pd.DataFrame({sym_a: data_a, sym_b: data_b}).dropna()
        if len(df) < window:
            return None, "HOLD"

        df['ratio']   = df[sym_a] / df[sym_b]
        mean          = df['ratio'].rolling(window=window).mean()
        std           = df['ratio'].rolling(window=window).std()
        df['z_score'] = (df['ratio'] - mean) / std

        last_z = float(df['z_score'].iloc[-1])
        signal = "HOLD"
        if last_z < -1.5:  signal = "BUY_PAIR"
        elif last_z > 1.5: signal = "SELL_PAIR"

        return last_z, signal
    except:
        return None, "HOLD"


# ─────────────────────────────────────────────────
# AI JSON PARSER (shared by both modes)
# ─────────────────────────────────────────────────
def parse_ai_decision(crew_output):
    """Safely extracts JSON from CrewAI output."""
    try:
        clean_text  = re.sub(r"```json\s*", "", str(crew_output))
        clean_text  = re.sub(r"```\s*", "", clean_text)
        data        = json.loads(clean_text)
        final_action = data.get("final_action", "WAIT").upper()
        should_trade = final_action in ("BUY", "SELL")
        signal       = "BUY_PAIR" if final_action == "BUY" else "SELL_PAIR" if final_action == "SELL" else None
        return data, should_trade, signal
    except Exception as e:
        print(f"      ⚠️ Failed to parse AI JSON: {e}")
        return {"final_action": "WAIT"}, False, None


# ═══════════════════════════════════════════════════
#  ELITE BOT — unified class, mode-aware behaviour
# ═══════════════════════════════════════════════════
class EliteBot:

    def __init__(self):
        self.live_pnl     = 0.0
        self.daily_profit = self.load_daily_profit()
        self.cooldowns    = {}
        
        # Load settings globally so Goal-Seeking applies everywhere
        self.settings = load_owner_settings()
        self.engine_mode = self.settings.get("engine_mode", "hybrid")

        if is_paper:
            # ── PAPER MODE: original fixed settings ──
            self.profit_target  = DAILY_PROFIT_GOAL   # e.g. $1000
            self.hard_stop      = DAILY_STOP_LOSS      # e.g. -$100
            self.min_z          = 1.5
            self.once_per_session = False
            self.max_hold_secs  = None                 # no time limit in paper mode
            self.max_position_pct = None               # uses kelly from quant brain
            print(f"   📄 Paper Mode | Target: ${self.profit_target:.2f} | Stop: ${self.hard_stop:.2f}")

        else:
            # ── LIVE MODE: personal capital-aware settings ──
            capital             = self.settings["starting_capital_usd"]
            self.profit_target  = round(capital * self.settings["daily_profit_target_pct"] / 100, 4)
            self.hard_stop      = round(capital * self.settings["hard_stop_loss_pct"] / 100 * -1, 4)
            self.min_z          = get_min_z_threshold(self.settings["daily_profit_target_pct"])
            self.once_per_session = self.settings["trade_once_per_session"]
            self.max_hold_secs  = self.settings["max_hold_hours"] * 3600
            self.max_position_pct = self.settings["max_position_pct"] / 100
            print(f"\n   💰 Capital      : ${capital:.2f}")
            print(f"   🎯 Profit Target: +${self.profit_target:.4f}  ({self.settings['daily_profit_target_pct']}%)")
            print(f"   🛑 Hard Stop    : ${self.hard_stop:.4f}  ({self.settings['hard_stop_loss_pct']}%)")
            print(f"   📐 Min Z-Score  : |Z| ≥ {self.min_z}")
            print(f"   ⏱️  Max Hold Time: {self.settings['max_hold_hours']}h")
            print(f"   🔂 Once-per-session: {self.once_per_session}")

        # ── Goal-Seeking Engine State ──
        self.bypass_crewai = False
        self.urgency_multiplier = 1.0

        # ── Run Monte Carlo at startup to validate goal feasibility ──
        try:
            goal_settings = self.settings
            if goal_settings.get("enable_goal_seeking") and not is_paper:
                run_monte_carlo(
                    start_capital=goal_settings.get("starting_capital_usd", 100),
                    target=goal_settings.get("target_goal_usd", 72000),
                    days=goal_settings.get("deadline_days", 180)
                )
        except: pass

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
    def get_buying_power(self):
        try: return float(client.get_account().buying_power)
        except: return 0.0

    def get_account_equity(self):
        try: return float(client.get_account().equity)
        except: return self.settings.get("starting_capital_usd", 100.0)

    def get_price(self, sym):
        try:
            df = yf.download(sym, period="1d", interval="1m", progress=False)
            if not df.empty:
                return float(df['Close'].iloc[-1].squeeze())
        except Exception as e:
            print(f"      ⚠️ Price fetch failed for {sym}: {e}")
        return 0.0

    def calculate_qty(self, sym, budget):
        """PAPER MODE: whole-share sizing."""
        price = self.get_price(sym)
        if price <= 0: return 0
        return math.floor((budget * 0.95) / price)

    def close_all(self):
        try: client.close_all_positions(cancel_orders=True)
        except: pass

    def is_active_trade(self, sym_a, sym_b):
        try:
            positions = client.get_all_positions()
            for p in positions:
                if p.symbol in [sym_a, sym_b]: return True
        except: pass
        return False

    # ─────────────────────────────────────────
    # PAPER MODE: original trailing stop loop
    # ─────────────────────────────────────────
    def _paper_trailing_stop_loop(self):
        max_profit = 0.0
        stop_price = DAILY_STOP_LOSS
        print(f"   🚀 RUNNING TRADE (Stop: ${stop_price:.2f})")

        while True:
            try:
                positions = client.get_all_positions()
                if not positions: return "CLOSED"

                curr_pnl = sum([float(p.unrealized_pl) for p in positions])
                self.live_pnl = curr_pnl

                if curr_pnl > max_profit:
                    max_profit = curr_pnl
                    if max_profit >= BASE_TARGET:
                        new_stop = max_profit - TRAILING_STEP
                        if new_stop > stop_price:
                            stop_price = new_stop
                            print(f"\n      🔥 Trailing Stop Raised: ${stop_price:.2f}")

                print(f"\r      💎 PnL: ${curr_pnl:.2f} (Stop: ${stop_price:.2f})   ", end="")

                if curr_pnl <= stop_price:
                    self.close_all()
                    self.daily_profit += curr_pnl
                    self.save_daily_profit()
                    print(f"\n   💰 CLOSED POSITION: ${curr_pnl:.2f}")
                    self.live_pnl = 0.0
                    return "CLOSED"

                time.sleep(2)
            except: time.sleep(5)

    # ─────────────────────────────────────────
    # LIVE MODE: capital-aware exit loop
    # ─────────────────────────────────────────
    def _live_trailing_stop_loop(self) -> str:
        """Exit on: profit target, hard stop, or max hold time."""
        trade_start = time.time()
        print(f"   🚀 TRADE RUNNING | Target: +${self.profit_target:.4f} | Stop: ${self.hard_stop:.4f}")

        while True:
            try:
                positions = client.get_all_positions()
                if not positions: return "CLOSED"

                curr_pnl  = sum(float(p.unrealized_pl) for p in positions)
                self.live_pnl = curr_pnl
                elapsed_h = (time.time() - trade_start) / 3600

                print(
                    f"\r      💎 PnL: ${curr_pnl:+.4f} | "
                    f"Target: +${self.profit_target:.4f} | "
                    f"Stop: ${self.hard_stop:.4f} | "
                    f"Elapsed: {elapsed_h:.1f}h   ", end=""
                )

                # Take-profit
                if curr_pnl >= self.profit_target:
                    self.close_all()
                    self.daily_profit += curr_pnl
                    self.save_daily_profit()
                    print(f"\n\n   🏆 PROFIT TARGET HIT! +${curr_pnl:.4f} | Session: ${self.daily_profit:.4f}")
                    self.live_pnl = 0.0
                    return "TARGET_HIT"

                # Hard stop
                if curr_pnl <= self.hard_stop:
                    self.close_all()
                    self.daily_profit += curr_pnl
                    self.save_daily_profit()
                    print(f"\n\n   🛑 HARD STOP HIT! ${curr_pnl:.4f} | Session: ${self.daily_profit:.4f}")
                    self.live_pnl = 0.0
                    return "STOP_HIT"

                # Max hold time
                if self.max_hold_secs and (time.time() - trade_start) > self.max_hold_secs:
                    self.close_all()
                    self.daily_profit += curr_pnl
                    self.save_daily_profit()
                    print(f"\n\n   ⏰ MAX HOLD TIME REACHED. PnL: ${curr_pnl:.4f}")
                    self.live_pnl = 0.0
                    return "TIME_EXIT"

                time.sleep(3)
            except Exception:
                time.sleep(5)

    # ─────────────────────────────────────────
    # UNIFIED DISPATCHER
    # ─────────────────────────────────────────
    def trailing_stop_loop(self):
        if is_paper:
            return self._paper_trailing_stop_loop()
        else:
            return self._live_trailing_stop_loop()

    # ─────────────────────────────────────────
    # MAIN RUN LOOP
    # ─────────────────────────────────────────
    def run(self):
        print("   ⏳ Warming up market scanners...")
        time.sleep(3)

        # ── Goal-Seeking Engine Check ──
        if self.settings.get("enable_goal_seeking"):
            target_usd = self.settings.get("target_goal_usd", 72000.0)
            deadline_days = self.settings.get("deadline_days", 180)
            start_date_str = self.settings.get("start_date", "")
            
            # Default to 1 day passed if something is wrong
            days_passed = 1 
            if start_date_str:
                try:
                    start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
                    days_passed = (datetime.date.today() - start_date).days
                    if days_passed < 1: days_passed = 1
                except:
                    pass
            
            days_remaining = deadline_days - days_passed
            if days_remaining <= 0: days_remaining = 1
            
            current_capital = self.get_account_equity()
            
            if current_capital > 0 and current_capital < target_usd:
                # Required Daily Return formula: (Target / Current) ^ (1 / Days) - 1
                rdr = (target_usd / current_capital) ** (1.0 / days_remaining) - 1.0
                print(f"\n   🚀 GOAL-SEEKING ENGINE ENGAGED")
                print(f"      Target: ${target_usd:.2f} | Remaining Days: {days_remaining}")
                print(f"      Required Daily Return (RDR): {rdr*100:.2f}%")
                
                if rdr > 0.05: # > 5% daily required
                    print("      ⚠️ STATE: MAXIMUM AGGRESSION (Critical Deficit)")
                    self.bypass_crewai = True
                    self.urgency_multiplier = 2.0
                    self.min_z = max(1.0, self.min_z - 0.5) # Take riskier trades
                elif rdr > 0.02: # > 2% daily required
                    print("      ⚡ STATE: HIGH URGENCY")
                    self.bypass_crewai = True
                    self.urgency_multiplier = 1.5
                    self.min_z = max(1.2, self.min_z - 0.2)
                else:
                    print("      🌿 STATE: SUSTAINABLE GROWTH (Ahead of schedule)")
                    self.bypass_crewai = False
                    self.urgency_multiplier = 1.0

        while True:
            # ── Daily guards ──
            if self.daily_profit >= self.profit_target:
                print(f"\n🏆 {'DAILY' if is_paper else 'SESSION'} GOAL HIT (${self.daily_profit:.4f}). Shutting down.")
                break
            if self.daily_profit <= self.hard_stop:
                print(f"\n🛑 {'DAILY' if is_paper else 'SESSION'} STOP HIT (${self.daily_profit:.4f}). Shutting down.")
                break

            # ── 🛡️ RISK GUARDS (Additive) ──
            # Guard 1: Market Hours
            if not is_safe_trading_hours():
                time.sleep(300)  # Wait 5 min and re-check
                continue

            # Guard 2: Overnight Gap Protection
            if is_too_late_to_enter():
                print("   🌙 Waiting for next session...")
                time.sleep(600)
                continue

            # Guard 3: Rolling Drawdown Circuit Breaker
            current_equity = self.get_account_equity()
            record_equity_snapshot(current_equity)
            if not is_drawdown_safe(current_equity):
                send_telegram_alert("🔴 CIRCUIT BREAKER: 10% drawdown triggered. Trading frozen 24h.")
                time.sleep(86400)  # 24 hour freeze
                continue

            print(f"\n[{time.strftime('%H:%M:%S')}] 🔭 SCANNING MARKET... (Min |Z| ≥ {self.min_z})")
            best_opp = None
            best_z   = 0.0

            if self.engine_mode in ["pair", "hybrid"]:
                for sym_a, sym_b in PAIRS_UNIVERSE:
                    # ── Blacklist check ──
                    try:
                        if os.path.exists("blacklist.json"):
                            with open("blacklist.json") as f:
                                frozen = json.load(f).get("frozen_tickers", [])
                                if sym_a in frozen or sym_b in frozen:
                                    continue
                    except: pass
    
                    pair_key = f"{sym_a}/{sym_b}"
    
                    # ── Cooldown check ──
                    if pair_key in self.cooldowns:
                        if time.time() - self.cooldowns[pair_key] < 3600:
                            continue
    
                    # ── Guard 4: Earnings Blackout ──
                    if has_earnings_soon(sym_a) or has_earnings_soon(sym_b):
                        continue

                    z, signal = calculate_z_score(sym_a, sym_b)
                    if z is None: continue

                    if abs(z) >= self.min_z and abs(z) > abs(best_z):
                        # ── Guard 5: Multi-Timeframe Confirmation ──
                        _, _, mtf_confirmed = get_mtf_z_score(sym_a, sym_b)
                        if mtf_confirmed:
                            best_z, best_opp = z, (sym_a, sym_b, signal)

            if best_opp:
                sym_a, sym_b, signal = best_opp
                pair_key = f"{sym_a}/{sym_b}"

                if self.is_active_trade(sym_a, sym_b):
                    print(f"   ⚠️ Skipping {sym_a}/{sym_b} — already in position.")
                    time.sleep(10)
                    continue

                print(f"\n   🚨 SIGNAL: {sym_a}/{sym_b}  Z={best_z:.2f}")
                print("   📡 Calling CrewAI team for validation...")
                send_telegram_alert(f"📊 Signal Found: {sym_a}/{sym_b} | Z={best_z:.2f}")

                try:
                    # ── Quant Brain ──
                    qs_context     = ""
                    kelly_fraction = 0.10   # safe fallback

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
                        except: pass

                        if not qs.approved:
                            print(f"   🛑 Quant Brain rejected: {qs.reason}. Cooldown 1h.")
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
                        kelly_fraction = qs.kelly_fraction

                    except Exception as q_err:
                        print(f"      ⚠️ Quant Brain failed (safe fallback): {q_err}")

                    # ── CrewAI Validation ──
                    if not self.bypass_crewai:
                        crew_output = evaluate_opportunity(sym_a, sym_b, best_z, qs_context)
                        data, should_trade, signal = parse_ai_decision(crew_output)

                        print(f"\n   📋 TRADER AGENT OUTPUT:")
                        print(json.dumps(data, indent=2))

                        if not should_trade:
                            print(f"   🛑 AI rejected (action: {data.get('final_action', 'WAIT')}). Cooldown 1h.")
                            self.cooldowns[pair_key] = time.time()
                            time.sleep(15)
                            continue
                    else:
                        print(f"\n   ⚡ BYPASSING CREW AI (URGENCY ENGINE): Relying on pure Quantitative Instinct!")
                        should_trade = True
                        signal = "BUY_PAIR" if best_z < 0 else "SELL_PAIR"
                        # Maximize kelly and position size limit
                        kelly_fraction = min(1.0, kelly_fraction * self.urgency_multiplier)

                    # ── EXECUTION — mode-aware ──
                    if is_paper:
                        # PAPER: original whole-share sizing
                        cash = self.get_buying_power()
                        if cash < 100:
                            print(f"   ⚠️ Not enough buying power (${cash:.2f}). Skipping.")
                            continue

                        budget  = cash * kelly_fraction
                        qty_a   = self.calculate_qty(sym_a, budget)
                        qty_b   = self.calculate_qty(sym_b, budget)

                        if qty_a > 0 and qty_b > 0 and signal:
                            print(f"   ⚡ PAPER EXECUTE: {signal} | {qty_a}×{sym_a} / {qty_b}×{sym_b} [Kelly {kelly_fraction:.1%}]")
                            side_a = OrderSide.BUY  if signal == "BUY_PAIR" else OrderSide.SELL
                            side_b = OrderSide.SELL if signal == "BUY_PAIR" else OrderSide.BUY

                            client.submit_order(MarketOrderRequest(symbol=sym_a, qty=qty_a, side=side_a, time_in_force=TimeInForce.GTC))
                            client.submit_order(MarketOrderRequest(symbol=sym_b, qty=qty_b, side=side_b, time_in_force=TimeInForce.GTC))
                        else:
                            print(f"   ⚠️ Qty = 0 — budget ${budget:.2f} | {sym_a}: ${self.get_price(sym_a):.2f} | {sym_b}: ${self.get_price(sym_b):.2f}")
                            continue

                    else:
                        # LIVE: fractional notional sizing
                        equity = self.get_account_equity()
                        # Apply urgency multiplier to max_position_pct (cap at 100%)
                        aggro_position_pct = min(1.0, self.max_position_pct * self.urgency_multiplier)
                        budget = round(equity * aggro_position_pct, 2)

                        if budget < 1.0:
                            print(f"   ⚠️ Budget ${budget:.2f} below Alpaca $1 minimum. Skipping.")
                            continue

                        print(f"   💰 Equity: ${equity:.2f} | Budget per leg: ${budget:.2f}")
                        print(f"   ⚡ LIVE EXECUTE: {signal} | ${budget:.2f} notional ×{sym_a} / ${budget:.2f} notional ×{sym_b}")

                        side_a = OrderSide.BUY  if signal == "BUY_PAIR" else OrderSide.SELL
                        side_b = OrderSide.SELL if signal == "BUY_PAIR" else OrderSide.BUY

                        price_a = self.get_price(sym_a)
                        price_b = self.get_price(sym_b)
                        sl_a = price_a * 0.95 if side_a == OrderSide.BUY else price_a * 1.05
                        sl_b = price_b * 0.95 if side_b == OrderSide.BUY else price_b * 1.05

                        client.submit_order(MarketOrderRequest(
                            symbol=sym_a, notional=budget, side=side_a, time_in_force=TimeInForce.DAY,
                            stop_loss=StopLossRequest(stop_price=round(sl_a, 2))
                        ))
                        client.submit_order(MarketOrderRequest(
                            symbol=sym_b, notional=budget, side=side_b, time_in_force=TimeInForce.DAY,
                            stop_loss=StopLossRequest(stop_price=round(sl_b, 2))
                        ))

                    time.sleep(5)

                    # ── Monitor trade ──
                    result = self.trailing_stop_loop()
                    print(f"\n   📊 Trade result: {result}")

                    # ── Once-per-session (live only) ──
                    if not is_paper and self.once_per_session:
                        print("\n✅ Session complete (once-per-session). Restart bot to trade again.")
                        return

                except Exception as e:
                    print(f"   ❌ Error: {e}")
                    print("   ⏳ Sleeping 60s...")
                    time.sleep(60)

            elif self.engine_mode in ["universal", "hybrid"]:
                print("   🌎 Scanning Universal Market for Breakouts...")
                from quant.quant_brain import get_single_stock_signal
                best_uni = None
                for sym in UNIVERSAL_STOCKS:
                    try:
                        # Guard 4b: Earnings Blackout on universal stocks
                        if has_earnings_soon(sym, days=5):
                            continue
                        # Guard 6: Liquidity Filter
                        if not is_liquid_enough(sym):
                            continue
                        sig, direction = get_single_stock_signal(sym)
                        if sig.approved:
                            best_uni = (sym, direction, sig)
                            break
                    except: pass
                
                if best_uni:
                    sym, direction, sig = best_uni
                    print(f"\\n   🚨 UNIVERSAL SIGNAL: {sym} -> {direction}")
                    print(f"   🧠 Reason: {sig.reason}")
                    
                    try:
                        budget = round(self.get_account_equity() * min(1.0, self.max_position_pct * self.urgency_multiplier), 2)
                        if budget < 1.0:
                            print("   ⚠️ Budget below $1 minimum. Skipping.")
                            continue
                            
                        side = OrderSide.BUY if direction == "BUY_SINGLE" else OrderSide.SELL
                        price = self.get_price(sym)
                        
                        # Bracket Orders: TP based on target, SL 2% (tight strict logic)
                        target_cash = self.profit_target
                        qty = budget / price
                        tp_dist = target_cash / qty
                        
                        tp_price = price + tp_dist if side == OrderSide.BUY else price - tp_dist
                        sl_price = price * 0.98 if side == OrderSide.BUY else price * 1.02
                        
                        print(f"   ⚡ Submitting Bracket Order: TP=${tp_price:.2f}, SL=${sl_price:.2f}")
                        
                        client.submit_order(MarketOrderRequest(
                            symbol=sym, notional=budget, side=side, time_in_force=TimeInForce.DAY,
                            take_profit=TakeProfitRequest(limit_price=round(tp_price, 2)),
                            stop_loss=StopLossRequest(stop_price=round(sl_price, 2))
                        ))
                        send_telegram_alert(
                            f"⚡ TRADE ENTERED\n"
                            f"Stock: {sym} | {direction}\n"
                            f"Entry: ${price:.2f} | Budget: ${budget:.2f}\n"
                            f"🎯 TP: ${tp_price:.2f} | 🛑 SL: ${sl_price:.2f}"
                        )
                        time.sleep(5)
                        
                        result = self.trailing_stop_loop()
                        print(f"\\n   📊 Trade result: {result}")
                        send_telegram_alert(f"📊 Trade Closed: {sym}\nResult: {result}")
                        
                        if not is_paper and self.once_per_session:
                            print("\\n✅ Session complete. Restart bot.")
                            send_telegram_alert("✅ Session complete. Restart bot to trade again.")
                            return
                    except Exception as e:
                        print(f"   ❌ Error: {e}")
                        time.sleep(60)
                else:
                    print(f"   💤 No universal setups found. Retrying in 60s...")
                    time.sleep(60)
            else:
                print(f"   💤 No pairs with |Z| ≥ {self.min_z}. Retrying in 60s...")
                time.sleep(60)


if __name__ == "__main__":
    try:
        EliteBot().run()
    except KeyboardInterrupt:
        print("\n👋 Exiting Bot.")