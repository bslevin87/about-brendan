"""
Tests for Coinbase Advanced exchange adapter.

Tests JWT authentication, REST API calls, symbol normalization,
order book fetching, balance management, order creation, and WebSocket handling.
"""
import pytest
import jwt
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import ClientSession

from src.exchanges.adapters.coinbase_advanced import CoinbaseAdvancedExchange
from src.exchanges.rate_limiter import RateLimiter
from src.exchanges.models import OrderBook, Ticker, Balance, Order
from src.exchanges.exceptions import (
    AuthenticationError,
    RateLimitExceeded,
    ExchangeException,
    InvalidOrderError,
)


class TestCoinbaseAdvancedExchange:
    """Test Coinbase Advanced exchange adapter."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = {
            "name": "Coinbase Advanced",
            "api_url": "https://api.coinbase.com",
            "ws_url": "wss://advanced-trade-ws.coinbase.com",
            "api_key": "test_key_name",
            "api_secret": """-----BEGIN EC PRIVATE KEY-----
MHcCAQEEIBKHWFawjt5gsXhE5PXs+G/sZPdFCvxlOJsHjpXw+T0ooAoGCCqGSM49
AwEHoUQDQgAE+N4Bfyb6R9YU8F2vwzc4v8gp2j5X0mJ6nv4mT5nW9sT8nW5sT9m
J6nv4mT5nW9sT8nW5sT9mJ6nv4mT5nW9sT==
-----END EC PRIVATE KEY-----""",
            "rate_limit_requests_per_second": 10,
            "taker_fee": 0.006,
            "maker_fee": 0.004,
        }
        self.rate_limiter = RateLimiter(requests_per_second=10, name="coinbase_test")
        self.exchange = CoinbaseAdvancedExchange(self.config, self.rate_limiter)

    def teardown_method(self):
        """Clean up after tests."""
        if hasattr(self.exchange, "_session") and self.exchange._session:
            # Session cleanup will be handled by disconnect
            pass

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test exchange initialization."""
        assert self.exchange.name == "Coinbase Advanced"
        assert self.exchange.api_url == "https://api.coinbase.com"
        assert self.exchange.ws_url == "wss://advanced-trade-ws.coinbase.com"
        assert not self.exchange.connected

    @pytest.mark.asyncio
    async def test_jwt_generation(self):
        """Test JWT token generation with ES256 algorithm."""
        # Generate JWT token
        token = await self.exchange._sign_request("/api/v3/brokerage/time", "GET")

        # Verify it's a valid JWT
        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # JWT has 3 parts

        # Decode without verification to check payload structure
        unverified_payload = jwt.decode(
            token, options={"verify_signature": False}
        )

        assert unverified_payload["sub"] == "test_key_name"
        assert unverified_payload["iss"] == "coinbase-cloud"
        assert "nbf" in unverified_payload
        assert "exp" in unverified_payload
        assert unverified_payload["uri"] == "GET /api/v3/brokerage/time"

        # Check headers
        unverified_headers = jwt.get_unverified_header(token)
        assert unverified_headers["kid"] == "test_key_name"
        assert "nonce" in unverified_headers
        assert unverified_headers["alg"] == "ES256"

    def test_symbol_normalization(self):
        """Test symbol format conversion."""
        # Coinbase format to standard
        assert self.exchange.normalize_symbol("BTC-USD") == "BTC/USD"
        assert self.exchange.normalize_symbol("ETH-USD") == "ETH/USD"
        assert self.exchange.normalize_symbol("BTC-EUR") == "BTC/EUR"

        # Standard to Coinbase format
        assert self.exchange.denormalize_symbol("BTC/USD") == "BTC-USD"
        assert self.exchange.denormalize_symbol("ETH/USD") == "ETH-USD"
        assert self.exchange.denormalize_symbol("BTC/EUR") == "BTC-EUR"

        # Round-trip conversion
        assert (
            self.exchange.normalize_symbol(
                self.exchange.denormalize_symbol("BTC/USD")
            )
            == "BTC/USD"
        )

    @pytest.mark.asyncio
    async def test_connect(self):
        """Test connection initialization."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session.return_value
            )
            mock_session.return_value.__aexit__ = AsyncMock()

            await self.exchange.connect()
            assert self.exchange.connected
            assert self.exchange._session is not None

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test clean disconnection."""
        # Setup connection
        self.exchange._session = MagicMock(spec=ClientSession)
        self.exchange._session.close = AsyncMock()
        self.exchange._session.closed = False
        self.exchange.connected = True

        # Mock websocket manager
        self.exchange._ws_manager = MagicMock()
        self.exchange._ws_manager.disconnect = AsyncMock()

        await self.exchange.disconnect()
        assert not self.exchange.connected
        self.exchange._session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_ticker(self):
        """Test fetching ticker data."""
        mock_response = {
            "trades": [
                {
                    "trade_id": "123",
                    "product_id": "BTC-USD",
                    "price": "50000.00",
                    "size": "0.5",
                    "time": "2024-01-01T00:00:00Z",
                    "side": "BUY",
                }
            ],
            "best_bid": "49995.00",
            "best_ask": "50005.00",
        }

        with patch.object(
            self.exchange, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            ticker = await self.exchange.fetch_ticker("BTC/USD")

            assert isinstance(ticker, Ticker)
            assert ticker.symbol == "BTC/USD"
            assert ticker.last == Decimal("50000.00")
            assert ticker.bid == Decimal("49995.00")
            assert ticker.ask == Decimal("50005.00")
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_order_book(self):
        """Test fetching order book."""
        mock_response = {
            "pricebook": {
                "product_id": "BTC-USD",
                "bids": [
                    {"price": "50000.00", "size": "1.5"},
                    {"price": "49900.00", "size": "2.0"},
                ],
                "asks": [
                    {"price": "50100.00", "size": "1.0"},
                    {"price": "50200.00", "size": "1.5"},
                ],
                "time": "2024-01-01T00:00:00Z",
            }
        }

        with patch.object(
            self.exchange, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            order_book = await self.exchange.fetch_order_book("BTC/USD", depth=20)

            assert isinstance(order_book, OrderBook)
            assert order_book.symbol == "BTC/USD"
            assert order_book.exchange == "Coinbase Advanced"
            assert len(order_book.bids) == 2
            assert len(order_book.asks) == 2
            assert order_book.bids[0] == (Decimal("50000.00"), Decimal("1.5"))
            assert order_book.asks[0] == (Decimal("50100.00"), Decimal("1.0"))

    @pytest.mark.asyncio
    async def test_fetch_balances(self):
        """Test fetching account balances."""
        mock_response = {
            "accounts": [
                {
                    "uuid": "account-1",
                    "name": "BTC Wallet",
                    "currency": "BTC",
                    "available_balance": {"value": "1.5", "currency": "BTC"},
                    "hold": {"value": "0.1", "currency": "BTC"},
                },
                {
                    "uuid": "account-2",
                    "name": "USD Wallet",
                    "currency": "USD",
                    "available_balance": {"value": "50000.00", "currency": "USD"},
                    "hold": {"value": "1000.00", "currency": "USD"},
                },
            ]
        }

        with patch.object(
            self.exchange, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            balances = await self.exchange.fetch_balances()

            assert len(balances) == 2
            assert "BTC" in balances
            assert "USD" in balances

            btc_balance = balances["BTC"]
            assert isinstance(btc_balance, Balance)
            assert btc_balance.currency == "BTC"
            assert btc_balance.free == Decimal("1.5")
            assert btc_balance.used == Decimal("0.1")
            assert btc_balance.total == Decimal("1.6")

    @pytest.mark.asyncio
    async def test_create_limit_order(self):
        """Test creating limit order."""
        mock_response = {
            "success": True,
            "order_id": "order-123",
            "product_id": "BTC-USD",
            "side": "BUY",
            "order_configuration": {
                "limit_limit_gtc": {
                    "base_size": "0.1",
                    "limit_price": "50000.00",
                }
            },
        }

        with patch.object(
            self.exchange, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            order = await self.exchange.create_order(
                symbol="BTC/USD",
                order_type="limit",
                side="buy",
                amount=Decimal("0.1"),
                price=Decimal("50000.00"),
            )

            assert isinstance(order, Order)
            assert order.order_id == "order-123"
            assert order.symbol == "BTC/USD"
            assert order.side == "buy"
            assert order.amount == Decimal("0.1")
            assert order.price == Decimal("50000.00")

    @pytest.mark.asyncio
    async def test_create_market_order(self):
        """Test creating market order."""
        mock_response = {
            "success": True,
            "order_id": "order-456",
            "product_id": "BTC-USD",
            "side": "SELL",
            "order_configuration": {
                "market_market_ioc": {"base_size": "0.1"}
            },
        }

        with patch.object(
            self.exchange, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            order = await self.exchange.create_order(
                symbol="BTC/USD",
                order_type="market",
                side="sell",
                amount=Decimal("0.1"),
            )

            assert isinstance(order, Order)
            assert order.order_id == "order-456"
            assert order.side == "sell"
            assert order.order_type == "market"

    @pytest.mark.asyncio
    async def test_cancel_order(self):
        """Test canceling an order."""
        mock_response = {"success": True, "order_id": "order-123"}

        with patch.object(
            self.exchange, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await self.exchange.cancel_order("order-123")
            assert result is True

    @pytest.mark.asyncio
    async def test_get_order_status(self):
        """Test getting order status."""
        mock_response = {
            "order": {
                "order_id": "order-123",
                "product_id": "BTC-USD",
                "side": "BUY",
                "status": "FILLED",
                "order_configuration": {
                    "limit_limit_gtc": {
                        "base_size": "0.1",
                        "limit_price": "50000.00",
                    }
                },
                "filled_size": "0.1",
                "average_filled_price": "50000.00",
            }
        }

        with patch.object(
            self.exchange, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            order = await self.exchange.get_order_status("order-123")

            assert isinstance(order, Order)
            assert order.order_id == "order-123"
            assert order.status == "filled"
            assert order.filled == Decimal("0.1")

    @pytest.mark.asyncio
    async def test_rate_limit_error(self):
        """Test handling rate limit errors."""
        with patch.object(
            self.exchange, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = RateLimitExceeded(
                "Rate limit exceeded", exchange="Coinbase Advanced"
            )

            with pytest.raises(RateLimitExceeded):
                await self.exchange.fetch_ticker("BTC/USD")

    @pytest.mark.asyncio
    async def test_authentication_error(self):
        """Test handling authentication errors."""
        with patch.object(
            self.exchange, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = AuthenticationError(
                "Invalid API key", exchange="Coinbase Advanced"
            )

            with pytest.raises(AuthenticationError):
                await self.exchange.fetch_balances()

    @pytest.mark.asyncio
    async def test_invalid_order_error(self):
        """Test handling invalid order errors."""
        with patch.object(
            self.exchange, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = InvalidOrderError(
                "Insufficient funds", exchange="Coinbase Advanced"
            )

            with pytest.raises(InvalidOrderError):
                await self.exchange.create_order(
                    symbol="BTC/USD",
                    order_type="market",
                    side="buy",
                    amount=Decimal("100.0"),
                )

    @pytest.mark.asyncio
    async def test_websocket_subscription(self):
        """Test WebSocket order book subscription."""
        # Mock websocket manager
        self.exchange._ws_manager = MagicMock()
        self.exchange._ws_manager.subscribe = AsyncMock()

        await self.exchange.subscribe_order_book("BTC/USD")

        self.exchange._ws_manager.subscribe.assert_called_once()
        call_args = self.exchange._ws_manager.subscribe.call_args
        assert call_args[0][0] == "level2"
        assert call_args[0][1] == "BTC/USD"
        assert call_args[0][2]["product_ids"] == ["BTC-USD"]

    @pytest.mark.asyncio
    async def test_websocket_trade_subscription(self):
        """Test WebSocket trade subscription."""
        # Mock websocket manager
        self.exchange._ws_manager = MagicMock()
        self.exchange._ws_manager.subscribe = AsyncMock()

        await self.exchange.subscribe_trades("ETH/USD")

        self.exchange._ws_manager.subscribe.assert_called_once()
        call_args = self.exchange._ws_manager.subscribe.call_args
        assert call_args[0][0] == "market_trades"
        assert call_args[0][1] == "ETH/USD"
        assert call_args[0][2]["product_ids"] == ["ETH-USD"]

    @pytest.mark.asyncio
    async def test_order_book_callback(self):
        """Test order book update callback processing."""
        callback = AsyncMock()
        self.exchange._ws_manager = MagicMock()

        # Simulate WebSocket message
        ws_message = {
            "channel": "l2_data",
            "events": [
                {
                    "type": "snapshot",
                    "product_id": "BTC-USD",
                    "updates": [
                        {"side": "bid", "price_level": "50000.00", "new_quantity": "1.5"},
                        {"side": "offer", "price_level": "50100.00", "new_quantity": "1.0"},
                    ],
                }
            ],
        }

        # Process the message
        processed = self.exchange._process_order_book_update(ws_message)

        assert processed is not None
        assert processed["symbol"] == "BTC/USD"
        assert "bids" in processed
        assert "asks" in processed

    @pytest.mark.asyncio
    async def test_get_trading_pairs(self):
        """Test fetching available trading pairs."""
        mock_response = {
            "products": [
                {
                    "product_id": "BTC-USD",
                    "price": "50000.00",
                    "status": "online",
                    "base_currency": "BTC",
                    "quote_currency": "USD",
                },
                {
                    "product_id": "ETH-USD",
                    "price": "3000.00",
                    "status": "online",
                    "base_currency": "ETH",
                    "quote_currency": "USD",
                },
            ]
        }

        with patch.object(
            self.exchange, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            pairs = await self.exchange.get_trading_pairs()

            assert len(pairs) == 2
            assert "BTC/USD" in pairs
            assert "ETH/USD" in pairs

    @pytest.mark.asyncio
    async def test_error_response_handling(self):
        """Test proper error response parsing."""
        with patch.object(
            self.exchange, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = ExchangeException(
                "API error: Invalid request", exchange="Coinbase Advanced"
            )

            with pytest.raises(ExchangeException) as exc_info:
                await self.exchange.fetch_ticker("INVALID/PAIR")

            assert "Invalid request" in str(exc_info.value)

    def test_fee_calculation(self):
        """Test fee calculations."""
        # Taker fee
        taker_fee = self.exchange.config["taker_fee"]
        assert taker_fee == 0.006  # 0.6%

        # Maker fee
        maker_fee = self.exchange.config["maker_fee"]
        assert maker_fee == 0.004  # 0.4%

        # Calculate fee for order
        order_value = Decimal("50000")  # $50,000 order
        calculated_taker_fee = order_value * Decimal(str(taker_fee))
        assert calculated_taker_fee == Decimal("300")  # $300 fee
