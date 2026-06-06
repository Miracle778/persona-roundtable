const state = {
  config: null,
  personas: [],
  sessions: [],
  currentSession: null,
  currentPersonaId: null,
  topic: null,
};

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

async function loadAll() {
  const [config, personas, sessions] = await Promise.all([
    api("/api/config"),
    api("/api/personas"),
    api("/api/sessions"),
  ]);
  state.config = config;
  state.personas = personas;
  state.sessions = sessions;
  renderConfig();
  renderModelPicker();
  renderPersonas();
  renderSessions();
}

function renderConfig() {
  $("configJson").value = JSON.stringify(state.config, null, 2);
}

function renderModelPicker() {
  const providerSelect = $("providerSelect");
  providerSelect.innerHTML = "";
  for (const provider of state.config.providers || []) {
    const option = document.createElement("option");
    option.value = provider.id;
    option.textContent = provider.name || provider.id;
    providerSelect.appendChild(option);
  }
  providerSelect.onchange = renderModels;
  renderModels();
}

function renderModels() {
  const providerId = $("providerSelect").value;
  const provider = (state.config.providers || []).find((item) => item.id === providerId);
  const modelSelect = $("modelSelect");
  modelSelect.innerHTML = "";
  for (const model of provider?.available_models || []) {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    modelSelect.appendChild(option);
  }
}

function renderPersonas() {
  const container = $("personaList");
  container.innerHTML = "";
  for (const persona of state.personas) {
    const row = document.createElement("div");
    row.className = "persona-item";
    if (persona.id === state.currentPersonaId) row.classList.add("active");
    row.innerHTML = `
      <input type="checkbox" value="${escapeHtml(persona.id)}" checked>
      <button type="button" class="persona-edit">
        <strong>${escapeHtml(persona.display_name)}</strong>
        <span class="meta">${escapeHtml((persona.categories || []).join(" / ") || "未分类")} · ${escapeHtml(persona.model || "默认模型")}</span>
      </button>
    `;
    row.querySelector(".persona-edit").onclick = () => selectPersona(persona.id);
    container.appendChild(row);
  }
  if (!state.currentPersonaId && state.personas.length) {
    state.currentPersonaId = state.personas[0].id;
  }
  renderPersonaEditor();
}

function currentPersona() {
  return state.personas.find((persona) => persona.id === state.currentPersonaId) || null;
}

function selectPersona(id) {
  state.currentPersonaId = id;
  renderPersonas();
}

function renderPersonaEditor() {
  const persona = currentPersona();
  $("personaForm").classList.toggle("hidden", !persona);
  if (!persona) return;
  $("personaName").value = persona.display_name || "";
  $("personaDescription").value = persona.description || "";
  $("personaCategories").value = (persona.categories || []).join(", ");
  $("personaPrompt").value = persona.prompt || "";
}

function renderSessions() {
  const container = $("sessionList");
  container.innerHTML = "";
  if (!state.sessions.length) {
    const empty = document.createElement("div");
    empty.className = "session-item meta";
    empty.textContent = "暂无会话";
    container.appendChild(empty);
    return;
  }
  for (const session of state.sessions) {
    const button = document.createElement("button");
    button.className = "session-item";
    button.innerHTML = `
      <strong>${escapeHtml(session.title)}</strong>
      <span class="meta">${escapeHtml((session.topic_tags || []).join(" / "))} · ${session.message_count || 0} 条</span>
    `;
    button.onclick = () => openSession(session.id);
    container.appendChild(button);
  }
}

function renderTopicCard(topic) {
  state.topic = topic;
  $("topicCard").classList.remove("hidden");
  $("topicTitle").value = topic.title || "";
  $("topicTags").value = (topic.tags || []).join(", ");
  $("topicTask").value = topic.discussion_task || "";
}

function readTopicCard() {
  return {
    ...state.topic,
    title: $("topicTitle").value.trim(),
    tags: $("topicTags").value.split(",").map((item) => item.trim()).filter(Boolean),
    discussion_task: $("topicTask").value.trim(),
  };
}

function selectedPersonaIds() {
  return Array.from(document.querySelectorAll("#personaList input:checked")).map((item) => item.value);
}

async function openSession(id) {
  state.currentSession = await api(`/api/sessions/${id}`);
  renderMessages();
}

function renderMessages() {
  const container = $("messageList");
  container.innerHTML = "";
  const messages = state.currentSession?.messages || [];
  for (const message of messages) {
    const row = document.createElement("article");
    row.className = "message";
    row.innerHTML = `
      <div class="speaker">${escapeHtml(message.speaker || message.role)}</div>
      <div>
        <div class="message-body">${escapeHtml(message.content)}</div>
        <div class="meta">${escapeHtml([message.provider_id, message.model].filter(Boolean).join(" / "))}</div>
      </div>
    `;
    container.appendChild(row);
  }
  container.scrollTop = container.scrollHeight;
}

async function refreshSessions() {
  const query = $("sessionSearch").value.trim();
  state.sessions = await api(`/api/sessions${query ? `?q=${encodeURIComponent(query)}` : ""}`);
  renderSessions();
}

async function refineTopic() {
  const rawInput = $("rawInput").value.trim();
  if (!rawInput) return;
  const topic = await api("/api/topic/refine", {
    method: "POST",
    body: JSON.stringify({ raw_input: rawInput }),
  });
  renderTopicCard(topic);
}

async function createSession() {
  const rawInput = $("rawInput").value.trim();
  if (!rawInput) return;
  const topic = state.topic ? readTopicCard() : await api("/api/topic/refine", {
    method: "POST",
    body: JSON.stringify({ raw_input: rawInput }),
  });
  const session = await api("/api/sessions", {
    method: "POST",
    body: JSON.stringify({
      raw_input: rawInput,
      topic,
      persona_ids: selectedPersonaIds(),
    }),
  });
  state.currentSession = session;
  await refreshSessions();
  renderMessages();
}

async function sendMessage(event) {
  event.preventDefault();
  if (!state.currentSession) return;
  const input = $("messageInput");
  const content = input.value.trim();
  if (!content) return;
  input.value = "";
  state.currentSession = await api(`/api/sessions/${state.currentSession.id}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
  await refreshSessions();
  renderMessages();
}

async function assignModel() {
  const personaIds = selectedPersonaIds();
  if (!personaIds.length) return;
  await api("/api/personas/model", {
    method: "POST",
    body: JSON.stringify({
      persona_ids: personaIds,
      provider_id: $("providerSelect").value,
      model: $("modelSelect").value,
    }),
  });
  state.personas = await api("/api/personas");
  renderPersonas();
}

async function savePersona(event) {
  event.preventDefault();
  const persona = currentPersona();
  if (!persona) return;
  const updated = await api(`/api/personas/${persona.id}`, {
    method: "PATCH",
    body: JSON.stringify({
      display_name: $("personaName").value.trim(),
      description: $("personaDescription").value.trim(),
      categories: $("personaCategories").value.split(",").map((item) => item.trim()).filter(Boolean),
      prompt: $("personaPrompt").value,
    }),
  });
  state.personas = state.personas.map((item) => item.id === updated.id ? updated : item);
  state.currentPersonaId = updated.id;
  renderPersonas();
}

async function clonePersona() {
  const persona = currentPersona();
  if (!persona) return;
  const clone = await api("/api/personas", {
    method: "POST",
    body: JSON.stringify({
      source_persona_id: persona.id,
      display_name: `${$("personaName").value.trim() || persona.display_name} 副本`,
    }),
  });
  state.personas = await api("/api/personas");
  state.currentPersonaId = clone.id;
  renderPersonas();
}

async function archivePersona() {
  const persona = currentPersona();
  if (!persona) return;
  await api(`/api/personas/${persona.id}`, { method: "DELETE" });
  state.personas = await api("/api/personas");
  state.currentPersonaId = state.personas[0]?.id || null;
  renderPersonas();
}

async function saveConfig() {
  const config = JSON.parse($("configJson").value);
  state.config = await api("/api/config", {
    method: "POST",
    body: JSON.stringify(config),
  });
  renderConfig();
  renderModelPicker();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

$("refreshSessions").onclick = refreshSessions;
$("sessionSearch").oninput = () => refreshSessions();
$("refineTopic").onclick = refineTopic;
$("createSession").onclick = createSession;
$("messageForm").onsubmit = sendMessage;
$("assignModel").onclick = assignModel;
$("personaForm").onsubmit = savePersona;
$("clonePersona").onclick = clonePersona;
$("archivePersona").onclick = archivePersona;
$("saveConfig").onclick = saveConfig;

loadAll().catch((error) => {
  console.error(error);
  alert(error.message);
});
