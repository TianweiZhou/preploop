// PrepLoop frontend. Plain JS, no build step.

const $ = (sel) => document.querySelector(sel);

// Escape user content before putting it in HTML.
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// ---- Icons (inline SVG, 24x24, drawn with currentColor) ----

const ICON_PATHS = {
  logo: '<path d="M8 12a4 4 0 0 1 6.8-2.8L16 10.5M16 7v3.5h-3.5M16 12a4 4 0 0 1-6.8 2.8L8 13.5M8 17v-3.5h3.5"/>',
  library: '<path d="M4 19.5V5a2 2 0 0 1 2-2h14v16H6.5A2.5 2.5 0 0 0 4 21.5Z"/><path d="M8 7h8M8 11h6"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  swap: '<path d="M7 4v16M3 8l4-4 4 4M17 20V4M13 16l4 4 4-4"/>',
  sparkles: '<path d="M11 3l1.9 5.1L18 10l-5.1 1.9L11 17l-1.9-5.1L4 10l5.1-1.9Z"/><path d="M19 15l.7 1.8 1.8.7-1.8.7L19 20l-.7-1.8-1.8-.7 1.8-.7Z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  pencil: '<path d="M4 20h4L19 9l-4-4L4 16v4Z"/><path d="m14 6 4 4"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  logout: '<path d="M15 4h4v16h-4M10 17l5-5-5-5M15 12H3"/>',
  check: '<path d="m5 12 5 5L20 7"/>',
  checkCircle: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  alert: '<path d="M12 3 2 20h20Z"/><path d="M12 10v4M12 17h.01"/>',
  message: '<path d="M4 5h16v11H9l-5 4Z"/>',
  quote: '<path d="M7 7h4v4c0 3-1.5 5-4 6M15 7h4v4c0 3-1.5 5-4 6"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>',
  download: '<path d="M12 4v12M7 11l5 5 5-5M4 20h16"/>',
  file: '<path d="M14 3H6v18h12V7Z"/><path d="M14 3v4h4M9 13h6M9 17h4"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  repeat: '<path d="M4 12a8 8 0 0 1 14-5.3L20 9M20 4v5h-5M20 12a8 8 0 0 1-14 5.3L4 15M4 20v-5h5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  trophy: '<path d="M8 4h8v5a4 4 0 0 1-8 0Z"/><path d="M8 6H4v1a4 4 0 0 0 4 4M16 6h4v1a4 4 0 0 1-4 4M12 13v4M8 20h8M10 17h4"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5Z"/><path d="m3 13 9 5 9-5"/>',
  trend: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
  flame: '<path d="M12 3c1 4 5 5.5 5 10a5 5 0 0 1-10 0c0-3 2-4 2-6.5 1 1 2 2 3 2 0-2-1-3.5 0-5.5Z"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  play: '<path d="M7 4v16l13-8Z"/>',
  inbox: '<path d="M3 13h5l1.5 3h5L16 13h5"/><path d="M5 5h14l2 8v6H3v-6Z"/>',
};

function icon(name, cls = "") {
  return `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[name] || ""}</svg>`;
}

// Static markup uses <i data-icon="name">; swap those for real SVGs.
function fillIcons(root = document) {
  for (const el of root.querySelectorAll("i[data-icon]")) el.outerHTML = icon(el.dataset.icon);
}
fillIcons();

// ---- Small UI helpers ----

function toast(message, type = "success") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `${icon(type === "error" ? "alert" : "checkCircle")}<span>${esc(message)}</span>`;
  $("#toasts").append(el);
  setTimeout(() => el.classList.add("leaving"), 2600);
  setTimeout(() => el.remove(), 3000);
}

// Promise-based confirm in our own dialog. Resolves true/false.
function confirmDialog(title, text, okLabel = "Confirm", danger = false) {
  const dialog = $("#confirm-dialog");
  $("#confirm-title").textContent = title;
  $("#confirm-text").textContent = text;
  const ok = $("#confirm-ok");
  ok.textContent = okLabel;
  ok.className = `btn ${danger ? "danger" : "primary"}`;
  dialog.showModal();
  return new Promise((resolve) => {
    const done = (value) => {
      ok.onclick = $("#confirm-cancel").onclick = dialog.onclose = null;
      dialog.close();
      resolve(value);
    };
    ok.onclick = () => done(true);
    $("#confirm-cancel").onclick = () => done(false);
    dialog.onclose = () => done(false);
  });
}

// Close a modal by clicking the dark backdrop (not the form, so edits aren't lost).
for (const dialog of document.querySelectorAll("dialog.modal:not(#q-dialog)")) {
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog) dialog.close();
  });
}

// ---- API ----

// Small fetch wrapper: JSON in and out, throws with the server's message.
async function api(path, options = {}) {
  const opts = { credentials: "same-origin", ...options };
  if (opts.body && typeof opts.body !== "string" && !(opts.body instanceof FormData)) {
    opts.headers = { "Content-Type": "application/json", ...opts.headers };
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, opts);
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(errorMessage(data, res.status));
    err.status = res.status;
    // Session expired somewhere in the app: back to login.
    if (res.status === 401 && !path.startsWith("/api/me") && !path.startsWith("/api/auth")) showLogin();
    throw err;
  }
  return data;
}

function errorMessage(data, status) {
  const detail = data && data.detail;
  // FastAPI validation errors come as a list.
  if (Array.isArray(detail)) {
    return detail.map((d) => `${d.loc?.slice(-1)[0] ?? "field"}: ${d.msg}`).join("; ");
  }
  return detail ? String(detail) : `Request failed (${status})`;
}

function show(id) {
  for (const el of ["#loading", "#login", "#app"]) $(el).hidden = el !== id;
}

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "never";
}

function formatDateTime(iso) {
  return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function plural(n, word) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

// ---- Auth ----

let googleReady = false;

async function showLogin() {
  show("#login");
  if (googleReady) return;
  const { googleClientId } = await api("/api/config");
  // The Google script loads async, wait for it.
  while (!window.google?.accounts?.id) await new Promise((r) => setTimeout(r, 50));
  google.accounts.id.initialize({ client_id: googleClientId, callback: onGoogleCredential });
  google.accounts.id.renderButton($("#google-button"), {
    theme: "outline", size: "large", shape: "pill", text: "continue_with", width: 300,
  });
  googleReady = true;
}

async function onGoogleCredential(response) {
  const errorEl = $("#login-error");
  errorEl.hidden = true;
  try {
    const { email } = await api("/api/auth/google", { method: "POST", body: { credential: response.credential } });
    showApp(email);
  } catch (err) {
    errorEl.textContent = err.status === 403 ? "This Google account isn't allowed." : err.message;
    errorEl.hidden = false;
  }
}

function showApp(email) {
  $("#user-email").textContent = email;
  $("#user-avatar").textContent = email.charAt(0).toUpperCase();
  show("#app");
  loadLibrary();
}

$("#logout").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  window.google?.accounts?.id.disableAutoSelect();
  showLogin();
});

// ---- Tabs ----

function switchView(view) {
  for (const t of document.querySelectorAll(".tab")) t.classList.toggle("active", t.dataset.view === view);
  for (const v of ["library", "practice", "io"]) $(`#view-${v}`).hidden = v !== view;
  // Ratings, feedback, and imports change the list, so refresh it.
  if (view === "library" && libraryStale) {
    libraryStale = false;
    loadLibrary();
  }
}

for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => switchView(tab.dataset.view));
}

// ---- Shared bits: confidence, AI scores, answers, tags ----

const CONF_LABELS = { 1: "Lost", 2: "Shaky", 3: "Okay", 4: "Good", 5: "Nailed it" };
const SCORE_LABELS = { clarity: "Clarity", structure: "Structure", specificity: "Specificity" };

function confidencePill(n) {
  const dots = [1, 2, 3, 4, 5].map((i) => `<span class="${i <= n ? "on" : ""}"></span>`).join("");
  return `<span class="conf conf-${n}" title="Confidence ${n}/5"><span class="conf-dots">${dots}</span>${CONF_LABELS[n]}</span>`;
}

function scoreLevel(avg) {
  return avg >= 4 ? "high" : avg >= 3 ? "mid" : "low";
}

function avgScore(scores) {
  const values = Object.keys(SCORE_LABELS).map((k) => Number(scores[k]) || 0);
  return values.reduce((a, b) => a + b, 0) / values.length;
}

// Small "AI 3.7" pill for cards, with the breakdown on hover.
function aiPill(last) {
  if (!last) return "";
  const avg = avgScore(last.scores);
  const detail = Object.entries(SCORE_LABELS).map(([k, l]) => `${l} ${last.scores[k]}`).join(", ");
  return `<span class="ai-pill ${scoreLevel(avg)}" title="AI review: ${esc(detail)} (${esc(last.modelId)}, ${esc(formatDateTime(last.createdAt))})">
    ${icon("sparkles")} AI ${avg.toFixed(1)}</span>`;
}

// Full breakdown, used in practice once the answer is revealed.
function scoreChipsHtml(last) {
  if (!last) return "";
  const chips = Object.entries(SCORE_LABELS).map(([k, label]) =>
    `<span class="score-chip ${scoreLevel(Number(last.scores[k]))}">${label} <b>${Number(last.scores[k]) || 0}</b></span>`).join("");
  return `<div class="score-chips">${aiPill(last)}${chips}</div>`;
}

// Answer, STAR parts, and notes. Shared by the library and practice views.
function answerHtml(q) {
  const star = q.star && Object.values(q.star).some(Boolean)
    ? `<dl class="star">${["situation", "task", "action", "result"]
        .filter((k) => q.star[k])
        .map((k) => `<div><dt>${k}</dt><dd>${esc(q.star[k])}</dd></div>`).join("")}</dl>`
    : "";
  return `
    ${q.answer ? `<p class="answer">${esc(q.answer)}</p>` : `<p class="muted">No answer written yet.</p>`}
    ${star}
    ${q.notes ? `<p class="notes"><strong>Notes</strong> ${esc(q.notes)}</p>` : ""}`;
}

function tagsHtml(tags) {
  return tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("");
}

function typeBadge(type) {
  return `<span class="badge ${esc(type)}">${type === "behavioral" ? "Behavioral" : "Technical"}</span>`;
}

function hasAnswer(q) {
  return Boolean(q.answer || (q.star && Object.values(q.star).some(Boolean)));
}

// ---- Library ----

let questions = []; // the currently shown (filtered) list
let allQuestions = []; // everything, for stats and tag lists
let libraryStale = false; // set after practice ratings, feedback, or imports

function filterParams() {
  const params = new URLSearchParams();
  const q = $("#f-q").value.trim();
  if (q) params.set("q", q);
  if ($("#f-type").value) params.set("type", $("#f-type").value);
  if ($("#f-tag").value) params.set("tag", $("#f-tag").value);
  if ($("#f-conf").value) {
    const [min, max] = $("#f-conf").value.split("-");
    params.set("min_conf", min);
    params.set("max_conf", max);
  }
  const [sort, order] = $("#f-sort").value.split(":");
  params.set("sort", sort);
  params.set("order", order);
  return params;
}

function filtersActive() {
  return Boolean($("#f-q").value.trim() || $("#f-type").value || $("#f-tag").value || $("#f-conf").value);
}

// Reload the list. refreshAll also reloads stats and tag dropdowns.
async function loadLibrary({ refreshAll = true } = {}) {
  const status = $("#lib-status");
  try {
    if (refreshAll) {
      allQuestions = await api("/api/questions");
      fillTagFilter(allQuestions);
      renderStats();
    }
    questions = await api(`/api/questions?${filterParams()}`);
    renderList();
    status.textContent = filtersActive()
      ? `Showing ${questions.length} of ${plural(allQuestions.length, "question")}`
      : plural(questions.length, "question");
  } catch (err) {
    status.textContent = err.message;
  }
}

function renderStats() {
  const total = allQuestions.length;
  const avg = total ? allQuestions.reduce((s, q) => s + q.confidence, 0) / total : 0;
  const weak = allQuestions.filter((q) => q.confidence <= 2).length;
  const weekAgo = Date.now() - 7 * 86400000;
  const week = allQuestions.filter((q) => q.lastPracticed && new Date(q.lastPracticed) > weekAgo).length;
  const tiles = [
    { icon: "layers", label: "Questions", value: total, note: `${allQuestions.filter((q) => q.type === "behavioral").length} behavioral` },
    { icon: "trend", label: "Avg confidence", value: total ? avg.toFixed(1) : "–", note: "out of 5" },
    { icon: "flame", label: "Need work", value: weak, note: "confidence 1–2", tone: weak ? "warn" : "" },
    { icon: "calendar", label: "Practiced", value: week, note: "in the last 7 days" },
  ];
  $("#lib-stats").innerHTML = tiles.map((t) => `
    <div class="stat ${t.tone || ""}">
      <span class="stat-icon">${icon(t.icon)}</span>
      <div>
        <div class="stat-label">${t.label}</div>
        <div class="stat-value">${t.value}</div>
        <div class="stat-note">${t.note}</div>
      </div>
    </div>`).join("");
}

// Rebuild the tag dropdowns (library and practice), keeping the current choice.
function fillTagFilter(all) {
  const tags = [...new Set(all.flatMap((q) => q.tags))].sort((a, b) => a.localeCompare(b));
  for (const select of [$("#f-tag"), $("#p-tag")]) {
    const current = select.value;
    select.innerHTML = `<option value="">All tags</option>` +
      tags.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("");
    if (tags.includes(current)) select.value = current;
  }
}

function renderList() {
  const list = $("#q-list");
  if (!questions.length) {
    list.innerHTML = filtersActive()
      ? `<div class="panel empty">
          <span class="empty-icon">${icon("search")}</span>
          <h3>No matches</h3><p>Try a different search or clear the filters.</p>
        </div>`
      : `<div class="panel empty">
          <span class="empty-icon">${icon("inbox")}</span>
          <h3>Your library is empty</h3>
          <p>Add your first question, or import a CSV from the Import / Export tab.</p>
          <button class="btn primary" data-action="add">${icon("plus")} Add question</button>
        </div>`;
    return;
  }
  list.innerHTML = questions.map((q) => `
    <article class="q-card" data-id="${esc(q.id)}">
      <div class="q-top">
        <div class="q-badges">
          ${typeBadge(q.type)}
          ${confidencePill(q.confidence)}
          ${aiPill(q.lastFeedback)}
        </div>
        <div class="q-actions">
          ${hasAnswer(q) ? `<button class="icon-btn" data-action="feedback" title="AI feedback" aria-label="AI feedback">${icon("sparkles")}</button>` : ""}
          <button class="icon-btn" data-action="edit" title="Edit" aria-label="Edit">${icon("pencil")}</button>
          <button class="icon-btn danger" data-action="delete" title="Delete" aria-label="Delete">${icon("trash")}</button>
        </div>
      </div>
      <h3 class="q-title">${esc(q.question)}</h3>
      ${q.tags.length ? `<div class="tags">${tagsHtml(q.tags)}</div>` : ""}
      <details class="q-answer">
        <summary>Show answer</summary>
        <div class="answer-box">${answerHtml(q)}</div>
      </details>
      <div class="q-foot">
        <span>${icon("repeat")} Practiced ${q.timesPracticed}×</span>
        <span>${icon("clock")} Last ${formatDate(q.lastPracticed)}</span>
        <span>${icon("calendar")} Added ${formatDate(q.createdAt)}</span>
      </div>
    </article>`).join("");
}

// Card buttons (and the empty-state "Add question").
$("#q-list").addEventListener("click", async (e) => {
  const button = e.target.closest("button[data-action]");
  if (!button) return;
  if (button.dataset.action === "add") return openForm();
  const id = button.closest(".q-card").dataset.id;
  const q = questions.find((x) => x.id === id);
  if (button.dataset.action === "edit") openForm(q);
  if (button.dataset.action === "feedback") openFeedbackDialog(q);
  if (button.dataset.action === "delete") {
    const ok = await confirmDialog("Delete this question?", q.question, "Delete", true);
    if (!ok) return;
    try {
      await api(`/api/questions/${encodeURIComponent(id)}`, { method: "DELETE" });
      toast("Question deleted");
      loadLibrary();
    } catch (err) {
      toast(err.message, "error");
    }
  }
});

// Filters: search waits for typing to pause, the rest reload right away.
let searchTimer;
$("#f-q").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadLibrary({ refreshAll: false }), 250);
});
for (const id of ["#f-type", "#f-tag", "#f-conf", "#f-sort"]) {
  $(id).addEventListener("change", () => loadLibrary({ refreshAll: false }));
}

// ---- Add / edit form ----

const form = $("#q-form");
const fields = form.elements; // safer than form.action etc., which clash with built-ins
let editingId = null;

function toggleStar() {
  $("#star-fields").hidden = fields.type.value !== "behavioral";
}
fields.type.addEventListener("change", toggleStar);

function openForm(q = null) {
  editingId = q ? q.id : null;
  form.reset();
  $("#q-form-title").textContent = q ? "Edit question" : "Add question";
  $("#q-form-error").hidden = true;
  if (q) {
    fields.type.value = q.type;
    fields.confidence.value = String(q.confidence);
    fields.question.value = q.question;
    fields.answer.value = q.answer;
    fields.tags.value = q.tags.join(", ");
    fields.notes.value = q.notes;
    for (const k of ["situation", "task", "action", "result"]) fields[k].value = q.star?.[k] ?? "";
  }
  toggleStar();
  $("#q-dialog").showModal();
  fields.question.focus();
}

$("#add-btn").addEventListener("click", () => openForm());
$("#q-cancel").addEventListener("click", () => $("#q-dialog").close());
$("#q-close").addEventListener("click", () => $("#q-dialog").close());

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = {
    type: fields.type.value,
    question: fields.question.value,
    answer: fields.answer.value,
    confidence: Number(fields.confidence.value),
    tags: fields.tags.value.split(",").map((t) => t.trim()).filter(Boolean),
    notes: fields.notes.value,
  };
  if (body.type === "behavioral") {
    body.star = Object.fromEntries(["situation", "task", "action", "result"].map((k) => [k, fields[k].value]));
  }
  try {
    if (editingId) {
      await api(`/api/questions/${encodeURIComponent(editingId)}`, { method: "PUT", body });
    } else {
      await api("/api/questions", { method: "POST", body });
    }
    $("#q-dialog").close();
    toast(editingId ? "Changes saved" : "Question added");
    loadLibrary();
  } catch (err) {
    $("#q-form-error").textContent = err.message;
    $("#q-form-error").hidden = false;
  }
});

// ---- AI feedback ----

function listHtml(items, iconName, tone) {
  if (!items.length) return `<p class="muted small">Nothing here.</p>`;
  return `<ul class="fb-list ${tone}">${items.map((i) => `<li>${icon(iconName)}<span>${esc(i)}</span></li>`).join("")}</ul>`;
}

function feedbackHtml({ feedback: fb, model_id, created_at, cached }) {
  const avg = avgScore(fb.scores);
  const level = scoreLevel(avg);
  const verdict = { high: "Strong answer", mid: "Solid, with gaps", low: "Needs work" }[level];
  const bars = Object.entries(SCORE_LABELS).map(([key, label]) => {
    const n = Number(fb.scores[key]) || 0;
    return `<div class="score-row">
      <span class="score-name">${label}</span>
      <span class="score-track"><span class="${scoreLevel(n)}" style="width:${n * 20}%"></span></span>
      <span class="score-num">${n}<small>/5</small></span>
    </div>`;
  }).join("");
  const meta = cached
    ? `${icon("clock")} Saved review from ${esc(formatDateTime(created_at))}. Answer unchanged, so no new AI call. <button class="link fb-fresh">Get fresh feedback</button>`
    : `${icon("sparkles")} New review, ${esc(formatDateTime(created_at))}`;
  return `
    <p class="fb-meta">${meta}</p>
    <div class="fb-summary">
      <div class="fb-overall ${level}">
        <div class="fb-overall-num">${avg.toFixed(1)}<small>/5</small></div>
        <div class="fb-overall-label">${verdict}</div>
      </div>
      <div class="fb-bars">${bars}</div>
    </div>
    <div class="fb-columns">
      <section><h4>${icon("checkCircle")} Strengths</h4>${listHtml(fb.strengths, "check", "good")}</section>
      <section><h4>${icon("alert")} Gaps to fix</h4>${listHtml(fb.gaps, "alert", "warn")}</section>
    </div>
    <section class="fb-suggested">
      <div class="fb-suggested-head">
        <h4>${icon("quote")} Suggested answer</h4>
        <button class="btn ghost sm fb-copy">${icon("copy")} Copy</button>
      </div>
      <blockquote class="fb-suggested-text">${esc(fb.suggested_answer)}</blockquote>
    </section>
    <section><h4>${icon("message")} Likely follow-ups</h4>${listHtml(fb.follow_up_questions, "arrow", "neutral")}</section>
    <p class="model-label">Model · ${esc(model_id)}</p>`;
}

function feedbackLoadingHtml() {
  return `<div class="fb-loading">
    <span class="spinner"></span>
    <div><strong>Reviewing your answer…</strong><p class="sub">A new review can take 10–20 seconds.</p></div>
  </div>`;
}

// Calls the API and fills `container`. Returns the result, or null on error.
// Saved reviews come back instantly; "Get fresh feedback" re-asks the model.
async function requestFeedback(body, container, button) {
  container.hidden = false;
  container.innerHTML = feedbackLoadingHtml();
  if (button) button.disabled = true;
  try {
    const result = await api("/api/feedback", { method: "POST", body });
    container.innerHTML = feedbackHtml(result);
    container.querySelector(".fb-fresh")?.addEventListener("click", () =>
      requestFeedback({ ...body, force: true }, container, button));
    container.querySelector(".fb-copy").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(result.feedback.suggested_answer);
        toast("Suggested answer copied");
      } catch {
        toast("Couldn't copy", "error");
      }
    });
    if (!result.cached) libraryStale = true; // new scores to show on the cards
    return result;
  } catch (err) {
    container.innerHTML = `<p class="alert error">${icon("alert")} ${esc(err.message)}</p>`;
    return null;
  } finally {
    if (button) button.disabled = false;
  }
}

function openFeedbackDialog(q) {
  $("#fb-dialog-question").textContent = q.question;
  $("#fb-dialog").showModal();
  requestFeedback({ question_id: q.id }, $("#fb-dialog-body"));
}

$("#fb-dialog").addEventListener("close", () => {
  if (libraryStale && !$("#view-library").hidden) {
    libraryStale = false;
    loadLibrary();
  }
});
$("#fb-dialog-close").addEventListener("click", () => $("#fb-dialog").close());

// ---- Practice ----
// A session goes through each matching question once, weakest first.

let current = null; // question being practiced
let session = null; // { seen: [ids], answered, skipped, total, remaining }

function newSession() {
  session = { seen: [], answered: 0, skipped: 0, total: 0, remaining: 0 };
  $("#p-done").hidden = true;
  $("#p-intro").hidden = true;
}

async function nextQuestion() {
  if (!session) newSession();
  const body = { type: $("#p-type").value || null, tag: $("#p-tag").value || null, seen: session.seen };
  try {
    const r = await api("/api/practice/next", { method: "POST", body });
    session.total = r.total;
    session.remaining = r.remaining;
    current = r.question;
    if (!current) return showDone();
    session.seen.push(current.id);
    renderPractice();
  } catch (err) {
    $("#p-status").textContent = err.message;
  }
}

function renderProgress() {
  const done = session.answered + session.skipped;
  $("#p-progress").hidden = false;
  $("#p-pos").textContent = current ? `Question ${session.seen.length} of ${session.total}` : "All done";
  const left = current ? session.remaining : 0; // includes the one on screen
  $("#p-counts").innerHTML =
    `<span class="count good">${session.answered} answered</span>` +
    `<span class="count">${session.skipped} skipped</span>` +
    `<span class="count">${left} left</span>`;
  $("#p-bar").style.width = `${session.total ? (done / session.total) * 100 : 0}%`;
}

function renderPractice() {
  $("#p-status").textContent = "";
  $("#p-done").hidden = true;
  $("#p-badge").outerHTML = typeBadge(current.type).replace("<span", '<span id="p-badge"');
  $("#p-dots").innerHTML = confidencePill(current.confidence);
  $("#p-question").textContent = current.question;
  $("#p-tags").innerHTML = tagsHtml(current.tags);
  $("#p-answer-body").innerHTML = answerHtml(current);
  $("#p-last-fb").innerHTML = scoreChipsHtml(current.lastFeedback);
  $("#p-fb-saved span").textContent = current.lastFeedback ? "Show AI feedback" : "Get AI feedback";
  $("#p-fb-saved").hidden = !hasAnswer(current);
  $("#p-answer").hidden = true;
  $("#p-reveal").hidden = false;
  $("#p-feedback").hidden = true;
  $("#p-typed").value = "";
  $("#p-try").open = false;
  $("#p-save-typed").hidden = true;
  $("#p-card").hidden = false;
  renderProgress();
  // Drop focus from the clicked button so Space doesn't re-click it.
  document.activeElement?.blur();
}

function showDone() {
  $("#p-card").hidden = true;
  if (!session.total) {
    $("#p-progress").hidden = true;
    $("#p-intro").hidden = false;
    $("#p-status").textContent = "No questions match this filter. Add some in the Library.";
    return;
  }
  renderProgress();
  $("#p-done-text").textContent =
    `You went through all ${plural(session.total, "question")}: ${session.answered} answered, ${session.skipped} skipped.`;
  $("#p-done").hidden = false;
}

function reveal() {
  if (!current || !$("#p-answer").hidden) return;
  $("#p-answer").hidden = false;
  $("#p-reveal").hidden = true;
}

async function rate(confidence) {
  if (!current || $("#p-answer").hidden) return; // rate only after reveal
  try {
    await api(`/api/practice/${encodeURIComponent(current.id)}/rate`, { method: "POST", body: { confidence } });
    session.answered += 1;
    libraryStale = true;
    nextQuestion();
  } catch (err) {
    $("#p-status").textContent = err.message;
  }
}

function skip() {
  if (!current) return;
  session.skipped += 1;
  nextQuestion();
}

$("#p-fb-saved").addEventListener("click", (e) => {
  requestFeedback({ question_id: current.id }, $("#p-feedback"), e.currentTarget);
});

$("#p-fb-typed").addEventListener("click", async (e) => {
  const answer = $("#p-typed").value.trim();
  if (!answer) {
    $("#p-feedback").hidden = false;
    $("#p-feedback").innerHTML = `<p class="alert info">Type an answer first.</p>`;
    return;
  }
  const result = await requestFeedback({ question_id: current.id, answer }, $("#p-feedback"), e.currentTarget);
  $("#p-save-typed").hidden = !result;
});

// Replace the saved answer with the typed one, keeping everything else.
$("#p-save-typed").addEventListener("click", async () => {
  const answer = $("#p-typed").value.trim();
  if (!answer) return;
  const ok = await confirmDialog("Replace your saved answer?", "Your typed answer will become the saved answer for this question.", "Replace");
  if (!ok) return;
  try {
    const { id, type, question, star, tags, confidence, notes } = current;
    current = await api(`/api/questions/${encodeURIComponent(id)}`, {
      method: "PUT", body: { type, question, answer, star, tags, confidence, notes },
    });
    $("#p-answer-body").innerHTML = answerHtml(current);
    $("#p-last-fb").innerHTML = scoreChipsHtml(current.lastFeedback);
    $("#p-save-typed").hidden = true;
    libraryStale = true;
    toast("Saved as your answer");
  } catch (err) {
    toast(err.message, "error");
  }
});

function startSession() {
  current = null;
  newSession();
  nextQuestion();
}

$("#p-start").addEventListener("click", startSession);
$("#p-again").addEventListener("click", startSession);
$("#p-skip").addEventListener("click", skip);
$("#p-reveal").addEventListener("click", reveal);
for (const b of document.querySelectorAll("[data-rate]")) {
  b.addEventListener("click", () => rate(Number(b.dataset.rate)));
}

// Keyboard: space reveals, 1-5 rates. Ignored while typing or when a dialog is open.
document.addEventListener("keydown", (e) => {
  if ($("#view-practice").hidden || $("#app").hidden || !current) return;
  if (document.querySelector("dialog[open]")) return;
  if (e.target.closest?.("input, textarea, select, dialog") || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === " ") {
    e.preventDefault();
    reveal();
  } else if (/^[1-5]$/.test(e.key)) {
    rate(Number(e.key));
  }
});

// ---- Import / Export ----

const fileInput = $("#import-file");
const dropzone = $("#dropzone");

function showChosenFile() {
  const file = fileInput.files[0];
  $("#import-filename").innerHTML = file
    ? `<strong>${esc(file.name)}</strong> · ${(file.size / 1024).toFixed(1)} KB`
    : `<strong>Choose a file</strong> or drag it here`;
  dropzone.classList.toggle("has-file", Boolean(file));
}

fileInput.addEventListener("change", showChosenFile);
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("dragging");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragging"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragging");
  if (e.dataTransfer.files.length) {
    fileInput.files = e.dataTransfer.files;
    showChosenFile();
  }
});

$("#import-btn").addEventListener("click", async (e) => {
  const button = e.currentTarget; // currentTarget is null after an await
  const file = fileInput.files[0];
  const out = $("#import-result");
  out.hidden = false;
  if (!file) {
    out.innerHTML = `<p class="alert info">Choose a file first.</p>`;
    return;
  }
  if (file.size > 1_000_000) {
    out.innerHTML = `<p class="alert error">${icon("alert")} File is too big (max 1 MB).</p>`;
    return;
  }
  button.disabled = true;
  out.innerHTML = `<p class="muted">Importing…</p>`;
  try {
    const r = await api("/api/import", {
      method: "POST", body: await file.text(), headers: { "Content-Type": "text/plain" },
    });
    const errors = r.errors.map((x) => `<li>Row ${x.row}: ${esc(x.error)}</li>`).join("");
    const more = r.error_count > r.errors.length ? `<li>…and ${r.error_count - r.errors.length} more</li>` : "";
    out.innerHTML = `
      <div class="import-summary">
        <div class="stat-mini good"><b>${r.imported}</b><span>imported</span></div>
        <div class="stat-mini"><b>${r.skipped_duplicates}</b><span>duplicates skipped</span></div>
        <div class="stat-mini ${r.error_count ? "bad" : ""}"><b>${r.error_count}</b><span>rows with errors</span></div>
      </div>
      ${errors ? `<ul class="import-errors">${errors}${more}</ul>` : ""}`;
    fileInput.value = "";
    showChosenFile();
    if (r.imported) toast(`Imported ${plural(r.imported, "question")}`);
    libraryStale = true;
  } catch (err) {
    out.innerHTML = `<p class="alert error">${icon("alert")} ${esc(err.message)}</p>`;
  } finally {
    button.disabled = false;
  }
});

// ---- Start ----

(async function init() {
  try {
    const { email } = await api("/api/me");
    showApp(email);
  } catch {
    showLogin();
  }
})();
