"""
dual_market_bot.py — Dual-Market Trading Bot
===============================================
Uses the Strategy Pattern adapters to run the SAME trading logic
across Indian NSE and Global Forex markets.

This bot follows the EXACT same loop structure as EliteBot/CryptoBot:
  1. Scan pairs → calculate Z-Score
  2. Validate via CrewAI agents (with market-specific context)
  3. Execute trades via the market adapter's broker

It does NOT modify any existing bot or math logic.
"""

import time
import os
import json
import re
import math
import datetime

from market_adapter import BaseMarketAdapter
from agent_context import build_enriched_crew_tasks
from crew_trader import evaluate_open_position


class DualMarketBot:
    """
    A market-agnostic trading bot that delegates all market-specific
    logic to the active adapter (Indian or Forex).
    """

    def __init__(self, market: str = "indian", adapter: BaseMarketAdapter = None):
        """
        Initialize with a specific market adapter.
        market: 'indian' or 'forex' — used if no adapter provided
        adapter: Pre-built adapter instance (for Auto-Shift mode)
        """
        if adapter:
            self.adapter = adapter
        elif market == "indian":
            from indian_market_adapter import IndianMarketAdapter
            self.adapter = IndianMarketAdapter()
        elif market == "forex":
            from forex_market_adapter import ForexMarketAdapter
            self.adapter = ForexMarketAdapter()
        else:
            raise ValueError(f"Unknown market: {market}. Use 'indian' or 'forex'.")

        self.daily_profit = 0.0
        self.cooldowns = {}
        self.journal_file = f"trade_journal_{market}.txt"

        print(f"\n--- 🦅 DUAL-MARKET BOT: {self.adapter.market_name.upper()} MODE ---")
        print(f"   💱 Currency: {self.adapter.currency_symbol}")
        print(f"   📊 Pairs: {len(self.adapter.get_pairs_universe())} pairs loaded")
        print(f"   🔎 Singles: {len(self.adapter.get_single_universe())} tickers loaded")

    # ── AI Decision Parser (same logic as elite_trader_ai.py) ──

    def parse_ai_decision(self, crew_output):
        """
        Safely extracts JSON from CrewAI output.
        SAME logic as elite_trader_ai.py parse_ai_decision — NOT modified.
        """
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

    # ── CrewAI Validation with Market Context ──

    def evaluate_with_context(self, ticker_a, ticker_b, technicals):
        """
        Run CrewAI evaluation with market-specific context injected.
        Uses the SAME agents from crew_trader.py — only task descriptions are enriched.
        """
        from crewai import Task, Crew, Process
        from crew_trader import quant_agent, analyst_agent, bear_analyst_agent, cio_agent

        # Build enriched task descriptions
        descriptions = build_enriched_crew_tasks(
            self.adapter, ticker_a, ticker_b, technicals
        )

        is_pair = ticker_b is not None
        context_str = f"{ticker_a}/{ticker_b}" if is_pair else ticker_a
        type_str = "MEAN-REVERSION PAIR" if is_pair else "SINGLE-TICKER MOMENTUM"

        print(f"\n📢 Assembling the Crew for {context_str} ({self.adapter.market_name} | {type_str})")

        # Create tasks with enriched descriptions
        task_quant = Task(
            description=descriptions["quant"],
            expected_output='A quantitative summary confirming if the technical setup is valid.',
            agent=quant_agent
        )

        task_news = Task(
            description=descriptions["news"],
            expected_output='A fundamental summary of recent catalysts and news sentiment.',
            agent=analyst_agent
        )

        task_bear = Task(
            description=descriptions["bear"],
            expected_output='A concise list of skeptical concerns and risks.',
            agent=bear_analyst_agent
        )

        task_cio = Task(
            description=descriptions["cio"],
            expected_output='A strict JSON final decision object.',
            agent=cio_agent,
            context=[task_quant, task_news, task_bear]
        )

        trading_crew = Crew(
            agents=[quant_agent, analyst_agent, bear_analyst_agent, cio_agent],
            tasks=[task_quant, task_news, task_bear, task_cio],
            process=Process.sequential,
            verbose=True
        )

        return trading_crew.kickoff()

    # ── Trailing Stop (Percentage-Based — Universal) ──

    def trailing_stop_loop(self):
        """
        Percentage-based trailing stop — works for both ₹ and $.
        Same concept as elite_trader_ai.py but uses % instead of absolute values.
        """
        max_profit_pct = 0.0
        stop_pct = -2.0  # -2% hard stop
        trail_step_pct = 0.5  # Raise stop by 0.5% increments
        trigger_pct = 1.0  # Start trailing after 1% profit
        cs = self.adapter.currency_symbol

        print(f"   🚀 RUNNING TRADE (Stop: {stop_pct:.1f}%)")

        while True:
            try:
                positions = self.adapter.get_positions()
                if not positions:
                    return

                # Calculate total PnL 
                total_value = 0
                total_cost = 0
                for pos in positions:
                    if isinstance(pos, dict):
                        total_value += abs(float(pos.get('unrealized_pl', 0)))
                    else:
                        total_value += abs(float(getattr(pos, 'unrealized_pl', 0)))

                curr_pnl = sum(
                    float(p.get('unrealized_pl', 0)) if isinstance(p, dict) 
                    else float(getattr(p, 'unrealized_pl', 0))
                    for p in positions
                )

                buying_power = self.adapter.get_buying_power()
                pnl_pct = (curr_pnl / max(buying_power, 1)) * 100

                if pnl_pct > max_profit_pct:
                    max_profit_pct = pnl_pct
                    if max_profit_pct >= trigger_pct:
                        new_stop = max_profit_pct - trail_step_pct
                        if new_stop > stop_pct:
                            stop_pct = new_stop
                            print(f"\n      🔥 Trailing Stop Raised: {stop_pct:.1f}%")

                print(f"\r      💎 PnL: {cs}{curr_pnl:.2f} ({pnl_pct:.1f}%) | Stop: {stop_pct:.1f}%   ", end="")

                if pnl_pct <= stop_pct:
                    self.adapter.close_all_positions()
                    self.daily_profit += curr_pnl
                    print(f"\n   💰 CLOSED: {cs}{curr_pnl:.2f} ({pnl_pct:.1f}%)")
                    return

                time.sleep(2)
            except Exception:
                time.sleep(5)

    # ── Main Trading Loop ──

    def run(self):
        """
        Main bot loop — mirrors the structure of EliteBot.run() and CryptoBot.run().
        Scan → Validate → Execute → Trail
        """
        import config
        daily_goal = getattr(config, 'DAILY_PROFIT_TARGET', 1000.0)
        daily_stop = getattr(config, 'DAILY_STOP_LOSS', -100.0)

        print(f"   ⏳ Warming up {self.adapter.market_name} scanners...")
        time.sleep(3)

        while True:
            # Daily limits check
            if self.daily_profit >= daily_goal:
                print(f"\n🏆 DAILY GOAL HIT ({self.adapter.currency_symbol}{self.daily_profit:.2f}). Shutting down.")
                break
            if self.daily_profit <= daily_stop:
                print(f"\n🛑 DAILY STOP HIT ({self.adapter.currency_symbol}{self.daily_profit:.2f}). Shutting down.")
                break

            # ── 🤖 ACTIVE POSITION MANAGER (TRADE MANAGER AGENT) ──
            try:
                positions = self.adapter.get_open_positions()
                if positions:
                    print(f"\n[{time.strftime('%H:%M:%S')}] 👮 TRADE MANAGER: Evaluating {len(positions)} open positions...")
                    for p in positions:
                        try:
                            pnl   = float(getattr(p, 'unrealized_pl', 0) or 0)
                            entry = float(getattr(p, 'avg_entry_price', 0) or 0)
                            sym   = str(getattr(p, 'symbol', 'UNKNOWN'))

                            print(f"      🔍 Reviewing {sym} (PnL: {self.adapter.currency_symbol}{pnl:.2f})")

                            try:
                                decision_output = evaluate_open_position(sym, pnl, entry)

                                data = {}
                                if hasattr(decision_output, 'json_dict') and decision_output.json_dict:
                                    data = decision_output.json_dict
                                elif isinstance(decision_output, dict):
                                    data = decision_output
                                elif hasattr(decision_output, 'raw'):
                                    try:
                                        raw = decision_output.raw.strip()
                                        if raw.startswith('```json'): raw = raw[7:-3]
                                        elif raw.startswith('```'): raw = raw[3:-3]
                                        data = json.loads(raw)
                                    except:
                                        pass

                                action = data.get('final_action', 'HOLD').upper()
                                reason = data.get('reason', 'No reason provided')
                                print(f"      🧠 Decision: {action} | Reason: {reason}")

                                if action == 'CLOSE':
                                    print(f"      ⚡ EXECUTING CLOSE on {sym}")
                                    self.adapter.close_position(sym)
                                    self.daily_profit += pnl
                                    print(f"      ✅ Closed {sym} for {self.adapter.currency_symbol}{pnl:.2f}.")

                            except Exception as e:
                                print(f"      ⚠️ Trade Manager failed to evaluate {sym}: {e}")

                        except Exception as inner_e:
                            print(f"      ⚠️ Position loop error: {inner_e}")
            except Exception:
                pass

            print(f"\n[{time.strftime('%H:%M:%S')}] 🔭 SCANNING {self.adapter.market_name.upper()} MARKET...")


            best_opp = None
            best_z = 0

            for sym_a, sym_b in self.adapter.get_pairs_universe():
                # Blacklist check
                try:
                    if os.path.exists("blacklist.json"):
                        with open("blacklist.json", "r") as f:
                            frozen = json.load(f).get("frozen_tickers", [])
                            # Strip suffixes for comparison
                            clean_a = sym_a.replace(".NS", "").replace("=X", "")
                            clean_b = sym_b.replace(".NS", "").replace("=X", "")
                            if clean_a in frozen or clean_b in frozen:
                                continue
                except Exception:
                    pass

                # Cooldown check (1 hour)
                pair_key = f"{sym_a}/{sym_b}"
                if pair_key in self.cooldowns:
                    if time.time() - self.cooldowns[pair_key] < 3600:
                        continue

                # Z-Score calculation — uses the SAME math from BaseMarketAdapter
                z, signal = self.adapter.calculate_z_score(sym_a, sym_b)
                if z is None:
                    continue

                if abs(z) > 1.5 and abs(z) > abs(best_z):
                    best_z, best_opp = z, (sym_a, sym_b, signal)

            if best_opp:
                sym_a, sym_b, signal = best_opp
                pair_key = f"{sym_a}/{sym_b}"

                print(f"\n   🚨 MATH SIGNAL: {sym_a}/{sym_b} (Z={best_z:.2f})")
                print(f"   📞 Calling CrewAI team ({self.adapter.market_name} context)...")

                try:
                    technicals = {"z_score": round(best_z, 2), "type": "pair"}
                    crew_output = self.evaluate_with_context(sym_a, sym_b, technicals)
                    data, should_trade, signal = self.parse_ai_decision(crew_output)

                    print(f"\n   📋 TRADER AGENT OUTPUT:")
                    print(json.dumps(data, indent=2))

                    if not should_trade:
                        print(f"   🛑 Trade Rejected. Cooling down {pair_key} for 1 hour.")
                        self.cooldowns[pair_key] = time.time()
                        time.sleep(15)
                        continue

                    # ── EXECUTION ──
                    cash = self.adapter.get_buying_power()
                    if cash < 100:
                        print(f"   ⚠️ Insufficient buying power ({self.adapter.currency_symbol}{cash})")
                        continue

                    budget = cash * 0.10  # 10% per trade
                    price_a = self.adapter.get_price(sym_a)
                    price_b = self.adapter.get_price(sym_b)

                    qty_a = self.adapter.calculate_position_size(budget, price_a)
                    qty_b = self.adapter.calculate_position_size(budget, price_b)

                    if qty_a > 0 and qty_b > 0 and signal:
                        print(f"   ⚡ EXECUTING: {signal} ({qty_a} {sym_a} / {qty_b} {sym_b})")

                        side_a = "BUY" if signal == "BUY_PAIR" else "SELL"
                        side_b = "SELL" if signal == "BUY_PAIR" else "BUY"

                        self.adapter.submit_order(sym_a, qty_a, side_a)
                        self.adapter.submit_order(sym_b, qty_b, side_b)

                        time.sleep(5)
                        self.trailing_stop_loop()
                    else:
                        print(f"   ⚠️ Skipped: Calculated quantity is 0!")
                        print(f"      Budget: {self.adapter.currency_symbol}{budget:.2f}")
                        print(f"      {sym_a}: {self.adapter.currency_symbol}{price_a} | {sym_b}: {self.adapter.currency_symbol}{price_b}")

                except Exception as e:
                    print(f"   ❌ CrewAI or Execution Failed: {e}")
                    print("   ⏳ Sleeping 60s to reset...")
                    time.sleep(60)
            else:
                print("   💤 No actionable setups found. Retrying in 60s...")
                time.sleep(60)
