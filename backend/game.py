import os
import random
import time
import uuid
from models import GameState, Player, Phase, PlayerAction, ActionType, SystemName
from crises import spawn_crises


class Game:
    MIN_PLAYERS = 4
    MAX_PLAYERS = 15

    def __init__(self, room_code: str):
        self.state = GameState(room_code=room_code)
        # Wall-clock time of the last resolve_round() call. The manual
        # resolve handler checks this to reject a resolve that races the
        # auto-timer (or a double-click) — otherwise the fresh round gets
        # resolved instantly and players lose an action window. The auto-timer
        # itself does NOT check it (short-deadline test mode must still
        # advance).
        self.last_resolve_at: float = 0.0
        # Number of actions submitted since the last resolve. A resolve that
        # follows the previous one within the debounce window is only a
        # double-click / timer race if NOBODY has acted on the fresh round
        # yet — a host resolving quickly after players acted is legitimate.
        self.actions_since_resolve: int = 0

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

    def get_player(self, player_id: str) -> Player | None:
        for p in self.state.players:
            if p.id == player_id:
                return p
        return None

    def rejoin_player(self, player_id: str | None, name: str) -> Player:
        """Reclaim a player's slot on reconnect, or join fresh.

        A reconnecting client sends the player_id it received on first join.
        If that player still exists, reuse it (clearing any disconnect-induced
        down) instead of creating a duplicate. If the id is unknown/missing,
        fall through to a normal join (a new player). In a started game the
        fall-through raises ValueError (add_player's lobby guard), which the
        WS handler surfaces to the client instead of letting it crash the
        socket.
        """
        if player_id:
            existing = self.get_player(player_id)
            if existing is not None:
                if existing.disconnect_down:
                    existing.disconnect_down = False
                    existing.is_down = False
                return existing
        return self.add_player(name)

    def remove_player(self, player_id: str) -> None:
        """Drop a player entirely (lobby disconnect — no game state yet)."""
        self.state.players = [p for p in self.state.players if p.id != player_id]

    def promote_next_host(self) -> None:
        """Give host duties to the first remaining non-host player."""
        for p in self.state.players:
            if not p.is_host:
                p.is_host = True
                return

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
        self.state.started_at = time.time()
        self.state.active_crises = spawn_crises(1)
        self._set_action_deadline()

    def _set_action_deadline(self) -> None:
        seconds = float(os.environ.get("ACTION_PHASE_SECONDS", "45"))
        self.state.action_phase_deadline = time.time() + seconds

    def _apply_afk_defaults(self) -> None:
        """Players who didn't submit an action default to BOLSTER on lowest-health system."""
        acted_ids = {a.player_id for a in self.state.pending_actions}
        for player in self.state.players:
            if player.is_down:
                continue
            if player.id not in acted_ids:
                lowest = min(self.state.systems, key=lambda s: self.state.systems[s])
                self.state.pending_actions.append(PlayerAction(
                    player_id=player.id,
                    action_type=ActionType.BOLSTER,
                    target_system=lowest,
                ))

    def _apply_afk_defaults_finale(self) -> None:
        """In finale, AFK players default to RUN."""
        acted_ids = {a.player_id for a in self.state.pending_actions}
        for player in self.state.players:
            if player.is_down:
                continue
            if player.id not in acted_ids:
                self.state.pending_actions.append(PlayerAction(
                    player_id=player.id,
                    action_type=ActionType.RUN,
                ))

    def submit_action(self, action: PlayerAction) -> None:
        if self.state.phase != Phase.SURVIVAL and self.state.phase != Phase.FINALE:
            raise ValueError("can only submit actions during survival or finale")
        # Phase-appropriate action types — reject off-phase actions from
        # modified clients (they'd otherwise silently consume the slot).
        if self.state.phase == Phase.SURVIVAL:
            allowed = (ActionType.FIX, ActionType.BOLSTER, ActionType.REVIVE)
        else:
            allowed = (ActionType.RUN, ActionType.CARRY, ActionType.HOLD)
        if action.action_type not in allowed:
            raise ValueError(f"{action.action_type} is not allowed in {self.state.phase} phase")
        # Downed players can't act.
        player = self.get_player(action.player_id)
        if player is not None and player.is_down:
            raise ValueError("you are down and cannot take an action")
        # Target validation — reject actions that would silently no-op.
        if action.action_type == ActionType.FIX:
            if not action.target_crisis_id:
                raise ValueError("FIX requires a target_crisis_id")
            if not any(c.id == action.target_crisis_id for c in self.state.active_crises):
                raise ValueError("target crisis not found")
        elif action.action_type == ActionType.REVIVE:
            if not action.target_player_id:
                raise ValueError("REVIVE requires a target_player_id")
            target = self.get_player(action.target_player_id)
            if target is None:
                raise ValueError("target player not found")
            if not target.is_down:
                raise ValueError("target player is not down")
        elif action.action_type == ActionType.CARRY:
            if not action.target_player_id:
                raise ValueError("CARRY requires a target_player_id")
            target = self.get_player(action.target_player_id)
            if target is None:
                raise ValueError("target player not found")
            if not target.is_down:
                raise ValueError("target player is not down")
        # Remove any existing action from this player (replace, not duplicate)
        self.state.pending_actions = [
            a for a in self.state.pending_actions
            if a.player_id != action.player_id
        ]
        self.state.pending_actions.append(action)
        self.actions_since_resolve += 1

    def resolve_round(self) -> None:
        self.last_resolve_at = time.time()
        self.actions_since_resolve = 0
        if self.state.phase == Phase.SURVIVAL:
            self._resolve_survival_round()
        elif self.state.phase == Phase.FINALE:
            self._resolve_finale_round()

    def _resolve_survival_round(self) -> None:
        self._apply_afk_defaults()
        actions = self.state.pending_actions
        # Group FIX actions by crisis ID
        fix_groups: dict[str, list[PlayerAction]] = {}
        for a in actions:
            if a.action_type == ActionType.FIX and a.target_crisis_id:
                fix_groups.setdefault(a.target_crisis_id, []).append(a)

        # Determine which crises are fixed
        fixed_crisis_ids: set[str] = set()
        for crisis_id, fixers in fix_groups.items():
            crisis = next((c for c in self.state.active_crises if c.id == crisis_id), None)
            if crisis and len(fixers) >= crisis.crew_required:
                fixed_crisis_ids.add(crisis_id)

        # Apply crisis drains (only for unfixed crises)
        for crisis in self.state.active_crises:
            if crisis.id not in fixed_crisis_ids:
                self.state.systems[crisis.system] -= crisis.drain_rate
                if self.state.systems[crisis.system] < 0:
                    self.state.systems[crisis.system] = 0

        # Apply shields-at-0 degradation
        if self.state.systems[SystemName.SHIELDS] == 0:
            for s in SystemName:
                if s != SystemName.SHIELDS:
                    self.state.systems[s] -= 2
                    if self.state.systems[s] < 0:
                        self.state.systems[s] = 0
            # If shields degradation pushed reactor to 0, end the game
            # immediately — don't wait for the next round's loss check.
            if self.state.systems[SystemName.REACTOR] == 0:
                self._end_game(victory=False)
                return

        # Apply BOLSTER actions
        for a in actions:
            if a.action_type == ActionType.BOLSTER and a.target_system:
                self.state.systems[a.target_system] = min(
                    100, self.state.systems[a.target_system] + 5
                )

        # Apply REVIVE actions
        for a in actions:
            if a.action_type == ActionType.REVIVE and a.target_player_id:
                if self.state.systems[SystemName.MED_BAY] > 0:
                    target = next(
                        (p for p in self.state.players if p.id == a.target_player_id),
                        None
                    )
                    if target and target.is_down:
                        target.is_down = False

        # Down a crew member if life support is at 0
        if self.state.systems[SystemName.LIFE_SUPPORT] == 0:
            standing = [p for p in self.state.players if not p.is_down]
            if standing:
                victim = random.choice(standing)
                victim.is_down = True

        # Check loss conditions
        if self.state.systems[SystemName.REACTOR] == 0:
            self._end_game(victory=False)
            return
        standing = [p for p in self.state.players if not p.is_down]
        if not standing:
            self._end_game(victory=False)
            return

        # Clear pending actions
        self.state.pending_actions = []

        # Advance round
        self.state.round_number += 1
        if self.state.round_number > 10:
            # Transition to finale. Set a FRESH deadline for finale round 1
            # so the timer spawned by the `resolve` handler (or any auto-
            # resolve chain) sees a future timestamp and gives players the
            # full 45s action window. Without this, the stale round-10
            # deadline (now in the past) persists into finale round 1 and
            # the timer skips its sleep, instantly resolving finale round 1
            # with zero action window.
            self.state.phase = Phase.FINALE
            self.state.round_number = 1  # finale round 1
            self.state.active_crises = []
            self.state.collapse_bar = 0
            self._set_action_deadline()
        else:
            self.state.active_crises = spawn_crises(self.state.round_number)
            self._set_action_deadline()

    def _resolve_finale_round(self) -> None:
        self._apply_afk_defaults_finale()
        actions = self.state.pending_actions

        # Apply RUN actions
        for a in actions:
            if a.action_type == ActionType.RUN:
                player = next((p for p in self.state.players if p.id == a.player_id), None)
                if player and not player.is_down:
                    player.escape_track = min(3, player.escape_track + 1)

        # Apply CARRY actions (need 2 carries per downed crewmate to advance +1)
        carry_groups: dict[str, list[PlayerAction]] = {}
        for a in actions:
            if a.action_type == ActionType.CARRY and a.target_player_id:
                carry_groups.setdefault(a.target_player_id, []).append(a)
        for target_id, carriers in carry_groups.items():
            if len(carriers) >= 2:
                target = next((p for p in self.state.players if p.id == target_id), None)
                if target and target.is_down:
                    target.escape_track = min(3, target.escape_track + 1)

        # Apply HOLD actions
        hold_count = sum(1 for a in actions if a.action_type == ActionType.HOLD)
        self.state.collapse_bar = max(0, self.state.collapse_bar + 34 - (hold_count * 15))

        # Check if collapse hit 100%
        if self.state.collapse_bar >= 100:
            # Anyone not at escape_track 3 is lost
            self._end_finale()
            return

        # Check if all crew (standing + downed) reached escape track 3
        all_escaped = all(p.escape_track >= 3 for p in self.state.players)
        if all_escaped and self.state.players:
            self._end_finale()
            return

        # Clear pending actions
        self.state.pending_actions = []

        # Advance finale round
        self.state.round_number += 1
        if self.state.round_number > 3:
            # Finale ended — check who escaped
            self._end_finale()
        else:
            self._set_action_deadline()

    def _end_finale(self) -> None:
        survived = []
        lost = []
        for p in self.state.players:
            if p.escape_track >= 3:
                survived.append(p.id)
            else:
                lost.append(p.id)
        self.state.crew_survived = survived
        self.state.crew_lost = lost
        self.state.victory = len(lost) == 0
        self.state.partial = len(lost) > 0 and len(survived) > 0
        self.state.phase = Phase.RESULTS

    def _end_game(self, victory: bool) -> None:
        self.state.victory = victory
        self.state.partial = False
        if victory:
            self.state.crew_survived = [p.id for p in self.state.players]
            self.state.crew_lost = []
        else:
            self.state.crew_survived = []
            self.state.crew_lost = [p.id for p in self.state.players]
        self.state.phase = Phase.RESULTS
