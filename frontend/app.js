const state = {
  lobbyId: null,
  playerId: null,
  playerName: null,
  isOwner: false,
  lobby: null,
  ws: null,
  timerIntervalId: null,
};

// DOM referansları
const screenWelcome = document.getElementById("screen-welcome");
const screenLobby = document.getElementById("screen-lobby");

const inputName = document.getElementById("input-name");
const inputLobbyId = document.getElementById("input-lobby-id");
const btnCreateLobby = document.getElementById("btn-create-lobby");
const btnJoinLobby = document.getElementById("btn-join-lobby");
const welcomeError = document.getElementById("welcome-error");

const lblLobbyId = document.getElementById("lbl-lobby-id");
const lblStatus = document.getElementById("lbl-status");
const lblRound = document.getElementById("lbl-round");
const lblTimer = document.getElementById("lbl-timer");
const btnStartGame = document.getElementById("btn-start-game");
const btnShowLeaderboard = document.getElementById("btn-show-leaderboard");
const youInfo = document.getElementById("you-info");

const inputGuess = document.getElementById("input-guess");
const btnSubmitGuess = document.getElementById("btn-submit-guess");
const guessHelp = document.getElementById("guess-help");
const guessError = document.getElementById("guess-error");
const guessResult = document.getElementById("guess-result");

const playersTableBody = document.getElementById("players-table-body");
const logContainer = document.getElementById("log");

// Leaderboard modal
const leaderboardModal = document.getElementById("leaderboard-modal");
const btnCloseLeaderboard = document.getElementById("btn-close-leaderboard");
const leaderboardTop = document.getElementById("leaderboard-top");
const leaderboardMe = document.getElementById("leaderboard-me");

// Ekran değiştirme
function showWelcomeScreen() {
  screenWelcome.classList.add("active");
  screenLobby.classList.remove("active");
}

function showLobbyScreen() {
  screenWelcome.classList.remove("active");
  screenLobby.classList.add("active");
}

// Log
function addLogLine(text) {
  const line = document.createElement("div");
  line.className = "log-line";
  const timestamp = new Date().toLocaleTimeString("tr-TR", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  line.textContent = `[${timestamp}] ${text}`;
  logContainer.appendChild(line);
  logContainer.scrollTop = logContainer.scrollHeight;
}

// Timer
function startTimer(deadline) {
  stopTimer();
  if (!deadline) {
    lblTimer.textContent = "—";
    return;
  }

  function update() {
    const now = Date.now() / 1000;
    let remaining = Math.max(0, Math.floor(deadline - now));
    const m = String(Math.floor(remaining / 60)).padStart(2, "0");
    const s = String(remaining % 60).padStart(2, "0");
    lblTimer.textContent = `${m}:${s}`;
  }

  update();
  state.timerIntervalId = setInterval(update, 1000);
}

function stopTimer() {
  if (state.timerIntervalId !== null) {
    clearInterval(state.timerIntervalId);
    state.timerIntervalId = null;
  }
}

// Lobby render
function renderLobby() {
  const lobby = state.lobby;
  if (!lobby) return;

  lblLobbyId.textContent = lobby.lobby_id;
  lblStatus.textContent =
    lobby.status === "waiting"
      ? "Bekliyor"
      : lobby.status === "running"
      ? "Oynanıyor"
      : "Bitti";

  lblRound.textContent = lobby.round_no || "-";

  if (lobby.status === "running" && lobby.round_deadline) {
    startTimer(lobby.round_deadline);
  } else {
    stopTimer();
    lblTimer.textContent = lobby.status === "finished" ? "00:00" : "—";
  }

  const me = lobby.players.find((p) => p.player_id === state.playerId);
  const roleText = state.isOwner
    ? "Lobi sahibi"
    : me && me.is_spectator
    ? "Seyirci"
    : "Oyuncu";

  youInfo.textContent = `Sen: ${state.playerName} (${roleText}). Lobideki skorun: ${
    me ? me.score : 0
  }`;

  // Start düğmesini sadece owner görsün
  btnStartGame.style.display = state.isOwner ? "inline-block" : "none";
  btnStartGame.disabled = lobby.status !== "waiting";

  // Tahmin input durumu
  let guessDisabled = false;
  let guessHelper = "";

  if (lobby.status !== "running") {
    guessDisabled = true;
    guessHelper =
      lobby.status === "waiting"
        ? "Oyun başlamadı. Owner başlatınca tahmin yapabilirsin."
        : "Oyun bitti. Owner yeni bir oyun başlatana kadar bekleyin.";
  } else if (me && me.is_spectator) {
    guessDisabled = true;
    guessHelper = "Seyircisin. Yeni oyun başlayana kadar tahmin yapamazsın.";
  } else if (me && me.has_solved) {
    guessDisabled = true;
    guessHelper = "Sayiyi bildin! Diğer oyuncuları bekliyorsun.";
  }

  inputGuess.disabled = guessDisabled;
  btnSubmitGuess.disabled = guessDisabled;
  guessHelp.textContent =
    guessHelper ||
    "Oyun başladıktan sonra her turda 1 tahmin yapabilirsin. Hiç rakam tutmazsa bonus puan!";

  // Oyuncu tablosu
  playersTableBody.innerHTML = "";
  lobby.players
    .slice()
    .sort((a, b) => b.score - a.score)
    .forEach((p) => {
      const tr = document.createElement("tr");
      const isMe = p.player_id === state.playerId;

      const tdName = document.createElement("td");
      tdName.textContent = isMe ? `${p.name} (sen)` : p.name;

      const tdRole = document.createElement("td");
      if (p.player_id === lobby.owner_id) {
        tdRole.textContent = "Owner";
      } else if (p.is_spectator) {
        tdRole.textContent = "Seyirci";
      } else {
        tdRole.textContent = "Oyuncu";
      }

      const tdScore = document.createElement("td");
      tdScore.textContent = p.score;

      const tdStatus = document.createElement("td");
      if (p.has_solved) {
        tdStatus.textContent = "Bildi";
      } else if (p.is_spectator) {
        tdStatus.textContent = "—";
      } else {
        tdStatus.textContent = "Oynuyor";
      }

      tr.appendChild(tdName);
      tr.appendChild(tdRole);
      tr.appendChild(tdScore);
      tr.appendChild(tdStatus);
      playersTableBody.appendChild(tr);
    });
}

// WebSocket
function connectWebSocket() {
  if (!state.lobbyId || !state.playerId) return;

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${protocol}://${window.location.host}/ws/lobby/${state.lobbyId}?player_id=${state.playerId}`;
  const ws = new WebSocket(wsUrl);
  state.ws = ws;

  ws.onopen = () => {
    addLogLine("WebSocket bağlantısı kuruldu.");
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    handleWsMessage(msg);
  };

  ws.onclose = () => {
    addLogLine("WebSocket bağlantısı kapandı.");
  };

  ws.onerror = () => {
    addLogLine("WebSocket hatası oluştu.");
  };
}

function sendWsMessage(message) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
  state.ws.send(JSON.stringify(message));
}

function handleWsMessage(msg) {
  const { type, payload } = msg;

  switch (type) {
    case "connected":
      addLogLine(`Lobiye bağlandın (id: ${payload.lobby_id}).`);
      break;

    case "lobby_state":
      state.lobby = payload;
      renderLobby();
      addLogLine("Lobi durumu güncellendi.");
      break;

    case "player_joined":
      addLogLine(`Oyuncu katıldı: ${payload.name} (${payload.is_spectator ? "Seyirci" : "Oyuncu"})`);
      if (state.lobby) {
        state.lobby.players.push({
          player_id: payload.player_id,
          name: payload.name,
          is_spectator: payload.is_spectator,
          score: 0,
          has_solved: false,
        });
        renderLobby();
      }
      break;

    case "round_started":
      if (state.lobby) {
        state.lobby.status = "running";
        state.lobby.round_no = payload.round_no;
        state.lobby.round_deadline = payload.round_deadline;
      }
      addLogLine(`Yeni tur başladı: #${payload.round_no}`);
      renderLobby();
      break;

    case "lobby_update":
      state.lobby = payload;
      renderLobby();
      break;

    case "guess_result":
      showGuessResult(payload);
      break;

    case "game_finished":
      handleGameFinished(payload);
      break;

    case "error":
      handleError(payload);
      break;

    default:
      addLogLine(`Bilinmeyen mesaj tipi alındı: ${type}`);
  }
}

// Tahmin sonucu UI
function showGuessResult(payload) {
  const { guess, plus, minus, bonus_points, score_change, total_score, is_correct } = payload;

  let text = `Tahminin ${guess} → `;
  if (is_correct) {
    text += `TEBRİKLER! Doğru bildin. (+${score_change} puan)`;
    guessResult.className = "guess-result guess-result-good";
  } else if (plus === 0 && minus === 0) {
    text += `Hiç rakam tutmadı. Bonus: +${bonus_points} puan, toplam değişim: +${score_change}`;
    guessResult.className = "guess-result guess-result-bad";
  } else {
    text += `+${plus}, -${minus}, puan değişimi: ${score_change >= 0 ? "+" : ""}${score_change}`;
    guessResult.className = "guess-result guess-result-neutral";
  }
  guessResult.textContent = text;

  addLogLine(text + ` | Yeni skorun: ${total_score}`);

  // inputu temizle
  inputGuess.value = "";
}

// Oyun bitti
function handleGameFinished(payload) {
  stopTimer();

  if (state.lobby) {
    state.lobby.status = "finished";
  }

  let reasonText = "Oyun bitti.";
  if (payload.reason === "all_solved") {
    reasonText = "Lobideki herkes sayıyı bildi, oyun bitti.";
  } else if (payload.reason === "max_rounds") {
    reasonText = "Maksimum tur sayısına ulaşıldı, oyun bitti.";
  } else if (payload.reason === "no_active_players") {
    reasonText = "Aktif oyuncu kalmadı, oyun bitti.";
  }

  addLogLine(`${reasonText} Gizli sayı: ${payload.secret_number}`);

  if (payload.scores && payload.scores.length) {
    const sorted = payload.scores.slice().sort((a, b) => b.score - a.score);
    addLogLine("Final skorlar:");
    sorted.forEach((p, idx) => {
      addLogLine(
        `#${idx + 1} ${p.name} → ${p.score} puan${
          p.player_id === state.playerId ? " (sen)" : ""
        }`
      );
    });
  }

  renderLobby();
}

// Hata mesajı
function handleError(payload) {
  const message = payload?.message || "Bilinmeyen hata";
  guessError.textContent = message;
  addLogLine(`Hata: ${message}`);
}

// HTTP helper
async function postJson(url, data) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    const detail = err?.detail || resp.statusText;
    throw new Error(detail);
  }
  return resp.json();
}

async function getJson(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    const detail = err?.detail || resp.statusText;
    throw new Error(detail);
  }
  return resp.json();
}

// Event listeners

btnCreateLobby.addEventListener("click", async () => {
  welcomeError.textContent = "";
  const name = inputName.value.trim();
  if (!name) {
    welcomeError.textContent = "Lütfen bir kullanıcı adı gir.";
    return;
  }

  try {
    const data = await postJson("/api/lobbies", { name });
    state.playerName = name;
    state.playerId = data.player_id;
    state.lobbyId = data.lobby_id;
    state.isOwner = true;

    showLobbyScreen();
    connectWebSocket();
    addLogLine(`Yeni lobi kuruldu. ID: ${data.lobby_id}`);
  } catch (err) {
    welcomeError.textContent = err.message || "Lobi oluşturulurken hata oluştu.";
  }
});

btnJoinLobby.addEventListener("click", async () => {
  welcomeError.textContent = "";
  const name = inputName.value.trim();
  const lobbyIdRaw = inputLobbyId.value.trim();
  const lobbyId = lobbyIdRaw.toUpperCase();

  if (!name || !lobbyId) {
    welcomeError.textContent = "Kullanıcı adı ve lobi ID gerekli.";
    return;
  }

  try {
    const data = await postJson(`/api/lobbies/${lobbyId}/join`, { name });
    state.playerName = name;
    state.playerId = data.player_id;
    state.lobbyId = data.lobby_id;
    state.isOwner = false;

    showLobbyScreen();
    connectWebSocket();
    addLogLine(`Lobiye katıldın. ID: ${data.lobby_id}`);
  } catch (err) {
    welcomeError.textContent = err.message || "Lobiye katılırken hata oluştu.";
  }
});

btnStartGame.addEventListener("click", () => {
  guessError.textContent = "";
  sendWsMessage({ type: "start_game" });
});

btnSubmitGuess.addEventListener("click", () => {
  guessError.textContent = "";
  const guess = inputGuess.value.trim();

  if (!/^\d{4}$/.test(guess)) {
    guessError.textContent = "Tahmin 4 haneli bir sayı olmalı.";
    return;
  }

  sendWsMessage({
    type: "submit_guess",
    payload: { guess },
  });
});

// Enter ile submit kolaylığı
inputGuess.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    btnSubmitGuess.click();
  }
});

// Leaderboard modal
btnShowLeaderboard.addEventListener("click", async () => {
  if (!state.playerId) return;
  try {
    const data = await getJson(`/api/leaderboard/${state.playerId}`);

    leaderboardTop.innerHTML = "";
    data.top.forEach((p, idx) => {
      const tr = document.createElement("tr");
      const tdRank = document.createElement("td");
      tdRank.textContent = idx + 1;
      const tdName = document.createElement("td");
      tdName.textContent = p.name;
      const tdScore = document.createElement("td");
      tdScore.textContent = p.score;
      tr.appendChild(tdRank);
      tr.appendChild(tdName);
      tr.appendChild(tdScore);
      leaderboardTop.appendChild(tr);
    });

    const me = data.me;
    const rankText =
      me.rank != null ? `Sıran: ${me.rank}` : "Henüz sıralamada değilsin.";
    leaderboardMe.textContent = `${me.name} → Skor: ${me.score}. ${rankText}`;

    leaderboardModal.classList.remove("hidden");
  } catch (err) {
    addLogLine(`Leaderboard alınırken hata: ${err.message}`);
  }
});

btnCloseLeaderboard.addEventListener("click", () => {
  leaderboardModal.classList.add("hidden");
});

// Başlangıç ekranı
showWelcomeScreen();
