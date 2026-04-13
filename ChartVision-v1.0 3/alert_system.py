"""
Alert System Module
Handles desktop notifications and alert condition checking.
"""

import platform
import subprocess
from datetime import datetime


class AlertSystem:
    """Manages trading alerts and desktop notifications."""

    def __init__(self):
        self.alert_history = []
        self.alert_rules = {
            "rsi_overbought": {"enabled": True, "threshold": 70},
            "rsi_oversold": {"enabled": True, "threshold": 30},
            "strong_buy": {"enabled": True},
            "strong_sell": {"enabled": True},
            "pattern_detected": {"enabled": True},
        }

    def check_alerts(self, analysis: dict) -> list:
        """
        Check analysis results against alert rules.
        Returns a list of triggered alert messages.
        """
        triggered = []

        # Check RSI conditions
        indicators = analysis.get("indicators", {})
        rsi = indicators.get("rsi")
        if rsi is not None and isinstance(rsi, (int, float)):
            if self.alert_rules["rsi_overbought"]["enabled"] and rsi >= self.alert_rules["rsi_overbought"]["threshold"]:
                triggered.append(f"⚠️ RSI OVERBOUGHT: {rsi} (above {self.alert_rules['rsi_overbought']['threshold']})")
            if self.alert_rules["rsi_oversold"]["enabled"] and rsi <= self.alert_rules["rsi_oversold"]["threshold"]:
                triggered.append(f"⚠️ RSI OVERSOLD: {rsi} (below {self.alert_rules['rsi_oversold']['threshold']})")

        # Check signal strength
        signals = analysis.get("signals", {})
        overall = signals.get("overall", "")
        if self.alert_rules["strong_buy"]["enabled"] and overall == "STRONG_BUY":
            triggered.append(f"🟢🟢 STRONG BUY SIGNAL detected! {signals.get('reasoning', '')}")
        if self.alert_rules["strong_sell"]["enabled"] and overall == "STRONG_SELL":
            triggered.append(f"🔴🔴 STRONG SELL SIGNAL detected! {signals.get('reasoning', '')}")

        # Check trade action — ENTER NOW is the big one
        trade = analysis.get("trade_action", {})
        should_trade = trade.get("should_trade", "")
        if should_trade == "YES_ENTER_NOW":
            direction = trade.get("direction", "")
            entry = trade.get("entry_price", "")
            sl = trade.get("stop_loss", "")
            tp1 = trade.get("take_profit_1", "")
            triggered.append(
                f"🚀 TRADE NOW: {direction} at ${entry} | SL: ${sl} | TP: ${tp1} | {trade.get('reasoning', '')}"
            )

        # Check for chart patterns
        patterns = analysis.get("patterns", {})
        formations = patterns.get("formations")
        if self.alert_rules["pattern_detected"]["enabled"] and formations and formations.lower() not in ("none", "n/a", ""):
            triggered.append(f"📊 PATTERN: {formations}")

        # Check analysis-provided alerts
        chart_alerts = analysis.get("alerts", [])
        for alert in chart_alerts:
            if alert and alert.strip():
                triggered.append(f"📢 {alert}")

        # Log triggered alerts
        for alert_msg in triggered:
            self.alert_history.append({
                "timestamp": datetime.now().isoformat(),
                "message": alert_msg,
                "symbol": analysis.get("symbol", "UNKNOWN"),
            })

        return triggered

    def send_notification(self, title: str, message: str):
        """Send a desktop notification (cross-platform)."""
        system = platform.system()

        try:
            if system == "Darwin":  # macOS
                subprocess.run([
                    "osascript", "-e",
                    f'display notification "{message}" with title "{title}" sound name "Glass"'
                ], capture_output=True, timeout=5)

            elif system == "Windows":
                # Use PowerShell toast notification
                ps_script = f"""
                [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
                [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null
                $template = @"
                <toast>
                    <visual>
                        <binding template="ToastGeneric">
                            <text>{title}</text>
                            <text>{message}</text>
                        </binding>
                    </visual>
                    <audio src="ms-winsoundevent:Notification.Default"/>
                </toast>
"@
                $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
                $xml.LoadXml($template)
                $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
                [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("TradingView Vision").Show($toast)
                """
                subprocess.run(["powershell", "-Command", ps_script], capture_output=True, timeout=10)

            elif system == "Linux":
                subprocess.run(["notify-send", title, message], capture_output=True, timeout=5)

            else:
                print(f"[ALERT] {title}: {message}")

        except Exception as e:
            # Fallback: print to console
            print(f"[ALERT] {title}: {message}")
            print(f"  (Notification error: {e})")

    def notify_alerts(self, alerts: list, symbol: str = "Chart"):
        """Send desktop notifications for each triggered alert."""
        for alert_msg in alerts:
            self.send_notification(
                title=f"TradingView Vision - {symbol}",
                message=alert_msg[:200],  # Truncate for notification limits
            )

    def get_history(self) -> list:
        """Return alert history."""
        return self.alert_history.copy()

    def update_rules(self, rules: dict):
        """Update alert rules from a config dict."""
        for key, value in rules.items():
            if key in self.alert_rules:
                self.alert_rules[key].update(value)
