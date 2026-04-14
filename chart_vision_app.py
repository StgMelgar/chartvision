#!/usr/bin/env python3
"""
TradingView Chart Vision App  —  Apple-style two-column layout
"""

import os
import sys
import json
import time
import base64
import threading
import subprocess
import tkinter as tk
import tkinter.ttk as _ttk_import
from tkinter import messagebox, filedialog, simpledialog
from datetime import datetime
from io import BytesIO

# ── Platform detection ────────────────────────────────────────────────────────
IS_MAC     = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
IS_LINUX   = sys.platform.startswith("linux")

# ── matplotlib for equity curve (optional) ──────────────────────────────────
try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# ── Sound system — cross-platform ────────────────────────────────────────────
# macOS: afplay with .aiff system sounds
# Windows: winsound with built-in MB_ constants (no file needed)
# Linux: paplay/aplay (optional, silent if not available)

MAC_SOUNDS = {
    "BUY":   "/System/Library/Sounds/Glass.aiff",
    "SELL":  "/System/Library/Sounds/Sosumi.aiff",
    "SCALP": "/System/Library/Sounds/Ping.aiff",
    "EXIT":  "/System/Library/Sounds/Basso.aiff",
    "READY": "/System/Library/Sounds/Tink.aiff",
    "ALERT": "/System/Library/Sounds/Hero.aiff",
}

if IS_WINDOWS:
    try:
        import winsound as _winsound
        WINSOUND_AVAILABLE = True
    except ImportError:
        WINSOUND_AVAILABLE = False

    # Map signal types to Windows MB_ beep constants
    WIN_SOUNDS = {
        "BUY":   _winsound.MB_ICONASTERISK   if WINSOUND_AVAILABLE else None,  # info chime
        "SELL":  _winsound.MB_ICONHAND       if WINSOUND_AVAILABLE else None,  # critical
        "SCALP": _winsound.MB_ICONASTERISK   if WINSOUND_AVAILABLE else None,
        "EXIT":  _winsound.MB_ICONEXCLAMATION if WINSOUND_AVAILABLE else None, # warning
        "READY": _winsound.MB_ICONASTERISK   if WINSOUND_AVAILABLE else None,
        "ALERT": _winsound.MB_ICONEXCLAMATION if WINSOUND_AVAILABLE else None,
    } if WINSOUND_AVAILABLE else {}
else:
    WINSOUND_AVAILABLE = False
    WIN_SOUNDS = {}

import pandas as pd
from PIL import Image, ImageTk

from screen_capture import ScreenCapture, image_to_base64, get_monitors
try:
    import mss as _mss_mod
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False
from chart_analyzer import ChartAnalyzer, format_analysis, format_premarket_briefing
from alert_system import AlertSystem
from tastytrade_broker import TastytradeBroker, format_positions, format_balance, calculate_position_size
from paper_trader import PaperTrader
from strategy_library import StrategyLibrary
from trade_memory import TradeMemory
try:
    from agent_system import AgentOrchestrator
    AGENTS_AVAILABLE = True
except ImportError:
    AGENTS_AVAILABLE = False


CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# ── Apple macOS Dark Mode palette ──────────────────────────────
C = {
    "bg":      "#111111",
    "card":    "#1C1C1E",
    "card2":   "#2C2C2E",
    "border":  "#38383A",
    "text":    "#FFFFFF",
    "text2":   "#AEAEB2",
    "text3":   "#636366",
    "blue":    "#0A84FF",
    "green":   "#30D158",
    "red":     "#FF453A",
    "orange":  "#FF9F0A",
    "yellow":  "#FFD60A",
    "btn":     "#2C2C2E",
    "input":   "#2C2C2E",
    "console": "#0A0A0A",
}

FONT_TITLE = ("Helvetica Neue", 20, "bold")
FONT_CARD  = ("Helvetica Neue", 10, "bold")
FONT_BODY  = ("Helvetica Neue", 12)
FONT_LABEL = ("Helvetica Neue", 11)
FONT_SMALL = ("Helvetica Neue", 10)
FONT_MONO  = ("Menlo", 11)
FONT_MONOS = ("Menlo", 10)


# ── Config I/O ─────────────────────────────────────────────────

def load_config() -> dict:
    default = {
        "api_key": "", "model": "claude-sonnet-4-5-20250929",
        "interval_seconds": 10, "region": None, "extra_context": "",
        "watchlist": ["SPY", "QQQ", "AAPL", "TSLA"],
        # Tastytrade broker credentials
        "tt_username": "", "tt_password": "",
        "alert_rules": {
            "rsi_overbought": {"enabled": True, "threshold": 70},
            "rsi_oversold":   {"enabled": True, "threshold": 30},
            "strong_buy":     {"enabled": True},
            "strong_sell":    {"enabled": True},
            "pattern_detected": {"enabled": True},
        },
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                default.update(json.load(f))
        except Exception:
            pass
    return default


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


# ── Shared UI helpers ──────────────────────────────────────────

def divider(parent, padx=16):
    tk.Frame(parent, bg=C["border"], height=1).pack(fill=tk.X, padx=padx)


def section_label(parent, text):
    tk.Label(parent, text=text, font=FONT_CARD,
             bg=C["card"], fg=C["text3"]).pack(anchor="w", padx=16, pady=(12, 4))


def card_frame(parent, pady=(8, 0), padx=0) -> tk.Frame:
    f = tk.Frame(parent, bg=C["card"],
                 highlightthickness=1, highlightbackground=C["border"])
    f.pack(fill=tk.X, padx=padx, pady=pady)
    return f


def apple_entry(parent, textvariable, show=None, width=20, font=None):
    return tk.Entry(parent, textvariable=textvariable, show=show,
                    font=font or FONT_BODY, bg=C["input"], fg=C["text"],
                    insertbackground=C["text"], relief=tk.FLAT,
                    highlightthickness=1,
                    highlightbackground=C["border"],
                    highlightcolor=C["blue"], width=width)


class AppleButton(tk.Canvas):
    """Rounded-pill button drawn on a Canvas."""

    STYLES = {
        "default": (C["btn"],   C["text"]),
        "accent":  (C["blue"],  C["text"]),
        "green":   (C["green"], "#000000"),
        "red":     (C["red"],   C["text"]),
        "ghost":   (C["card2"], C["text2"]),
    }

    def __init__(self, parent, text, command=None, style="default",
                 btn_width=None, height=32, **kw):
        super().__init__(parent, highlightthickness=0, bd=0,
                         bg=parent["bg"], **kw)
        self.command  = command
        self.btn_text = text
        self.bg_color, self.fg_color = self.STYLES.get(style, self.STYLES["default"])

        tmp = tk.Label(parent, text=text, font=FONT_LABEL)
        tw  = tmp.winfo_reqwidth()
        tmp.destroy()

        self.bw = btn_width or max(tw + 28, 80)
        self.bh = height
        self.config(width=self.bw, height=self.bh)
        self._draw()

        self.bind("<ButtonPress-1>",   lambda _: self._draw(dim=True))
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>",           lambda _: self._draw())
        self.bind("<Leave>",           lambda _: self._draw())

    def _draw(self, dim=False):
        self.delete("all")
        r = self.bh // 2
        w, h = self.bw, self.bh
        c = self.bg_color
        for args in [
            (0, 0, 2*r, 2*r, 90, 90),
            (w-2*r, 0, w, 2*r, 0, 90),
            (0, h-2*r, 2*r, h, 180, 90),
            (w-2*r, h-2*r, w, h, 270, 90),
        ]:
            self.create_arc(*args[:4], start=args[4], extent=args[5],
                            fill=c, outline=c)
        self.create_rectangle(r, 0, w-r, h, fill=c, outline=c)
        self.create_rectangle(0, r, w, h-r, fill=c, outline=c)
        fg = self.fg_color if not dim else C["text3"]
        self.create_text(w//2, h//2, text=self.btn_text, font=FONT_LABEL, fill=fg)

    def _on_release(self, _):
        self._draw()
        if self.command:
            self.command()

    def set_text(self, text):
        self.btn_text = text
        self._draw()


# ── Region selector overlay ────────────────────────────────────

class RegionSelector:
    def __init__(self, callback):
        self.callback = callback
        self.sx = self.sy = 0
        self.rect = None

        self.win = tk.Toplevel()
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-alpha", 0.25)
        self.win.configure(bg="black")

        tk.Label(self.win, text="Click and drag to select the chart area",
                 font=("Helvetica Neue", 22, "bold"),
                 fg="white", bg="black").pack(pady=30)

        self.cv = tk.Canvas(self.win, cursor="crosshair",
                            bg="black", highlightthickness=0)
        self.cv.pack(fill=tk.BOTH, expand=True)
        self.cv.bind("<ButtonPress-1>",   self._press)
        self.cv.bind("<B1-Motion>",       self._drag)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.win.bind("<Escape>", lambda _: self.win.destroy())

    def _press(self, e):
        self.sx, self.sy = e.x_root, e.y_root
        if self.rect:
            self.cv.delete(self.rect)

    def _drag(self, e):
        if self.rect:
            self.cv.delete(self.rect)
        rx = self.win.winfo_rootx()
        ry = self.win.winfo_rooty()
        self.rect = self.cv.create_rectangle(
            self.sx - rx, self.sy - ry,
            e.x_root - rx, e.y_root - ry,
            outline=C["blue"], width=3)

    def _release(self, e):
        left   = min(self.sx, e.x_root)
        top    = min(self.sy, e.y_root)
        width  = abs(e.x_root - self.sx)
        height = abs(e.y_root - self.sy)
        self.win.destroy()
        if width > 50 and height > 50:
            self.callback(left, top, width, height)
        else:
            messagebox.showwarning("Too Small",
                "Region too small — please try again.")


# ── Trade Execution Dialog ─────────────────────────────────────

class TradeDialog:
    """
    0DTE Options Trade Dialog.
    AI mode  : pre-filled from chart analysis — user just sets dollar amount & executes.
    Manual mode: clean inline form — symbol, CALL/PUT toggle, strike, premium.
    Automatically detects which mode based on whether trade_info is populated.
    """
    def __init__(self, parent, broker, trade_info: dict, on_complete=None):
        self.broker      = broker
        self.trade_info  = trade_info
        self.on_complete = on_complete
        self.result      = None

        # Detect mode: AI-filled if we have a meaningful option_type/action
        self._manual_mode = not bool(trade_info.get("option_type") or trade_info.get("options_play"))

        self.win = tk.Toplevel(parent)
        self.win.title("0DTE Options Trade")
        self.win.geometry("520x780")
        self.win.configure(bg=C["bg"])
        self.win.resizable(False, False)
        self.win.grab_set()
        self._build(trade_info)

    def _build(self, info):
        if self._manual_mode:
            self._build_manual()
        else:
            self._build_ai(info)

    # ── AI Mode ──────────────────────────────────────────────────
    def _build_ai(self, info):
        opt_type    = info.get("option_type", "CALL").upper()
        opt_play    = info.get("options_play", f"BUY_{opt_type}S")
        strike      = info.get("strike", 0)
        expiry      = info.get("expiration", datetime.now().strftime("%m%d%Y"))
        strike_tp   = info.get("strike_type", "ATM")
        entry_spx   = float(info.get("entry_price", 0) or 0)
        sl_spx      = float(info.get("stop_loss", 0) or 0)
        tp1_spx     = float(info.get("take_profit_1", 0) or 0)
        tp2_spx     = float(info.get("take_profit_2", 0) or 0)
        contract_px = float(info.get("contract_price", 0) or 0)
        if contract_px == 0:
            sym = info.get("symbol", "SPY").upper()
            if sym == "SPX":           contract_px = 5.00
            elif sym == "QQQ":         contract_px = 2.00
            elif sym in ("SPY","XSP"): contract_px = 1.50
            else:                      contract_px = 1.00
        setup      = info.get("setup", "")
        max_hold   = info.get("max_hold", "")
        confidence = info.get("confidence", "N/A")
        symbol     = info.get("symbol", "SPY")

        is_call    = opt_type == "CALL"
        play_color = C["green"] if is_call else C["red"]
        play_emoji = "📈" if is_call else "📉"

        # ── Header banner ──────────────────────────────────────
        hdr = tk.Frame(self.win, bg=play_color, pady=14)
        hdr.pack(fill=tk.X)
        action_lbl = "BUY CALLS" if is_call else "BUY PUTS"
        tk.Label(hdr, text=f"{play_emoji}  {action_lbl}",
                 font=("Helvetica Neue", 22, "bold"),
                 bg=play_color, fg="white").pack()
        tk.Label(hdr,
                 text=f"{symbol}  ·  Strike {int(strike) if strike else '—'}  ·  {confidence} confidence",
                 font=("Helvetica Neue", 11), bg=play_color, fg="white").pack()
        mode_lbl = "  SANDBOX  " if self.broker.sandbox else "  ⚠️ LIVE  "
        mode_col = C["card2"] if self.broker.sandbox else C["red"]
        tk.Label(hdr, text=mode_lbl, font=("Helvetica Neue", 9, "bold"),
                 bg=mode_col, fg="white", padx=6, pady=2).pack(pady=(4,0))

        # ── AI Decision summary ────────────────────────────────
        sc = card_frame(self.win, pady=(0, 4), padx=20)
        section_label(sc, "AI DECISION  —  READ ONLY")
        divider(sc)
        expiry_fmt = f"{expiry[0:2]}/{expiry[2:4]}/{expiry[4:]}" if len(expiry) == 8 else expiry
        rows_ai = [
            ("Direction",     f"{action_lbl}",                                     play_color),
            ("Expiration",    f"{expiry_fmt}  (0DTE)",                             C["orange"]),
            ("Strike",        f"{int(strike) if strike else '—'}  ({strike_tp})",  play_color),
            ("Entry Zone",    f"{entry_spx:.2f}" if entry_spx else "—",            C["blue"]),
            ("Stop Loss",     f"{sl_spx:.2f}"   if sl_spx   else "—",             C["red"]),
            ("Take Profit 1", f"{tp1_spx:.2f}"  if tp1_spx  else "—",             C["green"]),
            ("Take Profit 2", f"{tp2_spx:.2f}"  if tp2_spx  else "—",             C["green"]),
            ("Max Hold",      max_hold if max_hold else "—",                        C["text2"]),
            ("Setup",         setup if setup else "—",                              C["text2"]),
        ]
        for lbl, val, col in rows_ai:
            r = tk.Frame(sc, bg=C["card"])
            r.pack(fill=tk.X, padx=16, pady=2)
            tk.Label(r, text=lbl, font=FONT_SMALL,
                     bg=C["card"], fg=C["text3"], width=14, anchor="w").pack(side=tk.LEFT)
            tk.Label(r, text=val, font=("Menlo", 11, "bold"),
                     bg=C["card"], fg=col).pack(side=tk.LEFT)
        tk.Frame(sc, bg=C["card"]).pack(pady=4)

        # ── Dollar risk input ──────────────────────────────────
        self._finish_build(is_call, play_emoji, play_color, contract_px)

    # ── Manual Mode ──────────────────────────────────────────────
    def _build_manual(self):
        # ── Header ────────────────────────────────────────────
        hdr = tk.Frame(self.win, bg=C["card2"], pady=14)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="✍️  Manual Trade Entry",
                 font=("Helvetica Neue", 18, "bold"),
                 bg=C["card2"], fg=C["text"]).pack()
        tk.Label(hdr, text="AI has no active signal — fill in your own trade",
                 font=("Helvetica Neue", 10), bg=C["card2"], fg=C["text3"]).pack()

        # ── Manual fields ──────────────────────────────────────
        mc = card_frame(self.win, pady=4, padx=20)
        section_label(mc, "TRADE DETAILS")
        divider(mc)

        # Symbol
        sym_row = tk.Frame(mc, bg=C["card"])
        sym_row.pack(fill=tk.X, padx=16, pady=6)
        tk.Label(sym_row, text="Symbol", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"], width=14, anchor="w").pack(side=tk.LEFT)
        self._manual_sym = tk.StringVar(value="QQQ")
        apple_entry(sym_row, self._manual_sym, width=10, font=FONT_MONO).pack(side=tk.LEFT, ipady=4)

        # CALL / PUT toggle
        dir_row = tk.Frame(mc, bg=C["card"])
        dir_row.pack(fill=tk.X, padx=16, pady=6)
        tk.Label(dir_row, text="Direction", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"], width=14, anchor="w").pack(side=tk.LEFT)
        self._manual_dir = tk.StringVar(value="CALL")
        self._call_btn = tk.Label(dir_row, text="  📈 BUY CALLS  ",
                                  font=("Helvetica Neue", 11, "bold"),
                                  bg=C["green"], fg="white", cursor="hand2", padx=6, pady=4)
        self._call_btn.pack(side=tk.LEFT, padx=(0, 4))
        self._put_btn  = tk.Label(dir_row, text="  📉 BUY PUTS  ",
                                  font=("Helvetica Neue", 11, "bold"),
                                  bg=C["card2"], fg=C["text3"], cursor="hand2", padx=6, pady=4)
        self._put_btn.pack(side=tk.LEFT)
        self._call_btn.bind("<Button-1>", lambda _: self._set_manual_dir("CALL"))
        self._put_btn.bind( "<Button-1>", lambda _: self._set_manual_dir("PUT"))

        # Strike
        stk_row = tk.Frame(mc, bg=C["card"])
        stk_row.pack(fill=tk.X, padx=16, pady=6)
        tk.Label(stk_row, text="Strike Price", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"], width=14, anchor="w").pack(side=tk.LEFT)
        self._manual_strike = tk.StringVar(value="")
        apple_entry(stk_row, self._manual_strike, width=10, font=FONT_MONO).pack(side=tk.LEFT, ipady=4)
        tk.Label(stk_row, text="  (leave blank = ATM)", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)

        # Premium
        prem_row = tk.Frame(mc, bg=C["card"])
        prem_row.pack(fill=tk.X, padx=16, pady=6)
        tk.Label(prem_row, text="Est. Premium $", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"], width=14, anchor="w").pack(side=tk.LEFT)
        self._manual_prem = tk.StringVar(value="1.50")
        apple_entry(prem_row, self._manual_prem, width=10, font=FONT_MONO).pack(side=tk.LEFT, ipady=4)
        tk.Label(prem_row, text="  per share", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)

        tk.Frame(mc, bg=C["card"]).pack(pady=4)

        # ── Dollar risk input ──────────────────────────────────
        self._finish_build(True, "📈", C["green"], 1.50)

    def _set_manual_dir(self, direction):
        self._manual_dir.set(direction)
        is_call = direction == "CALL"
        self._call_btn.config(bg=C["green"]  if is_call else C["card2"],
                              fg="white"     if is_call else C["text3"])
        self._put_btn.config( bg=C["red"]    if not is_call else C["card2"],
                              fg="white"     if not is_call else C["text3"])
        # Update execute button style
        if hasattr(self, "exec_btn"):
            self.exec_btn.config(bg=C["green"] if is_call else C["red"])

    def _resolve_manual_trade_info(self):
        """Build trade_info from manual fields before executing."""
        sym      = self._manual_sym.get().strip().upper() or "QQQ"
        dir_     = self._manual_dir.get()
        strike_s = self._manual_strike.get().strip()
        prem_s   = self._manual_prem.get().strip()

        # Default premium by symbol if blank
        if not prem_s:
            prem_s = {"SPX":"5.00","QQQ":"2.00","SPY":"1.50"}.get(sym,"1.50")
        try:
            contract_px = float(prem_s)
        except ValueError:
            contract_px = 1.50

        try:
            strike = float(strike_s) if strike_s else 0
        except ValueError:
            strike = 0

        self.trade_info = {
            "trade_type":    "OPTIONS",
            "symbol":        sym,
            "option_type":   dir_,
            "options_play":  f"BUY_{dir_}S",
            "direction":     "BUY",
            "strike":        strike,
            "expiration":    datetime.now().strftime("%m%d%Y"),
            "strike_type":   "ATM" if not strike_s else "MANUAL",
            "contract_price": contract_px,
            "entry_price":   0,
            "stop_loss":     0,
            "take_profit_1": 0,
            "take_profit_2": 0,
            "risk_reward":   "N/A",
            "confidence":    "Manual",
            "setup":         "Manual",
            "max_hold":      "",
            "reasoning":     "Manual trade entry",
        }
        # Sync limit_var to the entered premium
        self.limit_var.set(f"{contract_px:.2f}")

    # ── Shared bottom section: dollar amount + order type + buttons ──
    def _finish_build(self, is_call, play_emoji, play_color, contract_px):
        # ── Dollar risk ────────────────────────────────────────
        ac = card_frame(self.win, pady=8, padx=20)
        section_label(ac, "HOW MUCH DO YOU WANT TO RISK?")
        divider(ac)

        self.amount_var = tk.StringVar(value="300")
        dr = tk.Frame(ac, bg=C["card"])
        dr.pack(fill=tk.X, padx=16, pady=10)
        tk.Label(dr, text="$", font=("Helvetica Neue", 28, "bold"),
                 bg=C["card"], fg=C["text"]).pack(side=tk.LEFT)
        tk.Entry(dr, textvariable=self.amount_var,
                 font=("Helvetica Neue", 28, "bold"),
                 bg=C["card"], fg=C["text"], insertbackground=C["text"],
                 relief=tk.FLAT, highlightthickness=0,
                 width=10).pack(side=tk.LEFT, fill=tk.X, expand=True)

        pr = tk.Frame(ac, bg=C["card"])
        pr.pack(fill=tk.X, padx=16, pady=(0, 10))
        for amt in ["100", "200", "300", "500", "1000"]:
            lbl = tk.Label(pr, text=f"${amt}", font=FONT_SMALL,
                           bg=C["card2"], fg=C["blue"], padx=10, pady=4, cursor="hand2")
            lbl.pack(side=tk.LEFT, padx=3)
            lbl.bind("<Button-1>", lambda _, a=amt: self.amount_var.set(a))

        divider(ac)
        self.contracts_lbl = tk.Label(ac, text="", font=FONT_MONOS,
                                      bg=C["card"], fg=C["text2"])
        self.contracts_lbl.pack(anchor="w", padx=16, pady=(8, 12))

        # ── Order Type ────────────────────────────────────────
        oc = card_frame(self.win, pady=4, padx=20)
        ot_row = tk.Frame(oc, bg=C["card"])
        ot_row.pack(fill=tk.X, padx=16, pady=10)
        tk.Label(ot_row, text="Order Type", font=FONT_LABEL,
                 bg=C["card"], fg=C["text2"]).pack(side=tk.LEFT)
        self.order_type_var = tk.StringVar(value="LIMIT")
        for ot in ["LIMIT", "MARKET"]:
            tk.Radiobutton(ot_row, text=ot, variable=self.order_type_var, value=ot,
                           bg=C["card"], fg=C["text"], selectcolor=C["card2"],
                           activebackground=C["card"], activeforeground=C["blue"],
                           font=FONT_LABEL).pack(side=tk.LEFT, padx=14)
        lim_row = tk.Frame(oc, bg=C["card"])
        lim_row.pack(fill=tk.X, padx=16, pady=(0, 10))
        tk.Label(lim_row, text="Limit Premium $:", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        self.limit_var = tk.StringVar(value=f"{contract_px:.2f}")
        apple_entry(lim_row, self.limit_var, width=8,
                    font=FONT_MONO).pack(side=tk.LEFT, padx=8, ipady=4)
        tk.Label(lim_row, text="per share  (×100 = cost/contract)",
                 font=FONT_SMALL, bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)

        # Wire up contract calculator now that limit_var exists
        self.amount_var.trace_add("write", self._update_contracts)
        self.limit_var.trace_add("write",  self._update_contracts)
        self._update_contracts()

        # ── Action Buttons ────────────────────────────────────
        ba = tk.Frame(self.win, bg=C["bg"])
        ba.pack(fill=tk.X, padx=20, pady=12)
        AppleButton(ba, "Preview Order", command=self._preview,
                    style="ghost", height=38).pack(fill=tk.X, pady=3)
        exec_label = f"{'📈 BUY CALLS' if is_call else '📉 BUY PUTS'}  —  Confirm & Execute"
        self.exec_btn = AppleButton(ba, exec_label, command=self._execute,
                                    style="green" if is_call else "red", height=42)
        self.exec_btn.pack(fill=tk.X, pady=3)
        self.exec_btn.config(state=tk.DISABLED)
        AppleButton(ba, "Cancel", command=self.win.destroy,
                    style="ghost", height=36).pack(fill=tk.X, pady=3)

        self.status_lbl = tk.Label(self.win, text="", font=FONT_SMALL,
                                   bg=C["bg"], fg=C["text2"],
                                   wraplength=480, justify=tk.LEFT)
        self.status_lbl.pack(padx=24, pady=4)

    # ── Helpers ───────────────────────────────────────────────

    def _contracts(self):
        """Calculate number of contracts based on dollar amount and limit premium."""
        try:
            amt  = float(self.amount_var.get())
            prem = float(self.limit_var.get())
            cost_per_contract = prem * 100  # 1 contract = 100 shares
            if cost_per_contract <= 0:
                return 0
            return max(1, int(amt / cost_per_contract))
        except (ValueError, ZeroDivisionError):
            return 0

    def _update_contracts(self, *_):
        try:
            prem = float(self.limit_var.get())
            c    = self._contracts()
            cost = c * prem * 100
            # Risk guidance based on account phase
            try:
                acct_val = float(self.amount_var.get()) * 10   # rough estimate
            except Exception:
                acct_val = 300
            risk_pct = (cost / max(acct_val, 1)) * 100

            # Color-code the risk level
            if risk_pct <= 10:
                risk_color = C["green"]
                risk_note  = "✅ Safe risk"
            elif risk_pct <= 20:
                risk_color = C["yellow"]
                risk_note  = "⚠️ Moderate risk"
            else:
                risk_color = C["red"]
                risk_note  = "🚨 High risk — reduce size!"

            self.contracts_lbl.config(
                text=f"≈ {c} contract{'s' if c != 1 else ''}  ·  "
                     f"${cost:,.2f} total  ·  "
                     f"${prem:.2f}/share × 100 × {c}",
                fg=risk_color)
        except Exception:
            self.contracts_lbl.config(text="Enter a premium price above",
                                      fg=C["text2"])

    def _preview(self):
        if not self.broker or not self.broker.connected:
            self.status_lbl.config(text="⚠️  Broker not connected", fg=C["red"])
            return
        if self._manual_mode:
            self._resolve_manual_trade_info()
        c = self._contracts()
        if c <= 0:
            self.status_lbl.config(
                text="⚠️  Enter a valid amount and premium price", fg=C["red"])
            return

        info       = self.trade_info
        opt_type   = info.get("option_type", "CALL")
        strike     = info.get("strike", 0)
        expiry     = info.get("expiration", datetime.now().strftime("%m%d%Y"))
        ot         = self.order_type_var.get()
        lp         = float(self.limit_var.get()) if ot == "LIMIT" else None

        # Convert expiry MMDDYYYY → YYYY-MM-DD for Tastytrade
        expiry_tt = (f"{expiry[4:]}-{expiry[0:2]}-{expiry[2:4]}"
                     if len(expiry) == 8 else expiry)

        self.status_lbl.config(text="Previewing with broker…", fg=C["text2"])
        self.win.update()
        try:
            r = self.broker.preview_options_order(
                underlying=      self.trade_info.get("symbol", "SPY"),
                option_type=     opt_type[0],
                strike=          float(strike),
                expiration_date= expiry_tt,
                action=          "Buy to Open",
                contracts=       c,
                order_type=      ot.capitalize(),
                limit_price=     lp,
            )
            if "error" in r:
                self.status_lbl.config(text=f"⚠️  {r['error']}", fg=C["red"])
            else:
                prem = float(self.limit_var.get())
                total = c * prem * 100
                expiry_fmt = f"{expiry[0:2]}/{expiry[2:4]}/{expiry[4:]}" if len(expiry) == 8 else expiry
                self.status_lbl.config(
                    text=(f"✅  Preview OK\n"
                          f"    BUY {c}× {self.trade_info.get('symbol','SPY')} {int(strike)} {opt_type} exp {expiry_fmt}\n"
                          f"    Est. cost: ${total:,.2f}  (${prem:.2f}/sh × 100 × {c})\n"
                          f"    Tap Confirm & Execute to place."),
                    fg=C["green"])
                self.exec_btn.config(state=tk.NORMAL)
        except Exception as e:
            self.status_lbl.config(text=f"⚠️  {e}", fg=C["red"])

    def _execute(self):
        if self._manual_mode:
            self._resolve_manual_trade_info()
        c          = self._contracts()
        info       = self.trade_info
        opt_type   = info.get("option_type", "CALL")
        strike     = info.get("strike", 0)
        expiry     = info.get("expiration", datetime.now().strftime("%m%d%Y"))
        ot         = self.order_type_var.get()
        lp         = float(self.limit_var.get()) if ot == "LIMIT" else None
        prem       = float(self.limit_var.get())
        total      = c * prem * 100
        expiry_fmt = f"{expiry[0:2]}/{expiry[2:4]}/{expiry[4:]}" if len(expiry) == 8 else expiry
        expiry_tt  = (f"{expiry[4:]}-{expiry[0:2]}-{expiry[2:4]}"
                      if len(expiry) == 8 else expiry)
        mode       = "SANDBOX" if self.broker.sandbox else "⚠️ LIVE"

        sym = self.trade_info.get("symbol", "SPY")
        if not messagebox.askyesno(
                "Final Confirmation",
                f"Place options order?\n\n"
                f"  BUY {c} contract{'s' if c != 1 else ''}\n"
                f"  {sym}  {int(strike)}  {opt_type}  exp {expiry_fmt}\n"
                f"  Limit: ${prem:.2f}/share  ·  Total: ${total:,.2f}\n"
                f"  Order: {ot}  ·  Mode: {mode}",
                parent=self.win):
            return

        self.status_lbl.config(text="Placing order…", fg=C["text2"])
        self.exec_btn.config(state=tk.DISABLED)
        self.win.update()
        try:
            r = self.broker.place_options_order(
                underlying=      self.trade_info.get("symbol", "SPY"),
                option_type=     opt_type[0],
                strike=          float(strike),
                expiration_date= expiry_tt,
                action=          "Buy to Open",
                contracts=       c,
                order_type=      ot.capitalize(),
                limit_price=     lp,
            )
            if "error" in r:
                self.status_lbl.config(text=f"❌  {r['error']}", fg=C["red"])
            else:
                emoji = "📈" if opt_type == "CALL" else "📉"
                self.status_lbl.config(
                    text=f"🎉  Order placed!\n"
                         f"    {emoji} BUY {c}× {sym} {int(strike)} {opt_type} — ${total:,.2f}",
                    fg=C["green"])
            self.result = r
            if self.on_complete:
                self.on_complete(r)
        except Exception as e:
            self.status_lbl.config(text=f"❌  {e}", fg=C["red"])


# ══════════════════════════════════════════════════════════════
#  Futures Trade Dialog
# ══════════════════════════════════════════════════════════════

class FuturesTradeDialog:
    """
    Trade dialog for outright futures contracts (/MNQ, /MES, /NQ, /ES, /GC, /CL…).
    Shows contract specs, point value, dollar P&L preview, and quantity selector.
    """

    SPECS = {
        "/MNQ": {"point_value": 2,    "tick": 0.25,  "name": "Micro Nasdaq-100", "color": "#3B82F6"},
        "/MES": {"point_value": 5,    "tick": 0.25,  "name": "Micro S&P 500",    "color": "#10B981"},
        "/MGC": {"point_value": 10,   "tick": 0.10,  "name": "Micro Gold",       "color": "#F59E0B"},
        "/MCL": {"point_value": 100,  "tick": 0.01,  "name": "Micro Crude Oil",  "color": "#8B5CF6"},
        "/M2K": {"point_value": 5,    "tick": 0.10,  "name": "Micro Russell",    "color": "#EC4899"},
        "/NQ":  {"point_value": 20,   "tick": 0.25,  "name": "Nasdaq-100",       "color": "#3B82F6"},
        "/ES":  {"point_value": 50,   "tick": 0.25,  "name": "S&P 500",          "color": "#10B981"},
        "/GC":  {"point_value": 100,  "tick": 0.10,  "name": "Gold",             "color": "#F59E0B"},
        "/CL":  {"point_value": 1000, "tick": 0.01,  "name": "Crude Oil",        "color": "#8B5CF6"},
        "/RTY": {"point_value": 50,   "tick": 0.10,  "name": "Russell 2000",     "color": "#EC4899"},
        "/SI":  {"point_value": 5000, "tick": 0.005, "name": "Silver",           "color": "#94A3B8"},
    }

    def __init__(self, parent, broker, trade_info: dict, on_complete=None):
        self.broker      = broker
        self.trade_info  = trade_info
        self.on_complete = on_complete
        self._contract_sym = None   # resolved front-month symbol e.g. /NQM6

        root_sym   = trade_info.get("symbol", "/MNQ").upper()
        # Normalize: strip spaces/trailing chars
        for k in self.SPECS:
            if root_sym.startswith(k):
                root_sym = k
                break
        self.root_sym = root_sym
        self.spec     = self.SPECS.get(root_sym, {"point_value": 2, "tick": 0.25,
                                                   "name": root_sym, "color": "#3B82F6"})

        self.win = tk.Toplevel(parent)
        self.win.title(f"Futures Trade — {root_sym}")
        self.win.geometry("540x820")
        self.win.configure(bg=C["bg"])
        self.win.resizable(False, False)
        self.win.grab_set()
        self._build()

    def _build(self):
        info       = self.trade_info
        direction  = info.get("direction", "BUY LONG")
        is_long    = "BUY" in direction.upper() or "LONG" in direction.upper()
        action_lbl = "BUY LONG (go long)" if is_long else "SELL SHORT (go short)"
        clr        = self.spec["color"]
        pv         = self.spec["point_value"]
        entry      = float(info.get("entry_price", 0) or 0)
        sl         = float(info.get("stop_loss",   0) or 0)
        tp1        = float(info.get("take_profit_1", 0) or 0)
        tp2        = float(info.get("take_profit_2", 0) or 0)
        rr         = info.get("risk_reward", "N/A")

        # ── Header ───────────────────────────────────────────────
        hdr = tk.Frame(self.win, bg=clr, pady=14)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"📊  {action_lbl}",
                 font=("Helvetica Neue", 20, "bold"),
                 bg=clr, fg="white").pack()
        tk.Label(hdr, text=f"{self.spec['name']}  ({self.root_sym})  ·  ${pv}/point",
                 font=("Helvetica Neue", 11), bg=clr, fg="white").pack()
        mode_lbl = "  SANDBOX  " if self.broker.sandbox else "  ⚠️ LIVE  "
        mode_col = C["card2"] if self.broker.sandbox else C["red"]
        tk.Label(hdr, text=mode_lbl, font=("Helvetica Neue", 9, "bold"),
                 bg=mode_col, fg="white", padx=6, pady=2).pack(pady=(4,0))

        # ── AI Signal summary ─────────────────────────────────────
        sc = card_frame(self.win, pady=(0,4), padx=20)
        section_label(sc, "AI SIGNAL  —  ENTRY LEVELS")
        divider(sc)

        def _risk_pts(a, b):
            return abs(a - b) if a and b else 0

        risk_pts = _risk_pts(entry, sl)
        tp1_pts  = _risk_pts(tp1, entry)
        risk_usd = risk_pts * pv
        tp1_usd  = tp1_pts * pv

        rows = [
            ("Direction",    action_lbl,                                          clr),
            ("Entry Zone",   f"{entry:.2f}" if entry else "—",                   C["blue"]),
            ("Stop Loss",    f"{sl:.2f}"   if sl   else "—",                     C["red"]),
            ("Target 1",     f"{tp1:.2f}"  if tp1  else "—",                     C["green"]),
            ("Target 2",     f"{tp2:.2f}"  if tp2  else "—",                     C["green"]),
            ("Risk/contract",f"${risk_usd:.0f}  ({risk_pts:.2f} pts × ${pv})",  C["orange"]),
            ("Reward T1",    f"${tp1_usd:.0f}  ({tp1_pts:.2f} pts × ${pv})",    C["green"]),
            ("R:R",          str(rr),                                             C["text2"]),
        ]
        for lbl, val, col in rows:
            r = tk.Frame(sc, bg=C["card"])
            r.pack(fill=tk.X, padx=16, pady=2)
            tk.Label(r, text=lbl, font=FONT_SMALL,
                     bg=C["card"], fg=C["text3"], width=14, anchor="w").pack(side=tk.LEFT)
            tk.Label(r, text=val, font=("Menlo", 11, "bold"),
                     bg=C["card"], fg=col).pack(side=tk.LEFT)

        # ── Quantity selector ─────────────────────────────────────
        qc = card_frame(self.win, pady=(0,4), padx=20)
        section_label(qc, "CONTRACTS")
        divider(qc)
        q_row = tk.Frame(qc, bg=C["card"])
        q_row.pack(fill=tk.X, padx=16, pady=8)
        tk.Label(q_row, text="Contracts:", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"], width=14, anchor="w").pack(side=tk.LEFT)
        self._qty_var = tk.IntVar(value=1)
        for q in (1, 2, 3, 5, 10):
            tk.Radiobutton(q_row, text=str(q), variable=self._qty_var, value=q,
                           bg=C["card"], fg=C["text"], selectcolor=C["blue"],
                           activebackground=C["card"],
                           font=FONT_SMALL).pack(side=tk.LEFT, padx=6)

        # Live dollar risk preview
        self._risk_lbl = tk.Label(qc, text="", font=FONT_SMALL,
                                   bg=C["card"], fg=C["orange"])
        self._risk_lbl.pack(padx=16, pady=(0,6))
        self._qty_var.trace_add("write", self._update_risk_preview)
        self._update_risk_preview()

        # ── Order type ────────────────────────────────────────────
        oc = card_frame(self.win, pady=(0,4), padx=20)
        section_label(oc, "ORDER TYPE")
        divider(oc)
        ot_row = tk.Frame(oc, bg=C["card"])
        ot_row.pack(fill=tk.X, padx=16, pady=6)
        self._otype_var = tk.StringVar(value="Limit")
        for ot in ("Limit", "Market"):
            tk.Radiobutton(ot_row, text=ot, variable=self._otype_var, value=ot,
                           bg=C["card"], fg=C["text"], selectcolor=C["blue"],
                           activebackground=C["card"],
                           font=FONT_SMALL).pack(side=tk.LEFT, padx=10)

        # Limit price field (pre-filled with entry zone)
        lp_row = tk.Frame(oc, bg=C["card"])
        lp_row.pack(fill=tk.X, padx=16, pady=(0,8))
        tk.Label(lp_row, text="Limit Price:", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"], width=14, anchor="w").pack(side=tk.LEFT)
        self._lp_var = tk.StringVar(value=f"{entry:.2f}" if entry else "")
        tk.Entry(lp_row, textvariable=self._lp_var,
                 bg=C["card2"], fg=C["text"], font=FONT_SMALL,
                 insertbackground=C["text"], width=12).pack(side=tk.LEFT)

        # ── Resolve contract button + status ──────────────────────
        rc = card_frame(self.win, pady=(0,4), padx=20)
        self._contract_lbl = tk.Label(rc, text="Contract: resolving…",
                                       font=FONT_SMALL, bg=C["card"], fg=C["text3"])
        self._contract_lbl.pack(padx=16, pady=6)

        # ── Action buttons ────────────────────────────────────────
        bb = tk.Frame(self.win, bg=C["bg"], pady=16)
        bb.pack(fill=tk.X, padx=20)
        AppleButton(bb, "✅  Place Order", command=self._place,
                    style="blue").pack(side=tk.LEFT, padx=(0,8))
        AppleButton(bb, "Cancel", command=self.win.destroy,
                    style="default").pack(side=tk.LEFT)

        # Resolve front-month contract in background
        import threading as _t
        _t.Thread(target=self._resolve_contract, daemon=True).start()

    def _resolve_contract(self):
        sym = self.broker.get_front_month_contract(self.root_sym)
        self._contract_sym = sym
        lbl = f"Contract: {sym}" if sym else f"Contract: ❌ not found — check connection"
        self.win.after(0, lambda: self._contract_lbl.config(
            text=lbl, fg=C["green"] if sym else C["red"]))

    def _update_risk_preview(self, *_):
        q        = self._qty_var.get()
        pv       = self.spec["point_value"]
        entry    = float(self.trade_info.get("entry_price", 0) or 0)
        sl       = float(self.trade_info.get("stop_loss", 0) or 0)
        risk_pts = abs(entry - sl) if entry and sl else 0
        risk_usd = risk_pts * pv * q
        tp1      = float(self.trade_info.get("take_profit_1", 0) or 0)
        tp1_pts  = abs(tp1 - entry) if tp1 and entry else 0
        rwd_usd  = tp1_pts * pv * q
        self._risk_lbl.config(
            text=f"{q} contract{'s' if q>1 else ''}  →  "
                 f"Risk: ${risk_usd:,.0f}  |  Reward T1: ${rwd_usd:,.0f}")

    def _place(self):
        if not self._contract_sym:
            messagebox.showerror("No Contract",
                "Front-month contract not resolved yet. Wait a moment and try again.")
            return

        info     = self.trade_info
        direction= info.get("direction", "BUY")
        is_long  = "BUY" in direction.upper() or "LONG" in direction.upper()
        action   = "Buy to Open" if is_long else "Sell to Open"
        qty      = self._qty_var.get()
        otype    = self._otype_var.get()
        lp_str   = self._lp_var.get().strip()
        lp       = float(lp_str) if lp_str else None

        # Confirm
        pv       = self.spec["point_value"]
        entry    = float(info.get("entry_price", 0) or 0)
        sl       = float(info.get("stop_loss",   0) or 0)
        risk_usd = abs(entry - sl) * pv * qty
        msg = (f"Place {action} {qty}x {self._contract_sym}?\n\n"
               f"Order type: {otype}"
               + (f"\nLimit price: {lp}" if lp else " (Market)")
               + f"\n\nMax risk: ${risk_usd:,.0f}\n\nThis will execute on your LIVE account.")
        if self.broker.sandbox:
            msg = msg.replace("LIVE account", "SANDBOX account")
        if not messagebox.askyesno("Confirm Futures Order", msg):
            return

        result = self.broker.place_futures_order(
            symbol     = self._contract_sym,
            action     = action,
            quantity   = qty,
            order_type = otype,
            limit_price= lp,
        )
        if "error" in result:
            messagebox.showerror("Order Failed", result["error"])
            if self.on_complete:
                self.on_complete(result)
        else:
            messagebox.showinfo("Order Placed",
                f"✅ Futures order placed!\nOrder ID: {result.get('order_id','—')}")
            if self.on_complete:
                self.on_complete({**result, "status": "PLACED",
                                  "symbol": self._contract_sym,
                                  "contracts": qty,
                                  "entry_price": lp or entry})
            self.win.destroy()


# ══════════════════════════════════════════════════════════════
#  Strategy Coach Dialog — teach the AI new strategies
# ══════════════════════════════════════════════════════════════

class StrategyCoachDialog:
    """
    Full-screen dialog for creating or editing a trading strategy.
    The user writes their strategy rules in plain English.
    The AI will apply those rules on every chart scan.
    """

    def __init__(self, parent, strategy_lib: StrategyLibrary,
                 existing: dict | None = None, on_saved=None):
        self.lib       = strategy_lib
        self.existing  = existing
        self.on_saved  = on_saved

        self.win = tk.Toplevel(parent)
        title = "Edit Strategy" if existing and not existing.get("builtin") else "Teach New Strategy"
        self.win.title(title)
        self.win.geometry("740x720")
        self.win.configure(bg=C["bg"])
        self.win.grab_set()
        self._build()

    def _build(self):
        win = self.win
        ex  = self.existing or {}

        # Header
        hdr = tk.Frame(win, bg=C["bg"])
        hdr.pack(fill=tk.X, padx=24, pady=(20, 4))
        tk.Label(hdr, text="🧠  Strategy Coach",
                 font=FONT_TITLE, bg=C["bg"], fg=C["text"]).pack(side=tk.LEFT)
        tk.Label(hdr,
                 text="The AI will apply these rules on every chart scan",
                 font=FONT_SMALL, bg=C["bg"], fg=C["text3"]).pack(
                     anchor="w", padx=24)

        # Name + description row
        nf = tk.Frame(win, bg=C["bg"])
        nf.pack(fill=tk.X, padx=24, pady=(12, 0))

        tk.Label(nf, text="Strategy Name", font=FONT_SMALL,
                 bg=C["bg"], fg=C["text3"]).pack(anchor="w")
        self.name_var = tk.StringVar(value=ex.get("name", ""))
        apple_entry(nf, self.name_var, width=50).pack(
            fill=tk.X, ipady=7, pady=(4, 0))

        tk.Label(nf, text="Short Description (optional)",
                 font=FONT_SMALL, bg=C["bg"], fg=C["text3"]).pack(
                     anchor="w", pady=(10, 0))
        self.desc_var = tk.StringVar(value=ex.get("description", ""))
        apple_entry(nf, self.desc_var, width=50).pack(
            fill=tk.X, ipady=5, pady=(4, 0))

        # Entry rules
        ef = tk.Frame(win, bg=C["bg"])
        ef.pack(fill=tk.BOTH, expand=True, padx=24, pady=(12, 0))

        tk.Label(ef, text="📋  ENTRY RULES  — describe what to look for and when to enter",
                 font=FONT_CARD, bg=C["bg"], fg=C["text2"]).pack(anchor="w")
        tk.Label(ef,
                 text="Write in plain English. Example: 'Enter when price sweeps a double bottom then a 5m body closes above the low'",
                 font=FONT_SMALL, bg=C["bg"], fg=C["text3"],
                 wraplength=680, justify=tk.LEFT).pack(anchor="w", pady=(2, 4))

        entry_frame = tk.Frame(ef, bg=C["border"], padx=1, pady=1)
        entry_frame.pack(fill=tk.BOTH, expand=True)
        self.entry_text = tk.Text(entry_frame, bg=C["card2"], fg=C["text"],
                                  insertbackground=C["text"],
                                  font=FONT_MONO, relief=tk.FLAT,
                                  wrap=tk.WORD, height=10)
        self.entry_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.entry_text.insert("1.0", ex.get("entry_rules", "").strip())

        # Exit rules
        xf = tk.Frame(win, bg=C["bg"])
        xf.pack(fill=tk.BOTH, expand=False, padx=24, pady=(12, 0))

        tk.Label(xf, text="🚪  EXIT / STOP RULES  — when to take profit and when to cut losses",
                 font=FONT_CARD, bg=C["bg"], fg=C["text2"]).pack(anchor="w")
        exit_frame = tk.Frame(xf, bg=C["border"], padx=1, pady=1)
        exit_frame.pack(fill=tk.X)
        self.exit_text = tk.Text(exit_frame, bg=C["card2"], fg=C["text"],
                                 insertbackground=C["text"],
                                 font=FONT_MONO, relief=tk.FLAT,
                                 wrap=tk.WORD, height=5)
        self.exit_text.pack(fill=tk.X, padx=2, pady=2)
        self.exit_text.insert("1.0", ex.get("exit_rules", "").strip())

        # Indicators focus
        inf = tk.Frame(win, bg=C["bg"])
        inf.pack(fill=tk.X, padx=24, pady=(10, 0))
        tk.Label(inf, text="Indicators / tools to focus on (optional)",
                 font=FONT_SMALL, bg=C["bg"], fg=C["text3"]).pack(anchor="w")
        self.indic_var = tk.StringVar(value=ex.get("indicators_focus", ""))
        apple_entry(inf, self.indic_var, width=60).pack(
            fill=tk.X, ipady=5, pady=(4, 0))

        # Buttons
        bf = tk.Frame(win, bg=C["bg"])
        bf.pack(fill=tk.X, padx=24, pady=(16, 20))
        self.save_status = tk.Label(bf, text="", font=FONT_SMALL,
                                    bg=C["bg"], fg=C["green"])
        self.save_status.pack(side=tk.LEFT)
        AppleButton(bf, "Cancel", command=win.destroy,
                    style="ghost").pack(side=tk.RIGHT, padx=(6, 0))
        AppleButton(bf, "💾  Save & Activate", command=self._save,
                    style="accent", height=36).pack(side=tk.RIGHT)

    def _save(self):
        name  = self.name_var.get().strip()
        desc  = self.desc_var.get().strip()
        rules = self.entry_text.get("1.0", tk.END).strip()
        exits = self.exit_text.get("1.0", tk.END).strip()
        indic = self.indic_var.get().strip()

        if not name:
            self.save_status.config(text="⚠ Please enter a strategy name", fg=C["red"])
            return
        if not rules:
            self.save_status.config(text="⚠ Please enter your entry rules", fg=C["red"])
            return

        ex_id = self.existing.get("id") if self.existing and not self.existing.get("builtin") else None
        s = self.lib.save(name=name, description=desc, entry_rules=rules,
                          exit_rules=exits, indicators_focus=indic,
                          strategy_id=ex_id)
        self.lib.set_active(s["id"])
        self.save_status.config(text=f"✓  Saved and activated", fg=C["green"])
        if self.on_saved:
            self.on_saved(s)
        self.win.after(800, self.win.destroy)


# ══════════════════════════════════════════════════════════════
#  Main Application
# ══════════════════════════════════════════════════════════════

class ChartVisionApp:

    def __init__(self):
        self.config          = load_config()
        self.capture         = ScreenCapture()
        self.analyzer        = None
        self.alerts          = AlertSystem()
        self.monitoring      = False
        self.monitor_thread  = None
        self.analysis_count  = 0
        self.broker          = None
        self.last_trade_info = None
        self._last_analysis  = None        # memory: last committed signal
        self.signal_history  = []          # list of dicts

        # ── Signal Lock System ──────────────────────────────────
        self._locked_signal   = None       # locked BUY/SELL signal dict
        self._consecutive_buf = []         # last N signals for confirmation
        self._CONFIRM_COUNT   = 1          # 1 clean BUY/SELL = lock immediately
        self._alert_shown     = False      # prevent repeat popups same signal
        self._active_trade    = None       # set when a trade is executed — triggers management mode
        self._active_trade_id = None       # trade_memory row ID for the active trade
        self._trade_entry_time = None      # datetime when trade was entered

        # ── Multi-agent system (Ruflo-inspired) ──────────────────────────────
        self.trade_memory      = TradeMemory()   # always available
        self.agent_orchestrator = None           # initialized when API key is set
        self._use_agents       = False           # toggled in settings

        # ── Daily risk controls ───────────────────────────────────────────────
        self._daily_loss_limit   = 100.0   # stop trading if down $100 today
        self._max_trades_per_day = 5       # max trades in one session
        self._max_consecutive_losses = 2   # pause after 2 losses in a row
        self._today_trades       = 0       # trades taken today
        self._today_pnl          = 0.0     # today's estimated P&L
        self._consecutive_losses = 0       # current losing streak
        self._trading_paused     = False   # True = risk limit hit
        self._scan_count         = 0       # total scans this session
        self._session_start      = datetime.now()
        self._last_loss_time     = None    # datetime of last losing trade
        self._last_trade_time    = None    # datetime of any last trade close
        # ── Bias stability lock ───────────────────────────────────────────────
        self._confirmed_bias     = None    # last confirmed HTF bias (BULLISH/BEARISH)
        self._bias_candidate     = None    # bias seen but not yet confirmed
        self._bias_candidate_count = 0     # how many times candidate seen consecutively
        self._BIAS_CONFIRM_NEEDED  = 3     # scans needed to flip bias
        # ── ICT Setup memory — tracks setup build progress across scans ───────
        self._ict_setup_zone     = None    # price zone being watched (entry zone)
        self._ict_setup_type     = None    # FVG | OB | BOS_RETEST
        self._ict_setup_scans    = 0       # how many scans we've been watching this zone
        self._ict_last_phase     = None    # last market phase seen (IMPULSE/PULLBACK/etc)
        self._ict_checklist_prev = {}      # checklist state from last scan
        self._ict_missing_step   = None    # which step was missing last scan
        self.paper           = PaperTrader()
        self.strategy_lib    = StrategyLibrary()
        self._preview_photo  = None        # keep PhotoImage ref alive
        self._watchlist_running = False
        self._watchlist_thread  = None

        self.root = tk.Tk()
        self.root.title("Chart Vision")
        self.root.geometry("1300x860")
        self.root.configure(bg=C["bg"])
        self.root.minsize(900, 640)

        self._build_ui()
        self._load_saved_settings()
        self._start_watchlist_refresh()
        self._bind_hotkeys()

    # ──────────────────────────────────────────────────────────
    #  BUILD UI
    # ──────────────────────────────────────────────────────────

    def _build_ui(self):
        """Two-column layout: left = controls, right = dashboard."""
        root_h = tk.Frame(self.root, bg=C["bg"])
        root_h.pack(fill=tk.BOTH, expand=True)

        # ── Left column (fixed 540px, scrollable)
        left_outer = tk.Frame(root_h, bg=C["bg"], width=540)
        left_outer.pack(side=tk.LEFT, fill=tk.Y, expand=False)
        left_outer.pack_propagate(False)

        lcanvas = tk.Canvas(left_outer, bg=C["bg"], highlightthickness=0)
        lcanvas.pack(fill=tk.BOTH, expand=True)

        self.lframe = tk.Frame(lcanvas, bg=C["bg"])
        self.lframe.bind("<Configure>",
            lambda _: lcanvas.configure(
                scrollregion=lcanvas.bbox("all")))
        lcanvas.create_window((0, 0), window=self.lframe, anchor="nw")

        # ── Scroll left panel only when mouse is over it ─────────────────────
        # On macOS the delta is a small integer (1-5), NOT 120 per notch.
        # Use sign only so both directions always work.
        self._left_scroll_active = False

        def _on_mousewheel(e):
            if not self._left_scroll_active:
                return
            direction = -1 if e.delta > 0 else 1
            lcanvas.yview_scroll(direction, "units")

        def _on_enter_left(_e):
            self._left_scroll_active = True

        def _on_leave_left(_e):
            self._left_scroll_active = False

        lcanvas.bind("<Enter>", _on_enter_left)
        lcanvas.bind("<Leave>", _on_leave_left)
        self.lframe.bind("<Enter>", _on_enter_left)
        self.lframe.bind("<Leave>", _on_leave_left)
        self.root.bind_all("<MouseWheel>", _on_mousewheel)

        self._build_left(self.lframe)

        # ── Vertical separator
        tk.Frame(root_h, bg=C["border"], width=1).pack(
            side=tk.LEFT, fill=tk.Y, padx=0)

        # ── Right column (expands)
        right_outer = tk.Frame(root_h, bg=C["bg"])
        right_outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_right(right_outer)

    # ── LEFT PANEL ─────────────────────────────────────────────

    def _build_left(self, sf):
        # Title
        title_row = tk.Frame(sf, bg=C["bg"])
        title_row.pack(fill=tk.X, padx=20, pady=(22, 2))
        tk.Label(title_row, text="Chart Vision",
                 font=FONT_TITLE, bg=C["bg"], fg=C["text"]).pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(title_row, textvariable=self.status_var,
                 font=FONT_SMALL, bg=C["bg"], fg=C["text3"]).pack(side=tk.RIGHT)
        tk.Label(sf, text="AI-powered analysis · ICT/SMC · 0DTE options",
                 font=FONT_SMALL, bg=C["bg"], fg=C["text3"]).pack(anchor="w", padx=22)
        tk.Label(sf, text="Made by Santiago Melgar",
                 font=FONT_SMALL, bg=C["bg"], fg=C["blue"]).pack(anchor="w", padx=22)

        # API key card
        ac = card_frame(sf, pady=(16, 0), padx=16)
        section_label(ac, "ANTHROPIC API KEY")
        divider(ac)
        ar = tk.Frame(ac, bg=C["card"])
        ar.pack(fill=tk.X, padx=16, pady=10)
        self.api_key_var = tk.StringVar()
        apple_entry(ar, self.api_key_var, show="•", width=40).pack(
            fill=tk.X, ipady=6)

        # Capture card
        cap = card_frame(sf, pady=(12, 0), padx=16)
        section_label(cap, "CAPTURE")
        divider(cap)

        # Symbol selector row — dropdown
        sym_row = tk.Frame(cap, bg=C["card"])
        sym_row.pack(fill=tk.X, padx=16, pady=(10, 4))
        tk.Label(sym_row, text="Symbol", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT, padx=(0,8))

        self.symbol_var = tk.StringVar(value="SPY")

        _sym_options = [
            "🤖 AUTO  —  Detect from chart",
            "── Options (Real Trading) ──",
            "SPY  —  S&P 500 ETF  0DTE",
            "XSP  —  Mini-SPX  0DTE",
            "SPX  —  Full Index  0DTE",
            "── Crypto (Paper / Spot) ──",
            "BTC  —  Bitcoin",
            "ETH  —  Ethereum",
            "SOL  —  Solana",
            "DOGE —  Dogecoin",
            "── Stocks / ETFs (Paper) ──",
            "SPY  —  S&P 500 ETF",
            "QQQ  —  Nasdaq ETF",
            "AAPL —  Apple",
            "TSLA —  Tesla",
            "NVDA —  Nvidia",
            "AMD  —  AMD",
            "── Micro Futures (Live) ──",
            "/MNQ —  Micro Nasdaq  $2/pt",
            "/MES —  Micro S&P     $5/pt",
            "/MGC —  Micro Gold   $10/pt",
            "/MCL —  Micro Crude $100/pt",
            "/M2K —  Micro Russ   $5/pt",
            "── Standard Futures (Live) ──",
            "/NQ  —  Nasdaq-100  $20/pt",
            "/ES  —  S&P 500     $50/pt",
            "/GC  —  Gold       $100/pt",
            "/CL  —  Crude Oil $1000/pt",
            "/RTY —  Russell    $50/pt",
            "── Forex (Paper) ──",
            "EURUSD — EUR/USD",
            "GBPUSD — GBP/USD",
        ]
        self._sym_label_to_key = {
            "🤖 AUTO  —  Detect from chart": "AUTO",
            "SPY  —  S&P 500 ETF  0DTE":  "SPY",
            "XSP  —  Mini-SPX  0DTE":     "XSP",
            "SPX  —  Full Index  0DTE":   "SPX",
            "BTC  —  Bitcoin":            "BTC",
            "ETH  —  Ethereum":           "ETH",
            "SOL  —  Solana":             "SOL",
            "DOGE —  Dogecoin":           "DOGE",
            "SPY  —  S&P 500 ETF":        "SPY",
            "QQQ  —  Nasdaq ETF":         "QQQ",
            "AAPL —  Apple":              "AAPL",
            "TSLA —  Tesla":              "TSLA",
            "NVDA —  Nvidia":             "NVDA",
            "AMD  —  AMD":                "AMD",
            "/MNQ —  Micro Nasdaq  $2/pt":  "/MNQ",
            "/MES —  Micro S&P     $5/pt":  "/MES",
            "/MGC —  Micro Gold   $10/pt":  "/MGC",
            "/MCL —  Micro Crude $100/pt":  "/MCL",
            "/M2K —  Micro Russ   $5/pt":   "/M2K",
            "/NQ  —  Nasdaq-100  $20/pt":   "/NQ",
            "/ES  —  S&P 500     $50/pt":   "/ES",
            "/GC  —  Gold       $100/pt":   "/GC",
            "/CL  —  Crude Oil $1000/pt":   "/CL",
            "/RTY —  Russell    $50/pt":    "/RTY",
            "EURUSD — EUR/USD":           "EURUSD",
            "GBPUSD — GBP/USD":           "GBPUSD",
        }

        self._sym_dropdown_var = tk.StringVar(value="SPY  —  S&P 500 ETF  0DTE")
        sym_dd = tk.OptionMenu(sym_row, self._sym_dropdown_var, *_sym_options,
                               command=self._on_sym_dropdown)
        sym_dd.configure(bg=C["card2"], fg=C["text"], activebackground=C["blue"],
                         activeforeground=C["text"], highlightthickness=0,
                         relief=tk.FLAT, font=FONT_SMALL, width=26)
        sym_dd["menu"].configure(bg=C["card2"], fg=C["text"],
                                 activebackground=C["blue"],
                                 activeforeground=C["text"], font=FONT_SMALL)
        sym_dd.pack(side=tk.LEFT)

        self.sym_desc_lbl = tk.Label(cap, text="SPY — 0DTE Options  ·  $20–$80/contract",
                                     font=FONT_SMALL, bg=C["card"], fg=C["green"])
        self.sym_desc_lbl.pack(anchor="w", padx=16, pady=(0, 4))
        self._sym_btns = {}  # kept for compat

        r1 = tk.Frame(cap, bg=C["card"])
        r1.pack(fill=tk.X, padx=16, pady=10)
        tk.Label(r1, text="Interval (sec)", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        self.interval_var = tk.StringVar(value="10")
        apple_entry(r1, self.interval_var, width=5).pack(
            side=tk.LEFT, padx=(6, 18), ipady=5)
        tk.Label(r1, text="Context", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        self.context_var = tk.StringVar()
        apple_entry(r1, self.context_var, width=18).pack(
            side=tk.LEFT, padx=6, fill=tk.X, expand=True, ipady=5)

        # ── Multi-Agent toggle ───────────────────────────────────
        agent_row = tk.Frame(cap, bg=C["card"])
        agent_row.pack(fill=tk.X, padx=16, pady=(0, 4))
        self.agents_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            agent_row, text="🤖 Multi-Agent Mode  (Bias + Entry + Scalp agents in parallel)",
            variable=self.agents_var, bg=C["card"], fg=C["blue"],
            activebackground=C["card"], activeforeground=C["blue"],
            selectcolor=C["card2"], font=FONT_SMALL,
            command=self._toggle_agents
        ).pack(side=tk.LEFT)

        # ── Sound alerts toggle ──────────────────────────────────
        sound_row = tk.Frame(cap, bg=C["card"])
        sound_row.pack(fill=tk.X, padx=16, pady=(0, 8))
        self.sound_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            sound_row, text="🔊 Sound Alerts  (plays on BUY / SELL / EXIT signals)",
            variable=self.sound_var, bg=C["card"], fg=C["text2"],
            activebackground=C["card"], activeforeground=C["text2"],
            selectcolor=C["card2"], font=FONT_SMALL,
        ).pack(side=tk.LEFT)

        # ── Screen picker (inline, no popup) ────────────────────
        screen_row = tk.Frame(cap, bg=C["card"])
        screen_row.pack(fill=tk.X, padx=16, pady=(0, 4))
        tk.Label(screen_row, text="Screen:", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT, padx=(0, 6))

        self._screen_btns = {}
        monitors = get_monitors()
        if monitors:
            for m in monitors:
                lbl = f"Monitor {m['index']}"
                btn = AppleButton(screen_row, lbl,
                                  command=lambda mon=m: self._set_monitor_quick(mon),
                                  style="default", height=28)
                btn.pack(side=tk.LEFT, padx=(0, 4))
                self._screen_btns[m["index"]] = btn
        else:
            # mss not available or single monitor — show one button
            btn = AppleButton(screen_row, "Primary",
                              command=lambda: self._set_monitor_quick(None),
                              style="default", height=28)
            btn.pack(side=tk.LEFT, padx=(0, 4))

        AppleButton(screen_row, "Custom Region",
                    command=self.select_custom_region,
                    style="ghost", height=28).pack(side=tk.LEFT, padx=(0, 4))

        self.region_lbl = tk.Label(cap,
            text="📍  No screen selected",
            font=FONT_SMALL, bg=C["card"], fg=C["text3"])
        self.region_lbl.pack(anchor="w", padx=16, pady=(2, 8))

        divider(cap)
        # Capture row 1: main actions
        br = tk.Frame(cap, bg=C["card"])
        br.pack(fill=tk.X, padx=16, pady=(12, 4))
        self.start_btn = AppleButton(br, "▶  Monitor",
                                     command=self.toggle_monitoring,
                                     style="accent")
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))
        AppleButton(br, "Analyze Once", command=self.analyze_once,
                    style="default").pack(side=tk.LEFT, padx=6)

        # Coach mode indicator — updates when paper market changes
        self._coach_mode_lbl = tk.Label(cap,
            text="🧠 Coach mode: SPY 0DTE Options",
            font=FONT_SMALL, bg=C["card"], fg=C["text3"])
        self._coach_mode_lbl.pack(anchor="w", padx=16, pady=(0, 4))

        # Capture row 2: Pre-Market Briefing + Export
        br2 = tk.Frame(cap, bg=C["card"])
        br2.pack(fill=tk.X, padx=16, pady=(0, 12))
        AppleButton(br2, "📊  Pre-Market Briefing", command=self.open_premarket_briefing,
                    style="accent", height=34).pack(side=tk.LEFT, padx=(0, 6))
        AppleButton(br2, "Export Log", command=self.export_log,
                    style="ghost").pack(side=tk.LEFT)

        # ── Strategy Coach Card ───────────────────────────────────
        strat_card = card_frame(sf, pady=(12, 0), padx=16)
        sh = tk.Frame(strat_card, bg=C["card"])
        sh.pack(fill=tk.X, padx=16, pady=(12, 6))
        tk.Label(sh, text="STRATEGY COACH", font=FONT_CARD,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        tk.Label(sh, text="🧠", font=("Helvetica Neue", 14),
                 bg=C["card"], fg=C["orange"]).pack(side=tk.RIGHT)
        divider(strat_card)

        # Auto-detect mode highlight banner
        auto_row = tk.Frame(strat_card, bg=C["blue"])
        auto_row.pack(fill=tk.X, padx=16, pady=(8, 4))
        self._auto_banner_lbl = tk.Label(
            auto_row,
            text="🤖  AUTO  —  AI reads the chart and picks the best strategy",
            font=("Helvetica Neue", 10, "bold"),
            bg=C["blue"], fg=C["text"], padx=8, pady=5)
        self._auto_banner_lbl.pack(fill=tk.X)

        # Active strategy label (shown when not in AUTO)
        self._strat_active_lbl = tk.Label(
            strat_card, text="", font=("Helvetica Neue", 11, "bold"),
            bg=C["card"], fg=C["blue"], wraplength=460, justify=tk.LEFT)
        self._strat_active_lbl.pack(anchor="w", padx=16, pady=(4, 2))

        self._strat_desc_lbl = tk.Label(
            strat_card, text="", font=FONT_SMALL,
            bg=C["card"], fg=C["text3"], wraplength=460, justify=tk.LEFT)
        self._strat_desc_lbl.pack(anchor="w", padx=16, pady=(0, 6))

        # Strategy dropdown
        strat_dd_row = tk.Frame(strat_card, bg=C["card"])
        strat_dd_row.pack(fill=tk.X, padx=16, pady=(0, 4))
        tk.Label(strat_dd_row, text="Active:", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT, padx=(0, 6))

        self._strat_var = tk.StringVar()
        self._strat_menu_btn = tk.OptionMenu(
            strat_dd_row, self._strat_var, "Loading…",
            command=self._on_strategy_select)
        self._strat_menu_btn.configure(
            bg=C["card2"], fg=C["text"], activebackground=C["blue"],
            activeforeground=C["text"], highlightthickness=0,
            relief=tk.FLAT, font=FONT_SMALL, width=28)
        self._strat_menu_btn["menu"].configure(
            bg=C["card2"], fg=C["text"],
            activebackground=C["blue"], activeforeground=C["text"],
            font=FONT_SMALL)
        self._strat_menu_btn.pack(side=tk.LEFT)

        # New / Edit / Delete buttons
        strat_btn_row = tk.Frame(strat_card, bg=C["card"])
        strat_btn_row.pack(fill=tk.X, padx=16, pady=(6, 12))
        AppleButton(strat_btn_row, "✏️  New Strategy",
                    command=self._open_new_strategy,
                    style="accent", height=30).pack(side=tk.LEFT, padx=(0, 6))
        AppleButton(strat_btn_row, "Edit",
                    command=self._open_edit_strategy,
                    style="default", height=30).pack(side=tk.LEFT, padx=(0, 6))
        AppleButton(strat_btn_row, "Delete",
                    command=self._delete_strategy,
                    style="red", height=30).pack(side=tk.LEFT)

        self._refresh_strategy_ui()

        # Broker card
        bcard = card_frame(sf, pady=(12, 0), padx=16)
        bh = tk.Frame(bcard, bg=C["card"])
        bh.pack(fill=tk.X, padx=16, pady=(12, 6))
        tk.Label(bh, text="TASTYTRADE BROKER", font=FONT_CARD,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        self.broker_dot = tk.Label(bh, text="●", font=("Helvetica Neue", 14),
                                   bg=C["card"], fg=C["text3"])
        self.broker_dot.pack(side=tk.RIGHT, padx=(0, 4))
        self.broker_status_var = tk.StringVar(value="Not connected")
        self.broker_status_lbl = tk.Label(bh,
            textvariable=self.broker_status_var,
            font=FONT_SMALL, bg=C["card"], fg=C["text3"])
        self.broker_status_lbl.pack(side=tk.RIGHT)

        divider(bcard)
        # Key row
        kr = tk.Frame(bcard, bg=C["card"])
        kr.pack(fill=tk.X, padx=16, pady=(10, 4))
        tk.Label(kr, text="Username", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        self.tt_user_var = tk.StringVar()
        apple_entry(kr, self.tt_user_var, show=None,
                    width=20).pack(side=tk.LEFT, padx=(6, 14), ipady=5, fill=tk.X, expand=True)
        # Password row
        sr = tk.Frame(bcard, bg=C["card"])
        sr.pack(fill=tk.X, padx=16, pady=(0, 4))
        tk.Label(sr, text="Password", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        self.tt_pass_var = tk.StringVar()
        apple_entry(sr, self.tt_pass_var, show="•",
                    width=20).pack(side=tk.LEFT, padx=6, ipady=5, fill=tk.X, expand=True)
        # Sandbox row
        sbr = tk.Frame(bcard, bg=C["card"])
        sbr.pack(fill=tk.X, padx=16, pady=(0, 8))
        self.sandbox_var = tk.BooleanVar(value=False)
        tk.Checkbutton(sbr, text="Sandbox mode (no real trades)",
                       variable=self.sandbox_var,
                       bg=C["card"], fg=C["text2"], selectcolor=C["card2"],
                       activebackground=C["card"], activeforeground=C["blue"],
                       font=FONT_SMALL).pack(side=tk.LEFT)

        divider(bcard)
        # Row 1: Connect + data buttons
        bb1 = tk.Frame(bcard, bg=C["card"])
        bb1.pack(fill=tk.X, padx=16, pady=(12, 4))
        AppleButton(bb1, "Connect", command=self.connect_broker,
                    style="accent").pack(side=tk.LEFT, padx=(0, 6))
        AppleButton(bb1, "Positions", command=self.show_positions,
                    style="default").pack(side=tk.LEFT, padx=6)
        AppleButton(bb1, "Balance", command=self.show_balance,
                    style="default").pack(side=tk.LEFT, padx=6)
        AppleButton(bb1, "Orders", command=self.show_orders,
                    style="default").pack(side=tk.LEFT, padx=6)
        # Row 2: Execute Trade (full width)
        bb2 = tk.Frame(bcard, bg=C["card"])
        bb2.pack(fill=tk.X, padx=16, pady=(0, 12))
        AppleButton(bb2, "🚀  Execute Trade", command=self.open_trade_dialog,
                    style="green", height=36).pack(fill=tk.X)

        # ── Live Status Panel ─────────────────────────────────
        live_card = card_frame(sf, pady=(12, 8), padx=16)
        section_label(live_card, "LIVE STATUS")
        divider(live_card)

        # Kill Zone row
        kz_row = tk.Frame(live_card, bg=C["card"])
        kz_row.pack(fill=tk.X, padx=16, pady=(10, 4))
        tk.Label(kz_row, text="Kill Zone", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        self._kz_lbl = tk.Label(kz_row, text="—", font=("Helvetica Neue", 11, "bold"),
                                bg=C["card"], fg=C["text2"])
        self._kz_lbl.pack(side=tk.RIGHT)

        # Clock / countdown row
        clk_row = tk.Frame(live_card, bg=C["card"])
        clk_row.pack(fill=tk.X, padx=16, pady=(0, 4))
        tk.Label(clk_row, text="PT Time", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        self._clk_lbl = tk.Label(clk_row, text="—", font=("Menlo", 11),
                                 bg=C["card"], fg=C["text2"])
        self._clk_lbl.pack(side=tk.RIGHT)

        # Countdown row
        cd_row = tk.Frame(live_card, bg=C["card"])
        cd_row.pack(fill=tk.X, padx=16, pady=(0, 8))
        tk.Label(cd_row, text="Next Zone", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        self._cd_lbl = tk.Label(cd_row, text="—", font=("Menlo", 11),
                                bg=C["card"], fg=C["orange"])
        self._cd_lbl.pack(side=tk.RIGHT)

        divider(live_card)

        # Entry / SL / Targets
        setup_grid = tk.Frame(live_card, bg=C["card"])
        setup_grid.pack(fill=tk.X, padx=16, pady=10)
        setup_grid.columnconfigure(1, weight=1)

        def _setup_row(parent, label, attr, color, row):
            tk.Label(parent, text=label, font=FONT_SMALL,
                     bg=C["card"], fg=C["text3"]).grid(row=row, column=0, sticky="w", pady=3)
            lbl = tk.Label(parent, text="—", font=("Helvetica Neue", 12, "bold"),
                           bg=C["card"], fg=color)
            lbl.grid(row=row, column=1, sticky="e", pady=3)
            setattr(self, attr, lbl)

        _setup_row(setup_grid, "Action",     "_setup_dir",    C["text"],    0)
        _setup_row(setup_grid, "Entry Zone", "_setup_entry",  C["blue"],    1)
        _setup_row(setup_grid, "Stop Loss",  "_setup_sl",     C["red"],     2)
        _setup_row(setup_grid, "Target 1",   "_setup_tp1",    C["green"],   3)
        _setup_row(setup_grid, "Target 2",   "_setup_tp2",    C["green"],   4)
        _setup_row(setup_grid, "Trade",      "_setup_opt",    C["orange"],  5)
        _setup_row(setup_grid, "R:R",        "_setup_rr",     C["text2"],   6)
        _setup_row(setup_grid, "P&L Est.",   "_setup_pnl",    C["green"],   7)
        _setup_row(setup_grid, "Scans",      "_setup_scans",  C["text3"],   8)

        # Close Trade button — hidden until a trade is active
        self._close_trade_btn = AppleButton(
            live_card, "✅  Close Trade (I Exited)",
            command=self._exit_trade_mode,
            style="default"
        )

        # ── Daily Stats mini-panel ───────────────────────────────────────────
        divider(live_card)
        stats_grid = tk.Frame(live_card, bg=C["card"])
        stats_grid.pack(fill=tk.X, padx=16, pady=(6, 10))
        stats_grid.columnconfigure(1, weight=1)

        def _stat_row(parent, label, attr, color, row):
            tk.Label(parent, text=label, font=FONT_SMALL,
                     bg=C["card"], fg=C["text3"]).grid(row=row, column=0, sticky="w", pady=2)
            lbl = tk.Label(parent, text="—", font=("Helvetica Neue", 11, "bold"),
                           bg=C["card"], fg=color)
            lbl.grid(row=row, column=1, sticky="e", pady=2)
            setattr(self, attr, lbl)

        _stat_row(stats_grid, "Today P&L",     "_stat_pnl",       C["green"],  0)
        _stat_row(stats_grid, "Today Trades",  "_stat_trades",    C["text2"],  1)
        _stat_row(stats_grid, "Win Rate",      "_stat_winrate",   C["green"],  2)
        _stat_row(stats_grid, "Streak",        "_stat_streak",    C["text2"],  3)
        _stat_row(stats_grid, "Risk Status",   "_stat_risk",      C["green"],  4)

        # Start the clock
        self._tick_clock()



    # ── RIGHT PANEL ────────────────────────────────────────────

    def _build_right(self, parent):
        """Four stacked sections in the right column."""
        parent.columnconfigure(0, weight=1)

        # ── 1. Chart Preview
        prev_card = tk.Frame(parent, bg=C["card"],
                             highlightthickness=1, highlightbackground=C["border"])
        prev_card.pack(fill=tk.X, padx=16, pady=(18, 0))

        ph = tk.Frame(prev_card, bg=C["card"])
        ph.pack(fill=tk.X, padx=16, pady=(12, 6))
        tk.Label(ph, text="CHART PREVIEW", font=FONT_CARD,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        self.preview_ts_lbl = tk.Label(ph, text="—", font=FONT_SMALL,
                                       bg=C["card"], fg=C["text3"])
        self.preview_ts_lbl.pack(side=tk.RIGHT)
        divider(prev_card)

        self.preview_canvas = tk.Canvas(prev_card, bg=C["console"],
                                        highlightthickness=0, height=200)
        self.preview_canvas.pack(fill=tk.X, padx=8, pady=8)
        self.preview_canvas.create_text(
            10, 100, anchor="w",
            text="No screenshot yet — click Analyze Once or Start Monitoring",
            fill=C["text3"], font=FONT_SMALL)

        # ── Tabbed middle section: Dashboard | Paper Trade ──────
        import tkinter.ttk as ttk
        nb_style = ttk.Style()
        try:
            nb_style.theme_use("default")
        except Exception:
            pass
        nb_style.configure("CV.TNotebook",
                           background=C["bg"], borderwidth=0,
                           tabmargins=[16, 6, 0, 0])
        nb_style.configure("CV.TNotebook.Tab",
                           background=C["card2"], foreground=C["text3"],
                           padding=[14, 7], font=FONT_SMALL)
        nb_style.map("CV.TNotebook.Tab",
                     background=[("selected", C["card"])],
                     foreground=[("selected", C["text"])])
        self._nb = ttk.Notebook(parent, style="CV.TNotebook", height=420)
        self._nb.pack(fill=tk.X, padx=16, pady=(12, 0))
        _tab_dash    = tk.Frame(self._nb, bg=C["bg"])
        _tab_paper   = tk.Frame(self._nb, bg=C["bg"])
        _tab_agents  = tk.Frame(self._nb, bg=C["bg"])
        _tab_journal = tk.Frame(self._nb, bg=C["bg"])
        self._nb.add(_tab_dash,    text="  📊 Dashboard  ")
        self._nb.add(_tab_paper,   text="  📄 Paper Trade  ")
        self._nb.add(_tab_agents,  text="  🤖 Agents  ")
        self._nb.add(_tab_journal, text="  📓 Journal  ")

        # ── 2. Signal History
        sig_card = tk.Frame(_tab_dash, bg=C["card"],
                            highlightthickness=1, highlightbackground=C["border"])
        sig_card.pack(fill=tk.X, padx=0, pady=(0, 0))

        sh = tk.Frame(sig_card, bg=C["card"])
        sh.pack(fill=tk.X, padx=16, pady=(12, 6))
        tk.Label(sh, text="SIGNAL HISTORY", font=FONT_CARD,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        tk.Label(sh, text="last 10 signals", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.RIGHT)
        divider(sig_card)

        self.sig_frame = tk.Frame(sig_card, bg=C["card"])
        self.sig_frame.pack(fill=tk.X, padx=8, pady=8)
        tk.Label(self.sig_frame, text="No signals yet",
                 font=FONT_SMALL, bg=C["card"], fg=C["text3"]).pack(pady=10)

        # ── 3. Account Dashboard
        acct_card = tk.Frame(_tab_dash, bg=C["card"],
                             highlightthickness=1, highlightbackground=C["border"])
        acct_card.pack(fill=tk.X, padx=0, pady=(8, 0))

        ah = tk.Frame(acct_card, bg=C["card"])
        ah.pack(fill=tk.X, padx=16, pady=(12, 6))
        tk.Label(ah, text="ACCOUNT DASHBOARD", font=FONT_CARD,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        divider(acct_card)

        self.acct_frame = tk.Frame(acct_card, bg=C["card"])
        self.acct_frame.pack(fill=tk.X, padx=16, pady=10)
        for col in range(4):
            self.acct_frame.columnconfigure(col, weight=1)

        self._acct_tiles = {}
        for i, (key, label) in enumerate([
            ("total",   "Total Value"),
            ("cash",    "Cash Available"),
            ("buying",  "Buying Power"),
            ("pl",      "Open P&L"),
        ]):
            tile = tk.Frame(self.acct_frame, bg=C["card2"],
                            highlightthickness=1, highlightbackground=C["border"])
            tile.grid(row=0, column=i, padx=4, pady=4, sticky="ew")
            tk.Label(tile, text=label, font=FONT_SMALL,
                     bg=C["card2"], fg=C["text3"]).pack(pady=(8, 2))
            val_lbl = tk.Label(tile, text="—",
                               font=("Helvetica Neue", 14, "bold"),
                               bg=C["card2"], fg=C["text"])
            val_lbl.pack(pady=(0, 8))
            self._acct_tiles[key] = val_lbl

        # ── 4. Watchlist
        wl_outer = tk.Frame(_tab_dash, bg=C["card"],
                            highlightthickness=1, highlightbackground=C["border"])
        wl_outer.pack(fill=tk.BOTH, expand=True, padx=0, pady=(8, 8))

        wh = tk.Frame(wl_outer, bg=C["card"])
        wh.pack(fill=tk.X, padx=16, pady=(12, 6))
        tk.Label(wh, text="WATCHLIST", font=FONT_CARD,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        self.wl_refresh_lbl = tk.Label(wh, text="", font=FONT_SMALL,
                                       bg=C["card"], fg=C["text3"])
        self.wl_refresh_lbl.pack(side=tk.RIGHT)

        divider(wl_outer)

        # Add symbol row
        add_row = tk.Frame(wl_outer, bg=C["card"])
        add_row.pack(fill=tk.X, padx=16, pady=8)
        self.wl_add_var = tk.StringVar()
        add_e = apple_entry(add_row, self.wl_add_var, width=12)
        add_e.pack(side=tk.LEFT, ipady=4)
        add_e.bind("<Return>", lambda _: self._watchlist_add())
        AppleButton(add_row, "Add Symbol", command=self._watchlist_add,
                    style="default", height=28).pack(side=tk.LEFT, padx=8)

        divider(wl_outer)

        # Watchlist rows container
        self.wl_frame = tk.Frame(wl_outer, bg=C["card"])
        self.wl_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        self._wl_rows = {}   # symbol -> (frame, price_lbl, chg_lbl)
        for sym in self.config.get("watchlist", []):
            self._wl_add_row(sym)

        # ── Paper Trading Panel ───────────────────────────────
        pt_card = tk.Frame(_tab_paper, bg=C["card"],
                           highlightthickness=1, highlightbackground=C["border"])
        pt_card.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        pth = tk.Frame(pt_card, bg=C["card"])
        pth.pack(fill=tk.X, padx=16, pady=(12, 6))
        tk.Label(pth, text="PAPER TRADING", font=FONT_CARD,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        self._pt_price_lbl = tk.Label(pth, text="fetching…", font=FONT_SMALL,
                                      bg=C["card"], fg=C["text2"])
        self._pt_price_lbl.pack(side=tk.RIGHT)
        divider(pt_card)

        # Market selector — dropdown
        mkt_outer = tk.Frame(pt_card, bg=C["card"])
        mkt_outer.pack(fill=tk.X, padx=16, pady=(10, 4))
        tk.Label(mkt_outer, text="Market:", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT, padx=(0,8))

        from paper_trader import MARKETS as _PT_MARKETS
        # Build grouped dropdown options
        _dropdown_options = [
            "── Crypto ──",
            "BTC  —  Bitcoin",
            "ETH  —  Ethereum",
            "SOL  —  Solana",
            "DOGE —  Dogecoin",
            "── Stocks / ETFs ──",
            "SPY  —  S&P 500 ETF",
            "QQQ  —  Nasdaq ETF",
            "AAPL —  Apple",
            "TSLA —  Tesla",
            "NVDA —  Nvidia",
            "AMD  —  AMD",
            "── Micro Futures (Live) ──",
            "/MNQ —  Micro Nasdaq  $2/pt",
            "/MES —  Micro S&P     $5/pt",
            "/MGC —  Micro Gold   $10/pt",
            "/MCL —  Micro Crude $100/pt",
            "/M2K —  Micro Russ   $5/pt",
            "── Standard Futures (Live) ──",
            "/NQ  —  Nasdaq-100  $20/pt",
            "/ES  —  S&P 500     $50/pt",
            "/GC  —  Gold       $100/pt",
            "/CL  —  Crude Oil $1000/pt",
            "/RTY —  Russell    $50/pt",
            "── Forex ──",
            "EURUSD — EUR/USD",
            "GBPUSD — GBP/USD",
        ]
        # Map display → symbol key
        self._pt_label_to_sym = {
            "BTC  —  Bitcoin":      "BTC",
            "ETH  —  Ethereum":     "ETH",
            "SOL  —  Solana":       "SOL",
            "DOGE —  Dogecoin":     "DOGE",
            "SPY  —  S&P 500 ETF":  "SPY",
            "QQQ  —  Nasdaq ETF":   "QQQ",
            "AAPL —  Apple":        "AAPL",
            "TSLA —  Tesla":        "TSLA",
            "NVDA —  Nvidia":       "NVDA",
            "AMD  —  AMD":          "AMD",
            "/MNQ —  Micro Nasdaq  $2/pt":  "/MNQ",
            "/MES —  Micro S&P     $5/pt":  "/MES",
            "/MGC —  Micro Gold   $10/pt":  "/MGC",
            "/MCL —  Micro Crude $100/pt":  "/MCL",
            "/M2K —  Micro Russ   $5/pt":   "/M2K",
            "/NQ  —  Nasdaq-100  $20/pt":   "/NQ",
            "/ES  —  S&P 500     $50/pt":   "/ES",
            "/GC  —  Gold       $100/pt":   "/GC",
            "/CL  —  Crude Oil $1000/pt":   "/CL",
            "/RTY —  Russell    $50/pt":    "/RTY",
            "EURUSD — EUR/USD":     "EURUSD",
            "GBPUSD — GBP/USD":     "GBPUSD",
        }

        self._pt_dropdown_var = tk.StringVar(value="BTC  —  Bitcoin")
        dropdown = tk.OptionMenu(mkt_outer, self._pt_dropdown_var, *_dropdown_options,
                                 command=self._pt_on_dropdown)
        dropdown.configure(
            bg=C["card2"], fg=C["text"], activebackground=C["blue"],
            activeforeground=C["text"], highlightthickness=0,
            relief=tk.FLAT, font=FONT_SMALL, indicatoron=True,
            width=22)
        dropdown["menu"].configure(
            bg=C["card2"], fg=C["text"], activebackground=C["blue"],
            activeforeground=C["text"], font=FONT_SMALL)
        dropdown.pack(side=tk.LEFT, padx=(0,10))

        # Custom ticker entry for anything not in the list
        tk.Label(mkt_outer, text="or type:", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT, padx=(0,4))
        self._pt_sym_var = tk.StringVar()
        sym_entry = apple_entry(mkt_outer, self._pt_sym_var, width=7)
        sym_entry.pack(side=tk.LEFT, padx=(0,4), ipady=3)
        sym_entry.bind("<Return>", lambda _: self._pt_set_symbol())
        AppleButton(mkt_outer, "Go", command=self._pt_set_symbol,
                    style="default", height=26).pack(side=tk.LEFT)

        self._pt_active_sym_lbl = tk.Label(pt_card, text="▶  BTC/USD",
                                           font=("Helvetica Neue", 11, "bold"),
                                           bg=C["card"], fg=C["blue"])
        self._pt_active_sym_lbl.pack(anchor="w", padx=16, pady=(4, 6))
        divider(pt_card)

        # Stats row
        stats_row = tk.Frame(pt_card, bg=C["card"])
        stats_row.pack(fill=tk.X, padx=16, pady=8)
        for col in range(4):
            stats_row.columnconfigure(col, weight=1)

        def _pt_tile(parent, label, attr, color, col):
            f = tk.Frame(parent, bg=C["card2"],
                         highlightthickness=1, highlightbackground=C["border"])
            f.grid(row=0, column=col, padx=3, sticky="ew")
            tk.Label(f, text=label, font=FONT_SMALL,
                     bg=C["card2"], fg=C["text3"]).pack(pady=(6,1))
            lbl = tk.Label(f, text="—", font=("Helvetica Neue", 12, "bold"),
                           bg=C["card2"], fg=color)
            lbl.pack(pady=(0,6))
            setattr(self, attr, lbl)

        _pt_tile(stats_row, "Cash",       "_pt_cash",    C["text"],   0)
        _pt_tile(stats_row, "Total Value","_pt_total",   C["blue"],   1)
        _pt_tile(stats_row, "Open P&L",   "_pt_opnl",    C["green"],  2)
        _pt_tile(stats_row, "Win Rate",   "_pt_wr",      C["orange"], 3)

        # Position info
        pos_row = tk.Frame(pt_card, bg=C["card"])
        pos_row.pack(fill=tk.X, padx=16, pady=(0, 6))
        self._pt_pos_lbl = tk.Label(pos_row, text="No open position",
                                    font=FONT_SMALL, bg=C["card"], fg=C["text3"])
        self._pt_pos_lbl.pack(side=tk.LEFT)
        self._pt_trades_lbl = tk.Label(pos_row, text="",
                                       font=FONT_SMALL, bg=C["card"], fg=C["text3"])
        self._pt_trades_lbl.pack(side=tk.RIGHT)

        divider(pt_card)

        # Buy/Sell controls
        ctrl = tk.Frame(pt_card, bg=C["card"])
        ctrl.pack(fill=tk.X, padx=16, pady=10)
        tk.Label(ctrl, text="$", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        self._pt_amt_var = tk.StringVar(value="100")
        apple_entry(ctrl, self._pt_amt_var, width=8).pack(side=tk.LEFT, padx=(2,10), ipady=4)

        AppleButton(ctrl, "BUY BTC",  command=self._pt_buy,
                    style="accent", height=30).pack(side=tk.LEFT, padx=(0,6))
        AppleButton(ctrl, "SELL / CLOSE", command=self._pt_sell,
                    style="default", height=30).pack(side=tk.LEFT, padx=(0,6))
        AppleButton(ctrl, "Reset",    command=self._pt_reset,
                    style="ghost", height=30).pack(side=tk.LEFT)

        # Start paper trader price feed
        self.paper.on("price",  lambda p: self.root.after(0, self._pt_refresh))
        self.paper.on("trade",  lambda _: self.root.after(0, self._pt_refresh))
        self.paper.on("closed", lambda t: self.root.after(0, lambda: self._pt_on_close(t)))
        self.paper.on("reset",  lambda _: self.root.after(0, self._pt_refresh))
        self.paper.start_price_feed()

        # ── 🤖 Agents Tab ─────────────────────────────────────
        ag_card = tk.Frame(_tab_agents, bg=C["card"],
                           highlightthickness=1, highlightbackground=C["border"])
        ag_card.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # Header row
        agh = tk.Frame(ag_card, bg=C["card"])
        agh.pack(fill=tk.X, padx=16, pady=(12, 4))
        tk.Label(agh, text="🤖  AGENT BREAKDOWN", font=FONT_CARD,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        self._ag_ts_lbl = tk.Label(agh, text="No scan yet",
                                   font=FONT_SMALL, bg=C["card"], fg=C["text3"])
        self._ag_ts_lbl.pack(side=tk.RIGHT)
        divider(ag_card)

        # Confidence bar row
        conf_row = tk.Frame(ag_card, bg=C["card"])
        conf_row.pack(fill=tk.X, padx=16, pady=(6, 4))
        tk.Label(conf_row, text="Confidence", font=FONT_SMALL,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        self._ag_conf_lbl = tk.Label(conf_row, text="—",
                                     font=("Helvetica Neue", 12, "bold"),
                                     bg=C["card"], fg=C["text2"])
        self._ag_conf_lbl.pack(side=tk.LEFT, padx=(8, 0))
        self._ag_score_lbl = tk.Label(conf_row, text="",
                                      font=FONT_SMALL, bg=C["card"], fg=C["text3"])
        self._ag_score_lbl.pack(side=tk.RIGHT)

        divider(ag_card)

        # Per-agent rows grid
        ag_grid = tk.Frame(ag_card, bg=C["card"])
        ag_grid.pack(fill=tk.X, padx=16, pady=(6, 4))
        ag_grid.columnconfigure(0, minsize=120)
        ag_grid.columnconfigure(1, minsize=80)
        ag_grid.columnconfigure(2, weight=1)

        # Column headers
        for col, hdr_text in enumerate(["AGENT", "STATUS", "DETAIL"]):
            tk.Label(ag_grid, text=hdr_text, font=("Helvetica Neue", 9, "bold"),
                     bg=C["card"], fg=C["text3"],
                     anchor="w").grid(row=0, column=col, sticky="w", pady=(0, 4))

        # Agent rows — (label, status_attr, detail_attr)
        AGENT_ROWS = [
            ("🕐  Session",       "_ag_sess_st",  "_ag_sess_dt"),
            ("📰  News Guard",    "_ag_news_st",  "_ag_news_dt"),
            ("🧭  Bias",          "_ag_bias_st",  "_ag_bias_dt"),
            ("📊  Volume",        "_ag_vol_st",   "_ag_vol_dt"),
            ("⚡  Momentum",      "_ag_mom_st",   "_ag_mom_dt"),
            ("💰  Scalp",         "_ag_scalp_st", "_ag_scalp_dt"),
            ("😨  Sentiment",     "_ag_sent_st",  "_ag_sent_dt"),
            ("🗺️  Liquidity",     "_ag_liq_st",   "_ag_liq_dt"),
            ("🔀  MTF Conf.",     "_ag_mtf_st",   "_ag_mtf_dt"),
            ("🔍  ICT Pattern",   "_ag_ict_st",   "_ag_ict_dt"),
            ("🎯  Entry",         "_ag_entry_st", "_ag_entry_dt"),
            ("🛡️  Risk Mgr",      "_ag_risk_st",  "_ag_risk_dt"),
            ("📐  Position Size", "_ag_size_st",  "_ag_size_dt"),
            ("🧠  Strategy",      "_ag_strat_st", "_ag_strat_dt"),
            ("📉  Divergence",    "_ag_div_st",   "_ag_div_dt"),
            ("🌅  Pre-Market",    "_ag_pm_st",    "_ag_pm_dt"),
        ]

        for i, (label, st_attr, dt_attr) in enumerate(AGENT_ROWS, start=1):
            tk.Label(ag_grid, text=label, font=FONT_SMALL,
                     bg=C["card"], fg=C["text2"],
                     anchor="w").grid(row=i, column=0, sticky="w", pady=3)

            st_lbl = tk.Label(ag_grid, text="—",
                              font=("Helvetica Neue", 10, "bold"),
                              bg=C["card"], fg=C["text3"], anchor="w")
            st_lbl.grid(row=i, column=1, sticky="w", padx=(4, 0), pady=3)
            setattr(self, st_attr, st_lbl)

            dt_lbl = tk.Label(ag_grid, text="Waiting for scan…",
                              font=FONT_SMALL, bg=C["card"],
                              fg=C["text3"], anchor="w", wraplength=420)
            dt_lbl.grid(row=i, column=2, sticky="w", padx=(8, 0), pady=3)
            setattr(self, dt_attr, dt_lbl)

        divider(ag_card)

        # Veto / note banner
        self._ag_veto_lbl = tk.Label(ag_card, text="",
                                     font=("Helvetica Neue", 11, "bold"),
                                     bg=C["card"], fg=C["orange"],
                                     anchor="w", wraplength=600, justify=tk.LEFT)
        self._ag_veto_lbl.pack(fill=tk.X, padx=16, pady=(4, 2))

        # Hint label when agents are off
        self._ag_hint_lbl = tk.Label(ag_card,
                                     text="Enable Multi-Agent Mode (left panel) to see per-agent analysis here.",
                                     font=FONT_SMALL, bg=C["card"], fg=C["text3"])
        self._ag_hint_lbl.pack(pady=10)

        # ── 📓 Trade Journal Tab ───────────────────────────────
        jnl_card = tk.Frame(_tab_journal, bg=C["card"],
                            highlightthickness=1, highlightbackground=C["border"])
        jnl_card.pack(fill=tk.BOTH, expand=True)

        # Header
        jh = tk.Frame(jnl_card, bg=C["card"])
        jh.pack(fill=tk.X, padx=16, pady=(12, 4))
        tk.Label(jh, text="📓  TRADE JOURNAL", font=FONT_CARD,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        AppleButton(jh, "↺  Refresh", command=lambda: self._refresh_journal(),
                    style="ghost", height=24).pack(side=tk.RIGHT)
        divider(jnl_card)

        # Summary stats row
        js = tk.Frame(jnl_card, bg=C["card"])
        js.pack(fill=tk.X, padx=16, pady=(6, 4))
        for col in range(5):
            js.columnconfigure(col, weight=1)

        def _jstat(parent, label, attr, color, col):
            f = tk.Frame(parent, bg=C["card2"],
                         highlightthickness=1, highlightbackground=C["border"])
            f.grid(row=0, column=col, padx=3, sticky="ew")
            tk.Label(f, text=label, font=FONT_SMALL,
                     bg=C["card2"], fg=C["text3"]).pack(pady=(5,1))
            lbl = tk.Label(f, text="—", font=("Helvetica Neue", 12, "bold"),
                           bg=C["card2"], fg=color)
            lbl.pack(pady=(0,5))
            setattr(self, attr, lbl)

        _jstat(js, "Total P&L",   "_j_pnl",     C["green"],  0)
        _jstat(js, "Win Rate",    "_j_winrate",  C["blue"],   1)
        _jstat(js, "Total Trades","_j_trades",   C["text2"],  2)
        _jstat(js, "Best Trade",  "_j_best",     C["green"],  3)
        _jstat(js, "Worst Trade", "_j_worst",    C["red"],    4)

        divider(jnl_card)

        # Equity curve canvas
        self._j_chart_frame = tk.Frame(jnl_card, bg=C["card"], height=120)
        self._j_chart_frame.pack(fill=tk.X, padx=16, pady=(4, 4))
        self._j_chart_frame.pack_propagate(False)
        self._j_canvas = None   # matplotlib canvas (created lazily)

        divider(jnl_card)

        # Trade table headers
        th = tk.Frame(jnl_card, bg=C["card2"])
        th.pack(fill=tk.X, padx=16, pady=(2, 0))
        for col_w, col_txt in [(6,"#"),(10,"Date"),(6,"Sym"),(5,"Type"),
                                (8,"Entry"),(8,"Exit"),(8,"P&L"),(7,"Hold"),(6,"Result")]:
            tk.Label(th, text=col_txt, font=("Helvetica Neue", 9, "bold"),
                     bg=C["card2"], fg=C["text3"],
                     width=col_w, anchor="w").pack(side=tk.LEFT, padx=2, pady=4)

        # Scrollable trade rows
        jscroll_frame = tk.Frame(jnl_card, bg=C["card"])
        jscroll_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))
        jscroll = tk.Scrollbar(jscroll_frame)
        jscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._j_listbox = tk.Listbox(
            jscroll_frame, yscrollcommand=jscroll.set,
            bg=C["console"], fg=C["text2"], font=FONT_MONOS,
            selectbackground=C["blue"], relief=tk.FLAT,
            highlightthickness=0, borderwidth=0, height=10)
        self._j_listbox.pack(fill=tk.BOTH, expand=True)
        jscroll.config(command=self._j_listbox.yview)

        # Output Log (fills remaining right-panel space) ─────
        log_card = tk.Frame(parent, bg=C["card"],
                            highlightthickness=1, highlightbackground=C["border"])
        log_card.pack(fill=tk.BOTH, expand=True, padx=16, pady=(12, 18))

        lh = tk.Frame(log_card, bg=C["card"])
        lh.pack(fill=tk.X, padx=16, pady=(12, 6))
        tk.Label(lh, text="OUTPUT LOG", font=FONT_CARD,
                 bg=C["card"], fg=C["text3"]).pack(side=tk.LEFT)
        divider(log_card)

        self.output_text = tk.Text(
            log_card, wrap=tk.WORD, bg=C["console"], fg=C["text2"],
            font=FONT_MONOS, insertbackground=C["text"],
            selectbackground=C["blue"], relief=tk.FLAT,
            padx=12, pady=10)
        sb_log = tk.Scrollbar(log_card, command=self.output_text.yview,
                              bg=C["card"], troughcolor=C["card2"])
        self.output_text.configure(yscrollcommand=sb_log.set)
        sb_log.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=4)
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.output_text.tag_configure("alert", foreground=C["red"],
            font=(*FONT_MONOS[:1], FONT_MONOS[1], "bold"))
        self.output_text.tag_configure("signal_buy",  foreground=C["green"])
        self.output_text.tag_configure("signal_sell", foreground=C["red"])
        self.output_text.tag_configure("header", foreground=C["blue"],
            font=(*FONT_MONOS[:1], FONT_MONOS[1], "bold"))

    # ──────────────────────────────────────────────────────────
    #  RIGHT PANEL: Chart Preview
    # ──────────────────────────────────────────────────────────

    def update_chart_preview(self, img_b64: str):
        """Display the latest chart screenshot in the preview canvas."""
        try:
            raw = base64.b64decode(img_b64)
            img = Image.open(BytesIO(raw))

            cw = self.preview_canvas.winfo_width() or 600
            ch = 200
            img.thumbnail((cw - 16, ch - 16), Image.LANCZOS)

            photo = ImageTk.PhotoImage(img)
            self._preview_photo = photo  # keep reference!

            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(
                cw // 2, ch // 2, anchor="center", image=photo)
            self.preview_ts_lbl.config(
                text=datetime.now().strftime("%H:%M:%S"))
        except Exception as e:
            print(f"Preview error: {e}")

    # ──────────────────────────────────────────────────────────
    #  RIGHT PANEL: Signal History
    # ──────────────────────────────────────────────────────────

    def add_signal_to_history(self, analysis: dict):
        """Push latest signal into the history panel."""
        ta     = analysis.get("trade_action", {})
        signal = analysis.get("signals", {}).get("overall", "NEUTRAL")
        should = ta.get("should_trade", "WAIT")
        sym    = analysis.get("symbol", "?")
        price  = analysis.get("price", {}).get("current", "—")
        ts     = datetime.now().strftime("%H:%M")

        if should == "YES_ENTER_NOW":
            direction = ta.get("direction", "BUY")
            color     = C["green"] if direction == "BUY" else C["red"]
            label     = f"{direction}  {sym}"
        elif "SELL" in signal:
            color = C["red"]
            label = f"SELL  {sym}"
        elif "BUY" in signal:
            color = C["green"]
            label = f"BUY  {sym}"
        else:
            color = C["text3"]
            label = f"WAIT  {sym}"

        entry = {"ts": ts, "label": label, "color": color,
                 "price": price, "signal": signal}
        self.signal_history.insert(0, entry)
        self.signal_history = self.signal_history[:10]

        # Rebuild signal rows
        for w in self.sig_frame.winfo_children():
            w.destroy()

        for rec in self.signal_history:
            row = tk.Frame(self.sig_frame, bg=C["card2"],
                           highlightthickness=1, highlightbackground=C["border"])
            row.pack(fill=tk.X, pady=2, padx=4)

            tk.Label(row, text=rec["ts"], font=FONT_SMALL,
                     bg=C["card2"], fg=C["text3"], width=6).pack(side=tk.LEFT, padx=6)
            tk.Label(row, text=rec["label"], font=("Helvetica Neue", 11, "bold"),
                     bg=C["card2"], fg=rec["color"]).pack(side=tk.LEFT, padx=4)
            tk.Label(row, text=f"${rec['price']}", font=FONT_MONOS,
                     bg=C["card2"], fg=C["text2"]).pack(side=tk.RIGHT, padx=10)

    # ──────────────────────────────────────────────────────────
    #  RIGHT PANEL: Account Dashboard
    # ──────────────────────────────────────────────────────────

    def update_account_dashboard(self, balance: dict, positions: list = None):
        """Update the four account tiles."""
        def fmt(val):
            try:
                v = float(val)
                color = C["green"] if v >= 0 else C["red"]
                return f"${v:,.2f}", color
            except Exception:
                return "—", C["text"]

        total, tc  = fmt(balance.get("total_value", 0))
        cash,  cc  = fmt(balance.get("cash_available", 0))
        bp,    bc  = fmt(balance.get("buying_power", 0))

        # Compute open P&L from positions
        pl_val = 0
        if positions:
            pl_val = sum(p.get("total_gain", 0) for p in positions)
        pl, pc = fmt(pl_val)

        self._acct_tiles["total"].config(text=total, fg=tc)
        self._acct_tiles["cash"].config(text=cash,  fg=cc)
        self._acct_tiles["buying"].config(text=bp,  fg=bc)
        self._acct_tiles["pl"].config(text=pl,      fg=pc)

    # ──────────────────────────────────────────────────────────
    #  RIGHT PANEL: Watchlist
    # ──────────────────────────────────────────────────────────

    def _wl_add_row(self, symbol: str):
        symbol = symbol.upper().strip()
        if not symbol or symbol in self._wl_rows:
            return
        row = tk.Frame(self.wl_frame, bg=C["card"],
                       highlightthickness=1, highlightbackground=C["border"])
        row.pack(fill=tk.X, pady=2, padx=2)

        tk.Label(row, text=symbol, font=("Helvetica Neue", 13, "bold"),
                 bg=C["card"], fg=C["text"], width=8, anchor="w").pack(side=tk.LEFT, padx=10)
        price_lbl = tk.Label(row, text="—", font=("Menlo", 13, "bold"),
                             bg=C["card"], fg=C["text"])
        price_lbl.pack(side=tk.LEFT, padx=8)
        chg_lbl = tk.Label(row, text="", font=FONT_SMALL,
                           bg=C["card"], fg=C["text3"])
        chg_lbl.pack(side=tk.LEFT)

        rm_btn = tk.Label(row, text="✕", font=FONT_SMALL,
                          bg=C["card"], fg=C["text3"], cursor="hand2")
        rm_btn.pack(side=tk.RIGHT, padx=10)
        rm_btn.bind("<Button-1>", lambda _, s=symbol: self._watchlist_remove(s))

        self._wl_rows[symbol] = (row, price_lbl, chg_lbl)

    def _watchlist_add(self):
        sym = self.wl_add_var.get().upper().strip()
        if not sym:
            return
        if sym not in self.config.get("watchlist", []):
            self.config.setdefault("watchlist", []).append(sym)
            save_config(self.config)
        self._wl_add_row(sym)
        self.wl_add_var.set("")
        self._refresh_watchlist_prices()

    def _watchlist_remove(self, symbol: str):
        if symbol in self._wl_rows:
            self._wl_rows[symbol][0].destroy()
            del self._wl_rows[symbol]
        wl = self.config.get("watchlist", [])
        if symbol in wl:
            wl.remove(symbol)
            save_config(self.config)

    def _refresh_watchlist_prices(self):
        """Fetch quotes for all watchlist symbols in background."""
        if not self.broker or not self.broker.connected:
            self.wl_refresh_lbl.config(text="Connect broker for live prices")
            return

        symbols = list(self._wl_rows.keys())
        if not symbols:
            return

        def _fetch():
            for sym in symbols:
                try:
                    q = self.broker.get_quote(sym)
                    if q:
                        price  = float(q.get("last_price", 0))
                        chg    = float(q.get("change", 0))
                        chg_pct = float(q.get("change_pct", 0))
                        color  = C["green"] if chg >= 0 else C["red"]
                        sign   = "+" if chg >= 0 else ""
                        self.root.after(0, lambda s=sym, p=price, c=chg,
                                        cp=chg_pct, col=color, sg=sign:
                            self._update_wl_row(s, p, c, cp, col, sg))
                except Exception:
                    pass
            ts = datetime.now().strftime("%H:%M:%S")
            self.root.after(0, lambda: self.wl_refresh_lbl.config(
                text=f"Updated {ts}"))

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_wl_row(self, sym, price, chg, chg_pct, color, sign):
        if sym in self._wl_rows:
            _, price_lbl, chg_lbl = self._wl_rows[sym]
            price_lbl.config(text=f"${price:,.2f}", fg=color)
            chg_lbl.config(
                text=f"{sign}{chg:.2f} ({sign}{chg_pct:.2f}%)",
                fg=color)

    def _start_watchlist_refresh(self):
        """Auto-refresh watchlist every 30 seconds."""
        self._watchlist_running = True
        def _loop():
            while self._watchlist_running:
                self.root.after(0, self._refresh_watchlist_prices)
                time.sleep(30)
        self._watchlist_thread = threading.Thread(target=_loop, daemon=True)
        self._watchlist_thread.start()

    # ──────────────────────────────────────────────────────────
    #  Strategy Coach helpers
    # ──────────────────────────────────────────────────────────

    def _refresh_strategy_ui(self):
        """Rebuild the strategy dropdown and update active label."""
        strategies = self.strategy_lib.list_all()
        active_id  = self.strategy_lib.active_id
        active     = self.strategy_lib.get_active()

        # Rebuild OptionMenu options
        menu = self._strat_menu_btn["menu"]
        menu.delete(0, "end")
        for s in strategies:
            menu.add_command(label=s["name"],
                             command=lambda sid=s["id"]: self._on_strategy_select_id(sid))

        # Show/hide AUTO banner and update labels
        is_auto = (active_id == "AUTO")
        if is_auto:
            self._auto_banner_lbl.config(
                text="🤖  AUTO  —  AI reads the chart and picks the best strategy",
                bg=C["blue"])
            self._strat_active_lbl.config(text="")
            self._strat_desc_lbl.config(text="")
        else:
            self._auto_banner_lbl.config(text="AUTO off", bg=C["card2"])
            if active:
                self._strat_active_lbl.config(text=f"Active: {active['name']}")
                self._strat_desc_lbl.config(text=active.get("description", ""))

        if active:
            self._strat_var.set(active["name"])

    def _on_strategy_select(self, selection: str):
        """Called when OptionMenu item clicked (by name)."""
        for s in self.strategy_lib.list_all():
            if s["name"] == selection:
                self._on_strategy_select_id(s["id"])
                break

    def _on_strategy_select_id(self, strategy_id: str):
        """Switch the active strategy."""
        self.strategy_lib.set_active(strategy_id)
        self._refresh_strategy_ui()
        active = self.strategy_lib.get_active()
        if active:
            if strategy_id == "AUTO":
                self.log("🤖  Strategy AUTO-DETECT enabled — AI will pick the best strategy for each chart", "info")
            else:
                self.log(f"🧠  Strategy switched to: {active['name']}", "info")

    def _open_new_strategy(self):
        StrategyCoachDialog(self.root, self.strategy_lib,
                            on_saved=lambda s: self._refresh_strategy_ui())

    def _open_edit_strategy(self):
        active = self.strategy_lib.get_active()
        if active and active.get("builtin"):
            # Can't edit built-ins directly — offer to clone
            StrategyCoachDialog(self.root, self.strategy_lib,
                                existing={**active,
                                          "id": None,
                                          "builtin": False,
                                          "name": f"{active['name']} (custom)"},
                                on_saved=lambda s: self._refresh_strategy_ui())
        elif active:
            StrategyCoachDialog(self.root, self.strategy_lib,
                                existing=active,
                                on_saved=lambda s: self._refresh_strategy_ui())

    def _delete_strategy(self):
        active = self.strategy_lib.get_active()
        if not active:
            return
        if active.get("builtin"):
            messagebox.showinfo("Built-in",
                "Built-in strategies can't be deleted. You can create a custom one instead.")
            return
        if messagebox.askyesno("Delete Strategy",
                               f"Delete '{active['name']}'? This can't be undone."):
            self.strategy_lib.delete(active["id"])
            self._refresh_strategy_ui()
            self.log(f"🗑  Strategy deleted: {active['name']}", "info")

    def _get_strategy_injection(self) -> str:
        """Get the active strategy prompt injection (empty string = default ICT/SMC)."""
        return self.strategy_lib.build_strategy_injection()

    # ──────────────────────────────────────────────────────────
    #  Settings
    # ──────────────────────────────────────────────────────────

    def _on_sym_dropdown(self, selection: str):
        """Called when user picks from the symbol dropdown."""
        if selection.startswith("──"):
            return
        sym = self._sym_label_to_key.get(selection, selection.split()[0])
        self._set_symbol(sym)

    def _set_symbol(self, sym: str):
        """Switch the active trading symbol and update coach mode."""
        self.symbol_var.set(sym)

        # Sync paper trader only when a real symbol is selected (not AUTO)
        if hasattr(self, "paper") and sym != "AUTO":
            self.paper.set_symbol(sym)

        _options_syms = {"SPY", "XSP", "SPX"}
        is_options = sym in _options_syms and sym != "AUTO"

        _desc_map = {
            "AUTO":   ("🤖 Auto-Detect — AI reads chart and identifies symbol", C["blue"]),
            "SPY":    ("SPY — 0DTE Options  ·  $20–$80/contract",  C["green"]),
            "XSP":    ("XSP — Mini-SPX 0DTE  ·  60/40 tax",        C["blue"]),
            "SPX":    ("SPX — Full Index 0DTE  ·  $200–$2K/contract", C["orange"]),
            "BTC":    ("BTC — Bitcoin Spot  ·  24/7 market",        C["orange"]),
            "ETH":    ("ETH — Ethereum Spot  ·  24/7 market",       C["blue"]),
            "SOL":    ("SOL — Solana Spot  ·  24/7 market",         C["blue"]),
            "QQQ":    ("QQQ — Nasdaq ETF  ·  Spot/Paper",           C["blue"]),
            "AAPL":   ("AAPL — Apple Stock  ·  Spot/Paper",         C["text2"]),
            "TSLA":   ("TSLA — Tesla Stock  ·  Spot/Paper",         C["text2"]),
            "NVDA":   ("NVDA — Nvidia Stock  ·  Spot/Paper",        C["green"]),
            "NQ=F":   ("NQ — Nasdaq Futures  ·  Spot/Paper",        C["blue"]),
            "ES=F":   ("ES — S&P Futures  ·  Spot/Paper",           C["green"]),
            "GC=F":   ("Gold Futures  ·  Spot/Paper",               C["yellow"]),
            "EURUSD": ("EUR/USD — Forex  ·  Spot/Paper",            C["text2"]),
        }
        desc, color = _desc_map.get(sym, (f"{sym} — Spot/Paper", C["text2"]))
        self.sym_desc_lbl.config(text=desc, fg=color)

        # Update coach mode label
        if hasattr(self, "_coach_mode_lbl"):
            strat = self.strategy_lib.get_active() if hasattr(self, "strategy_lib") else None
            strat_tag = f"  ·  {strat['name']}" if strat else ""
            if is_options:
                self._coach_mode_lbl.config(
                    text=f"🧠 {sym} 0DTE Options{strat_tag}", fg=C["text3"])
            else:
                self._coach_mode_lbl.config(
                    text=f"🧠 {sym} Spot{strat_tag}",
                    fg=C["orange"])

        # Update paper trading panel active label
        if hasattr(self, "_pt_active_sym_lbl"):
            self._pt_active_sym_lbl.config(text=f"▶  {sym}")
            self._pt_price_lbl.config(text="fetching…")

    def _tick_clock(self):
        """Update the live status panel every second."""
        from datetime import datetime, time as dtime, timezone, timedelta
        try:
            try:
                from zoneinfo import ZoneInfo
                now = datetime.now(ZoneInfo("America/Los_Angeles"))
            except Exception:
                # fallback: UTC-7 (PDT) or UTC-8 (PST)
                import time as _t
                is_dst = bool(_t.daylight) and _t.localtime().tm_isdst
                offset = timedelta(hours=-7 if is_dst else -8)
                now = datetime.now(timezone(offset))
            now_t = now.time()
            self._clk_lbl.config(text=now.strftime("%I:%M:%S %p PT"))

            # Kill zone definitions (PT)
            zones = [
                (dtime(6, 30),  dtime(8, 0),   "AM Kill Zone 🔥",  C["green"]),
                (dtime(8, 0),   dtime(10, 30),  "Dead Zone ☠️",     C["red"]),
                (dtime(10, 30), dtime(12, 0),   "PM Kill Zone 🔥",  C["green"]),
                (dtime(12, 0),  dtime(13, 0),   "Wind Down",        C["text3"]),
            ]
            next_starts = [
                (dtime(6, 30),  "AM Kill Zone"),
                (dtime(10, 30), "PM Kill Zone"),
            ]

            in_zone = False
            for start, end, label, color in zones:
                if start <= now_t < end:
                    self._kz_lbl.config(text=label, fg=color)
                    in_zone = True
                    # countdown to end
                    from datetime import timedelta
                    end_dt = now.replace(hour=end.hour, minute=end.minute, second=0)
                    diff = end_dt - now
                    m, s = divmod(int(diff.total_seconds()), 60)
                    self._cd_lbl.config(text=f"{m}m {s}s left", fg=color)
                    break

            if not in_zone:
                # find next kill zone
                self._kz_lbl.config(text="Market Closed" if now_t >= dtime(13,0) or now_t < dtime(4,0) else "Pre-Market", fg=C["text3"])
                best = None
                for start, label in next_starts:
                    from datetime import timedelta
                    start_dt = now.replace(hour=start.hour, minute=start.minute, second=0)
                    if start_dt < now:
                        start_dt += timedelta(days=1)
                    diff = start_dt - now
                    if best is None or diff < best[0]:
                        best = (diff, label)
                if best:
                    h, rem = divmod(int(best[0].total_seconds()), 3600)
                    m, s   = divmod(rem, 60)
                    if h > 0:
                        self._cd_lbl.config(text=f"{h}h {m}m to {best[1]}", fg=C["orange"])
                    else:
                        self._cd_lbl.config(text=f"{m}m {s}s to {best[1]}", fg=C["orange"])
        except Exception:
            pass
        self.root.after(1000, self._tick_clock)

    # ── Paper Trading methods ─────────────────────────────────

    def _pt_on_dropdown(self, selection: str):
        """Called when user picks from the dropdown."""
        if selection.startswith("──"):
            return   # section header — ignore
        sym = self._pt_label_to_sym.get(selection)
        if sym:
            self._pt_apply_symbol(sym, selection)

    def _pt_set_symbol(self):
        """Called when user types a custom symbol and hits Go / Enter."""
        sym = self._pt_sym_var.get().strip().upper()
        if not sym:
            return
        self._pt_sym_var.set("")
        self._pt_apply_symbol(sym, sym)

    def _pt_quick_market(self, symbol: str, label: str):
        self._pt_apply_symbol(symbol, label)

    def _pt_apply_symbol(self, symbol: str, label: str):
        if self.paper.state.get("position"):
            self.log("📄 Close your open position before switching markets.", "alert")
            return
        self.paper.set_symbol(symbol)
        from paper_trader import MARKETS
        display = MARKETS.get(symbol, (symbol,))[0]
        self._pt_active_sym_lbl.config(text=f"▶  {display}")
        self._pt_price_lbl.config(text="fetching…")
        self.log(f"📄 Paper market → {display}", "header")

        # Update coach mode indicator
        is_spot = self.analyzer.is_spot_symbol(symbol) if self.analyzer else True
        if is_spot:
            self._coach_mode_lbl.config(
                text=f"🧠 Coach mode: {display} Spot  (BUY / SELL / WAIT)",
                fg=C["orange"])
        else:
            self._coach_mode_lbl.config(
                text="🧠 Coach mode: SPY 0DTE Options",
                fg=C["text3"])

    def _pt_refresh(self):
        """Refresh all paper trading UI labels."""
        s = self.paper.stats()
        price = s.get("btc_price")
        if price:
            from paper_trader import MARKETS
            display = MARKETS.get(self.paper.symbol, (self.paper.symbol,))[0]
            fmt = f"${price:,.2f}" if price < 100 else f"${price:,.0f}"
            self._pt_price_lbl.config(text=f"{display}  {fmt}")

        self._pt_cash.config( text=f"${s['cash']:,.2f}")
        self._pt_total.config(text=f"${s['total_value']:,.2f}")

        pnl = s["open_pnl"]
        pct = s["open_pct"]
        pnl_color = C["green"] if pnl >= 0 else C["red"]
        sign = "+" if pnl >= 0 else ""
        self._pt_opnl.config(
            text=f"{sign}${pnl:.2f} ({sign}{pct:.1f}%)" if s["position"] else "—",
            fg=pnl_color)

        wr = s["win_rate"]
        self._pt_wr.config(text=f"{wr}%" if s["num_trades"] else "—",
                           fg=C["green"] if wr >= 50 else C["red"])

        ot = s["position"]
        if ot:
            sym  = ot.get("symbol", self.paper.symbol)
            qty  = ot.get("qty", ot.get("btc_qty", 0))
            ep   = ot.get("entry_price", 0)
            fmt  = f"${ep:,.2f}" if ep < 100 else f"${ep:,.0f}"
            self._pt_pos_lbl.config(
                text=f"LONG {qty:.6f} {sym} @ {fmt}",
                fg=C["orange"])
        else:
            self._pt_pos_lbl.config(text="No open position", fg=C["text3"])

        n = s["num_trades"]
        self._pt_trades_lbl.config(
            text=f"{n} trade{'s' if n!=1 else ''}  |  {s['wins']}W {s['losses']}L")

    def _pt_buy(self):
        try:
            amt = float(self._pt_amt_var.get() or 100)
        except ValueError:
            self.log("Paper trade: enter a valid dollar amount", "alert")
            return
        result = self.paper.buy(amt)
        if result["ok"]:
            self.log(f"📄 PAPER BUY  ${amt:.0f} of BTC @ ${result['entry_price']:,.0f}"
                     f"  ({result['btc_qty']:.6f} BTC)", "signal_buy")
            self._pt_refresh()
        else:
            self.log(f"📄 Paper buy failed: {result['error']}", "alert")

    def _pt_sell(self):
        result = self.paper.sell()
        if result["ok"]:
            pnl = result["pnl"]
            sign = "+" if pnl >= 0 else ""
            tag = "signal_buy" if pnl >= 0 else "signal_sell"
            self.log(f"📄 PAPER SELL @ ${result['exit_price']:,.0f}"
                     f"  P&L: {sign}${pnl:.2f}", tag)
            self._pt_refresh()
        else:
            self.log(f"📄 Paper sell failed: {result['error']}", "alert")

    def _pt_on_close(self, trade: dict):
        self._pt_refresh()

    def _pt_reset(self):
        self.paper.reset()
        self.log("📄 Paper account reset to $500.00", "header")
        self._pt_refresh()

    def _update_setup_panel(self, trade_info: dict):
        """Populate the live setup panel from the latest signal."""
        if not trade_info:
            for attr in ("_setup_dir","_setup_entry","_setup_sl","_setup_tp1","_setup_tp2","_setup_opt","_setup_rr"):
                try: getattr(self, attr).config(text="—")
                except: pass
            return
        opt    = trade_info.get("options_play", "—")
        entry  = trade_info.get("entry_price", 0)
        sl     = trade_info.get("stop_loss", 0)
        tp1    = trade_info.get("take_profit_1", 0)
        tp2    = trade_info.get("take_profit_2", 0)
        rr     = trade_info.get("risk_reward", "N/A")
        dir_   = trade_info.get("direction", "—")
        opt_t  = trade_info.get("option_type", "")
        strike = trade_info.get("strike", "")

        # Normalize: action might be raw "BUY"/"SELL" or already "BUY CALLS"/"BUY PUTS"
        dir_up = dir_.upper()
        is_puts  = "PUT"  in dir_up or dir_up == "SELL"
        is_calls = "CALL" in dir_up or (dir_up == "BUY" and "PUT" not in dir_up)
        is_wait  = "WAIT" in dir_up or (not is_puts and not is_calls)

        if is_puts:
            display_dir = "📉  BUY PUTS"
            dir_color   = C["red"]
        elif is_calls:
            display_dir = "📈  BUY CALLS"
            dir_color   = C["green"]
        else:
            display_dir = "⏳  WAIT"
            dir_color   = C["text2"]

        self._setup_dir.config(text=display_dir, fg=dir_color)

        # Entry label — puts entry is a ceiling (price needs to rally UP to it, then reject)
        # calls entry is a floor (price needs to pull DOWN to it, then bounce)
        if entry:
            if is_puts:
                self._setup_entry.config(
                    text=f"{entry:.2f}  ← wait for price to rally here, then SHORT",
                    fg=C["red"])
            elif is_calls:
                self._setup_entry.config(
                    text=f"{entry:.2f}  ← wait for price to pull back here, then LONG",
                    fg=C["green"])
            else:
                self._setup_entry.config(text=f"{entry:.2f}", fg=C["blue"])
        else:
            self._setup_entry.config(text="—", fg=C["text3"])

        self._setup_sl.config(   text=f"{sl:.2f}"    if sl    else "—")
        self._setup_tp1.config(  text=f"{tp1:.2f}"   if tp1   else "—")
        self._setup_tp2.config(  text=f"{tp2:.2f}"   if tp2   else "—")
        # Always show as "BUY CALLS" or "BUY PUTS" — never raw "SELL"
        if strike and opt_t:
            self._setup_opt.config(text=f"${strike}  {'CALL' if is_calls else 'PUT'}")
        elif is_puts:
            self._setup_opt.config(text="BUY A PUT OPTION 📉")
        elif is_calls:
            self._setup_opt.config(text="BUY A CALL OPTION 📈")
        else:
            self._setup_opt.config(text=opt)
        self._setup_rr.config(text=str(rr))

    # ──────────────────────────────────────────────────────────
    #  Signal Lock + Consecutive Confirmation + Popup Alert
    # ──────────────────────────────────────────────────────────

    def _check_signal_lock(self, action: str, spot_info: dict, analysis: dict):
        """
        Lock signal on first clean BUY or SELL.
        WAIT does NOT break the lock — only a true reversal (BUY→SELL or SELL→BUY) resets it.
        Once locked the popup fires once; it won't re-fire until the lock is released.
        """
        # If already locked in same direction — just refresh the info, don't re-popup
        if self._locked_signal and self._locked_signal.get("action") == action:
            self._locked_signal = {**spot_info, "action": action}
            self.log(f"🔒 Signal still locked: {'BUY CALLS 📈' if action == 'BUY' else 'BUY PUTS 📉'} — holding position", "info")
            if not self._alert_shown:
                self._alert_shown = True
                self._show_signal_popup(action, spot_info)
            return

        # Reversal detected — release old lock and start fresh
        if self._locked_signal and self._locked_signal.get("action") != action:
            old = self._locked_signal.get("action","")
            self.log(f"🔄 Reversal: {old} → {action} — releasing old lock", "alert")
            self._locked_signal   = None
            self._consecutive_buf = []
            self._alert_shown     = False

        # Accumulate confirmations (WAIT is ignored by callers — only BUY/SELL reaches here)
        self._consecutive_buf.append(action)
        if len(self._consecutive_buf) > self._CONFIRM_COUNT:
            self._consecutive_buf = self._consecutive_buf[-self._CONFIRM_COUNT:]

        confirmed = (
            len(self._consecutive_buf) >= self._CONFIRM_COUNT
            and len(set(self._consecutive_buf)) == 1
        )

        if confirmed:
            self._locked_signal = {**spot_info, "action": action}
            self._alert_shown   = False
            direction_label = "BUY CALLS 📈" if action == "BUY" else "BUY PUTS 📉"
            self.log(f"🔒 SIGNAL LOCKED: {direction_label} — committed!", "alert")
            self._alert_shown = True
            self._show_signal_popup(action, spot_info)
        else:
            same = sum(1 for s in self._consecutive_buf if s == action)
            self.log(f"⏳ Signal building: {action} {same}/{self._CONFIRM_COUNT}", "info")

    def _show_signal_popup(self, action: str, spot_info: dict):
        """
        Large, eye-catching popup card with all trade details and one-click Execute.
        Stays open until user closes or executes.
        """
        popup = tk.Toplevel(self.root)
        popup.title("⚡ TRADE SIGNAL CONFIRMED")
        popup.configure(bg=C["bg"])
        popup.resizable(False, False)
        popup.attributes("-topmost", True)

        # Centre on screen
        popup.update_idletasks()
        sw = popup.winfo_screenwidth()
        sh = popup.winfo_screenheight()
        w, h = 500, 560
        popup.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        is_buy    = (action == "BUY")
        color     = C["green"] if is_buy else C["red"]
        label     = "BUY CALLS  📈" if is_buy else "BUY PUTS  📉"
        bg_accent = "#0d2b1a" if is_buy else "#2b0d0d"

        sym     = spot_info.get("symbol", "—")
        entry   = spot_info.get("entry",  "—")
        stop    = spot_info.get("stop_loss", "—")
        tp1     = spot_info.get("take_profit_1", "—")
        tp2     = spot_info.get("take_profit_2", "—")
        rr      = spot_info.get("risk_reward", "—")
        opt     = spot_info.get("options_play", "—")
        strike  = spot_info.get("strike", "")
        conf    = spot_info.get("confidence", "—")

        # Header banner
        hdr = tk.Frame(popup, bg=color, pady=14)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=label, font=("SF Pro Display", 26, "bold"),
                 fg="white", bg=color).pack()
        tk.Label(hdr, text=f"Symbol: {sym}  |  Confidence: {conf}",
                 font=("SF Pro Display", 12), fg="white", bg=color).pack()

        # Details grid
        det = tk.Frame(popup, bg=bg_accent, padx=24, pady=16)
        det.pack(fill=tk.X, padx=0)

        def row(label_txt, value_txt, value_color=C["text"]):
            fr = tk.Frame(det, bg=bg_accent)
            fr.pack(fill=tk.X, pady=3)
            tk.Label(fr, text=label_txt, font=("SF Pro Display", 11),
                     fg=C["text3"], bg=bg_accent, width=18, anchor="w").pack(side=tk.LEFT)
            tk.Label(fr, text=str(value_txt), font=("SF Pro Display", 12, "bold"),
                     fg=value_color, bg=bg_accent, anchor="w").pack(side=tk.LEFT)

        entry_label = f"≥ {entry}  (buy at or below)" if is_buy else f"≤ {entry}  (sell at or above)"
        row("Entry Zone:",    entry_label,   color)
        row("Stop Loss:",     f"{stop}",     C["red"])
        row("Take Profit 1:", f"{tp1}",      C["green"])
        row("Take Profit 2:", f"{tp2}",      C["green"])
        row("Risk : Reward:", f"{rr}",       C["blue"])
        row("Options Play:",  f"${strike} {opt}" if strike else opt, color)

        # Divider
        tk.Frame(popup, bg=C["border"], height=1).pack(fill=tk.X, padx=16, pady=4)

        # Reasoning summary
        reasoning = spot_info.get("reasoning", "")
        if reasoning:
            rbox = tk.Frame(popup, bg=C["card"], padx=16, pady=10)
            rbox.pack(fill=tk.X, padx=16)
            tk.Label(rbox, text="📝 AI Reasoning", font=("SF Pro Display", 10, "bold"),
                     fg=C["text3"], bg=C["card"]).pack(anchor="w")
            short = reasoning[:200] + ("…" if len(reasoning) > 200 else "")
            tk.Label(rbox, text=short, font=("SF Pro Display", 10),
                     fg=C["text"], bg=C["card"], wraplength=440, justify=tk.LEFT).pack(anchor="w")

        # Buttons
        btn_fr = tk.Frame(popup, bg=C["bg"], pady=16)
        btn_fr.pack(fill=tk.X, padx=24)

        def execute_now():
            popup.destroy()
            self.open_trade_dialog()

        tk.Button(btn_fr, text="⚡  EXECUTE NOW",
                  font=("SF Pro Display", 15, "bold"),
                  fg="white", bg=color, activebackground=color,
                  relief=tk.FLAT, cursor="hand2", padx=20, pady=12,
                  command=execute_now).pack(fill=tk.X, pady=(0, 8))

        tk.Button(btn_fr, text="✕  Dismiss",
                  font=("SF Pro Display", 11),
                  fg=C["text3"], bg=C["card"], relief=tk.FLAT,
                  cursor="hand2", padx=10, pady=6,
                  command=popup.destroy).pack(fill=tk.X)

        # Try to play system bell
        try:
            popup.bell()
        except Exception:
            pass

        self.log(f"🚨 POPUP SHOWN — {label} | Entry: {entry} | SL: {stop} | TP1: {tp1}", "alert")

    def _load_saved_settings(self):
        self.api_key_var.set(self.config.get("api_key", ""))
        self.interval_var.set(str(self.config.get("interval_seconds", 10)))
        self.context_var.set(self.config.get("extra_context", ""))
        self.tt_user_var.set(self.config.get("tt_username", ""))
        self.tt_pass_var.set(self.config.get("tt_password", ""))
        region = self.config.get("region")
        if region:
            self.capture.set_region(
                region["left"], region["top"],
                region["width"], region["height"])
            self.region_lbl.config(
                text=(f"📺  Saved  {region['width']}×{region['height']}"
                      f" at ({region['left']}, {region['top']})"),
                fg=C["green"])
        if self.config.get("alert_rules"):
            self.alerts.update_rules(self.config["alert_rules"])

    def _save_current_settings(self):
        self.config["api_key"]          = self.api_key_var.get().strip()
        self.config["interval_seconds"] = int(self.interval_var.get() or 10)
        self.config["extra_context"]    = self.context_var.get().strip()
        if self.capture.region:
            self.config["region"] = self.capture.region
        save_config(self.config)

    # ──────────────────────────────────────────────────────────
    #  Logging
    # ──────────────────────────────────────────────────────────

    def log(self, text: str, tag: str = None):
        self.output_text.insert(tk.END, text + "\n", tag)
        self.output_text.see(tk.END)

    # ──────────────────────────────────────────────────────────
    #  Region selection
    # ──────────────────────────────────────────────────────────

    def _set_monitor_quick(self, monitor):
        """Instantly set capture to a full monitor. No popup needed."""
        if monitor is None:
            # Single monitor / primary fallback
            if MSS_AVAILABLE:
                import mss as _mss
                with _mss.mss() as sct:
                    m = sct.monitors[1]
                    l, t, w, h = m["left"], m["top"], m["width"], m["height"]
            else:
                l, t, w, h = 0, 0, 1920, 1080
            label = "Primary Monitor"
        else:
            l, t, w, h = monitor["left"], monitor["top"], monitor["width"], monitor["height"]
            label = monitor["label"]

        self.capture.set_region(l, t, w, h)
        self.config["region"] = {"left": l, "top": t, "width": w, "height": h}
        self.region_lbl.config(
            text=f"📺  {label}  ({w}×{h})", fg=C["green"])
        self.log(f"📺  Screen set to {label}  {w}×{h}")

        # Highlight the active button
        for idx, btn in self._screen_btns.items():
            is_active = (monitor is not None and idx == monitor.get("index"))
            btn.configure(bg=C["blue"] if is_active else C["btn"])

        self._save_current_settings()

    def select_custom_region(self):
        """Let user drag-draw a custom region (original behaviour)."""
        def on_selected(l, t, w, h):
            self.capture.set_region(l, t, w, h)
            self.config["region"] = {"left": l, "top": t, "width": w, "height": h}
            self.region_lbl.config(
                text=f"📍  Custom  {w}×{h} at ({l}, {t})", fg=C["orange"])
            self.log(f"Custom region set: {w}×{h} at ({l}, {t})")
            self.root.deiconify()
            # Unhighlight monitor buttons since custom is active
            for btn in self._screen_btns.values():
                btn.configure(bg=C["btn"])
            self._save_current_settings()

        self.root.iconify()
        time.sleep(0.3)
        RegionSelector(on_selected)

    def select_region(self):
        """Legacy alias — just open custom region selector."""
        self.select_custom_region()

    # ──────────────────────────────────────────────────────────
    #  Analysis
    # ──────────────────────────────────────────────────────────

    def _init_analyzer(self) -> bool:
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showerror("API Key Required",
                "Please enter your Anthropic API key.")
            return False
        try:
            self.analyzer = ChartAnalyzer(
                api_key=key,
                model=self.config.get("model", "claude-sonnet-4-5-20250929"))
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to init analyzer:\n{e}")
            return False

    def analyze_once(self):
        if not self.capture.region:
            messagebox.showwarning("No Region",
                "Select a screen region first.")
            return
        if not self.analyzer and not self._init_analyzer():
            return
        self._save_current_settings()
        self.status_var.set("Analyzing…")
        self.root.update()

        def _run():
            try:
                img_b64  = self.capture.capture_to_base64()
                sym      = self.symbol_var.get()
                pt_sym   = self.paper.symbol  # paper trading market

                strat_inj = self._get_strategy_injection()
                active_s  = self.strategy_lib.get_active()
                strat_name = active_s["name"] if active_s else "ICT/SMC"

                # Use the Capture section symbol for analysis (independent of paper trading)
                analysis_sym = sym if sym != "AUTO" else "AUTO"
                if self.analyzer.is_spot_symbol(analysis_sym) or analysis_sym == "AUTO":
                    self.log(f"\n── Spot Analysis  [{analysis_sym}]  Strategy: {strat_name} ──", "header")
                    # Build memory context from last analysis
                    prev = self._last_analysis
                    memory_ctx = ""
                    if self._locked_signal:
                        # Iron-clad lock instruction — AI cannot override this
                        locked_action = self._locked_signal.get("action", "BUY")
                        locked_entry  = self._locked_signal.get("entry_price", "?")
                        locked_stop   = self._locked_signal.get("stop_loss", "?")
                        locked_dir    = "BUY CALLS" if locked_action == "BUY" else "BUY PUTS"
                        memory_ctx = (
                            f"\n\n🔒 SIGNAL IS LOCKED — DO NOT CHANGE THE DIRECTION.\n"
                            f"The trader has committed to: {locked_dir}.\n"
                            f"Entry zone: {locked_entry}  |  Stop loss: {locked_stop}.\n"
                            f"YOUR ONLY JOB NOW: confirm if price is at or inside the entry zone.\n"
                            f"- If price is AT or NEAR the entry zone → action = {locked_action} (enter now).\n"
                            f"- If price has NOT reached entry yet → action = WAIT (but keep same direction).\n"
                            f"- If price has CLOSED beyond {locked_stop} → you may release the lock.\n"
                            f"DO NOT flip to the opposite direction. DO NOT change entry/stop/targets unless "
                            f"price has definitively closed beyond the stop loss level. Stay committed."
                        )
                    elif prev and prev.get("symbol","").upper() == analysis_sym.upper().replace("AUTO",""):
                        memory_ctx = (
                            f"\n\nPREVIOUS SCAN: bias={prev.get('timeframe_bias','?')} "
                            f"action={prev.get('action','?')} entry={prev.get('entry_price','?')} "
                            f"stop={prev.get('stop_loss','?')}. "
                            f"Keep the same entry/stop/targets unless price has closed beyond the stop."
                        )
                    extra = (self.context_var.get().strip() + memory_ctx).strip()
                    analysis = self.analyzer.analyze_spot(
                        img_b64, symbol=analysis_sym,
                        extra_context=extra,
                        strategy_injection=strat_inj)
                    text = self._format_spot_analysis(analysis)
                else:
                    self.log(f"\n── Analysis  [{sym}]  Strategy: {strat_name} ──", "header")
                    analysis = self.analyzer.analyze(
                        img_b64, self.context_var.get().strip(), symbol=sym,
                        strategy_injection=strat_inj)
                    text = format_analysis(analysis)

                self.root.after(0, lambda: self._display_analysis(
                    analysis, text, img_b64))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"Error: {e}", "alert"))
                self.root.after(0, lambda: self.status_var.set("Error"))

        threading.Thread(target=_run, daemon=True).start()

    def _format_spot_analysis(self, a: dict) -> str:
        """Format spot/paper analysis result for the output log."""
        def fmt(v):
            if v is None: return "—"
            try:
                v = float(v)
                return f"{v:,.4f}" if v < 100 else f"{v:,.2f}"
            except: return str(v)

        action  = a.get("action", "WAIT")
        sym     = a.get("symbol", a.get("_symbol", "?"))
        conf    = a.get("confidence", "")
        setup   = a.get("setup_type", "")
        rr      = a.get("risk_reward", "")
        bias    = a.get("timeframe_bias", "")
        inv     = a.get("invalidation", "")
        steps   = a.get("steps_complete", {})

        # Auto-detected strategy
        detected = a.get("detected_strategy", {})
        det_label = f"  🤖 {detected['name']}" if detected and detected.get("name") else ""

        emoji = "📈" if action == "BUY" else "📉" if action == "SELL" else "⏸️"
        lines = [
            f"\n{'═'*52}",
            f"{emoji}  {action}  {sym}  [{conf}]  |  {setup}",
        ]
        if det_label:
            lines.append(det_label)
            if detected.get("reason"):
                lines.append(f"     ↳ {detected['reason']}")
        lines += [
            f"{'═'*52}",
            f"  Bias:      {bias}",
            f"  Price:     {fmt(a.get('current_price'))}",
            f"  Entry:     {fmt(a.get('entry_price'))}",
            f"  Stop:      {fmt(a.get('stop_loss'))}",
            f"  Target 1:  {fmt(a.get('take_profit_1'))}",
            f"  Target 2:  {fmt(a.get('take_profit_2'))}",
            f"  R:R        {rr}",
            f"  Invalidate if: {inv}",
        ]

        # Visual scan section
        vs = a.get("visual_scan", {})
        if vs:
            lines.append(f"\n  ── VISUAL SCAN ──")
            if vs.get("candle_character"):
                lines.append(f"  Candles:   {vs['candle_character']}")
            if vs.get("rejection_candles"):
                lines.append(f"  Rejection: {vs['rejection_candles']}")
            if vs.get("volume_note"):
                lines.append(f"  Volume:    {vs['volume_note']}")
            if vs.get("market_structure"):
                lines.append(f"  Structure: {vs['market_structure']}")
            if vs.get("choch_level"):
                lines.append(f"  CHoCH:     {fmt(vs['choch_level'])}")
            if vs.get("bos_level"):
                lines.append(f"  BOS:       {fmt(vs['bos_level'])}")
            fvgs = vs.get("fvgs") or vs.get("fvgs_visible", [])
            if fvgs:
                lines.append(f"  FVGs:")
                for fvg in fvgs[:4]:
                    fresh = "FRESH" if fvg.get("fresh") or not fvg.get("mitigated") else "mitigated"
                    tf = fvg.get("tf") or fvg.get("timeframe","")
                    lines.append(f"    {tf}  {fmt(fvg.get('bottom'))}–{fmt(fvg.get('top'))}  [{fresh}]")
            obs = vs.get("order_blocks") or vs.get("order_blocks_visible", [])
            if obs:
                lines.append(f"  Order Blocks:")
                for ob in obs[:3]:
                    tf = ob.get("tf") or ob.get("timeframe","")
                    lines.append(f"    {ob.get('type','').upper()}  {tf}  {fmt(ob.get('low'))}–{fmt(ob.get('high'))}")

        if steps:
            lines.append(f"\n  ── 5-STEP SEQUENCE ──")
            lines.append(f"  1. Bias:    {steps.get('step1_bias', '—')}")
            lines.append(f"  2. Target:  {steps.get('step2_liquidity_target', '—')}")
            lines.append(f"  3. Sweep:   {steps.get('step3_sweep', '—')}")
            lines.append(f"  4. BOS:     {steps.get('step4_bos', '—')}")
            lines.append(f"  5. Entry:   {steps.get('step5_entry', '—')}")

        lines.append(f"\n  {a.get('summary', a.get('reasoning', ''))}")
        lines.append(f"{'─'*52}")
        return "\n".join(lines)

    def _display_analysis(self, analysis: dict, result_text: str,
                          img_b64: str = None):
        # Spot mode (BTC, ETH, stocks etc.)
        if analysis.get("_mode") == "SPOT":
            action = analysis.get("action", "WAIT")
            tag = ("signal_buy"  if action == "BUY"
                   else "signal_sell" if action == "SELL"
                   else "alert"       if action == "READY"
                   else None)
            self.log(result_text, tag)
            self.analysis_count += 1
            # Save as memory for next scan so AI doesn't flip bias randomly
            self._last_analysis = analysis
            # ── Track ICT setup build progress across scans ───────────────────
            _agents_data = analysis.get("_agents", {})
            _entry_data  = _agents_data.get("entry", {}) if _agents_data else {}
            _bias_data   = _agents_data.get("bias",  {}) if _agents_data else {}
            _new_zone    = _entry_data.get("entry_zone", 0)
            _new_phase   = _bias_data.get("phase", analysis.get("timeframe_bias", ""))
            _new_missing = _entry_data.get("missing_step", None)
            _new_checklist = {
                "bos":      _entry_data.get("checklist_bos", False),
                "pullback": _entry_data.get("checklist_pullback", False),
                "fvg_ob":   _entry_data.get("checklist_fvg_ob", False),
                "at_zone":  _entry_data.get("checklist_at_zone", False),
                "confirm":  _entry_data.get("checklist_confirmation", False),
                "path":     _entry_data.get("checklist_clear_path", False),
            }
            # Reset setup scan count if zone changed significantly
            if (self._ict_setup_zone and _new_zone and
                    abs(float(_new_zone or 0) - float(self._ict_setup_zone or 0)) > 5):
                self._ict_setup_scans = 0
            if _new_zone:
                self._ict_setup_zone = _new_zone
                self._ict_setup_scans += 1
            else:
                self._ict_setup_scans = 0
            if _new_phase:
                self._ict_last_phase = _new_phase
            self._ict_missing_step   = _new_missing
            self._ict_checklist_prev = _new_checklist
            self._ict_setup_type     = _entry_data.get("entry_type", self._ict_setup_type)
            if img_b64:
                self.update_chart_preview(img_b64)
            # ── Refresh Agents tab on every scan ─────────────────────────────
            try:
                self._update_agents_tab(analysis)
            except Exception:
                pass
            # Update Live Status panel with spot levels
            action = analysis.get("action", "WAIT")
            # Use AI-detected symbol (e.g. "QQQ") — never show "AUTO" to user
            detected_sym = analysis.get("symbol", "") or ""
            if not detected_sym or detected_sym.upper() == "AUTO":
                detected_sym = self.symbol_var.get().split("—")[0].strip()
            if detected_sym.upper() == "AUTO":
                detected_sym = "SPY"   # fallback
            # Translate BUY/SELL/READY to options language so user isn't confused
            bias = analysis.get("timeframe_bias", "")

            # ── Bias stability lock ───────────────────────────────────────────
            # Prevent flip-flopping: HTF bias must be seen N times in a row
            # before it replaces the confirmed bias.
            new_bias = bias  # what the AI just reported
            if new_bias in ("BULLISH", "BEARISH"):
                if self._confirmed_bias is None:
                    # First scan — accept immediately
                    self._confirmed_bias = new_bias
                    self._bias_candidate = new_bias
                    self._bias_candidate_count = 1
                elif new_bias == self._confirmed_bias:
                    # Same as confirmed — reinforce, reset candidate
                    self._bias_candidate = new_bias
                    self._bias_candidate_count = self._BIAS_CONFIRM_NEEDED
                elif new_bias == self._bias_candidate:
                    # Candidate building up
                    self._bias_candidate_count += 1
                    if self._bias_candidate_count >= self._BIAS_CONFIRM_NEEDED:
                        old = self._confirmed_bias
                        self._confirmed_bias = new_bias
                        self._bias_candidate_count = self._BIAS_CONFIRM_NEEDED
                        self.log(f"   🔄 Bias flipped: {old} → {new_bias} "
                                 f"(confirmed after {self._BIAS_CONFIRM_NEEDED} scans)", "alert")
                else:
                    # Brand new opposite candidate — start count from 1
                    self._bias_candidate = new_bias
                    self._bias_candidate_count = 1

                # Override action if it conflicts with CONFIRMED bias
                if self._confirmed_bias and action in ("BUY", "SELL", "READY",
                                                        "SCALP_BUY", "SCALP_SELL"):
                    bias_ok = (
                        (action in ("BUY", "SCALP_BUY") and self._confirmed_bias == "BULLISH") or
                        (action in ("SELL", "SCALP_SELL") and self._confirmed_bias == "BEARISH") or
                        (action == "READY")   # READY is directional via timeframe_bias below
                    )
                    # For READY, check if bias matches
                    if action == "READY" and self._confirmed_bias != new_bias:
                        self.log(f"   🔒 Bias lock — READY signal ignored "
                                 f"({new_bias} conflicts with locked {self._confirmed_bias})", "info")
                        action = "WAIT"
                    elif not bias_ok and action in ("BUY", "SELL", "SCALP_BUY", "SCALP_SELL"):
                        self.log(f"   🔒 Bias lock — {action} signal ignored "
                                 f"({new_bias} conflicts with locked {self._confirmed_bias})", "info")
                        action = "WAIT"

            # ── If in active trade, ONLY allow management actions ────────────
            MANAGEMENT_ACTIONS = {"HOLD", "MOVE_STOP_BE", "TAKE_PROFIT", "EXIT_NOW"}
            if self._active_trade and action not in MANAGEMENT_ACTIONS:
                # AI returned an entry signal while we're already in a trade — ignore it
                self.log(f"   [In trade — ignoring {action} signal]", "info")
                return

            # ── Trade management actions (when in active trade) ──────────────
            if action == "HOLD":
                self._setup_dir.config(text="🟢  HOLD — Stay In", fg=C["green"])
                self.log("🟢  HOLD — price moving in your favor. Stay in the trade.", "signal_buy")
                return
            elif action == "MOVE_STOP_BE":
                self._setup_dir.config(text="⚙️  MOVE STOP → B/E", fg=C["blue"])
                self.log("⚙️  MOVE STOP TO BREAKEVEN — Target 1 reached. Lock in your floor!", "alert")
                self._play_alert("ALERT")
                return
            elif action == "TAKE_PROFIT":
                self._setup_dir.config(text="💰  TAKE PROFIT!", fg=C["green"])
                self.log("💰  TAKE PROFIT — price at target. Consider closing or scaling out!", "alert")
                self._play_alert("BUY")
                return
            elif action == "EXIT_NOW":
                self._setup_dir.config(text="🚨  EXIT NOW!", fg=C["red"])
                self.log("🚨  EXIT NOW — stop threatened or setup failed. Get out!", "signal_sell")
                self._play_alert("EXIT")
                return

            if action == "SCALP_BUY":
                self._setup_dir.config(text="⚡ SCALP — BUY CALLS", fg=C["blue"])
                self.log(f"⚡ 5M SCALP — BUY CALLS on {detected_sym}! "
                         f"Sell-side liquidity swept, sharp reversal. Quick scalp, short hold.", "alert")
                self._play_alert("SCALP")
                spot_info = {
                    **({} if not self.last_trade_info else self.last_trade_info),
                    "direction": "⚡ SCALP — BUY CALLS",
                    "option_type": "CALL",
                    "symbol": detected_sym,
                    "entry_price":   analysis.get("entry_price", 0),
                    "stop_loss":     analysis.get("stop_loss", 0),
                    "take_profit_1": analysis.get("take_profit_1", 0),
                    "take_profit_2": analysis.get("take_profit_2", 0),
                    "strike":        round(analysis.get("current_price", 0)),
                    "expiration":    datetime.now().strftime("%m%d%Y"),
                    "options_play":  f"SCALP CALLS {detected_sym}",
                }
                self.last_trade_info = spot_info
                self._update_setup_panel(spot_info)
                return
            elif action == "SCALP_SELL":
                self._setup_dir.config(text="⚡ SCALP — BUY PUTS", fg=C["blue"])
                self.log(f"⚡ 5M SCALP — BUY PUTS on {detected_sym}! "
                         f"Buy-side liquidity swept, sharp rejection. Quick scalp, short hold.", "alert")
                self._play_alert("SCALP")
                spot_info = {
                    **({} if not self.last_trade_info else self.last_trade_info),
                    "direction": "⚡ SCALP — BUY PUTS",
                    "option_type": "PUT",
                    "symbol": detected_sym,
                    "entry_price":   analysis.get("entry_price", 0),
                    "stop_loss":     analysis.get("stop_loss", 0),
                    "take_profit_1": analysis.get("take_profit_1", 0),
                    "take_profit_2": analysis.get("take_profit_2", 0),
                    "strike":        round(analysis.get("current_price", 0)),
                    "expiration":    datetime.now().strftime("%m%d%Y"),
                    "options_play":  f"SCALP PUTS {detected_sym}",
                }
                self.last_trade_info = spot_info
                self._update_setup_panel(spot_info)
                return
            elif action == "BUY":
                display_dir  = "BUY CALLS"
                display_play = f"BUY CALLS {detected_sym}"
            elif action == "SELL":
                display_dir  = "BUY PUTS"
                display_play = f"BUY PUTS {detected_sym}"
            elif action == "READY":
                if bias == "BEARISH":
                    display_dir  = "⚠️ GET READY — BUY PUTS"
                    display_play = f"READY PUTS {detected_sym}"
                else:
                    display_dir  = "⚠️ GET READY — BUY CALLS"
                    display_play = f"READY CALLS {detected_sym}"
                self.log(f"🔔 SETUP CONFIRMED — GET READY! Steps 1-4 done. Entry zone approaching — finger on the button!", "alert")
            else:
                display_dir  = "WAIT"
                display_play = f"WAIT {detected_sym}"
            # Suggest ATM strike based on current price
            cur_price = analysis.get("current_price", 0)
            atm_strike = round(cur_price) if cur_price else None
            spot_info = {
                "direction":     display_dir,
                "option_type":   "CALL" if action in ("BUY","READY") and bias != "BEARISH" else "PUT" if action in ("SELL","READY") and bias == "BEARISH" else "",
                "symbol":        detected_sym,
                "entry_price":   analysis.get("entry_price", 0),
                "stop_loss":     analysis.get("stop_loss", 0),
                "take_profit_1": analysis.get("take_profit_1", 0),
                "take_profit_2": analysis.get("take_profit_2", 0),
                "risk_reward":   analysis.get("risk_reward", "N/A"),
                "options_play":  display_play,
                "strike":        atm_strike,
                "expiration":    datetime.now().strftime("%m%d%Y"),
                "confidence":    analysis.get("confidence", "MEDIUM"),
                "setup":         analysis.get("setup_type", "FVG_ENTRY"),
                "strike_type":   "ATM",
                "reasoning":     analysis.get("reasoning", ""),
                "max_hold":      "",
            }
            self._update_setup_panel(spot_info)
            if action in ("BUY", "SELL"):
                self.last_trade_info = spot_info
                self._play_alert(action)   # BUY → Glass.aiff, SELL → Sosumi.aiff
                self._check_signal_lock(action, spot_info, analysis)
            elif action == "READY":
                # Setup confirmed — lock direction so it can't flip next scan
                self.last_trade_info = spot_info
                self._play_alert("READY")
                # Lock the bias so a WAIT or opposite signal can't undo the setup
                if not self._locked_signal:
                    ready_action = "BUY" if self._confirmed_bias == "BULLISH" else "SELL"
                    self._locked_signal = {
                        "action":      ready_action,
                        "entry_price": spot_info.get("entry_price", 0),
                        "stop_loss":   spot_info.get("stop_loss", 0),
                        "invalidation":spot_info.get("stop_loss", 0),
                        "locked_at":   "READY",
                    }
                    self.log(f"   🔒 Setup locked — direction held until stop hit", "info")
            elif action == "WAIT":
                # Reset consecutive buffer on WAIT only if locked signal is invalidated
                if self._locked_signal:
                    cur_price = analysis.get("current_price", 0)
                    inv = self._locked_signal.get("invalidation", 0)
                    if inv and cur_price:
                        locked_action = self._locked_signal.get("action","")
                        if locked_action == "BUY" and cur_price < float(inv):
                            self._locked_signal = None
                            self._consecutive_buf = []
                            self._alert_shown = False
                            self.log("🔓 Signal lock released — price hit invalidation", "alert")
                        elif locked_action == "SELL" and cur_price > float(inv):
                            self._locked_signal = None
                            self._consecutive_buf = []
                            self._alert_shown = False
                            self.log("🔓 Signal lock released — price hit invalidation", "alert")
                # ── Keep Execute Trade pre-filled even during WAIT ────────────
                # Merge: keep best non-zero price levels (WAIT scans often return
                # 0 for entry/stop/targets, so preserve the last good values)
                if self._confirmed_bias:
                    _wait_opt = "CALL" if self._confirmed_bias == "BULLISH" else "PUT"
                    _wait_dir = "BUY CALLS" if self._confirmed_bias == "BULLISH" else "BUY PUTS"
                    _prev = self.last_trade_info or {}
                    _merged = {**spot_info}
                    # For price levels, keep previous non-zero value if new scan returned 0
                    for _key in ("entry_price", "stop_loss", "take_profit_1",
                                 "take_profit_2", "risk_reward", "setup",
                                 "strike", "reasoning"):
                        if not _merged.get(_key) and _prev.get(_key):
                            _merged[_key] = _prev[_key]
                    _merged["option_type"]  = _wait_opt
                    _merged["direction"]    = _wait_dir
                    _merged["options_play"] = f"{_wait_dir} {detected_sym}"
                    self.last_trade_info = _merged
            return

        signal = analysis.get("signals", {}).get("overall", "")
        tag = ("signal_buy" if "BUY" in signal
               else "signal_sell" if "SELL" in signal else None)
        self.log(result_text, tag)
        self.analysis_count += 1

        # Update right panel
        if img_b64:
            self.update_chart_preview(img_b64)
        self.add_signal_to_history(analysis)

        # Trade action — SPX 0DTE options signal
        ta = analysis.get("trade_action", {})
        if ta and ta.get("should_trade") == "YES_ENTER_NOW":
            options_play  = ta.get("options_play", "")      # "BUY_CALLS" or "BUY_PUTS"
            opt_type      = "CALL" if "CALL" in options_play.upper() else "PUT"
            direction     = "BUY" if "BUY" in options_play.upper() else "SELL"
            strike        = ta.get("suggested_strike")
            entry_spx     = ta.get("entry_spx_price") or ta.get("entry_price", 0)
            sl_spx        = ta.get("stop_loss_spx") or ta.get("stop_loss", 0)
            tp1_spx       = ta.get("take_profit_1", 0)
            tp2_spx       = ta.get("take_profit_2", 0)
            contract_px   = ta.get("option_premium_estimate", 0)  # estimated premium per share
            strat         = analysis.get("strategy", {})
            expiry_str    = datetime.now().strftime("%m%d%Y")      # today = 0DTE

            self.last_trade_info = {
                # Core identification
                "trade_type":    "OPTIONS",
                "symbol":        analysis.get("_symbol", self.symbol_var.get()),
                "options_play":  options_play,
                "option_type":   opt_type,                  # "CALL" or "PUT"
                "direction":     direction,
                "strike":        strike,
                "expiration":    expiry_str,                # 0DTE = today
                "strike_type":   ta.get("strike_type", "ATM"),

                # Prices (SPX index levels)
                "entry_price":   entry_spx,                 # SPX entry level
                "stop_loss":     sl_spx,                    # SPX stop level
                "take_profit_1": tp1_spx,
                "take_profit_2": tp2_spx,
                "contract_price": contract_px,              # Option premium estimate

                # Meta
                "risk_reward":   ta.get("risk_reward_ratio", "N/A"),
                "confidence":    strat.get("setup_quality", "N/A"),
                "setup":         strat.get("best_setup", ""),
                "max_hold":      ta.get("max_hold_time", ""),
                "reasoning":     strat.get("setup_explanation", ""),
            }
            opt_emoji = "📈" if opt_type == "CALL" else "📉"
            self.log(f"\n{opt_emoji}  Signal ready: {options_play} SPX {strike} 0DTE — click 🚀 Trade\n", "signal_buy")
            self.root.after(0, lambda: self._update_setup_panel(self.last_trade_info))
        elif ta:
            self.last_trade_info = None
            self.root.after(0, lambda: self._update_setup_panel(None))

        # Alerts
        triggered = self.alerts.check_alerts(analysis)
        if triggered:
            self.log("\n🚨  ALERTS:", "alert")
            for msg in triggered:
                self.log(f"  {msg}", "alert")
            self.alerts.notify_alerts(triggered, analysis.get("symbol", "Chart"))

        self.status_var.set(
            f"Analysis #{self.analysis_count} · "
            f"{datetime.now().strftime('%H:%M:%S')}")

    # ──────────────────────────────────────────────────────────
    #  Monitoring
    # ──────────────────────────────────────────────────────────

    def toggle_monitoring(self):
        if self.monitoring:
            self.stop_monitoring()
        else:
            self.start_monitoring()

    def start_monitoring(self):
        if not self.capture.region:
            messagebox.showwarning("No Region", "Select a region first.")
            return
        if not self.analyzer and not self._init_analyzer():
            return
        self._save_current_settings()
        interval = int(self.interval_var.get() or 10)
        self.monitoring = True
        self.start_btn.set_text("⏹  Stop")
        self.status_var.set(f"Monitoring every {interval}s…")
        self.log(f"\n── Monitoring every {interval}s ──\n", "header")

        def _loop():
            while self.monitoring:
                try:
                    img_b64  = self.capture.capture_to_base64()
                    sym      = self.symbol_var.get()
                    pt_sym   = self.paper.symbol
                    ctx      = self.context_var.get().strip()

                    strat_inj = self._get_strategy_injection()
                    # Use Capture section symbol for analysis, independent of paper trading
                    analysis_sym = sym if sym != "AUTO" else "AUTO"
                    if self.analyzer.is_spot_symbol(analysis_sym) or analysis_sym == "AUTO":
                        # Inject memory — iron-clad lock when signal is committed
                        prev = self._last_analysis
                        memory_ctx = ""
                        if self._locked_signal:
                            locked_action = self._locked_signal.get("action", "BUY")
                            locked_entry  = self._locked_signal.get("entry_price", "?")
                            locked_stop   = self._locked_signal.get("stop_loss", "?")
                            locked_dir    = "BUY CALLS" if locked_action == "BUY" else "BUY PUTS"
                            memory_ctx = (
                                f"\n\n🔒 SIGNAL IS LOCKED — DO NOT CHANGE THE DIRECTION.\n"
                                f"The trader has committed to: {locked_dir}.\n"
                                f"Entry zone: {locked_entry}  |  Stop loss: {locked_stop}.\n"
                                f"YOUR ONLY JOB NOW: confirm if price is at or inside the entry zone.\n"
                                f"- If price is AT or NEAR the entry zone → action = {locked_action} (enter now).\n"
                                f"- If price has NOT reached entry yet → action = WAIT (but keep same direction).\n"
                                f"- If price has CLOSED beyond {locked_stop} → you may release the lock.\n"
                                f"DO NOT flip to the opposite direction. DO NOT change entry/stop/targets unless "
                                f"price has definitively closed beyond the stop loss level. Stay committed."
                            )
                        elif prev:
                            _bias_note = ""
                            if self._confirmed_bias:
                                _cnt = self._bias_candidate_count
                                if _cnt >= self._BIAS_CONFIRM_NEEDED:
                                    _bias_note = (
                                        f"\n\n🔒 CONFIRMED HTF BIAS LOCK: {self._confirmed_bias} — "
                                        f"confirmed by {_cnt} consecutive scans. "
                                        f"DO NOT flip the bias based on small pullbacks or wicks. "
                                        f"Only a decisive close beyond the stop loss on 15M+ warrants a flip. "
                                        f"BIAS_LOCK={self._confirmed_bias}"
                                    )
                                else:
                                    _bias_note = (
                                        f"\n\nHTF BIAS CONTEXT: {self._confirmed_bias} "
                                        f"(working bias from prior scans — not yet locked). "
                                        f"BIAS_LOCK={self._confirmed_bias}"
                                    )
                            # ── Build rich ICT setup continuity context ───────
                            _ict_mem = ""
                            if self._ict_setup_zone:
                                _chk = self._ict_checklist_prev
                                _chk_str = (
                                    f"BOS={'✅' if _chk.get('bos') else '❌'} "
                                    f"Pullback={'✅' if _chk.get('pullback') else '❌'} "
                                    f"FVG/OB={'✅' if _chk.get('fvg_ob') else '❌'} "
                                    f"AtZone={'✅' if _chk.get('at_zone') else '❌'} "
                                    f"Confirm={'✅' if _chk.get('confirm') else '❌'} "
                                    f"Path={'✅' if _chk.get('path') else '❌'}"
                                )
                                _missing = self._ict_missing_step or "Unknown"
                                _zone_scans = self._ict_setup_scans
                                _phase_str = self._ict_last_phase or "?"
                                _zone_type = self._ict_setup_type or "zone"
                                _ict_mem = (
                                    f"\n\n📊 ICT SETUP BUILD — SCAN #{_zone_scans}:\n"
                                    f"We have been watching this setup for {_zone_scans} scan(s).\n"
                                    f"Watching: {_zone_type} zone at {self._ict_setup_zone}\n"
                                    f"Last market phase: {_phase_str}\n"
                                    f"Last checklist state: {_chk_str}\n"
                                    f"Currently missing: {_missing}\n"
                                    f"IMPORTANT: Continue building on this context. Do NOT start over.\n"
                                    f"If the missing step is now resolved → advance the signal.\n"
                                    f"If new conditions have changed the setup → explain why.\n"
                                    f"Be PATIENT — this is ICT methodology, not scalping. "
                                    f"We wait for ALL 6 checklist steps before signaling BUY/SELL."
                                )
                            memory_ctx = (
                                f"\n\nPREVIOUS SCAN [{self._scan_count} total]: "
                                f"bias={prev.get('timeframe_bias','?')} "
                                f"action={prev.get('action','?')} entry={prev.get('entry_price','?')} "
                                f"stop={prev.get('stop_loss','?')} "
                                f"setup={prev.get('setup_type','?')}. "
                                f"Keep the same entry/stop/targets unless price has definitively "
                                f"closed beyond the stop level."
                                f"{_ict_mem}"
                                f"{_bias_note}"
                            )

                        # ── Active trade: override everything with management mode ──
                        if self._active_trade:
                            at = self._active_trade
                            opt_type = at.get("option_type", "CALL")
                            direction = "CALLS (bullish)" if opt_type == "CALL" else "PUTS (bearish)"
                            memory_ctx = (
                                f"\n\n🟢 TRADER IS IN AN ACTIVE TRADE — SWITCH TO MANAGEMENT MODE.\n"
                                f"Trade: BUY {direction} on {at.get('symbol','?')}\n"
                                f"ACTUAL FILL PRICE (where the trader was actually executed): {at.get('entry_price','?')}\n"
                                f"NOTE: This is the REAL entry price the trader was filled at — NOT a suggested zone.\n"
                                f"Stop loss: {at.get('stop_loss','?')} (exit if price closes beyond this)\n"
                                f"Target 1: {at.get('take_profit_1','?')} (first profit zone)\n"
                                f"Target 2: {at.get('take_profit_2','?')} (final target)\n"
                                f"Entry time: {at.get('entry_time','?')}\n\n"
                                f"YOUR ONLY JOB: look at the current price on the chart and compare it to these EXACT levels.\n"
                                f"The trader's fill was {at.get('entry_price','?')} — measure profit/loss from THAT price.\n"
                                f"Return one of these actions:\n"
                                f"  HOLD         — price moving in our favor from fill price, stay in trade\n"
                                f"  MOVE_STOP_BE — price has moved {('down' if opt_type=='PUT' else 'up')} enough to move stop to breakeven\n"
                                f"  TAKE_PROFIT  — price is at or beyond Target 1 or Target 2 from the fill price\n"
                                f"  EXIT_NOW     — price is threatening the stop loss, exit immediately\n\n"
                                f"DO NOT look for new entries. DO NOT return BUY/SELL/WAIT/READY. "
                                f"The trader is already in a position. Manage it from their fill of {at.get('entry_price','?')}."
                            )

                        # ── Multi-agent or single-agent analysis ─────────────
                        if self._use_agents and self.agent_orchestrator:
                            # Inject trade memory pattern context
                            mem_ctx = ""
                            if self.last_trade_info:
                                sym_    = self.last_trade_info.get("symbol", analysis_sym)
                                setup_  = self.last_trade_info.get("setup", "UNKNOWN")
                                opt_    = self.last_trade_info.get("option_type", "")
                                t_now   = datetime.now().strftime("%H:%M")
                                mem_ctx = self.trade_memory.get_pattern_context(
                                    sym_, setup_, opt_, t_now)
                            # Pass current account balance for position sizing
                            if self.broker and self.broker.connected:
                                try:
                                    bal = self.broker.get_balance()
                                    if bal:
                                        self.agent_orchestrator.account_balance = float(
                                            bal.get("net-liq-value", 0) or 0)
                                except Exception:
                                    pass
                            # Pass strategy performance stats to StrategyAnalystAgent
                            try:
                                all_trades = self.trade_memory.get_all_trades()
                                stats: dict = {}
                                for t in all_trades:
                                    s = t.get("setup", "UNKNOWN") or "UNKNOWN"
                                    if s not in stats:
                                        stats[s] = {"wins": 0, "losses": 0,
                                                    "total_pnl": 0.0}
                                    pnl = t.get("pnl", 0) or 0
                                    if pnl > 0:
                                        stats[s]["wins"] += 1
                                    elif pnl < 0:
                                        stats[s]["losses"] += 1
                                    stats[s]["total_pnl"] += pnl
                                # Add avg_pnl per strategy
                                for s, d in stats.items():
                                    total = d["wins"] + d["losses"]
                                    d["avg_pnl"] = round(
                                        d["total_pnl"] / total, 2) if total else 0
                                self.agent_orchestrator.trade_stats = stats
                            except Exception:
                                pass
                            # ── Inject confirmed HTF bias lock into agent memory ──
                            bias_lock_ctx = ""
                            if self._confirmed_bias and not self._active_trade:
                                if self._bias_candidate_count >= self._BIAS_CONFIRM_NEEDED:
                                    bias_lock_ctx = (
                                        f"\n\n🔒 CONFIRMED HTF BIAS LOCK: {self._confirmed_bias}\n"
                                        f"This bias has been confirmed across {self._bias_candidate_count} "
                                        f"consecutive scans. DO NOT flip the bias based on small 1M/5M candle "
                                        f"wicks, momentary pops, or minor retracements. The bias is "
                                        f"{self._confirmed_bias} until price DEFINITIVELY closes beyond the "
                                        f"stop loss level with clear structural confirmation on the 15M or higher.\n"
                                        f"BIAS_LOCK={self._confirmed_bias}"
                                    )
                                else:
                                    bias_lock_ctx = (
                                        f"\n\nHTF BIAS CONTEXT: {self._confirmed_bias} "
                                        f"(working directional bias from prior scans). "
                                        f"Treat this as the likely direction unless the chart shows "
                                        f"a clear higher-timeframe structure break. "
                                        f"BIAS_LOCK={self._confirmed_bias}"
                                    )
                            # ── Inject ICT setup build context for agents ─────
                            ict_setup_ctx = ""
                            if self._ict_setup_zone and not self._active_trade:
                                _chk = self._ict_checklist_prev
                                _chk_str = (
                                    f"BOS={'✅' if _chk.get('bos') else '❌'} "
                                    f"Pullback={'✅' if _chk.get('pullback') else '❌'} "
                                    f"FVG/OB={'✅' if _chk.get('fvg_ob') else '❌'} "
                                    f"AtZone={'✅' if _chk.get('at_zone') else '❌'} "
                                    f"Confirm={'✅' if _chk.get('confirm') else '❌'} "
                                    f"Path={'✅' if _chk.get('path') else '❌'}"
                                )
                                _missing = self._ict_missing_step or "None identified yet"
                                ict_setup_ctx = (
                                    f"\n\n📊 SETUP CONTINUITY — Scan #{self._ict_setup_scans}:\n"
                                    f"Zone being watched: {self._ict_setup_type or 'zone'} @ {self._ict_setup_zone}\n"
                                    f"Market phase last scan: {self._ict_last_phase or '?'}\n"
                                    f"ICT Checklist last scan: {_chk_str}\n"
                                    f"Step still missing: {_missing}\n"
                                    f"INSTRUCTION: Build on top of this existing analysis context. "
                                    f"Do NOT restart from scratch. If the missing step is now resolved "
                                    f"on this new chart, advance the signal to the next stage. "
                                    f"Be patient — only signal BUY/SELL when ALL 6 steps confirm."
                                )
                            mem_ctx_combined = (mem_ctx + bias_lock_ctx + ict_setup_ctx).strip()
                            analysis = self.agent_orchestrator.analyze(
                                img_b64,
                                symbol       = analysis_sym,
                                active_trade = self._active_trade,
                                memory_context = mem_ctx_combined,
                            )
                        else:
                            analysis = self.analyzer.analyze_spot(
                                img_b64, symbol=analysis_sym,
                                extra_context=(ctx + memory_ctx).strip(),
                                strategy_injection=strat_inj)
                        text = self._format_spot_analysis(analysis)
                    else:
                        analysis = self.analyzer.analyze(
                            img_b64, ctx, symbol=sym,
                            strategy_injection=strat_inj)
                        text = format_analysis(analysis)

                    self._scan_count += 1
                    sc = self._scan_count
                    elapsed = (datetime.now() - self._session_start)
                    mins = int(elapsed.total_seconds() // 60)
                    secs = int(elapsed.total_seconds() % 60)
                    scan_txt = f"{sc}  ({mins:02d}:{secs:02d} session)"
                    self.root.after(0, lambda t=scan_txt: self._setup_scans.config(text=t))
                    self.root.after(0, lambda r=text, a=analysis, i=img_b64:
                        self._display_analysis(a, r, i))
                except Exception as e:
                    self.root.after(0,
                        lambda err=e: self.log(f"Error: {err}", "alert"))
                for _ in range(interval):
                    if not self.monitoring:
                        break
                    time.sleep(1)

        self.monitor_thread = threading.Thread(target=_loop, daemon=True)
        self.monitor_thread.start()

    def stop_monitoring(self):
        self.monitoring = False
        self._last_analysis   = None   # clear memory on stop
        self._locked_signal   = None   # release any active lock
        self._consecutive_buf = []
        self._alert_shown     = False
        self.start_btn.set_text("▶  Monitor")
        self.status_var.set("Stopped")
        self.log("\n⏹  Monitoring stopped\n", "header")

    # ──────────────────────────────────────────────────────────
    #  Export
    # ──────────────────────────────────────────────────────────

    def export_log(self):
        if not self.analyzer or not self.analyzer.history:
            messagebox.showinfo("No Data", "No analysis data yet.")
            return
        fp = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx")],
            initialfile=f"chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        if not fp:
            return
        try:
            rows = [{"timestamp": h.get("_analyzed_at", ""),
                     "symbol": h.get("symbol", ""),
                     "signal": h.get("signals", {}).get("overall", ""),
                     "confidence": h.get("signals", {}).get("confidence", ""),
                     "price": h.get("price", {}).get("current", ""),
                     "summary": h.get("summary", "")}
                    for h in self.analyzer.history]
            df = pd.DataFrame(rows)
            if fp.endswith(".xlsx"):
                df.to_excel(fp, index=False, engine="openpyxl")
            else:
                df.to_csv(fp, index=False)
            self.log(f"\n💾  Exported {len(rows)} rows → {fp}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    # ──────────────────────────────────────────────────────────
    #  Broker
    # ──────────────────────────────────────────────────────────

    def _set_broker_status(self, text: str, connected: bool):
        self.broker_status_var.set(text)
        c = C["green"] if connected else (C["red"] if "fail" in text.lower()
                                          else C["text3"])
        self.broker_dot.config(fg=c)
        self.broker_status_lbl.config(fg=c)

    def connect_broker(self):
        username = self.tt_user_var.get().strip()
        password = self.tt_pass_var.get().strip()
        if not username or not password:
            messagebox.showerror("Missing Credentials",
                "Enter your Tastytrade username and password.")
            return
        try:
            self.broker = TastytradeBroker(username, password,
                                           sandbox=self.sandbox_var.get())
            self.log("\n🔗  Connecting to Tastytrade…", "header")

            # ── Step 1: initial login attempt (no OTP) ──────────────────────
            result = self.broker.login()

            # ── Step 2: handle device challenge if required ──────────────────
            if result == TastytradeBroker.DEVICE_CHALLENGE:
                self.log("📱  Device verification required — Tastytrade is sending "
                         "a code to your email/SMS…", "alert")
                otp = self._ask_device_challenge_code()
                if otp is None:
                    self.log("⚠️  Connection cancelled.", "alert")
                    self._set_broker_status("Cancelled", False)
                    return
                # Step 3: complete login with the verification code
                result = self.broker.complete_device_challenge(otp)

            # ── Evaluate final result ────────────────────────────────────────
            if result is True:
                self._set_broker_status("Connected", True)
                self.log("✅  Connected to Tastytrade!", "signal_buy")
                accounts = self.broker.get_accounts()
                if accounts:
                    a = accounts[0]
                    self.broker.set_account(a.get("account-number", ""))
                    self.log(f"Account: {a.get('account-number','N/A')}")
                    self.log(f"Found {len(accounts)} account(s)\n")
                    self.config["tt_username"] = username
                    self.config["tt_password"] = password
                    save_config(self.config)
                    self.show_balance()
                    self.show_positions()
                    self._refresh_watchlist_prices()
            else:
                self._set_broker_status("Auth failed", False)
                self.log("❌  Login failed — check username/password.", "alert")
        except Exception as e:
            self._set_broker_status("Error", False)
            self.log(f"❌  {e}", "alert")

    def _ask_device_challenge_code(self) -> str:
        """
        Show a dialog telling the user Tastytrade sent a verification code,
        and asking them to enter it.
        Returns the code string, or None if cancelled.
        """
        dialog = tk.Toplevel(self.root)
        dialog.title("Device Verification")
        dialog.configure(bg=C["bg"])
        dialog.resizable(False, False)
        dialog.grab_set()

        # Center on parent
        dialog.geometry("360x210")
        self.root.update_idletasks()
        px = self.root.winfo_x() + (self.root.winfo_width()  // 2) - 180
        py = self.root.winfo_y() + (self.root.winfo_height() // 2) - 105
        dialog.geometry(f"+{px}+{py}")

        tk.Label(dialog, text="📱  Device Verification",
                 bg=C["bg"], fg=C["text"], font=FONT_CARD).pack(pady=(18, 4))
        tk.Label(dialog,
                 text="Tastytrade sent a verification code\nto your email or phone.\n\nEnter it below:",
                 bg=C["bg"], fg=C["text2"], font=FONT_SMALL,
                 justify="center").pack(pady=(0, 8))

        code_var = tk.StringVar()
        entry = tk.Entry(dialog, textvariable=code_var,
                         bg=C["input"], fg=C["text"],
                         insertbackground=C["text"],
                         font=("Menlo", 20), width=10,
                         justify="center", relief="flat",
                         highlightthickness=1,
                         highlightbackground=C["border"],
                         highlightcolor=C["blue"])
        entry.pack(pady=4)
        entry.focus_set()

        result = {"code": None, "cancelled": False}

        def on_confirm(event=None):
            result["code"] = code_var.get().strip()
            dialog.destroy()

        def on_cancel():
            result["cancelled"] = True
            dialog.destroy()

        btn_frame = tk.Frame(dialog, bg=C["bg"])
        btn_frame.pack(pady=12)
        tk.Button(btn_frame, text="Verify", command=on_confirm,
                  bg=C["blue"], fg="white", font=FONT_SMALL,
                  relief="flat", padx=18, pady=6,
                  activebackground="#0070E0", activeforeground="white",
                  cursor="hand2").pack(side="left", padx=6)
        tk.Button(btn_frame, text="Cancel", command=on_cancel,
                  bg=C["btn"], fg=C["text2"], font=FONT_SMALL,
                  relief="flat", padx=18, pady=6,
                  cursor="hand2").pack(side="left", padx=6)

        entry.bind("<Return>", on_confirm)
        dialog.wait_window()
        if result["cancelled"]:
            return None
        return result["code"] if result["code"] else None

    def show_positions(self):
        if not self.broker or not self.broker.connected:
            messagebox.showwarning("Not Connected", "Connect to Tastytrade first.")
            return
        def _fetch():
            try:
                positions = self.broker.get_positions()
                text = format_positions(positions)
                self.root.after(0, lambda: self.log(f"\n{text}", "header"))
                # Also update dashboard
                balance = self.broker.get_balance()
                self.root.after(0, lambda b=balance, p=positions:
                    self.update_account_dashboard(b, p))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"Error: {e}", "alert"))
        self.log("\nFetching positions…", "header")
        threading.Thread(target=_fetch, daemon=True).start()

    def show_balance(self):
        if not self.broker or not self.broker.connected:
            messagebox.showwarning("Not Connected", "Connect to Tastytrade first.")
            return
        def _fetch():
            try:
                balance = self.broker.get_balance()
                text = format_balance(balance)
                self.root.after(0, lambda: self.log(f"\n{text}", "header"))
                self.root.after(0, lambda b=balance:
                    self.update_account_dashboard(b))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"Error: {e}", "alert"))
        self.log("\nFetching balance…", "header")
        threading.Thread(target=_fetch, daemon=True).start()

    def show_orders(self):
        if not self.broker or not self.broker.connected:
            messagebox.showwarning("Not Connected", "Connect to Tastytrade first.")
            return
        def _fetch():
            try:
                orders = self.broker.get_orders()
                if not orders:
                    self.root.after(0,
                        lambda: self.log("\nNo open orders.", "header"))
                    return
                lines = ["\n── Orders ──", ""]
                for o in orders:
                    d = (o.get("OrderDetail", [{}])[0]
                         if o.get("OrderDetail") else {})
                    inst = (d.get("Instrument", [{}])[0]
                            if d.get("Instrument") else {})
                    prod = inst.get("Product", {})
                    lines.append(
                        f"  {prod.get('symbol','?')}  "
                        f"{inst.get('orderAction','?')} "
                        f"{inst.get('orderedQuantity','?')} shares  "
                        f"[{o.get('orderStatus','?')}]")
                lines.append("─" * 30)
                self.root.after(0,
                    lambda: self.log("\n".join(lines), "header"))
            except Exception as e:
                self.root.after(0,
                    lambda: self.log(f"Error: {e}", "alert"))
        self.log("\nFetching orders…", "header")
        threading.Thread(target=_fetch, daemon=True).start()

    def open_premarket_briefing(self):
        """
        Walk the user through capturing 4 timeframe charts (Daily, 4H, 1H, 15m)
        on TradingView, then send all 4 to Claude for a pre-market ICT/SMC briefing.
        """
        if not self.analyzer and not self._init_analyzer():
            return

        TIMEFRAMES = ["Daily", "4H", "1H", "15m"]
        captured_charts = []

        # ── Instructions dialog
        msg = (
            "📊  PRE-MARKET MULTI-TIMEFRAME BRIEFING\n\n"
            "This will capture 4 SPX charts and build your morning game plan\n"
            "using ICT / Smart Money Concepts.\n\n"
            "You will capture charts in this order:\n"
            "  1️⃣  Daily  chart\n"
            "  2️⃣  4-Hour chart\n"
            "  3️⃣  1-Hour chart\n"
            "  4️⃣  15-min chart\n\n"
            "For each one:\n"
            "  • Switch TradingView to that timeframe\n"
            "  • Press the capture button when ready\n\n"
            "Make sure VWAP, RSI, and MACD are visible on your charts.\n"
            "Ready to start?"
        )
        if not messagebox.askyesno("Pre-Market Briefing", msg):
            return

        # ── Capture loop — one chart per timeframe
        for tf in TIMEFRAMES:
            result = messagebox.askyesno(
                f"Capture {tf} Chart",
                f"Switch TradingView to the  {tf}  timeframe.\n\n"
                f"Click YES when ready to capture the {tf} chart.\n"
                f"(Make sure SPX is visible with RSI, MACD, VWAP)"
            )
            if not result:
                self.log(f"⚠️  Pre-market briefing cancelled at {tf} chart.", "alert")
                return

            if not self.capture.region:
                messagebox.showwarning(
                    "No Region",
                    "Please select your chart region first using 'Select Region'.")
                return

            try:
                self.log(f"📸  Capturing {tf} chart…", "header")
                self.root.update()
                img_b64 = self.capture.capture_to_base64()
                captured_charts.append({
                    "timeframe": tf,
                    "image_base64": img_b64,
                })
                self.log(f"  ✅  {tf} captured", "signal_buy")
            except Exception as e:
                self.log(f"  ❌  Error capturing {tf}: {e}", "alert")
                return

        # ── Send all 4 charts to Claude
        self.log("\n🧠  Analyzing all timeframes with ICT/SMC methodology…", "header")
        self.log("  (This may take 15–30 seconds — Claude is reading all 4 charts)\n")
        self.status_var.set("Running pre-market briefing…")
        self.root.update()

        def _run_briefing():
            try:
                briefing = self.analyzer.analyze_premarket(captured_charts)
                text     = format_premarket_briefing(briefing)
                self.root.after(0, lambda: self._display_premarket(briefing, text,
                                                                    captured_charts))
            except Exception as e:
                self.root.after(0,
                    lambda: self.log(f"❌  Briefing error: {e}", "alert"))
                self.root.after(0,
                    lambda: self.status_var.set("Briefing error"))

        threading.Thread(target=_run_briefing, daemon=True).start()

    def _display_premarket(self, briefing: dict, text: str, charts: list):
        """Display the pre-market briefing in the output log."""
        self.log(text, "header")

        # Update chart preview with the most recent (15m) capture
        if charts:
            self.update_chart_preview(charts[-1]["image_base64"])

        # Show bias in status bar
        bias = briefing.get("htf_bias", "NEUTRAL")
        bias_short = {
            "STRONGLY_BULLISH": "🟢🟢 STRONGLY BULL",
            "BULLISH":          "🟢 BULLISH",
            "NEUTRAL":          "⬜ NEUTRAL",
            "BEARISH":          "🔴 BEARISH",
            "STRONGLY_BEARISH": "🔴🔴 STRONGLY BEAR",
        }.get(bias, bias)
        self.status_var.set(f"Pre-Market: {bias_short}")

        # Alert about likely sweep
        lp = briefing.get("liquidity_pools", {})
        sweep_dir  = lp.get("most_likely_swept_first", "")
        sweep_tgt  = lp.get("sweep_target")
        if sweep_dir and sweep_tgt:
            arrow = "↑" if sweep_dir == "buy_side" else "↓"
            self.log(
                f"\n{arrow}  WATCH: Likely liquidity sweep at {sweep_tgt} "
                f"({sweep_dir.replace('_',' ')} liquidity)\n",
                "signal_buy" if sweep_dir == "sell_side" else "signal_sell"
            )

        messagebox.showinfo(
            "Pre-Market Briefing Ready",
            f"✅  Briefing complete!\n\n"
            f"HTF Bias: {bias}\n\n"
            f"The full analysis is in your Output Log.\n"
            f"Your morning game plan is ready — check the MORNING GAME PLAN section at the bottom."
        )

    def open_trade_dialog(self):
        if not self.broker or not self.broker.connected:
            messagebox.showwarning("Not Connected", "Connect to Tastytrade first.")
            return

        # ── Pre-trade risk check ─────────────────────────────────────────────
        allowed, reason = self._check_daily_risk()
        if not allowed:
            self.log(f"\n{reason}", "alert")
            messagebox.showwarning("Risk Limit", reason.replace("⛔  ", "").replace("⚠️  ", ""))
            return

        # ── Revenge trade detector ────────────────────────────────────────────
        blocked = self._revenge_trade_check()
        if blocked:
            return

        # Resolve real symbol — never pass AUTO or dropdown label text
        raw_sym = self.symbol_var.get().split("—")[0].strip()
        if not raw_sym or raw_sym.upper() in ("AUTO", "🤖 AUTO", "──"):
            if self.last_trade_info and self.last_trade_info.get("symbol","").upper() not in ("AUTO",""):
                raw_sym = self.last_trade_info["symbol"]
            else:
                raw_sym = ""   # manual mode — TradeDialog will ask

        real_sym = raw_sym.upper()

        # Patch symbol into last_trade_info if it was AUTO
        if self.last_trade_info and real_sym:
            if self.last_trade_info.get("symbol","").upper() in ("AUTO",""):
                self.last_trade_info["symbol"] = real_sym

        # If no AI trade info → open in manual mode (empty dict, dialog has its own form)
        trade_info = self.last_trade_info or {}

        # ── Route: futures vs options ─────────────────────────────────────────
        is_futures = (real_sym.startswith("/") or
                      (self.analyzer and self.analyzer.is_futures_symbol(real_sym)))

        # Ensure trade_info has the resolved symbol
        if is_futures and real_sym:
            trade_info = {**trade_info, "symbol": real_sym}

        # ── Pre-trade checklist popup ────────────────────────────────────────
        proceed = self._show_pretrade_checklist(trade_info)
        if not proceed:
            return   # user cancelled

        def on_done(r):
            if r and "error" not in r:
                self.log(f"\n✅  {r.get('status','')}", "signal_buy")
                updated_info = dict(trade_info)
                last = self._last_analysis
                if last:
                    current_price = last.get("current_price", 0)
                    if current_price:
                        updated_info["entry_price"] = current_price
                        self.log(f"   Fill price: {current_price}  →  "
                                 f"Stop: {updated_info.get('stop_loss','?')}  "
                                 f"T1: {updated_info.get('take_profit_1','?')}  "
                                 f"T2: {updated_info.get('take_profit_2','?')}", "info")
                self._enter_trade_mode(updated_info)
            elif r:
                self.log(f"\n❌  {r.get('error','')}", "alert")

        if is_futures:
            self.log(f"\n📊 Futures order — {real_sym}", "info")
            FuturesTradeDialog(self.root, self.broker, trade_info, on_complete=on_done)
        else:
            TradeDialog(self.root, self.broker, trade_info, on_complete=on_done)

    def _show_pretrade_checklist(self, trade_info: dict) -> bool:
        """
        Show a pre-trade checklist popup with risk stats, pattern memory,
        and a GO / CANCEL decision.  Returns True if user clicks GO.
        """
        popup = tk.Toplevel(self.root)
        popup.title("Pre-Trade Checklist")
        popup.configure(bg=C["bg"])
        popup.resizable(False, False)
        popup.grab_set()

        result = {"go": False}

        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(popup, bg=C["blue"], padx=20, pady=12)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="🔎  Pre-Trade Checklist",
                 font=("Helvetica Neue", 15, "bold"),
                 bg=C["blue"], fg=C["text"]).pack(side=tk.LEFT)

        body = tk.Frame(popup, bg=C["bg"], padx=20, pady=14)
        body.pack(fill=tk.BOTH, expand=True)

        def add_row(label, value, color=C["text"]):
            row = tk.Frame(body, bg=C["card"],
                           highlightthickness=1, highlightbackground=C["border"])
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=label, font=FONT_SMALL, width=22, anchor="w",
                     bg=C["card"], fg=C["text3"], padx=10, pady=6).pack(side=tk.LEFT)
            tk.Label(row, text=value, font=("Helvetica Neue", 11, "bold"),
                     bg=C["card"], fg=color, padx=10, pady=6).pack(side=tk.LEFT)

        # ── 1. Setup summary ─────────────────────────────────────────────────
        action   = trade_info.get("action", "—")
        symbol   = trade_info.get("symbol", "—")
        opt_type = trade_info.get("option_type", "—")
        setup    = trade_info.get("setup", "—")
        entry    = trade_info.get("entry_price", "?")
        sl       = trade_info.get("stop_loss",   "?")
        tp1      = trade_info.get("take_profit_1","?")
        bias     = trade_info.get("timeframe_bias","?")

        action_color = C["green"] if "BUY" in str(action).upper() or action == "BUY" else C["red"]
        add_row("Signal",    f"{action}  {opt_type}", action_color)
        add_row("Symbol",    symbol,                  C["blue"])
        add_row("Setup",     setup,                   C["orange"])
        add_row("HTF Bias",  bias,                    C["text2"])
        add_row("Entry",     f"${entry}",             C["text"])
        add_row("Stop Loss", f"${sl}",                C["red"])
        add_row("Target 1",  f"${tp1}",               C["green"])

        # ── 2. Daily risk snapshot ────────────────────────────────────────────
        tk.Label(body, text="Daily Risk", font=("Helvetica Neue", 10, "bold"),
                 bg=C["bg"], fg=C["text3"]).pack(anchor="w", pady=(10, 2))

        remaining_loss   = abs(self._daily_loss_limit) + self._today_pnl
        remaining_trades = self._max_trades_per_day - self._today_trades
        risk_status      = "✅  OK" if remaining_loss > 0 and remaining_trades > 0 else "⚠️  Near limit"
        risk_color       = C["green"] if "OK" in risk_status else C["orange"]

        add_row("Today P&L",      f"${self._today_pnl:+.0f}",       C["green"] if self._today_pnl >= 0 else C["red"])
        add_row("Trades Today",   f"{self._today_trades} of {self._max_trades_per_day}", C["text2"])
        add_row("Loss Room Left", f"${remaining_loss:.0f}",          risk_color)
        add_row("Loss Streak",    f"{self._consecutive_losses} in a row", C["red"] if self._consecutive_losses > 0 else C["green"])

        # ── 3. Pattern memory ─────────────────────────────────────────────────
        mem_text = ""
        try:
            mem_text = self.trade_memory.get_pattern_context(
                symbol    = symbol,
                setup_type= setup,
                option_type= opt_type,
            )
        except Exception:
            pass

        if mem_text.strip():
            tk.Label(body, text="Pattern Memory", font=("Helvetica Neue", 10, "bold"),
                     bg=C["bg"], fg=C["text3"]).pack(anchor="w", pady=(10, 2))
            mem_box = tk.Text(body, height=4, font=FONT_MONOS, wrap=tk.WORD,
                              bg=C["card"], fg=C["text2"],
                              relief=tk.FLAT, borderwidth=0, padx=8, pady=6)
            mem_box.insert("1.0", mem_text.strip())
            mem_box.config(state=tk.DISABLED)
            mem_box.pack(fill=tk.X, pady=3)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_fr = tk.Frame(popup, bg=C["bg"], pady=14, padx=20)
        btn_fr.pack(fill=tk.X)

        def do_go():
            result["go"] = True
            popup.destroy()

        def do_cancel():
            result["go"] = False
            popup.destroy()

        AppleButton(btn_fr, "⚡  GO — Execute Trade",
                    command=do_go, style="green", height=38).pack(fill=tk.X, pady=(0, 8))
        AppleButton(btn_fr, "✖  Cancel",
                    command=do_cancel, style="default", height=34).pack(fill=tk.X)

        # Center on parent
        popup.update_idletasks()
        pw, ph = popup.winfo_reqwidth(), popup.winfo_reqheight()
        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        popup.geometry(f"{pw}x{ph}+{rx + (rw - pw)//2}+{ry + (rh - ph)//2}")

        self.root.wait_window(popup)
        return result["go"]

    # ──────────────────────────────────────────────────────────
    #  Trade Management Mode
    # ──────────────────────────────────────────────────────────

    def _enter_trade_mode(self, trade_info: dict):
        """Switch AI to management mode after a trade is executed."""
        now = datetime.now()
        self._trade_entry_time = now
        self._active_trade = {
            **trade_info,
            "entry_time": now.strftime("%H:%M:%S"),
        }
        # Record entry in trade memory
        try:
            self._active_trade_id = self.trade_memory.record_entry(trade_info)
            self.log(f"   📝 Trade #{self._active_trade_id} recorded in memory", "info")
        except Exception as e:
            self._active_trade_id = None
            self.log(f"   ⚠️  Memory record failed: {e}", "info")

        # Increment daily trade counter & update stats
        self._today_trades += 1
        self._update_daily_stats()

        self._setup_dir.config(text="🟢  IN TRADE", fg=C["green"])
        self._setup_pnl.config(text="Tracking…", fg=C["text3"])
        self._close_trade_btn.pack(fill=tk.X, padx=16, pady=(0, 10))
        self.log("\n🟢  TRADE ACTIVE — AI switching to management mode", "signal_buy")
        self.log(f"   Entry: {trade_info.get('entry_price','?')}  |  "
                 f"Stop: {trade_info.get('stop_loss','?')}  |  "
                 f"T1: {trade_info.get('take_profit_1','?')}  |  "
                 f"T2: {trade_info.get('take_profit_2','?')}", "info")
        self.log("   Hit '✅ Close Trade' when you exit the position.\n", "info")

    def _exit_trade_mode(self):
        """Clear active trade — record outcome and resume signal scanning."""
        at = self._active_trade
        if at and self._active_trade_id:
            # Ask exit price to record outcome
            exit_px = simpledialog.askstring(
                "Exit Price",
                "What price did you exit at?\n(Enter underlying price for P&L tracking)",
                parent=self.root
            )
            if exit_px:
                try:
                    exit_price  = float(exit_px.strip())
                    entry_price = float(at.get("entry_price", 0))
                    hold_min    = 0.0
                    if self._trade_entry_time:
                        hold_min = (datetime.now() - self._trade_entry_time
                                    ).total_seconds() / 60
                    pnl = self.trade_memory.record_exit(
                        trade_id    = self._active_trade_id,
                        exit_price  = exit_price,
                        entry_price = entry_price,
                        option_type = at.get("option_type", "PUT"),
                        hold_minutes= round(hold_min, 1),
                    )
                    outcome = "✅ WIN" if pnl > 0 else "❌ LOSS"
                    self.log(f"\n{outcome}  Exit: ${exit_price}  |  "
                             f"Est. P&L: ${pnl:+.0f}  |  "
                             f"Hold: {hold_min:.0f} min", "signal_buy" if pnl > 0 else "signal_sell")

                    # Update daily counters
                    self._today_pnl += pnl
                    self._last_trade_time = datetime.now()
                    if pnl > 0:
                        self._consecutive_losses = 0
                    else:
                        self._consecutive_losses += 1
                        self._last_loss_time = datetime.now()

                    # Show updated stats
                    stats = self.trade_memory.get_summary()
                    self.log(f"   📊 All-time: {stats['wins']}W {stats['losses']}L  "
                             f"({stats['win_rate']}%)  Total P&L: ${stats['total_pnl']:+.0f}", "info")

                    # Grade this trade
                    self.root.after(300, lambda p=pnl, e=exit_price,
                                    a=at: self._grade_trade(p, e, a))

                    # Warn if limits are approaching
                    allowed, reason = self._check_daily_risk()
                    if not allowed:
                        self.log(f"\n{reason}", "alert")
                except Exception as e:
                    self.log(f"   ⚠️  Memory exit failed: {e}", "info")

        self._active_trade     = None
        self._active_trade_id  = None
        self._trade_entry_time = None
        self._locked_signal    = None
        self._consecutive_buf  = []
        self._alert_shown      = False
        self._close_trade_btn.pack_forget()
        self._setup_pnl.config(text="—", fg=C["green"])
        self._update_daily_stats()
        self.log("\n📋  Trade closed — resuming signal scanning\n", "header")

    # ──────────────────────────────────────────────────────────
    #  Daily Risk Controls
    # ──────────────────────────────────────────────────────────

    def _check_daily_risk(self) -> tuple:
        """
        Check if trading is allowed given today's risk limits.
        Returns (allowed: bool, reason: str).
        """
        if self._trading_paused:
            return False, "⛔  TRADING PAUSED — Daily limit already hit. Resume tomorrow."

        # Daily loss limit
        if self._today_pnl <= -abs(self._daily_loss_limit):
            self._trading_paused = True
            self._update_daily_stats()
            return False, (f"⛔  DAILY LOSS LIMIT HIT — Down ${abs(self._today_pnl):.0f} today "
                           f"(limit: ${self._daily_loss_limit:.0f}). No more trades today.")

        # Max trades per day
        if self._today_trades >= self._max_trades_per_day:
            self._trading_paused = True
            self._update_daily_stats()
            return False, (f"⛔  MAX TRADES REACHED — {self._today_trades} trades taken today "
                           f"(limit: {self._max_trades_per_day}).")

        # Consecutive loss limit
        if self._consecutive_losses >= self._max_consecutive_losses:
            self._trading_paused = True
            self._update_daily_stats()
            return False, (f"⛔  CONSECUTIVE LOSS LIMIT — {self._consecutive_losses} losses in a row "
                           f"(limit: {self._max_consecutive_losses}). Take a break.")

        return True, "✅ Risk OK"

    def _update_daily_stats(self):
        """Refresh the Live Status daily stats panel labels."""
        # P&L color — green if positive, red if negative
        pnl_color = C["green"] if self._today_pnl >= 0 else C["red"]
        self._stat_pnl.config(
            text=f"${self._today_pnl:+.0f}",
            fg=pnl_color
        )

        # Trades count
        self._stat_trades.config(
            text=f"{self._today_trades} / {self._max_trades_per_day}",
            fg=C["text2"]
        )

        # Win rate from memory
        try:
            s = self.trade_memory.get_summary()
            wr = s.get("win_rate", 0)
            wins = s.get("wins", 0)
            losses = s.get("losses", 0)
            wr_color = C["green"] if wr >= 50 else C["red"]
            self._stat_winrate.config(
                text=f"{wr:.0f}%  ({wins}W {losses}L)",
                fg=wr_color
            )
        except Exception:
            self._stat_winrate.config(text="—", fg=C["text2"])

        # Streak
        if self._consecutive_losses > 0:
            streak_text  = f"🔴  {self._consecutive_losses} loss streak"
            streak_color = C["red"]
        else:
            streak_text  = "🟢  No losing streak"
            streak_color = C["green"]
        self._stat_streak.config(text=streak_text, fg=streak_color)

        # Risk status
        if self._trading_paused:
            risk_text  = "⛔  PAUSED"
            risk_color = C["red"]
        elif self._today_pnl <= -abs(self._daily_loss_limit) * 0.75:
            risk_text  = "⚠️  Near limit"
            risk_color = C["orange"]
        else:
            remaining_loss = abs(self._daily_loss_limit) + self._today_pnl
            remaining_trades = self._max_trades_per_day - self._today_trades
            risk_text  = f"✅  ${remaining_loss:.0f} left | {remaining_trades} trades left"
            risk_color = C["green"]
        self._stat_risk.config(text=risk_text, fg=risk_color)

    # ──────────────────────────────────────────────────────────
    #  Agents Tab Updater
    # ──────────────────────────────────────────────────────────

    def _update_agents_tab(self, analysis: dict):
        """Refresh the 🤖 Agents tab with the latest per-agent results."""
        agents = analysis.get("_agents", {})
        if not agents:
            # Single-agent mode — show hint
            self._ag_hint_lbl.config(
                text="Enable Multi-Agent Mode (left panel) to see per-agent analysis here.")
            return

        self._ag_hint_lbl.config(text="")

        # ── Timestamp ────────────────────────────────────────────────────────
        self._ag_ts_lbl.config(text=f"Last scan  {datetime.now().strftime('%H:%M:%S')}")

        # ── Confidence ───────────────────────────────────────────────────────
        conf = analysis.get("confidence", "—")
        conf_color = {
            "HIGH":   C["green"],
            "MEDIUM": C["orange"],
            "LOW":    C["red"],
        }.get(conf, C["text2"])
        action = analysis.get("action", "—")
        self._ag_conf_lbl.config(text=conf, fg=conf_color)
        self._ag_score_lbl.config(text=f"→  Final signal: {action}")

        # ── Helper: status label text + color ────────────────────────────────
        def _ok(text):   return text, C["green"]
        def _warn(text): return text, C["orange"]
        def _bad(text):  return text, C["red"]
        def _neu(text):  return text, C["text2"]

        # ── Bias Agent ───────────────────────────────────────────────────────
        bias = agents.get("bias", {})
        if bias:
            b_val   = bias.get("bias", "?")
            b_str   = bias.get("strength", "?")
            b_color = C["green"] if b_val == "BULLISH" else C["red"] if b_val == "BEARISH" else C["text2"]
            self._ag_bias_st.config(text=b_val, fg=b_color)
            self._ag_bias_dt.config(text=f"{b_str}  —  {bias.get('reasoning','')[:80]}", fg=C["text2"])

        # ── Volume Agent ─────────────────────────────────────────────────────
        vol = agents.get("volume", {})
        if vol:
            confirms = vol.get("volume_confirms", True)
            warning  = vol.get("warning", "")
            if confirms and not warning:
                st_txt, st_col = _ok("CONFIRM")
                dt_txt = vol.get("reasoning", "Volume supports the move")[:80]
            elif warning:
                st_txt, st_col = _warn("WARNING")
                dt_txt = warning[:80]
            else:
                st_txt, st_col = _bad("WEAK")
                dt_txt = vol.get("reasoning", "Volume does not confirm")[:80]
            self._ag_vol_st.config(text=st_txt, fg=st_col)
            self._ag_vol_dt.config(text=dt_txt, fg=C["text2"])

        # ── Momentum Agent ───────────────────────────────────────────────────
        mom = agents.get("momentum", {})
        if mom:
            m_state = mom.get("momentum", "MODERATE")
            m_action = mom.get("best_action", "ENTER_NOW")
            m_color = (C["green"] if m_state == "STRONG"
                       else C["red"] if m_state == "EXHAUSTED"
                       else C["orange"])
            self._ag_mom_st.config(text=m_state, fg=m_color)
            self._ag_mom_dt.config(
                text=f"Best action: {m_action}  —  {mom.get('reasoning','')[:60]}",
                fg=C["text2"])

        # ── Scalp Agent ──────────────────────────────────────────────────────
        scalp = agents.get("scalp", {})
        if scalp:
            detected = scalp.get("scalp_detected", False)
            s_conf   = scalp.get("confidence", "LOW")
            if detected:
                direction = scalp.get("scalp_direction", "")
                s_txt, s_col = _ok(f"DETECTED ({direction})")
                s_dt  = f"{s_conf} conf  —  {scalp.get('reasoning','')[:60]}"
            else:
                s_txt, s_col = _neu("None")
                s_dt = "No 5M sweep setup detected"
            self._ag_scalp_st.config(text=s_txt, fg=s_col)
            self._ag_scalp_dt.config(text=s_dt, fg=C["text2"])

        # ── Sentiment Agent ──────────────────────────────────────────────────
        sent = agents.get("sentiment", {})
        if sent:
            s_val     = sent.get("sentiment", "NEUTRAL")
            tradeable = sent.get("tradeable", True)
            s_color   = (C["red"]    if s_val in ("FEAR", "EXTREME_FEAR")
                         else C["green"] if s_val in ("GREED", "EXTREME_GREED")
                         else C["text2"])
            self._ag_sent_st.config(text=s_val, fg=s_color)
            self._ag_sent_dt.config(
                text=f"Tradeable: {'Yes' if tradeable else 'No'}  —  {sent.get('reasoning','')[:60]}",
                fg=C["text2"])

        # ── Entry Agent ──────────────────────────────────────────────────────
        entry = agents.get("entry", {})
        if entry:
            at_zone   = entry.get("price_at_zone", False)
            z_quality = entry.get("zone_quality", "LOW")
            e_zone    = entry.get("entry_zone", 0)
            if at_zone and z_quality in ("HIGH", "MEDIUM"):
                e_txt, e_col = _ok("AT ZONE")
            elif e_zone:
                e_txt, e_col = _warn("BUILDING")
            else:
                e_txt, e_col = _neu("NOT YET")
            self._ag_entry_st.config(text=e_txt, fg=e_col)
            self._ag_entry_dt.config(
                text=f"Zone: ${e_zone}  Quality: {z_quality}  —  {entry.get('reasoning','')[:50]}",
                fg=C["text2"])

        # ── Risk Manager ─────────────────────────────────────────────────────
        risk = agents.get("risk", {})
        if risk:
            rec     = risk.get("recommendation", "TAKE_TRADE")
            quality = risk.get("trade_quality", "B")
            rr      = risk.get("risk_reward", "?")
            r_color = (C["green"]  if rec == "TAKE_TRADE"
                       else C["red"] if rec in ("SKIP", "WAIT")
                       else C["orange"])
            self._ag_risk_st.config(text=f"{rec}  ({quality})", fg=r_color)
            self._ag_risk_dt.config(
                text=f"R:R {rr}  —  {risk.get('reasoning','')[:60]}",
                fg=C["text2"])

        # ── Session Agent ─────────────────────────────────────────────────────
        sess = agents.get("session", {})
        if sess:
            sq = sess.get("session_quality", "LOW")
            sess_color = (C["green"] if sq == "HIGH"
                          else C["orange"] if sq == "MEDIUM"
                          else C["red"])
            self._ag_sess_st.config(text=sq, fg=sess_color)

            # Build a compact "Asia 3h 12m · London OPEN · NY 6h 37m" countdown line
            countdowns = sess.get("market_countdowns", []) or []
            if countdowns:
                parts = []
                for mc in countdowns:
                    lbl = mc.get("label", "?")
                    if mc.get("is_open"):
                        parts.append(f"{lbl} OPEN")
                    else:
                        parts.append(f"{lbl} {mc.get('countdown','?')}")
                cd_line = "  ·  ".join(parts)
            else:
                # Fallback to old "next kill zone" display
                cd_line = f"Next: {sess.get('next_kill_zone','?')} in {sess.get('mins_to_next_kz','?')} min"

            current_time_pt = sess.get("current_time_pt") or sess.get("current_time_et", "")
            self._ag_sess_dt.config(
                text=f"{sess.get('session','?')}  —  {current_time_pt}  |  {cd_line}",
                fg=C["text2"])

        # ── News Guard Agent ──────────────────────────────────────────────────
        news = agents.get("news_guard", {})
        if news:
            blocked = news.get("trade_blocked", False)
            n_color = C["red"] if blocked else C["green"]
            n_status = "⛔ BLOCKED" if blocked else "✅ CLEAR"
            self._ag_news_st.config(text=n_status, fg=n_color)
            self._ag_news_dt.config(
                text=news.get("reasoning", "")[:80], fg=C["text2"])

        # ── Liquidity Map Agent ───────────────────────────────────────────────
        liq = agents.get("liquidity", {})
        if liq:
            l_bias = liq.get("liquidity_bias", "NEUTRAL")
            l_color = (C["red"] if l_bias == "HUNTING_LOWS"
                       else C["green"] if l_bias == "HUNTING_HIGHS"
                       else C["text2"])
            target  = liq.get("nearest_liquidity_target", "?")
            t_type  = liq.get("target_type", "")
            t_side  = liq.get("target_side", "")
            self._ag_liq_st.config(text=l_bias.replace("_", " "), fg=l_color)
            self._ag_liq_dt.config(
                text=f"Target: ${target} ({t_type} {t_side})  —  {liq.get('reasoning','')[:50]}",
                fg=C["text2"])

        # ── MTF Confluence Agent ──────────────────────────────────────────────
        mtf = agents.get("mtf", {})
        if mtf:
            score = mtf.get("confluence_score", 0)
            conflict = mtf.get("conflict_timeframe")
            m_color = C["green"] if score >= 3 else C["orange"] if score == 2 else C["red"]
            tfs = f"W:{mtf.get('weekly_bias','?')[0]}  D:{mtf.get('daily_bias','?')[0]}  4H:{mtf.get('h4_bias','?')[0]}  1H:{mtf.get('h1_bias','?')[0]}"
            self._ag_mtf_st.config(text=f"{score}/4 TFs", fg=m_color)
            self._ag_mtf_dt.config(
                text=f"{tfs}{'  ⚠️ Conflict: ' + conflict if conflict else ''}",
                fg=C["text2"])

        # ── ICT Pattern Agent ─────────────────────────────────────────────────
        ict = agents.get("ict_pattern", {})
        if ict:
            strongest = ict.get("strongest_pattern", "NONE")
            iq = ict.get("setup_quality", "B")
            i_color = (C["green"] if iq in ("A+", "A")
                       else C["orange"] if iq == "B"
                       else C["red"])
            patterns = ", ".join(ict.get("patterns_detected", [])) or "None"
            self._ag_ict_st.config(text=f"{strongest}  ({iq})", fg=i_color)
            self._ag_ict_dt.config(
                text=f"Patterns: {patterns}  —  {ict.get('reasoning','')[:50]}",
                fg=C["text2"])

        # ── Position Sizing Agent ─────────────────────────────────────────────
        sizing = agents.get("position_size", {})
        if sizing:
            contracts = sizing.get("recommended_contracts", 1)
            risk_usd  = sizing.get("max_risk_dollars", 0)
            s_color   = C["red"] if sizing.get("trade_blocked") else C["green"]
            self._ag_size_st.config(
                text=f"{contracts} contract{'s' if contracts != 1 else ''}",
                fg=s_color)
            self._ag_size_dt.config(
                text=sizing.get("reasoning", "")[:80], fg=C["text2"])

        # ── Strategy Analyst Agent ────────────────────────────────────────────
        sa = agents.get("strategy_analyst", {})
        if sa:
            best_strat   = sa.get("best_strategy", "—")
            market_cond  = sa.get("market_condition", "—")
            sa_conf      = sa.get("confidence", "LOW")
            avoid        = sa.get("avoid_strategy", "")
            sa_color = {
                "ICT_SMC":      C["green"],
                "ORB":          C["blue"],
                "SUPPLY_DEMAND":C["orange"],
                "SCALP":        C["yellow"],
                "WAIT":         C["red"],
            }.get(best_strat, C["text2"])
            conf_tag = {"HIGH": "✅", "MEDIUM": "⚠️", "LOW": "🔴"}.get(sa_conf, "")
            self._ag_strat_st.config(
                text=f"{conf_tag} {best_strat}  ({market_cond})",
                fg=sa_color)
            avoid_txt = f"  Avoid: {avoid}" if avoid and avoid != "NONE" else ""
            self._ag_strat_dt.config(
                text=f"{sa.get('reasoning','')[:70]}{avoid_txt}",
                fg=C["text2"])

        # ── Divergence Agent ─────────────────────────────────────────────────
        div = agents.get("divergence", {})
        if div:
            detected  = div.get("divergence_detected", False)
            div_type  = div.get("divergence_type", "NONE")
            div_dir   = div.get("divergence_direction", "NONE")
            div_str   = div.get("strength", "NONE")
            div_tf    = div.get("timeframe", "")
            if detected and div_type != "NONE":
                d_color = C["green"] if div_dir == "BULLISH" else C["red"]
                self._ag_div_st.config(
                    text=f"{div_dir}  {div_type}  ({div_str})",
                    fg=d_color)
                self._ag_div_dt.config(
                    text=f"{div_tf} — {div.get('reasoning','')[:70]}",
                    fg=C["text2"])
            else:
                self._ag_div_st.config(text="None detected", fg=C["text3"])
                self._ag_div_dt.config(
                    text=div.get("reasoning", "No divergence visible")[:80],
                    fg=C["text3"])

        # ── Pre-Market Agent ──────────────────────────────────────────────────
        pm = agents.get("premarket", {})
        if pm:
            gap_dir  = pm.get("gap_direction", "FLAT")
            gap_sz   = pm.get("gap_size", 0)
            pm_bias  = pm.get("premarket_bias", "NEUTRAL")
            play     = pm.get("likely_play", "WAIT")
            key_lvl  = pm.get("key_level", 0)
            gap_color = (C["green"] if gap_dir == "UP"
                         else C["red"] if gap_dir == "DOWN"
                         else C["text3"])
            play_color = (C["green"] if play == "GAP_GO"
                          else C["orange"] if play == "GAP_FILL"
                          else C["blue"] if play == "RANGE_BREAK"
                          else C["text3"])
            self._ag_pm_st.config(
                text=f"Gap {gap_dir} {gap_sz:.1f}pt  |  {play}",
                fg=play_color)
            self._ag_pm_dt.config(
                text=f"Bias: {pm_bias}  Key: {key_lvl}  —  {pm.get('reasoning','')[:50]}",
                fg=C["text2"])

        # ── Veto banner ──────────────────────────────────────────────────────
        setup_type = analysis.get("setup_type", "")
        if setup_type == "NEWS_BLOCK":
            self._ag_veto_lbl.config(
                text=f"📰  NEWS GUARD BLOCK — {news.get('reasoning','')[:100]}",
                fg=C["red"])
        elif setup_type == "RISK_VETO":
            self._ag_veto_lbl.config(
                text=f"⛔  RISK MANAGER VETO — {risk.get('reasoning','')[:100]}",
                fg=C["red"])
        elif setup_type == "MOMENTUM_EXHAUSTED":
            self._ag_veto_lbl.config(
                text=f"⚠️  MOMENTUM EXHAUSTED — {mom.get('reasoning','')[:100]}",
                fg=C["orange"])
        elif sess and sess.get("session_quality") == "AVOID":
            self._ag_veto_lbl.config(
                text=f"🕐  DEAD ZONE — {sess.get('session','')} — avoid trading now",
                fg=C["orange"])
        else:
            self._ag_veto_lbl.config(text="")

    def _toggle_agents(self):
        """Enable/disable multi-agent mode."""
        if not AGENTS_AVAILABLE:
            self.agents_var.set(False)
            messagebox.showwarning("Multi-Agent",
                "agent_system.py not found. Make sure it's in the ChartVision folder.")
            return
        if self.agents_var.get():
            api_key = self.api_key_var.get().strip()
            if not api_key:
                self.agents_var.set(False)
                messagebox.showwarning("Multi-Agent", "Enter your API key first.")
                return
            try:
                self.agent_orchestrator = AgentOrchestrator(api_key)
                self._use_agents = True
                self.log("🤖  Multi-Agent Mode ON — Bias + Entry + Scalp agents running in parallel", "signal_buy")
                self.log("    Each scan uses 3 specialized agents instead of 1 general one.\n", "info")
            except Exception as e:
                self.agents_var.set(False)
                self.log(f"❌  Multi-Agent init failed: {e}", "alert")
        else:
            self.agent_orchestrator = None
            self._use_agents = False
            self.log("🤖  Multi-Agent Mode OFF — back to single-agent analysis\n", "info")

    # ──────────────────────────────────────────────────────────
    #  Run
    # ──────────────────────────────────────────────────────────

    def _startup_connection_check(self):
        """Auto-run on launch: verify API key + auto-connect TastyTrade if creds saved."""
        self.log("🔍  Running startup checks…", "header")
        self.log("─" * 32)

        # ── 1. API Key ───────────────────────────────────────────────────────
        api_key = self.api_key_var.get().strip()
        if api_key and api_key.startswith("sk-ant"):
            self.log("✅  Anthropic API key detected", "signal_buy")
        elif api_key:
            self.log("⚠️  API key found but format looks off — double-check it", "alert")
        else:
            self.log("❌  No API key — enter it in Settings before trading", "signal_sell")

        # ── 2. TastyTrade ────────────────────────────────────────────────────
        username = self.config.get("tt_username", "").strip()
        password = self.config.get("tt_password", "").strip()

        if not username or not password:
            self.log("⚠️  TastyTrade credentials not saved", "alert")
            self.log("    → Go to Broker tab and click Connect", "info")
            self.log("")
            self._startup_summary(api_ok=bool(api_key), broker_ok=False)
            return

        # Credentials found — attempt auto-connect in background thread
        self.log("🔗  Auto-connecting to TastyTrade…", "info")

        def _auto_connect():
            try:
                broker = TastytradeBroker(username, password,
                                         sandbox=self.sandbox_var.get())
                result = broker.login()

                if result is True:
                    accounts = broker.get_accounts()
                    if accounts:
                        a = accounts[0]
                        broker.set_account(a.get("account-number", ""))
                        self.broker = broker

                        def _on_success():
                            self._set_broker_status("Connected", True)
                            self.log("✅  TastyTrade connected!", "signal_buy")
                            self.log(f"    Account: {a.get('account-number','N/A')}", "info")
                            self.log("")
                            self._startup_summary(api_ok=bool(api_key), broker_ok=True)
                            self.show_balance()
                            self.show_positions()

                        self.root.after(0, _on_success)
                    else:
                        self.root.after(0, lambda: self._startup_broker_fail("No accounts found"))
                elif result == TastytradeBroker.DEVICE_CHALLENGE:
                    # Device challenge — can't auto-complete, ask user to connect manually
                    def _on_challenge():
                        self.log("📱  TastyTrade needs device verification", "alert")
                        self.log("    → Go to Broker tab and click Connect to complete it", "info")
                        self.log("")
                        self._startup_summary(api_ok=bool(api_key), broker_ok=False)
                    self.root.after(0, _on_challenge)
                else:
                    self.root.after(0, lambda: self._startup_broker_fail("Login failed — check credentials"))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: self._startup_broker_fail(err))

        import threading
        t = threading.Thread(target=_auto_connect, daemon=True)
        t.start()

    def _startup_broker_fail(self, reason: str):
        """Called on main thread when auto-connect fails."""
        self._set_broker_status("Not connected", False)
        self.log(f"❌  TastyTrade: {reason}", "signal_sell")
        self.log("    → Go to Broker tab and click Connect", "info")
        self.log("")
        api_key = self.api_key_var.get().strip()
        self._startup_summary(api_ok=bool(api_key), broker_ok=False)

    def _startup_summary(self, api_ok: bool, broker_ok: bool):
        """Print final startup status banner."""
        self.log("─" * 32)
        # Initialise the live stats panel right away
        self.root.after(100, self._update_daily_stats)
        if api_ok and broker_ok:
            self.log("🟢  ALL SYSTEMS GO — ready to trade!", "signal_buy")
            self.log("    Select your chart region and hit Start Monitoring", "info")
        elif api_ok and not broker_ok:
            self.log("🟡  API ready — fix TastyTrade before trading", "alert")
            self.log("    Broker tab → Connect", "info")
        elif not api_ok and broker_ok:
            self.log("🟡  Broker ready — add API key before trading", "alert")
            self.log("    Settings tab → Anthropic API key", "info")
        else:
            self.log("🔴  Setup needed before trading:", "signal_sell")
            self.log("    1. Settings tab → enter Anthropic API key", "info")
            self.log("    2. Broker tab → Connect TastyTrade", "info")
        self.log("")

    # ──────────────────────────────────────────────────────────
    #  Sound Alerts
    # ──────────────────────────────────────────────────────────

    def _play_alert(self, signal_type: str):
        """Play a system sound for the given signal type (non-blocking, cross-platform)."""
        if not self.sound_var.get():
            return
        key = signal_type.upper()

        if IS_MAC:
            # macOS: use afplay with .aiff system sounds
            sound_file = MAC_SOUNDS.get(key)
            if sound_file and os.path.exists(sound_file):
                try:
                    subprocess.Popen(
                        ["afplay", sound_file],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                except Exception:
                    pass

        elif IS_WINDOWS and WINSOUND_AVAILABLE:
            # Windows: use winsound MessageBeep (plays instantly, non-blocking via thread)
            sound_type = WIN_SOUNDS.get(key)
            if sound_type is not None:
                def _beep():
                    try:
                        import winsound as _ws
                        _ws.MessageBeep(sound_type)
                    except Exception:
                        pass
                threading.Thread(target=_beep, daemon=True).start()

        elif IS_LINUX:
            # Linux: try paplay or aplay with /usr/share/sounds if available
            # Falls back to terminal bell if nothing found
            try:
                subprocess.Popen(
                    ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception:
                try:
                    # Terminal bell fallback
                    subprocess.Popen(
                        ["bash", "-c", "echo -e '\\a'"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                except Exception:
                    pass

    # ──────────────────────────────────────────────────────────
    #  Trade Grade System
    # ──────────────────────────────────────────────────────────

    def _grade_trade(self, pnl: float, exit_price: float, trade_info: dict):
        """
        After a trade closes, show a grading popup so the trader reflects
        on execution quality independently of the P&L outcome.
        """
        win = pnl > 0
        popup = tk.Toplevel(self.root)
        popup.title("Grade Your Trade")
        popup.configure(bg=C["card"])
        popup.geometry("420x380")
        popup.resizable(False, False)
        popup.grab_set()

        pnl_color = C["green"] if win else C["red"]
        pnl_str   = f"{'+'if pnl>=0 else ''}${pnl:.2f}"

        tk.Label(popup, text="📋  TRADE REVIEW",
                 font=FONT_CARD, bg=C["card"], fg=C["text3"]).pack(pady=(14,2))
        tk.Label(popup, text=f"Result: {pnl_str}  ({'WIN' if win else 'LOSS'})",
                 font=("Helvetica Neue", 16, "bold"),
                 bg=C["card"], fg=pnl_color).pack(pady=(0,10))

        tk.Label(popup,
                 text="Grade your EXECUTION — not the outcome.\nDid you follow the rules?",
                 font=FONT_SMALL, bg=C["card"], fg=C["text2"],
                 justify="center").pack(pady=(0,12))

        grade_var = tk.StringVar(value="B")

        grades = [
            ("A+", "Perfect — waited for full confirmation, ideal entry, held to target",   C["green"]),
            ("A",  "Good — followed the rules with minor deviations",                        C["green"]),
            ("B",  "Acceptable — some rule breaks but manageable",                           C["orange"]),
            ("C",  "Poor — chased entry, moved stop, or ignored checklist",                  C["red"]),
            ("F",  "Revenge trade / FOMO / broke every rule",                                C["red"]),
        ]
        for gval, gdesc, gcol in grades:
            f = tk.Frame(popup, bg=C["card2"],
                         highlightthickness=1, highlightbackground=C["border"])
            f.pack(fill=tk.X, padx=16, pady=2)
            tk.Radiobutton(f, text=f"  {gval}  —  {gdesc}",
                           variable=grade_var, value=gval,
                           font=FONT_SMALL, bg=C["card2"],
                           fg=gcol, selectcolor=C["card2"],
                           activebackground=C["card2"],
                           anchor="w").pack(fill=tk.X, padx=6, pady=4)

        def _submit():
            grade = grade_var.get()
            grade_colors = {"A+": C["green"], "A": C["green"],
                            "B": C["orange"], "C": C["red"], "F": C["red"]}
            self.log(f"   📋  Trade Grade: {grade}  |  P&L: {pnl_str}", "info")
            if grade in ("C", "F"):
                self.log("   ⚠️  Review your rules — discipline is the edge.", "alert")
            elif grade in ("A+", "A"):
                self.log("   ✅  Great execution! Process over outcome.", "signal_buy")
            # Store grade in trade memory if possible
            try:
                self.trade_memory.add_note(
                    f"Grade: {grade} | Exit: ${exit_price}")
            except Exception:
                pass
            popup.destroy()
            # Auto-refresh journal
            self._refresh_journal()

        AppleButton(popup, "Save Grade", command=_submit,
                    style="default").pack(pady=12)

    # ──────────────────────────────────────────────────────────
    #  Revenge Trade Detector
    # ──────────────────────────────────────────────────────────

    def _revenge_trade_check(self) -> bool:
        """
        Detect potential revenge/emotional trading.
        Returns True if the trade should be BLOCKED, False if OK to proceed.
        """
        now = datetime.now()
        COOLDOWN_MINUTES = 15   # must wait 15 min after a loss

        # Check 1: too soon after a loss
        if self._last_loss_time:
            mins_since_loss = (now - self._last_loss_time).total_seconds() / 60
            if mins_since_loss < COOLDOWN_MINUTES:
                mins_left = int(COOLDOWN_MINUTES - mins_since_loss)
                msg = (f"⚠️  REVENGE TRADE ALERT\n\n"
                       f"You just had a loss {int(mins_since_loss)} minute(s) ago.\n\n"
                       f"Revenge trading is the #1 account killer.\n"
                       f"Cooldown: {mins_left} minute(s) remaining.\n\n"
                       f"Are you sure you want to trade right now?")
                self.log(f"⚠️  Revenge trade warning — {int(mins_since_loss)}m since last loss "
                         f"(cooldown: {mins_left}m left)", "alert")
                proceed = messagebox.askyesno(
                    "Revenge Trade Warning", msg, icon="warning")
                if not proceed:
                    self.log("   ✅  Good call — sitting out. Discipline is the edge.", "signal_buy")
                    return True   # blocked

        # Check 2: consecutive losses streak
        if self._consecutive_losses >= 2:
            msg = (f"⚠️  LOSING STREAK ALERT\n\n"
                   f"You've had {self._consecutive_losses} losses in a row.\n\n"
                   f"This is when emotional trading peaks.\n"
                   f"Consider stepping away or reducing size.\n\n"
                   f"Still want to take this trade?")
            self.log(f"⚠️  {self._consecutive_losses} consecutive losses — "
                     f"are you trading emotionally?", "alert")
            proceed = messagebox.askyesno(
                "Losing Streak Warning", msg, icon="warning")
            if not proceed:
                self.log("   ✅  Smart — protecting your capital.", "signal_buy")
                return True   # blocked

        return False   # all clear

    # ──────────────────────────────────────────────────────────
    #  Trade Journal
    # ──────────────────────────────────────────────────────────

    def _refresh_journal(self):
        """Load all completed trades from TradeMemory and populate journal UI."""
        try:
            trades = self.trade_memory.get_all_trades()
        except Exception:
            trades = []

        # ── Stats ─────────────────────────────────────────────
        total_pnl  = sum(t.get("pnl", 0) or 0 for t in trades)
        wins       = [t for t in trades if (t.get("pnl", 0) or 0) > 0]
        losses     = [t for t in trades if (t.get("pnl", 0) or 0) < 0]
        win_rate   = (len(wins) / len(trades) * 100) if trades else 0
        best_pnl   = max((t.get("pnl", 0) or 0 for t in trades), default=0)
        worst_pnl  = min((t.get("pnl", 0) or 0 for t in trades), default=0)

        pnl_color  = C["green"] if total_pnl >= 0 else C["red"]
        self._j_pnl.config(
            text=f"{'+'if total_pnl>=0 else ''}${total_pnl:.2f}",
            fg=pnl_color)
        self._j_winrate.config(text=f"{win_rate:.0f}%")
        self._j_trades.config(text=str(len(trades)))
        self._j_best.config(
            text=f"+${best_pnl:.2f}" if best_pnl else "—",
            fg=C["green"])
        self._j_worst.config(
            text=f"-${abs(worst_pnl):.2f}" if worst_pnl < 0 else "—",
            fg=C["red"])

        # ── Equity Curve ──────────────────────────────────────
        if MATPLOTLIB_AVAILABLE and trades:
            equity = []
            running = 0.0
            for t in sorted(trades, key=lambda x: x.get("timestamp", "")):
                running += t.get("pnl", 0) or 0
                equity.append(running)

            # Destroy previous canvas if any
            if self._j_canvas:
                try:
                    self._j_canvas.get_tk_widget().destroy()
                except Exception:
                    pass
                self._j_canvas = None

            fig = Figure(figsize=(6, 1.2), dpi=80, facecolor=C["card"])
            ax  = fig.add_subplot(111)
            ax.set_facecolor(C["card"])
            color = C["green"] if equity[-1] >= 0 else C["red"]
            ax.plot(equity, color=color, linewidth=1.5)
            ax.fill_between(range(len(equity)), equity, 0,
                            color=color, alpha=0.15)
            ax.axhline(0, color=C["border"], linewidth=0.8, linestyle="--")
            ax.tick_params(colors=C["text3"], labelsize=7)
            ax.spines[:].set_color(C["border"])
            fig.tight_layout(pad=0.5)

            self._j_canvas = FigureCanvasTkAgg(fig, master=self._j_chart_frame)
            self._j_canvas.draw()
            self._j_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # ── Trade rows ────────────────────────────────────────
        self._j_listbox.delete(0, tk.END)
        if not trades:
            self._j_listbox.insert(tk.END, "  No completed trades yet.")
            return

        for i, t in enumerate(reversed(trades), 1):
            ts   = t.get("timestamp", "")[:16] if t.get("timestamp") else "—"
            sym  = t.get("symbol", "?")
            typ  = t.get("option_type", "?")
            entr = t.get("entry_price", 0) or 0
            ext  = t.get("exit_price",  0) or 0
            pnl  = t.get("pnl",         0) or 0
            hold = t.get("hold_minutes", "?")
            res  = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BE"
            pnl_str = f"{'+'if pnl>=0 else ''}${pnl:.2f}"
            row  = (f"  {i:<4} {ts:<17} {sym:<6} {typ:<5} "
                    f"${entr:<7.2f} ${ext:<7.2f} {pnl_str:<9} "
                    f"{str(hold)+'m':<7} {res}")
            tag = "win" if pnl > 0 else "loss" if pnl < 0 else ""
            self._j_listbox.insert(tk.END, row)
            if tag:
                self._j_listbox.itemconfig(tk.END, fg=C["green"] if tag=="win" else C["red"])

    # ──────────────────────────────────────────────────────────
    #  Keyboard Hotkeys
    # ──────────────────────────────────────────────────────────

    def _bind_hotkeys(self):
        """Register global keyboard shortcuts."""
        root = self.root
        # Ctrl/Cmd+M  →  Toggle Monitor
        root.bind_all("<Control-m>", lambda e: self.toggle_monitoring())
        root.bind_all("<Command-m>", lambda e: self.toggle_monitoring())
        # Ctrl/Cmd+A  →  Analyze Once
        root.bind_all("<Control-a>", lambda e: self._analyze_once())
        root.bind_all("<Command-a>", lambda e: self._analyze_once())
        # Ctrl/Cmd+E  →  Execute / Open trade dialog
        root.bind_all("<Control-e>", lambda e: self.open_trade_dialog())
        root.bind_all("<Command-e>", lambda e: self.open_trade_dialog())
        # Ctrl/Cmd+W  →  Close / Exit active trade
        root.bind_all("<Control-w>", lambda e: self._exit_trade_mode())
        root.bind_all("<Command-w>", lambda e: self._exit_trade_mode())
        # Ctrl/Cmd+R  →  Refresh journal
        root.bind_all("<Control-r>", lambda e: self._refresh_journal())
        root.bind_all("<Command-r>", lambda e: self._refresh_journal())

    def _analyze_once(self):
        """Run a single analysis (hotkey wrapper for analyze_once)."""
        try:
            self.analyze_once()
        except Exception:
            pass

    def run(self):
        self.log("🚀  Chart Vision — Loading…")
        self.log("⌨️  Hotkeys: ⌘M=Monitor  ⌘A=Analyze  ⌘E=Execute  ⌘W=Close Trade  ⌘R=Journal", "info")
        self.log("")
        # Run startup check after UI is fully rendered (500ms delay)
        self.root.after(500, self._startup_connection_check)
        self.root.mainloop()


def main():
    app = ChartVisionApp()
    app.run()


if __name__ == "__main__":
    main()
