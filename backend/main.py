import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from game import Game
from models import PlayerAction, ActionType

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
                except ValueError as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        if player_id is not None:
            manager.disconnect(room_code, player_id)


# Mount static SPA in production (built by Dockerfile)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")