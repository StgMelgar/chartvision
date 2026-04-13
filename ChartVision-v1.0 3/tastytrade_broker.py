"""
Tastytrade Broker Module
Handles authentication, account data, positions, and order execution via Tastytrade API.

Tastytrade offers:
- Official REST API with session-token auth
- Full options trading including 0DTE SPY/XSP/SPX
- Commission: $1/contract to open, $0 to close (great for 0DTE!)
- No platform fees

API docs: https://developer.tastytrade.com/
"""

import json
import time
import requests
from datetime import datetime, date


# ── Tastytrade API base URLs ────────────────────────────────────────────────
LIVE_BASE   = "https://api.tastytrade.com"
SANDBOX_BASE = "https://api.cert.tastytrade.com"   # certification / sandbox


class TastytradeError(Exception):
    """Raised when the Tastytrade API returns an error."""
    pass


class TastytradeBroker:
    """
    Manages Tastytrade broker connection and options trading operations.

    Authentication flow:
        broker = TastytradeBroker(username, password)
        broker.login()          # gets session token
        accounts = broker.get_accounts()
        broker.set_account(accounts[0]["account-number"])
        positions = broker.get_positions()

    Order flow (always preview first):
        preview = broker.preview_options_order(...)
        if confirmed:
            result = broker.place_options_order(...)
    """

    def __init__(self, username: str, password: str, sandbox: bool = False):
        self.username  = username
        self.password  = password
        self.base_url  = SANDBOX_BASE if sandbox else LIVE_BASE
        self.sandbox   = sandbox

        self.session_token  = None
        self.remember_token = None
        self.connected      = False
        self.account_number = None
        self._session       = requests.Session()

    # ── Authentication ───────────────────────────────────────────────────────

    # Special return value for device challenge
    DEVICE_CHALLENGE = "device_challenge"

    def login(self, otp: str = None) -> "bool | str":
        """
        Authenticate with Tastytrade.

        Returns:
          True                    — success, connected
          False                   — wrong credentials or other error
          DEVICE_CHALLENGE str    — Tastytrade requires device verification;
                                    a code was sent to your email/SMS.
                                    Call complete_device_challenge(otp) next.

        otp: 6-digit verification code (2FA or device challenge).
        """
        url  = f"{self.base_url}/sessions"
        body = {
            "login":       self.username,
            "password":    self.password,
            "remember-me": True,
        }
        # Include challenge token + OTP in headers (Tastytrade requires both in headers, not body)
        extra_headers = {}
        if getattr(self, "_challenge_token", None):
            extra_headers["X-Tastyworks-Challenge-Token"] = self._challenge_token
        if otp:
            extra_headers["X-Tastyworks-OTP"] = otp.strip()

        try:
            resp = self._session.post(url, json=body,
                                      headers=extra_headers, timeout=15)
            data = resp.json()

            if resp.status_code == 201:
                sess = data.get("data", {})
                self.session_token  = sess.get("session-token")
                self.remember_token = sess.get("remember-token")
                self._session.headers.update({
                    "Authorization": self.session_token,
                    "Content-Type":  "application/json",
                })
                self.connected = True
                self._challenge_token = None   # clear challenge state
                return True

            elif resp.status_code == 403:
                err_data = data.get("error", {})
                if err_data.get("code") == "device_challenge_required":
                    # Step 1 complete — save the challenge token from response headers
                    self._challenge_token = resp.headers.get("X-Tastyworks-Challenge-Token")
                    print(f"[Tastytrade] Device challenge required. Token: {self._challenge_token}")
                    # Step 2 — trigger sending the code to the user's email/phone
                    self._trigger_device_challenge()
                    return self.DEVICE_CHALLENGE
                err = err_data.get("message", "Unknown 403 error")
                print(f"[Tastytrade] Login failed: {err}")
                return False

            else:
                err = data.get("error", {}).get("message", "Unknown error")
                print(f"[Tastytrade] Login failed ({resp.status_code}): {err}")
                return False

        except Exception as e:
            print(f"[Tastytrade] Login error: {e}")
            return False

    def _trigger_device_challenge(self):
        """
        POST /device-challenge with the challenge token to trigger
        Tastytrade to send the verification code via email/SMS.
        """
        if not getattr(self, "_challenge_token", None):
            print("[Tastytrade] No challenge token — cannot trigger device challenge.")
            return
        try:
            url  = f"{self.base_url}/device-challenge"
            hdrs = {"X-Tastyworks-Challenge-Token": self._challenge_token}
            resp = self._session.post(url, headers=hdrs, timeout=15)
            print(f"[Tastytrade] Device challenge triggered: "
                  f"{resp.status_code} {resp.text[:120]}")
        except Exception as e:
            print(f"[Tastytrade] Device challenge trigger error: {e}")

    def complete_device_challenge(self, otp: str) -> bool:
        """
        Step 3 of the device challenge flow.
        Call this after the user has received and entered their verification code.
        Returns True on success, False on failure.
        """
        result = self.login(otp=otp)
        return result is True

    def logout(self):
        """Delete the session token (good practice)."""
        if self.session_token:
            try:
                self._session.delete(f"{self.base_url}/sessions")
            except Exception:
                pass
        self.connected      = False
        self.session_token  = None

    # ── Account ──────────────────────────────────────────────────────────────

    def get_accounts(self) -> list:
        """
        Returns list of account dicts:
          [{"account-number": "5WX12345", "account-type-name": "Individual", ...}, ...]
        """
        if not self.connected:
            return []
        try:
            resp = self._session.get(f"{self.base_url}/customers/me/accounts", timeout=10)
            items = resp.json().get("data", {}).get("items", [])
            return [item.get("account", item) for item in items]
        except Exception as e:
            print(f"[Tastytrade] get_accounts error: {e}")
            return []

    def set_account(self, account_number: str):
        """Set the active trading account."""
        self.account_number = account_number

    def get_balance(self) -> dict:
        """
        Returns account balance info:
          {total_value, cash_available, buying_power, net_liquidating_value}
        """
        if not self.connected or not self.account_number:
            return {}
        try:
            url  = f"{self.base_url}/accounts/{self.account_number}/balances"
            resp = self._session.get(url, timeout=10)
            d    = resp.json().get("data", {})
            return {
                "total_value":           float(d.get("net-liquidating-value", 0)),
                "cash_available":        float(d.get("cash-available-to-withdraw", 0)),
                "buying_power":          float(d.get("derivative-buying-power", 0)),
                "equity_buying_power":   float(d.get("equity-buying-power", 0)),
                "net_liquidating_value": float(d.get("net-liquidating-value", 0)),
                "day_trading_buying_power": float(d.get("day-trading-buying-power", 0)),
            }
        except Exception as e:
            print(f"[Tastytrade] get_balance error: {e}")
            return {}

    def get_positions(self) -> list:
        """
        Returns list of open positions (options and equities).
        Each dict includes: symbol, type, quantity, cost_basis,
          current_value, total_gain, total_gain_pct
        """
        if not self.connected or not self.account_number:
            return []
        try:
            url  = f"{self.base_url}/accounts/{self.account_number}/positions"
            resp = self._session.get(url, timeout=10)
            items = resp.json().get("data", {}).get("items", [])

            positions = []
            for p in items:
                qty         = float(p.get("quantity", 0))
                cost        = float(p.get("average-open-price", 0))
                mkt_val     = float(p.get("close-price", cost)) * qty * (
                    100 if p.get("instrument-type") == "Equity Option" else 1
                )
                cost_basis  = cost * qty * (
                    100 if p.get("instrument-type") == "Equity Option" else 1
                )
                gain        = mkt_val - cost_basis
                gain_pct    = (gain / cost_basis * 100) if cost_basis else 0

                positions.append({
                    "symbol":         p.get("symbol", ""),
                    "type":           p.get("instrument-type", ""),
                    "quantity":       qty,
                    "cost_basis":     cost_basis,
                    "current_value":  mkt_val,
                    "last_price":     float(p.get("close-price", 0)),
                    "day_gain":       0.0,   # would need separate quote call
                    "day_gain_pct":   0.0,
                    "total_gain":     gain,
                    "total_gain_pct": gain_pct,
                })
            return positions
        except Exception as e:
            print(f"[Tastytrade] get_positions error: {e}")
            return []

    # ── Market Data ──────────────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> dict:
        """
        Get a simple equity quote.
        symbol: e.g. "SPY", "SPX"
        """
        if not self.connected:
            return {}
        try:
            url  = f"{self.base_url}/market-data/quotes/{symbol}"
            resp = self._session.get(url, timeout=10)

            # Guard: empty body = market closed or no data available
            if not resp.text or not resp.text.strip():
                return {"symbol": symbol, "market_closed": True}

            # Guard: non-200 status
            if resp.status_code != 200:
                return {"symbol": symbol, "market_closed": True}

            d    = resp.json().get("data", {})
            return {
                "symbol":     symbol,
                "last_price": float(d.get("last", 0)),
                "bid":        float(d.get("bid", 0)),
                "ask":        float(d.get("ask", 0)),
                "volume":     int(d.get("volume", 0)),
                "change":     float(d.get("change", 0)),
                "change_pct": float(d.get("change-pct", 0)),
                "day_high":   float(d.get("high", 0)),
                "day_low":    float(d.get("low", 0)),
            }
        except Exception as e:
            # Only log unexpected errors, not routine "market closed" empty responses
            if "Expecting value" not in str(e):
                print(f"[Tastytrade] get_quote error: {e}")
            return {"symbol": symbol, "market_closed": True}

    def get_option_chain(self, underlying: str, expiration: str = None) -> list:
        """
        Fetch option chain for an underlying (e.g., "SPY", "SPX").
        expiration: "YYYY-MM-DD" or None (returns all expirations)
        Returns list of option dicts.
        """
        if not self.connected:
            return []
        try:
            params = {"underlying-symbol": underlying}
            if expiration:
                params["expiration-date"] = expiration
            url  = f"{self.base_url}/option-chains/{underlying}/nested"
            resp = self._session.get(url, params=params, timeout=15)
            data = resp.json().get("data", {})
            return data.get("items", [])
        except Exception as e:
            print(f"[Tastytrade] get_option_chain error: {e}")
            return []

    # ── Orders ───────────────────────────────────────────────────────────────

    def _build_option_order(
        self,
        underlying: str,
        option_type: str,
        strike: float,
        expiration_date: str,
        action: str,
        contracts: int,
        order_type: str = "Limit",
        limit_price: float = None,
    ) -> dict:
        """
        Build the Tastytrade order body for a single-leg options order.

        underlying:      "SPY", "XSP", "SPX"
        option_type:     "C" (call) or "P" (put)
        strike:          e.g. 565.0
        expiration_date: "YYYY-MM-DD"
        action:          "Buy to Open" | "Sell to Close" | "Buy to Close" | "Sell to Open"
        contracts:       number of contracts
        order_type:      "Limit" | "Market"
        limit_price:     per-share premium (e.g. 1.25 means $125/contract)
        """
        # Build OCC-style option symbol: SPY   250308C00565000
        exp_str = expiration_date.replace("-", "")[2:]  # YYMMDD
        strike_int = int(strike * 1000)                 # strikes in thousandths
        occ_symbol = f"{underlying:<6}{exp_str}{option_type.upper()}{strike_int:08d}"
        occ_symbol = occ_symbol.replace(" ", " ")       # keep spaces for 6-char root

        legs = [{
            "instrument-type":  "Equity Option",
            "symbol":           occ_symbol,
            "quantity":         contracts,
            "action":           action,
        }]

        order = {
            "order-type":        order_type,
            "time-in-force":     "Day",
            "legs":              legs,
        }

        if order_type == "Limit" and limit_price is not None:
            # Tastytrade expects price as a positive number regardless of buy/sell
            order["price"]           = round(float(limit_price), 2)
            order["price-effect"]    = "Debit" if "Buy" in action else "Credit"

        return order

    def preview_options_order(
        self,
        underlying: str,
        option_type: str,
        strike: float,
        expiration_date: str,
        action: str,
        contracts: int,
        order_type: str = "Limit",
        limit_price: float = None,
    ) -> dict:
        """
        Dry-run an options order. Returns Tastytrade's fee/margin estimate.
        Does NOT submit the order.
        """
        if not self.connected or not self.account_number:
            return {"error": "Not connected or no account selected"}

        order_body = self._build_option_order(
            underlying, option_type, strike, expiration_date,
            action, contracts, order_type, limit_price,
        )
        url = f"{self.base_url}/accounts/{self.account_number}/orders/dry-run"
        try:
            resp = self._session.post(url, json=order_body, timeout=15)
            data = resp.json()
            if resp.status_code in (200, 201):
                return {
                    "status":    "PREVIEW",
                    "order":     order_body,
                    "response":  data.get("data", {}),
                }
            else:
                err = data.get("error", {})
                return {
                    "error":    err.get("message", str(data)),
                    "order":    order_body,
                }
        except Exception as e:
            return {"error": str(e), "order": order_body}

    def place_options_order(
        self,
        underlying: str,
        option_type: str,
        strike: float,
        expiration_date: str,
        action: str,
        contracts: int,
        order_type: str = "Limit",
        limit_price: float = None,
    ) -> dict:
        """
        Submit a live options order.

        Always do preview_options_order() first and confirm with the user!

        Returns dict with status, order_id, and full response.
        """
        if not self.connected or not self.account_number:
            return {"error": "Not connected or no account selected"}

        order_body = self._build_option_order(
            underlying, option_type, strike, expiration_date,
            action, contracts, order_type, limit_price,
        )
        url = f"{self.base_url}/accounts/{self.account_number}/orders"
        try:
            resp = self._session.post(url, json=order_body, timeout=15)
            data = resp.json()
            if resp.status_code in (200, 201):
                order_data = data.get("data", {}).get("order", {})
                return {
                    "status":   "PLACED",
                    "order_id": order_data.get("id"),
                    "order":    order_body,
                    "response": data.get("data", {}),
                }
            else:
                err = data.get("error", {})
                return {
                    "error":  err.get("message", str(data)),
                    "order":  order_body,
                }
        except Exception as e:
            return {"error": str(e), "order": order_body}

    def place_equity_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str = "Market",
        limit_price: float = None,
    ) -> dict:
        """
        Place an equity (stock/ETF) order.
        action: "Buy to Open" | "Sell to Close"
        """
        if not self.connected or not self.account_number:
            return {"error": "Not connected or no account selected"}

        legs = [{
            "instrument-type": "Equity",
            "symbol":          symbol,
            "quantity":        quantity,
            "action":          action,
        }]
        order_body = {
            "order-type":    order_type,
            "time-in-force": "Day",
            "legs":          legs,
        }
        if order_type == "Limit" and limit_price:
            order_body["price"]        = round(float(limit_price), 2)
            order_body["price-effect"] = "Debit" if "Buy" in action else "Credit"

        url = f"{self.base_url}/accounts/{self.account_number}/orders"
        try:
            resp = self._session.post(url, json=order_body, timeout=15)
            data = resp.json()
            if resp.status_code in (200, 201):
                order_data = data.get("data", {}).get("order", {})
                return {
                    "status":   "PLACED",
                    "order_id": order_data.get("id"),
                    "order":    order_body,
                    "response": data.get("data", {}),
                }
            else:
                return {"error": data.get("error", {}).get("message", str(data)), "order": order_body}
        except Exception as e:
            return {"error": str(e), "order": order_body}

    # ── Futures ──────────────────────────────────────────────────────────────

    # Contract specs: point value in USD per 1-point move
    FUTURES_SPECS = {
        "/MNQ": {"point_value": 2,    "tick": 0.25,  "name": "Micro Nasdaq-100"},
        "/MES": {"point_value": 5,    "tick": 0.25,  "name": "Micro S&P 500"},
        "/NQ":  {"point_value": 20,   "tick": 0.25,  "name": "Nasdaq-100"},
        "/ES":  {"point_value": 50,   "tick": 0.25,  "name": "S&P 500"},
        "/GC":  {"point_value": 100,  "tick": 0.10,  "name": "Gold"},
        "/MGC": {"point_value": 10,   "tick": 0.10,  "name": "Micro Gold"},
        "/CL":  {"point_value": 1000, "tick": 0.01,  "name": "Crude Oil"},
        "/MCL": {"point_value": 100,  "tick": 0.01,  "name": "Micro Crude Oil"},
        "/SI":  {"point_value": 5000, "tick": 0.005, "name": "Silver"},
        "/RTY": {"point_value": 50,   "tick": 0.10,  "name": "Russell 2000"},
        "/M2K": {"point_value": 5,    "tick": 0.10,  "name": "Micro Russell 2000"},
    }

    def get_futures_contracts(self, product_code: str) -> list:
        """
        Fetch active futures contracts for a root symbol.
        product_code: "/NQ", "/ES", "/MNQ", "/GC", "/CL" etc.
        Returns list of contract dicts with symbol, expiration, is-front-month.
        """
        try:
            url    = f"{self.base_url}/instruments/futures"
            params = {"product-codes[]": product_code}
            resp   = self._session.get(url, params=params, timeout=10)
            data   = resp.json()
            items  = data.get("data", {}).get("items", [])
            # Sort by expiration, return active (non-expired) contracts
            active = [c for c in items if not c.get("expired", True)]
            active.sort(key=lambda c: c.get("expiration-date", ""))
            return active
        except Exception as e:
            print(f"[Tastytrade] get_futures_contracts error: {e}")
            return []

    def get_front_month_contract(self, product_code: str) -> str | None:
        """
        Returns the front-month futures symbol for a product code.
        e.g. "/NQ" → "/NQM6"
        """
        contracts = self.get_futures_contracts(product_code)
        if not contracts:
            return None
        # Prefer the one explicitly marked as front month
        for c in contracts:
            if c.get("is-front-month"):
                return c.get("symbol")
        # Otherwise return the nearest expiration
        return contracts[0].get("symbol") if contracts else None

    def place_futures_order(
        self,
        symbol: str,
        action: str,
        quantity: int = 1,
        order_type: str = "Limit",
        limit_price: float = None,
    ) -> dict:
        """
        Place an outright futures order.

        symbol:     Full contract symbol e.g. "/NQM6" or "/MNQM6"
        action:     "Buy to Open" | "Sell to Open" | "Buy to Close" | "Sell to Close"
        quantity:   Number of contracts
        order_type: "Limit" | "Market"
        limit_price: Price per contract (the futures price, e.g. 19500.25)
        """
        if not self.connected or not self.account_number:
            return {"error": "Not connected or no account selected"}

        legs = [{
            "instrument-type": "Future",
            "symbol":          symbol,
            "quantity":        quantity,
            "action":          action,
        }]
        order_body = {
            "order-type":    order_type,
            "time-in-force": "Day",
            "legs":          legs,
        }
        if order_type == "Limit" and limit_price is not None:
            order_body["price"]        = round(float(limit_price), 2)
            order_body["price-effect"] = "Debit" if "Buy" in action else "Credit"

        url = f"{self.base_url}/accounts/{self.account_number}/orders"
        try:
            resp = self._session.post(url, json=order_body, timeout=15)
            data = resp.json()
            if resp.status_code in (200, 201):
                order_data = data.get("data", {}).get("order", {})
                return {
                    "status":   "PLACED",
                    "order_id": order_data.get("id"),
                    "order":    order_body,
                    "response": data.get("data", {}),
                }
            else:
                err = data.get("error", {})
                return {"error": err.get("message", str(data)), "order": order_body}
        except Exception as e:
            return {"error": str(e), "order": order_body}

    def preview_futures_order(
        self,
        symbol: str,
        action: str,
        quantity: int = 1,
        order_type: str = "Limit",
        limit_price: float = None,
    ) -> dict:
        """Dry-run a futures order — returns fee/margin estimate without placing."""
        if not self.connected or not self.account_number:
            return {"error": "Not connected or no account selected"}

        legs = [{
            "instrument-type": "Future",
            "symbol":          symbol,
            "quantity":        quantity,
            "action":          action,
        }]
        order_body = {
            "order-type":    order_type,
            "time-in-force": "Day",
            "legs":          legs,
        }
        if order_type == "Limit" and limit_price is not None:
            order_body["price"]        = round(float(limit_price), 2)
            order_body["price-effect"] = "Debit" if "Buy" in action else "Credit"

        url = f"{self.base_url}/accounts/{self.account_number}/orders/dry-run"
        try:
            resp = self._session.post(url, json=order_body, timeout=15)
            data = resp.json()
            if resp.status_code in (200, 201):
                return {"status": "PREVIEW", "order": order_body, "response": data.get("data", {})}
            else:
                err = data.get("error", {})
                return {"error": err.get("message", str(data)), "order": order_body}
        except Exception as e:
            return {"error": str(e), "order": order_body}

    def place_futures_option_order(
        self,
        underlying_symbol: str,
        expiration_date: str,
        option_type: str,
        strike: float,
        action: str,
        quantity: int = 1,
        order_type: str = "Limit",
        limit_price: float = None,
    ) -> dict:
        """
        Place a futures OPTIONS order (options ON a futures contract).

        underlying_symbol: Root futures symbol e.g. "/NQ", "/MNQ"
        expiration_date:   "YYYY-MM-DD"
        option_type:       "C" or "P"
        strike:            Strike price e.g. 19500.0
        action:            "Buy to Open" | "Sell to Close"
        """
        if not self.connected or not self.account_number:
            return {"error": "Not connected or no account selected"}

        # Tastytrade futures option symbol format: ./NQM6 NQ2J 250418C19500
        # We'll let the API validate the symbol — build the streamer symbol
        # Format: ./[contract_sym] [root][month][day] [YYMMDD][C/P][strike*1000]
        exp_dt     = datetime.strptime(expiration_date, "%Y-%m-%d")
        exp_str    = exp_dt.strftime("%y%m%d")
        strike_int = int(strike * 1000)
        root       = underlying_symbol.lstrip("/")

        # Get front month contract symbol
        front = self.get_front_month_contract(underlying_symbol)
        if not front:
            return {"error": f"Could not find active contract for {underlying_symbol}"}

        # Futures option OCC symbol: ./NQM6 NQ 250418C19500000
        occ = f".{front} {root} {exp_str}{option_type.upper()}{strike_int:08d}"

        legs = [{
            "instrument-type": "Future Option",
            "symbol":          occ,
            "quantity":        quantity,
            "action":          action,
        }]
        order_body = {
            "order-type":    order_type,
            "time-in-force": "Day",
            "legs":          legs,
        }
        if order_type == "Limit" and limit_price is not None:
            order_body["price"]        = round(float(limit_price), 2)
            order_body["price-effect"] = "Debit" if "Buy" in action else "Credit"

        url = f"{self.base_url}/accounts/{self.account_number}/orders"
        try:
            resp = self._session.post(url, json=order_body, timeout=15)
            data = resp.json()
            if resp.status_code in (200, 201):
                order_data = data.get("data", {}).get("order", {})
                return {
                    "status":   "PLACED",
                    "order_id": order_data.get("id"),
                    "order":    order_body,
                    "response": data.get("data", {}),
                }
            else:
                err = data.get("error", {})
                return {"error": err.get("message", str(data)), "order": order_body}
        except Exception as e:
            return {"error": str(e), "order": order_body}

    def get_futures_positions(self) -> list:
        """Return open futures positions (both outright and futures options)."""
        if not self.connected or not self.account_number:
            return []
        try:
            url  = f"{self.base_url}/accounts/{self.account_number}/positions"
            resp = self._session.get(url, timeout=10)
            items = resp.json().get("data", {}).get("items", [])
            return [p for p in items
                    if p.get("instrument-type") in ("Future", "Future Option")]
        except Exception as e:
            print(f"[Tastytrade] get_futures_positions error: {e}")
            return []

    def get_orders(self, status: str = "Live") -> list:
        """
        Fetch open or recent orders.
        status: "Live" | "Filled" | "Cancelled" | "Expired"
        """
        if not self.connected or not self.account_number:
            return []
        try:
            url    = f"{self.base_url}/accounts/{self.account_number}/orders"
            params = {"status": status}
            resp   = self._session.get(url, params=params, timeout=10)
            items  = resp.json().get("data", {}).get("items", [])
            return items
        except Exception as e:
            print(f"[Tastytrade] get_orders error: {e}")
            return []

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a live order by ID."""
        if not self.connected or not self.account_number:
            return {"error": "Not connected"}
        try:
            url  = f"{self.base_url}/accounts/{self.account_number}/orders/{order_id}"
            resp = self._session.delete(url, timeout=10)
            if resp.status_code == 200:
                return {"status": "CANCELLED", "order_id": order_id}
            else:
                return {"error": resp.json().get("error", {}).get("message", "Unknown")}
        except Exception as e:
            return {"error": str(e)}


# ── Helper / Formatting functions ────────────────────────────────────────────

def today_expiration() -> str:
    """Return today's date as 'YYYY-MM-DD' for 0DTE orders."""
    return date.today().isoformat()


def calculate_position_size(
    account_value: float,
    risk_pct: float,
    contract_premium: float,
    target_risk: float = None,
) -> dict:
    """
    Calculate how many contracts to buy for a given risk %.

    account_value:    total account value in $
    risk_pct:         max % of account to risk, e.g. 0.10 for 10%
    contract_premium: per-contract cost in $, e.g. 45.00
    target_risk:      override: exact $ amount to risk (ignores risk_pct)

    Returns:
        {
            "max_risk_dollars":  float,   # $ at risk
            "contracts":         int,     # number of contracts
            "total_cost":        float,   # total dollars spent
            "breakeven_move":    float,   # premium per share (pct move needed)
        }
    """
    if target_risk:
        max_risk = target_risk
    else:
        max_risk = account_value * risk_pct

    contracts = max(1, int(max_risk / contract_premium))
    total_cost = contracts * contract_premium

    return {
        "max_risk_dollars": max_risk,
        "contracts":        contracts,
        "total_cost":       total_cost,
    }


def format_positions(positions: list) -> str:
    """Format positions into a readable string."""
    if not positions:
        return "No open positions."

    lines = ["=== YOUR POSITIONS ===", ""]
    total_value = 0
    total_gain  = 0

    for p in positions:
        gain_emoji = "🟢" if p["total_gain"] >= 0 else "🔴"
        lines.append(f"  {p['symbol']}")
        lines.append(f"    Qty: {p['quantity']} @ ${p['last_price']:.2f}")
        lines.append(f"    Value: ${p['current_value']:.2f}")
        lines.append(f"    P&L: {gain_emoji} ${p['total_gain']:.2f} ({p['total_gain_pct']:.1f}%)")
        lines.append("")
        total_value += p["current_value"]
        total_gain  += p["total_gain"]

    lines.append(f"  Total Portfolio Value: ${total_value:.2f}")
    gain_emoji = "🟢" if total_gain >= 0 else "🔴"
    lines.append(f"  Total P&L: {gain_emoji} ${total_gain:.2f}")
    lines.append("=" * 30)
    return "\n".join(lines)


def format_balance(balance: dict) -> str:
    """Format balance into a readable string."""
    if not balance:
        return "Balance unavailable."

    lines = [
        "=== ACCOUNT BALANCE ===",
        "",
        f"  Net Liq Value:    ${balance.get('net_liquidating_value', 0):,.2f}",
        f"  Cash Available:   ${balance.get('cash_available', 0):,.2f}",
        f"  Options BP:       ${balance.get('buying_power', 0):,.2f}",
        f"  Equity BP:        ${balance.get('equity_buying_power', 0):,.2f}",
        "=" * 30,
    ]
    return "\n".join(lines)
