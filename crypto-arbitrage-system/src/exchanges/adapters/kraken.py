"""
Kraken exchange adapter implementation.

Official API docs: https://docs.kraken.com/rest/
WebSocket docs: https://docs.kraken.com/websockets/
"""
import asyncio
import base64
import hashlib
import hmac
import time
import urllib.parse
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import aiohttp

from src.core.logger import get_logger
from src.exchanges.base import BaseExchange
from src.exchanges.exceptions import (
    APIError,
    AuthenticationError,
    ExchangeUnavailableError,
    InsufficientFundsError,
    InvalidOrderError,
    InvalidSymbolError,
    NetworkError,
    OrderNotFoundError,
    RateLimitExceeded,
    map_exchange_error,
)
from src.exchanges.models import Balance, Order, OrderBook, Ticker, Trade
from src.exchanges.rate_limiter import RateLimiter
from src.exchanges.websocket_manager import WebSocketManager

logger = get_logger(__name__, component="kraken")


class KrakenExchange(BaseExchange):
    """
    Kraken exchange adapter.

    Implements full REST API and WebSocket integration for Kraken.
    Handles Kraken-specific symbol formats, authentication, and error codes.
    """

    # Kraken symbol mappings (Kraken format -> Normalized format)
    SYMBOL_MAP = {
        "XXBTZUSD": "BTC/USD",
        "XETHZUSD": "ETH/USD",
        "XXBTZEUR": "BTC/EUR",
        "XETHZEUR": "ETH/EUR",
        "XXBTZGBP": "BTC/GBP",
        "XETHZGBP": "ETH/GBP",
        "XXBTZJPY": "BTC/JPY",
        "XETHZJPY": "ETH/JPY",
        "XLTCZUSD": "LTC/USD",
        "XXRPZUSD": "XRP/USD",
        "XZECZUSD": "ZEC/USD",
        "USDCUSD": "USDC/USD",
        "USDTZUSD": "USDT/USD",
    }

    # Reverse mapping
    REVERSE_SYMBOL_MAP = {v: k for k, v in SYMBOL_MAP.items()}

    def __init__(
        self,
        config: Dict[str, Any],
        rate_limiter: RateLimiter,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        """Initialize Kraken adapter."""
        super().__init__(config, rate_limiter, api_key, api_secret)

        # Kraken API version
        self.api_version = "0"

        # WebSocket manager
        if self.ws_url:
            self._ws_manager = WebSocketManager(
                url=self.ws_url,
                name=self.name,
                on_message=self._handle_ws_message,
            )

    # ==================== Connection Management ====================

    async def connect(self) -> None:
        """Establish connection to Kraken."""
        try:
            await self._create_session()

            # Test connection with server time endpoint
            await self._make_request("GET", "/public/Time")

            self._is_connected = True
            logger.info("kraken_connected", exchange=self.name)

            # Connect WebSocket if available
            if self._ws_manager:
                await self._ws_manager.connect()

        except Exception as e:
            logger.error("kraken_connection_failed", error=str(e))
            raise ExchangeUnavailableError(
                f"Failed to connect to Kraken: {e}", exchange=self.name
            )

    async def disconnect(self) -> None:
        """Close all connections to Kraken."""
        self._is_connected = False

        # Disconnect WebSocket
        if self._ws_manager:
            await self._ws_manager.disconnect()

        # Close HTTP session
        await self._close_session()

        logger.info("kraken_disconnected", exchange=self.name)

    async def health_check(self) -> bool:
        """Check if Kraken is reachable."""
        try:
            result = await self._make_request("GET", "/public/SystemStatus")
            status = result.get("status", "offline")
            return status == "online"
        except Exception as e:
            logger.warning("kraken_health_check_failed", error=str(e))
            return False

    # ==================== Market Data (Public API) ====================

    async def fetch_ticker(self, symbol: str) -> Ticker:
        """Fetch current ticker for a symbol."""
        kraken_symbol = self.denormalize_symbol(symbol)

        try:
            async with self.rate_limiter:
                result = await self._make_request(
                    "GET", "/public/Ticker", params={"pair": kraken_symbol}
                )

            # Kraken returns data keyed by symbol
            ticker_data = result.get(kraken_symbol)
            if not ticker_data:
                raise InvalidSymbolError(
                    f"No ticker data for {symbol}", exchange=self.name, symbol=symbol
                )

            # Parse Kraken ticker format
            # a = ask [price, whole lot volume, lot volume]
            # b = bid [price, whole lot volume, lot volume]
            # c = last trade [price, lot volume]
            # v = volume [today, last 24 hours]
            # p = volume weighted average price [today, last 24 hours]
            # t = number of trades [today, last 24 hours]
            # l = low [today, last 24 hours]
            # h = high [today, last 24 hours]
            # o = today's opening price

            return Ticker(
                exchange=self.name,
                symbol=symbol,
                bid=Decimal(ticker_data["b"][0]),
                ask=Decimal(ticker_data["a"][0]),
                last=Decimal(ticker_data["c"][0]),
                volume_24h=Decimal(ticker_data["v"][1]),
                high_24h=Decimal(ticker_data["h"][1]),
                low_24h=Decimal(ticker_data["l"][1]),
                timestamp=datetime.utcnow(),
            )

        except InvalidSymbolError:
            raise
        except Exception as e:
            logger.error("kraken_fetch_ticker_failed", symbol=symbol, error=str(e))
            raise APIError(
                f"Failed to fetch ticker: {e}", exchange=self.name, details={"symbol": symbol}
            )

    async def fetch_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        """Fetch current order book."""
        kraken_symbol = self.denormalize_symbol(symbol)

        try:
            async with self.rate_limiter:
                result = await self._make_request(
                    "GET", "/public/Depth", params={"pair": kraken_symbol, "count": depth}
                )

            order_book_data = result.get(kraken_symbol)
            if not order_book_data:
                raise InvalidSymbolError(
                    f"No order book data for {symbol}", exchange=self.name, symbol=symbol
                )

            # Parse bids and asks
            # Format: [price, volume, timestamp]
            bids = [
                (Decimal(str(bid[0])), Decimal(str(bid[1])))
                for bid in order_book_data.get("bids", [])
            ]
            asks = [
                (Decimal(str(ask[0])), Decimal(str(ask[1])))
                for ask in order_book_data.get("asks", [])
            ]

            return OrderBook(
                exchange=self.name,
                symbol=symbol,
                bids=bids,
                asks=asks,
                timestamp=datetime.utcnow(),
            )

        except InvalidSymbolError:
            raise
        except Exception as e:
            logger.error("kraken_fetch_order_book_failed", symbol=symbol, error=str(e))
            raise APIError(
                f"Failed to fetch order book: {e}",
                exchange=self.name,
                details={"symbol": symbol},
            )

    async def fetch_trades(self, symbol: str, limit: int = 100) -> List[Trade]:
        """Fetch recent trades."""
        kraken_symbol = self.denormalize_symbol(symbol)

        try:
            async with self.rate_limiter:
                result = await self._make_request(
                    "GET", "/public/Trades", params={"pair": kraken_symbol}
                )

            trades_data = result.get(kraken_symbol, [])

            # Parse trades
            # Format: [price, volume, time, buy/sell, market/limit, miscellaneous]
            trades = []
            for trade in trades_data[:limit]:
                trades.append(
                    Trade(
                        trade_id=f"{trade[2]}",  # Using timestamp as ID
                        exchange=self.name,
                        symbol=symbol,
                        side="buy" if trade[3] == "b" else "sell",
                        price=Decimal(str(trade[0])),
                        quantity=Decimal(str(trade[1])),
                        timestamp=datetime.fromtimestamp(float(trade[2])),
                    )
                )

            return trades

        except Exception as e:
            logger.error("kraken_fetch_trades_failed", symbol=symbol, error=str(e))
            raise APIError(
                f"Failed to fetch trades: {e}",
                exchange=self.name,
                details={"symbol": symbol},
            )

    async def fetch_supported_pairs(self) -> List[str]:
        """Fetch all trading pairs supported by Kraken."""
        try:
            async with self.rate_limiter:
                result = await self._make_request("GET", "/public/AssetPairs")

            # Normalize all pairs
            pairs = []
            for kraken_pair in result.keys():
                try:
                    normalized = self.normalize_symbol(kraken_pair)
                    if normalized and "/" in normalized:
                        pairs.append(normalized)
                except Exception:
                    # Skip pairs that can't be normalized
                    continue

            logger.info("kraken_supported_pairs_fetched", count=len(pairs))
            return sorted(pairs)

        except Exception as e:
            logger.error("kraken_fetch_supported_pairs_failed", error=str(e))
            raise APIError(
                f"Failed to fetch supported pairs: {e}", exchange=self.name
            )

    # ==================== Account Management (Private API) ====================

    async def fetch_balances(self) -> List[Balance]:
        """Fetch all account balances."""
        try:
            async with self.rate_limiter:
                result = await self._make_request("POST", "/private/Balance", signed=True)

            balances = []
            for currency, amount in result.items():
                # Normalize currency codes (remove X/Z prefixes)
                normalized_currency = self._normalize_currency(currency)

                balances.append(
                    Balance(
                        exchange=self.name,
                        currency=normalized_currency,
                        total=Decimal(str(amount)),
                        available=Decimal(str(amount)),  # Kraken doesn't separate locked
                        locked=Decimal("0"),
                        timestamp=datetime.utcnow(),
                    )
                )

            return balances

        except Exception as e:
            logger.error("kraken_fetch_balances_failed", error=str(e))
            raise APIError(f"Failed to fetch balances: {e}", exchange=self.name)

    async def fetch_balance(self, currency: str) -> Balance:
        """Fetch balance for specific currency."""
        balances = await self.fetch_balances()

        for balance in balances:
            if balance.currency == currency:
                return balance

        # Return zero balance if not found
        return Balance(
            exchange=self.name,
            currency=currency,
            total=Decimal("0"),
            available=Decimal("0"),
            locked=Decimal("0"),
            timestamp=datetime.utcnow(),
        )

    # ==================== Order Management (Private API) ====================

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        dry_run: bool = True,
    ) -> Order:
        """Create a new order."""
        if dry_run:
            # Return mock order for dry run
            return Order(
                order_id=f"DRYRUN-{int(time.time())}",
                exchange=self.name,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                filled_quantity=Decimal("0"),
                status="pending",
                timestamp=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

        kraken_symbol = self.denormalize_symbol(symbol)

        # Build order parameters
        params = {
            "pair": kraken_symbol,
            "type": side,
            "ordertype": order_type,
            "volume": str(quantity),
        }

        if order_type == "limit" and price:
            params["price"] = str(price)

        try:
            async with self.rate_limiter:
                result = await self._make_request("POST", "/private/AddOrder", params, signed=True)

            # Parse response
            txid = result.get("txid", [None])[0]

            return Order(
                order_id=txid or f"ORDER-{int(time.time())}",
                exchange=self.name,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                filled_quantity=Decimal("0"),
                status="open",
                timestamp=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

        except Exception as e:
            logger.error("kraken_create_order_failed", symbol=symbol, error=str(e))
            raise self._map_order_error(e, symbol)

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an open order."""
        try:
            async with self.rate_limiter:
                await self._make_request(
                    "POST", "/private/CancelOrder", {"txid": order_id}, signed=True
                )

            logger.info("kraken_order_cancelled", order_id=order_id)
            return True

        except Exception as e:
            logger.error("kraken_cancel_order_failed", order_id=order_id, error=str(e))
            return False

    async def fetch_order(self, order_id: str, symbol: str) -> Order:
        """Fetch order status."""
        try:
            async with self.rate_limiter:
                result = await self._make_request(
                    "POST", "/private/QueryOrders", {"txid": order_id}, signed=True
                )

            order_data = result.get(order_id)
            if not order_data:
                raise OrderNotFoundError(
                    f"Order {order_id} not found",
                    exchange=self.name,
                    order_id=order_id,
                )

            return self._parse_kraken_order(order_id, order_data)

        except OrderNotFoundError:
            raise
        except Exception as e:
            logger.error("kraken_fetch_order_failed", order_id=order_id, error=str(e))
            raise APIError(
                f"Failed to fetch order: {e}",
                exchange=self.name,
                details={"order_id": order_id},
            )

    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Fetch all open orders."""
        try:
            async with self.rate_limiter:
                result = await self._make_request("POST", "/private/OpenOrders", signed=True)

            orders = []
            for order_id, order_data in result.get("open", {}).items():
                parsed_order = self._parse_kraken_order(order_id, order_data)

                # Filter by symbol if provided
                if symbol and parsed_order.symbol != symbol:
                    continue

                orders.append(parsed_order)

            return orders

        except Exception as e:
            logger.error("kraken_fetch_open_orders_failed", error=str(e))
            raise APIError(f"Failed to fetch open orders: {e}", exchange=self.name)

    # ==================== WebSocket Real-Time Data ====================

    async def subscribe_order_book(self, symbol: str) -> None:
        """Subscribe to real-time order book updates."""
        if not self._ws_manager:
            raise APIError("WebSocket not configured", exchange=self.name)

        kraken_symbol = self.denormalize_symbol(symbol)

        subscription = {
            "event": "subscribe",
            "pair": [kraken_symbol],
            "subscription": {"name": "book"},
        }

        await self._ws_manager.subscribe("orderbook", symbol, subscription)
        logger.info("kraken_orderbook_subscribed", symbol=symbol)

    async def subscribe_trades(self, symbol: str) -> None:
        """Subscribe to real-time trade updates."""
        if not self._ws_manager:
            raise APIError("WebSocket not configured", exchange=self.name)

        kraken_symbol = self.denormalize_symbol(symbol)

        subscription = {
            "event": "subscribe",
            "pair": [kraken_symbol],
            "subscription": {"name": "trade"},
        }

        await self._ws_manager.subscribe("trades", symbol, subscription)
        logger.info("kraken_trades_subscribed", symbol=symbol)

    async def unsubscribe(self, channel: str, symbol: str) -> None:
        """Unsubscribe from a channel."""
        if not self._ws_manager:
            return

        kraken_symbol = self.denormalize_symbol(symbol)

        subscription = {
            "event": "unsubscribe",
            "pair": [kraken_symbol],
            "subscription": {"name": channel},
        }

        await self._ws_manager.send(subscription)
        await self._ws_manager.unsubscribe(channel, symbol)
        logger.info("kraken_unsubscribed", channel=channel, symbol=symbol)

    # ==================== Utility Methods ====================

    def normalize_symbol(self, symbol: str) -> str:
        """Convert Kraken symbol to standard format."""
        # Check direct mapping first
        if symbol in self.SYMBOL_MAP:
            return self.SYMBOL_MAP[symbol]

        # Try to parse format like "XXBTZUSD"
        # Kraken prefixes: X for crypto, Z for fiat
        symbol_clean = symbol.replace(".", "").replace("_", "")

        # Common patterns
        if symbol_clean.startswith("X") and "Z" in symbol_clean:
            # Crypto/Fiat pair
            parts = symbol_clean.split("Z", 1)
            base = parts[0].replace("X", "", 1)
            quote = parts[1].replace("Z", "")
            return f"{base}/{quote}"

        # Try splitting by common currency codes
        for fiat in ["USD", "EUR", "GBP", "JPY"]:
            if symbol_clean.endswith(fiat):
                base = symbol_clean[: -len(fiat)].replace("X", "")
                return f"{base}/{fiat}"

        # Return as-is if can't normalize
        return symbol

    def denormalize_symbol(self, symbol: str) -> str:
        """Convert standard format to Kraken symbol."""
        # Check reverse mapping
        if symbol in self.REVERSE_SYMBOL_MAP:
            return self.REVERSE_SYMBOL_MAP[symbol]

        # Try to construct Kraken format
        if "/" in symbol:
            base, quote = symbol.split("/")

            # Add prefixes
            kraken_base = f"X{base}" if base not in ["USD", "EUR", "GBP", "JPY"] else base
            kraken_quote = f"Z{quote}" if quote in ["USD", "EUR", "GBP", "JPY"] else quote

            kraken_symbol = f"{kraken_base}{kraken_quote}"

            # Check if it exists in our map
            if kraken_symbol in self.SYMBOL_MAP:
                return kraken_symbol

        # Return as-is if can't denormalize
        return symbol.replace("/", "")

    async def _sign_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, str]:
        """Generate authentication signature for private endpoints."""
        if not self.api_key or not self.api_secret:
            raise AuthenticationError(
                "API key and secret required for private endpoints", exchange=self.name
            )

        # Add nonce
        nonce = str(int(time.time() * 1000))
        params["nonce"] = nonce

        # Encode params
        postdata = urllib.parse.urlencode(params)

        # Create signature
        # SHA256(nonce + postdata)
        message = nonce + postdata
        message_hash = hashlib.sha256(message.encode()).digest()

        # HMAC-SHA512(path + hash, secret)
        path = f"/{self.api_version}{endpoint}"
        hmac_key = base64.b64decode(self.api_secret)
        signature = hmac.new(
            hmac_key, path.encode() + message_hash, hashlib.sha512
        ).digest()
        signature_b64 = base64.b64encode(signature).decode()

        return {
            "API-Key": self.api_key,
            "API-Sign": signature_b64,
        }

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Dict[str, Any]:
        """Make HTTP request with rate limiting, retries, and error handling."""
        if not self._session:
            raise ExchangeUnavailableError("Session not initialized", exchange=self.name)

        params = params or {}
        url = f"{self.api_url}/{self.api_version}{endpoint}"

        # Prepare headers
        headers = {"User-Agent": "CryptoArbitrageSystem/1.0"}

        # Sign request if needed
        if signed:
            signature_headers = await self._sign_request(endpoint, params)
            headers.update(signature_headers)

        # Make request with retries
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if method == "GET":
                    async with self._session.get(url, params=params, headers=headers) as resp:
                        data = await resp.json()
                else:
                    async with self._session.post(url, data=params, headers=headers) as resp:
                        data = await resp.json()

                # Check for Kraken errors
                errors = data.get("error", [])
                if errors:
                    error_msg = ", ".join(errors)
                    raise self._map_kraken_error(error_msg)

                return data.get("result", {})

            except aiohttp.ClientError as e:
                if attempt == max_retries - 1:
                    raise NetworkError(
                        f"Network error: {e}", exchange=self.name, details={"endpoint": endpoint}
                    )
                await asyncio.sleep(2**attempt)  # Exponential backoff

            except Exception as e:
                if attempt == max_retries - 1:
                    raise

                await asyncio.sleep(2**attempt)

        raise NetworkError("Max retries exceeded", exchange=self.name)

    def _normalize_currency(self, currency: str) -> str:
        """Normalize Kraken currency codes."""
        # Remove X/Z prefixes
        if currency.startswith(("X", "Z")) and len(currency) > 3:
            return currency[1:]
        return currency

    def _parse_kraken_order(self, order_id: str, order_data: Dict[str, Any]) -> Order:
        """Parse Kraken order format to normalized Order."""
        descr = order_data.get("descr", {})

        # Normalize symbol
        pair = order_data.get("descr", {}).get("pair", "")
        normalized_symbol = self.normalize_symbol(pair)

        # Parse status
        status_map = {
            "pending": "pending",
            "open": "open",
            "closed": "filled",
            "canceled": "cancelled",
            "expired": "cancelled",
        }
        kraken_status = order_data.get("status", "open")
        status = status_map.get(kraken_status, "open")

        return Order(
            order_id=order_id,
            exchange=self.name,
            symbol=normalized_symbol,
            side=descr.get("type", "buy"),
            order_type=descr.get("ordertype", "limit"),
            quantity=Decimal(str(order_data.get("vol", "0"))),
            price=Decimal(str(descr.get("price", "0"))) if descr.get("price") else None,
            filled_quantity=Decimal(str(order_data.get("vol_exec", "0"))),
            status=status,
            timestamp=datetime.fromtimestamp(float(order_data.get("opentm", time.time()))),
            updated_at=datetime.utcnow(),
            fee=Decimal(str(order_data.get("fee", "0"))),
        )

    def _map_kraken_error(self, error_msg: str) -> Exception:
        """Map Kraken error messages to appropriate exceptions."""
        error_lower = error_msg.lower()

        if "api key" in error_lower or "invalid key" in error_lower:
            return AuthenticationError(error_msg, exchange=self.name)
        elif "rate limit" in error_lower or "eorder:rate limit" in error_lower:
            return RateLimitExceeded(error_msg, exchange=self.name)
        elif "insufficient funds" in error_lower:
            return InsufficientFundsError(error_msg, exchange=self.name)
        elif "unknown asset pair" in error_lower:
            return InvalidSymbolError(error_msg, exchange=self.name)
        elif "unknown order" in error_lower:
            return OrderNotFoundError(error_msg, exchange=self.name)
        else:
            return APIError(error_msg, exchange=self.name)

    def _map_order_error(self, error: Exception, symbol: str) -> Exception:
        """Map order creation errors."""
        error_msg = str(error).lower()

        if "insufficient" in error_msg:
            return InsufficientFundsError(str(error), exchange=self.name)
        elif "invalid" in error_msg:
            return InvalidOrderError(str(error), exchange=self.name, details={"symbol": symbol})
        else:
            return APIError(str(error), exchange=self.name)

    async def _handle_ws_message(self, message: Dict[str, Any]) -> None:
        """Handle incoming WebSocket messages."""
        # Parse and log WebSocket messages
        # This can be extended to update local order book cache, etc.
        event = message.get("event")
        if event:
            logger.debug("kraken_ws_event", event=event, data=message)
