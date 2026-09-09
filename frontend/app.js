const state = {
  sessionId: null,
  step: 0,
  activeAgent: "debate",
  messages: [],
  loading: false,
};

const stepCopy = document.querySelector("#step-copy");
const stepContent = document.querySelector("#step-content");
const errorMessage = document.querySelector("#error-message");
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
let selectedHtmlId = null;
let htmlEdits = {};
let pendingHtmlFile = null;
let pendingChatFile = null;

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

function updateHtmlPreview(url) {
  if (!url) return;
  const freshUrl = `${url}?v=${Date.now()}`;
  htmlPreview.src = freshUrl;
  htmlOpenLink.href = freshUrl;
  htmlPreviewCard.hidden = false;
  workspace.classList.add("has-html-preview");
  htmlPreview.addEventListener("load", bindHtmlSections, { once: true });
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
    <div class="attachment-row"><button class="clip-button" id="chat-attach-button" type="button" title="Anexar arquivo">📎</button><span id="chat-file-name"></span><input id="chat-file-input" type="file" hidden /></div>
    <div class="actions">
      ${continueLabel ? `<button class="secondary-button" id="continue-button" type="button" ${canContinue ? "" : "disabled"}>${continueLabel} →</button>` : ""}
      <button class="primary-button" id="send-button" type="button">${sendLabel} ↑</button>
    </div>
    ${continueLabel && !canContinue ? '<p class="continue-hint">Envie pelo menos uma mensagem antes de avançar.</p>' : ""}
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
        <label for="agent-${value}"><strong>${name}</strong></label>
      </div>
    `).join("");
    stepContent.innerHTML = `
      <div class="agent-grid">${options}</div>
      <div class="stage-thread final-thread" id="stage-thread">${renderConversation(state.activeAgent)}</div>
      <label class="form-label" for="stage-input">Sua mensagem para o agente</label>
      <textarea id="stage-input" placeholder="Ex.: Ajuste a proposta para incluir uma atividade prática."></textarea>
      <div class="attachment-row"><button class="clip-button" id="chat-attach-button" type="button" title="Anexar arquivo">📎</button><span id="chat-file-name"></span><input id="chat-file-input" type="file" hidden /></div>
      <div class="actions"><button class="primary-button" id="send-button" type="button">Enviar mensagem ↑</button></div>
    `;
    document.querySelectorAll('input[name="agent"]').forEach((input) => {
      input.addEventListener("change", (event) => {
        state.activeAgent = event.target.value;
        renderStep();
      });
    });
    document.querySelector("#send-button").addEventListener("click", () => sendStageMessage(state.activeAgent));
    document.querySelector("#chat-attach-button").addEventListener("click", () => document.querySelector("#chat-file-input").click());
    document.querySelector("#chat-file-input").addEventListener("change", (event) => {
      pendingChatFile = event.target.files[0] || null;
      document.querySelector("#chat-file-name").textContent = pendingChatFile ? pendingChatFile.name : "";
    });
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
  htmlEdits = JSON.parse(localStorage.getItem(`html-edits-${state.sessionId}`) || "{}");
  state.messages = session.messages;
  state.step = 0;
  state.activeAgent = "debate";
  htmlPreview.src = "about:blank";
  htmlPreviewCard.hidden = true;
  workspace.classList.remove("has-html-preview");
  htmlEditPanel.hidden = true;
  selectedHtmlId = null;
  htmlEdits = {};
  htmlEditInput.value = "";
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
  updateHtmlPreview(data.html_url);
  return data.message;
}

async function requestAdvance(fromAgent) {
  setError("");
  setLoading(true);
  const response = await fetch(`/api/workflow/sessions/${state.sessionId}/advance`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ from_agent: fromAgent }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Não foi possível validar o avanço.");
  if (data.message) state.messages.push(data.message);
  if (data.html_url) updateHtmlPreview(data.html_url);
  renderStep();
  if (data.allowed) {
    state.step += 1;
    renderStep();
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

document.querySelector("#new-session").addEventListener("click", async () => {
  try { setError(""); await createSession(); }
  catch (error) { setError(error.message); }
});

createSession().catch((error) => setError(error.message));

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

htmlEditInput.addEventListener("input", () => {
  if (!selectedHtmlId) return;
  htmlEdits[selectedHtmlId] = htmlEditInput.value;
  saveHtmlEdits();
});
