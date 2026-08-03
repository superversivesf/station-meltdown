import asyncio
import os
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from game import Game
from models import PlayerAction, ActionType, Phase

app = FastAPI()

# In-memory registry of active games: room_code -> Game
ROOMS: dict[str, Game] = {}


class ConnectionManager:
    """Tracks WebSocket connections per room, keyed by player_id."""

    def __init__(self) -> None:
        self.connections: dict[str, dict[str, WebSocket]] = {}

    def register(self, room_code: str, player_id: str, websocket: WebSocket) -> None:
        self.connections.setdefault(room_code, {})[player_id] = websocket

    def disconnect(self, room_code: str, player_id: str) -> None:
        room = self.connections.get(room_code)
        if room is None:
            return
        room.pop(player_id, None)
        if not room:
            del self.connections[room_code]

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
            manager.disconnect(room_code, player_id)


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
    asyncio.create_task(start_action_timer(room_code))


@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str):
    room_code = room_code.upper()
    player_id: str | None = None
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "join":
                name = data.get("name", "Unknown")
                if room_code not in ROOMS:
                    ROOMS[room_code] = Game(room_code)
                game = ROOMS[room_code]
                player = game.add_player(name)
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
                    asyncio.create_task(start_action_timer(room_code))
                except ValueError as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

            elif msg_type == "action":
                game = ROOMS.get(room_code)
                if game is None or player_id is None:
                    await websocket.send_json(
                        {"type": "error", "message": "Not in a game"}
                    )
                    continue
                action = PlayerAction(
                    player_id=player_id,
                    action_type=ActionType(data["action_type"]),
                    target_system=data.get("target_system"),
                    target_crisis_id=data.get("target_crisis_id"),
                    target_player_id=data.get("target_player_id"),
                )
                game.submit_action(action)
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
                try:
                    game.resolve_round()
                    await broadcast_state(room_code)
                    # If the game is still in progress, arm the next round's
                    # auto-resolve timer. No-op if no deadline was set (game
                    # ended / transitioned to results).
                    asyncio.create_task(start_action_timer(room_code))
                except ValueError as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        if player_id is not None:
            manager.disconnect(room_code, player_id)


# Mount static SPA in production (built by Dockerfile)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")