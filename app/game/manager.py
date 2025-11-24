from __future__ import annotations

import asyncio
import random
import string
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from fastapi import WebSocket

# ---- Oyun sabitleri ----

ROUND_DURATION_SECONDS = 100.0        # tahmin süresi
MAX_ROUNDS = 10                       # güvenlik amaçlı üst limit
NO_MATCH_BONUS_POINTS = 2             # hiçbir rakam tutmazsa bonus
BASE_CORRECT_POINTS = 50              # ilk turda doğru bilene
CORRECT_DECAY_PER_ROUND = 3           # her tur puan kaybı
MIN_CORRECT_POINTS = 10               # doğru bilince asgari puan


# ---- Durum modelleri ----

@dataclass
class PlayerState:
    player_id: str
    name: str
    score: int = 0               # lobideki skor
    is_spectator: bool = False
    has_guessed: bool = False    # bu turda tahmin yaptı mı
    has_solved: bool = False     # sayıyı bildi mi


@dataclass
class LobbyState:
    lobby_id: str
    owner_id: str
    status: str = "waiting"      # waiting | running | finished
    secret_number: Optional[str] = None
    round_no: int = 0
    round_deadline: Optional[float] = None  # epoch timestamp
    players: Dict[str, PlayerState] = field(default_factory=dict)


class LobbyManager:
    """
    In-memory oyun yöneticisi.
    """

    def __init__(self) -> None:
        # lobby_id -> LobbyState
        self.lobbies: Dict[str, LobbyState] = {}
        # lobby_id -> player_id -> WebSocket
        self.connections: Dict[str, Dict[str, WebSocket]] = {}
        # global leaderboard için: player_id -> toplam puan
        self.global_scores: Dict[str, int] = {}
        # player_id -> isim (leaderboard için)
        self.player_names: Dict[str, str] = {}
        # eşzamanlı erişim için basit lock
        self._lock = asyncio.Lock()

    # -------------------------------------------------------------------------
    # Yardımcı generatorlar
    # -------------------------------------------------------------------------

    def _generate_lobby_id(self) -> str:
        while True:
            lobby_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if lobby_id not in self.lobbies:
                return lobby_id

    def _generate_player_id(self) -> str:
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=10))

    def _generate_secret_number(self) -> str:
        # 4 haneli, her hane farklı rakam
        digits = random.sample("0123456789", 4)
        # Başta 0 gelmesini istemiyorsan:
        if digits[0] == "0":
            # 0 olmayan bir rakamla yer değiştir
            for i in range(1, 4):
                if digits[i] != "0":
                    digits[0], digits[i] = digits[i], digits[0]
                    break
        return "".join(digits)

    # -------------------------------------------------------------------------
    # Oyun kuralları: tahmin değerlendirme ve skor hesaplama
    # -------------------------------------------------------------------------

    def _evaluate_guess(self, secret: str, guess: str) -> Tuple[int, int, bool, int]:
        """
        secret ve guess için:
        - plus: doğru rakam & doğru pozisyon
        - minus: doğru rakam & yanlış pozisyon
        - is_correct: tamamını bildi mi
        - bonus_points: hiç rakam tutmuyorsa NO_MATCH_BONUS_POINTS, yoksa 0
        """
        if len(guess) != 4 or not guess.isdigit():
            raise ValueError("Tahmin 4 haneli bir sayı olmalı.")
        plus = sum(1 for s, g in zip(secret, guess) if s == g)
        minus = sum(1 for g in guess if g in secret) - plus
        is_correct = plus == 4
        bonus_points = NO_MATCH_BONUS_POINTS if plus == 0 and minus == 0 else 0
        return plus, minus, is_correct, bonus_points

    def _correct_points_for_round(self, round_no: int) -> int:
        """
        Erken bilen daha çok puan alır:
        1. tur: BASE_CORRECT_POINTS
        2. tur: BASE_CORRECT_POINTS - CORRECT_DECAY_PER_ROUND
        ...
        Alt sınır MIN_CORRECT_POINTS
        """
        raw = BASE_CORRECT_POINTS - (round_no - 1) * CORRECT_DECAY_PER_ROUND
        return max(MIN_CORRECT_POINTS, raw)

    # -------------------------------------------------------------------------
    # Public API: HTTP endpointlerinin çağırdığı metodlar
    # -------------------------------------------------------------------------

    async def create_lobby(self, player_name: str) -> dict:
        """
        Yeni bir lobi kur ve ilk oyuncuyu owner olarak ekle.
        """
        async with self._lock:
            lobby_id = self._generate_lobby_id()
            player_id = self._generate_player_id()

            player = PlayerState(player_id=player_id, name=player_name)
            lobby = LobbyState(
                lobby_id=lobby_id,
                owner_id=player_id,
            )
            lobby.players[player_id] = player

            self.lobbies[lobby_id] = lobby
            self.connections.setdefault(lobby_id, {})

            # global leaderboard için
            self.global_scores.setdefault(player_id, 0)
            self.player_names[player_id] = player_name

            return {
                "lobby_id": lobby_id,
                "player_id": player_id,
                "player_name": player_name,
                "role": "owner",
            }

    async def join_lobby(self, lobby_id: str, player_name: str) -> dict:
        """
        Var olan bir lobiye katıl.
        Oyun başlamışsa spectator olarak eklenir.
        """
        async with self._lock:
            lobby = self.lobbies.get(lobby_id)
            if not lobby:
                raise ValueError("Lobi bulunamadı.")

            player_id = self._generate_player_id()
            is_spectator = lobby.status != "waiting"

            player = PlayerState(
                player_id=player_id,
                name=player_name,
                is_spectator=is_spectator,
            )
            lobby.players[player_id] = player

            self.global_scores.setdefault(player_id, 0)
            self.player_names[player_id] = player_name

            # lobideki herkese "player_joined" broadcast et
            await self.broadcast(
                lobby_id,
                {
                    "type": "player_joined",
                    "payload": {
                        "player_id": player_id,
                        "name": player_name,
                        "is_spectator": is_spectator,
                    },
                },
            )

            return {
                "lobby_id": lobby_id,
                "player_id": player_id,
                "player_name": player_name,
                "role": "spectator" if is_spectator else "player",
            }

    async def start_round(self, lobby_id: str, player_id: str) -> LobbyState:
        """
        Owner ilk oyunu başlatır.
        Aynı endpoint tekrar çağrılırsa hata.
        """
        async with self._lock:
            lobby = self.lobbies.get(lobby_id)
            if not lobby:
                raise ValueError("Lobi bulunamadı.")

            if lobby.owner_id != player_id:
                raise PermissionError("Sadece lobi sahibi oyunu başlatabilir.")

            if lobby.status == "running":
                raise RuntimeError("Oyun zaten başlamış.")
            if lobby.status == "finished":
                raise RuntimeError("Bu lobi için oyun tamamlanmış.")

            # yeni gizli sayıyı üret
            lobby.secret_number = self._generate_secret_number()
            lobby.status = "running"
            lobby.round_no = 1
            lobby.round_deadline = time.time() + ROUND_DURATION_SECONDS

            # tüm oyuncular için tur state reset
            for p in lobby.players.values():
                if not p.is_spectator:
                    p.has_guessed = False
                    p.has_solved = False
                    p.score = 0  # lobideki skor sıfırlanıyor

            await self.broadcast(
                lobby_id,
                {
                    "type": "round_started",
                    "payload": {
                        "round_no": lobby.round_no,
                        "round_deadline": lobby.round_deadline,
                    },
                },
            )
            return lobby

    async def serialize_lobby(self, lobby_id: str) -> dict:
        """
        Lobi durumunu frontende JSON olarak döndür.
        """
        lobby = self.lobbies.get(lobby_id)
        if not lobby:
            raise ValueError("Lobi bulunamadı.")

        return {
            "lobby_id": lobby.lobby_id,
            "status": lobby.status,
            "round_no": lobby.round_no,
            "round_deadline": lobby.round_deadline,
            "owner_id": lobby.owner_id,
            "players": [
                {
                    "player_id": p.player_id,
                    "name": p.name,
                    "score": p.score,
                    "is_spectator": p.is_spectator,
                    "has_solved": p.has_solved,
                }
                for p in lobby.players.values()
            ],
        }

    async def leaderboard(self, player_id: str) -> dict:
        """
        Global leaderboard:
        - ilk 3 oyuncu
        - istenen oyuncunun kendi sırası ve skoru
        """
        # in-memory olduğundan lock'a gerek yok ama yine de güvenli olsun
        async with self._lock:
            # skorları büyükten küçüğe sırala
            sorted_players = sorted(
                self.global_scores.items(), key=lambda kv: kv[1], reverse=True
            )

            top = []
            for pid, score in sorted_players[:3]:
                top.append(
                    {
                        "player_id": pid,
                        "name": self.player_names.get(pid, "Unknown"),
                        "score": score,
                    }
                )

            # oyuncunun kendi sırası
            me_rank = None
            me_score = self.global_scores.get(player_id, 0)
            for idx, (pid, _) in enumerate(sorted_players, start=1):
                if pid == player_id:
                    me_rank = idx
                    break

            me = {
                "player_id": player_id,
                "name": self.player_names.get(player_id, "Unknown"),
                "score": me_score,
                "rank": me_rank,
            }

            return {"top": top, "me": me}

    # -------------------------------------------------------------------------
    # WebSocket yönetimi
    # -------------------------------------------------------------------------

    async def connect(self, lobby_id: str, player_id: str, websocket: WebSocket) -> PlayerState:
        """
        WebSocket bağlantısı kuran oyuncuyu kaydet.
        """
        async with self._lock:
            lobby = self.lobbies.get(lobby_id)
            if not lobby:
                raise ValueError("Lobi bulunamadı.")

            player = lobby.players.get(player_id)
            if not player:
                raise ValueError("Oyuncu bu lobide değil.")

            self.connections.setdefault(lobby_id, {})
            self.connections[lobby_id][player_id] = websocket

            # basit bir "connected" mesajı da gönderebiliriz (zorunlu değil)
            await websocket.send_json(
                {
                    "type": "connected",
                    "payload": {
                        "lobby_id": lobby_id,
                        "player_id": player_id,
                        "name": player.name,
                    },
                }
            )

            return player

    async def disconnect(self, lobby_id: str, player_id: str) -> None:
        async with self._lock:
            lobby_conns = self.connections.get(lobby_id)
            if lobby_conns and player_id in lobby_conns:
                del lobby_conns[player_id]

    async def send_personal(self, lobby_id: str, player_id: str, message: dict) -> None:
        ws = self.connections.get(lobby_id, {}).get(player_id)
        if ws:
            await ws.send_json(message)

    async def broadcast(self, lobby_id: str, message: dict) -> None:
        conns = self.connections.get(lobby_id, {})
        # tüm bağlantılara paralel gönder
        await asyncio.gather(
            *[
                ws.send_json(message)
                for ws in conns.values()
                if ws.application_state.value == 1  # CONNECTED
            ],
            return_exceptions=True,
        )

    # -------------------------------------------------------------------------
    # Tahmin işleme
    # -------------------------------------------------------------------------

    async def submit_guess(self, lobby_id: str, player_id: str, guess: str) -> dict:
        """
        Bir oyuncunun tahminini al, sonucu hesapla, skorları güncelle.
        Bu metod sonucunu sadece ilgili oyuncuya döndürüyor; round bitiş
        ve game over kontrolleri ayrıca broadcast ediliyor.
        """
        async with self._lock:
            lobby = self.lobbies.get(lobby_id)
            if not lobby:
                raise ValueError("Lobi bulunamadı.")

            player = lobby.players.get(player_id)
            if not player:
                raise ValueError("Oyuncu bulunamadı.")

            if player.is_spectator:
                raise ValueError("Seyirciler tahmin yapamaz. Bir sonraki oyunu beklemelisin.")

            if lobby.status != "running":
                raise ValueError("Oyun şu anda çalışmıyor.")

            if lobby.secret_number is None:
                raise RuntimeError("Gizli sayı henüz oluşturulmadı.")

            now = time.time()
            if lobby.round_deadline and now > lobby.round_deadline:
                raise RuntimeError("Bu turun süresi doldu.")

            if player.has_guessed:
                raise ValueError("Bu tur için zaten tahmin yaptın.")

            # tahmini değerlendir
            plus, minus, is_correct, bonus_points = self._evaluate_guess(
                lobby.secret_number, guess
            )

            # skor hesapla
            score_change = 0
            if is_correct and not player.has_solved:
                correct_points = self._correct_points_for_round(lobby.round_no)
                score_change += correct_points
                player.has_solved = True

            if bonus_points:
                score_change += bonus_points

            player.score += score_change

            # global leaderboard güncelle
            self.global_scores[player_id] = self.global_scores.get(player_id, 0) + score_change

            player.has_guessed = True

            # diğer oyuncular için anlık skor/round durumu broadcast
            await self.broadcast(
                lobby_id,
                {
                    "type": "lobby_update",
                    "payload": await self.serialize_lobby(lobby_id),
                },
            )

            # round veya oyunun bitip bitmediğini kontrol et
            await self._check_round_or_game_end(lobby)

            # sadece bu oyuncuya gidecek cevap
            return {
                "type": "guess_result",
                "payload": {
                    "round_no": lobby.round_no,
                    "guess": guess,
                    "plus": plus,
                    "minus": minus,
                    "bonus_points": bonus_points,
                    "score_change": score_change,
                    "total_score": player.score,
                    "is_correct": is_correct,
                },
            }

    async def _check_round_or_game_end(self, lobby: LobbyState) -> None:
        """
        Her tahmin sonrası:
        - herkes bildiyse veya max ronde geldiysek oyunu bitir
        - aktif tüm oyuncular tahmin yaptıysa bir sonraki tura geç
        """
        # Oyun zaten bitmişse dokunma
        if lobby.status != "running":
            return

        players = list(lobby.players.values())
        active_players = [p for p in players if not p.is_spectator]

        # aktif oyuncu yoksa oyunu bitirelim
        if not active_players:
            lobby.status = "finished"
            await self.broadcast(
                lobby.lobby_id,
                {
                    "type": "game_finished",
                    "payload": {
                        "reason": "no_active_players",
                        "secret_number": lobby.secret_number,
                        "scores": [
                            {
                                "player_id": p.player_id,
                                "name": p.name,
                                "score": p.score,
                            }
                            for p in players
                        ],
                    },
                },
            )
            return

        # herkes bildiyse oyun biter
        if all(p.has_solved for p in active_players) or lobby.round_no >= MAX_ROUNDS:
            lobby.status = "finished"
            await self.broadcast(
                lobby.lobby_id,
                {
                    "type": "game_finished",
                    "payload": {
                        "reason": "all_solved"
                        if all(p.has_solved for p in active_players)
                        else "max_rounds",
                        "secret_number": lobby.secret_number,
                        "scores": [
                            {
                                "player_id": p.player_id,
                                "name": p.name,
                                "score": p.score,
                            }
                            for p in players
                        ],
                    },
                },
            )
            return

        # tüm aktif oyuncular bu turda tahmin yaptıysa, yeni tura geç
        if all(p.has_guessed or p.has_solved for p in active_players):
            lobby.round_no += 1
            lobby.round_deadline = time.time() + ROUND_DURATION_SECONDS
            # yeni tur için has_guessed reset
            for p in active_players:
                if not p.has_solved:
                    p.has_guessed = False

            await self.broadcast(
                lobby.lobby_id,
                {
                    "type": "round_started",
                    "payload": {
                        "round_no": lobby.round_no,
                        "round_deadline": lobby.round_deadline,
                    },
                },
            )
