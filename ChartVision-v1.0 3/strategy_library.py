"""
Strategy Library — teach the AI new trading strategies.

Each strategy is stored as a JSON file in the strategies/ folder.
The active strategy's rules are injected into every chart analysis prompt.

Built-in strategies (not files, always available):
  - ICT/SMC  :  The 5-step ICT Smart Money sequence (default)
  - ORB      :  Opening Range Breakout
  - Supply/Demand : Classic S&D zone entries

User-created strategies are saved in strategies/{id}.json and can be:
  - Created by describing rules in plain English
  - Edited at any time
  - Switched instantly — takes effect on the next analysis
"""

import json
import os
import time
from datetime import datetime

STRATEGIES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategies")
ACTIVE_FILE    = os.path.join(STRATEGIES_DIR, "_active.txt")

# ─── Built-in strategies ───────────────────────────────────────────────────────

BUILTIN_STRATEGIES = {
    "AUTO": {
        "id":          "AUTO",
        "name":        "🤖 Auto-Detect (recommended)",
        "description": "AI reads the chart and automatically picks the best strategy for what it sees. Switches between ICT/SMC, ORB, Supply/Demand, and any custom strategy you've taught it.",
        "builtin":     True,
        "entry_rules": "AUTO — the AI selects entry rules based on chart conditions",
        "exit_rules":  "AUTO — the AI selects exit rules based on chart conditions",
        "indicators_focus": "All — AI decides what to focus on",
        "created_at": "built-in",
    },

    "ICT_SMC": {
        "id":          "ICT_SMC",
        "name":        "ICT / Smart Money (Default)",
        "description": "5-Step ICT/Smart Money Concepts entry sequence — the main strategy I taught you.",
        "builtin":     True,
        "entry_rules": """
Use the full 5-step ICT sequence already built into your analysis:
1. Establish 4H bias (bullish = CALLS only, bearish = PUTS only)
2. Wait for 1H liquidity sweep of the swing high/low
3. Drop to 5-minute chart and mark the structure
4. Confirm 5-minute BOS (candle BODY close, not wick)
5. Enter at the FVG / CE / Order Block after BOS pullback

Entry type priority: FVG with CE > Order Block > iFVG > plain BOS retest
Only enter at DISCOUNT for CALLS, PREMIUM for PUTS.
""",
        "exit_rules": """
- TP1: 50% at the first draw on liquidity (nearest equal high/low or session level)
- TP2: 50% remaining at the second DOL (previous session high/low)
- TP3: Runner with trailing stop at the macro target (daily/weekly level)
- Move stop to breakeven once 1:1 is hit
- HARD STOP: Exit option if it loses 40-50% of premium. Never hold losers.
- TIME STOP: Never hold a 0DTE past 2 PM ET.
""",
        "indicators_focus": "FVG, CE, Order Block, CHoCH, BOS, liquidity sweeps, SMT divergence",
        "created_at": "built-in",
    },

    "ORB": {
        "id":          "ORB",
        "name":        "Opening Range Breakout (ORB)",
        "description": "Trade breakouts above or below the first 5-minute or 15-minute opening range candle.",
        "builtin":     True,
        "entry_rules": """
OPENING RANGE BREAKOUT STRATEGY:

Step 1 — Identify the Opening Range
- The opening range is the HIGH and LOW of the FIRST 5-minute candle (or first 15 minutes, whichever is clearer)
- Mark both the ORB High and ORB Low exactly

Step 2 — Wait for a CONFIRMED BREAKOUT
- Bullish ORB: A 5-minute candle BODY closes ABOVE the ORB High → this is the entry signal
- Bearish ORB: A 5-minute candle BODY closes BELOW the ORB Low → this is the entry signal
- Wicks above/below do NOT count — must be a full body close

Step 3 — Entry
- Enter on the CANDLE THAT BROKE OUT (at the close of that candle) OR
- Wait for a pullback to the ORB High/Low (which now acts as support/resistance) — this is the safer entry
- Do NOT chase — if price is already 1% or more past the breakout, skip it

Step 4 — Confluence filters (must have at least one)
- The breakout direction must match the pre-market trend or gap direction
- Volume must be above average on the breakout candle
- No major news event in the next 30 minutes
- If the first breakout fails (false break), wait for a second breakout in the opposite direction — those are often stronger

Step 5 — Entry on confluence:
- For CALLS: Buy when price reclaims ORB High after a false break, or on the initial breakout candle
- For PUTS: Buy when price breaks below ORB Low cleanly
""",
        "exit_rules": """
- TP1: Equal distance from the breakout as the height of the opening range (1:1 extension)
- TP2: 2x the opening range height from the breakout level (1:2 extension)
- TP3: Previous day's high (bullish) or low (bearish) as the macro target
- Stop loss: Just inside the other side of the opening range (below ORB Low for longs, above ORB High for shorts)
- If price re-enters the opening range → EXIT immediately. A failed ORB becomes a fade setup.
- TIME: Only trade ORB setups from 9:30–10:30 AM ET. After 10:30 the opening range loses significance.
""",
        "indicators_focus": "Opening range high/low, volume on breakout candle, pre-market levels, VWAP",
        "created_at": "built-in",
    },

    "SUPPLY_DEMAND": {
        "id":          "SUPPLY_DEMAND",
        "name":        "Supply & Demand Zones",
        "description": "Trade bounces from fresh supply and demand zones left by strong institutional moves.",
        "builtin":     True,
        "entry_rules": """
SUPPLY & DEMAND ZONE STRATEGY:

Step 1 — Identify fresh Supply and Demand zones
- DEMAND ZONE (buy zone): A price area where a strong BULLISH move originated. Look for:
  * A base (tight consolidation or small candles) followed by a strong up move
  * The zone = the range of the base candles before the impulse
  * Must be FRESH (price has NOT returned to test this zone yet)
- SUPPLY ZONE (sell zone): A price area where a strong BEARISH move originated. Look for:
  * A base followed by a strong down move
  * The zone = the range of the base candles before the drop
  * Must be FRESH (price has NOT returned to test this zone yet)

Step 2 — Wait for price to RETURN to the zone
- Only enter when price comes back to test the zone for the FIRST TIME
- Second or third tests are weaker — treat with caution
- Price must approach the zone, NOT already be in the middle of it

Step 3 — Entry confirmation
- Look for a REACTION CANDLE at the zone boundary:
  * At a demand zone: a bullish pin bar, hammer, or engulfing candle → entry
  * At a supply zone: a bearish pin bar, shooting star, or bearish engulfing → entry
- If price moves through the zone without reacting → DO NOT ENTER. The zone is broken.

Step 4 — Timeframe alignment
- Use 4H or Daily chart to identify the big zones
- Use 15m or 5m chart to time the exact entry
- Only enter if the higher timeframe trend supports the direction
""",
        "exit_rules": """
- TP1: The nearest supply zone above (for longs) or demand zone below (for shorts)
- TP2: The next major supply/demand zone or previous significant high/low
- Stop loss: Just BELOW the bottom of a demand zone (for longs) or just ABOVE the top of a supply zone (for shorts)
- If price fully closes below the demand zone → the zone is broken, exit immediately
- Trail stop to lock in profits as each zone is cleared
""",
        "indicators_focus": "Supply zones, demand zones, reaction candles at zone boundaries, zone freshness, timeframe alignment",
        "created_at": "built-in",
    },

    "VWAP_REVERSAL": {
        "id":          "VWAP_REVERSAL",
        "name":        "VWAP Reversal / Reclaim",
        "description": "Trade bounces and rejections at VWAP with volume confirmation. VWAP acts as dynamic intraday support/resistance — first test is the best entry.",
        "builtin":     True,
        "entry_rules": """
VWAP REVERSAL STRATEGY:

What is VWAP? The Volume Weighted Average Price — it is the most important intraday level. Institutions use it as a benchmark. Price above VWAP = bullish intraday tone. Price below VWAP = bearish intraday tone.

LONG SETUP (VWAP Reclaim / Bounce):
1. Price gaps up with catalyst OR trends up in first 15-30 min of session
2. Price pulls back and touches VWAP from ABOVE
3. Entry trigger: Bullish reversal candle at VWAP — hammer, pin bar, or bullish engulfing
4. MUST have volume spike on the bounce candle — no volume = no institutional support
5. Enter on close of the confirmation candle
6. KEY RULE: The FIRST touch of VWAP is the best entry. The 2nd and 3rd tests are progressively weaker.
7. Daily chart must be bullish — only trade long VWAP bounces when daily trend is up

SHORT SETUP (VWAP Rejection):
1. Price trends down, then attempts to bounce and reclaim VWAP from below
2. Price touches VWAP from BELOW but fails to close above it
3. Entry trigger: Bearish reversal candle at VWAP — shooting star, bearish engulfing, or pin bar with upper wick
4. Volume should spike on the rejection candle
5. Enter on close of the rejection candle
6. Daily chart must be bearish — only trade short VWAP rejections when daily trend is down

BONUS — VWAP DEVIATION BANDS:
- If visible, look for price at +1 or -1 standard deviation from VWAP (VWAP bands)
- Price at -1 SD in uptrend = extremely strong buy zone
- Price at +1 SD in downtrend = extremely strong sell zone

DO NOT TRADE:
- If price has crossed VWAP 3+ times already that session (choppy, no directional conviction)
- If volume is very low (lunch hour or end of day without catalyst)
- Against the daily trend direction
""",
        "exit_rules": """
- TP1: Previous session swing high (for longs) or swing low (for shorts) — this is the main target
- TP2: Daily high/low or major resistance/support beyond the swing
- Stop loss (longs): Just below VWAP AND below the low of the entry candle
- Stop loss (shorts): Just above VWAP AND above the high of the entry candle
- If price closes back through VWAP in the wrong direction → exit immediately. VWAP is broken.
- Trail stop: Once trade moves 1:1, move stop to breakeven
- Time stop: If price doesn't move favorably within 10-15 minutes after entry, exit — VWAP trades should work quickly
""",
        "indicators_focus": "VWAP (mandatory), VWAP standard deviation bands if visible, volume spikes, daily chart trend, reversal candles at VWAP",
        "created_at": "built-in",
    },

    "WYCKOFF": {
        "id":          "WYCKOFF",
        "name":        "Wyckoff Method (Spring / Upthrust)",
        "description": "Identify institutional accumulation and distribution phases. Trade the Spring (fake breakdown that reverses up) and Upthrust After Distribution (fake breakout that reverses down).",
        "builtin":     True,
        "entry_rules": """
WYCKOFF METHOD — SPRING AND UPTHRUST ENTRIES:

PART 1: ACCUMULATION (look for a BUY setup)

What does accumulation look like?
- Price has been in a sideways TRADING RANGE for an extended time (weeks/months)
- The range has a clear SUPPORT floor and RESISTANCE ceiling
- Volume is contracting as the range develops (institutions quietly buying on dips)

THE SPRING (most powerful Wyckoff buy signal):
1. Price has been consolidating in a range with established support
2. Price breaks DECISIVELY BELOW the support level (this is the "spring" — a shakeout)
3. The spring should CLOSE BACK ABOVE the broken support within the same candle or next 1-2 candles
4. Spring candle typically has: long lower wick, closes back in the range, high volume on the break
5. ENTRY: Buy on the close of the first candle that recovers back above support OR on the first pullback to the spring level (which now acts as support)
6. Confirmation: Next candle should show a "Sign of Strength" (SOS) — a strong up candle on high volume

PART 2: DISTRIBUTION (look for a SELL setup)

What does distribution look like?
- Price has been in a sideways range near a MAJOR HIGH (extended uptrend)
- Volume is contracting as the range develops (institutions quietly selling into strength)

UPTHRUST AFTER DISTRIBUTION (UTAD):
1. Price has been consolidating below resistance for an extended time
2. Price breaks ABOVE resistance briefly on lower-than-expected volume
3. The upthrust CLOSES BACK BELOW the resistance within 1-3 candles
4. This is a "bull trap" — retail buyers chase the breakout, institutions sell into them
5. ENTRY: Short when price closes back below resistance OR on the pullback up to the failed breakout level
6. Confirmation: A "Sign of Weakness" (SOW) — price breaks below recent support on high volume

KEY WYCKOFF LEVELS TO IDENTIFY ON CHART:
- Trading range HIGH (resistance ceiling)
- Trading range LOW (support floor)
- PS (Preliminary Supply/Support) — first major reaction at range extreme
- SC (Selling Climax / Buying Climax) — panic volume at range extreme
- AR (Automatic Rally/Reaction) — first bounce from range extreme
""",
        "exit_rules": """
SPRING (long) exits:
- TP1: The midpoint of the trading range
- TP2: The top of the trading range (resistance ceiling)
- TP3: A measured move target = height of the range added above the breakout
- Stop loss: Just below the LOWEST point of the spring wick (if price returns here, the spring is a failure)
- If price cannot hold above the support it sprang from within 3-5 candles → exit, it's a failed spring

UPTHRUST (short) exits:
- TP1: The midpoint of the trading range
- TP2: The bottom of the trading range (support floor)
- TP3: A measured move target = height of the range subtracted from the breakdown
- Stop loss: Just above the highest wick of the upthrust (if price holds above resistance, it's a valid breakout not a fake)
""",
        "indicators_focus": "Trading range boundaries, volume profile (high volume at climax, low volume at tests), Spring/Upthrust candles, Sign of Strength/Weakness candles",
        "created_at": "built-in",
    },

    "FIBONACCI": {
        "id":          "FIBONACCI",
        "name":        "Fibonacci Golden Zone Pullback",
        "description": "Enter trend continuations when price pulls back to the 50%-61.8% Fibonacci golden zone after a strong impulse move.",
        "builtin":     True,
        "entry_rules": """
FIBONACCI GOLDEN ZONE PULLBACK STRATEGY:

SETUP REQUIREMENTS:
1. There must be a clear, strong IMPULSE MOVE in one direction (the trend leg)
2. Price then begins a PULLBACK (counter-trend move) — this is what you wait for
3. Draw Fibonacci retracement from the START of the impulse to the END of the impulse

KEY FIBONACCI LEVELS:
- 0.382 (38.2%) — shallow pullback zone, entry only if strong momentum exists
- 0.500 (50.0%) — moderate pullback, often good entry
- 0.618 (61.8%) — GOLDEN ZONE — strongest and most reliable entry level
- THE GOLDEN ZONE = between 50% and 61.8% — this is the highest probability area

ENTRY RULES (step by step):
1. Identify a clear trend move — must be at least 2-3 strong candles in one direction
2. Draw fib retracement: for uptrend, draw from swing LOW to swing HIGH. For downtrend, draw from swing HIGH to swing LOW.
3. Wait for price to PULL BACK into the golden zone (50%-61.8%)
4. Look for a REVERSAL CONFIRMATION CANDLE at the fib level:
   - Pin bar / hammer at 61.8% in an uptrend = high probability long
   - Shooting star / bearish engulfing at 61.8% in a downtrend = high probability short
5. CONFLUENCE REQUIREMENT — the fib level must align with at least ONE other factor:
   - Prior support/resistance at the same level
   - VWAP or EMA (9/21/50) at the same price
   - FVG or Order Block at the same level (very powerful combo with ICT)
6. Enter on close of the confirmation candle AT the golden zone

DO NOT ENTER if:
- Price blows through the 61.8% level without showing any reaction
- No confluence with other indicators
- The original impulse move was on low volume (weak, unreliable)
- Price has already tested the 61.8% zone 2+ times (losing strength)
""",
        "exit_rules": """
- TP1: The starting point of the pullback (previous high for longs, previous low for shorts) — this is the 0% fib level, known as the "extension 0"
- TP2: The 127.2% fib extension — the first target beyond the original swing high/low
- TP3: The 161.8% fib extension — the measured move target
- Stop loss: Just BEYOND the 61.8% level — if trading from 61.8%, stop goes at the 78.6% level or just below the swing low of the impulse
- Rule: If price fully retraces past the 78.6% level, the original impulse is failing — exit
- Move stop to breakeven once price reaches TP1 (the original swing high/low)
""",
        "indicators_focus": "Fibonacci 50%-61.8% golden zone, reversal candles at fib levels, confluence with S/R, EMA, VWAP, or FVG at same level, volume on impulse vs pullback",
        "created_at": "built-in",
    },

    "JUDAS_SWING": {
        "id":          "JUDAS_SWING",
        "name":        "Judas Swing (London/NY Session Trap)",
        "description": "London or New York session opens with a fake move that sweeps one side of the Asian range, then violently reverses. Trade the reversal after the liquidity grab.",
        "builtin":     True,
        "entry_rules": """
JUDAS SWING / SESSION KILLZONE STRATEGY:

WHAT IS A JUDAS SWING?
At the start of major sessions (especially London and New York open), large institutions create a false move in one direction to grab liquidity (stop-loss orders), then quickly reverse in the TRUE direction. The "Judas" move betrays the retail traders who chased it.

EXACT TIME WINDOWS:
- London Killzone / Judas Swing: 2:00 AM – 5:00 AM EST (best: 2:00–3:00 AM EST)
- New York Killzone: 7:00 AM – 10:00 AM EST (best: 8:30–9:30 AM EST)
- Best day: Tuesday through Thursday (avoid Monday and Friday for this strategy)

STEP-BY-STEP ENTRY RULES:
1. Mark the ASIAN SESSION range: the HIGH and LOW formed while Asian markets were active (roughly 8 PM – 12 AM EST)
2. At the START of the London or NY session, watch for price to move toward and SWEEP one extreme of the Asian range
3. The sweep = price wicks through the Asian HIGH or Asian LOW, grabbing stop-loss orders placed there
4. After the sweep, watch for a MARKET STRUCTURE SHIFT (MSS) with displacement:
   - Strong, fast candle in the OPPOSITE direction of the sweep
   - This candle leaves a FAIR VALUE GAP (FVG) in its wake
5. After the MSS, price often returns to fill the FVG or retest the broken structure — THIS IS YOUR ENTRY
6. Entry: Enter on the pullback to the FVG or Order Block left by the displacement candle

BEARISH JUDAS (short):
- Asian high is swept (buy-side liquidity grabbed)
- Strong displacement candle DOWN, leaving bullish FVG above
- Price returns to that FVG → SELL at the FVG, targeting Asian low or sell-side liquidity below

BULLISH JUDAS (long):
- Asian low is swept (sell-side liquidity grabbed)
- Strong displacement candle UP, leaving bearish FVG below
- Price returns to that FVG → BUY at the FVG, targeting Asian high or buy-side liquidity above

CONFIRMATION FILTERS:
- Sweep should be a WICK through the Asian level, not a full candle close beyond it
- The displacement candle after the sweep must be LARGE relative to recent candles
- Volume should spike on the displacement candle
""",
        "exit_rules": """
- TP1: The opposite side of the Asian session range (Asian HIGH for longs, Asian LOW for shorts)
- TP2: Previous session high/low from prior day
- TP3: Higher timeframe liquidity level (PDH/PDL)
- Stop loss: Just beyond the sweep wick (above the swept high for shorts, below the swept low for longs)
- If price continues past the stop level and closes BEYOND the sweep wick → the Judas move failed, the real direction is the sweep direction. Exit immediately.
- Time rule: If no MSS occurs within 30 minutes of the sweep, the setup is invalid — don't trade it
""",
        "indicators_focus": "Asian session high/low (mark before session), market structure shift after sweep, FVG left by displacement candle, session open times, volume on displacement",
        "created_at": "built-in",
    },

    "GAP_AND_GO": {
        "id":          "GAP_AND_GO",
        "name":        "Gap and Go / Gap Fill",
        "description": "Trade opening gaps — either following the gap direction (Gap and Go) when it breaks pre-market highs, or fading the gap (Gap Fill) when it shows reversal signs.",
        "builtin":     True,
        "entry_rules": """
GAP AND GO STRATEGY:

WHAT IS A GAP? When a stock or index opens significantly higher or lower than the previous close due to overnight news or events.

PART 1 — GAP AND GO (trade WITH the gap direction):

Setup requirements:
- Gap of 0.5% or more from the previous close (larger gaps = stronger moves)
- Must have a CATALYST: earnings, news, macro event, product announcement
- Pre-market volume should be elevated (more than 2x average)

Entry rules:
1. Wait for the FIRST 5-MINUTE CANDLE of the regular session to CLOSE
2. Mark the pre-market HIGH (for gap-ups) or pre-market LOW (for gap-downs)
3. Entry trigger for GAP-UP: First 5-min candle body closes ABOVE the pre-market high → BUY immediately on that close
4. Entry trigger for GAP-DOWN: First 5-min candle body closes BELOW the pre-market low → SELL/BUY PUTS on that close
5. Volume MUST be above average on the breakout candle — no volume = no follow-through
6. Time limit: ONLY enter within the first 15 minutes of open (9:30–9:45 AM ET). After this, the setup loses reliability.

PART 2 — GAP FILL (trade AGAINST the gap direction):

Setup: Gap opens but shows IMMEDIATE weakness or reversal signs
- Gap-up but price immediately makes a lower high than the pre-market high → possible gap fill
- Gap-down but price immediately makes a higher low than the pre-market low → possible gap fill

Entry for gap fill:
1. First 5-minute candle closes back INSIDE the gap (below pre-market high for gap-ups)
2. This is a FAILED GAP — price is likely to fully fill the gap back to prior close
3. Enter in the direction of the fill on the second candle that confirms the reversal

DO NOT TRADE:
- Gaps without a clear catalyst (random overnight gaps)
- If the opening 5-minute candle is excessively wide/volatile (risk too high)
- After 9:45 AM ET for the initial gap-and-go entry
- On the day before or after a major news event (FOMC, CPI, NFP)
""",
        "exit_rules": """
GAP AND GO exits:
- TP1: Round number above/below entry (e.g., the nearest $1 or $5 round number)
- TP2: Previous day's high (for gap-ups) or previous day's low (for gap-downs)
- Trail stop: Once price moves 1% in your favor, move stop to breakeven; trail 0.5% below price
- Hard stop: Below the low of the first 5-minute candle (for longs) or above the high (for shorts)
- Time stop: If price doesn't move favorably within 30 minutes, exit — gap-and-go trades should work fast

GAP FILL exits:
- TP1: 50% of the gap filled (first take-profits)
- TP2: The full gap fill — price returns to prior day's close
- Stop: Above the gap-up high (for short gap fill) or below the gap-down low (for long gap fill)
""",
        "indicators_focus": "Pre-market high/low levels, gap size vs prior close, first 5-minute candle, opening range, volume on first candles, prior day's high/low",
        "created_at": "built-in",
    },

    "EMA_CROSS": {
        "id":          "EMA_CROSS",
        "name":        "9/21 EMA Cross Trend Follow",
        "description": "Follow the trend using 9 EMA and 21 EMA crossovers. Golden cross (9 crosses above 21) = go long. Death cross (9 crosses below 21) = go short.",
        "builtin":     True,
        "entry_rules": """
9/21 EMA CROSS TREND FOLLOWING STRATEGY:

WHAT ARE EMAs?
- 9 EMA = short-term momentum (reacts quickly to price)
- 21 EMA = medium-term trend (smoother, shows direction)
- When 9 EMA > 21 EMA = short-term momentum is up = bullish trend
- When 9 EMA < 21 EMA = short-term momentum is down = bearish trend
- Optional: 55 EMA for additional trend confirmation

LONG ENTRY (GOLDEN CROSS):
1. 9 EMA crosses ABOVE the 21 EMA → this is the golden cross signal
2. Price should be ABOVE both EMAs (not already extended far from them)
3. Optional confirmation: Both 9 EMA and 21 EMA should be above the 55 EMA (if visible)
4. Entry options (choose ONE):
   A) Aggressive: Enter immediately on the candle that closes above the 21 EMA cross
   B) Conservative: Wait for a pullback to the 21 EMA after the cross, enter on a bullish reversal candle at the 21 EMA
5. AVOID entering when EMAs are flat and tangled — only trade when they are clearly separated and sloping

SHORT ENTRY (DEATH CROSS):
1. 9 EMA crosses BELOW the 21 EMA → this is the death cross signal
2. Price should be BELOW both EMAs
3. Optional confirmation: Both 9 EMA and 21 EMA should be below the 55 EMA (if visible)
4. Entry options:
   A) Aggressive: Enter immediately on the candle that closes below the 21 EMA cross
   B) Conservative: Wait for a bounce to the 21 EMA after the cross, enter on a bearish reversal candle at the 21 EMA

BEST TIMEFRAMES:
- 4-hour or daily charts for swing trades
- 1-hour or 15-minute for intraday trend following
- 5-minute for scalping (less reliable, more noise)

DO NOT TRADE:
- When both EMAs are flat/horizontal (choppy, ranging market)
- When price is whipping back and forth through the EMAs repeatedly (avoid for 3-5 candles after the cross)
- Against a strong higher-timeframe trend
""",
        "exit_rules": """
- TP1: Previous swing high (for longs) or previous swing low (for shorts)
- TP2: A measured move equal to the distance from the last EMA cross to entry
- TP3: Major horizontal support/resistance on a higher timeframe
- Stop loss: Just below the 21 EMA (for longs) or just above the 21 EMA (for shorts)
  * Tighter option: Just below the entry candle's low (for longs)
- Trail stop: As price moves in your favor, trail the stop just below the 21 EMA
  * If the 9 EMA crosses back below the 21 EMA (death cross after a long) → EXIT IMMEDIATELY. The trend has reversed.
- Reversal exit rule: ALWAYS exit when the EMAs cross in the opposite direction of your trade
""",
        "indicators_focus": "9 EMA and 21 EMA (mandatory), optional 55 EMA, EMA slope direction, EMA separation width, price position relative to EMAs, volume on the cross candle",
        "created_at": "built-in",
    },

    "BULL_BEAR_FLAG": {
        "id":          "BULL_BEAR_FLAG",
        "name":        "Bull / Bear Flag Pattern",
        "description": "Trade momentum continuation patterns — a sharp impulse (flagpole) followed by a tight consolidation (flag) that breaks out in the trend direction.",
        "builtin":     True,
        "entry_rules": """
BULL FLAG / BEAR FLAG CONTINUATION PATTERN STRATEGY:

WHAT IS A FLAG PATTERN?
A flag is a CONTINUATION pattern — it says the trend paused briefly but is about to continue.
- Bull Flag: Sharp move UP (flagpole), then a tight downward-sloping channel (flag), then breakout UP
- Bear Flag: Sharp move DOWN (flagpole), then a tight upward-sloping channel (flag), then breakout DOWN
Flags are highest probability during strong trending momentum markets.

IDENTIFYING THE BULL FLAG:
1. FLAGPOLE: Look for a strong, fast move up — at least 3-5 consecutive bullish candles, ideally on heavy volume
2. FLAG: Price then consolidates in a tight, gently DOWNWARD-sloping channel (2-7 candles typically)
   - The channel should be NARROW — not a deep retracement. Flag should NOT retrace more than 50% of the flagpole.
   - Volume should CONTRACT during the flag (sellers are weak)
3. BREAKOUT: Entry trigger when a candle closes ABOVE the upper boundary of the flag channel
   - Volume must EXPAND on the breakout candle (confirms institutions are buying)
   - Conservative entry: Wait for a brief pullback to the top of the broken flag channel before entering

IDENTIFYING THE BEAR FLAG:
1. FLAGPOLE: Sharp fast move DOWN — 3-5+ consecutive bearish candles on heavy volume
2. FLAG: Tight, gently UPWARD-sloping channel consolidation (2-7 candles)
   - Volume contracts during the flag
   - Flag should not retrace more than 50% of the flagpole
3. BREAKOUT: Entry trigger when a candle closes BELOW the lower boundary of the flag channel
   - Volume expands on the breakdown candle

INTRADAY TIMING:
- Best on 5-minute or 15-minute charts for day trading
- Most flags form in the first 2 hours of trading (9:30–11:30 AM ET)
- Afternoon flags (1:00–3:00 PM ET) work but need higher-than-average volume to be reliable

CONFLUENCE FILTERS (need at least one):
- Flag breaks out in the same direction as the daily trend
- VWAP is in the direction of the breakout (price above VWAP for bull flags)
- RSI was not overbought (>80) at the top of the flagpole — overextended flags fail more often
- No major resistance within 0.5% of the breakout level
""",
        "exit_rules": """
- TP TARGET: Measure the HEIGHT of the flagpole and project it from the breakout point
  * Example: If flagpole was $2 tall and breakout is at $105, target is $107
  * This is the measured move — the most reliable target for flags
- TP1: 50% of the measured move target (partial profit to lock in gains)
- TP2: Full measured move from breakout
- TP3: If price pauses and forms a second flag (flag-within-flag), ride to the next measured move
- Stop loss: Just below the LOWEST point of the flag (for bull flags) or just above the highest point (for bear flags)
  * If price fully closes back into the flag, the pattern has failed — exit immediately
- Trail stop: Once at TP1, move stop to the breakout level (your entry)
- Invalidation: If the flag retraces more than 61.8% of the flagpole before breaking out, it is no longer a flag — exit
""",
        "indicators_focus": "Flagpole size and angle, flag channel boundaries, volume contraction during flag / volume expansion on breakout, RSI (should not be >80 at flagpole top for bulls), VWAP alignment with flag direction",
        "created_at": "built-in",
    },

    "RSI_DIVERGENCE": {
        "id":          "RSI_DIVERGENCE",
        "name":        "RSI Divergence (Regular + Hidden)",
        "description": "Trade reversals and trend continuations using RSI divergence. Regular divergence signals reversals; hidden divergence signals trend continuation.",
        "builtin":     True,
        "entry_rules": """
RSI DIVERGENCE STRATEGY:

WHAT IS DIVERGENCE?
Divergence occurs when PRICE and RSI move in OPPOSITE directions — a warning that the current trend is weakening (regular) or confirming the trend will continue (hidden).

RSI SETTINGS: Use 14-period RSI. Key levels: 70 (overbought), 30 (oversold), 50 (mid-line).

─── PART 1: REGULAR DIVERGENCE (REVERSAL SIGNALS) ───

REGULAR BULLISH DIVERGENCE (expect price to REVERSE UP):
- PRICE makes a LOWER LOW (downtrend in place)
- RSI makes a HIGHER LOW at the same time
- This means: price is still falling but momentum is weakening — a bottom may be near
- Entry trigger: Look for a bullish reversal candle (hammer, pin bar, engulfing) at the divergence low
  PLUS at least one of: RSI crossing back above 30, candle closes above a recent support, bullish engulfing on 5m chart
- Best confluence: RSI divergence happening AT a key support level, FVG, or demand zone

REGULAR BEARISH DIVERGENCE (expect price to REVERSE DOWN):
- PRICE makes a HIGHER HIGH (uptrend in place)
- RSI makes a LOWER HIGH at the same time
- This means: price is still rising but momentum is fading — a top may be near
- Entry trigger: Bearish reversal candle at the divergence high PLUS RSI below 70 and starting to roll over
- Best confluence: Divergence happening AT a key resistance level, supply zone, or FVG

─── PART 2: HIDDEN DIVERGENCE (TREND CONTINUATION SIGNALS) ───

HIDDEN BULLISH DIVERGENCE (CONTINUE UPTREND — BUY the dip):
- PRICE makes a HIGHER LOW (uptrend is intact — this is a pullback in an uptrend)
- RSI makes a LOWER LOW during the same pullback
- This means: the pullback looks deeper on RSI but price is still making higher lows — BIG MONEY is buying the dip
- Entry: Buy at the hidden divergence level — this is a high-probability pullback entry in an uptrend
- Must confirm: Price is still above the 21 EMA or VWAP (uptrend confirmation)

HIDDEN BEARISH DIVERGENCE (CONTINUE DOWNTREND — SELL the bounce):
- PRICE makes a LOWER HIGH (downtrend is intact — this is a bounce in a downtrend)
- RSI makes a HIGHER HIGH during the same bounce
- This means: RSI shows strength but price can't make higher highs — the bounce is fake
- Entry: Short at the hidden bearish divergence level during a bounce in a downtrend
- Must confirm: Price is still below the 21 EMA or VWAP (downtrend confirmation)

─── ENTRY TIMING ───
- NEVER enter on divergence alone — always wait for a CONFIRMATION CANDLE:
  * Bullish: Pin bar, hammer, morning star, bullish engulfing candle
  * Bearish: Shooting star, evening star, bearish engulfing candle
- The confirmation candle must close in the direction of your trade
- Best on 5-minute for intraday, 15-minute for swing

DO NOT TRADE:
- In choppy, low-volatility sideways markets (divergence signals are unreliable)
- If RSI divergence spans less than 5 candles (too small to be meaningful)
- During major news events (FOMC, CPI, NFP) — momentum crushes divergence signals
""",
        "exit_rules": """
REGULAR DIVERGENCE exits (reversal trades):
- TP1: The most recent swing high (bullish) or swing low (bearish) between the two divergence points
- TP2: The starting point of the divergence leg (where price began its lower lows / higher highs)
- TP3: A key higher timeframe level (daily high/low, major S/R)
- Stop loss: Just beyond the DIVERGENCE EXTREME (below the lower low for bullish divergence, above the higher high for bearish divergence)
  * If a new extreme forms, the divergence is invalidated — exit

HIDDEN DIVERGENCE exits (continuation trades):
- TP1: The most recent swing high of the trend (for longs) or swing low (for shorts)
- TP2: Measured move from the pullback = height of the prior impulse added from the hidden divergence low
- Stop loss: Below the hidden divergence pivot low (for longs) or above the pivot high (for shorts)
  * If price closes below this level, the trend structure is broken — the hidden divergence failed

UNIVERSAL RULES:
- RSI crosses back to the opposite extreme (overbought after bearish div = exit)
- Exit if a new divergence forms in the opposite direction
- TIME STOP: If trade doesn't move within 10-15 candles, close it — divergence signals have expiry
""",
        "indicators_focus": "RSI (14-period, mandatory), RSI overbought (70) / oversold (30) levels, RSI 50 mid-line, candlestick confirmation patterns at divergence points, alignment with support/resistance or supply/demand zones",
        "created_at": "built-in",
    },

    "BB_SQUEEZE": {
        "id":          "BB_SQUEEZE",
        "name":        "Bollinger Band Squeeze Breakout",
        "description": "Trade explosive breakouts when Bollinger Bands squeeze together (low volatility coiling), signaling an imminent high-volatility expansion move.",
        "builtin":     True,
        "entry_rules": """
BOLLINGER BAND SQUEEZE BREAKOUT STRATEGY:

WHAT IS A SQUEEZE?
Bollinger Bands (BB) expand during high volatility and CONTRACT during low volatility. When the bands are very close together (narrower than normal), it means volatility has compressed and energy is coiling — an explosive move is coming. You trade the BREAKOUT direction.

BB SETTINGS: 20-period SMA, 2 standard deviations (default). Optional: add Keltner Channels — when BB is inside KC, that is the classic "squeeze" signal.

IDENTIFYING THE SQUEEZE:
1. The upper and lower BB bands are MUCH CLOSER together than their recent average width
   - Look for the band width at a 20-30+ bar low (narrowest it's been in months)
   - Visually: the bands look "pinched" and price is moving in a tight, flat range
2. Price is consolidating with small, indecisive candles (dojis, small inside bars)
3. Volume has been DECLINING as the squeeze forms (calm before the storm)

ENTRY RULES — after confirming the squeeze:
1. Wait for the BREAKOUT CANDLE:
   - Bullish breakout: A candle's body closes ABOVE the upper Bollinger Band
   - Bearish breakout: A candle's body closes BELOW the lower Bollinger Band
2. VOLUME CONFIRMATION (mandatory):
   - The breakout candle must have SIGNIFICANTLY higher volume than the recent average (2x+ preferred)
   - A breakout on low volume is a false breakout — wait or skip
3. DIRECTION BIAS (use one of these to determine which way to trade):
   - If price was trending UP before the squeeze → bias is bullish (wait for upside breakout)
   - If price was trending DOWN → bias is bearish (wait for downside breakout)
   - If trending neutral/flat → trade whichever side breaks first with volume
4. Optional MACD confirmation: If MACD histogram is expanding in the breakout direction, that adds confidence
5. Conservative entry: Wait for a brief pullback to the BROKEN band after the initial breakout candle
   - The broken upper BB often becomes support on the first pullback (for bullish breakouts)

INTRADAY TIMING:
- Squeezes that form overnight (pre-market) and break out at 9:30 AM open are extremely powerful
- 15-minute chart squeezes are the most reliable for day trading
- Avoid entering squeezes that have already been running for 5+ candles post-breakout (chase risk)

CAUTION — FALSE BREAKOUTS:
- If price breaks out but IMMEDIATELY reverses back inside the bands within 1-2 candles → FALSE BREAKOUT, exit
- False breakouts on low volume are common — volume is the most important filter
""",
        "exit_rules": """
- TP TARGET (measured move): Width of the BB at the widest recent point = the expected move after the squeeze resolves
  * Project this distance from the breakout point in the breakout direction
  * This gives the first major target (TP1)
- TP1: 50% at the measured move target
- TP2: Previous significant high (bullish) or low (bearish) OR the next major support/resistance
- TP3: If bands continue expanding rapidly, trail the stop below the 20-period middle band (SMA)
- Stop loss: Just inside the opposite BB band — below the lower band for long breakouts, above upper band for short
  * Tighter option: Below the middle band (20 SMA)
- If price re-enters the bands after breakout and CLOSES back inside → exit immediately. The squeeze failed.
- TRAIL STOP: Once TP1 is hit, trail stop to the middle BB band (20 SMA). Exit when price closes below it (for longs) or above it (for shorts).
""",
        "indicators_focus": "Bollinger Bands width (squeeze identification), upper/lower band as breakout levels, middle band (20 SMA) as trailing support/resistance, volume on breakout candle (must be elevated), MACD histogram direction for bias confirmation",
        "created_at": "built-in",
    },

    "MACD_DIVERGENCE": {
        "id":          "MACD_DIVERGENCE",
        "name":        "MACD Crossover + Divergence",
        "description": "Trade trend direction changes using MACD line crossovers AND MACD histogram divergence. Crossovers confirm trend shifts; divergence signals early reversals.",
        "builtin":     True,
        "entry_rules": """
MACD CROSSOVER AND DIVERGENCE STRATEGY:

WHAT IS MACD?
- MACD Line = 12 EMA minus 26 EMA (the faster line)
- Signal Line = 9 EMA of the MACD line (the slower line)
- Histogram = MACD Line minus Signal Line (shows momentum strength visually)
- MACD Settings: Default 12/26/9. For faster intraday signals, use 6/13/5.
- Zero line: MACD above zero = bullish momentum regime. Below zero = bearish.

─── PART 1: MACD CROSSOVER (TREND-FOLLOWING SIGNAL) ───

BULLISH CROSSOVER (BUY signal):
1. MACD line crosses ABOVE the signal line — histogram turns positive (green bars appear)
2. Best when: the crossover happens BELOW the zero line (coming from oversold territory) — this is the strongest signal
3. Confirmation: The histogram bars must be GROWING (not shrinking) after the crossover
4. Entry: Buy on the close of the crossover candle OR wait for a pullback to the signal line (tighter entry)
5. Filter: ONLY take the signal if it aligns with the DAILY trend direction (daily MACD above zero for longs)

BEARISH CROSSOVER (SHORT/PUTS signal):
1. MACD line crosses BELOW the signal line — histogram turns negative (red bars)
2. Best when: crossover happens ABOVE the zero line (overbought territory)
3. Confirmation: Histogram bars must be growing in the negative direction after the cross
4. Entry: Short on the close of the crossover candle OR wait for a bounce back to the signal line

─── PART 2: MACD DIVERGENCE (EARLY REVERSAL SIGNAL) ───

BULLISH MACD DIVERGENCE (price going down but MACD rising = reversal coming UP):
- Price forms a lower low
- MACD histogram forms a higher low OR MACD line forms a higher low
- Entry trigger: MACD crossover (MACD crosses above signal) AFTER the divergence is confirmed
  * The crossover after a bullish divergence is extremely high probability
- Enter on the CROSSOVER candle close after the divergence is clear

BEARISH MACD DIVERGENCE (price going up but MACD declining = reversal coming DOWN):
- Price forms a higher high
- MACD histogram forms a lower high OR MACD line forms a lower high
- Entry trigger: MACD bearish crossover (MACD crosses below signal) after the divergence
- Enter on the crossover candle close

─── MULTI-TIMEFRAME RULE ───
- Check MACD on BOTH the higher timeframe (1H or 4H) and lower timeframe (5m or 15m)
- ONLY enter when BOTH timeframes show alignment:
  * 1H MACD bullish crossover + 5M MACD bullish crossover = very strong long signal
  * Any conflicting signals = skip the trade

AVOID:
- Choppy, sideways markets (MACD whipsaws constantly in flat markets)
- Taking every single crossover — only trade the ones with histogram confirmation AND multi-timeframe alignment
- Crossovers that happen right at the zero line in flat markets
""",
        "exit_rules": """
CROSSOVER EXITS:
- TP1: Previous swing high (long) or swing low (short)
- TP2: Major resistance/support on higher timeframe
- Stop loss: Just below the swing low that formed before the bullish crossover (or above swing high for shorts)
  * Tighter: Just below the 26 EMA
- EXIT SIGNAL: MACD makes a BEARISH crossover (line crosses back below signal) → exit long immediately
  * Do not wait for stop — the MACD reversal crossover IS the exit signal

DIVERGENCE EXITS:
- TP1: The most recent swing high/low BETWEEN the two divergence points
- TP2: The starting point of the divergence move (where the divergence leg began)
- Stop: Just beyond the divergence extreme (below the lower low for bullish divergence)
- Histogram rule: If histogram momentum starts shrinking before hitting TP → consider partial exit

UNIVERSAL:
- If MACD histogram starts shrinking consistently (bars getting shorter) while in trade → scale out or tighten stop
- Always move stop to breakeven at 1:1 R:R
- TIME STOP: MACD trades should move within 15-20 candles — if no movement, close
""",
        "indicators_focus": "MACD line (12/26 default or 6/13 fast), signal line (9 period), MACD histogram (bars must be growing to confirm), zero line crossings, alignment between two timeframes",
        "created_at": "built-in",
    },

    "DOUBLE_TOP_BOTTOM": {
        "id":          "DOUBLE_TOP_BOTTOM",
        "name":        "Double Top / Double Bottom",
        "description": "Trade classic reversal patterns at key levels. Double Top (M-shape) signals a bearish reversal; Double Bottom (W-shape) signals a bullish reversal.",
        "builtin":     True,
        "entry_rules": """
DOUBLE TOP / DOUBLE BOTTOM REVERSAL PATTERN STRATEGY:

WHAT ARE THEY?
- Double Top (M shape): Forms after a strong uptrend. Price hits a high, pulls back, rallies to the SAME high again but can't break it, then falls. Classic bearish reversal signal.
- Double Bottom (W shape): Forms after a strong downtrend. Price hits a low, bounces, falls to the SAME low again but holds, then rallies. Classic bullish reversal signal.

─── DOUBLE BOTTOM (W-shape — BULLISH REVERSAL, BUY CALLS) ───

Step 1 — Identify the W pattern:
- Price must be in a DOWNTREND before the pattern (context: prior selling)
- First bottom: price hits a significant low, then bounces (the left side of the W)
- Neckline: the high reached BETWEEN the two bottoms — this is the critical level
- Second bottom: price falls back toward the first bottom level (within 3-5% of it) and bounces AGAIN
- The two lows should be at approximately the SAME price level (within 1-3%)
- Volume: should be HIGHER on the second bottom bounce than on the first (confirms accumulation)

Step 2 — Entry (two options, choose based on risk tolerance):
- AGGRESSIVE ENTRY: Enter long on a bullish reversal candle at the second bottom (hammer, pin bar, engulfing)
  * Pro: Better entry price. Con: Pattern not yet confirmed.
- CONSERVATIVE ENTRY (preferred): Wait for price to break ABOVE the neckline (the high between the two bottoms)
  * Enter on the CLOSE above the neckline, or on a pullback to the neckline after it breaks
  * Pro: Pattern is confirmed. Con: Slightly worse price.
- Volume MUST EXPAND on the neckline breakout candle (this confirms the pattern)

─── DOUBLE TOP (M-shape — BEARISH REVERSAL, BUY PUTS) ───

Step 1 — Identify the M pattern:
- Price must be in an UPTREND before the pattern
- First top: price hits a significant high, pulls back
- Neckline: the LOW reached BETWEEN the two tops
- Second top: price rallies back to the FIRST HIGH (within 1-3%) but FAILS to break higher
- The two highs must be at approximately the same level
- Volume: often LOWER on the second top (sellers gaining control)

Step 2 — Entry (two options):
- AGGRESSIVE: Short on a bearish reversal candle at the second top
- CONSERVATIVE (preferred): Wait for price to close BELOW the neckline
  * Enter on the neckline break or on a pullback/retest of the neckline from below
  * Volume must expand on the breakdown

CONFIRMATIONS TO ADD CONFIDENCE:
- RSI showing divergence at the second top/bottom (even stronger signal)
- MACD making a bearish/bullish crossover near the second top/bottom
- Pattern forms near a major support/resistance level
- Pattern on daily or 4H chart (more significant than 5M)
""",
        "exit_rules": """
MEASURED MOVE TARGET (most important):
- Measure the HEIGHT of the pattern = distance from the neckline to the tops/bottoms
- Project this height FROM the neckline breakout in the trade direction
- Example: Double bottom neckline at $100, bottoms at $90 → pattern height = $10 → TP target = $110

- TP1: 50% of the measured move (first partial take-profit)
- TP2: Full measured move from neckline
- TP3: Next major support/resistance beyond the measured move
- Stop loss (conservative entry): Just above the second top (for double top shorts) or just below the second bottom (for double bottom longs)
- Stop loss (aggressive entry at the bottom): Below the second bottom low (for longs) or above the second top high (for shorts)
- INVALIDATION: If price breaks back through the second top/bottom = the pattern failed. EXIT IMMEDIATELY.
  * For double bottom: if price closes below both bottoms, exit. The downtrend is continuing.
  * For double top: if price closes above both tops, exit. The uptrend is continuing.
""",
        "indicators_focus": "Neckline level (critical — draw it), two tops or two bottoms at equal price levels, volume (must expand on neckline break), RSI divergence at second top/bottom for extra confirmation, MACD crossover near second peak/trough",
        "created_at": "built-in",
    },

    "HEAD_SHOULDERS": {
        "id":          "HEAD_SHOULDERS",
        "name":        "Head & Shoulders (H&S / Inverse H&S)",
        "description": "Trade the most reliable reversal pattern in technical analysis. Regular H&S at market tops signals bearish reversal; Inverse H&S at bottoms signals bullish reversal.",
        "builtin":     True,
        "entry_rules": """
HEAD & SHOULDERS REVERSAL PATTERN STRATEGY:

WHAT IS IT?
- Head & Shoulders (H&S): Forms at a market TOP. Three peaks — left shoulder (high), head (highest high), right shoulder (lower high) — with a neckline connecting the two troughs. Classic bearish reversal.
- Inverse H&S (iH&S): Forms at a market BOTTOM. Three troughs — left shoulder (low), head (lowest low), right shoulder (higher low) — with a neckline connecting the two peaks. Classic bullish reversal.

─── REGULAR HEAD & SHOULDERS (TOP — BEARISH, BUY PUTS) ───

Pattern identification:
1. Left Shoulder: Price rallies to a high (LS high), then pulls back to form a trough
2. Head: Price rallies ABOVE the left shoulder high (makes a higher high = the head), then pulls back again
3. Right Shoulder: Price rallies AGAIN but only gets to approximately the LEFT SHOULDER height (NOT a new high)
4. Neckline: Draw a line connecting the TWO TROUGHS between the shoulders and head
   - Neckline can be flat, ascending, or descending. Declining neckline = MORE bearish.
5. Volume pattern: Left shoulder and head form on HIGH volume; right shoulder forms on LOWER volume

Entry rules:
- CONSERVATIVE (preferred): Wait for a close BELOW the neckline with a volume surge
  * Enter short on the neckline break close, OR wait for a pullback/retest of the neckline from below
  * The pullback to the neckline after the break is the highest risk:reward entry
- AGGRESSIVE: Short the right shoulder peak on a bearish reversal candle (before neckline break)
  * Requires RSI divergence or MACD bearish crossover at the right shoulder peak
- Volume: MUST INCREASE on the neckline breakdown to confirm the pattern

─── INVERSE HEAD & SHOULDERS (BOTTOM — BULLISH, BUY CALLS) ───

Pattern identification:
1. Left Shoulder: Price falls to a low, then bounces
2. Head: Price falls BELOW the left shoulder low (makes a lower low = the inverted head), then bounces
3. Right Shoulder: Price falls again but ONLY reaches approximately the left shoulder depth (NOT a new low)
4. Neckline: Draw a line connecting the TWO HIGHS between the shoulders and head

Entry rules:
- CONSERVATIVE: Wait for a close ABOVE the neckline with elevated volume
  * Enter long on the neckline breakout candle close, OR on a pullback to the neckline from above
- AGGRESSIVE: Buy at the right shoulder low on a bullish reversal candle
- Volume must EXPAND on the neckline breakout

QUALITY CHECKS (the better the pattern, the better the trade):
- Symmetry: Left shoulder and right shoulder should be roughly symmetrical in TIME and PRICE
- Time ratio: Neither shoulder should be dramatically larger/longer than the other
- Volume: Decreasing volume from left shoulder to right shoulder, surge on neckline break
- Timeframe: H&S on 1H or higher = very significant. H&S on 5M = less reliable but tradeable intraday.
""",
        "exit_rules": """
MEASURED MOVE TARGET (always use this):
- Measure the HEIGHT of the pattern = distance from the HEAD peak (or trough) to the NECKLINE
- Project this height FROM the neckline breakout in the trade direction
- Example: H&S head at $110, neckline at $100 → height = $10 → breakdown target = $90

- TP1: 50% of the measured move (partial take-profit at half the distance)
- TP2: Full measured move from neckline
- TP3: Major support/resistance zone beyond the measured move (check higher timeframe)
- Stop loss (conservative neckline entry): Just above the right shoulder high (for H&S shorts) or below the right shoulder low (for iH&S longs)
- Stop loss (aggressive right-shoulder entry): Above the right shoulder peak / below the right shoulder trough
- INVALIDATION:
  * H&S: If price closes back above the neckline and then above the right shoulder → pattern failed, exit
  * iH&S: If price closes back below the neckline and then below the right shoulder → pattern failed, exit
  * NEVER hold once the right shoulder is exceeded in the pattern's fail direction
""",
        "indicators_focus": "Left shoulder, head, right shoulder peaks/troughs (all clearly visible), neckline level (must draw), volume decreasing from LS to RS and surging on neckline break, RSI divergence between head and right shoulder for confirmation, MACD crossover at right shoulder",
        "created_at": "built-in",
    },

    "GAMMA_SCALP_0DTE": {
        "id":          "GAMMA_SCALP_0DTE",
        "name":        "0DTE Gamma Scalp (SPY/SPX)",
        "description": "Specialized strategy for scalping 0-day-to-expiration SPY/SPX options using gamma acceleration, key intraday levels, and tight risk management. Built for rapid 20-50% option premium gains.",
        "builtin":     True,
        "entry_rules": """
0DTE GAMMA SCALP STRATEGY (SPY/SPX):

WHAT MAKES 0DTE UNIQUE?
- 0DTE options have EXTREME gamma — small moves in SPY/SPX create massive percentage moves in option premium
- A $0.50 move in SPY can turn a $0.50 option into a $1.50 option (200% gain) if close to the money
- Theta (time decay) accelerates all day — options lose 50-80% of value by 2 PM if SPY doesn't move
- The goal: capture 20-50% premium gain per trade, usually within 5-30 minutes

SETUP CONDITIONS REQUIRED (all must be present):
1. Strike selection: Use AT-THE-MONEY (ATM) or 1 strike OUT-OF-THE-MONEY options
   - ATM strikes have the most gamma and will move the most per SPY point
   - Example: SPY at $525.40 → buy the $525 or $526 call/put
2. Time of day: ONLY trade during the HIGH-PROBABILITY windows:
   - WINDOW 1 (BEST): 9:30–10:30 AM ET — first hour, most volume, most momentum
   - WINDOW 2: 11:00 AM – 12:00 PM ET — VWAP reclaim/rejection setups
   - WINDOW 3: 1:30–3:00 PM ET — afternoon trend continuation (lighter)
   - AVOID: 10:30–11:00 AM (transition/chop), 3:30–4:00 PM (too much gamma risk, pin risk)
3. Trend confirmation: Never buy calls in a downtrend or puts in an uptrend. Check:
   - SPY relative to VWAP (above = calls bias, below = puts bias)
   - 5-minute chart trend (higher highs/lows = bullish, lower highs/lows = bearish)

ENTRY TRIGGERS (need ONE clear trigger):
A. VWAP RECLAIM ENTRY:
   - SPY pulls back to VWAP, then a 5-min candle closes BACK ABOVE VWAP with volume
   - Buy ATM call on that candle's close
   - Target: previous high above VWAP

B. KEY LEVEL BREAKOUT:
   - SPY consolidates at/below a round number or key level (e.g., $525.00)
   - A 5-min candle body closes ABOVE with elevated volume
   - Buy ATM call immediately on close
   - Target: next round number ($1 away) or previous high

C. FIRST PULL IN TREND (most common):
   - SPY has made a clear directional move in the first 30 minutes (trend established)
   - Price pulls back 30-50 cents to the 9 EMA on 5-minute chart
   - Bullish 5-minute reversal candle at the 9 EMA → Buy ATM call
   - Price should NOT have broken the rising trendline

D. ORB BREAKOUT (combine with ORB strategy):
   - First 5-min candle establishes the range
   - Clean break above ORB high with volume → Buy ATM call (or call debit spread for lower cost)

OPTION PREMIUM RULES:
- NEVER pay more than $1.00 for a 0DTE call or put unless SPY has already moved strongly
- Ideal entry: $0.30–$0.70 premium for maximum gamma leverage
- Check bid-ask spread: Should be $0.02–$0.05 wide. Avoid illiquid strikes with $0.10+ spreads.
""",
        "exit_rules": """
HARD PROFIT TARGETS (take them — do not be greedy with 0DTE):
- QUICK SCALP: Exit at +25% of premium paid (e.g., bought for $0.50 → sell at $0.625)
- STANDARD TARGET: Exit at +40-50% of premium paid (e.g., $0.50 → sell at $0.70-$0.75)
- RUNNER (only if SPY is clearly trending hard): Hold for +75-100% with trailing stop

HARD STOP LOSSES (non-negotiable):
- MAXIMUM LOSS PER TRADE: -40% to -50% of premium paid
  * Example: Bought $0.50 option → stop at $0.25-$0.30
  * Do NOT hold through this. The premium will collapse quickly if you are wrong.
- If SPY moves against you $0.50 or more from your entry → EXIT IMMEDIATELY. Don't wait for the 50% stop.

TIME STOPS (most important rule for 0DTE):
- NEVER hold a 0DTE past 3:00 PM ET regardless of P&L
- By 2:00 PM, premium decay is brutal — only hold if trade is already deeply profitable (+80%+)
- If a trade is flat (not moving) for more than 10-15 minutes → EXIT. Time decay is eating you.

POSITION SIZING RULES:
- Maximum risk per trade: 1-2% of account (e.g., $300 account → max $3-$6 per option contract at entry)
- Maximum daily loss: 5% of account → STOP TRADING for the rest of the day, no exceptions
- Start small: 1 contract until you have 10+ winning trades to prove the system works

DAILY GAME PLAN:
- Take profit at 20-30% and move on — stack small wins
- After 2 wins in the morning, consider stopping or trading smaller
- After any loss, take a 15-minute break before re-entering
- NEVER average down on a losing 0DTE — they can go to zero in minutes
""",
        "indicators_focus": "VWAP (mandatory for directional bias), 9 EMA on 5-minute chart (key pullback entry), ORB high/low (9:30–9:35 candle), round number levels on SPY ($1 increments), option premium price (ATM preferred), bid-ask spread width, volume on entry candle (must be elevated)",
        "created_at": "built-in",
    },
}


# ─── StrategyLibrary class ─────────────────────────────────────────────────────

class StrategyLibrary:
    """
    Manages built-in and user-created trading strategies.
    """

    def __init__(self):
        os.makedirs(STRATEGIES_DIR, exist_ok=True)
        self._active_id = self._load_active_id()

    # ── Active strategy ────────────────────────────────────────────────────

    def _load_active_id(self) -> str:
        if os.path.exists(ACTIVE_FILE):
            try:
                return open(ACTIVE_FILE).read().strip() or "AUTO"
            except Exception:
                pass
        return "AUTO"

    def _save_active_id(self):
        with open(ACTIVE_FILE, "w") as f:
            f.write(self._active_id)

    @property
    def active_id(self) -> str:
        return self._active_id

    def set_active(self, strategy_id: str):
        if self.get(strategy_id):
            self._active_id = strategy_id
            self._save_active_id()

    def get_active(self) -> dict | None:
        return self.get(self._active_id)

    # ── CRUD ───────────────────────────────────────────────────────────────

    def list_all(self) -> list[dict]:
        """Return all strategies (built-in first, then user strategies sorted by name)."""
        result = list(BUILTIN_STRATEGIES.values())
        if os.path.isdir(STRATEGIES_DIR):
            for fname in sorted(os.listdir(STRATEGIES_DIR)):
                if fname.endswith(".json"):
                    path = os.path.join(STRATEGIES_DIR, fname)
                    try:
                        s = json.load(open(path))
                        if s.get("id") not in BUILTIN_STRATEGIES:
                            result.append(s)
                    except Exception:
                        pass
        return result

    def get(self, strategy_id: str) -> dict | None:
        if strategy_id in BUILTIN_STRATEGIES:
            return BUILTIN_STRATEGIES[strategy_id]
        path = os.path.join(STRATEGIES_DIR, f"{strategy_id}.json")
        if os.path.exists(path):
            try:
                return json.load(open(path))
            except Exception:
                pass
        return None

    def save(self, name: str, description: str, entry_rules: str,
             exit_rules: str, indicators_focus: str = "",
             strategy_id: str | None = None) -> dict:
        """
        Save a new or updated custom strategy. Returns the saved strategy dict.
        """
        sid = strategy_id or self._make_id(name)
        s = {
            "id":               sid,
            "name":             name,
            "description":      description,
            "builtin":          False,
            "entry_rules":      entry_rules,
            "exit_rules":       exit_rules,
            "indicators_focus": indicators_focus,
            "created_at":       datetime.now().isoformat(),
        }
        path = os.path.join(STRATEGIES_DIR, f"{sid}.json")
        with open(path, "w") as f:
            json.dump(s, f, indent=2)
        return s

    def delete(self, strategy_id: str) -> bool:
        if strategy_id in BUILTIN_STRATEGIES:
            return False  # can't delete built-ins
        path = os.path.join(STRATEGIES_DIR, f"{strategy_id}.json")
        if os.path.exists(path):
            os.remove(path)
            if self._active_id == strategy_id:
                self._active_id = "ICT_SMC"
                self._save_active_id()
            return True
        return False

    def _make_id(self, name: str) -> str:
        base = name.upper().replace(" ", "_")[:24]
        base = "".join(c for c in base if c.isalnum() or c == "_")
        return f"{base}_{int(time.time()) % 100000}"

    # ── Prompt injection ───────────────────────────────────────────────────

    def build_strategy_injection(self, strategy_id: str | None = None) -> str:
        """
        Return the text block to inject into an analysis prompt.
        - "AUTO" mode: inject ALL strategies and let the AI auto-select the best fit.
        - ICT_SMC: returns empty string (already baked into the base prompt).
        - Any other strategy: inject that strategy's rules.
        """
        sid = strategy_id or self._active_id

        # ── AUTO mode: show the AI every strategy and let it pick ──────────
        if sid == "AUTO":
            return self.build_auto_detect_injection()

        s = self.get(sid)
        if not s:
            return ""

        # ICT/SMC is already fully baked into the main prompt — no injection needed
        if sid == "ICT_SMC":
            return ""

        name        = s.get("name", "Custom Strategy")
        description = s.get("description", "")
        entry_rules = s.get("entry_rules", "")
        exit_rules  = s.get("exit_rules", "")
        indicators  = s.get("indicators_focus", "")

        lines = [
            "",
            "═══════════════════════════════════════",
            f"ACTIVE STRATEGY: {name}",
            "═══════════════════════════════════════",
            description,
            "",
            "ENTRY RULES — follow these instead of the default sequence:",
            entry_rules.strip(),
            "",
            "EXIT / STOP RULES:",
            exit_rules.strip(),
        ]
        if indicators:
            lines += ["", f"INDICATORS TO FOCUS ON: {indicators}"]
        lines += [
            "",
            "IMPORTANT: Apply THESE rules when outputting your entry_sequence, trade_action, and summary.",
            "Keep the visual scan (Step 0) — it is universal and applies to all strategies.",
            "Keep all price reading rules — they are always required.",
        ]
        return "\n".join(lines)

    def build_auto_detect_injection(self) -> str:
        """
        Build a prompt injection that shows the AI ALL available strategies
        and instructs it to automatically select the best-fitting one for
        what it sees on the chart right now.

        The AI returns `detected_strategy` in its JSON so the app can display
        which strategy was chosen and why.
        """
        # Exclude the AUTO pseudo-entry from the list shown to the AI
        strategies = [s for s in self.list_all() if s["id"] != "AUTO"]

        lines = [
            "",
            "═══════════════════════════════════════",
            "STRATEGY AUTO-DETECT MODE",
            "═══════════════════════════════════════",
            "You are in AUTO mode. Look at the chart and determine which of the",
            "following strategies best fits what you see RIGHT NOW. Apply that",
            "strategy's rules for your entry_sequence, trade_action, and summary.",
            "",
            "AVAILABLE STRATEGIES:",
            "─────────────────────",
        ]

        for i, s in enumerate(strategies, 1):
            sid  = s["id"]
            name = s["name"]
            desc = s.get("description", "").strip().split("\n")[0]
            entry = s.get("entry_rules", "").strip()
            # Show first 3 lines of entry rules as a quick summary
            entry_preview = "\n    ".join(entry.split("\n")[:4]) if entry else ""
            indicators = s.get("indicators_focus", "")

            lines += [
                f"",
                f"STRATEGY {i}: {name}  [ID: {sid}]",
                f"  What it is: {desc}",
            ]
            if entry_preview:
                lines += [f"  Key rules:", f"    {entry_preview}"]
            if indicators:
                lines += [f"  Focus on: {indicators}"]

        lines += [
            "",
            "═══════════════════════════════════════",
            "HOW TO AUTO-SELECT:",
            "═══════════════════════════════════════",
            "1. After completing your visual scan (Step 0), ask yourself:",
            "   • Is this a fresh ICT/SMC sequence in progress? (liquidity sweep + BOS setting up)",
            "   • OR is it near the market open and price just broke above/below an opening range?",
            "   • OR is price returning to a fresh supply or demand zone for the first time?",
            "   • OR does a custom user strategy better describe what's on this chart?",
            "",
            "2. Pick the ONE strategy whose setup conditions are most clearly visible right now.",
            "   If two setups overlap, prefer the one with MORE confluences visible.",
            "   If nothing clearly fits any strategy → ICT_SMC is always the default fallback.",
            "",
            "3. Apply that strategy's entry and exit rules fully.",
            "",
            "4. In your JSON output, add this field at the top level:",
            '   "detected_strategy": {',
            '     "id": "<strategy ID you selected>",',
            '     "name": "<strategy name>",',
            '     "reason": "<1-2 sentences: what you see on the chart that matches this strategy>"',
            '   }',
            "",
            "IMPORTANT: Keep the visual scan (Step 0) — it is universal.",
            "Keep all price reading rules — they always apply.",
        ]

        return "\n".join(lines)
