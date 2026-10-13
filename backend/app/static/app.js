// PrepLoop frontend. Plain JS, no build step.

const $ = (sel) => document.querySelector(sel);

// Escape user content before putting it in HTML.
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

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

// ---- Auth ----

let googleReady = false;

async function showLogin() {
  show("#login");
  if (googleReady) return;
  const { googleClientId } = await api("/api/config");
  // The Google script loads async, wait for it.
  while (!window.google?.accounts?.id) await new Promise((r) => setTimeout(r, 50));
  google.accounts.id.initialize({ client_id: googleClientId, callback: onGoogleCredential });
  google.accounts.id.renderButton($("#google-button"), { theme: "outline", size: "large" });
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
  show("#app");
  loadLibrary();
}

$("#logout").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  window.google?.accounts?.id.disableAutoSelect();
  showLogin();
});

// ---- Tabs ----

for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => {
    for (const t of document.querySelectorAll(".tab")) t.classList.toggle("active", t === tab);
    for (const view of ["library", "practice", "io"]) $(`#view-${view}`).hidden = view !== tab.dataset.view;
    // Ratings change confidence and practice stats, so refresh the list.
    if (tab.dataset.view === "library" && libraryStale) {
      libraryStale = false;
      loadLibrary();
    }
  });
}

// ---- Library ----

let questions = []; // the currently shown (filtered) list
let libraryStale = false; // set after practice ratings

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

// Reload the list. refreshTags also rebuilds the tag dropdown from all questions.
async function loadLibrary({ refreshTags = true } = {}) {
  const status = $("#lib-status");
  try {
    if (refreshTags) {
      const all = await api("/api/questions");
      fillTagFilter(all);
    }
    questions = await api(`/api/questions?${filterParams()}`);
    renderList();
    status.textContent = `${questions.length} question${questions.length === 1 ? "" : "s"}`;
  } catch (err) {
    status.textContent = err.message;
  }
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

function confidenceDots(n) {
  return `<span class="dots" title="Confidence ${n}/5">${[1, 2, 3, 4, 5]
    .map((i) => `<span class="dot${i <= n ? " on" : ""}"></span>`).join("")}</span>`;
}

// Answer, STAR parts, and notes. Shared by the library and practice views.
function answerHtml(q) {
  const star = q.star && Object.values(q.star).some(Boolean)
    ? `<dl class="star">${["situation", "task", "action", "result"]
        .filter((k) => q.star[k])
        .map((k) => `<dt>${k}</dt><dd>${esc(q.star[k])}</dd>`).join("")}</dl>`
    : "";
  return `
    ${q.answer ? `<p class="answer">${esc(q.answer)}</p>` : `<p class="muted">No answer yet.</p>`}
    ${star}
    ${q.notes ? `<p class="notes"><strong>Notes:</strong> ${esc(q.notes)}</p>` : ""}`;
}

function tagsHtml(tags) {
  return tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("");
}

function renderList() {
  const list = $("#q-list");
  if (!questions.length) {
    list.innerHTML = `<p class="empty muted">No questions yet. Add one to get started.</p>`;
    return;
  }
  list.innerHTML = questions.map((q) => `
      <article class="card" data-id="${esc(q.id)}">
        <div class="card-head">
          <span class="badge ${esc(q.type)}">${esc(q.type)}</span>
          ${confidenceDots(q.confidence)}
          <span class="spacer"></span>
          ${q.answer || (q.star && Object.values(q.star).some(Boolean)) ? `<button class="link" data-action="feedback">Feedback</button>` : ""}
          <button class="link" data-action="edit">Edit</button>
          <button class="link danger" data-action="delete">Delete</button>
        </div>
        <h3 class="q-text">${esc(q.question)}</h3>
        ${q.tags.length ? `<div class="tags">${tagsHtml(q.tags)}</div>` : ""}
        <details>
          <summary>Show answer</summary>
          ${answerHtml(q)}
        </details>
        <p class="meta muted small">Practiced ${q.timesPracticed}× · last ${formatDate(q.lastPracticed)} · added ${formatDate(q.createdAt)}</p>
      </article>`).join("");
}

// Edit / delete buttons on cards.
$("#q-list").addEventListener("click", async (e) => {
  const button = e.target.closest("button[data-action]");
  if (!button) return;
  const id = button.closest(".card").dataset.id;
  const q = questions.find((x) => x.id === id);
  if (button.dataset.action === "edit") openForm(q);
  if (button.dataset.action === "feedback") openFeedbackDialog(q);
  if (button.dataset.action === "delete" && confirm(`Delete this question?\n\n${q.question}`)) {
    try {
      await api(`/api/questions/${encodeURIComponent(id)}`, { method: "DELETE" });
      loadLibrary();
    } catch (err) {
      alert(err.message);
    }
  }
});

// Filters: search waits for typing to pause, the rest reload right away.
let searchTimer;
$("#f-q").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadLibrary({ refreshTags: false }), 250);
});
for (const id of ["#f-type", "#f-tag", "#f-conf", "#f-sort"]) {
  $(id).addEventListener("change", () => loadLibrary({ refreshTags: false }));
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
    loadLibrary();
  } catch (err) {
    $("#q-form-error").textContent = err.message;
    $("#q-form-error").hidden = false;
  }
});

// ---- AI feedback ----

const SCORE_LABELS = { clarity: "Clarity", structure: "Structure", specificity: "Specificity" };

function listHtml(items) {
  return items.length ? `<ul>${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : `<p class="muted small">None.</p>`;
}

function feedbackHtml({ feedback: fb, model_id }) {
  const scores = Object.entries(SCORE_LABELS).map(([key, label]) => {
    const n = Number(fb.scores[key]) || 0;
    return `<div class="score">
      <span>${label}</span>
      <span class="bar"><span style="width:${n * 20}%"></span></span>
      <span class="small">${n}/5</span>
    </div>`;
  }).join("");
  return `
    <div class="scores">${scores}</div>
    <h4>Strengths</h4>${listHtml(fb.strengths)}
    <h4>Gaps</h4>${listHtml(fb.gaps)}
    <h4>Suggested answer</h4><p class="answer">${esc(fb.suggested_answer)}</p>
    <h4>Follow-up questions</h4>${listHtml(fb.follow_up_questions)}
    <p class="model-label">Model: ${esc(model_id)}</p>`;
}

// Calls the API and fills `container`. Returns true on success.
async function requestFeedback(body, container, button) {
  container.hidden = false;
  container.innerHTML = `<p class="muted">Getting feedback… this can take 10–20 seconds.</p>`;
  if (button) button.disabled = true;
  try {
    container.innerHTML = feedbackHtml(await api("/api/feedback", { method: "POST", body }));
    return true;
  } catch (err) {
    container.innerHTML = `<p class="error">${esc(err.message)}</p>`;
    return false;
  } finally {
    if (button) button.disabled = false;
  }
}

function openFeedbackDialog(q) {
  $("#fb-dialog-question").textContent = q.question;
  $("#fb-dialog").showModal();
  requestFeedback({ question_id: q.id }, $("#fb-dialog-body"));
}

$("#fb-dialog-close").addEventListener("click", () => $("#fb-dialog").close());

// ---- Practice ----

let current = null; // question being practiced
let practicedCount = 0;

async function nextQuestion() {
  const params = new URLSearchParams();
  if ($("#p-type").value) params.set("type", $("#p-type").value);
  if ($("#p-tag").value) params.set("tag", $("#p-tag").value);
  if (current) params.set("exclude", current.id);
  try {
    current = await api(`/api/practice/next?${params}`);
    renderPractice();
  } catch (err) {
    current = null;
    $("#p-card").hidden = true;
    $("#p-status").textContent = err.status === 404 ? "No questions match this filter. Add some in the Library." : err.message;
  }
}

function renderPractice() {
  $("#p-status").textContent = "";
  $("#p-badge").className = `badge ${current.type}`;
  $("#p-badge").textContent = current.type;
  $("#p-dots").innerHTML = confidenceDots(current.confidence);
  $("#p-question").textContent = current.question;
  $("#p-tags").innerHTML = tagsHtml(current.tags);
  $("#p-answer-body").innerHTML = answerHtml(current);
  $("#p-answer").hidden = true;
  $("#p-reveal").hidden = false;
  $("#p-feedback").hidden = true;
  $("#p-typed").value = "";
  $("#p-try").open = false;
  $("#p-save-typed").hidden = true;
  $("#p-card").hidden = false;
  // Drop focus from the clicked button so Space doesn't re-click it.
  document.activeElement?.blur();
  $("#p-count").textContent = practicedCount ? `${practicedCount} practiced this session` : "";
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
    practicedCount += 1;
    libraryStale = true;
    nextQuestion();
  } catch (err) {
    $("#p-status").textContent = err.message;
  }
}

$("#p-fb-saved").addEventListener("click", (e) => {
  requestFeedback({ question_id: current.id }, $("#p-feedback"), e.currentTarget);
});

$("#p-fb-typed").addEventListener("click", async (e) => {
  const answer = $("#p-typed").value.trim();
  if (!answer) {
    $("#p-feedback").hidden = false;
    $("#p-feedback").innerHTML = `<p class="muted">Type an answer first.</p>`;
    return;
  }
  const ok = await requestFeedback({ question_id: current.id, answer }, $("#p-feedback"), e.currentTarget);
  $("#p-save-typed").hidden = !ok;
});

// Replace the saved answer with the typed one, keeping everything else.
$("#p-save-typed").addEventListener("click", async () => {
  const answer = $("#p-typed").value.trim();
  if (!answer || !confirm("Replace your saved answer with this one?")) return;
  try {
    const { id, type, question, star, tags, confidence, notes } = current;
    current = await api(`/api/questions/${encodeURIComponent(id)}`, {
      method: "PUT", body: { type, question, answer, star, tags, confidence, notes },
    });
    $("#p-answer-body").innerHTML = answerHtml(current);
    $("#p-save-typed").hidden = true;
    libraryStale = true;
  } catch (err) {
    alert(err.message);
  }
});

$("#p-start").addEventListener("click", () => {
  current = null;
  nextQuestion();
});
$("#p-skip").addEventListener("click", nextQuestion);
$("#p-reveal").addEventListener("click", reveal);
for (const b of document.querySelectorAll("[data-rate]")) {
  b.addEventListener("click", () => rate(Number(b.dataset.rate)));
}

// Keyboard: space reveals, 1-5 rates. Ignored while typing or when a dialog is open.
document.addEventListener("keydown", (e) => {
  if ($("#view-practice").hidden || $("#app").hidden || !current) return;
  if (e.target.closest("input, textarea, select, dialog") || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === " ") {
    e.preventDefault();
    reveal();
  } else if (/^[1-5]$/.test(e.key)) {
    rate(Number(e.key));
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
