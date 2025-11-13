"""
Coinbase Advanced exchange adapter implementation.

Official API docs: https://docs.cloud.coinbase.com/advanced-trade-api/docs/welcome
WebSocket docs: https://docs.cloud.coinbase.com/advanced-trade-api/docs/ws-overview

Key differences from Kraken:
- Uses JWT (ES256) authentication instead of HMAC-SHA512
- Symbol format: BTC-USD (not BTC/USD)
- Different API endpoints and response structure
- Stricter rate limits (10 req/s vs Kraken's 15 req/s)
"""
import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import aiohttp
import jwt
from tenacity import retry, stop_after_attempt, wait_exponential

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
)
from src.exchanges.models import Balance, Order, OrderBook, Ticker, Trade
from src.exchanges.rate_limiter import RateLimiter
from src.exchanges.websocket_manager import WebSocketManager

logger = get_logger(__name__, component="coinbase")


class CoinbaseAdvancedExchange(BaseExchange):
    """
    Coinbase Advanced exchange adapter.

    Implements full REST API and WebSocket integration for Coinbase Advanced Trade.
    Handles Coinbase-specific JWT authentication, symbol formats, and error codes.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        rate_limiter: RateLimiter,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        """Initialize Coinbase Advanced adapter."""
        super().__init__(config, rate_limiter, api_key, api_secret)

        # WebSocket manager
        if self.ws_url:
            self._ws_manager = WebSocketManager(
                url=self.ws_url,
                name=self.name,
            )

    # ==================== Connection Management ====================

    async def connect(self) -> None:
        """Establish connection to Coinbase Advanced."""
        try:
            await self._create_session()

            # Test connection with server time endpoint
            await self._make_request("GET", "/api/v3/brokerage/time")

            self._is_connected = True
            logger.info("coinbase_connected", exchange=self.name)

            # Connect WebSocket if available
            if self._ws_manager:
                await self._ws_manager.connect()

        except Exception as e:
            logger.error("coinbase_connection_failed", error=str(e))
            raise ExchangeUnavailableError(
                f"Failed to connect to Coinbase Advanced: {e}", exchange=self.name
            )

    async def disconnect(self) -> None:
        """Close all connections to Coinbase Advanced."""
        self._is_connected = False

        # Disconnect WebSocket
        if self._ws_manager:
            await self._ws_manager.disconnect()

        # Close HTTP session
        await self._close_session()

        logger.info("coinbase_disconnected", exchange=self.name)

    async def health_check(self) -> bool:
        """Check if Coinbase Advanced is reachable."""
        try:
            result = await self._make_request("GET", "/api/v3/brokerage/time")
            return "iso" in result
        except Exception as e:
            logger.warning("coinbase_health_check_failed", error=str(e))
            return False

    # ==================== Market Data (Public API) ====================

    async def fetch_ticker(self, symbol: str) -> Ticker:
        """Fetch current ticker for a symbol."""
        coinbase_symbol = self.denormalize_symbol(symbol)

        try:
            async with self.rate_limiter:
                result = await self._make_request(
                    "GET", f"/api/v3/brokerage/products/{coinbase_symbol}/ticker"
                )

            # Parse Coinbase ticker format
            trades = result.get("trades", [])
            if not trades:
                raise InvalidSymbolError(
                    f"No ticker data for {symbol}", exchange=self.name, symbol=symbol
                )

            latest_trade = trades[0]

            return Ticker(
                exchange=self.name,
                symbol=symbol,
                bid=Decimal(result.get("best_bid", "0")),
                ask=Decimal(result.get("best_ask", "0")),
                last=Decimal(latest_trade.get("price", "0")),
                volume_24h=Decimal(latest_trade.get("size", "0")),
                timestamp=datetime.utcnow(),
            )

        except InvalidSymbolError:
            raise
        except Exception as e:
            logger.error("coinbase_fetch_ticker_failed", symbol=symbol, error=str(e))
            raise APIError(
                f"Failed to fetch ticker: {e}", exchange=self.name, details={"symbol": symbol}
            )

    async def fetch_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        """Fetch current order book."""
        coinbase_symbol = self.denormalize_symbol(symbol)

        try:
            async with self.rate_limiter:
                result = await self._make_request(
                    "GET",
                    f"/api/v3/brokerage/products/{coinbase_symbol}/book",
                    params={"limit": depth},
                )

            pricebook = result.get("pricebook", {})

            # Parse bids and asks
            bids = [
                (Decimal(str(bid["price"])), Decimal(str(bid["size"])))
                for bid in pricebook.get("bids", [])[:depth]
            ]
            asks = [
                (Decimal(str(ask["price"])), Decimal(str(ask["size"])))
                for ask in pricebook.get("asks", [])[:depth]
            ]

            return OrderBook(
                exchange=self.name,
                symbol=symbol,
                bids=bids,
                asks=asks,
                timestamp=datetime.utcnow(),
            )

        except Exception as e:
            logger.error("coinbase_fetch_order_book_failed", symbol=symbol, error=str(e))
            raise APIError(
                f"Failed to fetch order book: {e}",
                exchange=self.name,
                details={"symbol": symbol},
            )

    async def fetch_trades(self, symbol: str, limit: int = 100) -> List[Trade]:
        """Fetch recent trades."""
        coinbase_symbol = self.denormalize_symbol(symbol)

        try:
            async with self.rate_limiter:
                result = await self._make_request(
                    "GET",
                    f"/api/v3/brokerage/products/{coinbase_symbol}/ticker",
                )

            trades_data = result.get("trades", [])[:limit]

            # Parse trades
            trades = []
            for i, trade in enumerate(trades_data):
                trades.append(
                    Trade(
                        trade_id=trade.get("trade_id", str(i)),
                        exchange=self.name,
                        symbol=symbol,
                        side=trade.get("side", "unknown"),
                        price=Decimal(str(trade["price"])),
                        quantity=Decimal(str(trade["size"])),
                        timestamp=datetime.fromisoformat(
                            trade["time"].replace("Z", "+00:00")
                        )
                        if "time" in trade
                        else datetime.utcnow(),
                    )
                )

            return trades

        except Exception as e:
            logger.error("coinbase_fetch_trades_failed", symbol=symbol, error=str(e))
            raise APIError(
                f"Failed to fetch trades: {e}",
                exchange=self.name,
                details={"symbol": symbol},
            )

    async def fetch_supported_pairs(self) -> List[str]:
        """Fetch all trading pairs supported by Coinbase Advanced."""
        try:
            async with self.rate_limiter:
                result = await self._make_request("GET", "/api/v3/brokerage/products")

            # Normalize all pairs
            pairs = []
            for product in result.get("products", []):
                if product.get("status") == "online" and product.get("trading_disabled") is False:
                    try:
                        normalized = self.normalize_symbol(product["product_id"])
                        if "/" in normalized:
                            pairs.append(normalized)
                    except Exception:
                        continue

            logger.info("coinbase_supported_pairs_fetched", count=len(pairs))
            return sorted(pairs)

        except Exception as e:
            logger.error("coinbase_fetch_supported_pairs_failed", error=str(e))
            raise APIError(
                f"Failed to fetch supported pairs: {e}", exchange=self.name
            )

    # ==================== Account Management (Private API) ====================

    async def fetch_balances(self) -> List[Balance]:
        """Fetch all account balances."""
        try:
            async with self.rate_limiter:
                result = await self._make_request(
                    "GET", "/api/v3/brokerage/accounts", signed=True
                )

            balances = []
            for account in result.get("accounts", []):
                currency = account.get("currency", "UNKNOWN")
                available_balance = account.get("available_balance", {})
                hold = account.get("hold", {})

                available = Decimal(str(available_balance.get("value", "0")))
                locked = Decimal(str(hold.get("value", "0")))
                total = available + locked

                if total > 0:
                    balances.append(
                        Balance(
                            exchange=self.name,
                            currency=currency,
                            total=total,
                            available=available,
                            locked=locked,
                            timestamp=datetime.utcnow(),
                        )
                    )

            return balances

        except Exception as e:
            logger.error("coinbase_fetch_balances_failed", error=str(e))
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

        coinbase_symbol = self.denormalize_symbol(symbol)

        # Build order configuration
        order_config = {
            "client_order_id": str(uuid.uuid4()),
            "product_id": coinbase_symbol,
            "side": side.upper(),
        }

        if order_type == "market":
            if side == "buy":
                order_config["order_configuration"] = {
                    "market_market_ioc": {
                        "quote_size": str(quantity * price) if price else str(quantity)
                    }
                }
            else:
                order_config["order_configuration"] = {
                    "market_market_ioc": {"base_size": str(quantity)}
                }
        elif order_type == "limit":
            order_config["order_configuration"] = {
                "limit_limit_gtc": {
                    "base_size": str(quantity),
                    "limit_price": str(price),
                    "post_only": False,
                }
            }

        try:
            async with self.rate_limiter:
                result = await self._make_request(
                    "POST",
                    "/api/v3/brokerage/orders",
                    data=order_config,
                    signed=True,
                )

            success_response = result.get("success_response", {})
            order_id = success_response.get("order_id", f"ORDER-{int(time.time())}")

            return Order(
                order_id=order_id,
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
            logger.error("coinbase_create_order_failed", symbol=symbol, error=str(e))
            raise self._map_order_error(e, symbol)

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an open order."""
        try:
            async with self.rate_limiter:
                await self._make_request(
                    "POST",
                    "/api/v3/brokerage/orders/batch_cancel",
                    data={"order_ids": [order_id]},
                    signed=True,
                )

            logger.info("coinbase_order_cancelled", order_id=order_id)
            return True

        except Exception as e:
            logger.error("coinbase_cancel_order_failed", order_id=order_id, error=str(e))
            return False

    async def fetch_order(self, order_id: str, symbol: str) -> Order:
        """Fetch order status."""
        try:
            async with self.rate_limiter:
                result = await self._make_request(
                    "GET",
                    f"/api/v3/brokerage/orders/historical/{order_id}",
                    signed=True,
                )

            order_data = result.get("order", {})
            if not order_data:
                raise OrderNotFoundError(
                    f"Order {order_id} not found",
                    exchange=self.name,
                    order_id=order_id,
                )

            return self._parse_coinbase_order(order_data)

        except OrderNotFoundError:
            raise
        except Exception as e:
            logger.error("coinbase_fetch_order_failed", order_id=order_id, error=str(e))
            raise APIError(
                f"Failed to fetch order: {e}",
                exchange=self.name,
                details={"order_id": order_id},
            )

    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Fetch all open orders."""
        try:
            params = {}
            if symbol:
                params["product_id"] = self.denormalize_symbol(symbol)

            async with self.rate_limiter:
                result = await self._make_request(
                    "GET",
                    "/api/v3/brokerage/orders/historical/batch",
                    params=params,
                    signed=True,
                )

            orders = []
            for order_data in result.get("orders", []):
                if order_data.get("status") in ["OPEN", "PENDING"]:
                    parsed_order = self._parse_coinbase_order(order_data)
                    if not symbol or parsed_order.symbol == symbol:
                        orders.append(parsed_order)

            return orders

        except Exception as e:
            logger.error("coinbase_fetch_open_orders_failed", error=str(e))
            raise APIError(f"Failed to fetch open orders: {e}", exchange=self.name)

    # ==================== WebSocket Real-Time Data ====================

    async def subscribe_order_book(self, symbol: str) -> None:
        """Subscribe to real-time order book updates."""
        if not self._ws_manager:
            raise APIError("WebSocket not configured", exchange=self.name)

        coinbase_symbol = self.denormalize_symbol(symbol)

        subscription = {
            "type": "subscribe",
            "product_ids": [coinbase_symbol],
            "channel": "level2",
        }

        await self._ws_manager.subscribe("level2", symbol, subscription)
        logger.info("coinbase_orderbook_subscribed", symbol=symbol)

    async def subscribe_trades(self, symbol: str) -> None:
        """Subscribe to real-time trade updates."""
        if not self._ws_manager:
            raise APIError("WebSocket not configured", exchange=self.name)

        coinbase_symbol = self.denormalize_symbol(symbol)

        subscription = {
            "type": "subscribe",
            "product_ids": [coinbase_symbol],
            "channel": "market_trades",
        }

        await self._ws_manager.subscribe("market_trades", symbol, subscription)
        logger.info("coinbase_trades_subscribed", symbol=symbol)

    async def unsubscribe(self, channel: str, symbol: str) -> None:
        """Unsubscribe from a channel."""
        if not self._ws_manager:
            return

        coinbase_symbol = self.denormalize_symbol(symbol)

        subscription = {
            "type": "unsubscribe",
            "product_ids": [coinbase_symbol],
            "channel": channel,
        }

        await self._ws_manager.send(subscription)
        await self._ws_manager.unsubscribe(channel, symbol)
        logger.info("coinbase_unsubscribed", channel=channel, symbol=symbol)

    # ==================== Utility Methods ====================

    def normalize_symbol(self, symbol: str) -> str:
        """Convert Coinbase symbol (BTC-USD) to standard format (BTC/USD)."""
        return symbol.replace("-", "/")

    def denormalize_symbol(self, symbol: str) -> str:
        """Convert standard format (BTC/USD) to Coinbase symbol (BTC-USD)."""
        return symbol.replace("/", "-")

    async def _sign_request(self, endpoint: str, method: str) -> str:
        """
        Generate JWT token for authentication.

        Coinbase Advanced uses ES256 (ECDSA with P-256 and SHA-256).
        """
        if not self.api_key or not self.api_secret:
            raise AuthenticationError(
                "API key and secret required for private endpoints", exchange=self.name
            )

        uri = f"{method} {self.api_url.replace('https://api.coinbase.com', '')}{endpoint}"

        payload = {
            "sub": self.api_key,
            "iss": "coinbase-cloud",
            "nbf": int(time.time()),
            "exp": int(time.time()) + 120,  # 2 minutes
            "uri": uri,
        }

        headers = {"kid": self.api_key, "nonce": str(uuid.uuid4())}

        try:
            # Encode using ES256 algorithm
            token = jwt.encode(
                payload, self.api_secret, algorithm="ES256", headers=headers
            )
            return token
        except Exception as e:
            logger.error("jwt_generation_failed", error=str(e))
            raise AuthenticationError(
                f"Failed to generate JWT token: {e}", exchange=self.name
            )

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Dict[str, Any]:
        """Make HTTP request with rate limiting, retries, and error handling."""
        if not self._session:
            raise ExchangeUnavailableError("Session not initialized", exchange=self.name)

        params = params or {}
        url = f"{self.api_url}{endpoint}"

        # Prepare headers
        headers = {"Content-Type": "application/json"}

        # Add authentication for signed requests
        if signed:
            jwt_token = await self._sign_request(endpoint, method)
            headers["Authorization"] = f"Bearer {jwt_token}"

        # Make request with retries
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
        )
        async def _request():
            async with self._session.request(
                method, url, params=params, json=data, headers=headers, timeout=10
            ) as resp:
                response_text = await resp.text()

                # Handle error responses
                if resp.status == 429:
                    raise RateLimitExceeded(
                        "Coinbase rate limit exceeded", exchange=self.name
                    )
                elif resp.status == 401:
                    raise AuthenticationError(
                        "Invalid Coinbase credentials", exchange=self.name
                    )
                elif resp.status >= 400:
                    try:
                        error_data = json.loads(response_text)
                        error_msg = error_data.get("message", response_text)
                    except:
                        error_msg = response_text

                    raise APIError(
                        f"Coinbase API error: {error_msg}",
                        exchange=self.name,
                        details={"status": resp.status},
                    )

                # Parse JSON response
                try:
                    return json.loads(response_text)
                except json.JSONDecodeError:
                    logger.error(
                        "invalid_json_response",
                        response=response_text[:200],
                        endpoint=endpoint,
                    )
                    return {}

        try:
            return await _request()
        except aiohttp.ClientError as e:
            raise NetworkError(
                f"Network error: {e}", exchange=self.name, details={"endpoint": endpoint}
            )

    def _parse_coinbase_order(self, order_data: Dict[str, Any]) -> Order:
        """Parse Coinbase order format to normalized Order."""
        # Map Coinbase status to our status
        status_map = {
            "OPEN": "open",
            "FILLED": "filled",
            "CANCELLED": "cancelled",
            "PENDING": "pending",
            "REJECTED": "rejected",
            "EXPIRED": "expired",
        }

        coinbase_status = order_data.get("status", "OPEN").upper()
        status = status_map.get(coinbase_status, "open")

        # Get order configuration
        order_config = order_data.get("order_configuration", {})
        limit_config = order_config.get("limit_limit_gtc", {})
        market_config = order_config.get("market_market_ioc", {})

        # Determine price and quantity
        price = None
        if limit_config:
            price = Decimal(str(limit_config.get("limit_price", "0")))
            quantity = Decimal(str(limit_config.get("base_size", "0")))
        elif market_config:
            quantity = Decimal(
                str(market_config.get("base_size", market_config.get("quote_size", "0")))
            )
        else:
            quantity = Decimal("0")

        return Order(
            order_id=order_data.get("order_id", ""),
            exchange=self.name,
            symbol=self.normalize_symbol(order_data.get("product_id", "")),
            side=order_data.get("side", "BUY").lower(),
            order_type=order_data.get("order_type", "LIMIT").lower(),
            quantity=quantity,
            price=price,
            filled_quantity=Decimal(str(order_data.get("filled_size", "0"))),
            status=status,
            timestamp=datetime.fromisoformat(
                order_data.get("created_time", datetime.utcnow().isoformat()).replace(
                    "Z", "+00:00"
                )
            ),
            updated_at=datetime.utcnow(),
            fee=Decimal(str(order_data.get("total_fees", "0"))),
        )

    def _map_order_error(self, error: Exception, symbol: str) -> Exception:
        """Map order creation errors."""
        error_msg = str(error).lower()

        if "insufficient" in error_msg:
            return InsufficientFundsError(str(error), exchange=self.name)
        elif "invalid" in error_msg:
            return InvalidOrderError(str(error), exchange=self.name, details={"symbol": symbol})
        else:
            return APIError(str(error), exchange=self.name)
