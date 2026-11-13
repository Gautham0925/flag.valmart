const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const state = { user: null, cfg: {}, challenges: [], tab: "challenges", mode: "login", timers: [], current: null };
let modal, toast;

async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: { "X-FD": "1" }, credentials: "same-origin" };
  if (opts.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, init);
  let data = null;
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) {
    const err = new Error((data && (typeof data.detail === "string" ? data.detail : data.detail && data.detail[0] && data.detail[0].msg)) || "Request failed");
    err.status = res.status;
    throw err;
  }
  return data;
}

function notify(msg, kind = "success") {
  const el = $("#toast");
  el.className = `toast align-items-center border-0 text-bg-${kind}`;
  $("#toast-body").textContent = msg;
  toast.show();
}

function show(view) {
  $$("main > section").forEach((s) => (s.hidden = s.id !== `view-${view}`));
}

function clearTimers() {
  state.timers.forEach(clearInterval);
  state.timers = [];
}

function setTab(tab) {
  if (tab === "admin" && (!state.user || state.user.role !== "admin")) tab = "challenges";
  state.tab = tab;
  clearTimers();
  $$("#tabs .nav-link").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
  show(tab);
  if (tab === "challenges") loadChallenges();
  if (tab === "scoreboard") { loadBoard(); state.timers.push(setInterval(loadBoard, 8000)); }
  if (tab === "admin") { loadAdmin(); state.timers.push(setInterval(loadAdmin, 10000)); }
}

function enterApp() {
  $("#tabs").hidden = false;
  $("#userbox").hidden = false;
  $("#admin-tab").hidden = state.user.role !== "admin";
  $("#whoami").textContent = state.user.username;
  refreshScore();
  setTab((location.hash || "#challenges").slice(1) || "challenges");
}

async function refreshScore() {
  try {
    const me = await api("/api/me");
    state.user = { ...state.user, ...me };
    $("#score-badge").textContent = `${me.score} pts`;
  } catch (e) {}
}

function leaveApp() {
  clearTimers();
  state.user = null;
  $("#tabs").hidden = true;
  $("#userbox").hidden = true;
  show("auth");
}

async function loadChallenges() {
  try {
    state.challenges = await api("/api/challenges");
  } catch (e) {
    if (e.status === 401) return leaveApp();
    return notify(e.message, "danger");
  }
  renderChallenges();
}

function renderChallenges() {
  const list = state.challenges;
  const solved = list.filter((c) => c.solved).length;
  $("#progress-label").textContent = `${solved} of ${list.length} solved`;
  $("#progress-bar").style.width = list.length ? `${(solved / list.length) * 100}%` : "0";
  $("#challenge-grid").innerHTML = list.map((c) => `
    <div class="col-md-6 col-lg-4"><div class="card chal ${c.solved ? "solved" : ""}" data-id="${esc(c.id)}"><div class="card-body">
      <div class="d-flex justify-content-between mb-2"><span class="mono small text-accent">${esc(c.id)}</span>${c.solved ? '<span class="badge text-bg-success"><i class="bi bi-check-lg"></i> Solved</span>' : `<span class="mono small text-secondary">${c.points} pts</span>`}</div>
      <h5 class="card-title">${esc(c.title)}</h5>
      <div class="d-flex justify-content-between align-items-center mt-3"><span class="badge text-bg-secondary">${esc(c.category)}</span><span class="small text-secondary"><i class="bi bi-people me-1"></i>${c.solves}</span></div>
      ${c.enabled ? "" : '<div class="small text-warning mt-2">Hidden from players</div>'}
    </div></div></div>`).join("");
}

function openChallenge(id) {
  const c = state.challenges.find((x) => x.id === id);
  if (!c) return;
  state.current = c;
  $("#m-id").textContent = c.id;
  $("#m-title").textContent = c.title;
  $("#m-cat").textContent = c.category;
  $("#m-points").textContent = `${c.points} pts`;
  $("#m-solves").textContent = `${c.solves} solves`;
  $("#m-desc").textContent = c.description;
  $("#m-flag").value = "";
  $("#m-flag").disabled = c.solved;
  $("#m-submit").disabled = c.solved;
  const r = $("#m-result");
  r.hidden = !c.solved;
  if (c.solved) { r.className = "alert alert-success mt-3 mb-0"; r.textContent = "You already solved this one."; }
  modal.show();
  setTimeout(() => $("#m-flag").focus(), 300);
}

async function submitFlag(ev) {
  ev.preventDefault();
  const c = state.current;
  const btn = $("#m-submit");
  const r = $("#m-result");
  btn.disabled = true;
  try {
    const res = await api(`/api/challenges/${encodeURIComponent(c.id)}/submit`, { method: "POST", body: { flag: $("#m-flag").value } });
    r.hidden = false;
    r.className = `alert mt-3 mb-0 alert-${res.status === "wrong" ? "danger" : "success"}`;
    r.textContent = res.message;
    if (res.status === "correct") {
      c.solved = true;
      c.solves += 1;
      $("#m-flag").disabled = true;
      renderChallenges();
      refreshScore();
      return;
    }
  } catch (e) {
    r.hidden = false;
    r.className = "alert mt-3 mb-0 alert-warning";
    r.textContent = e.message;
  }
  btn.disabled = c.solved;
}

async function loadBoard() {
  try {
    const rows = await api("/api/scoreboard");
    $("#board-body").innerHTML = rows.length ? rows.map((r) => `<tr class="${r.id === state.user.id ? "me" : ""}"><td class="mono">${r.rank}</td><td>${esc(r.username)}</td><td class="text-end mono">${r.solved}</td><td class="text-end mono">${r.score}</td></tr>`).join("") : '<tr><td colspan="4" class="text-center text-secondary py-4">No players yet</td></tr>';
    $("#board-updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (e) {
    if (e.status === 401) leaveApp();
  }
}

async function loadAdmin() {
  try {
    const [sum, chals, users, subs] = await Promise.all([api("/api/admin/summary"), api("/api/challenges"), api("/api/admin/users"), api("/api/admin/submissions?limit=60")]);
    $("#admin-stats").innerHTML = [["Players", sum.players], ["Submissions", sum.submissions], ["Correct", sum.correct], ["Solves", sum.solves]].map(([k, v]) => `<div class="col-6 col-md-3"><div class="card"><div class="card-body"><div class="text-secondary small">${k}</div><div class="h3 mono mb-0">${v}</div></div></div></div>`).join("");
    if (!$("#admin-challenges").contains(document.activeElement)) {
      $("#admin-challenges").innerHTML = chals.map((c) => `<tr data-id="${esc(c.id)}"><td class="mono text-accent">${esc(c.id)}</td><td>${esc(c.title)}</td><td><input class="form-control form-control-sm mono" type="number" min="0" value="${c.points}" data-f="points"></td><td><div class="form-check form-switch"><input class="form-check-input" type="checkbox" data-f="enabled" ${c.enabled ? "checked" : ""}></div></td><td><input class="form-control form-control-sm mono" placeholder="leave empty to keep" data-f="flag" autocomplete="off"></td><td><button class="btn btn-sm btn-outline-secondary" data-save>Save</button></td></tr>`).join("");
    }
    $("#admin-users").innerHTML = users.map((u) => `<tr data-uid="${u.id}"><td>${esc(u.username)} ${u.disabled ? '<span class="badge text-bg-warning">disabled</span>' : ""}</td><td class="text-end mono">${u.solved}</td><td class="text-end mono">${u.score}</td><td class="text-end text-nowrap"><button class="btn btn-sm btn-outline-secondary" data-act="disable">${u.disabled ? "Enable" : "Disable"}</button> <button class="btn btn-sm btn-outline-secondary" data-act="password">Set password</button> <button class="btn btn-sm btn-outline-danger" data-act="clear">Clear solves</button></td></tr>`).join("");
    $("#admin-subs").innerHTML = subs.map((s) => `<tr><td>${new Date(s.at).toLocaleTimeString()}</td><td>${esc(s.username)}</td><td>${esc(s.challenge)}</td><td>${s.correct ? '<span class="text-success">correct</span>' : '<span class="text-danger">wrong</span>'}</td><td>${esc(s.preview)}</td></tr>`).join("");
  } catch (e) {
    if (e.status === 401) leaveApp();
  }
}

async function adminClick(ev) {
  const save = ev.target.closest("[data-save]");
  if (save) {
    const row = save.closest("tr");
    const body = { points: parseInt($('[data-f="points"]', row).value, 10), enabled: $('[data-f="enabled"]', row).checked };
    const flag = $('[data-f="flag"]', row).value;
    if (flag) body.flag = flag;
    try { await api(`/api/admin/challenges/${row.dataset.id}`, { method: "PATCH", body }); notify("Saved"); loadAdmin(); } catch (e) { notify(e.message, "danger"); }
    return;
  }
  const act = ev.target.closest("[data-act]");
  if (!act) return;
  const uid = act.closest("tr").dataset.uid;
  try {
    if (act.dataset.act === "disable") await api(`/api/admin/users/${uid}/disable`, { method: "POST" });
    if (act.dataset.act === "clear" && confirm("Clear this player's solves?")) await api(`/api/admin/users/${uid}/solves`, { method: "DELETE" });
    if (act.dataset.act === "password") {
      const pw = prompt("New password (8+ characters)");
      if (!pw) return;
      await api(`/api/admin/users/${uid}/password`, { method: "POST", body: { password: pw } });
      notify("Password updated");
    }
    loadAdmin();
  } catch (e) { notify(e.message, "danger"); }
}

function setMode(mode) {
  state.mode = mode;
  $$("#auth-pills .nav-link").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  $("#auth-submit").textContent = mode === "login" ? "Sign in" : "Create account";
  $("#code-row").hidden = !(mode === "register" && state.cfg.needs_code);
  $("#f-pass").autocomplete = mode === "login" ? "current-password" : "new-password";
  $("#auth-error").hidden = true;
}

async function authSubmit(ev) {
  ev.preventDefault();
  const err = $("#auth-error");
  err.hidden = true;
  const body = { username: $("#f-user").value.trim(), password: $("#f-pass").value };
  if (state.mode === "register") body.code = $("#f-code").value;
  $("#auth-submit").disabled = true;
  try {
    state.user = await api(state.mode === "login" ? "/api/login" : "/api/register", { method: "POST", body });
    $("#f-pass").value = "";
    enterApp();
  } catch (e) {
    err.textContent = e.message;
    err.hidden = false;
  }
  $("#auth-submit").disabled = false;
}

async function init() {
  modal = new bootstrap.Modal($("#flag-modal"));
  toast = new bootstrap.Toast($("#toast"), { delay: 3500 });
  state.cfg = await api("/api/config");
  document.title = state.cfg.event;
  $("#event-name").textContent = state.cfg.event;
  $("#register-pill").parentElement.hidden = !state.cfg.registration_open;
  $$("#auth-pills .nav-link").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
  $("#auth-form").addEventListener("submit", authSubmit);
  $("#flag-form").addEventListener("submit", submitFlag);
  $("#challenge-grid").addEventListener("click", (e) => { const c = e.target.closest(".chal"); if (c) openChallenge(c.dataset.id); });
  $("#view-admin").addEventListener("click", adminClick);
  $("#reset-all").addEventListener("click", async () => {
    if (!confirm("Delete ALL solves and submissions? This cannot be undone.")) return;
    try { await api("/api/admin/reset", { method: "POST" }); notify("Scores reset"); loadAdmin(); } catch (e) { notify(e.message, "danger"); }
  });
  $("#logout").addEventListener("click", async () => { await api("/api/logout", { method: "POST" }).catch(() => {}); leaveApp(); });
  window.addEventListener("hashchange", () => state.user && setTab(location.hash.slice(1) || "challenges"));
  try {
    state.user = await api("/api/me");
    enterApp();
  } catch (e) {
    show("auth");
  }
}

init();
