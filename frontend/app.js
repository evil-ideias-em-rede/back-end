const state = {
  sessionId: null,
  step: 0,
  activeAgent: "debate",
  messages: [],
  loading: false,
  advanceFeedback: "",
  streamingMessage: null,
  artifacts: {},
  planningNeedsConversation: false,
  previousSessions: [],
};

const stepCopy = document.querySelector("#step-copy");
const stepContent = document.querySelector("#step-content");
const errorMessage = document.querySelector("#error-message");
const agentFeedback = document.querySelector("#agent-feedback");
const htmlPreviewCard = document.querySelector("#html-preview-card");
const htmlPreview = document.querySelector("#html-preview");
const htmlOpenLink = document.querySelector("#html-open-link");
const workspace = document.querySelector(".workspace");
const htmlEditPanel = document.querySelector("#html-edit-panel");
const selectedHtmlTarget = document.querySelector("#selected-html-target");
const htmlEditInput = document.querySelector("#html-edit-input");
const htmlEditSubmit = document.querySelector("#html-edit-submit");
const htmlAttachButton = document.querySelector("#html-attach-button");
const htmlFileInput = document.querySelector("#html-file-input");
const htmlFileName = document.querySelector("#html-file-name");
const generatePdfButton = document.querySelector("#generate-pdf-button");
const documentPreviewCard = document.querySelector("#document-preview-card");
const documentPreviewTitle = document.querySelector("#document-preview-title");
const documentPreviewContent = document.querySelector("#document-preview-content");
const audienciaDrawer = document.querySelector("#audiencia-drawer");
const audienciaBackdrop = document.querySelector("#audiencia-backdrop");
const audienciaDrawerTitle = document.querySelector("#audiencia-drawer-title");
const audienciaDrawerContent = document.querySelector("#audiencia-drawer-content");
const audienciaDrawerClose = document.querySelector("#audiencia-drawer-close");
let selectedHtmlId = null;
let htmlEdits = {};
let pendingHtmlFile = null;
let pendingChatFile = null;
let workflowSocket = null;
let socketConnectPromise = null;
let activeSocketRequest = null;

function closeAudienciaDrawer() {
  audienciaDrawer.hidden = true;
  audienciaBackdrop.hidden = true;
  audienciaDrawer.setAttribute("aria-hidden", "true");
}

function showAudienciaDrawer(audiencia) {
  if (!audiencia || typeof audiencia !== "object") return;
  audienciaDrawerTitle.textContent = audiencia.titulo || audiencia.id || "Audiência";
  const participantes = Array.isArray(audiencia.participantes) ? audiencia.participantes : [];
  const discursos = Array.isArray(audiencia.discursos) ? audiencia.discursos : [];
  audienciaDrawerContent.innerHTML = `
    <p class="audiencia-summary">${escapeHtml(audiencia.resumo || "Nenhum resumo disponível.")}</p>
    <dl class="audiencia-meta">
      <div><dt>ID</dt><dd>${escapeHtml(audiencia.id || "—")}</dd></div>
      <div><dt>Data</dt><dd>${escapeHtml(audiencia.data || "—")}</dd></div>
      <div><dt>Casa</dt><dd>${escapeHtml(audiencia.casa || "—")}</dd></div>
      <div><dt>Comissão</dt><dd>${escapeHtml(audiencia.comissao || "—")}</dd></div>
    </dl>
    <section class="audiencia-section"><h3>Participantes (${participantes.length})</h3>
      <ul class="audiencia-list">${participantes.map((item) => `<li><strong>${escapeHtml(item.nome || "Participante")}</strong>${item.papel ? ` · ${escapeHtml(item.papel)}` : ""}${item.partido ? ` (${escapeHtml(item.partido)})` : ""}</li>`).join("") || "<li>Não informado.</li>"}</ul>
    </section>
    <section class="audiencia-section"><h3>Discursos (${discursos.length})</h3>
      <ul class="audiencia-list">${discursos.map((item) => `<li><strong>${escapeHtml(item.orador || "Orador")}</strong>: ${escapeHtml(item.texto || "")}</li>`).join("") || "<li>Não informado.</li>"}</ul>
    </section>
    <section class="audiencia-section"><h3>Conteúdo recebido</h3><pre class="audiencia-json">${escapeHtml(JSON.stringify(audiencia, null, 2))}</pre></section>
  `;
  audienciaDrawer.hidden = false;
  audienciaBackdrop.hidden = false;
  audienciaDrawer.setAttribute("aria-hidden", "false");
}

audienciaDrawerClose.addEventListener("click", closeAudienciaDrawer);
audienciaBackdrop.addEventListener("click", closeAudienciaDrawer);

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

function setAgentFeedback(message = "") {
  state.advanceFeedback = message;
  agentFeedback.textContent = message;
  agentFeedback.classList.toggle("visible", Boolean(message));
}

function setLoading(loading) {
  state.loading = loading;
  document.querySelectorAll("button").forEach((button) => { button.disabled = loading; });
}

function workflowSocketUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/workflow/sessions/${state.sessionId}/ws`;
}

function closeWorkflowSocket() {
  if (activeSocketRequest) {
    activeSocketRequest.reject(new Error("A conexão com o agente foi encerrada."));
    activeSocketRequest = null;
  }
  if (workflowSocket) workflowSocket.close();
  workflowSocket = null;
  socketConnectPromise = null;
}

function ensureWorkflowSocket() {
  if (workflowSocket && workflowSocket.readyState === WebSocket.OPEN) return Promise.resolve(workflowSocket);
  if (socketConnectPromise) return socketConnectPromise;

  socketConnectPromise = new Promise((resolve, reject) => {
    const socket = new WebSocket(workflowSocketUrl());
    workflowSocket = socket;
    socket.onopen = () => {
      socketConnectPromise = null;
      resolve(socket);
    };
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (!activeSocketRequest) return;
      if (message.type === "token") {
        activeSocketRequest.onToken(message.content || "");
      } else if (message.type === "done") {
        const request = activeSocketRequest;
        activeSocketRequest = null;
        request.resolve(message);
      } else if (message.type === "error") {
        const request = activeSocketRequest;
        activeSocketRequest = null;
        request.reject(new Error(message.message || "O agente não conseguiu responder agora."));
      }
    };
    socket.onerror = () => {
      if (activeSocketRequest) {
        activeSocketRequest.reject(new Error("Não foi possível conectar ao agente."));
        activeSocketRequest = null;
      }
      reject(new Error("Não foi possível conectar ao agente."));
    };
    socket.onclose = () => {
      workflowSocket = null;
      socketConnectPromise = null;
      if (activeSocketRequest) {
        activeSocketRequest.reject(new Error("A conexão com o agente foi encerrada."));
        activeSocketRequest = null;
      }
    };
  });
  return socketConnectPromise;
}

async function sendSocketRequest(payload, onToken) {
  const socket = await ensureWorkflowSocket();
  if (activeSocketRequest) throw new Error("Já existe uma solicitação em andamento.");
  return new Promise((resolve, reject) => {
    activeSocketRequest = { resolve, reject, onToken };
    socket.send(JSON.stringify(payload));
  });
}

function renderStreamingConversation(agentName) {
  const thread = document.querySelector("#stage-thread");
  if (!thread) return;
  thread.innerHTML = renderConversation(agentName);
  scrollStageThreadToBottom();
}

function scrollStageThreadToBottom() {
  requestAnimationFrame(() => {
    const thread = document.querySelector("#stage-thread");
    if (thread) thread.scrollTop = thread.scrollHeight;
  });
}

function startStreamingMessage(agentName) {
  state.streamingMessage = { role: "assistant", content: "", agent_name: agentName };
  renderStreamingConversation(agentName);
}

function appendStreamToken(agentName, token) {
  if (!state.streamingMessage || state.streamingMessage.agent_name !== agentName) return;
  state.streamingMessage.content += token;
  renderStreamingConversation(agentName);
}

async function refreshWorkflowArtifacts(data) {
  // Este ponto só é chamado após o evento `done` recebido pelo socket.
  if (!data.artifact_url) return;
  const response = await fetch(`${data.artifact_url}?v=${Date.now()}`);
  if (!response.ok) return;
  const content = await response.text();
  const previousContent = state.artifacts[data.artifact_name];
  state.artifacts[data.artifact_name] = content;
  if (data.artifact_name === "HTML.html") {
    updateHtmlPreview(data.html_url || data.artifact_url);
  } else {
    if (data.artifact_name === "planning.json" && previousContent !== content) {
      // A resposta que acabou de chegar já é a conversa que confirmou essa
      // atualização. O bloqueio permanece somente durante uma seleção pendente.
      state.planningNeedsConversation = false;
    }
    updateDocumentPreview(data.artifact_name, content);
  }
}

function updateHtmlPreview(url) {
  if (!url) return;
  documentPreviewCard.hidden = true;
  workspace.classList.remove("has-document-preview");
  const freshUrl = `${url}?v=${Date.now()}`;
  htmlPreview.src = freshUrl;
  htmlOpenLink.href = freshUrl;
  htmlPreviewCard.hidden = false;
  workspace.classList.add("has-html-preview");
  htmlPreview.addEventListener("load", bindHtmlSections, { once: true });
}

function updateDocumentPreview(filename, content) {
  htmlPreviewCard.hidden = true;
  workspace.classList.remove("has-html-preview");
  documentPreviewTitle.textContent = filename;
  if (filename === "planning.json") {
    try {
      const planning = JSON.parse(content);
      const items = Array.isArray(planning) ? planning : [];
      documentPreviewContent.innerHTML = items.length
        ? `<p class="planning-hint">Clique em uma proposta para escolhê-la.</p><div class="planning-list">${items.map((item, index) => `
            <button type="button" class="planning-item ${item.user_has_accepted === true ? "selected" : ""}" data-planning-id="${escapeHtml(String(item.id ?? item.audiencia_id ?? item.session_id ?? index))}" aria-pressed="${item.user_has_accepted === true}">
              ${item.user_has_accepted === true ? '<span class="planning-status">Ideia aceita</span>' : ""}
              <h3>${escapeHtml(item.titulo || item.title || "Ideia sem título")}</h3>
              <p>${escapeHtml(item.resumo || item.description || "")}</p>
              ${item.long_description ? `<p>${escapeHtml(item.long_description)}</p>` : ""}
            </button>
          `).join("")}</div>`
        : '<p class="artifact-markdown">Nenhuma ideia registrada ainda.</p>';
      documentPreviewContent.querySelectorAll("[data-planning-id]").forEach((item) => {
        item.addEventListener("click", () => selectPlanningItem(item.dataset.planningId));
      });
    } catch (error) {
      documentPreviewContent.innerHTML = `<pre class="artifact-markdown">${escapeHtml(content)}</pre>`;
    }
  } else {
    documentPreviewContent.innerHTML = `<pre class="artifact-markdown">${escapeHtml(content)}</pre>`;
  }
  documentPreviewCard.hidden = false;
  workspace.classList.add("has-document-preview");
}

function formatSessionDate(value) {
  if (!value) return "Data desconhecida";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Data desconhecida";
  return date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function renderPreviousSessions() {
  return `
    <section class="previous-sessions">
      <div class="previous-sessions-heading">
        <h3>Chats anteriores</h3>
        <span>${state.previousSessions.length ? `${state.previousSessions.length} encontrada${state.previousSessions.length === 1 ? "" : "s"}` : "Nenhum salvo"}</span>
      </div>
      ${state.previousSessions.length ? `<div class="previous-sessions-list">
        ${state.previousSessions.map((session) => {
          const agentName = AGENTS[session.selected_agent]?.[0] || "Agente não definido";
          const preview = session.last_message || "Sessão iniciada, sem mensagens ainda.";
          return `
            <button type="button" class="previous-session" data-session-id="${escapeHtml(session.id)}">
              <span class="previous-session-topline"><strong>${escapeHtml(agentName)}</strong><time>${escapeHtml(formatSessionDate(session.last_message_at || session.created_at))}</time></span>
              <span class="previous-session-preview">${escapeHtml(preview)}</span>
              <span class="previous-session-count">${session.message_count} mensagem${session.message_count === 1 ? "" : "s"}</span>
            </button>
          `;
        }).join("")}
      </div>` : '<p class="previous-sessions-empty">Nenhum chat salvo para o usuário atual.</p>'}
    </section>
  `;
}

async function loadPreviousSessions() {
  try {
    const response = await fetch("/api/workflow/sessions?user_id=10");
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Não foi possível carregar as sessões anteriores.");
    state.previousSessions = data;
    if (state.step === 0 && !state.sessionId) renderStep();
  } catch (error) {
    state.previousSessions = [];
    if (state.step === 0 && !state.sessionId) setError(error.message);
  }
}

async function resumeSession(sessionId) {
  setError("");
  setLoading(true);
  closeWorkflowSocket();
  try {
    const response = await fetch(`/api/workflow/sessions/${encodeURIComponent(sessionId)}`);
    const session = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(session.detail || "Não foi possível abrir a sessão.");

    state.sessionId = session.id;
    state.messages = (session.messages || []).filter((message) => message.hidden !== true);
    const messageAgent = state.messages.find((message) => AGENTS[message.agent_name])?.agent_name;
    state.activeAgent = session.selected_agent || messageAgent || "debate";
    state.streamingMessage = null;
    state.artifacts = {};
    state.planningNeedsConversation = false;
    htmlEdits = JSON.parse(localStorage.getItem(`html-edits-${state.sessionId}`) || "{}");
    htmlPreview.src = "about:blank";
    htmlPreviewCard.hidden = true;
    documentPreviewCard.hidden = true;
    workspace.classList.remove("has-html-preview", "has-document-preview");
    htmlEditPanel.hidden = true;
    selectedHtmlId = null;
    htmlEditInput.value = "";
    pendingChatFile = null;

    const hasFinalConversation = state.messages.some(
      (message) => message.agent_name === state.activeAgent,
    );
    state.step = hasFinalConversation ? 2 : 1;
    renderStep();

    if (state.step === 1) {
      const planningUrl = `/api/workflow/sessions/${state.sessionId}/planning.json?v=${Date.now()}`;
      const planningResponse = await fetch(planningUrl);
      if (planningResponse.ok) {
        const content = await planningResponse.text();
        state.artifacts["planning.json"] = content;
        updateDocumentPreview("planning.json", content);
      }
    } else {
      const htmlUrl = `/api/workflow/sessions/${state.sessionId}/html`;
      const htmlResponse = await fetch(`${htmlUrl}?v=${Date.now()}`);
      if (htmlResponse.ok) updateHtmlPreview(htmlUrl);
    }
  } catch (error) {
    setError(error.message);
  } finally {
    setLoading(false);
  }
}

async function selectPlanningItem(planningId) {
  if (!state.sessionId || state.loading) return;
  setError("");
  setAgentFeedback("");
  setLoading(true);
  try {
    // Temporário: qualquer proposta clicada usa a audiência mock aud-001.
    const audienciaId = "aud-001";
    const response = await fetch(`/api/workflow/sessions/${state.sessionId}/planning/select/${audienciaId}`, {
      method: "POST",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Não foi possível selecionar essa proposta.");
    const content = JSON.stringify(data.planning || [], null, 2);
    showAudienciaDrawer(data.audiencia);
    state.artifacts["planning.json"] = content;
    if (data.changed !== false) state.planningNeedsConversation = true;
    updateDocumentPreview("planning.json", content);
    const selected = data.audiencia || {};
    const selectedTitle = selected.titulo || selected.title || "";
    const selectedDescription = selected.resumo || selected.description || "";
    if (data.changed !== false) {
      await callAgent(
        "brainstorm",
        `Uma nova audiência foi escolhida e salva em audiencia.json. Leia esse arquivo com execute_bash("cat audiencia.json") e descreva para o usuário o significado, o contexto, os participantes e os principais posicionamentos dessa audiência. A ideia escolhida foi: ${selectedTitle} ${selectedDescription}`.trim(),
        { showUserMessage: false },
      );
    }
    state.planningNeedsConversation = false;
  } catch (error) {
    setError(error.message);
  } finally {
    setLoading(false);
  }
}

function saveHtmlEdits() {
  if (state.sessionId) localStorage.setItem(`html-edits-${state.sessionId}`, JSON.stringify(htmlEdits));
}

function bindHtmlSections() {
  const documentHtml = htmlPreview.contentDocument;
  if (!documentHtml) return;
  documentHtml.addEventListener("click", (event) => {
    const section = event.target.closest("div[id]");
    if (!section || !section.id) return;
    event.preventDefault();
    event.stopPropagation();
    if (selectedHtmlId) {
      htmlEdits[selectedHtmlId] = htmlEditInput.value;
      saveHtmlEdits();
    }
    selectedHtmlId = section.id;
    selectedHtmlTarget.textContent = `Seção: #${section.id}`;
    htmlEditInput.value = htmlEdits[selectedHtmlId] || "";
    htmlEditPanel.hidden = false;
    htmlEditInput.focus();
  });
}

function renderProgress() {
  document.querySelectorAll(".progress-step").forEach((item) => {
    const itemStep = Number(item.dataset.step);
    item.classList.toggle("active", itemStep === state.step);
    item.classList.toggle("done", itemStep < state.step);
  });
}

function stageMessages(agentName) {
  return state.messages.filter((message) => message.agent_name === agentName);
}

function hasAssistantReply(agentName) {
  return stageMessages(agentName).some((message) => message.role === "assistant");
}

function renderConversation(agentName) {
  const messages = stageMessages(agentName);
  const streaming = state.streamingMessage && state.streamingMessage.agent_name === agentName
    ? [state.streamingMessage]
    : [];
  if (!messages.length && !streaming.length) {
    return '<p class="empty-stage">Comece a conversa quando quiser.</p>';
  }
  return [...messages, ...streaming].map((message) => `
    <article class="stage-message ${message.role}">
      <span class="stage-message-role">${message.role === "user" ? "Você" : "Agente"}</span>
      <p>${escapeHtml(message.content)}</p>
    </article>
  `).join("");
}

function renderChatStage({ agentName, inputLabel, placeholder, sendLabel, continueLabel }) {
  const blockedByPlanningConversation = agentName === "brainstorm" && state.planningNeedsConversation;
  const canContinue = hasAssistantReply(agentName) && !blockedByPlanningConversation;
  const continueHint = blockedByPlanningConversation
    ? "Aguarde a resposta do agente sobre a escolha antes de avançar."
    : "Envie pelo menos uma mensagem antes de avançar.";
  stepContent.innerHTML = `
    <div class="stage-thread" id="stage-thread">${renderConversation(agentName)}</div>
    <label class="form-label" for="stage-input">${inputLabel}</label>
    <textarea id="stage-input" placeholder="${placeholder}"></textarea>
    <div class="attachment-row"><button class="clip-button" id="chat-attach-button" type="button" title="Anexar arquivo">📎</button><span id="chat-file-name"></span><input id="chat-file-input" type="file" hidden /></div>
    <div class="actions">
      ${continueLabel ? `<button class="secondary-button" id="continue-button" type="button" ${canContinue ? "" : "disabled"}>${continueLabel} →</button>` : ""}
      <button class="primary-button" id="send-button" type="button">${sendLabel} ↑</button>
    </div>
    ${continueLabel && !canContinue ? `<p class="continue-hint">${continueHint}</p>` : ""}
  `;

  document.querySelector("#send-button").addEventListener("click", () => sendStageMessage(agentName));
  document.querySelector("#chat-attach-button").addEventListener("click", () => document.querySelector("#chat-file-input").click());
  document.querySelector("#chat-file-input").addEventListener("change", (event) => {
    pendingChatFile = event.target.files[0] || null;
    document.querySelector("#chat-file-name").textContent = pendingChatFile ? pendingChatFile.name : "";
  });
  document.querySelector("#stage-input").addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") sendStageMessage(agentName);
  });
  if (continueLabel) {
    document.querySelector("#continue-button").addEventListener("click", () => {
      requestAdvance(agentName).catch((error) => setError(error.message)).finally(() => setLoading(false));
    });
  }
}

function renderStep() {
  renderProgress();
  if (state.step === 0) {
    stepCopy.innerHTML = '<h2>Escolha o agente</h2><p>Defina agora qual agente vai conduzir o resultado final. Depois, você passará pelo brainstorm antes de conversar com ele.</p>';
    const options = Object.entries(AGENTS).map(([value, [name, description]]) => `
      <div class="agent-option">
        <input id="agent-${value}" type="radio" name="agent" value="${value}" ${state.activeAgent === value ? "checked" : ""} />
        <label for="agent-${value}"><strong>${name}</strong><span>${description}</span></label>
      </div>
    `).join("");
    stepContent.innerHTML = `
      ${renderPreviousSessions()}
      <div class="agent-grid">${options}</div>
      <div class="actions"><button class="primary-button" id="start-brainstorm" type="button">Começar brainstorm →</button></div>
    `;
    document.querySelectorAll(".previous-session").forEach((button) => {
      button.addEventListener("click", () => resumeSession(button.dataset.sessionId));
    });
    document.querySelectorAll('input[name="agent"]').forEach((input) => {
      input.addEventListener("change", (event) => {
        state.activeAgent = event.target.value;
        renderStep();
      });
    });
    document.querySelector("#start-brainstorm").addEventListener("click", async () => {
      setError("");
      setLoading(true);
      try {
        await createSession(state.activeAgent);
        state.step = 1;
        renderStep();
      } catch (error) {
        setError(error.message);
      } finally {
        setLoading(false);
      }
    });
  } else if (state.step === 1) {
    stepCopy.innerHTML = '<h2>Comece pelo brainstorm</h2><p>Converse com o agente e explore a ideia pelo tempo que precisar. Só avance quando você decidir.</p>';
    renderChatStage({
      agentName: "brainstorm",
      inputLabel: "Sua mensagem para o brainstorm",
      placeholder: "Ex.: Quero trabalhar o tema da água com uma turma do ensino fundamental...",
      sendLabel: "Enviar para o brainstorm",
      continueLabel: `Ir para ${AGENTS[state.activeAgent][0]}`,
    });
  } else {
    const [agentName, agentDescription] = AGENTS[state.activeAgent];
    stepCopy.innerHTML = `<h2>${agentName}</h2><p>${agentDescription} O agente escolhido no início continuará responsável pelo resultado final.</p>`;
    renderChatStage({
      agentName: state.activeAgent,
      inputLabel: `Sua mensagem para o agente de ${agentName.toLowerCase()}`,
      placeholder: "Ex.: Ajuste a proposta para incluir uma atividade prática.",
      sendLabel: "Enviar mensagem",
    });
  }
  scrollStageThreadToBottom();
}

async function createSession(agentName = state.activeAgent) {
  closeWorkflowSocket();
  const response = await fetch("/api/workflow/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: 10, agent_name: agentName }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Não foi possível iniciar a sessão.");
  }
  const session = await response.json();
  state.sessionId = session.id;
  state.previousSessions = [
    {
      id: session.id,
      created_at: session.created_at,
      selected_agent: session.selected_agent || agentName,
      message_count: 0,
      last_message_at: null,
      last_message: null,
    },
    ...state.previousSessions.filter((item) => item.id !== session.id),
  ];
  htmlEdits = JSON.parse(localStorage.getItem(`html-edits-${state.sessionId}`) || "{}");
  state.messages = session.messages.filter((message) => message.hidden !== true);
  state.step = 0;
  state.activeAgent = agentName;
  state.streamingMessage = null;
  state.artifacts = {};
  state.planningNeedsConversation = false;
  setAgentFeedback("");
  htmlPreview.src = "about:blank";
  htmlPreviewCard.hidden = true;
  documentPreviewCard.hidden = true;
  workspace.classList.remove("has-html-preview");
  workspace.classList.remove("has-document-preview");
  htmlEditPanel.hidden = true;
  selectedHtmlId = null;
  htmlEdits = {};
  htmlEditInput.value = "";
  renderStep();
}

function resetSessionSelection() {
  closeWorkflowSocket();
  state.sessionId = null;
  state.step = 0;
  state.activeAgent = "debate";
  state.messages = [];
  state.streamingMessage = null;
  state.artifacts = {};
  state.planningNeedsConversation = false;
  setAgentFeedback("");
  htmlPreview.src = "about:blank";
  htmlPreviewCard.hidden = true;
  documentPreviewCard.hidden = true;
  workspace.classList.remove("has-html-preview", "has-document-preview");
  htmlEditPanel.hidden = true;
  selectedHtmlId = null;
  htmlEdits = {};
  htmlEditInput.value = "";
  renderStep();
  loadPreviousSessions();
}

async function callAgent(agentName, text, { showUserMessage = true } = {}) {
  if (!text.trim()) throw new Error("Escreva uma mensagem antes de enviar.");
  setError("");
  setAgentFeedback("");
  setLoading(true);
  const normalizedText = text.trim();
  if (showUserMessage) {
    state.messages.push({ role: "user", content: normalizedText, agent_name: agentName });
    if (agentName === "brainstorm") state.planningNeedsConversation = false;
  }
  startStreamingMessage(agentName);
  let completedMessage;
  try {
    const data = await sendSocketRequest(
      { type: "message", text: normalizedText, agent_name: agentName, hidden: !showUserMessage },
      (token) => appendStreamToken(agentName, token),
    );
    state.streamingMessage = null;
    if (data.message) {
      state.messages.push(data.message);
      completedMessage = data.message;
    }
    await refreshWorkflowArtifacts(data);
  } catch (error) {
    state.streamingMessage = null;
    renderStreamingConversation(agentName);
    throw error;
  }
  return completedMessage;
}

async function sendHiddenGreeting(agentName) {
  try {
    return await callAgent(agentName, "oi", { showUserMessage: false });
  } finally {
    setLoading(false);
  }
}

async function requestAdvance(fromAgent) {
  if (state.loading) return;
  setError("");
  setAgentFeedback("");
  setLoading(true);
  startStreamingMessage(fromAgent);
  try {
    const data = await sendSocketRequest(
      { type: "advance", from_agent: fromAgent },
      (token) => appendStreamToken(fromAgent, token),
    );
    state.streamingMessage = null;
    if (data.message) {
      state.messages.push(data.message);
      // Quando não pode avançar, a resposta já aparece no histórico da conversa.
      // O feedback separado só é necessário depois da troca de etapa, quando o
      // histórico do agente anterior deixa de estar visível.
      setAgentFeedback(data.allowed ? (data.message.content || "") : "");
    }
    await refreshWorkflowArtifacts(data);
    if (data.allowed) {
      state.step = 2;
      renderStep();
      await sendHiddenGreeting(state.activeAgent);
      renderStep();
    } else {
      renderStep();
    }
  } catch (error) {
    state.streamingMessage = null;
    renderStreamingConversation(fromAgent);
    throw error;
  }
}

async function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`/api/workflow/sessions/${state.sessionId}/files`, { method: "POST", body: form });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Não foi possível anexar o arquivo.");
  return data;
}

async function sendStageMessage(agentName) {
  const input = document.querySelector("#stage-input");
  if (!input) return;
  try {
    let text = input.value.trim();
    if (pendingChatFile) {
      const file = await uploadFile(pendingChatFile);
      text += `${text ? "\n\n" : ""}[Arquivo anexado: ${file.filename}; armazenado em ${file.sandbox_path}]`;
    }
    await callAgent(agentName, text);
    pendingChatFile = null;
    document.querySelector("#chat-file-input").value = "";
    renderStep();
  } catch (error) {
    setError(error.message);
  } finally {
    setLoading(false);
  }
}

document.querySelector("#new-session").addEventListener("click", () => {
  setError("");
  resetSessionSelection();
});

renderStep();
loadPreviousSessions();

htmlEditSubmit.addEventListener("click", async () => {
  if (selectedHtmlId) htmlEdits[selectedHtmlId] = htmlEditInput.value.trim();
  saveHtmlEdits();
  const edits = Object.entries(htmlEdits)
    .map(([id, text]) => ({ id, text: String(text || "").trim() }))
    .filter(({ text }) => text.length > 0);
  if (!edits.length && !pendingHtmlFile) {
    setError("Selecione uma ou mais seções e descreva as melhorias.");
    return;
  }
  try {
    if (pendingHtmlFile) {
      const file = await uploadFile(pendingHtmlFile);
      edits.push({ id: "__arquivo__", text: `Arquivo anexado: ${file.filename}; armazenado em ${file.sandbox_path}` });
    }
    const request = JSON.stringify(edits, null, 2);
    await callAgent(state.activeAgent, `Aplique no HTML.html somente estas melhorias. Cada item contém o id da div e o pedido:\n${request}`);
    htmlEditPanel.hidden = true;
    htmlEdits = {};
    selectedHtmlId = null;
    htmlEditInput.value = "";
    pendingHtmlFile = null;
    htmlFileInput.value = "";
    htmlFileName.textContent = "";
    renderStep();
  } catch (error) {
    setError(error.message);
  } finally {
    setLoading(false);
  }
});

htmlAttachButton.addEventListener("click", () => htmlFileInput.click());
htmlFileInput.addEventListener("change", (event) => {
  pendingHtmlFile = event.target.files[0] || null;
  htmlFileName.textContent = pendingHtmlFile ? pendingHtmlFile.name : "";
});

async function generatePdf() {
  if (!state.sessionId || !htmlOpenLink.href || htmlOpenLink.getAttribute("href") === "#") {
    setError("Gere o HTML antes de criar o PDF.");
    return;
  }
  setError("");
  setLoading(true);
  try {
    const htmlResponse = await fetch(htmlOpenLink.href);
    if (!htmlResponse.ok) throw new Error("Não foi possível ler o HTML atual.");
    const htmlBlob = await htmlResponse.blob();
    const form = new FormData();
    form.append("file", htmlBlob, "HTML.html");
    const response = await fetch(`/api/workflow/sessions/${state.sessionId}/pdf`, {
      method: "POST",
      body: form,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || "Não foi possível gerar o PDF.");
    }
    const pdfBlob = await response.blob();
    const downloadUrl = URL.createObjectURL(pdfBlob);
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = "atividade.pdf";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(downloadUrl);
  } catch (error) {
    setError(error.message);
  } finally {
    setLoading(false);
  }
}

generatePdfButton.addEventListener("click", generatePdf);

htmlEditInput.addEventListener("input", () => {
  if (!selectedHtmlId) return;
  htmlEdits[selectedHtmlId] = htmlEditInput.value;
  saveHtmlEdits();
});
