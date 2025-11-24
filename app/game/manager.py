from __future__ import annotations

import asyncio
import time
from typing import Dict, List

from fastapi import WebSocket

from .logic import (
    ROUND_DURATION_SECONDS,
    TIMER_TICK_SECONDS,
    calculate_guess_score,
    evaluate_guess,
    generate_secret,
)
from .models import GameRound, Lobby, LobbyStatus, Player, make_player


class LobbyManager:
    """
    Keeps all lobby state in-memory. For production, swap with redis/db layer.
    """

    def __init__(self) -> None:
        self.lobbies: Dict[str, Lobby] = {}
        self.connections: Dict[str, Dict[str, WebSocket]] = {}
        self.global_scores: Dict[str, Dict[str, str | int]] = {}
        self._lock = asyncio.Lock()

    async def create_lobby(self, host_name: str) -> Dict[str, str]:
        player = make_player(host_name)
        lobby_id = player.player_id[:6]
        lobby = Lobby(lobby_id=lobby_id, host_id=player.player_id)
        lobby.players[player.player_id] = player
        self.lobbies[lobby_id] = lobby
        self.connections[lobby_id] = {}
        self.global_scores[player.player_id] = {"name": player.name, "score": 0}
        return {"lobby_id": lobby_id, "player_id": player.player_id}

    async def join_lobby(self, lobby_id: str, player_name: str) -> Dict[str, str]:
        lobby = self.lobbies.get(lobby_id)
        if not lobby:
            raise ValueError("Lobby does not exist")
        player = make_player(player_name)
        if lobby.status == LobbyStatus.RUNNING:
            player.can_guess = False  # must wait for next round
        lobby.players[player.player_id] = player
        self.global_scores[player.player_id] = {"name": player.name, "score": 0}
        return {"lobby_id": lobby_id, "player_id": player.player_id}

    async def connect(self, lobby_id: str, player_id: str, websocket: WebSocket) -> Player:
        lobby = self.lobbies.get(lobby_id)
        if not lobby:
            raise ValueError("Lobby not found")
        player = lobby.players.get(player_id)
        if not player:
            raise ValueError("Player not registered")
        await websocket.accept()
        self.connections.setdefault(lobby_id, {})[player_id] = websocket
        return player

    async def disconnect(self, lobby_id: str, player_id: str) -> None:
        ws_map = self.connections.get(lobby_id)
        if ws_map and player_id in ws_map:
            ws_map.pop(player_id, None)

    async def start_round(self, lobby_id: str, requester_id: str) -> Lobby:
        lobby = self.lobbies.get(lobby_id)
        if not lobby:
            raise ValueError("Lobby missing")
        if requester_id != lobby.host_id:
            raise PermissionError("Only host can start a round")
        if lobby.status == LobbyStatus.RUNNING:
            raise RuntimeError("Round already running")

        lobby.reset_round_state()
        lobby.status = LobbyStatus.RUNNING
        secret = generate_secret()
        lobby.round = GameRound(secret=secret)

        # Newcomers that arrived mid-round can now guess
        for pid in lobby.pending_newcomers:
            player = lobby.players.get(pid)
            if player:
                player.can_guess = True
        lobby.pending_newcomers.clear()

        if lobby.round.timer_task:
            lobby.round.timer_task.cancel()
        lobby.round.timer_task = asyncio.create_task(self._run_timer(lobby_id))
        await self.broadcast_state(lobby_id, "game_started", await self.serialize_lobby(lobby_id))
        return lobby

    async def submit_guess(self, lobby_id: str, player_id: str, guess: str) -> Dict[str, str | int | bool]:
        lobby = self.lobbies.get(lobby_id)
        if not lobby or lobby.status != LobbyStatus.RUNNING or not lobby.round:
            raise RuntimeError("Round not running")
        player = lobby.players.get(player_id)
        if not player:
            raise ValueError("Player missing")
        if not player.can_guess:
            raise PermissionError("Wait for the next round to guess")
        if player.guessed_correctly:
            raise RuntimeError("Already solved this round")

        guess = guess.strip()
        if len(guess) != 4 or not guess.isdigit():
            raise ValueError("Guess must be a 4-digit number")

        metrics = evaluate_guess(lobby.round.secret, guess)
        player.last_guess = guess
        position = None
        if guess == lobby.round.secret:
            player.guessed_correctly = True
            lobby.round.winners.append(player_id)
            position = len(lobby.round.winners)
        delta = calculate_guess_score(position, metrics["plus"], metrics["minus"], metrics["is_clean_miss"])
        player.round_score += delta
        player.score += delta
        self.global_scores[player_id]["score"] = player.score  # type: ignore[index]

        await self.broadcast_state(lobby_id, "score_update", await self.serialize_lobby(lobby_id))

        if self._round_should_end(lobby):
            await self.finish_round(lobby_id)

        return {
            "type": "guess_result",
            "payload": {
                "plus": metrics["plus"],
                "minus": metrics["minus"],
                "is_clean_miss": metrics["is_clean_miss"],
                "delta": delta,
                "total_score": player.score,
                "position": position,
            },
        }

    def _round_should_end(self, lobby: Lobby) -> bool:
        if not lobby.round:
            return False
        everyone_done = all(p.guessed_correctly for p in lobby.players.values())
        timer_elapsed = (time.time() - lobby.round.started_at) >= ROUND_DURATION_SECONDS
        return everyone_done or timer_elapsed

    async def finish_round(self, lobby_id: str) -> None:
        lobby = self.lobbies.get(lobby_id)
        if not lobby or not lobby.round:
            return
        secret_value = lobby.round.secret
        lobby.status = LobbyStatus.FINISHED
        if lobby.round.timer_task:
            lobby.round.timer_task.cancel()
        lobby.round = None
        payload = await self.serialize_lobby(lobby_id)
        payload["revealed_secret"] = secret_value
        await self.broadcast_state(lobby_id, "game_over", payload)

    async def serialize_lobby(self, lobby_id: str) -> Dict[str, object]:
        lobby = self.lobbies.get(lobby_id)
        if not lobby:
            raise ValueError("Lobby not found")
        remaining = 0
        if lobby.round:
            elapsed = time.time() - lobby.round.started_at
            remaining = max(0, ROUND_DURATION_SECONDS - int(elapsed))
        return {
            "lobby_id": lobby.lobby_id,
            "status": lobby.status.value,
            "players": [
                {
                    "player_id": p.player_id,
                    "name": p.name,
                    "score": p.score,
                    "round_score": p.round_score,
                    "last_guess": p.last_guess,
                    "guessed_correctly": p.guessed_correctly,
                    "can_guess": p.can_guess,
                }
                for p in lobby.players.values()
            ],
            "host_id": lobby.host_id,
            "remaining_seconds": remaining,
        }

    async def broadcast_state(self, lobby_id: str, message_type: str, payload: Dict[str, object]) -> None:
        ws_map = self.connections.get(lobby_id, {})
        dead: List[str] = []
        for pid, ws in ws_map.items():
            try:
                await ws.send_json({"type": message_type, "payload": payload})
            except Exception:
                dead.append(pid)
        for pid in dead:
            ws_map.pop(pid, None)

    async def send_personal(self, lobby_id: str, player_id: str, message: Dict[str, object]) -> None:
        ws = self.connections.get(lobby_id, {}).get(player_id)
        if ws:
            await ws.send_json(message)

    async def _run_timer(self, lobby_id: str) -> None:
        try:
            while True:
                lobby = self.lobbies.get(lobby_id)
                if not lobby or not lobby.round or lobby.status != LobbyStatus.RUNNING:
                    return
                remaining = ROUND_DURATION_SECONDS - int(time.time() - lobby.round.started_at)
                if remaining <= 0:
                    await self.finish_round(lobby_id)
                    return
                await self.broadcast_state(
                    lobby_id,
                    "timer_update",
                    {"lobby_id": lobby_id, "remaining_seconds": remaining},
                )
                await asyncio.sleep(TIMER_TICK_SECONDS)
        except asyncio.CancelledError:
            return

    async def leaderboard(self, player_id: str | None = None) -> Dict[str, object]:
        ordered = sorted(
            self.global_scores.items(),
            key=lambda kv: kv[1]["score"],
            reverse=True,
        )
        top_entries = [
            {"player_id": pid, "name": data["name"], "score": data["score"]}
            for pid, data in ordered[:3]
        ]
        rank_info = None
        if player_id:
            for idx, (pid, data) in enumerate(ordered, start=1):
                if pid == player_id:
                    rank_info = {"rank": idx, "name": data["name"], "score": data["score"]}
                    break
        return {"top": top_entries, "self": rank_info}

