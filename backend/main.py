import asyncio
import logging
import os
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from game import Game
from models import PlayerAction, ActionType, Phase

logger = logging.getLogger("station")

app = FastAPI()

# In-memory registry of active games: room_code -> Game
ROOMS: dict[str, Game] = {}

# Room lifecycle: how long an empty/finished room stays in memory before being
# purged. Bounds memory usage and lets stale 4-char room codes be reused for a
# fresh game after the TTL.
ROOM_CLEANUP_SECONDS = 600  # 10 minutes
# Minimum gap (seconds) between manual resolves. Blocks double-clicks and a
# host resolve racing the auto-timer from skipping a whole action window.
RESOLVE_DEBOUNCE_SECONDS = 1.0

# One auto-resolve timer task per room. Re-spawning cancels the previous task
# so concurrent timers can never double-resolve or skip a round.
ROOM_TIMERS: dict[str, asyncio.Task] = {}


class ConnectionManager:
    """Tracks WebSocket connections per room, keyed by player_id."""

    def __init__(self) -> None:
        self.connections: dict[str, dict[str, WebSocket]] = {}

    def register(self, room_code: str, player_id: str, websocket: WebSocket) -> None:
        self.connections.setdefault(room_code, {})[player_id] = websocket

    def disconnect(self, room_code: str, player_id: str, websocket: WebSocket) -> bool:
        """Unregister a socket; returns True if it was the active one.

        Stale sockets are ignored: if a player reconnected on a new socket,
        the old socket's disconnect must not unregister (or down) the fresh
        one.
        """
        room = self.connections.get(room_code)
        if room is None:
            return False
        if room.get(player_id) is not websocket:
            return False
        room.pop(player_id, None)
        if not room:
            del self.connections[room_code]
        return True

    def room(self, room_code: str) -> dict[str, WebSocket]:
        return self.connections.get(room_code, {})


manager = ConnectionManager()


@app.get("/api/health")
async def health():
    return {"status": "ok"}


async def broadcast_state(room_code: str) -> None:
    """Send current state to every connected player in a room."""
    game = ROOMS.get(room_code)
    if game is None:
        return
    state_data = game.get_state().model_dump(mode="json")
    for player_id, ws in list(manager.room(room_code).items()):
        try:
            await ws.send_json({
                "type": "state",
                "state": state_data,
                "player_id": player_id,
            })
        except Exception:
            manager.disconnect(room_code, player_id, ws)


async def schedule_room_cleanup(room_code: str) -> None:
    """Fire-and-forget: purge a room after a TTL if nobody has reconnected.

    Called when a room's last socket disconnects or a game reaches results.
    A player rejoining within the TTL keeps the room alive (their new socket
    makes manager.room() non-empty, so the purge is skipped).
    """
    await asyncio.sleep(ROOM_CLEANUP_SECONDS)
    if not manager.room(room_code):
        ROOMS.pop(room_code, None)
        prev = ROOM_TIMERS.pop(room_code, None)
        if prev is not None and not prev.done():
            prev.cancel()


def maybe_schedule_cleanup(room_code: str) -> None:
    """Schedule room purge once the game has reached results."""
    game = ROOMS.get(room_code)
    if game is None or game.state.phase != Phase.RESULTS:
        return
    asyncio.create_task(schedule_room_cleanup(room_code))


async def start_action_timer(room_code: str) -> None:
    """Background task: auto-resolve the round when the action deadline passes.

    Reads `action_phase_deadline` from the game state, sleeps until it
    elapses, then resolves the round (if the game is still in an action
    phase and the deadline hasn't been bumped by a manual resolve/advance).
    Handles missing games and stale deadlines gracefully — safe to fire-and-
    forget via `asyncio.create_task` from the WS handlers.
    """
    game = ROOMS.get(room_code)
    if game is None:
        return
    deadline = game.get_state().action_phase_deadline
    if deadline is None:
        return
    # Sleep until the deadline (clamped to >=0 to avoid negative sleeps).
    # `action_phase_deadline` is a wall-clock unix timestamp (set via
    # `time.time()` in game.py), so use `time.time()` here, not the
    # monotonic event-loop clock.
    remaining = deadline - time.time()
    if remaining > 0:
        await asyncio.sleep(remaining)
    # Re-read state after waking: the game may have been resolved manually,
    # ended, or removed while we slept.
    game = ROOMS.get(room_code)
    if game is None:
        return
    state = game.get_state()
    if state.phase not in (Phase.SURVIVAL, Phase.FINALE):
        return
    # If the deadline moved (manual resolve set a new one), bow out — a fresh
    # timer was spawned by the resolve handler and owns this round.
    if state.action_phase_deadline != deadline:
        return
    # 30-minute hard session cap: if the game has run >= 1800s since start,
    # end it as a loss instead of resolving another round.
    if state.started_at is not None and (time.time() - state.started_at) >= 1800:
        game._end_game(victory=False)
        await broadcast_state(room_code)
        maybe_schedule_cleanup(room_code)
        return
    try:
        game.resolve_round()
    except Exception:
        return
    await broadcast_state(room_code)
    # Re-arm the timer for the next round. `resolve_round` sets a fresh
    # `action_phase_deadline` for the next round (or clears it if the game
    # ended / transitioned to results), so the next `start_action_timer`
    # invocation will either sleep until that new deadline or exit
    # immediately (deadline is None). The stale-deadline guard at the top
    # of this function prevents double-resolve: if a manual resolve raced
    # us and set yet another deadline, the new task will see the changed
    # deadline and bow out.
    arm_action_timer(room_code)


def arm_action_timer(room_code: str) -> None:
    """Spawn (or replace) the room's single auto-resolve timer task.

    Cancelling the previous task before spawning a new one guarantees at
    most one timer per room, so a manual resolve racing the auto-timer can
    never leave two timers that both fire and double-resolve a round.
    """
    prev = ROOM_TIMERS.pop(room_code, None)
    if prev is not None and not prev.done():
        prev.cancel()
    ROOM_TIMERS[room_code] = asyncio.create_task(start_action_timer(room_code))


@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str):
    room_code = room_code.upper()
    player_id: str | None = None
    await websocket.accept()
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except (ValueError, TypeError):
                # Malformed JSON frame — surface an error, keep the socket open.
                await websocket.send_json({"type": "error", "message": "invalid message"})
                continue
            if not isinstance(data, dict):
                await websocket.send_json({"type": "error", "message": "invalid message"})
                continue
            msg_type = data.get("type")

            if msg_type == "join":
                name = data.get("name", "Unknown")
                if room_code not in ROOMS:
                    ROOMS[room_code] = Game(room_code)
                game = ROOMS[room_code]
                try:
                    player = game.rejoin_player(data.get("player_id"), name)
                except ValueError as e:
                    # Room full / game already in progress — tell the client
                    # instead of letting the exception kill the socket.
                    await websocket.send_json({"type": "error", "message": str(e)})
                    continue
                player_id = player.id
                manager.register(room_code, player_id, websocket)
                await broadcast_state(room_code)

            elif msg_type == "start":
                game = ROOMS.get(room_code)
                if game is None or player_id is None:
                    await websocket.send_json(
                        {"type": "error", "message": "Not in a game"}
                    )
                    continue
                if not game.is_host(player_id):
                    await websocket.send_json(
                        {"type": "error", "message": "Only host can start"}
                    )
                    continue
                try:
                    game.start()
                    await broadcast_state(room_code)
                    arm_action_timer(room_code)
                except ValueError as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

            elif msg_type == "action":
                game = ROOMS.get(room_code)
                if game is None or player_id is None:
                    await websocket.send_json(
                        {"type": "error", "message": "Not in a game"}
                    )
                    continue
                try:
                    action_type = ActionType(data.get("action_type"))
                except ValueError:
                    await websocket.send_json(
                        {"type": "error", "message": "invalid action_type"}
                    )
                    continue
                try:
                    action = PlayerAction(
                        player_id=player_id,
                        action_type=action_type,
                        target_system=data.get("target_system"),
                        target_crisis_id=data.get("target_crisis_id"),
                        target_player_id=data.get("target_player_id"),
                    )
                    game.submit_action(action)
                except (ValueError, ValidationError) as e:
                    await websocket.send_json({"type": "error", "message": str(e)})
                    continue
                await websocket.send_json({"type": "action_ack"})

            elif msg_type == "resolve":
                game = ROOMS.get(room_code)
                if game is None or player_id is None:
                    continue
                if not game.is_host(player_id):
                    await websocket.send_json(
                        {"type": "error", "message": "Only host can resolve"}
                    )
                    continue
                if time.time() - game.last_resolve_at < RESOLVE_DEBOUNCE_SECONDS:
                    # A double-click or a resolve racing the auto-timer would
                    # otherwise advance a second round instantly. Only reject
                    # when nobody has acted on the fresh round yet — a host
                    # resolving quickly after players submitted is legitimate.
                    if game.actions_since_resolve == 0:
                        await websocket.send_json(
                            {"type": "error", "message": "Round was already resolved"}
                        )
                        continue
                try:
                    game.resolve_round()
                    await broadcast_state(room_code)
                    # If the game is still in progress, arm the next round's
                    # auto-resolve timer. No-op if no deadline was set (game
                    # ended / transitioned to results).
                    arm_action_timer(room_code)
                    maybe_schedule_cleanup(room_code)
                except ValueError as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

            elif msg_type == "debug_set_system" and os.environ.get("DEBUG_MODE"):
                # Test-only hook: directly set a system's HP. Only enabled
                # when DEBUG_MODE env var is set (never in production).
                game = ROOMS.get(room_code)
                if game is None or player_id is None:
                    continue
                sys_name = data.get("system")
                hp = data.get("hp")
                if sys_name in game.get_state().systems:
                    game.get_state().systems[sys_name] = hp
                    await broadcast_state(room_code)
                else:
                    await websocket.send_json(
                        {"type": "error", "message": f"unknown system {sys_name}"}
                    )

            elif msg_type == "debug_down_player" and os.environ.get("DEBUG_MODE"):
                # Test-only hook: down a specific player by name. Only
                # enabled when DEBUG_MODE env var is set.
                game = ROOMS.get(room_code)
                if game is None or player_id is None:
                    continue
                target_name = data.get("name")
                for p in game.get_state().players:
                    if p.name == target_name:
                        p.is_down = True
                await broadcast_state(room_code)

    except WebSocketDisconnect:
        if player_id is not None and manager.disconnect(room_code, player_id, websocket):
            game = ROOMS.get(room_code)
            if game is not None:
                phase = game.state.phase
                if phase == Phase.LOBBY:
                    # No game state to preserve — drop the player entirely so
                    # a reconnect starts fresh (no ghost hogging a slot or
                    # blocking the game). If the host just left, someone must
                    # be able to start the game.
                    if game.get_player(player_id) is not None:
                        game.remove_player(player_id)
                        if not any(p.is_host for p in game.state.players):
                            game.promote_next_host()
                elif phase in (Phase.SURVIVAL, Phase.FINALE):
                    p = game.get_player(player_id)
                    if p is not None:
                        if p.is_host:
                            # Someone must still be able to start/resolve.
                            game.promote_next_host()
                        if not p.is_down:
                            # Spec: disconnect = downed. Record that the down
                            # was caused by the disconnect so a rejoin can
                            # undo it without reviving game-downed players.
                            p.is_down = True
                            p.disconnect_down = True
                await broadcast_state(room_code)
            # Reap empty/stale rooms after a TTL (idempotent).
            asyncio.create_task(schedule_room_cleanup(room_code))


# Mount static SPA in production (built by Dockerfile)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")