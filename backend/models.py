from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional


class SystemName(str, Enum):
    REACTOR = "reactor"
    LIFE_SUPPORT = "life_support"
    MED_BAY = "med_bay"
    HULL = "hull"
    COMMS = "comms"
    SHIELDS = "shields"


class Phase(str, Enum):
    LOBBY = "lobby"
    SURVIVAL = "survival"
    FINALE = "finale"
    RESULTS = "results"


class ActionType(str, Enum):
    FIX = "fix"
    BOLSTER = "bolster"
    REVIVE = "revive"
    RUN = "run"
    CARRY = "carry"
    HOLD = "hold"


class Crisis(BaseModel):
    id: str
    name: str
    description: str
    system: SystemName
    drain_rate: int
    crew_required: int
    tier: int
    weight: int = 10
    name_variants: list[str] = Field(default_factory=list)
    desc_variants: list[str] = Field(default_factory=list)


class Player(BaseModel):
    id: str = ""
    name: str
    is_host: bool = False
    is_down: bool = False
    # True when this player was downed purely because their WebSocket
    # disconnected (spec: disconnect = downed). Cleared on rejoin so a
    # reconnect brings them back without reviving players who were downed
    # by game mechanics (life support / finale).
    disconnect_down: bool = False
    escape_track: int = 0  # 0-3, reaches 3 = safe in pods


class PlayerAction(BaseModel):
    player_id: str
    action_type: ActionType
    target_system: Optional[SystemName] = None
    target_crisis_id: Optional[str] = None
    target_player_id: Optional[str] = None  # CARRY in finale: downed crewmate


class GameState(BaseModel):
    room_code: str
    phase: Phase = Phase.LOBBY
    round_number: int = 0
    systems: dict[SystemName, int] = Field(default_factory=lambda: {
        s: 100 for s in SystemName
    })
    players: list[Player] = Field(default_factory=list)
    active_crises: list[Crisis] = Field(default_factory=list)
    pending_actions: list[PlayerAction] = Field(default_factory=list)
    collapse_bar: int = 0  # 0-100, finale only
    action_phase_deadline: Optional[float] = None  # unix timestamp
    started_at: Optional[float] = None
    crew_survived: list[str] = Field(default_factory=list)  # player IDs
    crew_lost: list[str] = Field(default_factory=list)
    victory: bool = False
    partial: bool = False