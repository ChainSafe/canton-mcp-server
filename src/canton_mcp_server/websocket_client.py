"""
WebSocket client for connecting to facilitator's WebSocket server.

Handles real-time payment coordination:
- Check balance before tool calls
- Broadcast payment-required events
- Listen to balance-updated and access-denied events
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Optional, Callable
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

logger = logging.getLogger(__name__)


class FacilitatorWebSocketClient:
    """WebSocket client for facilitator communication"""

    def __init__(self, facilitator_url: str):
        """
        Initialize WebSocket client.

        Args:
            facilitator_url: Base URL of facilitator (e.g., http://localhost:3000)
        """
        # Convert HTTP URL to WebSocket URL
        ws_url = facilitator_url.replace("http://", "ws://").replace("https://", "wss://")
        self.ws_url = f"{ws_url}/ws"
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self.balance_cache: Dict[str, float] = {}  # party -> balance
        self.reconnect_delay = 5  # seconds
        self.listen_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        """Connect to facilitator WebSocket server"""
        try:
            logger.info(f"🔌 Connecting to facilitator WebSocket: {self.ws_url}")
            self.websocket = await websockets.connect(
                self.ws_url,
                ping_interval=20,
                ping_timeout=10,
            )
            self.connected = True
            logger.info("✅ Connected to facilitator WebSocket")
            
            # Start listening for messages
            self.listen_task = asyncio.create_task(self._listen())
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to facilitator WebSocket: {e}")
            self.connected = False
            return False

    async def disconnect(self):
        """Disconnect from facilitator WebSocket server"""
        self.connected = False
        if self.listen_task:
            self.listen_task.cancel()
            try:
                await self.listen_task
            except asyncio.CancelledError:
                pass
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        logger.info("🔌 Disconnected from facilitator WebSocket")

    async def _listen(self):
        """Listen for messages from facilitator"""
        while self.connected:
            try:
                if not self.websocket:
                    break
                
                message_str = await self.websocket.recv()
                message = json.loads(message_str)
                await self._handle_message(message)
            except ConnectionClosed:
                logger.warning("🔌 WebSocket connection closed, attempting reconnect...")
                self.connected = False
                await self._reconnect()
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error receiving WebSocket message: {e}")
                await asyncio.sleep(1)

    async def _handle_message(self, message: dict):
        """Handle incoming WebSocket message"""
        msg_type = message.get("type")
        party = message.get("party")
        data = message.get("data", {})

        if msg_type == "balance-updated":
            # Update balance cache
            balance = data.get("balance", 0)
            if party:
                self.balance_cache[party] = balance
                logger.debug(f"💰 Balance updated for {party}: ${balance:.2f}")
        
        elif msg_type == "access-denied":
            # Access denied due to threshold
            balance = data.get("balance", 0)
            reason = data.get("reason", "Unknown")
            if party:
                self.balance_cache[party] = balance
                logger.warning(f"🚫 Access denied for {party}: {reason} (balance: ${balance:.2f})")

    async def _reconnect(self):
        """Reconnect to WebSocket server with exponential backoff"""
        delay = self.reconnect_delay
        max_delay = 60
        while not self.connected:
            try:
                await asyncio.sleep(delay)
                logger.info(f"🔄 Attempting to reconnect to facilitator WebSocket...")
                success = await self.connect()
                if success:
                    break
                delay = min(delay * 2, max_delay)
            except Exception as e:
                logger.error(f"❌ Reconnection attempt failed: {e}")
                delay = min(delay * 2, max_delay)

    async def check_balance(self, party: str) -> float:
        """
        Check balance for a party.
        
        Uses cached balance if available, otherwise queries facilitator HTTP endpoint.
        
        Args:
            party: Party ID
            
        Returns:
            Current balance (amountDue - amountPaid)
        """
        # Return cached balance if available
        if party in self.balance_cache:
            return self.balance_cache[party]
        
        # Fallback to HTTP query if not cached
        try:
            import httpx
            facilitator_url = self.ws_url.replace("/ws", "").replace("ws://", "http://").replace("wss://", "https://")
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{facilitator_url}/balance",
                    params={"party": party},
                )
                if response.status_code == 200:
                    result = response.json()
                    balance = result.get("balance", 0)
                    self.balance_cache[party] = balance
                    return balance
        except Exception as e:
            logger.warning(f"⚠️  Failed to query balance via HTTP: {e}")
        
        return 0.0  # Default to 0 if query fails

    async def broadcast_payment_required(
        self,
        party: str,
        payee: str,
        amount: float,
        resource: str,
        tool: str,
    ):
        """
        Broadcast payment-required event to facilitator.
        
        Args:
            party: Payer party ID
            payee: Payee party ID
            amount: Payment amount
            resource: Resource URL
            tool: Tool name
        """
        if not self.connected or not self.websocket:
            logger.warning("⚠️  WebSocket not connected, cannot broadcast payment-required")
            return

        message = {
            "type": "payment-required",
            "party": party,
            "data": {
                "tool": tool,
                "amount": amount,
                "resource": resource,
                "payee": payee,
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        try:
            await self.websocket.send(json.dumps(message))
            logger.info(f"📤 Broadcasted payment-required: {tool} (${amount:.2f}) for {party}")
        except Exception as e:
            logger.error(f"❌ Failed to broadcast payment-required: {e}")
            # Attempt reconnect
            self.connected = False
            asyncio.create_task(self._reconnect())
