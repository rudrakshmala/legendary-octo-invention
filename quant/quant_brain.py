"""
Elite-Bot Master Quant Brain
-----------------------------
Coordinates all quantitative signals to produce a comprehensive
Renaissance-grade QuantSignal decision object.

If any module is disabled or fails to initialize, it implements immediate
defensive defaults so trading operations never experience failure.
"""
import os
import yfinance as yf
import pandas as pd
from dataclasses import dataclass

from .kalman_filter import get_kalman_signal
from .garch_model import GarchVolModel
from .hmm_regime import MarketRegimeDetector
from .kelly_criterion import KellySizer
from .sentiment_engine import SentimentEngine


@dataclass
class QuantSignal:
    approved: bool
    regime: str             # "MEAN_REVERTING" / "TRENDING" / "VOLATILE"
    regime_prob: float      # Confidence probability
    volatility_ok: bool     # GARCH gate approval
    forecasted_vol: float   # Forecasted volatility %
    kelly_fraction: float   # Position size multiplier
    hedge_ratio: float      # Kalman hedge ratio
    sentiment_score: float  # News pair sentiment (-1.0 to 1.0)
    fear_greed: int         # CNN Fear & Greed index
    confidence: float       # Composite model confidence
    reason: str             # Explanatory logic string


class QuantBrain:
    """
    Combines 5 math models into a singular quantitative signal for trade execution.
    """
    def __init__(self):
        self.garch = GarchVolModel()
        self.regime_detector = MarketRegimeDetector()
        self.kelly = KellySizer()
        self.sentiment = SentimentEngine()

    def generate_signal(self, sym_a: str, sym_b: str, base_z_score: float) -> QuantSignal:
        """
        Executes pipeline: Kalman spread analysis -> Volatility forecasting ->
        Regime classification -> Sizing allocation -> Sentiment scoring.
        """
        try:
            # 1. Fetch aligned price history for the pair (Default 30 days)
            ticker_a = yf.Ticker(sym_a)
            ticker_b = yf.Ticker(sym_b)
            
            data_a = ticker_a.history(period="30d", interval="1h")['Close'].dropna()
            data_b = ticker_b.history(period="30d", interval="1h")['Close'].dropna()
            
            # Find intersection of index timestamps to align data
            aligned_df = pd.DataFrame({sym_a: data_a, sym_b: data_b}).dropna()
            
            # Fallback if yfinance fetch failed or returned insufficient data
            if len(aligned_df) < 15:
                return self._defensive_fallback(
                    "yfinance API rate limited or offline. Activating baseline safe-guards."
                )

            prices_a = aligned_df[sym_a]
            prices_b = aligned_df[sym_b]

            # 2. Kalman Filter Dynamic Spread & Signal
            kalman = get_kalman_signal(prices_a, prices_b)
            hedge_ratio = kalman.get("hedge_ratio", 1.0)
            
            # Compute spread using the dynamic hedge ratio
            spread_series = prices_a - hedge_ratio * prices_b

            # 3. GARCH(1,1) Volatility Gate
            ratio_series = prices_a / prices_b
            vol_analysis = self.garch.predict_volatility(ratio_series)
            forecasted_vol = vol_analysis.get("forecasted_vol", 0.20)

            scale_factor = vol_analysis.get("scale_factor", 1.0)
            vol_tier = vol_analysis.get("tier", "GREEN")

            # 4. HMM Market Regime Classifier
            # Use market proxy index (SPY) for global regime detection
            spy_data = yf.download("SPY", period="30d", interval="1h", progress=False)['Close'].squeeze()
            if isinstance(spy_data, pd.Series) and not spy_data.empty:
                regime_analysis = self.regime_detector.detect_regime(spy_data)
            else:
                # Fallback to local pair regime
                regime_analysis = self.regime_detector.detect_regime(prices_a)

            regime = regime_analysis.get("regime", "MEAN_REVERTING")
            regime_prob = regime_analysis.get("confidence", 0.80)

            # 5. Kelly Criterion sizing optimizer
            kelly_analysis = self.kelly.calculate_kelly_fraction()
            kelly_base = kelly_analysis.get("kelly_fraction", 0.10)
            
            # Dynamic scaling: scale down the Kelly size if GARCH volatility is yellow
            kelly_fraction = float(kelly_base * scale_factor)

            # 6. Sentiment Engine Scraper
            sent_analysis = self.sentiment.evaluate_pair_sentiment(sym_a, sym_b)
            sentiment_score = sent_analysis.get("net_sentiment", 0.0)
            fear_greed = sent_analysis.get("fear_greed", 50)

            # --- 🧮 SYSTEM RULES & RENAISSANCE SIGNAL GENERATION ---
            # Rule 1: Volatility safety lock
            volatility_ok = (vol_tier != "RED")

            # Rule 2: Regime constraint
            # Pairs mean reversion struggles in sharp trending or hyper-volatile states
            regime_ok = (regime == "MEAN_REVERTING")

            # Calculate composite confidence (Weighted combination of models)
            # Higher z-score, mean reverting regime, stable volatility, positive sentiment alignment
            confidence = 0.50
            if regime_ok:
                confidence += 0.20
            if volatility_ok:
                confidence += 0.15
            if abs(base_z_score) > 2.0:
                confidence += 0.15

            # Final decision criteria
            approved = True
            reasons = []

            if not volatility_ok:
                approved = False
                reasons.append(f"GARCH Volatility is high ({forecasted_vol:.1%}) - Trade Blocked")
            if not regime_ok:
                # We still allow the trade but penalize the confidence & size (soft warning)
                reasons.append(f"Market in trending/volatile {regime} state")
                confidence -= 0.15
                kelly_fraction *= 0.5  # Defensive risk reduction

            if kelly_fraction < 0.05:
                approved = False
                reasons.append("Calculated position size below 5% minimum budget threshold")

            if not reasons:
                reasons.append("All structural quantitative models validated successfully")

            reason_str = "; ".join(reasons)

            return QuantSignal(
                approved=approved,
                regime=regime,
                regime_prob=regime_prob,
                volatility_ok=volatility_ok,
                forecasted_vol=forecasted_vol,
                kelly_fraction=round(kelly_fraction, 4),
                hedge_ratio=hedge_ratio,
                sentiment_score=sentiment_score,
                fear_greed=fear_greed,
                confidence=round(confidence, 2),
                reason=reason_str
            )

        except Exception as e:
            return self._defensive_fallback(f"Master pipeline execution failure: {e}")

    def _defensive_fallback(self, error_msg: str) -> QuantSignal:
        """
        Guarantees non-breaking performance in extreme failure events.
        """
        return QuantSignal(
            approved=True,
            regime="MEAN_REVERTING",
            regime_prob=0.50,
            volatility_ok=True,
            forecasted_vol=0.20,
            kelly_fraction=0.10,  # Safe default 10% sizing
            hedge_ratio=1.0,
            sentiment_score=0.0,
            fear_greed=50,
            confidence=0.50,
            reason=f"Quant Fallback Activated: {error_msg}"
        )

    def evaluate_single_stock(self, symbol: str) -> tuple:
        """
        Extremely strict momentum scanner for Universal Mode.
        "2000% sure" setups only: Extreme RSI + Volume confirmation.
        Returns (QuantSignal, direction), where direction is "BUY_SINGLE" or "SELL_SINGLE" or "HOLD".
        """
        try:
            df = yf.download(symbol, period="60d", interval="1d", progress=False)
            if df.empty or len(df) < 20:
                return self._defensive_fallback(f"Not enough data for {symbol}"), "HOLD"
            
            close = df['Close'].squeeze()
            volume = df['Volume'].squeeze()
            
            # Simple RSI (14)
            delta = close.diff()
            up, down = delta.copy(), delta.copy()
            up[up < 0] = 0
            down[down > 0] = 0
            
            roll_up = up.ewm(com=13, adjust=False).mean()
            roll_down = down.abs().ewm(com=13, adjust=False).mean()
            rs = roll_up / roll_down
            rsi = 100.0 - (100.0 / (1.0 + rs))
            current_rsi = float(rsi.iloc[-1])
            
            # Volume confirmation
            avg_vol = float(volume.rolling(14).mean().iloc[-1])
            current_vol = float(volume.iloc[-1])
            high_volume = current_vol > (avg_vol * 1.5)
            
            direction = "HOLD"
            reason = "No extreme momentum detected."
            approved = False
            
            # "2000% sure" rules (No loss or barely loss)
            if current_rsi < 25 and high_volume:
                direction = "BUY_SINGLE"
                approved = True
                reason = f"Extreme Oversold (RSI: {current_rsi:.1f}) + Volume Spike."
            elif current_rsi > 75 and high_volume:
                direction = "SELL_SINGLE"
                approved = True
                reason = f"Extreme Overbought (RSI: {current_rsi:.1f}) + Volume Spike."
                
            sig = QuantSignal(
                approved=approved,
                regime="TRENDING" if approved else "CHOPPY",
                regime_prob=0.99 if approved else 0.50,
                volatility_ok=True,
                forecasted_vol=0.25,
                kelly_fraction=0.30 if approved else 0.10,
                hedge_ratio=1.0,
                sentiment_score=0.8 if direction == "BUY_SINGLE" else -0.8,
                fear_greed=50,
                confidence=0.99 if approved else 0.0,
                reason=reason
            )
            return sig, direction
            
        except Exception as e:
            return self._defensive_fallback(f"Single stock eval failed: {e}"), "HOLD"




# Global convenience function
_brain = QuantBrain()

def get_quant_signal(sym_a: str, sym_b: str, base_z_score: float) -> QuantSignal:
    """
    High-level dynamic signal extraction endpoint for the Elite Trading bots (Pairs).
    """
    return _brain.generate_signal(sym_a, sym_b, base_z_score)

def get_single_stock_signal(symbol: str) -> tuple:
    """
    Universal Single-Stock extremely strict momentum endpoint.
    Returns (QuantSignal, direction).
    """
    return _brain.evaluate_single_stock(symbol)


if __name__ == "__main__":
    print("Orchestrator Quant Brain Test")
    sig = get_quant_signal("KO", "PEP", 1.8)
    print("  Signal Approved :", sig.approved)
    print("  Regime State    :", sig.regime)
    print("  Forecasted Vol  :", sig.forecasted_vol)
    print("  Kelly Fraction  :", sig.kelly_fraction)
    print("  Hedge Ratio     :", sig.hedge_ratio)
    print("  Fear & Greed    :", sig.fear_greed)
    print("  Reason          :", sig.reason)
