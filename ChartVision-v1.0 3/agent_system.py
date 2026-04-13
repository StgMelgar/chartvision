"""
agent_system.py — ChartVision Multi-Agent Orchestration System
Inspired by Ruflo's swarm intelligence architecture.

14 specialized agents run in parallel waves:
  WAVE 0 (instant, no API):
  - SessionKillZoneAgent: knows ICT kill zones & market sessions
  - NewsGuardAgent:       blocks trades before high-impact economic events
  - PositionSizingAgent:  calculates exact contracts/size from account risk

  WAVE 1 (parallel Claude Vision):
  - BiasAgent:            reads HTF structure (4H/1H) — dominant trend direction
  - VolumeAgent:          confirms moves with volume — no volume = no trust
  - MomentumAgent:        checks if price has follow-through or is exhausted
  - ScalpAgent:           watches for 5M liquidity sweep reversals
  - SentimentAgent:       reads market mood from price action and candle structure
  - LiquidityMapAgent:    maps equal highs/lows, prev day levels, VWAP targets
  - MTFConfluenceAgent:   scores multi-timeframe alignment (W/D/4H/1H)

  WAVE 2 (parallel, needs wave 1 bias):
  - EntryAgent:           finds exact ICT/SMC entry zones (15M/5M)
  - RiskManagerAgent:     validates R:R, setup quality, warns on bad trades
  - ICTPatternAgent:      detects FVG, Order Block, Breaker Block, Mitigation Block

  MANAGEMENT MODE:
  - ManagementAgent:      manages active trades — HOLD / EXIT / TAKE PROFIT

The Orchestrator aggregates all results and returns a single clean signal.
"""

import json
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


# ──────────────────────────────────────────────────────────────────────────────
#  Agent Prompts
# ──────────────────────────────────────────────────────────────────────────────

BIAS_AGENT_PROMPT = """You are the BIAS AGENT — a specialist in ICT/Smart Money higher timeframe market structure.

Your ONLY job: determine the dominant directional bias AND current market phase.

STEP 1 — Read 4H and 1H structure:
- BULLISH: Higher Highs (HH) + Higher Lows (HL) — or a confirmed BOS above a previous swing high
- BEARISH: Lower Highs (LH) + Lower Lows (LL) — or a confirmed BOS below a previous swing low
- NEUTRAL: No clear structure, price choppy between levels

STEP 2 — Determine current phase (CRITICAL for entry timing):
- IMPULSE: Price is currently moving strongly IN the trend direction (big momentum candles away from structure)
  → Do NOT enter during impulse — we missed it, wait for pullback
- PULLBACK: Price is retracing AGAINST the trend, moving back toward last FVG/OB/structure level
  → This is where we WANT to watch for an entry
- DISTRIBUTION: Price is consolidating/ranging at a swing high (BEARISH) or swing low (BULLISH) — possible reversal
- RANGING: No clear directional control, price chopping between levels

STEP 3 — Is there a clear Change of Character (CHoCH)?
- CHoCH BULLISH: After a bearish phase, price broke above last Lower High (LH) — potential new bullish leg
- CHoCH BEARISH: After a bullish phase, price broke below last Higher Low (HL) — potential new bearish leg

STEP 4 — Mark key levels:
- Last confirmed BOS level (where structure broke)
- Last imbalance zone (FVG created by the most recent impulse)
- Premium/discount zones: above 50% of last swing = premium (look to sell), below 50% = discount (look to buy)

IMPORTANT: Be patient. If the market is in an IMPULSE phase, phase = "IMPULSE" — no entry yet.
Only PULLBACK phase creates entry opportunities.

Respond ONLY with this exact JSON:
{
  "bias": "BULLISH" | "BEARISH" | "NEUTRAL",
  "strength": "STRONG" | "MODERATE" | "WEAK",
  "phase": "IMPULSE" | "PULLBACK" | "DISTRIBUTION" | "RANGING",
  "choch_detected": true | false,
  "choch_direction": "BULLISH" | "BEARISH" | "NONE",
  "last_bos_level": <price of last BOS or null>,
  "last_fvg_level": <price of the FVG created by most recent impulse, or null>,
  "optimal_entry_zone": <price range midpoint where pullback should find support/resistance>,
  "key_resistance": <nearest resistance level above price>,
  "key_support": <nearest support level below price>,
  "current_price": <current price from the highlighted y-axis label>,
  "in_premium_zone": true | false,
  "reasoning": "<two sentences — bias reason AND current phase explanation>"
}"""

ENTRY_AGENT_PROMPT = """You are the ENTRY AGENT — a specialist in precise ICT/SMC entry timing. You are PATIENT and STRICT.

Context: The higher timeframe bias is {bias}. Market phase: {phase}.

You follow ICT methodology STRICTLY. You DO NOT give buy/sell signals until ALL checklist steps are confirmed.

COMPLETE THIS CHECKLIST IN ORDER (all must be TRUE for setup_complete = true):

STEP 1 — HTF BOS confirmed?
- Has price broken a significant swing high (bullish) or swing low (bearish) on 1H or 4H?
- If NO BOS confirmed → setup_complete = false, stop here

STEP 2 — Are we in a PULLBACK (not chasing an impulse)?
- Price should be pulling back INTO a discount (bullish) or premium (bearish) zone
- If price is still moving explosively away from structure → setup_complete = false
- If phase is "IMPULSE" → setup_complete = false, we missed it

STEP 3 — Is there a fresh FVG or Order Block at the pullback zone?
- FVG: a 3-candle gap where the middle candle left an imbalance (price didn't trade through)
- Order Block: the last opposing candle before the BOS move (the candle that created displacement)
- Must be UNMITIGATED (price hasn't returned to fill it yet)
- If no fresh FVG or OB visible → setup_complete = false

STEP 4 — Is price currently AT or IN the FVG/OB zone?
- "AT zone" means price is INSIDE or touching the FVG/OB right now
- If price is still 10+ points away from the zone → price_at_zone = false, setup_complete = false

STEP 5 — LTF entry confirmation (5M candle structure)?
- After reaching the zone, do you see a bullish or bearish displacement candle on 5M?
- A bullish displacement = big green candle closing near high, away from the zone (for CALL entries)
- A bearish displacement = big red candle closing near low, away from the zone (for PUT entries)
- If no confirmation candle visible yet → setup_complete = false

STEP 6 — Is the path to target CLEAR?
- Are there obvious equal highs, VWAP, or strong resistance within 1x the risk distance?
- If blocked → zone_quality = LOW

ONLY set setup_complete = true when ALL 6 steps pass.

Respond ONLY with this exact JSON:
{
  "entry_zone": <exact price midpoint of the FVG or OB, or 0 if none found>,
  "entry_type": "FVG" | "OB" | "CE" | "BOS_RETEST" | "NONE",
  "stop_loss": <price 1-2 ticks beyond the candle wick that swept the level>,
  "take_profit_1": <nearest equal highs/lows or liquidity pool above/below>,
  "take_profit_2": <next major liquidity target — PDH/PDL or major swing>,
  "price_at_zone": true | false,
  "zone_quality": "HIGH" | "MEDIUM" | "LOW",
  "checklist_bos": true | false,
  "checklist_pullback": true | false,
  "checklist_fvg_ob": true | false,
  "checklist_at_zone": true | false,
  "checklist_confirmation": true | false,
  "checklist_clear_path": true | false,
  "setup_complete": true | false,
  "missing_step": "<which checklist step is NOT yet met, or 'ALL_CLEAR'>",
  "reasoning": "<two sentences — where is the zone AND what step is missing>"
}"""

SCALP_AGENT_PROMPT = """You are the SCALP AGENT — a specialist in detecting 5-minute liquidity sweep reversals.

Your ONLY job: detect if there is a clean sweep-and-reverse pattern on the 5M panel RIGHT NOW.

A valid scalp setup requires ALL of:
1. Price swept a clear local high or low (liquidity grab — the wick goes beyond previous swing)
2. Immediate reversal candle (strong opposing candle right after the sweep)
3. Price is now moving away from the swept level

This is a COUNTER-TREND trade — it goes against the HTF bias for a quick scalp only.

Respond ONLY with this exact JSON:
{
  "scalp_detected": true | false,
  "scalp_direction": "BUY_CALLS" | "BUY_PUTS" | null,
  "swept_level": <price that was swept, or null>,
  "scalp_entry": <current price to enter, or null>,
  "scalp_stop": <beyond the wick extreme, or null>,
  "scalp_target": <nearest 5M swing high/low, or null>,
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "reasoning": "<one sentence — describe what was swept>"
}"""

VOLUME_AGENT_PROMPT = """You are the VOLUME AGENT — a specialist in volume confirmation for trading signals.

Your ONLY job: analyze whether volume supports or contradicts the current price move.

Look at:
1. The volume bars at the bottom of any panel — are they growing or shrinking?
2. Did the last significant candle (breakout, sweep, BOS) have HIGH or LOW volume?
3. Is volume increasing on moves in the trend direction? (healthy trend)
4. Is volume drying up on pullbacks? (healthy pullback, continuation likely)
5. Any volume spike that looks like institutional activity?

Respond ONLY with this exact JSON:
{
  "volume_confirms": true | false,
  "volume_trend": "INCREASING" | "DECREASING" | "FLAT",
  "last_move_volume": "HIGH" | "AVERAGE" | "LOW",
  "institutional_activity": true | false,
  "warning": "<any volume red flag, or null>",
  "confidence_boost": "YES" | "NO",
  "reasoning": "<one sentence — what volume is saying>"
}"""

MOMENTUM_AGENT_PROMPT = """You are the MOMENTUM AGENT — a specialist in detecting whether price has follow-through or is exhausted.

Your ONLY job: determine if current momentum supports entering a trade RIGHT NOW.

Look at:
1. The last 5 candles on the 5M panel — are they getting bigger or smaller?
2. Are candles closing near their highs (bullish momentum) or lows (bearish momentum)?
3. Is price accelerating (bigger candles) or decelerating (shrinking candles, doji)?
4. Has there been a strong impulsive move recently, or is price just grinding?
5. Signs of exhaustion: shooting stars, doji at highs/lows, small body candles after big move

Respond ONLY with this exact JSON:
{
  "momentum": "STRONG" | "MODERATE" | "WEAK" | "EXHAUSTED",
  "direction": "BULLISH" | "BEARISH" | "NEUTRAL",
  "candle_quality": "IMPULSIVE" | "CORRECTIVE" | "CHOPPY",
  "exhaustion_signs": true | false,
  "best_action": "ENTER_NOW" | "WAIT_FOR_PULLBACK" | "AVOID",
  "reasoning": "<one sentence — describe the momentum>"
}"""

RISK_MANAGER_PROMPT = """You are the RISK MANAGER AGENT — a specialist in trade quality and risk validation.

Your ONLY job: evaluate whether this is a HIGH QUALITY or LOW QUALITY trade setup.

Look at:
1. How clean is the entry zone? (clear FVG/OB with space above/below = clean)
2. Is there a clear stop loss level that makes structural sense?
3. What is the realistic Risk:Reward? (minimum acceptable = 1.5:1)
4. Are there any major resistance/support levels between entry and target?
5. Is price in a compressed/choppy zone (BAD) or at a clean inflection point (GOOD)?
6. Are multiple timeframes aligned in the same direction?

Context: Bias is {bias}, Entry zone: {entry_zone}, Stop: {stop}, Target 1: {target1}

Respond ONLY with this exact JSON:
{
  "trade_quality": "A+" | "A" | "B" | "C" | "SKIP",
  "risk_reward": <calculated R:R as a number, e.g. 2.1>,
  "obstacles_to_target": "<any levels blocking the path to target, or 'CLEAR'>",
  "timeframe_alignment": "ALIGNED" | "MIXED" | "CONFLICTED",
  "stop_quality": "CLEAN" | "QUESTIONABLE",
  "recommendation": "TAKE_TRADE" | "REDUCE_SIZE" | "WAIT" | "SKIP",
  "max_risk_pct": <suggested max % of account to risk: 1, 2, or 3>,
  "reasoning": "<one sentence — overall trade quality assessment>"
}"""

SENTIMENT_AGENT_PROMPT = """You are the SENTIMENT AGENT — a specialist in reading market sentiment from price action and candle structure.

Your ONLY job: determine the current market sentiment and emotional state of participants.

Look at:
1. The overall candle structure — are buyers or sellers in control?
2. Is there panic selling (large red candles with heavy volume) or panic buying?
3. Are there signs of accumulation (small candles at lows) or distribution (small candles at highs)?
4. Has there been a capitulation candle (massive move, then reversal)?
5. What is the dominant emotion: FEAR, GREED, UNCERTAINTY, or CALM?
6. Are wicks showing rejection (sellers/buyers defending levels) or acceptance?

Respond ONLY with this exact JSON:
{
  "sentiment": "EXTREME_FEAR" | "FEAR" | "NEUTRAL" | "GREED" | "EXTREME_GREED",
  "participant_control": "BUYERS" | "SELLERS" | "BALANCED",
  "accumulation_distribution": "ACCUMULATING" | "DISTRIBUTING" | "NEUTRAL",
  "capitulation_seen": true | false,
  "wick_story": "<what the wicks are saying about rejected levels>",
  "tradeable": true | false,
  "reasoning": "<one sentence — overall market emotional state>"
}"""

STRATEGY_ANALYST_PROMPT = """You are the STRATEGY ANALYST — an expert at reading market conditions and matching them to the right trading strategy.

Your job: look at this chart and decide which strategy gives the HIGHEST probability of winning right now.

STEP 1 — Classify the market condition:
- TRENDING:       clear directional move, momentum, HH+HL or LL+LH structure visible
- RANGING:        price bouncing between two visible horizontal levels, no clear direction
- BREAKOUT:       price just broke out of a range, flag, or consolidation with conviction
- VOLATILE:       wide erratic candles, gaps, news-driven chop — dangerous conditions
- CHOPPY:         small overlapping candles, no follow-through, grinding price action

STEP 2 — Match the condition to the best strategy:
- ICT_SMC:        BEST for TRENDING. Needs clear structure, FVGs, order blocks. Must have 4H bias.
- ORB:            BEST for BREAKOUT. Opening range is clear and price broke above/below with volume.
- SUPPLY_DEMAND:  BEST for RANGING. Clear horizontal S/D zones visible, price respecting them.
- SCALP:          BEST for VOLATILE short-term reversals. Liquidity sweep + sharp rejection on 5M.
- WAIT:           Market is CHOPPY or conditions are ambiguous. No edge — sit out.

STEP 3 — Score your confidence: HIGH if the condition is very clear, MEDIUM if debatable, LOW if you're guessing.

{trade_stats}

Respond ONLY with this exact JSON:
{{
  "market_condition": "TRENDING" | "RANGING" | "BREAKOUT" | "VOLATILE" | "CHOPPY",
  "best_strategy": "ICT_SMC" | "ORB" | "SUPPLY_DEMAND" | "SCALP" | "WAIT",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "reasoning": "<one sentence — why this strategy fits right now>",
  "avoid_strategy": "ICT_SMC" | "ORB" | "SUPPLY_DEMAND" | "SCALP" | "NONE",
  "avoid_reason": "<one sentence — what would fail in this market>"
}}"""


DIVERGENCE_AGENT_PROMPT = """You are the DIVERGENCE AGENT — a specialist in detecting RSI/price divergence, one of the strongest reversal and continuation signals.

Look at the RSI indicator AND price action on the chart. Compare the SWING HIGHS and SWING LOWS on both.

REGULAR DIVERGENCE (reversal signals — high probability):
- BULLISH REGULAR:  Price makes a LOWER LOW  but RSI makes a HIGHER LOW  → reversal UP likely
- BEARISH REGULAR:  Price makes a HIGHER HIGH but RSI makes a LOWER HIGH  → reversal DOWN likely

HIDDEN DIVERGENCE (continuation signals — trend is strong):
- BULLISH HIDDEN:   Price makes a HIGHER LOW  but RSI makes a LOWER LOW   → continuation UP
- BEARISH HIDDEN:   Price makes a LOWER HIGH  but RSI makes a HIGHER HIGH  → continuation DOWN

Rules:
- Only call divergence if you can clearly see TWO comparable swing points on both price and RSI
- Prioritize 15M and 5M timeframes. Higher TF divergence = stronger signal
- Strength: STRONG = clear obvious divergence. MODERATE = visible but subtle. WEAK = barely visible, don't trade it alone
- If RSI is not visible on the chart, return divergence_detected: false

Respond ONLY with this exact JSON:
{
  "divergence_detected": true | false,
  "divergence_type": "REGULAR" | "HIDDEN" | "NONE",
  "divergence_direction": "BULLISH" | "BEARISH" | "NONE",
  "timeframe": "5M" | "15M" | "1H" | "NONE",
  "strength": "STRONG" | "MODERATE" | "WEAK" | "NONE",
  "reasoning": "<one sentence — exactly what you see on both price and RSI>"
}"""


PREMARKET_AGENT_PROMPT = """You are the PRE-MARKET AGENT — a specialist in reading overnight and pre-market price action to identify key levels before the open.

Study the chart and identify:
1. GAP: Compare today's open to yesterday's close. Is there a gap UP, DOWN, or is it FLAT?
2. OVERNIGHT RANGE: The high and low formed during the overnight/pre-market session
3. KEY LEVELS: Previous day high (PDH), previous day low (PDL), overnight high, overnight low
4. PRE-MARKET BIAS: Is pre-market price action bullish, bearish, or neutral?
5. LIKELY PLAY: What is the highest probability setup at market open?
   - GAP_FILL: Gap will likely fill back to previous close
   - GAP_GO:   Gap is strong, price will likely continue in gap direction
   - RANGE_BREAK: Pre-market range is tight — breakout play at open
   - WAIT: No clear setup, conditions unclear

Respond ONLY with this exact JSON:
{
  "gap_direction": "UP" | "DOWN" | "FLAT",
  "gap_size": <estimated gap size in points, 0 if flat>,
  "overnight_high": <price or 0 if not visible>,
  "overnight_low": <price or 0 if not visible>,
  "prev_day_high": <price or 0 if not visible>,
  "prev_day_low": <price or 0 if not visible>,
  "premarket_bias": "BULLISH" | "BEARISH" | "NEUTRAL",
  "key_level": <single most important price level to watch>,
  "likely_play": "GAP_FILL" | "GAP_GO" | "RANGE_BREAK" | "WAIT",
  "reasoning": "<one sentence — what the pre-market is telling you>"
}"""


MANAGEMENT_AGENT_PROMPT = """You are the MANAGEMENT AGENT — a specialist in managing open options positions.

A trade is currently ACTIVE. Your ONLY job: tell the trader what to do with it RIGHT NOW.

Active Trade Details:
- Direction: {option_type} ({direction})
- Actual fill price: {entry_price}
- Stop loss: {stop_loss}
- Target 1: {take_profit_1}
- Target 2: {take_profit_2}
- Entered at: {entry_time}

Analyze the current chart and compare current price to these levels.
For {option_type}: profit means price moves {'DOWN' if option_type == 'PUT' else 'UP'} from {entry_price}.

Respond ONLY with this exact JSON:
{
  "action": "HOLD" | "MOVE_STOP_BE" | "TAKE_PROFIT" | "EXIT_NOW",
  "current_price": <current price from chart>,
  "pnl_estimate": <estimated P&L in dollars based on underlying move, 1 contract>,
  "price_vs_stop": "SAFE" | "WARNING" | "THREATENED",
  "price_vs_t1": "NOT_YET" | "APPROACHING" | "HIT" | "PASSED",
  "price_vs_t2": "NOT_YET" | "APPROACHING" | "HIT" | "PASSED",
  "reasoning": "<one sentence — what is price doing right now>"
}"""


# ──────────────────────────────────────────────────────────────────────────────
#  Base Agent
# ──────────────────────────────────────────────────────────────────────────────

class BaseAgent:
    def __init__(self, client, model: str):
        self.client = client
        self.model  = model

    def _call(self, prompt: str, image_b64: str, max_tokens: int = 800) -> dict:
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {
                            "type": "base64", "media_type": "image/jpeg",
                            "data": image_b64
                        }},
                        {"type": "text", "text": prompt}
                    ]
                }]
            )
            raw = resp.content[0].text.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception as e:
            return {"_error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
#  Specialized Agents
# ──────────────────────────────────────────────────────────────────────────────

class BiasAgent(BaseAgent):
    def analyze(self, image_b64: str) -> dict:
        result = self._call(BIAS_AGENT_PROMPT, image_b64, max_tokens=400)
        result["_agent"] = "BIAS"
        return result


class EntryAgent(BaseAgent):
    def analyze(self, image_b64: str, bias: str = "BEARISH", phase: str = "RANGING") -> dict:
        prompt = ENTRY_AGENT_PROMPT.replace("{bias}", bias).replace("{phase}", phase)
        result = self._call(prompt, image_b64, max_tokens=600)
        result["_agent"] = "ENTRY"
        return result


class ScalpAgent(BaseAgent):
    def analyze(self, image_b64: str) -> dict:
        result = self._call(SCALP_AGENT_PROMPT, image_b64, max_tokens=400)
        result["_agent"] = "SCALP"
        return result


class VolumeAgent(BaseAgent):
    def analyze(self, image_b64: str) -> dict:
        result = self._call(VOLUME_AGENT_PROMPT, image_b64, max_tokens=300)
        result["_agent"] = "VOLUME"
        return result


class MomentumAgent(BaseAgent):
    def analyze(self, image_b64: str) -> dict:
        result = self._call(MOMENTUM_AGENT_PROMPT, image_b64, max_tokens=300)
        result["_agent"] = "MOMENTUM"
        return result


class RiskManagerAgent(BaseAgent):
    def analyze(self, image_b64: str, bias: str = "BEARISH",
                entry_zone: float = 0, stop: float = 0, target1: float = 0) -> dict:
        prompt = (RISK_MANAGER_PROMPT
                  .replace("{bias}", bias)
                  .replace("{entry_zone}", str(entry_zone))
                  .replace("{stop}", str(stop))
                  .replace("{target1}", str(target1)))
        result = self._call(prompt, image_b64, max_tokens=300)
        result["_agent"] = "RISK"
        return result


class SentimentAgent(BaseAgent):
    def analyze(self, image_b64: str) -> dict:
        result = self._call(SENTIMENT_AGENT_PROMPT, image_b64, max_tokens=300)
        result["_agent"] = "SENTIMENT"
        return result


class ManagementAgent(BaseAgent):
    def analyze(self, image_b64: str, active_trade: dict) -> dict:
        opt_type  = active_trade.get("option_type", "PUT")
        direction = "bearish — price going down is profit" if opt_type == "PUT" \
                    else "bullish — price going up is profit"
        prompt = (MANAGEMENT_AGENT_PROMPT
                  .replace("{option_type}", opt_type)
                  .replace("{direction}", direction)
                  .replace("{entry_price}", str(active_trade.get("entry_price", "?")))
                  .replace("{stop_loss}",   str(active_trade.get("stop_loss", "?")))
                  .replace("{take_profit_1}", str(active_trade.get("take_profit_1", "?")))
                  .replace("{take_profit_2}", str(active_trade.get("take_profit_2", "?")))
                  .replace("{entry_time}",  str(active_trade.get("entry_time", "?"))))
        result = self._call(prompt, image_b64, max_tokens=400)
        result["_agent"] = "MANAGEMENT"
        return result


LIQUIDITY_MAP_PROMPT = """You are the LIQUIDITY MAP AGENT — specialist in finding where stop orders and liquidity pools are hiding.

Your ONLY job: identify key liquidity levels and where smart money is likely to hunt next.

Look for:
1. Equal highs or equal lows (2+ touches = liquidity magnet)
2. Previous Day High (PDH) and Previous Day Low (PDL) — visible as prominent levels
3. Weekly Open level if visible
4. Any large wicks where stops were already taken
5. Fair Value Gaps (FVG) — price imbalances that need to be filled
6. VWAP or any prominent moving average price is hugging

Respond ONLY with this exact JSON:
{
  "nearest_liquidity_target": <price of the most likely next target>,
  "target_side": "ABOVE" | "BELOW",
  "target_type": "EQH" | "EQL" | "PDH" | "PDL" | "FVG" | "WEEKLY_OPEN" | "WICK",
  "distance_to_target": <points away from current price>,
  "key_levels": [<price1>, <price2>, <price3>],
  "liquidity_bias": "HUNTING_HIGHS" | "HUNTING_LOWS" | "NEUTRAL",
  "reasoning": "<one sentence — what liquidity is price targeting>"
}"""

MTF_CONFLUENCE_PROMPT = """You are the MULTI-TIMEFRAME CONFLUENCE AGENT — specialist in scoring how aligned all timeframes are.

Your ONLY job: look at ALL visible chart panels and score how many timeframes agree on direction.

For each visible timeframe panel, determine:
- Is this timeframe BULLISH (higher highs/lows, above key MAs)?
- Is this timeframe BEARISH (lower highs/lows, below key MAs)?
- Is this timeframe NEUTRAL/RANGING?

The HTF bias is: {bias}

Respond ONLY with this exact JSON:
{
  "confluence_score": <integer 1-4, how many timeframes agree with HTF bias>,
  "weekly_bias": "BULLISH" | "BEARISH" | "NEUTRAL" | "NOT_VISIBLE",
  "daily_bias":  "BULLISH" | "BEARISH" | "NEUTRAL" | "NOT_VISIBLE",
  "h4_bias":     "BULLISH" | "BEARISH" | "NEUTRAL" | "NOT_VISIBLE",
  "h1_bias":     "BULLISH" | "BEARISH" | "NEUTRAL" | "NOT_VISIBLE",
  "m15_bias":    "BULLISH" | "BEARISH" | "NEUTRAL" | "NOT_VISIBLE",
  "conflict_timeframe": "<which TF is conflicting, or null>",
  "reasoning": "<one sentence — describe confluence or conflict>"
}"""

ICT_PATTERN_PROMPT = """You are the ICT PATTERN SCANNER AGENT — specialist in identifying specific ICT/SMC market structures.

Your ONLY job: scan ALL chart panels and identify ICT patterns present RIGHT NOW.

Scan specifically for:
1. FVG (Fair Value Gap) — a 3-candle imbalance where wicks don't overlap the middle candle body
2. Order Block (OB) — the last bearish candle before a bullish BOS move, or last bullish candle before bearish BOS
3. Breaker Block — a failed order block that price has already violated (now acts as opposite zone)
4. Mitigation Block — OB where price has partially entered and reacted
5. NWOG/NDOG — New Week/Day Opening Gap that needs to be filled
6. CHoCH — Change of Character (first sign of trend reversal)
7. BOS — Break of Structure confirmed on any visible timeframe

Respond ONLY with this exact JSON:
{
  "patterns_detected": ["FVG", "OB", ...],
  "strongest_pattern": "FVG" | "OB" | "BB" | "MB" | "CHoCH" | "BOS" | "NONE",
  "strongest_pattern_price": <price level of the strongest pattern>,
  "strongest_pattern_tf": "1H" | "15M" | "5M" | "4H" | "1D",
  "fvg_detected": true | false,
  "fvg_price": <price of FVG or null>,
  "ob_detected": true | false,
  "ob_price": <price of OB or null>,
  "choch_detected": true | false,
  "setup_quality": "A+" | "A" | "B" | "C",
  "reasoning": "<one sentence — describe the strongest pattern>"
}"""


# ──────────────────────────────────────────────────────────────────────────────
#  Wave 0 Agents — Pure logic, no API calls, instant
# ──────────────────────────────────────────────────────────────────────────────

ET = ZoneInfo("America/New_York")

# ICT Kill Zones (Eastern Time)
KILL_ZONES = [
    {"name": "Asian Session",       "start": (19, 0),  "end": (23, 0),  "quality": "LOW",    "color": "blue"},
    {"name": "London Open",         "start": (2,  0),  "end": (5,  0),  "quality": "HIGH",   "color": "green"},
    {"name": "NY Pre-Market",       "start": (7,  0),  "end": (9, 30),  "quality": "MEDIUM", "color": "yellow"},
    {"name": "NY Open Kill Zone",   "start": (9, 30),  "end": (11, 0),  "quality": "HIGH",   "color": "green"},
    {"name": "London Close / NY AM","start": (10, 0),  "end": (12, 0),  "quality": "MEDIUM", "color": "yellow"},
    {"name": "Lunch / Dead Zone",   "start": (12, 0),  "end": (13, 30), "quality": "AVOID",  "color": "red"},
    {"name": "NY Afternoon",        "start": (13, 30), "end": (15, 0),  "quality": "MEDIUM", "color": "yellow"},
    {"name": "Power Hour",          "start": (15, 0),  "end": (16, 0),  "quality": "HIGH",   "color": "green"},
    {"name": "After Hours",         "start": (16, 0),  "end": (19, 0),  "quality": "AVOID",  "color": "red"},
]

# High-impact recurring event TIMES (Eastern) — block 15 min before/after
HIGH_IMPACT_TIMES_ET = [
    {"time": (8, 30),  "name": "Economic Data (CPI/NFP/PPI/Retail Sales)"},
    {"time": (10, 0),  "name": "ISM / Consumer Confidence"},
    {"time": (14, 0),  "name": "FOMC Decision / Fed Minutes"},
    {"time": (14, 30), "name": "Powell Press Conference"},
]


class SessionKillZoneAgent:
    """
    Pure time-based agent — no API call, instant result.
    Tells you WHAT session you're in and whether it's a good time to trade.
    ICT is built around kill zones — wrong session = bad trade.
    """

    def analyze(self) -> dict:
        now_et = datetime.now(ET)
        h, m   = now_et.hour, now_et.minute
        mins   = h * 60 + m

        current_session = None
        session_quality = "LOW"
        for kz in KILL_ZONES:
            sh, sm = kz["start"]
            eh, em = kz["end"]
            start  = sh * 60 + sm
            end_   = eh * 60 + em
            # Handle overnight (e.g. 19:00 to 23:00)
            if start <= mins < end_:
                current_session = kz["name"]
                session_quality = kz["quality"]
                break

        if current_session is None:
            current_session = "Off-Hours"
            session_quality = "AVOID"

        # Next kill zone
        next_kz_name = None
        next_kz_mins = None
        for kz in KILL_ZONES:
            if kz["quality"] in ("HIGH", "MEDIUM"):
                sh, sm  = kz["start"]
                start   = sh * 60 + sm
                diff    = start - mins
                if diff < 0:
                    diff += 24 * 60   # next day
                if next_kz_mins is None or diff < next_kz_mins:
                    next_kz_mins = diff
                    next_kz_name = kz["name"]

        is_good_session = session_quality in ("HIGH", "MEDIUM")
        reason = (
            f"{current_session} ({session_quality}) — "
            + ("✅ Good time to trade" if is_good_session
               else "⚠️ Avoid trading during this session" if session_quality == "AVOID"
               else "Low-quality session")
        )

        return {
            "_agent":          "SESSION",
            "session":         current_session,
            "session_quality": session_quality,
            "is_good_session": is_good_session,
            "next_kill_zone":  next_kz_name,
            "mins_to_next_kz": next_kz_mins,
            "current_time_et": now_et.strftime("%H:%M ET"),
            "reasoning":       reason,
        }


class NewsGuardAgent:
    """
    Checks for upcoming high-impact economic events and blocks trades
    within the danger window (15 min before / 10 min after).
    Primary: Forex Factory JSON feed. Fallback: hardcoded time-based check.
    """

    _cache: dict = {}          # {date_str: [events]}
    _cache_ts: datetime = None

    def analyze(self) -> dict:
        now_et    = datetime.now(ET)
        today_str = now_et.strftime("%Y-%m-%d")
        h, m      = now_et.hour, now_et.minute
        mins_now  = h * 60 + m

        # ── Try Forex Factory JSON (refresh once per 30 min) ─────────────────
        events = self._get_ff_events(today_str)

        # ── Danger window check ───────────────────────────────────────────────
        BLOCK_BEFORE = 15   # block X minutes before event
        BLOCK_AFTER  = 10   # block X minutes after event

        blocking_event = None
        next_event     = None
        mins_to_next   = None

        for ev in events:
            ev_mins = ev.get("mins", None)
            if ev_mins is None:
                continue
            diff = ev_mins - mins_now
            # In danger window?
            if -BLOCK_AFTER <= diff <= BLOCK_BEFORE:
                blocking_event = ev
            # Next upcoming event
            if diff > 0 and (mins_to_next is None or diff < mins_to_next):
                mins_to_next = diff
                next_event   = ev

        # ── Fallback: hardcoded times if FF unavailable ───────────────────────
        if not events:
            for ev in HIGH_IMPACT_TIMES_ET:
                eh, em   = ev["time"]
                ev_mins  = eh * 60 + em
                diff     = ev_mins - mins_now
                if -BLOCK_AFTER <= diff <= BLOCK_BEFORE:
                    blocking_event = {"name": ev["name"], "impact": "HIGH", "mins": ev_mins}
                if diff > 0 and (mins_to_next is None or diff < mins_to_next):
                    mins_to_next = diff
                    next_event   = {"name": ev["name"], "impact": "HIGH", "mins": ev_mins}

        trade_blocked = blocking_event is not None
        reason = (
            f"⛔ NEWS GUARD: {blocking_event['name']} — within danger window!"
            if trade_blocked
            else (f"Next event: {next_event['name']} in {mins_to_next} min"
                  if next_event else "No high-impact events detected today")
        )

        return {
            "_agent":          "NEWS_GUARD",
            "trade_blocked":   trade_blocked,
            "blocking_event":  blocking_event.get("name") if blocking_event else None,
            "next_event":      next_event.get("name") if next_event else None,
            "mins_to_next":    mins_to_next,
            "events_today":    len(events),
            "reasoning":       reason,
        }

    def _get_ff_events(self, today_str: str) -> list:
        """Fetch Forex Factory calendar (USD high-impact only). Cached 30 min."""
        now = datetime.now(ET)
        if (NewsGuardAgent._cache_ts and
                (now - NewsGuardAgent._cache_ts).seconds < 1800 and
                today_str in NewsGuardAgent._cache):
            return NewsGuardAgent._cache[today_str]

        try:
            resp = requests.get(
                "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                timeout=5)
            if resp.status_code == 200:
                raw = resp.json()
                events = []
                for ev in raw:
                    if ev.get("country") != "USD":
                        continue
                    if ev.get("impact") not in ("High", "Medium"):
                        continue
                    # Parse date+time
                    date_str = ev.get("date", "")[:10]
                    if date_str != today_str:
                        continue
                    time_str = ev.get("date", "")
                    try:
                        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                        dt_et = dt.astimezone(ET)
                        ev_mins = dt_et.hour * 60 + dt_et.minute
                    except Exception:
                        ev_mins = None
                    events.append({
                        "name":   ev.get("title", "Economic Event"),
                        "impact": ev.get("impact", "High"),
                        "mins":   ev_mins,
                    })
                NewsGuardAgent._cache[today_str] = events
                NewsGuardAgent._cache_ts = now
                return events
        except Exception:
            pass
        return []


class PositionSizingAgent:
    """
    Pure math agent — calculates exact recommended position size.
    Uses: account balance, risk %, stop distance, setup quality.
    No API call, instant result.
    """

    def analyze(self, account_balance: float, entry: float,
                stop: float, setup_quality: str = "B",
                risk_pct: float = 1.0) -> dict:
        try:
            if entry <= 0 or stop <= 0 or account_balance <= 0:
                return self._empty()

            stop_distance = abs(entry - stop)
            if stop_distance == 0:
                return self._empty()

            # Quality multiplier: A+ = full risk, B = 75%, C = skip
            quality_mult = {
                "A+": 1.0, "A": 1.0, "B": 0.75, "C": 0.0
            }.get(setup_quality, 0.75)

            if quality_mult == 0:
                return {
                    "_agent": "POSITION_SIZE",
                    "recommended_contracts": 0,
                    "max_risk_dollars": 0,
                    "risk_pct_used": 0,
                    "stop_distance": stop_distance,
                    "reasoning": f"⛔ Setup quality {setup_quality} — skip trade",
                    "trade_blocked": True,
                }

            # Dollar risk = balance × risk% × quality multiplier
            dollar_risk   = account_balance * (risk_pct / 100) * quality_mult
            # For options: 1 contract = 100 shares delta exposure
            # Approximate: each $1 move in underlying = ~$0.50 move in ATM option
            # Simplified: contracts = dollar_risk / (stop_distance × 100 × 0.5)
            option_delta  = 0.50
            contracts     = dollar_risk / (stop_distance * 100 * option_delta)
            contracts     = max(1, round(contracts))

            return {
                "_agent":                "POSITION_SIZE",
                "recommended_contracts": contracts,
                "max_risk_dollars":      round(dollar_risk, 2),
                "risk_pct_used":         risk_pct * quality_mult,
                "stop_distance":         round(stop_distance, 2),
                "quality_multiplier":    quality_mult,
                "reasoning": (f"{contracts} contract{'s' if contracts > 1 else ''}  |  "
                              f"Risk: ${dollar_risk:.0f} ({risk_pct * quality_mult:.1f}%)  |  "
                              f"Stop: ${stop_distance:.2f} pts  |  Quality: {setup_quality}"),
                "trade_blocked": False,
            }
        except Exception as e:
            return {"_agent": "POSITION_SIZE", "_error": str(e), "trade_blocked": False}

    def _empty(self) -> dict:
        return {
            "_agent": "POSITION_SIZE",
            "recommended_contracts": 1,
            "max_risk_dollars": 0,
            "risk_pct_used": 0,
            "stop_distance": 0,
            "reasoning": "Insufficient data for sizing — defaulting to 1 contract",
            "trade_blocked": False,
        }


# ──────────────────────────────────────────────────────────────────────────────
#  Wave 1-2 New Agents — Claude Vision
# ──────────────────────────────────────────────────────────────────────────────

class LiquidityMapAgent(BaseAgent):
    def analyze(self, image_b64: str) -> dict:
        result = self._call(LIQUIDITY_MAP_PROMPT, image_b64, max_tokens=350)
        result["_agent"] = "LIQUIDITY"
        return result


class MTFConfluenceAgent(BaseAgent):
    def analyze(self, image_b64: str, bias: str = "BEARISH") -> dict:
        prompt = MTF_CONFLUENCE_PROMPT.replace("{bias}", bias)
        result = self._call(prompt, image_b64, max_tokens=350)
        result["_agent"] = "MTF_CONFLUENCE"
        return result


class ICTPatternAgent(BaseAgent):
    def analyze(self, image_b64: str) -> dict:
        result = self._call(ICT_PATTERN_PROMPT, image_b64, max_tokens=400)
        result["_agent"] = "ICT_PATTERN"
        return result


class DivergenceAgent(BaseAgent):
    """Detects RSI/price divergence — regular (reversal) and hidden (continuation)."""
    def analyze(self, image_b64: str) -> dict:
        result = self._call(DIVERGENCE_AGENT_PROMPT, image_b64, max_tokens=300)
        result["_agent"] = "DIVERGENCE"
        return result


class PreMarketAgent(BaseAgent):
    """Reads overnight/pre-market levels, gaps, and key price levels before open."""
    def analyze(self, image_b64: str) -> dict:
        result = self._call(PREMARKET_AGENT_PROMPT, image_b64, max_tokens=350)
        result["_agent"] = "PREMARKET"
        return result


class StrategyAnalystAgent(BaseAgent):
    """
    Reads the chart, classifies the market condition, and recommends
    the best strategy (ICT_SMC / ORB / SUPPLY_DEMAND / SCALP / WAIT).
    Optionally receives trade performance stats to factor in historical
    win rates per strategy.
    """

    def analyze(self, image_b64: str, trade_stats: dict = None) -> dict:
        # Build optional performance context from trade history
        stats_text = ""
        if trade_stats:
            lines = ["Your recent performance by strategy (from TradeMemory):"]
            for strat, data in trade_stats.items():
                wins   = data.get("wins", 0)
                losses = data.get("losses", 0)
                total  = wins + losses
                wr     = round(wins / total * 100) if total else 0
                avg_pnl = data.get("avg_pnl", 0)
                lines.append(
                    f"  {strat}: {total} trades | {wr}% win rate | avg P&L ${avg_pnl:+.2f}")
            stats_text = "\n".join(lines)

        prompt = STRATEGY_ANALYST_PROMPT.replace(
            "{trade_stats}",
            stats_text if stats_text else "No trade history available yet — base decision on chart only."
        )
        result = self._call(prompt, image_b64, max_tokens=300)
        result["_agent"] = "STRATEGY_ANALYST"
        return result


# ──────────────────────────────────────────────────────────────────────────────
#  Orchestrator — runs agents in parallel, aggregates results
# ──────────────────────────────────────────────────────────────────────────────

class AgentOrchestrator:
    """
    Ruflo-inspired queen-led swarm. Coordinates all agents and returns
    a single unified signal for ChartVision.
    """

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        """
        Uses claude-haiku by default — fast and cheap for parallel agents.
        Each agent call is ~$0.001 vs $0.01 for sonnet. 15 agents = ~$0.015/scan.
        """
        if not ANTHROPIC_AVAILABLE:
            raise RuntimeError("anthropic library not installed")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model  = model

        # ── Wave 0: instant no-API agents ────────────────────────────────────
        self.session_agent   = SessionKillZoneAgent()
        self.news_agent      = NewsGuardAgent()
        self.sizing_agent    = PositionSizingAgent()

        # ── Wave 1: parallel Claude Vision ───────────────────────────────────
        self.bias_agent       = BiasAgent(self.client, model)
        self.volume_agent     = VolumeAgent(self.client, model)
        self.momentum_agent   = MomentumAgent(self.client, model)
        self.scalp_agent      = ScalpAgent(self.client, model)
        self.sentiment_agent  = SentimentAgent(self.client, model)
        self.liquidity_agent  = LiquidityMapAgent(self.client, model)
        self.mtf_agent        = MTFConfluenceAgent(self.client, model)
        self.strategy_agent   = StrategyAnalystAgent(self.client, model)
        self.divergence_agent = DivergenceAgent(self.client, model)
        self.premarket_agent  = PreMarketAgent(self.client, model)

        # ── Wave 2: needs wave 1 bias ─────────────────────────────────────────
        self.entry_agent     = EntryAgent(self.client, model)
        self.risk_agent      = RiskManagerAgent(self.client, model)
        self.ict_agent       = ICTPatternAgent(self.client, model)

        # ── Management mode ───────────────────────────────────────────────────
        self.mgmt_agent      = ManagementAgent(self.client, model)

        # Account balance for position sizing (updated by app)
        self.account_balance = 0.0
        # Trade stats cache (updated by app from TradeMemory)
        self.trade_stats: dict = {}

    def analyze(self, image_b64: str, symbol: str = "QQQ",
                active_trade: dict = None,
                memory_context: str = "") -> dict:
        """
        Run all 14 agents and return a unified signal.

        MANAGEMENT MODE (active trade): runs Management agent only.
        SCANNING MODE:
          Wave 0 (instant):  Session + NewsGuard  [no API]
          Wave 1 (parallel): Bias + Volume + Momentum + Scalp + Sentiment + Liquidity + MTF
          Wave 2 (parallel): Entry + Risk + ICTPattern  [need bias from wave 1]
          Wave 3 (instant):  PositionSizing  [math, uses entry+risk from wave 2]
        """

        # ── MANAGEMENT MODE ──────────────────────────────────────────────────
        if active_trade:
            mgmt = self.mgmt_agent.analyze(image_b64, active_trade)
            if "_error" in mgmt:
                return self._error_result(mgmt["_error"])
            return self._build_management_result(mgmt, active_trade, symbol)

        # ── WAVE 0: Instant logic agents (no API, run first) ─────────────────
        session_result = self.session_agent.analyze()
        news_result    = self.news_agent.analyze()

        # News Guard hard block — dangerous economic event window
        if news_result.get("trade_blocked"):
            return {
                "_mode": "SPOT", "action": "WAIT", "symbol": symbol,
                "current_price": 0, "timeframe_bias": "NEUTRAL",
                "entry_price": 0, "stop_loss": 0,
                "take_profit_1": 0, "take_profit_2": 0,
                "risk_reward": "N/A", "setup_type": "NEWS_BLOCK",
                "confidence": "LOW",
                "reasoning": news_result.get("reasoning", "News guard block"),
                "summary":   news_result.get("reasoning", "High-impact event — stand aside"),
                "_agents":   {"session": session_result, "news_guard": news_result},
                "_memory":   memory_context,
            }

        # Session quality warning (doesn't block, just lowers confidence)
        session_quality = session_result.get("session_quality", "LOW")

        # ── WAVE 1: 8 parallel Claude Vision agents ───────────────────────────
        wave1_results = {}
        wave1_tasks = {
            "bias":              lambda: self.bias_agent.analyze(image_b64),
            "volume":            lambda: self.volume_agent.analyze(image_b64),
            "momentum":          lambda: self.momentum_agent.analyze(image_b64),
            "scalp":             lambda: self.scalp_agent.analyze(image_b64),
            "sentiment":         lambda: self.sentiment_agent.analyze(image_b64),
            "liquidity":         lambda: self.liquidity_agent.analyze(image_b64),
            "strategy_analyst":  lambda: self.strategy_agent.analyze(
                                     image_b64, trade_stats=self.trade_stats),
            "divergence":        lambda: self.divergence_agent.analyze(image_b64),
            "premarket":         lambda: self.premarket_agent.analyze(image_b64),
        }
        with ThreadPoolExecutor(max_workers=9) as pool:
            futures = {pool.submit(fn): key for key, fn in wave1_tasks.items()}
            for f in as_completed(futures, timeout=30):
                key = futures[f]
                try:
                    wave1_results[key] = f.result()
                except Exception as e:
                    wave1_results[key] = {"_error": str(e)}

        bias_result = wave1_results.get("bias", {"bias": "BEARISH", "current_price": 0})
        htf_bias    = bias_result.get("bias", "BEARISH")
        htf_phase   = bias_result.get("phase", "RANGING")   # IMPULSE|PULLBACK|DISTRIBUTION|RANGING

        # ── WAVE 2: Entry + Risk + ICT Pattern (need bias from wave 1) ────────
        wave2_results = {}
        wave2_tasks = {
            "entry":       lambda: self.entry_agent.analyze(image_b64, htf_bias, htf_phase),
            "risk":        lambda: self.risk_agent.analyze(
                               image_b64, bias=htf_bias,
                               entry_zone=0, stop=0, target1=0),
            "ict_pattern": lambda: self.ict_agent.analyze(image_b64),
            "mtf":         lambda: self.mtf_agent.analyze(image_b64, htf_bias),
        }
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures2 = {pool.submit(fn): key for key, fn in wave2_tasks.items()}
            for f in as_completed(futures2, timeout=25):
                key = futures2[f]
                try:
                    wave2_results[key] = f.result()
                except Exception as e:
                    wave2_results[key] = {"_error": str(e)}

        # Re-run risk with actual entry zone if available
        entry = wave2_results.get("entry", {})
        if entry.get("entry_zone") and not wave2_results.get("risk", {}).get("_error"):
            try:
                risk = self.risk_agent.analyze(
                    image_b64, bias=htf_bias,
                    entry_zone=entry.get("entry_zone", 0),
                    stop=entry.get("stop_loss", 0),
                    target1=entry.get("take_profit_1", 0))
                wave2_results["risk"] = risk
            except Exception:
                pass

        # ── WAVE 3: Position sizing (instant math, uses entry + risk) ─────────
        risk_quality = wave2_results.get("risk", {}).get("trade_quality", "B")
        sizing_result = self.sizing_agent.analyze(
            account_balance = self.account_balance,
            entry           = entry.get("entry_zone", 0),
            stop            = entry.get("stop_loss", 0),
            setup_quality   = risk_quality,
            risk_pct        = 1.0,
        )

        all_results = {
            **wave1_results, **wave2_results,
            "session":       session_result,
            "news_guard":    news_result,
            "position_size": sizing_result,
        }

        return self._aggregate(
            bias              = all_results.get("bias", {}),
            entry             = all_results.get("entry", {}),
            scalp             = all_results.get("scalp", {}),
            volume            = all_results.get("volume", {}),
            momentum          = all_results.get("momentum", {}),
            risk              = all_results.get("risk", {}),
            sentiment         = all_results.get("sentiment", {}),
            liquidity         = all_results.get("liquidity", {}),
            mtf               = all_results.get("mtf", {}),
            ict_pattern       = all_results.get("ict_pattern", {}),
            strategy_analyst  = all_results.get("strategy_analyst", {}),
            divergence        = all_results.get("divergence", {}),
            premarket         = all_results.get("premarket", {}),
            session           = session_result,
            news_guard        = news_result,
            position_size     = sizing_result,
            symbol            = symbol,
            memory_ctx        = memory_context,
            session_quality   = session_quality,
        )

    # ── Result builders ───────────────────────────────────────────────────────

    def _aggregate(self, bias: dict, entry: dict, scalp: dict,
                   volume: dict, momentum: dict, risk: dict, sentiment: dict,
                   liquidity: dict = None, mtf: dict = None,
                   ict_pattern: dict = None, strategy_analyst: dict = None,
                   divergence: dict = None, premarket: dict = None,
                   session: dict = None,
                   news_guard: dict = None, position_size: dict = None,
                   symbol: str = "QQQ", memory_ctx: str = "",
                   session_quality: str = "MEDIUM") -> dict:
        """
        Aggregate all 14 agent results into a single ChartVision-compatible signal.
        Priority: Scalp (immediate) > Entry (setup ready) > Bias (waiting)
        Risk manager, News Guard, and Session can all veto or downgrade.
        """
        liquidity        = liquidity         or {}
        mtf              = mtf               or {}
        ict_pattern      = ict_pattern       or {}
        strategy_analyst = strategy_analyst  or {}
        divergence       = divergence        or {}
        premarket        = premarket         or {}
        session          = session           or {}
        news_guard       = news_guard        or {}
        position_size    = position_size     or {}

        current_price = (bias.get("current_price") or
                         entry.get("entry_zone") or 0)
        htf_bias  = bias.get("bias", "BEARISH")
        strength  = bias.get("strength", "MODERATE")

        # ── Honor confirmed HTF bias lock from memory context ─────────────────
        # If app has locked bias after N confirmations, override raw agent bias
        if memory_ctx and "BIAS_LOCK=" in memory_ctx:
            import re as _re
            _m = _re.search(r"BIAS_LOCK=(BULLISH|BEARISH)", memory_ctx)
            if _m:
                _locked = _m.group(1)
                if _locked != htf_bias:
                    htf_bias = _locked   # override agent's raw bias with confirmed lock
                    strength = "STRONG"  # locked bias is treated as strong conviction
                else:
                    strength = "STRONG"  # bias agrees with lock — boost conviction

        # ── Build agent consensus notes ───────────────────────────────────────
        vol_confirms    = volume.get("volume_confirms", True)
        vol_warning     = volume.get("warning")
        momentum_state  = momentum.get("momentum", "MODERATE")
        mom_action      = momentum.get("best_action", "ENTER_NOW")
        risk_rec        = risk.get("recommendation", "TAKE_TRADE")
        risk_quality    = risk.get("trade_quality", "B")
        sentiment_val   = sentiment.get("sentiment", "NEUTRAL")
        tradeable       = sentiment.get("tradeable", True)
        mtf_score       = mtf.get("confluence_score", 0)
        ict_quality     = ict_pattern.get("setup_quality", "B")
        liq_target      = liquidity.get("nearest_liquidity_target", 0)

        # ── Risk veto: if Risk Manager says SKIP, return WAIT ─────────────────
        if risk_rec == "SKIP" or risk_quality == "C":
            return {
                "_mode": "SPOT", "action": "WAIT", "symbol": symbol,
                "current_price": current_price, "timeframe_bias": htf_bias,
                "entry_price": 0, "stop_loss": 0,
                "take_profit_1": 0, "take_profit_2": 0,
                "risk_reward": "N/A", "setup_type": "RISK_VETO",
                "confidence": "LOW",
                "reasoning": f"⛔ Risk Manager VETO: {risk.get('reasoning','')}",
                "summary": f"Risk Manager blocked this trade — {risk_quality} quality",
                "_agents": {"bias": bias, "entry": entry, "risk": risk,
                            "session": session, "news_guard": news_guard,
                            "liquidity": liquidity, "mtf": mtf,
                            "ict_pattern": ict_pattern, "position_size": position_size,
                                   "strategy_analyst": strategy_analyst,
                                   "divergence": divergence, "premarket": premarket},
                "_memory": memory_ctx,
            }

        # ── Momentum exhaustion veto ──────────────────────────────────────────
        if momentum_state == "EXHAUSTED" and mom_action == "AVOID":
            return {
                "_mode": "SPOT", "action": "WAIT", "symbol": symbol,
                "current_price": current_price, "timeframe_bias": htf_bias,
                "entry_price": entry.get("entry_zone", 0), "stop_loss": 0,
                "take_profit_1": 0, "take_profit_2": 0,
                "risk_reward": "N/A", "setup_type": "MOMENTUM_EXHAUSTED",
                "confidence": "LOW",
                "reasoning": f"⚠️ Momentum exhausted: {momentum.get('reasoning','')}",
                "summary": "Momentum fading — waiting for reset",
                "_agents": {"bias": bias, "momentum": momentum,
                            "session": session, "news_guard": news_guard,
                            "liquidity": liquidity, "mtf": mtf,
                            "ict_pattern": ict_pattern, "position_size": position_size,
                                   "strategy_analyst": strategy_analyst,
                                   "divergence": divergence, "premarket": premarket},
                "_memory": memory_ctx,
            }

        # ── Build confidence score from all agents ────────────────────────────
        confidence_pts = 0
        if strength == "STRONG":        confidence_pts += 2
        elif strength == "MODERATE":    confidence_pts += 1
        if vol_confirms:                confidence_pts += 1
        if momentum_state in ("STRONG", "MODERATE"): confidence_pts += 1
        if risk_quality in ("A+", "A"): confidence_pts += 2
        elif risk_quality == "B":       confidence_pts += 1
        if sentiment_val in ("FEAR", "EXTREME_FEAR") and htf_bias == "BEARISH": confidence_pts += 1
        if sentiment_val in ("GREED", "EXTREME_GREED") and htf_bias == "BULLISH": confidence_pts += 1
        # NEW: MTF confluence bonus
        if mtf_score >= 3:              confidence_pts += 2
        elif mtf_score == 2:            confidence_pts += 1
        # NEW: ICT pattern bonus
        if ict_quality in ("A+", "A"): confidence_pts += 1
        # Strategy analyst alignment bonus
        sa_strat = strategy_analyst.get("best_strategy", "")
        sa_conf  = strategy_analyst.get("confidence", "LOW")
        if sa_strat == "WAIT":
            confidence_pts = max(0, confidence_pts - 2)
        elif sa_conf == "HIGH":
            confidence_pts += 1
        # Divergence confirmation bonus
        div_detected  = divergence.get("divergence_detected", False)
        div_direction = divergence.get("divergence_direction", "NONE")
        div_strength  = divergence.get("strength", "NONE")
        if div_detected and div_strength in ("STRONG", "MODERATE"):
            if (div_direction == "BULLISH" and htf_bias == "BULLISH") or \
               (div_direction == "BEARISH" and htf_bias == "BEARISH"):
                confidence_pts += 2   # divergence confirms bias — strong edge
        # NEW: Session quality penalty
        if session_quality == "AVOID": confidence_pts = max(0, confidence_pts - 3)
        elif session_quality == "LOW": confidence_pts = max(0, confidence_pts - 1)

        confidence = "HIGH" if confidence_pts >= 7 else "MEDIUM" if confidence_pts >= 4 else "LOW"

        # ── Extract new ICT fields from bias and entry agents ─────────────────
        bias_phase         = bias.get("phase", "RANGING")          # IMPULSE|PULLBACK|DISTRIBUTION|RANGING
        choch_detected     = bias.get("choch_detected", False)
        setup_complete     = entry.get("setup_complete", False)     # ALL 6 checklist steps passed
        missing_step       = entry.get("missing_step", "Unknown")
        chk_bos            = entry.get("checklist_bos", False)
        chk_pullback       = entry.get("checklist_pullback", False)
        chk_fvg_ob         = entry.get("checklist_fvg_ob", False)
        chk_at_zone        = entry.get("checklist_at_zone", False)
        chk_confirm        = entry.get("checklist_confirmation", False)
        chk_clear_path     = entry.get("checklist_clear_path", False)

        # ── 1. Check for scalp opportunity ───────────────────────────────────
        if (scalp.get("scalp_detected") and
                scalp.get("confidence") in ("HIGH", "MEDIUM") and
                momentum_state != "EXHAUSTED"):
            direction = scalp.get("scalp_direction", "")
            action = "SCALP_BUY" if direction == "BUY_CALLS" else "SCALP_SELL"
            agent_notes = self._build_notes(volume, momentum, risk, sentiment)
            return {
                "_mode":          "SPOT",
                "action":         action,
                "symbol":         symbol,
                "current_price":  current_price,
                "timeframe_bias": htf_bias,
                "entry_price":    scalp.get("scalp_entry", current_price),
                "stop_loss":      scalp.get("scalp_stop", 0),
                "take_profit_1":  scalp.get("scalp_target", 0),
                "take_profit_2":  scalp.get("scalp_target", 0),
                "risk_reward":    "1.5",
                "setup_type":     "SCALP",
                "confidence":     scalp.get("confidence", "MEDIUM"),
                "reasoning":      scalp.get("reasoning", "") + agent_notes,
                "summary":        f"5M scalp: {scalp.get('reasoning','')}",
                "session":        session.get("session", ""),
                "session_quality":session_quality,
                "liquidity_target": liq_target,
                "mtf_score":      mtf_score,
                "_agents":        {"bias": bias, "entry": entry, "scalp": scalp,
                                   "volume": volume, "momentum": momentum,
                                   "risk": risk, "sentiment": sentiment,
                                   "liquidity": liquidity, "mtf": mtf,
                                   "ict_pattern": ict_pattern,
                                   "strategy_analyst": strategy_analyst,
                                   "divergence": divergence, "premarket": premarket,
                                   "session": session, "news_guard": news_guard,
                                   "position_size": position_size},
                "_memory":        memory_ctx,
            }

        # ── 2. Check for entry signal — STRICT ICT REQUIREMENTS ──────────────
        at_zone     = entry.get("price_at_zone", False)
        zone_quality = entry.get("zone_quality", "LOW")
        entry_zone  = entry.get("entry_zone", 0)

        # Count how many checklist items passed (for READY signal reasoning)
        checklist_passed = sum([chk_bos, chk_pullback, chk_fvg_ob,
                                chk_at_zone, chk_confirm, chk_clear_path])
        checklist_pct = f"{checklist_passed}/6"

        # Build ICT checklist status string for reasoning output
        ict_checklist_status = (
            f"ICT Checklist [{checklist_pct}]: "
            f"BOS={'✅' if chk_bos else '❌'} "
            f"Pullback={'✅' if chk_pullback else '❌'} "
            f"FVG/OB={'✅' if chk_fvg_ob else '❌'} "
            f"AtZone={'✅' if chk_at_zone else '❌'} "
            f"Confirm={'✅' if chk_confirm else '❌'} "
            f"Path={'✅' if chk_clear_path else '❌'}"
        )

        # Strict ICT gate: ALL 6 checklist items + quality requirements
        # BUY/SELL only fires when the full ICT setup is verified
        ict_gate_pass = (
            setup_complete and                          # All 6 steps confirmed
            zone_quality in ("HIGH", "MEDIUM") and     # Good zone quality
            at_zone and                                 # Price actually at zone
            bias_phase in ("PULLBACK",) and            # In pullback (not chasing impulse)
            chk_bos and                                # BOS confirmed on HTF
            chk_confirm and                            # LTF confirmation candle seen
            ict_quality in ("A+", "A", "B") and        # ICT pattern quality acceptable
            mtf_score >= 1                              # At least some MTF alignment
        )

        if ict_gate_pass:
            if htf_bias == "BULLISH":
                action = "BUY"
                opt_type = "CALL"
            else:
                action = "SELL"
                opt_type = "PUT"

            # Further downgrade to READY if volume missing or momentum weak
            if not vol_confirms or momentum_state in ("WEAK", "EXHAUSTED"):
                action = "READY"
            # Also downgrade if risk manager says wait
            if risk_rec == "WAIT":
                action = "READY"

            agent_notes = self._build_notes(volume, momentum, risk, sentiment)
            return {
                "_mode":          "SPOT",
                "action":         action,
                "symbol":         symbol,
                "current_price":  current_price,
                "timeframe_bias": htf_bias,
                "entry_price":    entry_zone,
                "stop_loss":      entry.get("stop_loss", 0),
                "take_profit_1":  entry.get("take_profit_1", 0),
                "take_profit_2":  entry.get("take_profit_2", 0),
                "risk_reward":    self._calc_rr(entry_zone,
                                               entry.get("stop_loss", 0),
                                               entry.get("take_profit_1", 0),
                                               opt_type),
                "setup_type":     entry.get("entry_type", "FVG_ENTRY"),
                "confidence":     confidence,
                "reasoning":      (f"{bias.get('reasoning','')} | "
                                   f"{entry.get('reasoning','')} | "
                                   f"{ict_checklist_status}"
                                   + agent_notes),
                "summary":        entry.get("reasoning", ""),
                "option_type":    opt_type,
                "risk_quality":   risk_quality,
                "max_risk_pct":   risk.get("max_risk_pct", 2),
                "session":        session.get("session", ""),
                "session_quality":session_quality,
                "liquidity_target": liq_target,
                "mtf_score":      mtf_score,
                "ict_pattern":    ict_pattern.get("strongest_pattern", ""),
                "recommended_contracts": position_size.get("recommended_contracts", 1),
                "ict_checklist":  ict_checklist_status,
                "_agents":        {"bias": bias, "entry": entry, "scalp": scalp,
                                   "volume": volume, "momentum": momentum,
                                   "risk": risk, "sentiment": sentiment,
                                   "liquidity": liquidity, "mtf": mtf,
                                   "ict_pattern": ict_pattern,
                                   "strategy_analyst": strategy_analyst,
                                   "divergence": divergence, "premarket": premarket,
                                   "session": session, "news_guard": news_guard,
                                   "position_size": position_size},
                "_memory":        memory_ctx,
            }

        # ── 3. Setup building (READY or WAIT) ─────────────────────────────────
        # READY: FVG/OB zone identified, setup partially building, tracking
        # WAIT:  No zone identified yet, or market in wrong phase (impulse/choppy)
        if entry_zone and zone_quality in ("HIGH", "MEDIUM") and chk_bos:
            action = "READY"
            # Describe which step is blocking full entry
            phase_note = (f"Phase: {bias_phase} | "
                          f"Missing: {missing_step} | "
                          f"{ict_checklist_status}")
        elif entry_zone and chk_fvg_ob:
            action = "READY"
            phase_note = (f"Phase: {bias_phase} — watching zone @ {entry_zone} | "
                          f"{ict_checklist_status}")
        else:
            action = "WAIT"
            phase_note = (f"Phase: {bias_phase} — no clean setup yet | "
                          f"{ict_checklist_status}")

        agent_notes = self._build_notes(volume, momentum, risk, sentiment)
        return {
            "_mode":          "SPOT",
            "action":         action,
            "symbol":         symbol,
            "current_price":  current_price,
            "timeframe_bias": htf_bias,
            "entry_price":    entry_zone,
            "stop_loss":      entry.get("stop_loss", 0),
            "take_profit_1":  entry.get("take_profit_1", 0),
            "take_profit_2":  entry.get("take_profit_2", 0),
            "risk_reward":    "N/A",
            "setup_type":     entry.get("entry_type", "BUILDING"),
            "confidence":     confidence,
            "reasoning":      (f"{bias.get('reasoning','')} | "
                               f"{phase_note}"
                               + agent_notes),
            "summary":        bias.get("reasoning", ""),
            "session":        session.get("session", ""),
            "session_quality":session_quality,
            "liquidity_target": liq_target,
            "mtf_score":      mtf_score,
            "ict_pattern":    ict_pattern.get("strongest_pattern", ""),
            "recommended_contracts":  position_size.get("recommended_contracts", 1),
            "recommended_strategy":   strategy_analyst.get("best_strategy", ""),
            "market_condition":       strategy_analyst.get("market_condition", ""),
            "ict_checklist":          ict_checklist_status,
            "_agents":        {"bias": bias, "entry": entry, "scalp": scalp,
                               "volume": volume, "momentum": momentum,
                               "risk": risk, "sentiment": sentiment,
                               "liquidity": liquidity, "mtf": mtf,
                               "ict_pattern": ict_pattern,
                               "strategy_analyst": strategy_analyst,
                               "session": session, "news_guard": news_guard,
                               "position_size": position_size},
            "_memory":        memory_ctx,
        }

    def _build_notes(self, volume: dict, momentum: dict,
                     risk: dict, sentiment: dict) -> str:
        """Build a short agent consensus note appended to reasoning."""
        notes = []
        if volume.get("warning"):
            notes.append(f"⚠️ Vol: {volume['warning']}")
        elif volume.get("volume_confirms"):
            notes.append("✅ Vol confirmed")
        if momentum.get("momentum") == "EXHAUSTED":
            notes.append("⚠️ Momentum exhausted")
        elif momentum.get("momentum") == "STRONG":
            notes.append("✅ Strong momentum")
        q = risk.get("trade_quality")
        if q:
            notes.append(f"Risk: {q}")
        obs = risk.get("obstacles_to_target")
        if obs and obs != "CLEAR":
            notes.append(f"🚧 {obs}")
        s = sentiment.get("sentiment")
        if s in ("EXTREME_FEAR", "EXTREME_GREED"):
            notes.append(f"🎭 Sentiment: {s}")
        return ("  |  " + "  |  ".join(notes)) if notes else ""

    def _build_management_result(self, mgmt: dict, active_trade: dict,
                                  symbol: str) -> dict:
        action_map = {
            "HOLD":         "HOLD",
            "MOVE_STOP_BE": "MOVE_STOP_BE",
            "TAKE_PROFIT":  "TAKE_PROFIT",
            "EXIT_NOW":     "EXIT_NOW",
        }
        action = action_map.get(mgmt.get("action", "HOLD"), "HOLD")
        return {
            "_mode":         "SPOT",
            "action":        action,
            "symbol":        symbol,
            "current_price": mgmt.get("current_price", 0),
            "pnl_estimate":  mgmt.get("pnl_estimate", 0),
            "price_vs_stop": mgmt.get("price_vs_stop", "SAFE"),
            "price_vs_t1":   mgmt.get("price_vs_t1", "NOT_YET"),
            "price_vs_t2":   mgmt.get("price_vs_t2", "NOT_YET"),
            "reasoning":     mgmt.get("reasoning", ""),
            "summary":       mgmt.get("reasoning", ""),
            "timeframe_bias": active_trade.get("option_type",
                                               "PUT") == "PUT" and "BEARISH" or "BULLISH",
            "_agent":        "MANAGEMENT",
        }

    def _error_result(self, error: str) -> dict:
        return {
            "_mode": "SPOT", "action": "WAIT",
            "symbol": "?", "current_price": 0,
            "reasoning": f"Agent error: {error}",
            "summary": "Error — falling back to WAIT",
            "_error": error,
        }

    def _calc_rr(self, entry: float, stop: float,
                 target: float, opt_type: str) -> str:
        try:
            risk   = abs(entry - stop)
            reward = abs(target - entry)
            if risk == 0:
                return "N/A"
            return str(round(reward / risk, 1))
        except Exception:
            return "N/A"
