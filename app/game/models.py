from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class LobbyStatus(str, enum.Enum):
    WAITING = "waiting"
    RUNNING = "running"
    FINISHED = "finished"


@dataclass
class Player:
    player_id: str
    name: str
    score: int = 0
    round_score: int = 0
    last_guess: Optional[str] = None
    guessed_correctly: bool = False
    can_guess: bool = True


@dataclass
class GameRound:
    secret: str
    started_at: float = field(default_factory=time.time)
    winners: List[str] = field(default_factory=list)
    timer_task: Optional["asyncio.Task[None]"] = None  # type: ignore[name-defined]


@dataclass
class Lobby:
    lobby_id: str
    host_id: str
    players: Dict[str, Player] = field(default_factory=dict)
    status: LobbyStatus = LobbyStatus.WAITING
    round: Optional[GameRound] = None
    pending_newcomers: List[str] = field(default_factory=list)

    def reset_round_state(self) -> None:
        for player in self.players.values():
            player.round_score = 0
            player.last_guess = None
            player.guessed_correctly = False
            player.can_guess = True
        self.round = None
        self.status = LobbyStatus.WAITING


def make_player(name: str) -> Player:
    return Player(player_id=str(uuid.uuid4()), name=name.strip() or "Player")

