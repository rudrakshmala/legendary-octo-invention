import re

with open("elite_trader_ai.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update the loop start
target1 = """            for sym_a, sym_b in PAIRS_UNIVERSE:"""
repl1 = """            if self.engine_mode in ["pair", "hybrid"]:
                for sym_a, sym_b in PAIRS_UNIVERSE:"""
content = content.replace(target1, repl1)

# 2. Add catastrophic SL to Pair Live execution
target2 = """                        client.submit_order(MarketOrderRequest(symbol=sym_a, notional=budget, side=side_a, time_in_force=TimeInForce.DAY))
                        client.submit_order(MarketOrderRequest(symbol=sym_b, notional=budget, side=side_b, time_in_force=TimeInForce.DAY))"""

repl2 = """                        price_a = self.get_price(sym_a)
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
                        ))"""
content = content.replace(target2, repl2)

# 3. Add the Universal Branch
target3 = """            else:
                print(f"   💤 No pairs with |Z| ≥ {self.min_z}. Retrying in 60s...")
                time.sleep(60)"""

repl3 = """            elif self.engine_mode in ["universal", "hybrid"]:
                print("   🌎 Scanning Universal Market for Breakouts...")
                from quant.quant_brain import get_single_stock_signal
                best_uni = None
                for sym in UNIVERSAL_STOCKS:
                    try:
                        sig, direction = get_single_stock_signal(sym)
                        if sig.approved:
                            best_uni = (sym, direction, sig)
                            break
                    except: pass
                
                if best_uni:
                    sym, direction, sig = best_uni
                    print(f"\n   🚨 UNIVERSAL SIGNAL: {sym} -> {direction}")
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
                        time.sleep(5)
                        
                        result = self.trailing_stop_loop()
                        print(f"\n   📊 Trade result: {result}")
                        
                        if not is_paper and self.once_per_session:
                            print("\n✅ Session complete. Restart bot.")
                            return
                    except Exception as e:
                        print(f"   ❌ Error: {e}")
                        time.sleep(60)
                else:
                    print(f"   💤 No universal setups found. Retrying in 60s...")
                    time.sleep(60)
            else:
                print(f"   💤 No pairs with |Z| ≥ {self.min_z}. Retrying in 60s...")
                time.sleep(60)"""

content = content.replace(target3, repl3)

with open("elite_trader_ai.py", "w", encoding="utf-8") as f:
    f.write(content)
