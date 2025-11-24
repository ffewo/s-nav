## Multiplayer 4-Digit Guessing Game

Realtime WebSocket-powered guessing game with FastAPI backend and lightweight vanilla frontend.

### Features

- Lobby creation/join with unique IDs
- Single-round games with 100s timers and live score updates
- Rich scoring (+/- counts, early winner bonuses, clean-miss rewards)
- Global leaderboard (top 3 + personal rank)
- Dockerized for consistent local usage

### Running Locally

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Visit http://localhost:8000 to load the frontend.

### Docker

```bash
docker-compose up --build
```

Backend exposed on port `8000`.

### WebSocket API

- Endpoint: `/ws/lobby/{lobby_id}?player_id=...`
- Message formats:
  - Client → server: `{ "type": "submit_guess", "payload": { "guess": "1234" } }`
    and `{ "type": "start_game" }`
  - Server → client events include `lobby_state`, `game_started`, `timer_update`,
    `score_update`, `game_over`, `guess_result`, `error`.

### REST Helpers

- `POST /api/lobbies` `{ "name": "Ayse" }` → returns lobby & player IDs (host)
- `POST /api/lobbies/{lobby_id}/join` `{ "name": "Mehmet" }`
- `POST /api/lobbies/{lobby_id}/start` `{ "player_id": "<host_id>" }`
- `GET /api/lobbies/{lobby_id}` lobby snapshot
- `GET /api/leaderboard/{player_id}` top 3 + personal rank

### Tests

```bash
pytest
```

### Notes

- Secret numbers use unique digits to ensure challenging clues.
- Scoring constants documented in `app/game/logic.py`.

