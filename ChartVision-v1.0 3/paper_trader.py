"""
Multi-Market Paper Trader — virtual $500 practice account
Supports: Crypto (BTC, ETH, SOL...), Stocks/ETFs (SPY, QQQ, AAPL...),
          Forex (EUR/USD, GBP/USD...), Commodities (Gold, Oil...)
No API key needed — uses free public price feeds.
"""
import json
import os
import threading
import time
import urllib.request
from datetime import datetime

PAPER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trades.json")
STARTING_BALANCE = 500.0

# ── Market definitions ─────────────────────────────────────────
# Each entry: (display_label, source, source_id)
MARKETS = {
    # Crypto
    "BTC":    ("BTC/USD",   "coingecko", "bitcoin"),
    "ETH":    ("ETH/USD",   "coingecko", "ethereum"),
    "SOL":    ("SOL/USD",   "coingecko", "solana"),
    "DOGE":   ("DOGE/USD",  "coingecko", "dogecoin"),
    # Stocks / ETFs
    "SPY":    ("SPY",       "yahoo",     "SPY"),
    "QQQ":    ("QQQ",       "yahoo",     "QQQ"),
    "AAPL":   ("AAPL",      "yahoo",     "AAPL"),
    "TSLA":   ("TSLA",      "yahoo",     "TSLA"),
    "NVDA":   ("NVDA",      "yahoo",     "NVDA"),
    "AMD":    ("AMD",       "yahoo",     "AMD"),
    # Futures / Commodities (via Yahoo)
    "GC=F":   ("Gold",      "yahoo",     "GC=F"),
    "CL=F":   ("Oil",       "yahoo",     "CL=F"),
    "NQ=F":   ("NQ Fut",    "yahoo",     "NQ=F"),
    "ES=F":   ("ES Fut",    "yahoo",     "ES=F"),
    # Forex
    "EURUSD": ("EUR/USD",   "yahoo",     "EURUSD=X"),
    "GBPUSD": ("GBP/USD",   "yahoo",     "GBPUSD=X"),
}

# ── Price fetching ─────────────────────────────────────────────

def _fetch_coingecko(coin_id: str) -> float | None:
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        req = urllib.request.Request(url, headers={"User-Agent": "ChartVision/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
            return float(data[coin_id]["usd"])
    except Exception:
        return None


def _fetch_yahoo(ticker: str) -> float | None:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        })
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
            meta = data["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice") or meta.get("previousClose")
            return float(price) if price else None
    except Exception:
        return None


def get_price(symbol: str) -> float | None:
    """Get live price for any supported symbol."""
    if symbol not in MARKETS:
        # Try Yahoo directly for unknown symbols
        return _fetch_yahoo(symbol)
    _, source, source_id = MARKETS[symbol]
    if source == "coingecko":
        return _fetch_coingecko(source_id)
    return _fetch_yahoo(source_id)


# ── State management ───────────────────────────────────────────

def _default_state():
    return {
        "cash":       STARTING_BALANCE,
        "position":   None,   # {"symbol", "qty", "entry_price", "usd_in", "fee", "opened_at"}
        "trades":     [],
    }


def load_state() -> dict:
    if os.path.exists(PAPER_FILE):
        try:
            return json.load(open(PAPER_FILE))
        except Exception:
            pass
    return _default_state()


def save_state(state: dict):
    json.dump(state, open(PAPER_FILE, "w"), indent=2)


# ── PaperTrader class ──────────────────────────────────────────

class PaperTrader:
    def __init__(self):
        self.state      = load_state()
        self.symbol     = "BTC"
        self._price     = None
        self._callbacks = []
        self._running   = False
        self._thread    = None

    def set_symbol(self, symbol: str):
        """Switch the market being traded."""
        self.symbol  = symbol.upper()
        self._price  = None
        self._fire("price", None)
        # Fetch immediately in background
        threading.Thread(target=self._fetch_once, daemon=True).start()

    def _fetch_once(self):
        price = get_price(self.symbol)
        if price:
            self._price = price
            self._fire("price", price)

    # ── Price feed ────────────────────────────────────────────

    def start_price_feed(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._price_loop, daemon=True)
        self._thread.start()

    def stop_price_feed(self):
        self._running = False

    def _price_loop(self):
        while self._running:
            price = get_price(self.symbol)
            if price:
                self._price = price
                self._fire("price", price)
            time.sleep(15)

    def on(self, event: str, fn):
        self._callbacks.append((event, fn))

    def _fire(self, event: str, data):
        for ev, fn in self._callbacks:
            if ev == event:
                try:
                    fn(data)
                except Exception:
                    pass

    # ── Trading ───────────────────────────────────────────────

    def buy(self, usd_amount: float) -> dict:
        price = self._price or get_price(self.symbol)
        if not price:
            return {"ok": False, "error": f"Can't fetch {self.symbol} price"}
        state = self.state
        if state["position"]:
            return {"ok": False, "error": "Already in a position — close it first"}
        if usd_amount > state["cash"]:
            return {"ok": False, "error": f"Not enough cash (have ${state['cash']:.2f})"}

        fee      = usd_amount * 0.001
        qty      = usd_amount / price
        total    = usd_amount + fee

        state["cash"]    -= total
        state["position"] = {
            "symbol":      self.symbol,
            "qty":         qty,
            "entry_price": price,
            "usd_in":      usd_amount,
            "fee":         fee,
            "opened_at":   datetime.now().isoformat(),
        }
        save_state(state)
        self._fire("trade", state["position"])
        return {"ok": True, "qty": qty, "entry_price": price, "fee": fee, "symbol": self.symbol}

    def sell(self) -> dict:
        price = self._price or get_price(self.symbol)
        if not price:
            return {"ok": False, "error": "Can't fetch price"}
        state = self.state
        if not state["position"]:
            return {"ok": False, "error": "No open position to close"}

        pos      = state["position"]
        proceeds = pos["qty"] * price
        fee      = proceeds * 0.001
        net      = proceeds - fee
        pnl      = net - pos["usd_in"]

        state["cash"] += net
        closed = {**pos,
                  "exit_price": price,
                  "pnl":        round(pnl, 2),
                  "pnl_pct":    round(pnl / pos["usd_in"] * 100, 2),
                  "closed_at":  datetime.now().isoformat()}
        state["trades"].append(closed)
        state["position"] = None
        save_state(state)
        self._fire("closed", closed)
        return {"ok": True, "pnl": pnl, "exit_price": price, "net": net, "symbol": pos["symbol"]}

    def reset(self):
        self.state = _default_state()
        save_state(self.state)
        self._fire("reset", self.state)

    # ── Stats ─────────────────────────────────────────────────

    def stats(self) -> dict:
        state  = self.state
        trades = state["trades"]
        wins   = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]

        open_pnl = 0.0
        open_pct = 0.0
        pos = state["position"]
        if pos and self._price:
            open_pnl = (self._price - pos["entry_price"]) * pos["qty"]
            open_pct = (self._price - pos["entry_price"]) / pos["entry_price"] * 100

        held_value   = pos["qty"] * (self._price or pos["entry_price"]) if pos else 0
        total_value  = state["cash"] + held_value

        return {
            "cash":        round(state["cash"], 2),
            "position":    pos,
            "btc_price":   self._price,       # kept for compat
            "current_price": self._price,
            "open_pnl":    round(open_pnl, 2),
            "open_pct":    round(open_pct, 2),
            "total_value": round(total_value, 2),
            "total_pnl":   round(sum(t["pnl"] for t in trades), 2),
            "num_trades":  len(trades),
            "wins":        len(wins),
            "losses":      len(losses),
            "win_rate":    round(len(wins)/len(trades)*100, 1) if trades else 0,
        }
