from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from json import JSONDecodeError

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from starlette.websockets import WebSocketState

from app.core.exceptions import InvalidTradeError
from app.models.schemas import WsSubscribeMessage
from app.models.trade import LiquidityStreamMessage

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)

_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9.\-]{1,12}$")


@router.websocket("/ws/liquidity/{symbol}")
async def liquidity_symbol_stream(websocket: WebSocket, symbol: str) -> None:
    """Stream net flow and buy/sell volumes for a single ticker."""

    manager = websocket.app.state.broadcaster
    engine = websocket.app.state.liquidity_engine
    alerts = websocket.app.state.alerts
    heartbeat_seconds = websocket.app.state.settings.ws_heartbeat_seconds

    try:
        ticker = _normalize_symbol(symbol)
    except InvalidTradeError:
        try:
            await websocket.close(code=1008, reason="Invalid symbol")
        except Exception:
            logger.warning("could not reject invalid websocket symbol=%s", symbol, exc_info=True)
        return

    await manager.connect(websocket, ticker)
    try:
        tickchart = getattr(websocket.app.state, "tickchart", None)
        if tickchart is not None and getattr(tickchart, "watch", None):
            await tickchart.watch(ticker)
        snapshot = LiquidityStreamMessage.from_session(
            engine.session_snapshot(ticker),
            timestamp=datetime.now(timezone.utc),
        )
        await _send(websocket, snapshot.as_json())
        for alert in alerts.recent(ticker)[:20]:
            await _send(websocket, alert.as_json())
        await _keep_alive(websocket, heartbeat_seconds)
    except WebSocketDisconnect:
        logger.info("client disconnected from %s stream", ticker)
    except Exception:
        logger.exception("websocket handler failed for %s", ticker)
    finally:
        await manager.disconnect(websocket)


@router.websocket("/ws/liquidity")
async def liquidity_stream(
    websocket: WebSocket,
    symbols: str | None = Query(default=None, description="Comma-separated ticker list"),
) -> None:
    manager = websocket.app.state.broadcaster
    heartbeat_seconds = websocket.app.state.settings.ws_heartbeat_seconds
    initial = {part.strip().upper() for part in symbols.split(",")} if symbols else set()
    initial.discard("")

    await manager.connect(websocket, initial)
    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=heartbeat_seconds,
                )
            except TimeoutError:
                await _send(websocket, {"type": "ping"})
                continue
            except JSONDecodeError:
                await _send(
                    websocket,
                    {
                        "type": "error",
                        "error": "invalid_json",
                        "message": "WebSocket payload must be valid JSON",
                    },
                )
                continue

            try:
                message = WsSubscribeMessage.model_validate(raw)
            except ValidationError as exc:
                await _send(
                    websocket,
                    {"type": "error", "error": "validation_error", "details": exc.errors()},
                )
                continue

            if message.action == "subscribe":
                current = await manager.subscribe(websocket, message.symbols)
                await _send(websocket, {"type": "subscribed", "symbols": sorted(current)})
            elif message.action == "unsubscribe":
                current = await manager.unsubscribe(websocket, message.symbols)
                await _send(websocket, {"type": "subscribed", "symbols": sorted(current)})
            elif message.action == "ping":
                await _send(websocket, {"type": "pong"})
            else:
                await _send(
                    websocket,
                    {
                        "type": "error",
                        "error": "unknown_action",
                        "message": f"Unsupported action '{message.action}'",
                    },
                )
    except WebSocketDisconnect:
        logger.info("client disconnected from liquidity stream")
    except Exception:
        logger.exception("websocket handler failed")
    finally:
        await manager.disconnect(websocket)


async def _keep_alive(websocket: WebSocket, heartbeat_seconds: int) -> None:
    while websocket.client_state == WebSocketState.CONNECTED:
        try:
            message = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=heartbeat_seconds,
            )
        except TimeoutError:
            await _send(websocket, {"type": "ping"})
            continue

        if message.strip().lower() in {"ping", '{"action":"ping"}'}:
            await _send(websocket, {"type": "pong"})


async def _send(websocket: WebSocket, payload: dict) -> None:
    try:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        raise
    except Exception:
        logger.warning("failed to send websocket payload", exc_info=True)
        raise WebSocketDisconnect() from None


def _normalize_symbol(symbol: str) -> str:
    ticker = symbol.strip().upper()
    if not _SYMBOL_PATTERN.fullmatch(ticker):
        raise InvalidTradeError("symbol is invalid", details={"symbol": symbol})
    return ticker
