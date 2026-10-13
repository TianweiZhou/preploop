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
  });
}

// ---- Library ----

let questions = []; // the currently shown (filtered) list

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

function fillTagFilter(all) {
  const select = $("#f-tag");
  const current = select.value;
  const tags = [...new Set(all.flatMap((q) => q.tags))].sort((a, b) => a.localeCompare(b));
  select.innerHTML = `<option value="">All tags</option>` +
    tags.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("");
  if (tags.includes(current)) select.value = current;
}

function confidenceDots(n) {
  return `<span class="dots" title="Confidence ${n}/5">${[1, 2, 3, 4, 5]
    .map((i) => `<span class="dot${i <= n ? " on" : ""}"></span>`).join("")}</span>`;
}

function renderList() {
  const list = $("#q-list");
  if (!questions.length) {
    list.innerHTML = `<p class="empty muted">No questions yet. Add one to get started.</p>`;
    return;
  }
  list.innerHTML = questions.map((q) => {
    const star = q.star && Object.values(q.star).some(Boolean)
      ? `<dl class="star">${["situation", "task", "action", "result"]
          .filter((k) => q.star[k])
          .map((k) => `<dt>${k}</dt><dd>${esc(q.star[k])}</dd>`).join("")}</dl>`
      : "";
    return `
      <article class="card" data-id="${esc(q.id)}">
        <div class="card-head">
          <span class="badge ${esc(q.type)}">${esc(q.type)}</span>
          ${confidenceDots(q.confidence)}
          <span class="spacer"></span>
          <button class="link" data-action="edit">Edit</button>
          <button class="link danger" data-action="delete">Delete</button>
        </div>
        <h3 class="q-text">${esc(q.question)}</h3>
        ${q.tags.length ? `<div class="tags">${q.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>` : ""}
        <details>
          <summary>Show answer</summary>
          ${q.answer ? `<p class="answer">${esc(q.answer)}</p>` : `<p class="muted">No answer yet.</p>`}
          ${star}
          ${q.notes ? `<p class="notes"><strong>Notes:</strong> ${esc(q.notes)}</p>` : ""}
        </details>
        <p class="meta muted small">Practiced ${q.timesPracticed}× · last ${formatDate(q.lastPracticed)} · added ${formatDate(q.createdAt)}</p>
      </article>`;
  }).join("");
}

// Edit / delete buttons on cards.
$("#q-list").addEventListener("click", async (e) => {
  const button = e.target.closest("button[data-action]");
  if (!button) return;
  const id = button.closest(".card").dataset.id;
  const q = questions.find((x) => x.id === id);
  if (button.dataset.action === "edit") openForm(q);
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

// ---- Start ----

(async function init() {
  try {
    const { email } = await api("/api/me");
    showApp(email);
  } catch {
    showLogin();
  }
})();
