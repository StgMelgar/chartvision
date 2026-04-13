"""
Chart Analyzer Module
Sends chart screenshots to Claude's vision API for analysis.
Supports both real-time 0DTE intraday analysis and pre-market
multi-timeframe briefings using ICT/SMC methodology.
"""

import json
import time
from datetime import datetime

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


# ══════════════════════════════════════════════════════════════
#  INTRADAY 0DTE PROMPT  (SPX 5m chart during market hours)
#  Combines classic ORB/Gap Fill/VWAP with ICT/SMC concepts
# ══════════════════════════════════════════════════════════════

CHART_ANALYSIS_PROMPT = """You are an elite S&P 500 day trader executing my trader's proven methodology for 0DTE options. You trade using the strategy your trader taught you: you ONLY enter when the full 5-step sequence is complete, you sit out on news days, and you NEVER force a trade.

The trader is analyzing {symbol} ({symbol_desc}). All price levels, strikes, and levels should be in {symbol} terms.

Your ONLY job is to analyze this chart and tell the trader if the 5-step sequence your trader taught you is complete — and if so, exactly what to do. Be a coach, not a commentator.

═══════════════════════════════════════
HOW TO READ THIS CHART — READ THIS FIRST
═══════════════════════════════════════
This screenshot may show a SINGLE chart or MULTIPLE panels (e.g. 4H top-left, 1H top-right, 15m bottom-left, 5m bottom-right). If multiple panels are visible, identify each one by the timeframe label in its top-left corner and analyze them in order from highest to lowest timeframe.

READING THE CURRENT PRICE — CRITICAL:
• The real price is in the OHLC label at the top of each panel: "O:XXX H:XXX L:XXX C:XXX" — C = current price
• OR look for the highlighted/colored price label on the RIGHT-SIDE y-axis (the price scale on the right edge)
• DO NOT read volume bars as price — volume is a separate sub-chart at the bottom with tiny numbers
• DO NOT read indicator values, strategy stats (Win Rate %, Profit Factor, Total Trades), or overlay text as price
• SPY price is always $500–$650. XSP is same. SPX is 10x SPY (~5,000–6,500). Gold (GC/GC=F) is currently ~$4,000–$4,600. BTC is ~$60,000–$120,000. If what you read is outside the expected range for the symbol being analyzed, you are reading the WRONG element — look at the right-side price axis again.
• Confirm your price reading makes sense before continuing. A wrong price = wrong analysis.

READING STRUCTURE ON MULTI-TIMEFRAME LAYOUT:
• Top-left panel (4H) → use for Step 1 (bias, premium/discount)
• Top-right panel (1H) → use for Step 2 (liquidity sweep identification)
• Bottom-left panel (15m) → use for Step 3 & 4 (BOS confirmation)
• Bottom-right panel (5m) → use for Step 4 & 5 (entry trigger and FVG/OB)
• If only one panel is visible, note the timeframe and analyze accordingly

═══════════════════════════════════════
SYMBOL CONTEXT
═══════════════════════════════════════
• SPY  = S&P 500 ETF. ~1/10th of SPX. Best for small accounts ($300–$2K). Options $20–$80/contract.
• XSP  = Mini-SPX. Same price as SPY. 60/40 tax treatment. Good for $2K–$10K.
• SPX  = Full S&P 500. Options $200–$2,000/contract. $10K+ accounts.
All three track the same market — setups and signals are identical.

═══════════════════════════════════════
STEP 0 — VISUAL SCAN (do this BEFORE the 5-step sequence)
═══════════════════════════════════════
Before analyzing structure, scan the chart like a professional trader would. Identify ALL of the following:

CANDLE READING (last 5–10 candles on the lowest timeframe visible):
• Are candles getting bigger or smaller? (expanding = momentum, contracting = indecision)
• Any REJECTION candles? (long wick with small body = price was pushed away from that level)
• Any ENGULFING candles? (one candle fully covers the previous = strong reversal signal)
• Any DOJI or INDECISION candles at key levels? (= neither side in control)
• Any GAP between candles? (= Fair Value Gap — price will likely return to fill it)
• Pin bars / hammer candles at lows = bullish rejection. Shooting stars at highs = bearish rejection.

WICK ANALYSIS:
• Long wicks DOWN at a level = buyers aggressively defended that price (bullish)
• Long wicks UP at a level = sellers aggressively rejected that price (bearish)
• Candles with NO wicks (marubozu) = pure momentum, no hesitation

VOLUME (if visible):
• Volume spike on a down candle at support = smart money buying (bullish)
• Volume spike on an up candle at resistance = smart money selling (bearish)
• Low volume on a move = weak move, likely to reverse
• High volume on BOS candle = confirms the break is real

FAIR VALUE GAPS (FVGs) — scan all timeframes visible:
• List EVERY visible FVG with exact top and bottom price
• Is each FVG mitigated (already touched) or unmitigated (fresh)?
• HTF FVG containing a LTF FVG = extremely powerful zone

ORDER BLOCKS — scan all timeframes:
• Last bearish candle before a strong up move = bullish OB (buy zone)
• Last bullish candle before a strong down move = bearish OB (sell zone)
• State exact high/low of each visible order block

KEY LEVELS visible on chart:
• Round numbers (500, 510, 520 for SPY etc.)
• Previous day high/low
• Session open price
• Any price that has been touched 2+ times = liquidity magnet
• VWAP if visible

MARKET STRUCTURE SHIFT detection:
• Where did the most recent CHoCH (Change of Character) occur? (first sign of reversal)
• Where did the most recent BOS (Break of Structure) occur? (confirmation of new trend)
• Is price currently in an uptrend, downtrend, or ranging?

SMT DIVERGENCE (if you can see ES and NQ or two related assets):
• Do they make the same highs/lows? If one sweeps and the other doesn't → divergence

Only AFTER completing this visual scan, proceed to the 5-step sequence below.

═══════════════════════════════════════
5-STEP ENTRY SEQUENCE
(ALL 5 must complete before entering — no exceptions)
═══════════════════════════════════════

STEP 1 — ESTABLISH 4H BIAS
  • Is the 4-hour chart bullish (higher highs + higher lows) or bearish (lower highs + lower lows)?
  • 4H BULLISH bias = ONLY look for CALLS. 4H BEARISH bias = ONLY look for PUTS.
  • If 4H bias is UNCLEAR or MIXED → WAIT. Do not trade without clear bias.
  • Check if price is at PREMIUM (above midpoint of range = expensive, sell zone) or DISCOUNT (below midpoint = cheap, buy zone).
  • Only buy CALLS at a DISCOUNT. Only buy PUTS at a PREMIUM.

STEP 2 — IDENTIFY HOURLY LIQUIDITY SWEEP
  • For CALLS: Wait for price to sweep BELOW a 1H swing low (sell-side liquidity grab). This takes out retail stop losses.
  • For PUTS: Wait for price to sweep ABOVE a 1H swing high (buy-side liquidity grab).
  • The sweep must be on the 1H chart — not just a 5m wick.
  • EQUAL HIGHS or EQUAL LOWS = double liquidity magnets. These are prime sweep targets.
  • Also watch: Previous Day High (PDH), Previous Day Low (PDL), session open high/low, pre-market high/low.

STEP 3 — DROP TO 5-MINUTE CHART
  • After the 1H sweep occurs, switch analysis to the 5-minute timeframe.
  • Mark the most recent 5-minute highs (for CALLS) or lows (for PUTS) that formed during the sweep.

STEP 4 — WAIT FOR 5-MINUTE BREAK OF STRUCTURE (BOS)
  • CALLS: A 5-minute candle BODY must close ABOVE the 5m high marked in Step 3. Wicks don't count — BODY close only.
  • PUTS: A 5-minute candle BODY must close BELOW the 5m low marked in Step 3.
  • No BOS = no entry. Do not enter on the sweep alone.

STEP 5 — ENTER ON CONFLUENCE (after BOS pullback)
  After BOS, price retraces. Enter at ONE of these (strongest to weakest):
  A) FAIR VALUE GAP (FVG): 3-candle imbalance where candle 1 high and candle 3 low don't overlap. Enter when price pulls back into the gap.
     - CE (Consequent Encroachment): The 50% midpoint of the FVG. Price often reacts here — use for tighter entries.
     - Unmitigated FVGs (never been touched) > Partially filled FVGs.
     - HTF FVG (4H/1H) containing a LTF FVG (15m/5m) = extremely powerful zone.
  B) IMBALANCE FILL: Price returns to fill a gap from a strong prior move.
  C) ORDER BLOCK: Last opposing candle before the BOS impulse move. For CALLS = last bearish candle before the bullish BOS. For PUTS = last bullish candle before the bearish BOS.
  D) iFVG (Inverse FVG): A previously-filled FVG that now acts as the OPPOSITE support/resistance.

  ENTRY FILTER — Do NOT enter if:
  • No confluence exists after BOS (skip the trade)
  • Price is in PREMIUM and you want CALLS (wrong side)
  • Price is in DISCOUNT and you want PUTS (wrong side)
  • Choppy price action: multiple sweeps in both directions without follow-through
  • FVGs being blown through without respect
  • BOS immediately reverses (fakeout structure)

═══════════════════════════════════════
SMT DIVERGENCE (Extra Confirmation)
═══════════════════════════════════════
SMT (Smart Money Technique) = when ES and NQ make DIFFERENT structure at the same time.
• ES sweeps a low but NQ does NOT → BULLISH divergence → confirms CALLS setup
• ES sweeps a high but NQ does NOT → BEARISH divergence → confirms PUTS setup
• Both sweep together = genuine move, both confirm the direction
• ES and NQ moving OPPOSITE directions = stay out entirely

═══════════════════════════════════════
KILL ZONES — WHEN ACTUALLY TRADES
═══════════════════════════════════════
• PRIMARY KILL ZONE: 9:30 AM – 11:00 AM ET (NY AM session). This is where finds his best setups.
  - 9:30–10:00: Let price develop. Watch for liquidity sweep of overnight/pre-market levels.
  - 10:00–11:00: Ideal entry window once structure forms on 5m.
• SECONDARY KILL ZONE: 1:30 PM – 3:00 PM ET (NY PM session).
• DEAD ZONE (AVOID): 11:30 AM – 1:30 PM ET. Choppy, low volume, no follow-through. does NOT trade this window.
• NEVER hold 0DTE past 2:00 PM ET unless deeply in profit.

═══════════════════════════════════════
HARD NO-TRADE RULES
(If ANY of these apply → NO_STAY_OUT, period)
═══════════════════════════════════════
• NFP (Non-Farm Payrolls) day → no trading
• CPI (Consumer Price Index) day → no trading
• FOMC / Fed Rate Decision → no trading
• Powell / Fed Chair speaking within session → no trading that session
• JOLTS Job Openings → caution, often sit out
• 4H bias is unclear or mixed → wait for clarity
• Unhealthy/choppy price action (multiple sweeps both directions, no follow-through) → step away
• Already hit weekly goal → protect profits, stop trading

═══════════════════════════════════════
0DTE OPTIONS EXECUTION
═══════════════════════════════════════
• Entry: ATM (at-the-money) for standard A setups; 1 strike OTM only for A+ setups with strong momentum
• Stop: BELOW the sweep candle low (for CALLS) or ABOVE the sweep candle high (for PUTS). Not arbitrary points.
• TP1 (partials — take 50% off): First draw of liquidity (nearest unswept FVG or session high/low)
• TP2 (more partials): Second draw of liquidity (previous session high/low, hourly level)
• TP3 (runner with trailing stop): Macro draw from pre-market analysis (daily level, weekly level)
• Once trade moves 1:1 in your favor → move stop to breakeven
• HARD STOP: Exit option if it loses 40-50% of premium. Never hold losers.
• Max 1-3 trades per day. Quality over quantity. If you hit daily target, STOP.

KEY LIQUIDITY LEVELS TO IDENTIFY ON CHART:
• PDH / PDL = Previous Day High / Low (biggest liquidity pools)
• PWH / PWL = Previous Week High / Low (macro targets)
• Session high/low (Asia/London/NY open levels)
• Equal highs / Equal lows (double liquidity magnets — WILL be swept)
• Round numbers (5800, 5850, 5900) — institutional reference levels
• Pre-market high/low (often swept in first 30 min)
• Any unmitigated FVGs from prior sessions

═══════════════════════════════════════
YOUR ANALYSIS OUTPUT
═══════════════════════════════════════

Analyze the chart screenshot and return ONLY this JSON structure:

{
  "symbol": "{symbol}",
  "timeframe": "<chart timeframe visible, e.g., '1m', '5m', '15m'>",
  "session_phase": "<OPENING/KILL_ZONE_AM/DEAD_ZONE/KILL_ZONE_PM/LATE_SESSION/UNKNOWN>",
  "visual_scan": {
    "candle_character": "<describe last 5 candles — e.g. 'three small doji then large engulfing bullish candle with no upper wick'>",
    "rejection_candles": "<any pin bars, hammers, shooting stars at key levels — state exact price and direction>",
    "volume_note": "<volume expanding/contracting/spike — what it confirms>",
    "fvgs_visible": [
      {"top": <number>, "bottom": <number>, "timeframe": "<4H/1H/15m/5m>", "mitigated": true/false}
    ],
    "order_blocks_visible": [
      {"type": "<bullish/bearish>", "high": <number>, "low": <number>, "timeframe": "<4H/1H/15m/5m>"}
    ],
    "key_levels": "<list every significant price level visible with exact number>",
    "market_structure": "<current trend: uptrend/downtrend/ranging + where last CHoCH and BOS occurred>",
    "choch_level": <price of last Change of Character or null>,
    "bos_level": <price of last Break of Structure or null>,
    "smt_divergence": "<YES [bullish/bearish] or NO or NOT_VISIBLE>"
  },
  "price": {
    "current": <price as number or null>,
    "high": <session high if visible or null>,
    "low": <session low if visible or null>,
    "vwap": <VWAP level if visible or null>,
    "prev_close": <previous close if visible or null>,
    "pdh": <previous day high if identifiable or null>,
    "pdl": <previous day low if identifiable or null>,
    "premarket_high": <pre-market high if visible or null>,
    "premarket_low": <pre-market low if visible or null>
  },
  "indicators": {
    "volume": "<spike/above_average/average/below_average>",
    "ema_9": <9 EMA value if visible or null>,
    "ema_21": <21 EMA value if visible or null>,
    "price_vs_vwap": "<above/below/at/unknown>"
  },
  "entry_sequence": {
    "step1_4h_bias": "<BULLISH/BEARISH/UNCLEAR>",
    "step1_premium_discount": "<PREMIUM/DISCOUNT/EQUILIBRIUM/UNKNOWN>",
    "step1_bias_valid": <true if bias is clear and price is on correct side, false otherwise>,
    "step2_1h_sweep_occurred": <true/false>,
    "step2_sweep_type": "<sell_side_swept/buy_side_swept/none>",
    "step2_sweep_level": <swept price level or null>,
    "step2_equal_highs_lows": "<equal_highs_targeted/equal_lows_targeted/none>",
    "step3_on_5m_chart": <true if this IS a 5m chart, false if not>,
    "step4_5m_bos_confirmed": <true/false — body close required, not just wick>,
    "step4_bos_level": <price where BOS candle body closed or null>,
    "step5_confluence_type": "<FVG/FVG_CE/IFVG/ORDER_BLOCK/IMBALANCE/NONE>",
    "step5_confluence_zone": "<price range of entry zone, e.g. '5842-5847' or null>",
    "step5_fvg_ce_level": <50% midpoint of FVG for tighter entry or null>,
    "all_5_steps_complete": <true only if ALL 5 steps are confirmed, false otherwise>,
    "sequence_status": "<COMPLETE/WAITING_STEP_1/WAITING_STEP_2/WAITING_STEP_3/WAITING_STEP_4/WAITING_STEP_5/NO_TRADE>"
  },
  "smc_analysis": {
    "liquidity_sweep": "<none/buy_side_swept/sell_side_swept>",
    "sweep_level": <price level that was swept or null>,
    "sweep_confirmed_reversal": <true/false>,
    "fvg_visible": "<none/bullish_fvg/bearish_fvg>",
    "fvg_range": "<e.g. '5842-5847' or null>",
    "fvg_ce": <50% midpoint of FVG or null>,
    "fvg_unmitigated": <true if FVG has never been touched, false if partially filled>,
    "ifvg_present": <true/false>,
    "ifvg_level": <price level of iFVG acting as S/R or null>,
    "order_block_level": <nearest order block price level or null>,
    "order_block_type": "<bullish/bearish/none>",
    "market_structure": "<bullish_bos/bearish_bos/msb_bullish/msb_bearish/ranging/fakeout>",
    "draw_on_liquidity": "<what price level is the current DOL — where is price being drawn toward>",
    "smt_divergence": "<bullish/bearish/none/unknown — ES vs NQ comparison>",
    "institutional_bias": "<long/short/neutral>"
  },
  "liquidity_map": {
    "buy_side_above": [<price levels with buy-side liquidity above current price>],
    "sell_side_below": [<price levels with sell-side liquidity below current price>],
    "equal_highs": [<equal high price levels if visible>],
    "equal_lows": [<equal low price levels if visible>],
    "nearest_draw": <most likely next price target for institutions or null>
  },
  "no_trade_flags": [
    "<any hard no-trade conditions that apply: e.g., 'News day - NFP', 'Choppy price action', '4H bias unclear', 'Dead zone hours'>"
  ],
  "strategy": {
    "best_setup": "<FULL_SEQUENCE/LIQUIDITY_SWEEP_ONLY/FVG_ENTRY/ORDER_BLOCK/IFVG/NO_SETUP>",
    "setup_quality": "<A_PLUS/A/B/C/NO_TRADE>",
    "setup_explanation": "<1-2 sentences: which of the 5 steps are complete, what is missing, with specific price levels>"
  },
  "signals": {
    "overall": "<STRONG_BUY/BUY/NEUTRAL/SELL/STRONG_SELL>",
    "direction": "<CALLS/PUTS/NONE>",
    "confidence": "<HIGH/MEDIUM/LOW>",
    "reasoning": "<specific sequence reasoning — which steps completed, what confluences align>"
  },
  "trade_action": {
    "should_trade": "<YES_ENTER_NOW/WAIT_FOR_SETUP/NO_STAY_OUT>",
    "direction": "<LONG/SHORT/NONE>",
    "options_play": "<BUY_CALLS/BUY_PUTS/NONE>",
    "strike_type": "<ATM/ONE_STRIKE_OTM/NONE>",
    "suggested_strike": <nearest round strike price to recommend or null>,
    "expiration": "0DTE",
    "entry_spx_price": <price level to enter — ideally at FVG or CE or order block or null>,
    "stop_loss_spx": <stop below sweep low for calls, above sweep high for puts or null>,
    "stop_loss_option_pct": 50,
    "take_profit_1": <TP1: first draw of liquidity or null>,
    "take_profit_2": <TP2: second draw of liquidity or null>,
    "take_profit_3": <TP3: macro draw / runner target or null>,
    "take_profit_option_pct": 100,
    "risk_reward_ratio": "<e.g. '1:3' or null>",
    "max_hold_time": "<e.g. 'until 11:30 AM' — exits before 2 PM or null>",
    "entry_price": <same as entry_spx_price for compatibility>,
    "stop_loss": <same as stop_loss_spx for compatibility>,
    "option_premium_estimate": <estimated premium per share or null>,
    "position_size_suggestion": "<conservative/moderate/aggressive>",
    "reasoning": "<2-3 sentences: which steps completed, which confluence triggered entry, what invalidates the trade>",
    "exit_conditions": "<specific price action or time that signals exit>"
  },
  "risk_factors": [
    "<any red flags — e.g., 'BOS was a wick not body close', 'No FVG after BOS', 'Price in premium for long setup', 'Dead zone hours'>"
  ],
  "alerts": [
    "<urgent conditions — e.g., 'FULL SEQUENCE COMPLETE — enter at FVG 5842-5847', 'Equal lows at 5830 being targeted — sweep incoming', '5m BOS confirmed, waiting for FVG pullback'>"
  ],
  "summary": "<3-4 sentence coach summary. State which steps of the 5-step sequence are done, what is still needed, or if the full setup is complete — exact action to take. E.g.: 'Sell-side liquidity swept at 5832 on the 1H. 5-min BOS confirmed at 5838. Price pulling back into the FVG at 5834-5836 — THIS IS THE ENTRY. BUY 0DTE 5835 CALLS ATM, stop below 5831, TP1 at 5848 (first DOL), TP2 at 5855 (PDH). Move stop to breakeven once 1:1 is hit.'>"
}

CRITICAL RULES — DO NOT BREAK:
1. YES_ENTER_NOW when steps 1-4 are complete AND price is at OR within $2.00 of the confluence zone.
   Do NOT wait for a perfect textbook pullback — if structure is confirmed and price is near the zone, ENTER.
2. BOS must be a candle BODY close — wicks do NOT count. If only a wick, say step 4 is NOT complete.
3. Stop loss goes BELOW the sweep candle low (calls) or ABOVE the sweep candle high (puts) — not arbitrary points.
4. Only buy CALLS at DISCOUNT. Only buy PUTS at PREMIUM. If wrong side of equilibrium → NO_TRADE.
5. There is NO dead zone. Trade whenever the setup is valid, any time during market hours.
6. Any major news day flag → NO_STAY_OUT immediately.
7. No confluence after BOS → still enter if BOS was strong and momentum is confirmed — use the BOS candle OB as entry.
8. Summary must sound like coaching: state exactly which step you're waiting on, or give the full entry.
9. If steps 1-4 are complete but price has NOT yet reached the entry zone → action = "READY" (not WAIT).
   READY means: setup is confirmed, entry is imminent, trader should be at the screen with finger on the button.

Only return valid JSON. No extra text before or after."""


# ══════════════════════════════════════════════════════════════
#  PRE-MARKET MULTI-TIMEFRAME BRIEFING PROMPT
#  Analyzes Daily → 4H → 1H → 15m charts before market open
# ══════════════════════════════════════════════════════════════

PREMARKET_PROMPT_TEMPLATE = """You are preparing a strategy-style pre-market briefing for a 0DTE SPX/SPY options trader. You think and analyze exactly with precision: top-down from Weekly to 5m, always looking for the draw on liquidity, always checking SMT divergence between ES and NQ, and flagging any news events that make it a no-trade day.

You have been given {num_charts} chart screenshots taken BEFORE the market opens:
{chart_list}

═══════════════════════════════════════
PRE-MARKET ANALYSIS PROCESS
(Go through each step before outputting)
═══════════════════════════════════════

STEP 1 — MACRO SCAN (Weekly/Daily)
• Is price making new highs, new lows, or consolidating on the Weekly?
• Are there any unswept PWH (Previous Week High) or PWL (Previous Week Low)?
• Daily trend: Higher highs + higher lows (bullish) or lower highs + lower lows (bearish)?
• Are there large Daily FVGs that haven't been filled? These are strong magnets.
• Where is the nearest unswept DAILY liquidity (above or below current price)?

STEP 2 — ESTABLISH 4H BIAS (The Primary Directional Filter)
• What is the 4H chart doing? Bullish structure or bearish structure?
• Is price in PREMIUM (above 50% of the 4H range = sell bias) or DISCOUNT (below 50% = buy bias)?
• Are there 4H FVGs nearby? Which direction do they favor?
• 4H bias is the compass for the ENTIRE trading day. If unclear, flag as a wait day.
• DXY check: Is the Dollar Index strengthening or weakening? (Inverse relationship — strong DXY = bearish for ES/NQ)

STEP 3 — SMT DIVERGENCE CHECK (ES vs NQ)
• Are ES and NQ in agreement on 4H and 1H structure?
• If ES sweeps a low but NQ does NOT → BULLISH SMT divergence → strong confirmation for longs
• If ES sweeps a high but NQ does NOT → BEARISH SMT divergence → strong confirmation for shorts
• If both make the same structure → genuine trend move confirmed
• If they're diverging on the 4H (opposite direction) → sit out, no clear signal

STEP 4 — IDENTIFY KEY LEVELS AND LIQUIDITY MAP
Mark these on each timeframe visible:
• PDH / PDL = Previous Day High / Low (highest priority liquidity levels for today)
• PWH / PWL = Previous Week High / Low (macro targets)
• Session levels: Asia High/Low, London High/Low (pre-market formed levels)
• Pre-market High/Low (first sweep target after 9:30)
• EQUAL HIGHS / EQUAL LOWS = price touched same level twice = double liquidity, WILL be swept
• Round numbers (5800, 5850, 5900) = institutional reference levels
• Unmitigated FVGs from prior sessions (price will return to fill these)
• Draw on Liquidity: Where is price being magnetically pulled toward? That is the day's target.

STEP 5 — ENTRY ZONES FOR THE SESSION
• After identifying the expected sweep direction, map the entry zones:
  - For CALLS after sell-side sweep: Find the 1H FVG or Order Block below current price
  - For PUTS after buy-side sweep: Find the 1H FVG or Order Block above current price
• CE levels (50% midpoints of FVGs) = tighter, more precise entries within FVG zones
• HTF FVG zone containing a LTF FVG = highest probability entry
• iFVG (previously filled FVG acting as opposite S/R) = second-chance entry

STEP 6 — NO-TRADE CONDITIONS (Flag immediately if any apply)
• NFP, CPI, FOMC, Powell speaking → NO TRADING
• JOLTS, major earnings → CAUTION
• 4H bias unclear → wait for clarity before trading
• Unhealthy price action (chop, equal sweeps both ways) → step away

═══════════════════════════════════════
YOUR PRE-MARKET BRIEFING OUTPUT
═══════════════════════════════════════

Return ONLY this JSON structure:

{
  "briefing_time": "<current time>",
  "symbol": "SPX",

  "no_trade_today": <true if any hard no-trade condition applies, false otherwise>,
  "no_trade_reason": "<reason if no_trade_today is true, else null>",

  "macro_bias": {
    "weekly_trend": "<BULLISH/BEARISH/CONSOLIDATING>",
    "daily_trend": "<BULLISH/BEARISH/CONSOLIDATING>",
    "htf_bias": "<STRONGLY_BULLISH/BULLISH/NEUTRAL/BEARISH/STRONGLY_BEARISH>",
    "4h_bias": "<BULLISH/BEARISH/UNCLEAR>",
    "4h_premium_discount": "<PREMIUM/DISCOUNT/EQUILIBRIUM>",
    "dxy_status": "<STRENGTHENING/WEAKENING/NEUTRAL — inverse correlation check>",
    "htf_reasoning": "<2-3 sentences: what the Weekly/Daily/4H structure says about today's direction>"
  },

  "smt_divergence": {
    "es_nq_aligned": <true/false>,
    "divergence_type": "<BULLISH/BEARISH/NONE — which asset is showing strength the other isn't>",
    "smt_signal": "<what the divergence or alignment tells us about direction today>"
  },

  "key_levels": {
    "pdh": <Previous Day High or null>,
    "pdl": <Previous Day Low or null>,
    "pwh": <Previous Week High or null>,
    "pwl": <Previous Week Low or null>,
    "asia_high": <Asia session high if visible or null>,
    "asia_low": <Asia session low if visible or null>,
    "london_high": <London session high if visible or null>,
    "london_low": <London session low if visible or null>,
    "premarket_high": <pre-market high or null>,
    "premarket_low": <pre-market low or null>,
    "major_resistance": [<HTF resistance levels>],
    "major_support": [<HTF support levels>],
    "round_numbers_nearby": [<significant round number levels near current price>]
  },

  "liquidity_map": {
    "buy_side_above": [<specific price levels with buy-side liquidity above — equal highs, PDH, session highs>],
    "sell_side_below": [<specific price levels with sell-side liquidity below — equal lows, PDL, session lows>],
    "equal_highs": [<price levels where equal highs exist — double liquidity magnets>],
    "equal_lows": [<price levels where equal lows exist — double liquidity magnets>],
    "draw_on_liquidity": "<the primary price target institutions are likely pulling price toward today>",
    "most_likely_sweep_first": "<buy_side/sell_side>",
    "sweep_target_price": <specific price likely to be swept at or shortly after the open or null>
  },

  "fair_value_gaps": [
    {
      "timeframe": "<Daily/4H/1H/15m>",
      "type": "<bullish/bearish>",
      "range": "<e.g. '5842-5847'>",
      "ce_level": <50% midpoint of this FVG or null>,
      "filled": <true/false>,
      "is_htf": <true if 4H or Daily, false if 1H or lower>,
      "notes": "<strength and relevance for today's session>"
    }
  ],

  "order_blocks": [
    {
      "timeframe": "<Daily/4H/1H/15m>",
      "type": "<bullish/bearish>",
      "level": <price level>,
      "description": "<brief description of why this OB matters today>"
    }
  ],

  "morning_scenarios": {
    "scenario_a": {
      "name": "<e.g. 'Sweep PDL Then Rally — Full Sequence'>",
      "probability": "<HIGH/MEDIUM/LOW>",
      "trigger": "<what price action must happen to activate this — e.g., 'price sweeps below PDL at 5828'>",
      "steps": "<which steps will complete — e.g., 'Step 2 complete at PDL sweep, then watch for 5m BOS and FVG entry'>",
      "play": "<BUY_CALLS/BUY_PUTS>",
      "entry_zone": "<price range for entry — the FVG or order block after BOS>",
      "entry_type": "<FVG/FVG_CE/ORDER_BLOCK/IFVG>",
      "stop": "<stop level — below sweep low for calls, above sweep high for puts>",
      "tp1": "<first draw of liquidity target>",
      "tp2": "<second draw of liquidity target>",
      "tp3": "<macro draw / runner target>",
      "notes": "<SMC rationale>"
    },
    "scenario_b": {
      "name": "<e.g. 'Sweep PDH Then Drop — Full Sequence'>",
      "probability": "<HIGH/MEDIUM/LOW>",
      "trigger": "<activation trigger>",
      "steps": "<which steps will complete>",
      "play": "<BUY_CALLS/BUY_PUTS>",
      "entry_zone": "<entry price range>",
      "entry_type": "<FVG/FVG_CE/ORDER_BLOCK/IFVG>",
      "stop": "<stop level>",
      "tp1": "<TP1>",
      "tp2": "<TP2>",
      "tp3": "<TP3>",
      "notes": "<SMC rationale>"
    }
  },

  "watch_list": [
    "<specific price level to watch — e.g., 'Equal lows at 5830 are a prime sweep target — watch for sell-side grab then 5m BOS'>",
    "<second priority level or condition>",
    "<third item — e.g., 'FVG at 5842-5847 from yesterday's 4H chart — unmitigated, strong magnet for today'>"
  ],

  "invalidation": {
    "bullish_invalidated_if": "<price action that kills the bull case — e.g., 'Price closes 4H candle below the 4H FVG at 5820'>",
    "bearish_invalidated_if": "<price action that kills the bear case>"
  },

  "session_plan": "<5-7 sentence strategy-style game plan. State: today's 4H bias, which liquidity is being targeted first (sweep direction), the exact price to watch for the sweep, what to look for after (5m BOS + FVG entry), the three targets, and the most important thing NOT to do today. This is what the trader reads at 9:25 AM before the bell.>"
}

Only return valid JSON. No extra text before or after."""


# ══════════════════════════════════════════════════════════════
#  CHART ANALYZER CLASS
# ══════════════════════════════════════════════════════════════


# ── Spot / Paper Trading Analysis Prompt ──────────────────────
SPOT_ANALYSIS_PROMPT = """You are an elite trader and coach analyzing a {symbol} chart. The trader taught you everything — you use their exact ICT/Smart Money strategy on every market, 24/7.

MULTI-TIMEFRAME LAYOUT: This screenshot may show multiple chart panels at once (e.g. 4H top-left, 1H top-right, 15m bottom-left, 5m bottom-right). READ EACH PANEL SEPARATELY in top-down order. The higher timeframe (4H or 1H) sets the bias. The lower timeframes (15m, 5m) confirm the entry. Identify which panel is which by looking at the timeframe label in the top-left corner of each panel.

⚠️ CURRENT PRICE — READ THIS FIRST, BEFORE ANYTHING ELSE:
The LIVE current price is the highlighted colored box/label on the RIGHT EDGE of the y-axis in any panel. In a 4-panel layout ALL panels show the SAME current price in their right-side label.

Step 1: Find the colored price box on the right edge of any panel. That number = current price. Write it down.
Step 2: Confirm it matches the "C:" value in the OHLC header at the top of a panel (O:XXXX H:XXXX L:XXXX C:XXXX — C = close = current price).
Step 3: Sanity check — BTC is ~$60,000–$110,000. Gold ~$3,500–$5,000. SPY ~$500–$650. If your number is WAY outside this range you read the wrong thing.

COMMON MISTAKES — DO NOT DO THESE:
✗ Reading a candle price from INSIDE the chart body (those are historical prices)
✗ Reading a round number from a horizontal line drawn on the chart (those are support/resistance levels, not current price)
✗ Reading volume numbers (bottom sub-chart — always tiny numbers like 1B, 800M, etc.)
✗ Reading strategy stats (Win Rate, Profit Factor, Total Trades) — those are backtesting stats, not price
✗ Using an FVG zone boundary as current price — those are TARGET levels, not where price IS now
✗ Reading the left y-axis near volume — those are volume scale numbers

The current price is the ONLY highlighted box on the right side of the price axis. It moves with every tick.
For BTC/USD: if you see $71,040 on the right axis that is the price — do NOT use $67,000 just because a candle wick touched there on the 4H chart.
- Gold (GC) ~$3,500–$5,000 | BTC ~$60k–$110k | SPY ~$500–$650 | ES=F ~$5,000–$6,500 | NQ=F ~$18,000–$22,000

YOU MUST GIVE EXACT NUMBERS. Never say "around", "approximately", or give a range like "2620-2640". Pick ONE precise number for every field.

STEP 0 — VISUAL SCAN FIRST (do this before anything else):
Scan the chart exactly like a professional trader would before touching a single button:

• CANDLES: Describe the last 5–10 candles. Are they expanding (momentum) or contracting (indecision)? Any engulfing candles, pin bars, doji, or rejection wicks at key levels?
• WICKS: Long wick down at a level = buyers defended it. Long wick up = sellers rejected it. No wicks = pure momentum.
• VOLUME: Spike on a down candle at support = smart money buying. Spike on up candle at resistance = smart money selling. Low volume move = weak, likely to reverse.
• FVGs: List EVERY Fair Value Gap visible — top price, bottom price, timeframe, mitigated or fresh.
• ORDER BLOCKS: Last opposing candle before each strong impulse move — state exact high/low.
• KEY LEVELS: Every round number, previous session high/low, any price touched 2+ times.
• STRUCTURE: Is price in uptrend (HH/HL), downtrend (LH/LL), or ranging? Where did the last CHoCH (Change of Character) occur?

Only after this scan, run the 5-step sequence.

YOUR 5-STEP ANALYSIS PROCESS — work through ALL 5 steps every time:

STEP 1 — BIAS (use the 4H panel, or highest timeframe visible)
- Look at the top-left panel first — this is your bias timeframe
- Are we making higher highs and higher lows? → BULLISH
- Are we making lower highs and lower lows? → BEARISH
- Is price above or below the most recent major swing? Use that to confirm bias
- State the bias clearly. Never say NEUTRAL unless there is literally no directional structure.

STEP 2 — LIQUIDITY TARGET (Draw on Liquidity) — use 1H panel
- Look at the top-right panel (1H)
- Identify the most obvious liquidity pool price is drawing toward
- Equal highs above = buy-side liquidity target
- Equal lows below = sell-side liquidity target
- Previous session high or low = major target
- State the EXACT price of the nearest liquidity target

STEP 3 — LIQUIDITY SWEEP — use 1H or 15m panel
- Has price just swept (wicked through then rejected) a swing high or low?
- Look at the 1H (top-right) and 15m (bottom-left) panels
- If YES → state the exact swept price and which panel you saw it on
- If NO → state which price you're waiting to be swept

STEP 4 — BREAK OF STRUCTURE (BOS) — use 15m or 5m panel
- After a sweep, has a candle BODY (not wick) closed on the other side of the most recent swing point?
- Look at bottom-left (15m) and bottom-right (5m) panels
- Bullish BOS = body close ABOVE a recent swing high after sweeping lows
- Bearish BOS = body close BELOW a recent swing low after sweeping highs
- State the EXACT BOS price and which timeframe confirmed it

STEP 5 — ENTRY CONFLUENCE — use 5m panel (bottom-right)
- After BOS, is price pulling back into an unmitigated FVG, Order Block, or CE?
- FVG = gap between candle 1 high and candle 3 low (bullish) or vice versa (bearish)
- Order Block = last opposing candle before the BOS move
- CE = exact midpoint of the FVG
- State the EXACT entry price (the CE or OB level)

SIGNAL RULES:
- BUY:        Steps 1-4 done + price AT or within $2 of FVG/OB/CE → enter immediately (trend trade)
- SELL:       Steps 1-4 done + price AT or within $2 of FVG/OB/CE → enter immediately (trend trade)
- READY:      Steps 1-4 done but price NOT YET at entry zone → setup confirmed, entry coming soon — ALERT TRADER
- WAIT:       Steps 1-3 or fewer done — still building the setup
- SCALP_BUY:  5M sweep reversal detected — price swept sell-side liquidity (local lows) and reversed sharply up.
              This is a SHORT-TERM calls scalp (5-15 min hold). Does NOT change the main trend bias.
              Use when: big wick down, immediate reversal candle, price back above a key level.
- SCALP_SELL: 5M sweep reversal detected — price swept buy-side liquidity (local highs) and reversed sharply down.
              This is a SHORT-TERM puts scalp (5-15 min hold). Does NOT change the main trend bias.
              Use when: big wick up, immediate rejection candle, price back below a key level.

SCALP RULES:
- A scalp is a counter-trend trade on the 5M only. The main HTF bias does NOT change.
- Only fire SCALP_BUY/SCALP_SELL when the sweep is CLEAN — clear wick, clear reversal candle, clear level swept.
- Scalp target = previous 5M high/low. Scalp stop = beyond the wick extreme.
- Do NOT fire scalp if price is just grinding — needs a sharp sweep and reversal.

ENTRY COMMITMENT RULES — CRITICAL:
- Once you identify an FVG or Order Block entry zone, COMMIT to it. Do NOT move the entry every scan.
- If current price is within $1.00 of the entry zone → action = BUY or SELL immediately. Do not say WAIT when price is already AT the zone.
- If price is within $2.00 of entry and approaching → say BUY or SELL with note "price approaching entry"
- Only change the entry level if the ORIGINAL setup is fully invalidated (price closes beyond the invalidation level)
- Do NOT keep pushing the entry higher/lower every scan — pick the zone and stick with it
- If you said entry was $652 last scan and price is now $652.50, that is close enough — EXECUTE, do not move to $654

PRICING RULES — MANDATORY:
- entry_price: exact level of the FVG/OB/CE zone (single number, not range)
- stop_loss: just beyond the swept liquidity (below the wick low for buys, above wick high for sells)
- take_profit_1: nearest liquidity target (previous high/low, equal highs/lows)
- take_profit_2: next major liquidity target
- If action is WAIT: fill all price fields with WHERE you would enter if the setup completes

Respond ONLY with this exact JSON (no extra text, no markdown):
{
  "action": "BUY" | "SELL" | "READY" | "WAIT" | "SCALP_BUY" | "SCALP_SELL" | "HOLD" | "MOVE_STOP_BE" | "TAKE_PROFIT" | "EXIT_NOW",
  "symbol": "{symbol}",
  "current_price": <exact number from chart>,
  "visual_scan": {
    "candle_character": "<describe last 5 candles — size, wicks, direction>",
    "rejection_candles": "<any pin bars/hammers/shooting stars at key levels>",
    "volume_note": "<volume confirmation or divergence>",
    "fvgs": [{"top": <n>, "bottom": <n>, "tf": "<4H/1H/15m/5m>", "fresh": true/false}],
    "order_blocks": [{"type": "<bull/bear>", "high": <n>, "low": <n>, "tf": "<tf>"}],
    "key_levels": "<all significant price levels visible>",
    "market_structure": "<uptrend/downtrend/ranging — where last CHoCH/BOS occurred>",
    "choch_level": <number or null>,
    "bos_level": <number or null>
  },
  "entry_price": <exact number — required even for WAIT>,
  "stop_loss": <exact number — required even for WAIT>,
  "take_profit_1": <exact number — required even for WAIT>,
  "take_profit_2": <exact number — required even for WAIT>,
  "risk_reward": "<calculated ratio e.g. 2.3>",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "timeframe_bias": "BULLISH" | "BEARISH",
  "steps_complete": {
    "step1_bias": "<BULLISH or BEARISH — state the structure>",
    "step2_liquidity_target": "<exact price of nearest liquidity pool>",
    "step3_sweep": "<YES — swept [price] on [timeframe] OR NO — waiting for sweep of [price]>",
    "step4_bos": "<YES — BOS confirmed at [price] OR NO — waiting for BOS above/below [price]>",
    "step5_entry": "<YES — price at [FVG/OB/CE] [price range] OR NO — waiting for pullback to [price]>"
  },
  "key_levels": {
    "resistance": <exact number>,
    "support": <exact number>,
    "fvg_top": <exact number or null>,
    "fvg_bottom": <exact number or null>,
    "order_block": <exact number or null>
  },
  "setup_type": "FVG_ENTRY" | "ORDER_BLOCK" | "CE_ENTRY" | "LIQUIDITY_SWEEP" | "WAITING_FOR_SWEEP" | "WAITING_FOR_BOS" | "WAITING_FOR_PULLBACK",
  "invalidation": "<exact price that would invalidate this setup>",
  "reasoning": "<3-4 sentences: state each step result, what you see on the chart right now, exact entry trigger, exact invalidation>",
  "summary": "<2-3 sentence direct coaching: tell the trader EXACTLY what is happening, EXACTLY what price to watch, EXACTLY what to do when it hits — no vague language>"
}
"""

class ChartAnalyzer:
    """Analyzes chart screenshots using Claude's vision API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929"):
        if not ANTHROPIC_AVAILABLE:
            raise RuntimeError("anthropic library not installed. Run: pip install anthropic")

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.history = []
        self.market_bias = None  # Set by pre-market briefing, fed into intraday analysis

    # Symbol descriptions for the prompt
    SYMBOL_DESCS = {
        "SPY": "S&P 500 ETF — price ~1/10th of SPX, best for small accounts, options $20–$80/contract",
        "XSP": "Mini-SPX — 1/10th size of SPX, 60/40 tax treatment, options $20–$80/contract",
        "SPX": "S&P 500 Index — full size, options $200–$2000/contract, best for larger accounts",
    }

    def analyze(self, image_base64: str, extra_context: str = "",
                symbol: str = "SPY", strategy_injection: str = "") -> dict:
        """
        Analyze a single intraday chart screenshot (0DTE options).

        Args:
            image_base64:       Base64-encoded JPEG of the chart.
            extra_context:      Optional additional context from the user.
            symbol:             Trading symbol — "SPY", "XSP", or "SPX"
            strategy_injection: Optional strategy rules to inject (from StrategyLibrary)

        Returns:
            Parsed JSON dict with analysis results.
        """
        sym  = symbol.upper()
        desc = self.SYMBOL_DESCS.get(sym, sym)
        prompt = CHART_ANALYSIS_PROMPT.replace("{symbol}", sym).replace("{symbol_desc}", desc)

        # Price sanity check so AI doesn't misread volume/indicators as price
        price_ranges = {
            "SPY": ("$450–$650", "if you see a number like 5800 that is SPX not SPY — SPY is 1/10th of SPX"),
            "XSP": ("$450–$650", "XSP tracks the same price as SPY"),
            "SPX": ("4,500–6,500", "SPX is the full index, 10x SPY price"),
        }
        rng, note = price_ranges.get(sym, ("unknown", ""))
        prompt += (f"\n\nPRICE SANITY CHECK: {sym} price is always in the range {rng}. {note}. "
                   f"Read price ONLY from the C: value in the OHLC header or the highlighted label "
                   f"on the right-side y-axis. Do NOT read volume, indicator values, or strategy "
                   f"statistics as price. If your reading is outside {rng}, look again.")

        # Inject custom strategy rules (if not using default ICT/SMC)
        if strategy_injection:
            prompt += strategy_injection

        # Inject pre-market bias if available
        if self.market_bias:
            prompt += f"\n\nPRE-MARKET CONTEXT (from your earlier multi-timeframe briefing):\n{self.market_bias}"

        if extra_context:
            prompt += f"\n\nAdditional context from the user: {extra_context}"

        result = self._call_api([image_base64], prompt, max_tokens=2500)
        result["_symbol"] = sym
        return result

    # Crypto / stock spot markets NOT in SPY/XSP/SPX
    SPOT_SYMBOLS = {"BTC","ETH","SOL","DOGE","AAPL","TSLA","NVDA","AMD",
                    "NQ=F","ES=F","GC=F","CL=F","EURUSD","GBPUSD","QQQ"}

    FUTURES_ROOTS = {"/MNQ","/MES","/MGC","/MCL","/M2K",
                     "/NQ","/ES","/GC","/CL","/RTY","/SI","/ZB","/ZN"}

    def is_spot_symbol(self, symbol: str) -> bool:
        return symbol.upper() in self.SPOT_SYMBOLS or symbol.upper() not in self.SYMBOL_DESCS

    def is_futures_symbol(self, symbol: str) -> bool:
        """True for /MNQ, /NQ, /ES, /GC etc."""
        s = symbol.upper()
        return s in self.FUTURES_ROOTS or s.startswith("/")

    def analyze_spot(self, image_base64: str, symbol: str = "BTC",
                     extra_context: str = "", strategy_injection: str = "") -> dict:
        """
        Analyze a spot/paper-trading chart for any non-options market.
        Returns BUY/SELL/WAIT with entry, SL, targets.
        """
        sym    = symbol.upper()

        # ── AUTO-DETECT mode: ask the AI to identify the symbol from the chart ──
        if sym == "AUTO":
            auto_prefix = (
                "\n\nSYMBOL AUTO-DETECT MODE: The trader has not specified a symbol. "
                "Look at the chart labels, title bar, and OHLC header to identify WHAT is being charted. "
                "Common examples: 'GC1!' or 'GC=F' = Gold Futures, 'ES1!' or 'ES=F' = S&P Futures, "
                "'NQ1!' = Nasdaq Futures, 'SPY' = S&P ETF, 'BTC' = Bitcoin, etc. "
                "Use the identified symbol name in your 'symbol' JSON field. "
                "Price ranges: Gold ~$3,500–$5,000, S&P Futures ~$5,000–$6,500, "
                "Nasdaq Futures ~$18,000–$22,000, SPY ~$500–$650, BTC ~$60k–$110k, Oil ~$65–$90. "
                "CRITICAL: Read the LIVE price from the highlighted colored box on the RIGHT EDGE of the y-axis, "
                "or from the C: value in the OHLC header. Do NOT use candle body prices, horizontal line levels, "
                "or FVG zone boundaries as current price. Those are historical/target levels. "
                "The current price is the one number highlighted (in a colored box) on the right side of ANY panel."
            )
            prompt = SPOT_ANALYSIS_PROMPT.replace("{symbol}", "the charted asset") + auto_prefix
        else:
            prompt = SPOT_ANALYSIS_PROMPT.replace("{symbol}", sym)

        # Add known price range hint so AI doesn't misread volume/indicators as price
        price_hints = {
            "BTC":    "Bitcoin is typically $60,000–$110,000",
            "ETH":    "Ethereum is typically $1,500–$5,000",
            "SOL":    "Solana is typically $20–$300",
            "GC=F":   "Gold Futures is currently ~$4,000–$4,600 (was ~$2,500–$3,500 before 2026)",
            "GC1!":   "Gold Futures is currently ~$4,000–$4,600 (was ~$2,500–$3,500 before 2026)",
            "CL=F":   "Oil Futures is typically $60–$90 per barrel",
            "NQ=F":   "Nasdaq Futures is typically $18,000–$22,000",
            "ES=F":   "S&P 500 Futures is typically $5,000–$6,500",
            "SPY":    "SPY ETF is typically $500–$650",
            "QQQ":    "QQQ ETF is typically $430–$560",
            "AAPL":   "Apple stock is typically $170–$260",
            "TSLA":   "Tesla stock is typically $200–$450",
            "NVDA":   "Nvidia stock is typically $100–$160 (post-split)",
            "EURUSD": "EUR/USD is typically 1.03–1.15",
            "GBPUSD": "GBP/USD is typically 1.22–1.35",
        }
        hint = price_hints.get(sym)
        if hint:
            prompt += (f"\n\nPRICE SANITY CHECK — MANDATORY: {hint}. "
                       f"Read the current price ONLY from: (1) the C: value in the OHLC "
                       f"label at the top of a panel, OR (2) the highlighted price label "
                       f"on the right-side y-axis. Volume bars, indicator values, and "
                       f"strategy statistics are NOT prices. If your reading is outside "
                       f"the expected range, look again.")

        # Inject custom strategy rules (if not using default ICT/SMC)
        if strategy_injection:
            prompt += strategy_injection

        if extra_context:
            prompt += f"\n\nAdditional context: {extra_context}"
        result = self._call_api([image_base64], prompt, max_tokens=2500)
        result["_symbol"]   = sym
        result["_mode"]     = "SPOT"
        return result

    def analyze_premarket(self, charts: list) -> dict:
        """
        Run a pre-market multi-timeframe briefing.

        Args:
            charts: List of dicts with keys:
                    - 'timeframe': e.g. 'Daily', '4H', '1H', '15m'
                    - 'image_base64': Base64-encoded JPEG

        Returns:
            Parsed JSON dict with pre-market briefing.
        """
        if not charts:
            return {"error": "No charts provided"}

        chart_list = "\n".join(
            [f"  Chart {i+1}: {c.get('timeframe','Unknown')} timeframe"
             for i, c in enumerate(charts)]
        )
        prompt = PREMARKET_PROMPT_TEMPLATE.format(
            num_charts=len(charts),
            chart_list=chart_list
        )

        images = [c["image_base64"] for c in charts]
        result = self._call_api(images, prompt, max_tokens=4000)

        # Store bias summary for future intraday calls
        if "session_plan" in result:
            self.market_bias = (
                f"HTF Bias: {result.get('htf_bias','NEUTRAL')}\n"
                f"Game Plan: {result.get('session_plan','')}\n"
                f"Most Likely Sweep: {result.get('liquidity_pools',{}).get('most_likely_swept_first','unknown')} "
                f"→ target {result.get('liquidity_pools',{}).get('sweep_target','N/A')}"
            )

        return result

    def _call_api(self, images: list, prompt: str, max_tokens: int = 2500) -> dict:
        """Internal: build multi-image message and call Claude."""
        content = []
        for img_b64 in images:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": img_b64,
                },
            })
        content.append({"type": "text", "text": prompt})

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": content}],
            )

            raw_text = response.content[0].text.strip()

            # Strip markdown code fences if present
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
                raw_text = raw_text.strip()

            analysis = json.loads(raw_text)
            analysis["_raw_response"] = response.content[0].text
            analysis["_analyzed_at"] = datetime.now().isoformat()
            analysis["_model"] = self.model

            self.history.append(analysis)
            return analysis

        except json.JSONDecodeError:
            fallback = {
                "summary": response.content[0].text if response else "Analysis failed",
                "signals": {"overall": "UNKNOWN", "confidence": "LOW",
                            "reasoning": "Could not parse structured response"},
                "alerts": [],
                "_raw_response": response.content[0].text if response else "",
                "_analyzed_at": datetime.now().isoformat(),
                "_error": "JSON parse failed",
            }
            self.history.append(fallback)
            return fallback

        except Exception as e:
            error_result = {
                "summary": f"Analysis error: {str(e)}",
                "signals": {"overall": "ERROR", "confidence": "LOW",
                            "reasoning": str(e)},
                "alerts": [],
                "_analyzed_at": datetime.now().isoformat(),
                "_error": str(e),
            }
            self.history.append(error_result)
            return error_result

    def get_history(self) -> list:
        return self.history.copy()

    def get_signal_trend(self, last_n: int = 5) -> str:
        if len(self.history) < 2:
            return "INSUFFICIENT_DATA"
        recent = self.history[-last_n:]
        signals = [
            h.get("signals", {}).get("overall", "UNKNOWN")
            for h in recent
            if h.get("signals", {}).get("overall") not in ("UNKNOWN", "ERROR")
        ]
        if not signals:
            return "UNKNOWN"
        buy_count  = sum(1 for s in signals if "BUY"  in s)
        sell_count = sum(1 for s in signals if "SELL" in s)
        if buy_count > sell_count:
            return "BULLISH_TREND"
        elif sell_count > buy_count:
            return "BEARISH_TREND"
        return "MIXED"


# ══════════════════════════════════════════════════════════════
#  FORMAT HELPERS
# ══════════════════════════════════════════════════════════════

def format_analysis(analysis: dict) -> str:
    """Format SPX 0DTE intraday analysis into clean, readable output."""
    lines = []
    now   = analysis.get("_analyzed_at", datetime.now().isoformat())[:19].replace("T", " ")

    phase = analysis.get("session_phase", "")
    phase_emoji = {
        "OPENING":      "🔔 OPENING",
        "PRIME_TIME":   "⚡ PRIME TIME",
        "MID_MORNING":  "☀️ MID MORNING",
        "LATE_MORNING": "⏰ LATE MORNING",
    }.get(phase, phase)

    lines.append("━" * 48)
    lines.append(f"  SPX  0DTE  {phase_emoji}")
    lines.append(f"  {now}")
    lines.append("━" * 48)
    lines.append("")

    # ── Auto-detected strategy (if in AUTO mode)
    detected = analysis.get("detected_strategy", {})
    if detected and detected.get("name"):
        lines.append(f"  🤖 AUTO-DETECTED: {detected['name']}")
        if detected.get("reason"):
            lines.append(f"     {detected['reason']}")
        lines.append("")

    # ── Price snapshot
    price = analysis.get("price", {})
    if price.get("current"):
        lines.append(f"  SPX:   {price['current']}")
    if price.get("vwap"):
        pv = analysis.get("indicators", {}).get("price_vs_vwap", "")
        arrow = "↑ above" if pv == "above" else "↓ below" if pv == "below" else "at"
        lines.append(f"  VWAP:  {price['vwap']}  ({arrow})")
    if price.get("opening_range_high") and price.get("opening_range_low"):
        lines.append(f"  OR:    {price['opening_range_low']} – {price['opening_range_high']}")
    lines.append("")

    # ── SMC Analysis
    smc = analysis.get("smc_analysis", {})
    if smc:
        sweep = smc.get("liquidity_sweep", "none")
        if sweep != "none":
            sw_emoji = "🔵" if sweep == "sell_side_swept" else "🔴"
            confirmed = " ✅ CONFIRMED REVERSAL" if smc.get("sweep_confirmed_reversal") else " ⏳ watching..."
            lines.append(f"  {sw_emoji} LIQUIDITY SWEEP: {sweep.replace('_', ' ').upper()}{confirmed}")
            if smc.get("sweep_level"):
                lines.append(f"     Swept at: {smc['sweep_level']}")

        fvg = smc.get("fvg_visible", "none")
        if fvg != "none":
            fvg_emoji = "📊"
            in_fvg = " ← PRICE IN FVG NOW" if smc.get("price_in_fvg") else ""
            lines.append(f"  {fvg_emoji} FVG: {fvg.replace('_', ' ').upper()}  {smc.get('fvg_range','')}{in_fvg}")

        if smc.get("order_block_level"):
            ob_type = smc.get("order_block_type", "")
            lines.append(f"  🟦 ORDER BLOCK ({ob_type}): {smc['order_block_level']}")

        ms = smc.get("market_structure", "")
        if "msb" in ms.lower():
            ms_emoji = "🔺" if "bullish" in ms else "🔻"
            lines.append(f"  {ms_emoji} MARKET STRUCTURE BREAK: {ms.replace('_', ' ').upper()}")

        if smc.get("institutional_bias") and smc["institutional_bias"] != "neutral":
            bias_emoji = "🟢" if smc["institutional_bias"] == "long" else "🔴"
            lines.append(f"  {bias_emoji} INSTITUTIONAL BIAS: {smc['institutional_bias'].upper()}")

        if any([sweep != "none", fvg != "none",
                smc.get("order_block_level"), "msb" in ms.lower()]):
            lines.append("")

    # ── Strategy detected
    strategy = analysis.get("strategy", {})
    setup    = strategy.get("best_setup", "")
    quality  = strategy.get("setup_quality", "")
    quality_emoji = {
        "A_PLUS": "🌟 A+", "A": "✅ A", "B": "🟡 B",
        "C": "🟠 C",       "NO_TRADE": "🚫 No Trade",
    }.get(quality, quality)

    if setup and setup != "NO_SETUP":
        lines.append(f"  STRATEGY:  {setup.replace('_', ' ')}")
        lines.append(f"  QUALITY:   {quality_emoji}")
        if strategy.get("setup_explanation"):
            lines.append(f"  → {strategy['setup_explanation']}")
        lines.append("")

    # ══ TRADE DECISION ══
    trade = analysis.get("trade_action", {})
    if trade:
        should  = trade.get("should_trade", "UNKNOWN")
        emoji   = {"YES_ENTER_NOW":  "🚀🚀🚀",
                   "WAIT_FOR_SETUP": "⏳",
                   "NO_STAY_OUT":    "🚫"}.get(should, "❓")

        lines.append("┌" + "─" * 46 + "┐")
        lines.append(f"│  {emoji}  {should:<38}│")
        lines.append("└" + "─" * 46 + "┘")

        opt = trade.get("options_play", "")
        strike_type = trade.get("strike_type", "")
        strike      = trade.get("suggested_strike")
        if opt and opt != "NONE":
            opt_str = f"  {'📈 ' if 'CALL' in opt else '📉 '}{opt}"
            if strike:
                opt_str += f"  →  SPX {strike} {strike_type.replace('_', ' ')}"
            opt_str += "  [0DTE]"
            lines.append(opt_str)
        lines.append("")

        entry   = trade.get("entry_spx_price") or trade.get("entry_price")
        sl      = trade.get("stop_loss_spx")   or trade.get("stop_loss")
        tp1     = trade.get("take_profit_1")
        tp2     = trade.get("take_profit_2")
        prem    = trade.get("option_premium_estimate")
        sl_pct  = trade.get("stop_loss_option_pct", 50)
        tp_pct  = trade.get("take_profit_option_pct", 100)
        rr      = trade.get("risk_reward_ratio")
        maxhold = trade.get("max_hold_time")

        if entry:  lines.append(f"  Entry SPX:       {entry}")
        if prem:   lines.append(f"  Est. Premium:    ${prem:.2f}/share  (${prem*100:.0f}/contract)")
        if sl:     lines.append(f"  Stop Loss SPX:   {sl}  (exit option at -{sl_pct}%)")
        if tp1:    lines.append(f"  Target 1:        {tp1}  (take +{tp_pct}% on option)")
        if tp2:    lines.append(f"  Target 2:        {tp2}  🎯 runner")
        if rr:     lines.append(f"  Risk/Reward:     {rr}")
        if maxhold: lines.append(f"  Max Hold Time:   {maxhold}")
        lines.append("")

        if trade.get("reasoning"):
            lines.append(f"  WHY:      {trade['reasoning']}")
        if trade.get("exit_conditions"):
            lines.append(f"  EXIT IF:  {trade['exit_conditions']}")
        lines.append("")

    # ── Indicators
    ind = analysis.get("indicators", {})
    ind_parts = []
    if ind.get("rsi"):
        rsi_flag = " ⚠️ OB" if ind.get("rsi_signal") == "overbought" else \
                   " ⚠️ OS" if ind.get("rsi_signal") == "oversold" else ""
        ind_parts.append(f"RSI {ind['rsi']}{rsi_flag}")
    if ind.get("macd"):
        ind_parts.append(f"MACD {ind['macd'].replace('_', ' ')}")
    if ind.get("volume"):
        ind_parts.append(f"Vol {ind['volume'].replace('_', ' ')}")
    if ind.get("price_vs_ema"):
        ind_parts.append(f"EMA {ind['price_vs_ema'].replace('_', ' ')}")
    if ind_parts:
        lines.append("  " + "  ·  ".join(ind_parts))
        lines.append("")

    # ── Patterns
    pat = analysis.get("patterns", {})
    if pat.get("trend"):
        lines.append(f"  Trend:      {pat['trend'].replace('_', ' ')}")
    if pat.get("chart_pattern") and pat["chart_pattern"] != "none":
        lines.append(f"  Setup:      {pat['chart_pattern'].replace('_', ' ')}")
    if pat.get("support_levels"):
        lines.append(f"  Support:    {pat['support_levels']}")
    if pat.get("resistance_levels"):
        lines.append(f"  Resistance: {pat['resistance_levels']}")
    lines.append("")

    # ── Risk factors
    risks = analysis.get("risk_factors", [])
    if risks:
        lines.append("  ⚠️  RISKS:")
        for r in risks:
            lines.append(f"     • {r}")
        lines.append("")

    # ── Alerts
    alerts = analysis.get("alerts", [])
    if alerts:
        lines.append("  🚨 ALERTS:")
        for a in alerts:
            lines.append(f"     • {a}")
        lines.append("")

    # ── Coach summary
    if analysis.get("summary"):
        lines.append("━" * 48)
        lines.append("  🗣️  COACH SAYS:")
        lines.append(f"  {analysis['summary']}")
        lines.append("━" * 48)

    return "\n".join(lines)


def format_premarket_briefing(briefing: dict) -> str:
    """Format the pre-market multi-timeframe briefing into a clean readable output."""
    lines = []
    now = datetime.now().strftime("%I:%M %p")

    bias = briefing.get("htf_bias", "NEUTRAL")
    bias_emoji = {
        "STRONGLY_BULLISH": "🟢🟢 STRONGLY BULLISH",
        "BULLISH":          "🟢 BULLISH",
        "NEUTRAL":          "⬜ NEUTRAL",
        "BEARISH":          "🔴 BEARISH",
        "STRONGLY_BEARISH": "🔴🔴 STRONGLY BEARISH",
    }.get(bias, bias)

    lines.append("╔" + "═" * 48 + "╗")
    lines.append(f"║   📊  PRE-MARKET BRIEFING  —  {now:<16}║")
    lines.append("╚" + "═" * 48 + "╝")
    lines.append("")
    lines.append(f"  HTF BIAS:  {bias_emoji}")
    if briefing.get("htf_reasoning"):
        lines.append(f"  {briefing['htf_reasoning']}")
    lines.append("")

    # Key levels
    kl = briefing.get("key_levels", {})
    if kl:
        lines.append("  ── KEY LEVELS ────────────────────────")
        if kl.get("previous_day_high"):
            lines.append(f"  PDH: {kl['previous_day_high']}   PDL: {kl.get('previous_day_low','—')}")
        if kl.get("weekly_high"):
            lines.append(f"  WHH: {kl['weekly_high']}   WHL: {kl.get('weekly_low','—')}")
        if kl.get("premarket_high"):
            lines.append(f"  PMH: {kl['premarket_high']}   PML: {kl.get('premarket_low','—')}")
        if kl.get("major_resistance"):
            lines.append(f"  Resistance: {kl['major_resistance']}")
        if kl.get("major_support"):
            lines.append(f"  Support:    {kl['major_support']}")
        lines.append("")

    # Liquidity pools
    lp = briefing.get("liquidity_pools", {})
    if lp:
        lines.append("  ── LIQUIDITY POOLS ───────────────────")
        if lp.get("buy_side_liquidity"):
            lines.append(f"  🔵 Buy-side (above):  {lp['buy_side_liquidity']}")
        if lp.get("sell_side_liquidity"):
            lines.append(f"  🔴 Sell-side (below): {lp['sell_side_liquidity']}")
        most_likely = lp.get("most_likely_swept_first", "")
        target      = lp.get("sweep_target")
        if most_likely:
            arrow = "↑" if most_likely == "buy_side" else "↓"
            lines.append(f"  {arrow} LIKELY FIRST SWEEP: {most_likely.replace('_',' ').upper()} @ {target or '?'}")
        lines.append("")

    # Order blocks
    obs = briefing.get("order_blocks", [])
    if obs:
        lines.append("  ── ORDER BLOCKS ──────────────────────")
        for ob in obs[:4]:
            ob_emoji = "🟦" if ob.get("type") == "bullish" else "🟥"
            lines.append(f"  {ob_emoji} [{ob.get('timeframe','?')}] {ob.get('type','').upper()} OB @ {ob.get('level','?')}")
            if ob.get("description"):
                lines.append(f"     → {ob['description']}")
        lines.append("")

    # Fair Value Gaps
    fvgs = briefing.get("fair_value_gaps", [])
    open_fvgs = [f for f in fvgs if not f.get("filled")]
    if open_fvgs:
        lines.append("  ── OPEN FAIR VALUE GAPS ──────────────")
        for fvg in open_fvgs[:4]:
            fvg_emoji = "📈" if fvg.get("type") == "bullish" else "📉"
            lines.append(f"  {fvg_emoji} [{fvg.get('timeframe','?')}] {fvg.get('type','').upper()} FVG  {fvg.get('range','?')}")
            if fvg.get("notes"):
                lines.append(f"     → {fvg['notes']}")
        lines.append("")

    # Morning scenarios
    sc = briefing.get("morning_scenarios", {})
    sa = sc.get("scenario_a", {})
    sb = sc.get("scenario_b", {})

    if sa:
        play_emoji = "📈" if sa.get("play") == "BUY_CALLS" else "📉"
        prob_color = "⭐⭐⭐" if sa.get("probability") == "HIGH" else "⭐⭐" if sa.get("probability") == "MEDIUM" else "⭐"
        lines.append(f"  ── SCENARIO A  {prob_color} ──────────────────")
        lines.append(f"  {play_emoji}  {sa.get('name','')}")
        lines.append(f"  Trigger:  {sa.get('trigger','')}")
        lines.append(f"  Play:     {sa.get('play','').replace('_',' ')}  entry {sa.get('entry_zone','?')}  → target {sa.get('target','?')}")
        lines.append(f"  Stop:     {sa.get('stop','?')}")
        if sa.get("notes"):
            lines.append(f"  SMC:      {sa['notes']}")
        lines.append("")

    if sb:
        play_emoji = "📈" if sb.get("play") == "BUY_CALLS" else "📉"
        prob_color = "⭐⭐⭐" if sb.get("probability") == "HIGH" else "⭐⭐" if sb.get("probability") == "MEDIUM" else "⭐"
        lines.append(f"  ── SCENARIO B  {prob_color} ──────────────────")
        lines.append(f"  {play_emoji}  {sb.get('name','')}")
        lines.append(f"  Trigger:  {sb.get('trigger','')}")
        lines.append(f"  Play:     {sb.get('play','').replace('_',' ')}  entry {sb.get('entry_zone','?')}  → target {sb.get('target','?')}")
        lines.append(f"  Stop:     {sb.get('stop','?')}")
        if sb.get("notes"):
            lines.append(f"  SMC:      {sb['notes']}")
        lines.append("")

    # Watch list
    watches = briefing.get("watch_list", [])
    if watches:
        lines.append("  ── WATCH FOR ─────────────────────────")
        for w in watches:
            lines.append(f"  👁  {w}")
        lines.append("")

    # Invalidation
    inv = briefing.get("invalidation", {})
    if inv:
        if inv.get("bullish_invalidated_if"):
            lines.append(f"  🟢 Bullish killed if: {inv['bullish_invalidated_if']}")
        if inv.get("bearish_invalidated_if"):
            lines.append(f"  🔴 Bearish killed if: {inv['bearish_invalidated_if']}")
        lines.append("")

    # Game plan
    if briefing.get("session_plan"):
        lines.append("╔" + "═" * 48 + "╗")
        lines.append("║   🗣️  MORNING GAME PLAN                 ║")
        lines.append("╚" + "═" * 48 + "╝")
        lines.append(f"  {briefing['session_plan']}")
        lines.append("═" * 50)

    return "\n".join(lines)
