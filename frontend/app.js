const state = {
  lobbyId: null,
  playerId: null,
  hostId: null,
  ws: null,
};

const els = {
  createName: document.getElementById("create-name"),
  createBtn: document.getElementById("create-btn"),
  joinName: document.getElementById("join-name"),
  joinLobby: document.getElementById("join-lobby"),
  joinBtn: document.getElementById("join-btn"),
  sessionInfo: document.getElementById("session-info"),
  lobbyStatus: document.getElementById("lobby-status"),
  timer: document.getElementById("timer"),
  secretDisplay: document.getElementById("secret-display"),
  guessInput: document.getElementById("guess-input"),
  guessBtn: document.getElementById("guess-btn"),
  startBtn: document.getElementById("start-btn"),
  feedback: document.getElementById("feedback"),
  roundInfo: document.getElementById("round-info"),
  scoreBody: document.getElementById("score-body"),
  leaderTop: document.getElementById("leader-top"),
  leaderSelf: document.getElementById("leader-self"),
};

els.createBtn.addEventListener("click", async () => {
  if (!els.createName.value.trim()) return;
  const res = await fetch("/api/lobbies", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: els.createName.value }),
  });
  const data = await res.json();
  applySession(data);
});

els.joinBtn.addEventListener("click", async () => {
  if (!els.joinLobby.value.trim() || !els.joinName.value.trim()) return;
  const res = await fetch(`/api/lobbies/${els.joinLobby.value.trim()}/join`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: els.joinName.value }),
  });
  if (!res.ok) {
    const error = await res.json();
    alert(error.detail || "Unable to join lobby");
    return;
  }
  const data = await res.json();
  applySession(data);
});

els.guessBtn.addEventListener("click", () => {
  const guess = els.guessInput.value.trim();
  if (!state.ws || guess.length !== 4 || !/^[0-9]{4}$/.test(guess)) {
    return;
  }
  state.ws.send(JSON.stringify({ type: "submit_guess", payload: { guess } }));
  els.guessInput.value = "";
});

els.startBtn.addEventListener("click", () => {
  if (!state.ws) return;
  state.ws.send(JSON.stringify({ type: "start_game" }));
});

function applySession({ lobby_id, player_id }) {
  state.lobbyId = lobby_id;
  state.playerId = player_id;
  els.sessionInfo.classList.remove("hidden");
  els.sessionInfo.innerText = `Lobby ${lobby_id} • Player ID ${player_id}`;
  connectWs();
  refreshLeaderboard();
}

function connectWs() {
  if (!state.lobbyId || !state.playerId) return;
  if (state.ws) state.ws.close();

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  state.ws = new WebSocket(
    `${protocol}://${window.location.host}/ws/lobby/${state.lobbyId}?player_id=${state.playerId}`
  );

  state.ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    switch (msg.type) {
      case "lobby_state":
      case "game_started":
      case "score_update":
      case "game_over":
        updateLobby(msg.payload);
        break;
      case "timer_update":
        els.timer.innerText = msg.payload.remaining_seconds;
        break;
      case "guess_result":
        showFeedback(msg.payload);
        refreshLeaderboard();
        break;
      case "error":
        alert(msg.payload.message);
        break;
    }
  };

  state.ws.onclose = () => {
    state.ws = null;
  };
}

function updateLobby(payload) {
  state.hostId = payload.host_id;
  els.lobbyStatus.innerText = `Status: ${payload.status}`;
  els.timer.innerText = payload.status === "running" ? payload.remaining_seconds ?? "--" : "--";

  const rows = payload.players
    .map(
      (p, idx) => `
        <tr>
          <td>${idx + 1}</td>
          <td>${p.name}${p.player_id === state.hostId ? " ★" : ""}</td>
          <td>${p.score}</td>
          <td>${p.round_score}</td>
          <td>${p.guessed_correctly ? "Solved" : p.can_guess ? "Ready" : "Spectator"}</td>
        </tr>
      `
    )
    .join("");
  els.scoreBody.innerHTML = rows;

  const me = payload.players.find((p) => p.player_id === state.playerId);
  const canGuess = payload.status === "running" && me?.can_guess && !me?.guessed_correctly;
  els.guessBtn.disabled = !canGuess;
  els.guessInput.disabled = !canGuess;
  els.startBtn.disabled = !(state.playerId === state.hostId && payload.status !== "running");

  if (payload.revealed_secret) {
    els.secretDisplay.innerText = payload.revealed_secret;
    els.roundInfo.innerText = `Round tamamlandı. Sayı ${payload.revealed_secret}. Yeni round için hostu bekleyin.`;
  } else if (payload.status === "running") {
    els.secretDisplay.innerText = "????";
    els.roundInfo.innerText = "Tahmin penceresi açık.";
  } else if (payload.status === "waiting") {
    els.secretDisplay.innerText = "????";
    els.roundInfo.innerText = "Host yeni round başlatabilir.";
  } else {
    els.secretDisplay.innerText = "????";
    els.roundInfo.innerText = "";
  }
}

function showFeedback(payload) {
  const parts = [];
  parts.push(`+${payload.plus} / -${payload.minus}`);
  if (payload.is_clean_miss) parts.push("Bonus +5");
  if (payload.position) parts.push(`Position ${payload.position}`);
  parts.push(`Δ ${payload.delta}`);
  els.feedback.innerText = parts.join(" • ");
}

async function refreshLeaderboard() {
  if (!state.playerId) return;
  const res = await fetch(`/api/leaderboard/${state.playerId}`);
  const data = await res.json();
  els.leaderTop.innerHTML = data.top
    .map((entry) => `<li>${entry.name}: ${entry.score}</li>`)
    .join("");
  if (data.self) {
    els.leaderSelf.innerText = `${data.self.name}, you are #${data.self.rank} with ${data.self.score} pts`;
  } else {
    els.leaderSelf.innerText = "";
  }
}

