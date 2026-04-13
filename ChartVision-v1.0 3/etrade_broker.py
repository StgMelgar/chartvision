"""
E*TRADE Broker Module
Handles authentication, account data, positions, and order execution via E*TRADE API.
"""

import json
import webbrowser
from datetime import datetime

try:
    import pyetrade
    PYETRADE_AVAILABLE = True
except ImportError:
    PYETRADE_AVAILABLE = False


class ETradeBroker:
    """Manages E*TRADE broker connection and trading operations."""

    def __init__(self, consumer_key: str, consumer_secret: str, sandbox: bool = True):
        if not PYETRADE_AVAILABLE:
            raise RuntimeError("pyetrade not installed. Run: pip3 install pyetrade")

        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.sandbox = sandbox
        self.dev = sandbox  # pyetrade uses 'dev' for sandbox mode

        self.access_token = None
        self.access_token_secret = None
        self.accounts_client = None
        self.orders_client = None
        self.market_client = None

        self.connected = False
        self.account_id = None
        self.account_id_key = None

    def get_auth_url(self) -> str:
        """
        Step 1 of OAuth: Get the authorization URL.
        Returns the URL the user needs to visit to authorize the app.
        """
        self.oauth = pyetrade.ETradeOAuth(self.consumer_key, self.consumer_secret)
        auth_url = self.oauth.get_request_token()
        return auth_url

    def complete_auth(self, verification_code: str) -> bool:
        """
        Step 2 of OAuth: Complete authentication with the verification code.
        Returns True if successful.
        """
        try:
            tokens = self.oauth.get_access_token(verification_code)
            self.access_token = tokens["oauth_token"]
            self.access_token_secret = tokens["oauth_token_secret"]

            # Initialize API clients
            self.accounts_client = pyetrade.ETradeAccounts(
                self.consumer_key,
                self.consumer_secret,
                self.access_token,
                self.access_token_secret,
                dev=self.dev,
            )

            self.orders_client = pyetrade.ETradeOrder(
                self.consumer_key,
                self.consumer_secret,
                self.access_token,
                self.access_token_secret,
                dev=self.dev,
            )

            self.market_client = pyetrade.ETradeMarket(
                self.consumer_key,
                self.consumer_secret,
                self.access_token,
                self.access_token_secret,
                dev=self.dev,
            )

            self.connected = True
            return True

        except Exception as e:
            print(f"Auth error: {e}")
            self.connected = False
            return False

    def get_accounts(self) -> list:
        """Get list of accounts."""
        if not self.connected:
            return []

        try:
            response = self.accounts_client.list_accounts(resp_format="json")
            accounts = response["AccountListResponse"]["Accounts"]["Account"]
            if isinstance(accounts, dict):
                accounts = [accounts]
            return accounts
        except Exception as e:
            print(f"Error getting accounts: {e}")
            return []

    def set_account(self, account_id_key: str, account_id: str = None):
        """Set the active account to use for trading."""
        self.account_id_key = account_id_key
        self.account_id = account_id

    def get_positions(self) -> list:
        """Get current positions for the active account."""
        if not self.connected or not self.account_id_key:
            return []

        try:
            response = self.accounts_client.get_account_portfolio(
                self.account_id_key, resp_format="json"
            )

            positions = []
            portfolio = response.get("PortfolioResponse", {}).get("AccountPortfolio", [])
            if isinstance(portfolio, dict):
                portfolio = [portfolio]

            for acct in portfolio:
                pos_list = acct.get("Position", [])
                if isinstance(pos_list, dict):
                    pos_list = [pos_list]

                for pos in pos_list:
                    product = pos.get("Product", {})
                    quick = pos.get("Quick", {})
                    positions.append({
                        "symbol": product.get("symbol", ""),
                        "type": product.get("securityType", ""),
                        "quantity": pos.get("quantity", 0),
                        "cost_basis": pos.get("totalCost", 0),
                        "current_value": pos.get("marketValue", 0),
                        "day_gain": quick.get("change", 0),
                        "day_gain_pct": quick.get("changePct", 0),
                        "total_gain": quick.get("totalGainOrLoss", 0),
                        "total_gain_pct": quick.get("totalGainOrLossPct", 0),
                        "last_price": quick.get("lastTrade", 0),
                    })

            return positions

        except Exception as e:
            print(f"Error getting positions: {e}")
            return []

    def get_balance(self) -> dict:
        """Get account balance information."""
        if not self.connected or not self.account_id_key:
            return {}

        try:
            response = self.accounts_client.get_account_balance(
                self.account_id_key, resp_format="json"
            )
            balance = response.get("BalanceResponse", {}).get("Computed", {})
            return {
                "total_value": balance.get("RealTimeValues", {}).get("totalAccountValue", 0),
                "cash_available": balance.get("cashAvailableForInvestment", 0),
                "buying_power": balance.get("RealTimeValues", {}).get("totalBuyingPower", 0),
                "day_trading_buying_power": balance.get("dtCashBuyingPower", 0),
                "margin_buying_power": balance.get("marginBuyingPower", 0),
            }
        except Exception as e:
            print(f"Error getting balance: {e}")
            return {}

    def get_quote(self, symbol: str) -> dict:
        """Get real-time quote for a symbol."""
        if not self.connected:
            return {}

        try:
            response = self.market_client.get_quote(
                [symbol], resp_format="json"
            )
            quote_data = response.get("QuoteResponse", {}).get("QuoteData", [])
            if isinstance(quote_data, dict):
                quote_data = [quote_data]

            if quote_data:
                q = quote_data[0].get("All", {})
                return {
                    "symbol": symbol,
                    "last_price": q.get("lastTrade", 0),
                    "bid": q.get("bid", 0),
                    "ask": q.get("ask", 0),
                    "volume": q.get("totalVolume", 0),
                    "day_high": q.get("high", 0),
                    "day_low": q.get("low", 0),
                    "change": q.get("changeClose", 0),
                    "change_pct": q.get("changeClosePercentage", 0),
                }
            return {}
        except Exception as e:
            print(f"Error getting quote: {e}")
            return {}

    def place_order(self, symbol: str, action: str, quantity: int,
                    order_type: str = "MARKET", limit_price: float = None,
                    stop_price: float = None, preview_only: bool = True) -> dict:
        """
        Place or preview an order.

        Args:
            symbol: Stock ticker (e.g., "AAPL")
            action: "BUY" or "SELL"
            quantity: Number of shares
            order_type: "MARKET", "LIMIT", "STOP", "STOP_LIMIT"
            limit_price: Required for LIMIT and STOP_LIMIT orders
            stop_price: Required for STOP and STOP_LIMIT orders
            preview_only: If True, only preview the order (don't execute)

        Returns:
            Order response dict
        """
        if not self.connected or not self.account_id_key:
            return {"error": "Not connected or no account selected"}

        try:
            order_params = {
                "accountIdKey": self.account_id_key,
                "symbol": symbol,
                "orderAction": action.upper(),
                "clientOrderId": f"TV_{datetime.now().strftime('%H%M%S%f')[:10]}",
                "quantity": int(quantity),
                "orderType": "EQ",  # Equity
                "priceType": order_type.upper(),
                "marketSession": "REGULAR",
                "orderTerm": "GOOD_FOR_DAY",
                "resp_format": "json",
            }

            if limit_price and order_type.upper() in ("LIMIT", "STOP_LIMIT"):
                order_params["limitPrice"] = float(limit_price)
            if stop_price and order_type.upper() in ("STOP", "STOP_LIMIT"):
                order_params["stopPrice"] = float(stop_price)

            if preview_only:
                response = self.orders_client.preview_equity_order(**order_params)
                return {
                    "status": "PREVIEW",
                    "order": order_params,
                    "response": response,
                }
            else:
                # First preview, then place
                preview = self.orders_client.preview_equity_order(**order_params)
                preview_ids = preview.get("PreviewOrderResponse", {}).get("PreviewIds", [])
                if preview_ids:
                    order_params["previewId"] = preview_ids[0].get("previewId")
                response = self.orders_client.place_equity_order(**order_params)
                return {
                    "status": "PLACED",
                    "order": order_params,
                    "response": response,
                }

        except Exception as e:
            return {"error": str(e), "order": order_params if 'order_params' in dir() else {}}

    def place_options_order(self, underlying: str, option_type: str, strike: float,
                            expiration_date: str, action: str, contracts: int,
                            order_type: str = "LIMIT", limit_price: float = None,
                            preview_only: bool = True) -> dict:
        """
        Place or preview a 0DTE SPX options order.

        Args:
            underlying:      Underlying symbol, e.g. "SPX"
            option_type:     "CALL" or "PUT"
            strike:          Strike price, e.g. 5650.0
            expiration_date: Expiration as "MMDDYYYY", e.g. "03082026"
            action:          "BUY_OPEN" or "SELL_CLOSE"
            contracts:       Number of contracts (each = 100 shares exposure)
            order_type:      "MARKET" or "LIMIT"
            limit_price:     Option premium limit price (e.g. 3.20 per share = $320/contract)
            preview_only:    If True, only preview (don't execute)

        Returns:
            Order response dict
        """
        if not self.connected or not self.account_id_key:
            return {"error": "Not connected or no account selected"}

        try:
            order_params = {
                "accountIdKey":  self.account_id_key,
                "symbol":        underlying,
                "callPut":       option_type.upper(),       # "CALL" or "PUT"
                "strikePrice":   float(strike),
                "expiryDate":    expiration_date,           # "MMDDYYYY"
                "orderAction":   action.upper(),            # "BUY_OPEN"
                "clientOrderId": f"OPT_{datetime.now().strftime('%H%M%S%f')[:12]}",
                "quantity":      int(contracts),
                "orderType":     "OPTN",                    # Options order
                "priceType":     order_type.upper(),
                "marketSession": "REGULAR",
                "orderTerm":     "GOOD_FOR_DAY",
                "resp_format":   "json",
            }

            if limit_price and order_type.upper() == "LIMIT":
                order_params["limitPrice"] = float(limit_price)

            if preview_only:
                response = self.orders_client.preview_option_order(**order_params)
                return {
                    "status":   "PREVIEW",
                    "type":     "OPTIONS",
                    "order":    order_params,
                    "response": response,
                }
            else:
                preview = self.orders_client.preview_option_order(**order_params)
                preview_ids = preview.get("PreviewOrderResponse", {}).get("PreviewIds", [])
                if preview_ids:
                    order_params["previewId"] = preview_ids[0].get("previewId")
                response = self.orders_client.place_option_order(**order_params)
                return {
                    "status":   "PLACED",
                    "type":     "OPTIONS",
                    "order":    order_params,
                    "response": response,
                }

        except Exception as e:
            return {"error": str(e), "order": order_params if 'order_params' in locals() else {}}

    def get_orders(self) -> list:
        """Get open/recent orders."""
        if not self.connected or not self.account_id_key:
            return []

        try:
            response = self.orders_client.list_orders(
                self.account_id_key, resp_format="json"
            )
            orders = response.get("OrdersResponse", {}).get("Order", [])
            if isinstance(orders, dict):
                orders = [orders]
            return orders
        except Exception as e:
            print(f"Error getting orders: {e}")
            return []


def format_positions(positions: list) -> str:
    """Format positions into a readable string."""
    if not positions:
        return "No open positions."

    lines = ["=== YOUR POSITIONS ===", ""]
    total_value = 0
    total_gain = 0

    for p in positions:
        gain_emoji = "🟢" if p["total_gain"] >= 0 else "🔴"
        lines.append(f"  {p['symbol']}")
        lines.append(f"    Shares: {p['quantity']} @ ${p['last_price']:.2f}")
        lines.append(f"    Value: ${p['current_value']:.2f}")
        lines.append(f"    P&L: {gain_emoji} ${p['total_gain']:.2f} ({p['total_gain_pct']:.1f}%)")
        lines.append(f"    Today: ${p['day_gain']:.2f} ({p['day_gain_pct']:.1f}%)")
        lines.append("")

        total_value += p["current_value"]
        total_gain += p["total_gain"]

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
        f"  Total Value:      ${balance.get('total_value', 0):.2f}",
        f"  Cash Available:   ${balance.get('cash_available', 0):.2f}",
        f"  Buying Power:     ${balance.get('buying_power', 0):.2f}",
        f"  DT Buying Power:  ${balance.get('day_trading_buying_power', 0):.2f}",
        "=" * 30,
    ]
    return "\n".join(lines)
