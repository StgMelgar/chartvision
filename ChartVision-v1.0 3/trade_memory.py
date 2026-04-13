"""
trade_memory.py — ChartVision Trade Memory Layer
Inspired by Ruflo's AgentDB / RuVector intelligence layer.

Stores every trade outcome in SQLite so the AI learns from YOUR history.
Injects win-rate patterns into future analysis so it trades smarter over time.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path


DB_PATH = Path(__file__).parent / "trade_memory.db"


# ──────────────────────────────────────────────────────────────────────────────
#  Schema
# ──────────────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    option_type     TEXT NOT NULL,          -- CALL or PUT
    setup_type      TEXT,                   -- FVG_ENTRY, OB_ENTRY, BOS_ENTRY, SCALP, etc.
    bias            TEXT,                   -- BULLISH / BEARISH
    entry_price     REAL,                   -- actual fill price
    stop_loss       REAL,
    take_profit_1   REAL,
    take_profit_2   REAL,
    exit_price      REAL,                   -- filled on close
    outcome         TEXT,                   -- WIN / LOSS / BREAKEVEN
    pnl_dollars     REAL,
    hold_minutes    REAL,
    time_of_day     TEXT,                   -- HH:MM (entry time bucket)
    extra_notes     TEXT
);

CREATE TABLE IF NOT EXISTS pattern_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    setup_type      TEXT NOT NULL,
    option_type     TEXT NOT NULL,
    time_bucket     TEXT,                   -- e.g. "09:30-10:00", "10:00-11:00"
    win_count       INTEGER DEFAULT 0,
    loss_count      INTEGER DEFAULT 0,
    total_pnl       REAL DEFAULT 0.0,
    avg_hold_min    REAL DEFAULT 0.0,
    last_updated    TEXT,
    UNIQUE(symbol, setup_type, option_type, time_bucket)
);
"""


# ──────────────────────────────────────────────────────────────────────────────
#  TradeMemory
# ──────────────────────────────────────────────────────────────────────────────

class TradeMemory:
    """
    Ruflo-inspired AgentDB for ChartVision.
    Records trade outcomes and surfaces win-rate patterns to the AI.
    """

    def __init__(self, db_path: str = None):
        self.db_path = str(db_path or DB_PATH)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_SCHEMA)

    # ── Record a trade entry ──────────────────────────────────────────────────

    def record_entry(self, trade_info: dict) -> int:
        """Call this when a trade is executed. Returns the trade ID."""
        now = datetime.now()
        time_bucket = self._time_bucket(now.strftime("%H:%M"))
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("""
                INSERT INTO trades
                  (timestamp, symbol, option_type, setup_type, bias,
                   entry_price, stop_loss, take_profit_1, take_profit_2,
                   time_of_day, extra_notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                now.isoformat(),
                trade_info.get("symbol", "QQQ"),
                trade_info.get("option_type", "CALL"),
                trade_info.get("setup", "UNKNOWN"),
                trade_info.get("timeframe_bias", ""),
                trade_info.get("entry_price", 0),
                trade_info.get("stop_loss", 0),
                trade_info.get("take_profit_1", 0),
                trade_info.get("take_profit_2", 0),
                time_bucket,
                trade_info.get("reasoning", "")[:500],
            ))
            return cur.lastrowid

    # ── Record a trade exit ───────────────────────────────────────────────────

    def record_exit(self, trade_id: int, exit_price: float,
                    entry_price: float, option_type: str,
                    contracts: int = 1, premium_paid: float = 0.0,
                    hold_minutes: float = 0.0):
        """Call this when the user closes a trade."""
        # For options P&L: estimate based on underlying move × delta (~0.5 for ATM)
        delta        = 0.5
        underlying_move = (exit_price - entry_price) if option_type == "CALL" else (entry_price - exit_price)
        est_option_move = underlying_move * delta
        pnl_per_contract = est_option_move * 100   # 100 shares per contract
        pnl_dollars  = pnl_per_contract * contracts

        outcome = "WIN" if pnl_dollars > 0 else ("LOSS" if pnl_dollars < 0 else "BREAKEVEN")

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE trades
                SET exit_price=?, outcome=?, pnl_dollars=?, hold_minutes=?
                WHERE id=?
            """, (exit_price, outcome, round(pnl_dollars, 2), hold_minutes, trade_id))

            # Fetch the trade to update pattern_stats
            row = conn.execute(
                "SELECT symbol, setup_type, option_type, time_of_day FROM trades WHERE id=?",
                (trade_id,)
            ).fetchone()

        if row:
            self._update_pattern_stats(row[0], row[1] or "UNKNOWN",
                                       row[2], row[3], pnl_dollars, hold_minutes)
        return pnl_dollars

    # ── Query: what does history say about this setup? ────────────────────────

    def get_pattern_context(self, symbol: str, setup_type: str,
                            option_type: str, current_time: str = None) -> str:
        """
        Returns a short natural-language summary injected into the AI prompt.
        Example: 'Last 8 QQQ BOS PUT trades: 6W 2L (75%), avg +$142, best at 09:30-10:00'
        """
        time_bucket = self._time_bucket(current_time) if current_time else None

        with sqlite3.connect(self.db_path) as conn:
            # Overall stats for this pattern
            row = conn.execute("""
                SELECT win_count, loss_count, total_pnl, avg_hold_min
                FROM pattern_stats
                WHERE symbol=? AND setup_type=? AND option_type=?
                ORDER BY last_updated DESC LIMIT 1
            """, (symbol.upper(), setup_type, option_type)).fetchone()

            # Best time bucket
            best_time = conn.execute("""
                SELECT time_bucket, win_count, loss_count
                FROM pattern_stats
                WHERE symbol=? AND setup_type=? AND option_type=?
                ORDER BY (win_count * 1.0 / MAX(win_count+loss_count, 1)) DESC
                LIMIT 1
            """, (symbol.upper(), setup_type, option_type)).fetchone()

            # Recent trades (last 5)
            recent = conn.execute("""
                SELECT outcome, pnl_dollars, time_of_day
                FROM trades
                WHERE symbol=? AND setup_type=? AND option_type=?
                  AND outcome IS NOT NULL
                ORDER BY timestamp DESC LIMIT 5
            """, (symbol.upper(), setup_type, option_type)).fetchall()

        if not row or (row[0] + row[1]) == 0:
            return ""   # No history yet

        wins, losses, total_pnl, avg_hold = row
        total   = wins + losses
        win_pct = int(wins / total * 100) if total > 0 else 0
        avg_pnl = round(total_pnl / total, 0) if total > 0 else 0

        lines = [
            f"\n📊 PATTERN MEMORY — {symbol} {setup_type} {option_type}:",
            f"   Last {total} trades: {wins}W {losses}L ({win_pct}% win rate)",
            f"   Avg P&L: ${avg_pnl:+.0f}  |  Avg hold: {avg_hold:.0f} min",
        ]
        if best_time and best_time[0]:
            bt_total = best_time[1] + best_time[2]
            bt_pct   = int(best_time[1] / bt_total * 100) if bt_total > 0 else 0
            lines.append(f"   Best time: {best_time[0]} ({bt_pct}% win rate at that hour)")
        if recent:
            rec_str = "  ".join(
                f"{'✅' if r[0]=='WIN' else '❌'}"
                f"{'${:+.0f}'.format(r[1]) if r[1] else ''}"
                for r in recent
            )
            lines.append(f"   Recent: {rec_str}")

        # Time-specific boost/warning
        if time_bucket:
            tb_row = conn.execute("""
                SELECT win_count, loss_count FROM pattern_stats
                WHERE symbol=? AND setup_type=? AND option_type=? AND time_bucket=?
            """, (symbol.upper(), setup_type, option_type, time_bucket)).fetchone() if False else None
            # (inline conn closed — skip time-specific for now, handled by best_time)

        return "\n".join(lines)

    # ── All trades summary ────────────────────────────────────────────────────

    def get_summary(self) -> dict:
        """Returns overall trading stats for the UI dashboard."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN outcome='WIN'  THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses,
                    COALESCE(SUM(pnl_dollars), 0) as total_pnl,
                    COALESCE(AVG(hold_minutes), 0) as avg_hold
                FROM trades WHERE outcome IS NOT NULL
            """).fetchone()

            top_setups = conn.execute("""
                SELECT setup_type,
                       SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as w,
                       COUNT(*) as t,
                       SUM(pnl_dollars) as pnl
                FROM trades WHERE outcome IS NOT NULL
                GROUP BY setup_type ORDER BY pnl DESC LIMIT 3
            """).fetchall()

        total, wins, losses, total_pnl, avg_hold = row
        return {
            "total_trades": total or 0,
            "wins":         wins or 0,
            "losses":       losses or 0,
            "win_rate":     round((wins or 0) / max(total, 1) * 100, 1),
            "total_pnl":    round(total_pnl or 0, 2),
            "avg_hold_min": round(avg_hold or 0, 1),
            "top_setups":   [{"setup": r[0], "wins": r[1],
                              "total": r[2], "pnl": r[3]} for r in top_setups],
        }

    def get_recent_trades(self, limit: int = 20) -> list:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT timestamp, symbol, option_type, setup_type,
                       entry_price, exit_price, outcome, pnl_dollars, hold_minutes
                FROM trades ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()
        return [
            {"timestamp": r[0], "symbol": r[1], "option_type": r[2],
             "setup_type": r[3], "entry_price": r[4], "exit_price": r[5],
             "outcome": r[6], "pnl_dollars": r[7], "hold_minutes": r[8]}
            for r in rows
        ]

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _time_bucket(self, time_str: str) -> str:
        """Convert HH:MM to an hourly bucket like '09:30-10:30'."""
        try:
            h, m = map(int, time_str.split(":"))
            # Round down to nearest 30min for more granular buckets
            m_bucket = 0 if m < 30 else 30
            start = f"{h:02d}:{m_bucket:02d}"
            end_h, end_m = (h, m_bucket + 30) if m_bucket == 0 else (h + 1, 0)
            end   = f"{end_h:02d}:{end_m:02d}"
            return f"{start}-{end}"
        except Exception:
            return "unknown"

    def _update_pattern_stats(self, symbol, setup_type, option_type,
                               time_bucket, pnl, hold_min):
        win = 1 if pnl > 0 else 0
        loss = 1 if pnl < 0 else 0
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO pattern_stats
                  (symbol, setup_type, option_type, time_bucket,
                   win_count, loss_count, total_pnl, avg_hold_min, last_updated)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(symbol, setup_type, option_type, time_bucket)
                DO UPDATE SET
                    win_count    = win_count + excluded.win_count,
                    loss_count   = loss_count + excluded.loss_count,
                    total_pnl    = total_pnl + excluded.total_pnl,
                    avg_hold_min = (avg_hold_min + excluded.avg_hold_min) / 2.0,
                    last_updated = excluded.last_updated
            """, (symbol, setup_type or "UNKNOWN", option_type,
                  time_bucket or "unknown", win, loss, pnl, hold_min, now))
