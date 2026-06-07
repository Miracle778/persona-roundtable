const state = {
  config: null,
  personas: [],
  sessions: [],
  currentSession: null,
  currentPersonaId: null,
  topic: null,
  mode: "idle",
  topicCardExpanded: false,
  sending: false,
  sessionPersonaPickerOpen: false,
  pendingSessionPersonaIds: new Set(),
  selectedPersonaIds: new Set(),
  editingProviderId: null,
  personaModelDirty: false,
};

const $ = (id) => document.getElementById(id);

const sourceLabels = {
  llm: "LLM 精炼",
  local: "本地草稿",
  fallback: "降级草稿",
};

const roleColors = ["blue", "green", "purple", "orange", "pink", "amber"];

const roleColorMap = {
  "孙笑川": "pink",
  "马斯克": "green",
  "罗翔": "blue",
  "张维为": "purple",
  "峰哥": "orange",
  "敖厂长": "amber",
  "default": "blue",
};

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
  ensurePersonaSelection();
  renderConfig();
  renderModelPicker();
  renderPersonas();
  renderSessions();
  renderWorkSurface();
}

function renderConfig() {
  $("configJson").value = JSON.stringify(state.config, null, 2);
  renderProviderList();
  renderProviderFormMode();
}

function renderModelPicker() {
  renderProviderModelPicker("providerSelect", "modelSelect");
  syncPersonaModelPicker();
}

function renderProviderModelPicker(providerSelectId, modelSelectId) {
  const providerSelect = $(providerSelectId);
  providerSelect.innerHTML = "";
  for (const provider of state.config.providers || []) {
    const option = document.createElement("option");
    option.value = provider.id;
    option.textContent = provider.name || provider.id;
    providerSelect.appendChild(option);
  }
  providerSelect.onchange = () => {
    renderModels(providerSelectId, modelSelectId);
    if (providerSelectId === "providerSelect" && modelSelectId === "modelSelect") {
      state.personaModelDirty = true;
    }
  };
  renderModels(providerSelectId, modelSelectId);
  const modelSelect = $(modelSelectId);
  modelSelect.onchange = () => {
    if (providerSelectId === "providerSelect" && modelSelectId === "modelSelect") {
      state.personaModelDirty = true;
    }
  };
}

function renderModels(providerSelectId = "providerSelect", modelSelectId = "modelSelect") {
  const providerId = $(providerSelectId).value;
  const provider = (state.config.providers || []).find((item) => item.id === providerId);
  const modelSelect = $(modelSelectId);
  modelSelect.innerHTML = "";
  for (const model of provider?.available_models || []) {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    modelSelect.appendChild(option);
  }
}

function ensureModelOption(modelSelect, model) {
  if (!model) return;
  if (Array.from(modelSelect.options).some((option) => option.value === model)) return;
  const option = document.createElement("option");
  option.value = model;
  option.textContent = `${model} (当前)`;
  modelSelect.appendChild(option);
}

function renderProviderList() {
  const providers = state.config.providers || [];
  const list = $("providerList");
  const summary = $("providerListSummary");
  list.innerHTML = "";
  summary.textContent = `${providers.length} 个`;
  if (state.editingProviderId && !providers.some((provider) => provider.id === state.editingProviderId)) {
    cancelProviderEdit();
  }
  if (!providers.length) {
    const empty = document.createElement("div");
    empty.className = "provider-empty";
    empty.textContent = "还没有 Provider";
    list.appendChild(empty);
    return;
  }
  for (const provider of providers) {
    list.appendChild(createProviderRow(provider));
  }
}

function createProviderRow(provider) {
  const row = document.createElement("article");
  row.className = "provider-row";
  const details = document.createElement("div");
  details.className = "provider-details";
  const title = document.createElement("div");
  title.className = "provider-title";
  const name = document.createElement("strong");
  name.textContent = provider.name || provider.id;
  const id = document.createElement("code");
  id.textContent = provider.id;
  title.append(name, id);
  const models = document.createElement("div");
  models.className = "provider-models";
  models.textContent = providerModelLabel(provider);
  const keyStatus = document.createElement("span");
  keyStatus.className = "provider-key-status";
  keyStatus.dataset.state = provider.has_api_key ? "ok" : "empty";
  keyStatus.textContent = provider.has_api_key ? "Key 已配置" : "未配置 Key";
  details.append(title, models, keyStatus);
  const actions = document.createElement("div");
  actions.className = "provider-actions";
  const editButton = document.createElement("button");
  editButton.type = "button";
  editButton.className = "secondary provider-edit-button";
  editButton.textContent = "编辑";
  editButton.onclick = runAction(() => editProvider(provider.id));
  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "ghost provider-delete-button";
  deleteButton.textContent = "删除";
  deleteButton.onclick = runAction(() => deleteProvider(provider.id));
  const testButton = document.createElement("button");
  testButton.type = "button";
  testButton.className = "secondary provider-test-button";
  testButton.textContent = "测试连接";
  testButton.disabled = !defaultProviderModel(provider);
  testButton.onclick = runAction(() => testProviderConnection(
    provider.id,
    defaultProviderModel(provider),
    provider.name || provider.id,
  ));
  actions.append(editButton, deleteButton, testButton);
  row.append(details, actions);
  return row;
}

function providerModelLabel(provider) {
  const models = provider.available_models || [];
  if (!models.length) return "未配置模型";
  return models.join(" · ");
}

function defaultProviderModel(provider) {
  return provider.default_model || (provider.available_models || [])[0] || "";
}

function providerById(providerId) {
  return (state.config.providers || []).find((provider) => provider.id === providerId) || null;
}

function personaRecordId(persona) {
  return persona?.id || persona?.persona_id || null;
}

function livePersona(persona) {
  const id = personaRecordId(persona);
  if (!id) return null;
  return state.personas.find((item) => item.id === id) || null;
}

function displayPersonaModel(persona) {
  const live = livePersona(persona);
  return live?.model || persona.model || persona.model_snapshot || "默认模型";
}

function syncPersonaModelPicker() {
  const providerSelect = $("providerSelect");
  const modelSelect = $("modelSelect");
  if (!providerSelect || !modelSelect) return;
  const providers = state.config?.providers || [];
  if (!providers.length) {
    providerSelect.innerHTML = "";
    modelSelect.innerHTML = "";
    return;
  }
  const persona = currentPersona();
  const fallbackProviderId = state.config?.default_model?.provider_id || providers[0].id;
  const desiredProviderId = persona?.provider_id || fallbackProviderId;
  providerSelect.value = providers.some((provider) => provider.id === desiredProviderId)
    ? desiredProviderId
    : fallbackProviderId;
  renderModels("providerSelect", "modelSelect");
  const provider = providerById(providerSelect.value) || providers[0];
  const desiredModel = persona?.model || defaultProviderModel(provider);
  ensureModelOption(modelSelect, desiredModel);
  modelSelect.value = desiredModel;
  state.personaModelDirty = false;
}

function renderProviderFormMode() {
  const editing = Boolean(state.editingProviderId);
  $("providerId").disabled = editing;
  $("providerApiKey").placeholder = editing ? "留空保留已有 Key" : "sk-...";
  $("addProvider").textContent = editing ? "保存 Provider" : "添加 Provider";
  $("cancelProviderEdit").classList.toggle("hidden", !editing);
}

function editProvider(providerId) {
  const provider = providerById(providerId);
  if (!provider) return;
  state.editingProviderId = providerId;
  $("providerId").value = provider.id || "";
  $("providerName").value = provider.name || provider.id || "";
  $("providerBaseUrl").value = provider.base_url || "";
  $("providerApiKey").value = "";
  $("providerModels").value = (provider.available_models || []).join(", ");
  renderProviderFormMode();
  $("providerName").focus();
}

function cancelProviderEdit() {
  state.editingProviderId = null;
  $("providerForm").reset();
  renderProviderFormMode();
}

function renderPersonas() {
  ensurePersonaSelection();
  const statusContainer = $("personaList");
  const manageContainer = $("personaManageList");
  statusContainer.innerHTML = "";
  manageContainer.innerHTML = "";
  const displayPersonas = currentDisplayPersonas();
  $("personaCount").textContent = `${displayPersonas.length} 位`;
  if (!displayPersonas.length) {
    const empty = document.createElement("div");
    empty.className = "persona-empty";
    empty.textContent = "还没有选择本场嘉宾";
    statusContainer.appendChild(empty);
  }
  for (const persona of displayPersonas) {
    statusContainer.appendChild(createPersonaStatusRow(persona));
  }
  for (const persona of state.personas) {
    manageContainer.appendChild(createPersonaManageRow(persona));
  }
  if (!state.currentPersonaId && state.personas.length) {
    state.currentPersonaId = state.personas[0].id;
  }
  renderDiscussionPersonaList();
  renderSessionPersonaList();
  renderPersonaEditor();
}

function ensurePersonaSelection() {
  const activeIds = new Set(state.personas.map((persona) => persona.id));
  state.selectedPersonaIds = new Set(
    Array.from(state.selectedPersonaIds).filter((id) => activeIds.has(id)),
  );
  if (state.selectedPersonaIds.size || !state.personas.length) return;
  state.selectedPersonaIds = new Set(state.personas.map((persona) => persona.id));
}

function createPersonaStatusRow(persona) {
  const row = document.createElement("div");
  const name = persona.display_name || persona.display_name_snapshot;
  const model = displayPersonaModel(persona);
  const categories = persona.categories || [];
  const roleColor = getRoleColor(name);
  row.className = `persona-item role-card persona-status-card tone-${roleColor}`;
  row.innerHTML = `
    <span class="persona-dot ${roleColor}" aria-hidden="true"></span>
    <span class="persona-info">
      <strong>${escapeHtml(name)}</strong>
      <span class="meta">${escapeHtml(categories.join(" / ") || "本场角色")} · ${escapeHtml(model)}</span>
    </span>
  `;
  return row;
}

function currentDisplayPersonas() {
  if (state.currentSession?.personas?.length) return state.currentSession.personas;
  return state.personas.filter((persona) => state.selectedPersonaIds.has(persona.id));
}

function createPersonaManageRow(persona) {
  const row = document.createElement("div");
  const roleColor = getRoleColor(persona.display_name);
  row.className = `persona-item role-card persona-manage-card tone-${roleColor}`;
  if (persona.id === state.currentPersonaId) row.classList.add("active");
  row.innerHTML = `
    <span class="persona-dot ${roleColor}" aria-hidden="true"></span>
    <button type="button" class="persona-edit persona-info">
      <strong>${escapeHtml(persona.display_name)}</strong>
      <span class="meta">${escapeHtml((persona.categories || []).join(" / ") || "未分类")} · ${escapeHtml(persona.model || "默认模型")}</span>
    </button>
  `;
  row.querySelector(".persona-edit").onclick = runAction(() => selectPersona(persona.id));
  return row;
}

function createPersonaCheckRow(persona, selectedSet, onChange) {
  const row = document.createElement("div");
  const roleColor = getRoleColor(persona.display_name);
  row.className = `persona-item role-card persona-check-card tone-${roleColor}`;
  row.innerHTML = `
    <label class="persona-check" title="参与本场">
      <input type="checkbox" value="${escapeHtml(persona.id)}" ${selectedSet.has(persona.id) ? "checked" : ""}>
      <span class="persona-dot ${roleColor}" aria-hidden="true"></span>
    </label>
    <span class="persona-info">
      <strong>${escapeHtml(persona.display_name)}</strong>
      <span class="meta">${escapeHtml((persona.categories || []).join(" / ") || "未分类")} · ${escapeHtml(persona.model || "默认模型")}</span>
    </span>
  `;
  row.querySelector("input").onchange = (event) => onChange(persona.id, event.target.checked);
  return row;
}

function renderDiscussionPersonaList() {
  const container = $("discussionPersonaList");
  container.innerHTML = "";
  $("draftPersonaCount").textContent = `${state.selectedPersonaIds.size} 位`;
  for (const persona of state.personas) {
    container.appendChild(createPersonaCheckRow(persona, state.selectedPersonaIds, (id, checked) => {
      if (checked) {
        state.selectedPersonaIds.add(id);
      } else {
        state.selectedPersonaIds.delete(id);
      }
      renderPersonas();
    }));
  }
}

function renderSessionPersonaList() {
  const container = $("sessionPersonaList");
  container.innerHTML = "";
  $("sessionPersonaPicker").classList.toggle("hidden", !state.sessionPersonaPickerOpen);
  if (!state.currentSession) return;
  const existing = new Set((state.currentSession.personas || []).map((persona) => persona.persona_id));
  const candidates = state.personas.filter((persona) => !existing.has(persona.id));
  if (!candidates.length) {
    const empty = document.createElement("div");
    empty.className = "persona-empty";
    empty.textContent = "所有角色都已在本场讨论中";
    container.appendChild(empty);
    return;
  }
  for (const persona of candidates) {
    container.appendChild(createPersonaCheckRow(persona, state.pendingSessionPersonaIds, (id, checked) => {
      if (checked) {
        state.pendingSessionPersonaIds.add(id);
      } else {
        state.pendingSessionPersonaIds.delete(id);
      }
      renderSessionPersonaList();
    }));
  }
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
  syncPersonaModelPicker();
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
  const groups = groupSessionsByDate(state.sessions);
  for (const group of groups) {
    const section = document.createElement("section");
    section.className = "session-group";
    const label = document.createElement("div");
    label.className = "session-group-label";
    label.textContent = group.label;
    section.appendChild(label);
    for (const session of group.sessions) {
      const button = document.createElement("button");
      button.className = "session-item";
      if (state.currentSession?.id === session.id) button.classList.add("active");
      button.innerHTML = `
        <strong>${escapeHtml(session.title)}</strong>
        <span class="meta">${escapeHtml((session.topic_tags || []).join(" / "))} · ${session.message_count || 0} 条</span>
      `;
      button.onclick = runAction(() => openSession(session.id));
      section.appendChild(button);
    }
    container.appendChild(section);
  }
}

function renderWorkSurface() {
  const hasSession = Boolean(state.currentSession);
  const composing = state.mode === "composing";
  $("conversationEmpty").classList.toggle("hidden", hasSession || composing);
  $("topicEditor").classList.toggle("hidden", hasSession || !composing);
  $("sessionTopicSummary").classList.toggle("hidden", !hasSession);
  $("messageList").classList.toggle("hidden", !hasSession);
  $("messageForm").classList.toggle("hidden", !hasSession);
  if (hasSession) renderSessionTopicSummary();
}

function renderTopicCard(topic) {
  state.topic = topic;
  const hasQuestions = Boolean((topic.clarification_questions || []).length);
  if (hasQuestions) state.topicCardExpanded = true;
  $("topicCard").classList.remove("hidden");
  $("topicCard").classList.toggle("is-compact", !state.topicCardExpanded);
  $("toggleTopicCard").textContent = state.topicCardExpanded ? "收起" : "编辑";
  $("topicCompact").innerHTML = `
    <strong>${escapeHtml(topic.title || "未命名话题")}</strong>
    <span>${escapeHtml(topic.discussion_task || "确认后即可开始讨论。")}</span>
  `;
  $("topicTitle").value = topic.title || "";
  $("topicTags").value = (topic.tags || []).join(", ");
  $("topicTask").value = topic.discussion_task || "";
  const source = topic.refinement_source || "local";
  $("topicSource").textContent = sourceLabels[source] || sourceLabels.local;
  $("topicSource").dataset.source = source;
  renderTopicTags(topic.tags || []);
  renderClarificationQuestions(topic);
}

function readTopicCard() {
  return {
    ...state.topic,
    title: $("topicTitle").value.trim(),
    tags: $("topicTags").value.split(",").map((item) => item.trim()).filter(Boolean),
    discussion_task: $("topicTask").value.trim(),
  };
}

function renderClarificationQuestions(topic) {
  const questions = topic.clarification_questions || [];
  const list = $("topicQuestions");
  const answers = $("clarificationAnswers");
  list.innerHTML = "";
  answers.innerHTML = "";
  if (!questions.length) {
    list.classList.add("hidden");
    $("clarificationBox").classList.add("hidden");
    return;
  }
  list.classList.remove("hidden");
  const title = document.createElement("strong");
  title.textContent = `需要澄清（第 ${topic.clarification_round || 0}/${topic.clarification_round_limit || 3} 轮）`;
  list.appendChild(title);
  for (const [index, question] of questions.entries()) {
    const row = document.createElement("label");
    row.className = "clarification-answer-row";
    const text = document.createElement("span");
    text.textContent = question;
    const input = document.createElement("textarea");
    input.className = "clarification-answer";
    input.rows = 2;
    input.placeholder = `回答问题 ${index + 1}`;
    row.appendChild(text);
    row.appendChild(input);
    answers.appendChild(row);
  }
  $("clarificationBox").classList.remove("hidden");
}

function selectedPersonaIds() {
  return Array.from(state.selectedPersonaIds);
}

async function openSession(id) {
  state.currentSession = await api(`/api/sessions/${id}`);
  state.mode = "session";
  state.sessionPersonaPickerOpen = false;
  state.pendingSessionPersonaIds = new Set();
  renderWorkSurface();
  renderMessages();
  renderPersonas();
  renderSessions();
}

function startDiscussion() {
  state.mode = "composing";
  state.currentSession = null;
  state.topic = null;
  state.topicCardExpanded = false;
  state.sessionPersonaPickerOpen = false;
  state.pendingSessionPersonaIds = new Set();
  $("rawInput").value = "";
  $("topicTitle").value = "";
  $("topicTags").value = "";
  $("topicTask").value = "";
  $("topicCard").classList.add("hidden");
  $("topicQuestions").classList.add("hidden");
  $("clarificationBox").classList.add("hidden");
  renderTopicTags([]);
  renderWorkSurface();
  renderSessions();
  $("rawInput").focus();
}

function toggleTopicCard() {
  if (!state.topic) return;
  state.topicCardExpanded = !state.topicCardExpanded;
  renderTopicCard(readTopicCard());
}

function renderSessionTopicSummary() {
  const session = state.currentSession;
  if (!session) return;
  const tags = session.topic_tags || [];
  $("sessionTopicContent").innerHTML = `
    <div class="session-topic-title">
      <strong>${escapeHtml(session.title || session.refined_topic || "未命名讨论")}</strong>
      <span>${escapeHtml(session.discussion_task || "讨论进行中")}</span>
    </div>
    <div class="topic-tag-row">
      ${tags.map((tag) => `<span class="topic-tag">${escapeHtml(tag)}</span>`).join("")}
    </div>
  `;
  renderSessionPersonaList();
}

function getRoleColor(name) {
  for (const [key, color] of Object.entries(roleColorMap)) {
    if (name && name.includes(key)) return color;
  }
  const hash = Array.from(String(name || "default")).reduce(
    (sum, char) => sum + char.charCodeAt(0),
    0,
  );
  return roleColors[hash % roleColors.length];
}

function getInitial(name) {
  if (!name) return "?";
  return name.charAt(0);
}

function renderMessages() {
  const container = $("messageList");
  container.innerHTML = "";
  const messages = state.currentSession?.messages || [];
  if (!messages.length) {
    container.innerHTML = `
      <div class="empty-state">
        <strong>还没有讨论消息</strong>
        <span>主题确认后，角色发言会在这里展开。</span>
      </div>
    `;
    return;
  }
  for (const message of messages) {
    const row = document.createElement("article");
    const speakerName = message.speaker || message.role || "系统";
    const isUser = message.role === "user" || speakerName === "用户";
    const roleColor = getRoleColor(speakerName);
    row.className = `message ${isUser ? "user" : "assistant"} tone-${roleColor}`;

    if (isUser) {
      row.innerHTML = `
        <div class="avatar user">${escapeHtml(getInitial(speakerName))}</div>
        <div class="message-bubble">
          <div class="speaker">${escapeHtml(speakerName)}</div>
          <div class="message-body">${escapeHtml(message.content)}</div>
        </div>
      `;
    } else {
      row.innerHTML = `
        <div class="avatar ${roleColor}">${escapeHtml(getInitial(speakerName))}</div>
        <div class="message-bubble">
          <div class="speaker">${escapeHtml(speakerName)}</div>
          <div class="message-body">${escapeHtml(message.content)}</div>
          <div class="message-meta">${escapeHtml([message.provider_id, message.model].filter(Boolean).join(" / "))}</div>
        </div>
      `;
    }
    container.appendChild(row);
  }
  container.scrollTop = container.scrollHeight;
}

async function refreshSessions() {
  const query = $("sessionSearch").value.trim();
  state.sessions = await api(`/api/sessions${query ? `?q=${encodeURIComponent(query)}` : ""}`);
  renderSessions();
}

function groupSessionsByDate(sessions) {
  const today = new Date();
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const startOfWeek = new Date(startOfToday);
  startOfWeek.setDate(startOfToday.getDate() - 6);
  const buckets = [
    { label: "📅 今天", sessions: [] },
    { label: "📅 本周", sessions: [] },
    { label: "更早", sessions: [] },
  ];
  for (const session of sessions) {
    const updated = new Date(session.updated_at || session.created_at || 0);
    if (updated >= startOfToday) {
      buckets[0].sessions.push(session);
    } else if (updated >= startOfWeek) {
      buckets[1].sessions.push(session);
    } else {
      buckets[2].sessions.push(session);
    }
  }
  return buckets.filter((bucket) => bucket.sessions.length);
}

function renderTopicTags(tags) {
  const row = $("topicTagRow");
  row.innerHTML = "";
  for (const tag of tags) {
    const chip = document.createElement("span");
    chip.className = "topic-tag";
    chip.textContent = tag;
    row.appendChild(chip);
  }
}

async function refineTopic() {
  const rawInput = $("rawInput").value.trim();
  if (!rawInput) {
    alert("先输入一个讨论话题。");
    return;
  }
  const topic = await api("/api/topic/refine", {
    method: "POST",
    body: JSON.stringify({ raw_input: rawInput }),
  });
  state.topicCardExpanded = Boolean((topic.clarification_questions || []).length);
  renderTopicCard(topic);
}

async function continueRefinement() {
  const rawInput = $("rawInput").value.trim();
  const answers = Array.from(document.querySelectorAll(".clarification-answer"))
    .map((item) => item.value.trim())
    .filter(Boolean);
  if (!rawInput || !state.topic || !answers.length) {
    alert("先回答澄清问题，再继续精炼。");
    return;
  }
  const topic = await api("/api/topic/refine", {
    method: "POST",
    body: JSON.stringify({
      raw_input: rawInput,
      previous_topic: readTopicCard(),
      clarification_answers: answers,
    }),
  });
  state.topicCardExpanded = Boolean((topic.clarification_questions || []).length);
  renderTopicCard(topic);
}

function skipClarification() {
  if (!state.topic) return;
  state.topicCardExpanded = false;
  renderTopicCard({
    ...readTopicCard(),
    clarification_questions: [],
  });
}

$("topicTags").oninput = () => renderTopicTags(
  $("topicTags").value.split(",").map((item) => item.trim()).filter(Boolean),
);

async function createSession() {
  const rawInput = $("rawInput").value.trim();
  if (!rawInput) {
    alert("先输入一个讨论话题。");
    return;
  }
  if (!state.topic) {
    await refineTopic();
    return;
  }
  if ((state.topic.clarification_questions || []).length) {
    alert("请先回答澄清问题，或点击跳过澄清后再开始讨论。");
    return;
  }
  const personaIds = selectedPersonaIds();
  if (!personaIds.length) {
    alert("至少选择一位参与角色。");
    openSettings();
    return;
  }
  const topic = readTopicCard();
  const session = await api("/api/sessions", {
    method: "POST",
    body: JSON.stringify({
      raw_input: rawInput,
      topic,
      persona_ids: personaIds,
    }),
  });
  state.currentSession = session;
  state.mode = "session";
  state.sessionPersonaPickerOpen = false;
  state.pendingSessionPersonaIds = new Set();
  await refreshSessions();
  renderWorkSurface();
  renderMessages();
  renderPersonas();
}

async function sendMessage(event) {
  event.preventDefault();
  if (state.sending) return;
  if (!state.currentSession) {
    alert("请先开始一个讨论，再发送补充消息。");
    return;
  }
  const input = $("messageInput");
  const content = input.value.trim();
  if (!content) return;
  input.value = "";
  state.sending = true;
  setMessageSending(true, "发送中...");
  try {
    await streamSessionMessages(state.currentSession.id, content);
    await refreshSessions();
    renderMessages();
  } catch (error) {
    input.value = content;
    setMessageSending(false, "发送失败，已恢复输入");
    throw error;
  } finally {
    state.sending = false;
    if (!$("messageInput").value.trim()) setMessageSending(false, "");
  }
}

function setMessageSending(isSending, statusText) {
  $("sendMessage").disabled = isSending;
  $("sendMessage").textContent = isSending ? "发送中" : "发送";
  $("messageInput").disabled = isSending;
  $("messageStatus").textContent = statusText || "";
}

async function streamSessionMessages(sessionId, content) {
  const response = await fetch(`/api/sessions/${sessionId}/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  if (!response.body) {
    state.currentSession = await api(`/api/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = consumeSseBuffer(buffer);
  }
  buffer += decoder.decode();
  consumeSseBuffer(`${buffer}\n\n`);
}

function consumeSseBuffer(buffer) {
  const chunks = buffer.split("\n\n");
  const remainder = chunks.pop() || "";
  for (const chunk of chunks) {
    const event = parseSseEvent(chunk);
    if (event) applyStreamEvent(event);
  }
  return remainder;
}

function parseSseEvent(chunk) {
  const dataLines = [];
  let eventType = "message";
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event:")) eventType = line.slice("event:".length).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice("data:".length).trim());
  }
  if (!dataLines.length) return null;
  const payload = JSON.parse(dataLines.join("\n"));
  return { type: payload.type || eventType, ...payload };
}

function applyStreamEvent(event) {
  if (!state.currentSession) return;
  if (event.type === "message" && event.message) {
    state.currentSession.messages = [
      ...(state.currentSession.messages || []),
      event.message,
    ];
    renderMessages();
  }
  if (event.type === "done" && event.session) {
    state.currentSession = event.session;
    renderMessages();
  }
}

async function assignModel() {
  const persona = currentPersona();
  if (!persona) {
    alert("先在角色管理里选中一个角色。");
    return;
  }
  await api("/api/personas/model", {
    method: "POST",
    body: JSON.stringify({
      persona_ids: [persona.id],
      provider_id: $("providerSelect").value,
      model: $("modelSelect").value,
    }),
  });
  state.personas = await api("/api/personas");
  state.personaModelDirty = false;
  renderPersonas();
}

async function addProvider(event) {
  event.preventDefault();
  const editingId = state.editingProviderId;
  const id = editingId || $("providerId").value.trim();
  const models = $("providerModels").value.split(",").map((item) => item.trim()).filter(Boolean);
  if (!id || !models.length) {
    alert("Provider ID 和模型列表不能为空。");
    return;
  }
  const providers = [...(state.config.providers || [])];
  const index = providers.findIndex((item) => item.id === id);
  if (editingId && index < 0) {
    alert("找不到要编辑的 Provider。");
    cancelProviderEdit();
    return;
  }
  if (!editingId && index >= 0) {
    alert("Provider ID 已存在，请点编辑修改。");
    return;
  }
  const existing = index >= 0 ? providers[index] : {};
  const apiKey = $("providerApiKey").value.trim();
  const provider = {
    ...existing,
    id,
    name: $("providerName").value.trim() || id,
    base_url: $("providerBaseUrl").value.trim(),
    api_key: apiKey || (editingId ? existing.api_key : ""),
    available_models: models,
  };
  if (index >= 0) {
    providers[index] = provider;
  } else {
    providers.push(provider);
  }
  const nextConfig = { ...state.config, providers };
  if (!nextConfig.default_model?.provider_id) {
    nextConfig.default_model = { provider_id: id, model: models[0] };
  } else if (nextConfig.default_model.provider_id === id && !models.includes(nextConfig.default_model.model)) {
    nextConfig.default_model = { provider_id: id, model: models[0] };
  }
  state.config = await api("/api/config", {
    method: "POST",
    body: JSON.stringify(nextConfig),
  });
  state.editingProviderId = null;
  $("providerForm").reset();
  renderConfig();
  renderModelPicker();
  renderPersonas();
}

async function deleteProvider(providerId) {
  const provider = providerById(providerId);
  if (!provider) return;
  const label = provider.name || provider.id;
  if (!confirm(`删除 Provider「${label}」？`)) return;
  const providers = (state.config.providers || []).filter((item) => item.id !== providerId);
  const nextConfig = { ...state.config, providers };
  if (nextConfig.default_model?.provider_id === providerId) {
    const first = providers[0];
    nextConfig.default_model = first
      ? { provider_id: first.id, model: defaultProviderModel(first) }
      : {};
  }
  state.config = await api("/api/config", {
    method: "POST",
    body: JSON.stringify(nextConfig),
  });
  if (state.editingProviderId === providerId) {
    state.editingProviderId = null;
    $("providerForm").reset();
  }
  renderConfig();
  renderModelPicker();
  renderPersonas();
}

async function testProviderConnection(providerId, model, providerName) {
  const status = $("providerTestStatus");
  const label = providerName || providerId;
  if (!providerId || !model) {
    status.textContent = "这个 Provider 还没有可测试模型。";
    status.dataset.state = "error";
    return;
  }
  status.textContent = `${label} 测试中...`;
  status.dataset.state = "pending";
  const result = await api("/api/providers/test", {
    method: "POST",
    body: JSON.stringify({ provider_id: providerId, model }),
  });
  if (result.ok) {
    status.textContent = `连接成功：${label} / ${result.message || result.model}`;
    status.dataset.state = "ok";
  } else {
    status.textContent = `连接失败：${label} / ${result.error || "未知错误"}`;
    status.dataset.state = "error";
  }
}

function openSessionPersonaPicker() {
  if (!state.currentSession) return;
  state.sessionPersonaPickerOpen = true;
  state.pendingSessionPersonaIds = new Set();
  renderSessionPersonaList();
}

function closeSessionPersonaPicker() {
  state.sessionPersonaPickerOpen = false;
  state.pendingSessionPersonaIds = new Set();
  renderSessionPersonaList();
}

async function addSessionPersonas() {
  if (!state.currentSession) return;
  const personaIds = Array.from(state.pendingSessionPersonaIds);
  if (!personaIds.length) {
    alert("先选择要加入本场讨论的角色。");
    return;
  }
  state.currentSession = await api(`/api/sessions/${state.currentSession.id}/personas`, {
    method: "POST",
    body: JSON.stringify({ persona_ids: personaIds }),
  });
  state.sessionPersonaPickerOpen = false;
  state.pendingSessionPersonaIds = new Set();
  renderWorkSurface();
  renderMessages();
  renderPersonas();
}

function openSettings() {
  switchSettingsTab("providers");
  $("settingsOverlay").classList.remove("hidden");
  $("settingsDrawer").classList.remove("hidden");
}

function closeSettings() {
  $("settingsOverlay").classList.add("hidden");
  $("settingsDrawer").classList.add("hidden");
}

function switchSettingsTab(tab) {
  for (const button of document.querySelectorAll("[data-settings-tab]")) {
    button.classList.toggle("active", button.dataset.settingsTab === tab);
  }
  for (const panel of document.querySelectorAll("[data-settings-panel]")) {
    panel.classList.toggle("hidden", panel.dataset.settingsPanel !== tab);
  }
}

async function savePersona(event) {
  event.preventDefault();
  const persona = currentPersona();
  if (!persona) return;
  const payload = {
    display_name: $("personaName").value.trim(),
    description: $("personaDescription").value.trim(),
    categories: $("personaCategories").value.split(",").map((item) => item.trim()).filter(Boolean),
    prompt: $("personaPrompt").value,
  };
  if (state.personaModelDirty) {
    payload.provider_id = $("providerSelect").value;
    payload.model = $("modelSelect").value;
  }
  const updated = await api(`/api/personas/${persona.id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  state.personas = state.personas.map((item) => item.id === updated.id ? updated : item);
  state.currentPersonaId = updated.id;
  state.personaModelDirty = false;
  renderPersonas();
}

async function createPersona() {
  const created = await api("/api/personas", {
    method: "POST",
    body: JSON.stringify({ display_name: "新角色" }),
  });
  state.personas = await api("/api/personas");
  state.currentPersonaId = created.id;
  state.selectedPersonaIds.add(created.id);
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
  if (!confirm(`删除角色「${persona.display_name || persona.id}」？`)) return;
  await api(`/api/personas/${persona.id}`, { method: "DELETE" });
  state.personas = await api("/api/personas");
  state.selectedPersonaIds.delete(persona.id);
  state.pendingSessionPersonaIds.delete(persona.id);
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

function runAction(action) {
  return (...args) => {
    Promise.resolve(action(...args)).catch(showError);
  };
}

function showError(error) {
  console.error(error);
  alert(error.message || String(error));
}

$("refreshSessions").onclick = runAction(refreshSessions);
$("sessionSearch").oninput = runAction(() => refreshSessions());
$("newDiscussion").onclick = runAction(startDiscussion);
$("startDiscussion").onclick = runAction(startDiscussion);
$("refineTopic").onclick = runAction(refineTopic);
$("continueRefine").onclick = runAction(continueRefinement);
$("skipClarification").onclick = runAction(skipClarification);
$("toggleTopicCard").onclick = runAction(toggleTopicCard);
$("createSession").onclick = runAction(createSession);
$("messageForm").onsubmit = runAction(sendMessage);
$("sessionAddPersona").onclick = runAction(openSessionPersonaPicker);
$("confirmSessionPersonas").onclick = runAction(addSessionPersonas);
$("cancelSessionPersonas").onclick = runAction(closeSessionPersonaPicker);
$("openSettings").onclick = runAction(openSettings);
$("closeSettings").onclick = runAction(closeSettings);
$("settingsOverlay").onclick = runAction(closeSettings);
for (const button of document.querySelectorAll("[data-settings-tab]")) {
  button.onclick = runAction(() => switchSettingsTab(button.dataset.settingsTab));
}
$("assignModel").onclick = runAction(assignModel);
$("providerForm").onsubmit = runAction(addProvider);
$("cancelProviderEdit").onclick = runAction(cancelProviderEdit);
$("personaForm").onsubmit = runAction(savePersona);
$("newPersona").onclick = runAction(createPersona);
$("clonePersona").onclick = runAction(clonePersona);
$("archivePersona").onclick = runAction(archivePersona);
$("saveConfig").onclick = runAction(saveConfig);

loadAll().catch(showError);
