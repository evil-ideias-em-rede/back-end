const state = {
  sessionId: null,
  step: 0,
  activeAgent: "debate",
  messages: [],
  loading: false,
};

const stepCopy = document.querySelector("#step-copy");
const stepContent = document.querySelector("#step-content");
const history = document.querySelector("#history");
const errorMessage = document.querySelector("#error-message");

const AGENTS = {
  debate: ["Debate", "Constrói uma proposta de debate com argumentos e mediação."],
  generic: ["Genérico", "Cria uma atividade adaptável para o seu contexto."],
  lesson_plan: ["Plano de aula", "Organiza objetivos, etapas, tempo e avaliação."],
  political_leteracy: ["Letramento político", "Desenvolve leitura crítica e participação cidadã."],
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setError(message = "") {
  errorMessage.textContent = message;
  errorMessage.classList.toggle("visible", Boolean(message));
}

function setLoading(loading) {
  state.loading = loading;
  document.querySelectorAll("button").forEach((button) => { button.disabled = loading; });
}

function renderProgress() {
  document.querySelectorAll(".progress-step").forEach((item) => {
    const itemStep = Number(item.dataset.step);
    item.classList.toggle("active", itemStep === state.step);
    item.classList.toggle("done", itemStep < state.step);
  });
}

function renderHistory() {
  if (!state.messages.length) {
    history.innerHTML = '<p class="empty-history">A conversa aparecerá aqui.</p>';
    return;
  }
  history.innerHTML = state.messages.map((message) => `
    <article class="history-item ${message.role}">
      <div class="history-meta"><span>${message.role === "user" ? "Você" : escapeHtml(message.agent_name || "Agente")}</span></div>
      <p class="history-content">${escapeHtml(message.content)}</p>
    </article>
  `).join("");
  history.scrollTop = history.scrollHeight;
}

function stageMessages(agentName) {
  return state.messages.filter((message) => message.agent_name === agentName);
}

function hasAssistantReply(agentName) {
  return stageMessages(agentName).some((message) => message.role === "assistant");
}

function renderConversation(agentName) {
  const messages = stageMessages(agentName);
  if (!messages.length) {
    return '<p class="empty-stage">Comece a conversa quando quiser.</p>';
  }
  return messages.map((message) => `
    <article class="stage-message ${message.role}">
      <span class="stage-message-role">${message.role === "user" ? "Você" : "Agente"}</span>
      <p>${escapeHtml(message.content)}</p>
    </article>
  `).join("");
}

function renderChatStage({ agentName, inputLabel, placeholder, sendLabel, continueLabel }) {
  const canContinue = hasAssistantReply(agentName);
  stepContent.innerHTML = `
    <div class="stage-thread" id="stage-thread">${renderConversation(agentName)}</div>
    <label class="form-label" for="stage-input">${inputLabel}</label>
    <textarea id="stage-input" placeholder="${placeholder}"></textarea>
    <div class="actions">
      ${continueLabel ? `<button class="secondary-button" id="continue-button" type="button" ${canContinue ? "" : "disabled"}>${continueLabel} →</button>` : ""}
      <button class="primary-button" id="send-button" type="button">${sendLabel} ↑</button>
    </div>
    ${continueLabel && !canContinue ? '<p class="continue-hint">Envie pelo menos uma mensagem antes de avançar.</p>' : ""}
  `;

  document.querySelector("#send-button").addEventListener("click", () => sendStageMessage(agentName));
  document.querySelector("#stage-input").addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") sendStageMessage(agentName);
  });
  if (continueLabel) {
    document.querySelector("#continue-button").addEventListener("click", () => {
      state.step += 1;
      renderStep();
    });
  }
}

function renderStep() {
  renderProgress();
  if (state.step === 0) {
    stepCopy.innerHTML = '<h2>Comece pelo brainstorm</h2><p>Converse com o agente e explore a ideia pelo tempo que precisar. Só avance quando você decidir.</p>';
    renderChatStage({
      agentName: "brainstorm",
      inputLabel: "Sua mensagem para o brainstorm",
      placeholder: "Ex.: Quero trabalhar o tema da água com uma turma do ensino fundamental...",
      sendLabel: "Enviar para o brainstorm",
      continueLabel: "Ir para especificação",
    });
  } else if (state.step === 1) {
    stepCopy.innerHTML = '<h2>Agora vamos especificar</h2><p>Continue conversando com o agente de especificação. Quando a ideia estiver clara, avance para escolher o agente final.</p>';
    renderChatStage({
      agentName: "specification",
      inputLabel: "Sua mensagem para a especificação",
      placeholder: "Ex.: Quero que seja adequado para uma turma de 9º ano e dure 50 minutos...",
      sendLabel: "Enviar para a especificação",
      continueLabel: "Escolher agente final",
    });
  } else {
    stepCopy.innerHTML = '<h2>Escolha o agente final</h2><p>Escolha um agente e converse com ele até chegar ao resultado que você quer. Você pode trocar de agente a qualquer momento.</p>';
    const options = Object.entries(AGENTS).map(([value, [name, description]]) => `
      <div class="agent-option">
        <input id="agent-${value}" type="radio" name="agent" value="${value}" ${state.activeAgent === value ? "checked" : ""} />
        <label for="agent-${value}"><strong>${name}</strong><small>${description}</small></label>
      </div>
    `).join("");
    stepContent.innerHTML = `
      <div class="agent-grid">${options}</div>
      <div class="stage-thread final-thread" id="stage-thread">${renderConversation(state.activeAgent)}</div>
      <label class="form-label" for="stage-input">Sua mensagem para o agente</label>
      <textarea id="stage-input" placeholder="Ex.: Ajuste a proposta para incluir uma atividade prática."></textarea>
      <div class="actions"><button class="primary-button" id="send-button" type="button">Enviar mensagem ↑</button></div>
    `;
    document.querySelectorAll('input[name="agent"]').forEach((input) => {
      input.addEventListener("change", (event) => {
        state.activeAgent = event.target.value;
        renderStep();
      });
    });
    document.querySelector("#send-button").addEventListener("click", () => sendStageMessage(state.activeAgent));
    document.querySelector("#stage-input").addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") sendStageMessage(state.activeAgent);
    });
  }
}

async function createSession() {
  const response = await fetch("/api/workflow/sessions", { method: "POST" });
  if (!response.ok) throw new Error("Não foi possível iniciar a sessão.");
  const session = await response.json();
  state.sessionId = session.id;
  state.messages = session.messages;
  state.step = 0;
  state.activeAgent = "debate";
  renderHistory();
  renderStep();
}

async function callAgent(agentName, text) {
  if (!text.trim()) throw new Error("Escreva uma mensagem antes de enviar.");
  setError("");
  setLoading(true);
  const response = await fetch(`/api/workflow/sessions/${state.sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text.trim(), agent_name: agentName }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "O agente não conseguiu responder agora.");
  state.messages.push({ role: "user", content: text.trim(), agent_name: agentName });
  state.messages.push(data.message);
  renderHistory();
  return data.message;
}

async function sendStageMessage(agentName) {
  const input = document.querySelector("#stage-input");
  if (!input) return;
  try {
    await callAgent(agentName, input.value);
    renderStep();
  } catch (error) {
    setError(error.message);
  } finally {
    setLoading(false);
  }
}

document.querySelector("#new-session").addEventListener("click", async () => {
  try { setError(""); await createSession(); }
  catch (error) { setError(error.message); }
});

createSession().catch((error) => setError(error.message));
