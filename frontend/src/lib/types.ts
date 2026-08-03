export type SystemName = 'reactor' | 'life_support' | 'med_bay' | 'hull' | 'comms' | 'shields';

export type Phase = 'lobby' | 'survival' | 'finale' | 'results';

export type ActionType = 'fix' | 'bolster' | 'revive' | 'run' | 'carry' | 'hold';

export interface Crisis {
  id: string;
  name: string;
  description: string;
  system: SystemName;
  drain_rate: number;
  crew_required: number;
  tier: number;
  weight: number;
}

export interface Player {
  id: string;
  name: string;
  is_host: boolean;
  is_down: boolean;
  escape_track: number;
}

export interface PlayerAction {
  player_id: string;
  action_type: ActionType;
  target_system?: SystemName;
  target_crisis_id?: string;
  target_player_id?: string;
}

export interface GameState {
  room_code: string;
  phase: Phase;
  round_number: number;
  systems: Record<SystemName, number>;
  players: Player[];
  active_crises: Crisis[];
  pending_actions: PlayerAction[];
  collapse_bar: number;
  action_phase_deadline: number | null;
  crew_survived: string[];
  crew_lost: string[];
  victory: boolean;
  partial: boolean;
}

export type ServerMessage =
  | { type: 'state'; state: GameState; player_id: string }
  | { type: 'action_ack' }
  | { type: 'error'; message: string };

export type ClientMessage =
  | { type: 'join'; name: string }
  | { type: 'start' }
  | { type: 'action'; action_type: ActionType; target_system?: SystemName; target_crisis_id?: string; target_player_id?: string }
  | { type: 'resolve' };