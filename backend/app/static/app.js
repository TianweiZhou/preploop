// PrepLoop frontend. Plain JS, no build step.

const $ = (sel) => document.querySelector(sel);

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
    const err = new Error((data && data.detail && String(data.detail)) || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

function show(id) {
  for (const el of ["#loading", "#login", "#app"]) $(el).hidden = el !== id;
}

// ---- Auth ----

async function showLogin() {
  show("#login");
  const { googleClientId } = await api("/api/config");
  // The Google script loads async, wait for it.
  while (!window.google?.accounts?.id) await new Promise((r) => setTimeout(r, 50));
  google.accounts.id.initialize({ client_id: googleClientId, callback: onGoogleCredential });
  google.accounts.id.renderButton($("#google-button"), { theme: "outline", size: "large" });
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
}

$("#logout").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  window.google?.accounts?.id.disableAutoSelect();
  showLogin();
});

// On load: check for an existing session.
(async function init() {
  try {
    const { email } = await api("/api/me");
    showApp(email);
  } catch {
    showLogin();
  }
})();
