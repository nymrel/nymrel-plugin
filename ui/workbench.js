import { App, PostMessageTransport } from "@modelcontextprotocol/ext-apps";

const TOOL_INFO = {
  website: {
    name: "nymrel_audit_website",
    title: "Website audit",
    description: "Measure technical signals on one public page.",
    working: "Checking the public page…",
  },
  domains: {
    name: "nymrel_find_domain",
    title: "Domain ideas",
    description: "Explore name ideas and see whether availability was checked.",
    working: "Finding domain ideas…",
  },
  golf: {
    name: "nymrel_golf_bag_gap",
    title: "Golf bag gaps",
    description: "Find spacing between your measured club carries.",
    working: "Comparing carry distances…",
  },
  clip: {
    name: "nymrel_social_clip_score",
    title: "Social clip signals",
    description: "Measure text signals in a short video hook.",
    working: "Measuring the opening…",
  },
};
const STORAGE_KEY = "nymrel-workbench-preferences-v1";
const TOOL_IDS = new Set(Object.keys(TOOL_INFO));
const PLATFORM_IDS = new Set(["tiktok", "reels", "shorts"]);
const app = new App({ name: "Nymrel Public Workbench", version: "1.0.0" }, {});
const state = {
  connected: false,
  tools: null,
  active: "website",
  deepLink: null,
  results: Object.create(null),
  requestIds: Object.create(null),
  preferences: loadPreferences(),
  hostContext: null,
  hostCapabilities: null,
  fullscreenRequested: false,
};

const el = (id) => document.getElementById(id);
const root = el("app-root");
const hostStatus = el("host-status");
const workbench = el("workbench");
const resultBox = el("result");

function loadPreferences() {
  const defaults = { defaultTool: "website", platform: "tiktok", showEvidence: false };
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    return {
      defaultTool: TOOL_IDS.has(saved?.defaultTool) ? saved.defaultTool : defaults.defaultTool,
      platform: PLATFORM_IDS.has(saved?.platform) ? saved.platform : defaults.platform,
      showEvidence: typeof saved?.showEvidence === "boolean" ? saved.showEvidence : defaults.showEvidence,
    };
  } catch {
    return defaults;
  }
}

function savePreferences() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.preferences));
  } catch {
    setStatus(state.active, "Browser storage is unavailable; this preference will last until you close this view.", "error");
  }
}

function setStatus(tool, message, kind = "") {
  const node = el(`status-${tool}`);
  if (!node) return;
  node.textContent = message;
  if (kind) node.dataset.kind = kind;
  else delete node.dataset.kind;
}

function setHostStatus(message, kind = "") {
  hostStatus.textContent = message;
  if (kind) hostStatus.dataset.kind = kind;
  else delete hostStatus.dataset.kind;
}

function safeString(value, fallback = "Not provided") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function resultData(result) {
  if (result && typeof result.structuredContent === "object" && result.structuredContent !== null) return result.structuredContent;
  for (const item of result?.content || []) {
    if (item?.type !== "text" || typeof item.text !== "string") continue;
    try {
      const parsed = JSON.parse(item.text);
      if (parsed && typeof parsed === "object") return parsed;
    } catch { /* plain text remains available in renderError */ }
  }
  return null;
}

function isOpenerContract(value) {
  return value?.version === "1.0" && Array.isArray(value.tools) &&
    value.tools.every((tool) => tool && TOOL_IDS.has(tool.id) && typeof tool.name === "string") &&
    TOOL_IDS.has(value.default_tool);
}

function consumeOpenerResult(result) {
  if (!result || result.isError) return;
  const data = resultData(result);
  if (isOpenerContract(data)) {
    state.tools = data.tools;
    setHostStatus("Connected. Choose a tool and run it when you’re ready.");
  }
}

function hostContextChanged(context) {
  if (!context || typeof context !== "object") return;
  state.hostContext = { ...(state.hostContext || {}), ...context };
  applyTheme(state.hostContext);
  const link = state.hostContext["openai/deepLink"];
  const route = parseDeepLink(link?.url);
  if (route && route !== state.deepLink) {
    state.deepLink = route;
    selectTool(route, { persist: false });
  }
}

function parseDeepLink(path) {
  if (typeof path !== "string") return null;
  try {
    const parsed = new URL(path, "https://nymrel.invalid");
    if (parsed.origin !== "https://nymrel.invalid" || parsed.search || parsed.hash) return null;
    const slug = parsed.pathname.replace(/^\/+|\/+$/g, "");
    return TOOL_IDS.has(slug) ? slug : null;
  } catch {
    return null;
  }
}

function applyTheme(context) {
  if (context.theme === "light" || context.theme === "dark") document.documentElement.style.colorScheme = context.theme;
  for (const [name, value] of Object.entries(context.styles?.variables || {})) {
    if (/^--(?:color|font|border|radius)-[a-z0-9-]+$/.test(name) && typeof value === "string") {
      document.documentElement.style.setProperty(name, value);
    }
  }
}

function setBusy(available) {
  document.querySelectorAll(".submit-button").forEach((button) => {
    button.disabled = !available;
    button.title = available ? "" : "This host has not enabled calls to Nymrel tools.";
  });
  el("add-club").disabled = !available || clubCount() >= 14;
  document.querySelectorAll(".remove-club").forEach((button) => { button.disabled = !available || clubCount() <= 1; });
}

function selectTool(tool, { persist = false } = {}) {
  if (!TOOL_IDS.has(tool)) return;
  state.active = tool;
  for (const tab of document.querySelectorAll(".tool-tab")) {
    const selected = tab.dataset.tool === tool;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  }
  for (const panel of document.querySelectorAll(".tool-form")) panel.hidden = panel.dataset.tool !== tool;
  const config = TOOL_INFO[tool];
  el("tool-title").textContent = state.tools?.find((entry) => entry.id === tool)?.title || config.title;
  el("tool-description").textContent = state.tools?.find((entry) => entry.id === tool)?.description || config.description;
  renderStoredResult(tool);
  if (persist) {
    state.preferences.defaultTool = tool;
    el("default-tool").value = tool;
    savePreferences();
  }
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text);
  return element;
}

function addMetric(parent, label, value) {
  const box = node("div", "metric");
  box.append(node("small", "", label), node("strong", "", value));
  parent.append(box);
}

function addList(parent, title, values, emptyMessage) {
  parent.append(node("h3", "", title));
  if (!Array.isArray(values) || !values.length) {
    parent.append(node("p", "help", emptyMessage));
    return;
  }
  const list = node("ul");
  for (const value of values) list.append(node("li", "", typeof value === "string" ? value : JSON.stringify(value)));
  parent.append(list);
}

function isErrorPayload(payload) {
  return payload?.status === "error" || Boolean(payload?.error);
}

function renderError(parent, result, payload) {
  const detail = payload?.error;
  const message = safeString(detail?.message, "Nymrel could not complete this request.");
  parent.append(node("p", "notice", message));
  if (!payload && Array.isArray(result?.content)) {
    const text = result.content.filter((item) => item?.type === "text").map((item) => item.text).join("\n");
    if (text) parent.append(node("p", "help", text));
  }
}

function renderWebsite(parent, data) {
  const grid = node("div", "result-grid");
  addMetric(grid, "Score", Number.isFinite(data.score) ? `${data.score} / 100` : "Unknown");
  addMetric(grid, "Grade", safeString(data.grade, "Unknown"));
  addMetric(grid, "AI discoverability", safeString(data.ai_discoverability_status, "Unknown"));
  parent.append(grid);
  addList(parent, "Recommended next steps", data.recommendations, "No recommendations were supplied.");
  addList(parent, "Detected structured data", data.schema_detected, "No structured data types were reported.");
  if (typeof data.full_report_url === "string") parent.append(node("p", "help", `Full report: ${data.full_report_url}`));
  parent.append(node("p", "help", "A point-in-time technical measurement, not a ranking forecast or certification."));
}

function renderDomains(parent, data) {
  const suggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
  parent.append(node("p", "help", `${suggestions.length} suggestion${suggestions.length === 1 ? "" : "s"}. Availability is confirmed only where the result says it was checked.`));
  const list = node("ul");
  for (const item of suggestions) {
    const availability = item?.availability_checked === true
      ? (item.available === true ? "Available when checked" : "Unavailable when checked")
      : "Availability not checked";
    const factors = item?.brandability_factors && typeof item.brandability_factors === "object"
      ? ` · ${item.brandability_factors.label_length ?? "?"} letters`
      : "";
    list.append(node("li", "", `${safeString(item?.domain)} — ${availability} · brandability ${Number.isFinite(item?.brandability_score) ? item.brandability_score : "unknown"}${factors}`));
  }
  parent.append(list);
}

function renderGolf(parent, data) {
  const grid = node("div", "result-grid");
  addMetric(grid, "Average gap", Number.isFinite(data.average_gap_yards) ? `${data.average_gap_yards} yd` : "Unknown");
  addMetric(grid, "Problem gaps", Array.isArray(data.problem_gaps) ? data.problem_gaps.length : 0);
  addMetric(grid, "Recommendations", Array.isArray(data.recommendations) ? data.recommendations.length : 0);
  parent.append(grid);
  addList(parent, "Gaps to review", data.problem_gaps, "No problem gaps were reported.");
  addList(parent, "Suggestions", data.recommendations, "No recommendations were supplied.");
}

function renderClip(parent, data) {
  const signals = data.signals && typeof data.signals === "object" ? data.signals : {};
  const grid = node("div", "result-grid");
  addMetric(grid, "Hook score", Number.isFinite(data.hook_score) ? `${data.hook_score} / 100` : "Unknown");
  addMetric(grid, "Strength", safeString(data.hook_strength, "Unknown"));
  addMetric(grid, "Opening words", Number.isInteger(signals.opening_word_count) ? signals.opening_word_count : "Unknown");
  addMetric(grid, "Word range", Array.isArray(signals.platform_word_range) ? signals.platform_word_range.join("–") : "Unknown");
  addMetric(grid, "Within range", typeof signals.total_word_count_in_platform_range === "boolean" ? (signals.total_word_count_in_platform_range ? "Yes" : "No") : "Unknown");
  parent.append(grid);
  const measured = [
    ["Opens with a hook pattern", signals.opens_with_hook_pattern],
    ["Addresses the viewer", signals.addresses_viewer],
    ["Includes curiosity", signals.has_curiosity_signal],
    ["Opening contains a number", signals.opening_contains_number],
  ].filter(([, value]) => typeof value === "boolean").map(([label, value]) => `${label}: ${value ? "yes" : "no"}`);
  addList(parent, "Measured signals", measured, "No signal details were returned.");
  addList(parent, "Possible edits", data.suggested_edits, "No suggested edits were supplied.");
  parent.append(node("p", "help", "This score measures text patterns; it does not predict views, reach, or retention."));
}

function conversationSummary(tool, data) {
  const title = TOOL_INFO[tool].title;
  if (tool === "website") return `${title}: score ${Number.isFinite(data.score) ? data.score : "unknown"}/100, grade ${safeString(data.grade, "unknown")}. ${Array.isArray(data.recommendations) ? data.recommendations.slice(0, 3).join("; ") : ""}`;
  if (tool === "domains") return `${title}: ${Array.isArray(data.suggestions) ? data.suggestions.map((item) => `${item.domain} (${item.availability_checked ? (item.available ? "available when checked" : "unavailable when checked") : "not checked"})`).join(", ") : "no suggestions"}.`;
  if (tool === "golf") return `${title}: average gap ${Number.isFinite(data.average_gap_yards) ? `${data.average_gap_yards} yards` : "unknown"}. ${Array.isArray(data.problem_gaps) ? data.problem_gaps.join("; ") : ""}`;
  return `${title}: score ${Number.isFinite(data.hook_score) ? data.hook_score : "unknown"}/100, strength ${safeString(data.hook_strength, "unknown")}. This is a text signal, not a performance prediction.`;
}

function renderStoredResult(tool) {
  const entry = state.results[tool];
  if (!entry) {
    resultBox.replaceChildren();
    resultBox.hidden = true;
    return;
  }
  resultBox.replaceChildren();
  resultBox.hidden = false;
  const head = node("div", "result-title");
  head.append(node("h2", "", entry.error ? "Request needs attention" : `${TOOL_INFO[tool].title} result`));
  const useButton = node("button", "quiet", "Use result in conversation");
  const updateCapability = state.hostCapabilities?.updateModelContext;
  const supportsTextContext = Boolean(updateCapability && Object.prototype.hasOwnProperty.call(updateCapability, "text"));
  useButton.disabled = !supportsTextContext || entry.error;
  useButton.title = supportsTextContext ? "Add a short summary to the conversation after you choose." : "This host does not support adding app results to the conversation.";
  useButton.addEventListener("click", () => useResultInConversation(tool, entry));
  head.append(useButton);
  resultBox.append(head);
  if (entry.error) renderError(resultBox, entry.result, entry.data);
  else if (entry.data && typeof entry.data === "object") {
    if (tool === "website") renderWebsite(resultBox, entry.data);
    if (tool === "domains") renderDomains(resultBox, entry.data);
    if (tool === "golf") renderGolf(resultBox, entry.data);
    if (tool === "clip") renderClip(resultBox, entry.data);
  } else renderError(resultBox, entry.result, null);
  const evidence = node("pre");
  evidence.dataset.testid = "evidence";
  evidence.textContent = JSON.stringify(entry.data || entry.result, null, 2);
  evidence.hidden = !state.preferences.showEvidence;
  resultBox.append(evidence);
}

async function useResultInConversation(tool, entry) {
  if (!entry?.data || !state.hostCapabilities?.updateModelContext?.text) return;
  const button = resultBox.querySelector(".result-title button");
  if (button) button.disabled = true;
  setStatus(tool, "Adding the result summary to the conversation…");
  try {
    await app.updateModelContext({ content: [{ type: "text", text: conversationSummary(tool, entry.data) }] }, { timeout: 8000 });
    setStatus(tool, "The result summary is now in the conversation.", "success");
  } catch {
    setStatus(tool, "This host could not add the result summary. The result is still shown here.", "error");
  } finally {
    renderStoredResult(tool);
  }
}

function clubCount() {
  return el("club-list").querySelectorAll(".club-row").length;
}

function addClubRow(values = {}) {
  if (clubCount() >= 14) return;
  const index = clubCount() + 1;
  const row = node("div", "club-row");
  const name = document.createElement("input");
  name.type = "text"; name.className = "club-name"; name.maxLength = 40; name.placeholder = "7 iron"; name.setAttribute("aria-label", `Club ${index} name`); name.value = values.name || "";
  const carry = document.createElement("input");
  carry.type = "number"; carry.className = "club-carry"; carry.min = "1"; carry.max = "400"; carry.step = "1"; carry.inputMode = "numeric"; carry.placeholder = "165"; carry.setAttribute("aria-label", `Club ${index} carry distance in yards`); carry.value = values.carry_distance_yards ?? "";
  const loft = document.createElement("input");
  loft.type = "number"; loft.className = "club-loft loft-field"; loft.min = "0"; loft.max = "80"; loft.step = "0.5"; loft.placeholder = "Optional loft"; loft.setAttribute("aria-label", `Club ${index} loft in degrees`); loft.value = values.loft_degrees ?? "";
  const remove = node("button", "quiet remove-club remove", "×");
  remove.type = "button"; remove.setAttribute("aria-label", `Remove club ${index}`); remove.addEventListener("click", () => { if (clubCount() > 1) { row.remove(); refreshClubRows(); } });
  row.append(name, carry, loft, remove);
  el("club-list").append(row);
  refreshClubRows();
}

function refreshClubRows() {
  [...el("club-list").querySelectorAll(".club-row")].forEach((row, index) => {
    for (const input of row.querySelectorAll("input")) {
      const label = input.classList.contains("club-name") ? "name" : input.classList.contains("club-carry") ? "carry distance in yards" : "loft in degrees";
      input.setAttribute("aria-label", `Club ${index + 1} ${label}`);
    }
    row.querySelector("button").setAttribute("aria-label", `Remove club ${index + 1}`);
  });
  el("club-count").textContent = `${clubCount()} of 14`;
  el("add-club").disabled = !state.connected || clubCount() >= 14;
  document.querySelectorAll(".remove-club").forEach((button) => { button.disabled = !state.connected || clubCount() <= 1; });
}

function readGolfForm() {
  const clubs = [...el("club-list").querySelectorAll(".club-row")].map((row, index) => {
    const name = row.querySelector(".club-name").value.trim();
    const carryRaw = row.querySelector(".club-carry").value;
    const loftRaw = row.querySelector(".club-loft").value;
    if (!name) throw new Error(`Enter a name for club ${index + 1}.`);
    if (!carryRaw || !Number.isInteger(Number(carryRaw)) || Number(carryRaw) < 1 || Number(carryRaw) > 400) throw new Error(`Enter a whole carry distance from 1 to 400 yards for club ${index + 1}.`);
    const club = { name, carry_distance_yards: Number(carryRaw) };
    if (loftRaw !== "") {
      if (!Number.isFinite(Number(loftRaw)) || Number(loftRaw) < 0 || Number(loftRaw) > 80) throw new Error(`Enter a loft from 0 to 80 degrees for club ${index + 1}, or leave it blank.`);
      club.loft_degrees = Number(loftRaw);
    }
    return club;
  });
  if (clubs.length < 1 || clubs.length > 14) throw new Error("Add between 1 and 14 clubs.");
  return { clubs };
}

function formArguments(tool) {
  if (tool === "website") {
    const url = el("website-url").value.trim();
    let parsed;
    try { parsed = new URL(url); } catch { throw new Error("Enter a full public web address, such as https://example.com."); }
    if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname) throw new Error("Use a full http:// or https:// web address.");
    if (parsed.username || parsed.password) throw new Error("Use a public URL without embedded credentials.");
    return { url };
  }
  if (tool === "domains") {
    const keyword = el("domain-idea").value.trim();
    if (!keyword) throw new Error("Enter a word or short idea for the domain name.");
    const rawTlds = el("domain-tlds").value.trim();
    const tlds = rawTlds ? rawTlds.split(",").map((item) => item.trim().toLowerCase()) : [];
    if (tlds.some((item) => !/^\.[a-z]{2,24}$/.test(item))) throw new Error("Enter domain endings like .com or .io, separated by commas.");
    return { keyword_or_concept: keyword, ...(tlds.length ? { tlds } : {}) };
  }
  if (tool === "golf") return readGolfForm();
  const transcript = el("clip-transcript").value.trim();
  if (!transcript) throw new Error("Paste the words spoken in the clip.");
  return { transcript_text: transcript, target_platform: el("clip-platform").value };
}

async function runTool(tool) {
  if (!state.connected || !state.hostCapabilities?.serverTools) {
    setStatus(tool, "This host has not enabled Nymrel tool calls.", "error");
    return;
  }
  let args;
  try { args = formArguments(tool); }
  catch (error) { setStatus(tool, error.message, "error"); return; }
  const requestId = (state.requestIds[tool] || 0) + 1;
  state.requestIds[tool] = requestId;
  const submit = el(`form-${tool}`).querySelector(".submit-button");
  submit.disabled = true;
  setStatus(tool, TOOL_INFO[tool].working);
  try {
    const result = await app.callServerTool({ name: TOOL_INFO[tool].name, arguments: args }, { timeout: 30000, maxTotalTimeout: 30000 });
    if (state.requestIds[tool] !== requestId) return;
    const data = resultData(result);
    state.results[tool] = { result, data, error: Boolean(result?.isError) || isErrorPayload(data) };
    setStatus(tool, state.results[tool].error ? "Nymrel returned an error. Review the details below; you can correct the form and try again." : "Result ready. Nothing was changed outside this workspace.", state.results[tool].error ? "error" : "success");
    if (state.active === tool) renderStoredResult(tool);
  } catch (error) {
    if (state.requestIds[tool] !== requestId) return;
    state.results[tool] = { result: null, data: { error: { message: error?.code === "RequestTimeout" ? "Nymrel did not respond in time. You can try again." : "The host could not reach Nymrel. Check the connection and try again." } }, error: true };
    setStatus(tool, "The request did not finish. You can try again when ready.", "error");
    if (state.active === tool) renderStoredResult(tool);
  } finally {
    if (state.requestIds[tool] === requestId) submit.disabled = !state.hostCapabilities?.serverTools;
  }
}

function wireForms() {
  for (const tool of TOOL_IDS) {
    el(`form-${tool}`).addEventListener("submit", (event) => { event.preventDefault(); runTool(tool); });
  }
  document.querySelectorAll(".tool-tab").forEach((tab) => {
    tab.addEventListener("click", () => selectTool(tab.dataset.tool));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const tabs = [...document.querySelectorAll(".tool-tab")];
      const current = tabs.indexOf(tab);
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (current + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length;
      tabs[next].focus(); tabs[next].click();
    });
  });
  el("add-club").addEventListener("click", () => addClubRow());
  el("clip-platform").addEventListener("change", () => { state.preferences.platform = el("clip-platform").value; el("default-platform").value = state.preferences.platform; savePreferences(); });
  el("default-tool").addEventListener("change", () => { state.preferences.defaultTool = el("default-tool").value; savePreferences(); });
  el("default-platform").addEventListener("change", () => { state.preferences.platform = el("default-platform").value; el("clip-platform").value = state.preferences.platform; savePreferences(); });
  el("show-evidence").addEventListener("change", () => { state.preferences.showEvidence = el("show-evidence").checked; savePreferences(); renderStoredResult(state.active); });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.activeElement?.matches("input,textarea,select")) document.activeElement.blur();
  });
}

function showReady(context) {
  state.connected = true;
  state.hostContext = context || {};
  state.hostCapabilities = app.getHostCapabilities() || {};
  hostStatus.hidden = true;
  workbench.hidden = false;
  root.setAttribute("aria-busy", "false");
  el("default-tool").value = state.preferences.defaultTool;
  el("default-platform").value = state.preferences.platform;
  el("clip-platform").value = state.preferences.platform;
  el("show-evidence").checked = state.preferences.showEvidence;
  applyTheme(state.hostContext);
  const initialRoute = parseDeepLink(state.hostContext["openai/deepLink"]?.url);
  if (initialRoute) state.deepLink = initialRoute;
  selectTool(initialRoute || state.preferences.defaultTool);
  setBusy(Boolean(state.hostCapabilities.serverTools));
  if (!state.hostCapabilities.serverTools) {
    setHostStatus("This host opened the workbench but did not enable calls to Nymrel tools. Your inputs stay in this view.", "error");
    hostStatus.hidden = false;
  }
  requestFullscreenOnce();
}

async function requestFullscreenOnce() {
  if (state.fullscreenRequested) return;
  const context = app.getHostContext() || state.hostContext || {};
  if (context.displayMode !== "inline" || !Array.isArray(context.availableDisplayModes) || !context.availableDisplayModes.includes("fullscreen")) return;
  state.fullscreenRequested = true;
  try {
    const actual = await app.requestDisplayMode({ mode: "fullscreen" }, { timeout: 5000 });
    if (actual?.mode) state.hostContext = { ...(state.hostContext || {}), displayMode: actual.mode };
  } catch {
    // Inline remains usable if a host declines the optional fullscreen request.
  }
}

async function boot() {
  wireForms();
  addClubRow();
  app.ontoolresult = consumeOpenerResult;
  app.onhostcontextchanged = hostContextChanged;
  const transport = new PostMessageTransport(window.parent, window.parent);
  try {
    const contextPromise = app.connect(transport).then(() => app.getHostContext() || {});
    const context = await Promise.race([
      contextPromise,
      new Promise((_, reject) => setTimeout(() => reject(new Error("Host connection timed out")), 7000)),
    ]);
    showReady(context);
  } catch {
    await app.close().catch(() => {});
    root.setAttribute("aria-busy", "false");
    setHostStatus("The Nymrel workbench could not connect to its host. Reopen it from ChatGPT or try again in a moment.", "error");
    const retry = node("button", "quiet", "Reconnect");
    retry.type = "button";
    retry.addEventListener("click", () => window.location.reload());
    hostStatus.append(document.createTextNode(" "), retry);
  }
}

boot();
