from __future__ import annotations

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .game.manager import LobbyManager

app = FastAPI(title="Realtime Guessing Game", version="1.0.0")
manager = LobbyManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="frontend"), name="static")


class PlayerRequest(BaseModel):
    name: str


class StartRequest(BaseModel):
    player_id: str


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse("frontend/index.html")


@app.post("/api/lobbies")
async def create_lobby(payload: PlayerRequest):
    try:
        return await manager.create_lobby(payload.name)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/lobbies/{lobby_id}/join")
async def join_lobby(lobby_id: str, payload: PlayerRequest):
    try:
        return await manager.join_lobby(lobby_id, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/lobbies/{lobby_id}/start")
async def start_round(lobby_id: str, payload: StartRequest):
    try:
        lobby = await manager.start_round(lobby_id, payload.player_id)
        return await manager.serialize_lobby(lobby.lobby_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/lobbies/{lobby_id}")
async def lobby_state(lobby_id: str):
    try:
        return await manager.serialize_lobby(lobby_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/leaderboard/{player_id}")
async def leaderboard(player_id: str):
    return await manager.leaderboard(player_id)


@app.websocket("/ws/lobby/{lobby_id}")
async def lobby_ws(websocket: WebSocket, lobby_id: str):
    player_id = websocket.query_params.get("player_id")
    if not player_id:
        await websocket.close(code=4000)
        return
    try:
        player = await manager.connect(lobby_id, player_id, websocket)
    except ValueError as exc:
        await websocket.close(code=4001)
        return
    try:
        await websocket.send_json(
            {"type": "lobby_state", "payload": await manager.serialize_lobby(lobby_id)}
        )
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "submit_guess":
                guess = data.get("payload", {}).get("guess", "")
                try:
                    result = await manager.submit_guess(lobby_id, player.player_id, guess)
                    await manager.send_personal(lobby_id, player.player_id, result)
                except Exception as exc:
                    await manager.send_personal(
                        lobby_id,
                        player.player_id,
                        {"type": "error", "payload": {"message": str(exc)}},
                    )
            elif msg_type == "start_game":
                try:
                    await manager.start_round(lobby_id, player.player_id)
                except Exception as exc:
                    await manager.send_personal(
                        lobby_id,
                        player.player_id,
                        {"type": "error", "payload": {"message": str(exc)}},
                    )
            else:
                await manager.send_personal(
                    lobby_id,
                    player.player_id,
                    {"type": "error", "payload": {"message": "Unknown message type"}},
                )
    except WebSocketDisconnect:
        await manager.disconnect(lobby_id, player.player_id)

