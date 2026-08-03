import uuid
from models import GameState, Player, Phase
from crises import spawn_crises


class Game:
    MIN_PLAYERS = 4
    MAX_PLAYERS = 15

    def __init__(self, room_code: str):
        self.state = GameState(room_code=room_code)

    def get_state(self) -> GameState:
        return self.state

    def add_player(self, name: str) -> Player:
        if self.state.phase != Phase.LOBBY:
            raise ValueError("can only add players in lobby phase")
        if len(self.state.players) >= self.MAX_PLAYERS:
            raise ValueError(f"room full (max {self.MAX_PLAYERS} players)")
        is_host = len(self.state.players) == 0
        player = Player(
            id=str(uuid.uuid4())[:8],
            name=name,
            is_host=is_host,
        )
        self.state.players.append(player)
        return player

    def is_host(self, player_id: str) -> bool:
        for p in self.state.players:
            if p.id == player_id:
                return p.is_host
        return False

    def start(self) -> None:
        if self.state.phase != Phase.LOBBY:
            raise ValueError("can only start from lobby phase")
        if len(self.state.players) < self.MIN_PLAYERS:
            raise ValueError(f"minimum {self.MIN_PLAYERS} players required")
        self.state.phase = Phase.SURVIVAL
        self.state.round_number = 1
        self.state.active_crises = spawn_crises(1)