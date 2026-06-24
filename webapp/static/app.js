"use strict";

const $ = (id) => document.getElementById(id);
const api = (path, opts) => fetch(path, opts).then(async (r) => {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
});

// ── Toast ──────────────────────────────────────────────────────────────────
let toastTimer;
function toast(msg, kind = "") {
  const t = $("toast");
  t.textContent = msg;
  t.className = "toast " + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 3200);
}

// ── Status / metrics ───────────────────────────────────────────────────────
function renderStatus(s) {
  const dot = $("statusDot"), text = $("statusText");
  if (s.error) { dot.className = "dot error"; text.textContent = "Error"; }
  else if (s.running) { dot.className = "dot live"; text.textContent = "Live"; }
  else { dot.className = "dot stopped"; text.textContent = "Stopped"; }

  $("btnStart").disabled = s.running;
  $("btnStop").disabled = !s.running;

  $("mFps").textContent = s.running ? (s.fps ?? 0).toFixed(0) : "—";
  $("mFaces").textContent = s.faces_in_view ?? 0;
  $("mPersons").textContent = s.person_detection ? (s.persons_in_view ?? 0) : "off";
  $("mKnown").textContent = (s.known_people || []).length;
  $("mCooldown").textContent = s.cooldown_remaining > 0 ? Math.ceil(s.cooldown_remaining) + "s" : "ready";

  if (s.error) toastOnce(s.error);
}
let lastErr = null;
function toastOnce(msg) { if (msg !== lastErr) { lastErr = msg; toast(msg, "err"); } }

let settingsDirty = false;
function renderSettings(s) {
  if (settingsDirty) return;            // don't stomp the slider the user is dragging
  const f = s.settings.faces, a = s.settings.alarm;
  setRange("matchThreshold", "matchVal", f.match_threshold, (v) => v.toFixed(2));
  setRange("detectScore", "detectVal", f.detect_score, (v) => v.toFixed(2));
  setRange("cooldownSeconds", "cooldownVal", a.cooldown_seconds, (v) => v + "s");
  $("onUnknownFace").checked = a.on_unknown_face;
  $("onPersonNoFace").checked = a.on_person_no_face;
  $("mLog").checked = a.methods.log;
  $("mSnapshot").checked = a.methods.snapshot;
  $("mSound").checked = a.methods.sound;
  $("mEmail").checked = a.methods.email;
}
function setRange(id, valId, value, fmt) {
  if (value == null) return;
  $(id).value = value;
  $(valId).textContent = fmt(Number(value));
}

// ── Alerts feed ────────────────────────────────────────────────────────────
function addAlert(a, prepend = true) {
  const list = $("alertList");
  list.querySelector(".empty")?.remove();
  const item = document.createElement("div");
  item.className = "alert-item";
  const thumb = a.snapshot
    ? `<img class="alert-thumb" src="/api/snapshots/${a.snapshot}" data-full="/api/snapshots/${a.snapshot}" alt="snapshot">`
    : `<div class="alert-thumb"></div>`;
  item.innerHTML = `${thumb}
    <div class="alert-body">
      <div class="alert-reason">⚠️ ${escapeHtml(a.reason)}</div>
      <div class="alert-time">${a.time}</div>
    </div>`;
  if (prepend) list.prepend(item); else list.append(item);
}
function escapeHtml(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

// ── People ─────────────────────────────────────────────────────────────────
async function loadPeople() {
  const people = await api("/api/people");
  const wrap = $("peopleList");
  wrap.innerHTML = "";
  if (!people.length) { wrap.innerHTML = `<p class="empty" style="padding:8px 0">No one enrolled yet.</p>`; return; }
  for (const p of people) {
    const chip = document.createElement("div");
    chip.className = "person-chip" + (p.enrolled ? "" : " pending");
    chip.innerHTML = `
      <span class="avatar">${(p.name[0] || "?").toUpperCase()}</span>
      <span>${escapeHtml(p.name)}</span>
      <span class="samples">${p.samples}📷</span>
      <button class="x" title="Remove">×</button>`;
    chip.querySelector(".x").onclick = () => removePerson(p.name);
    wrap.append(chip);
  }
}
async function removePerson(name) {
  if (!confirm(`Remove "${name}" from known people?`)) return;
  try { await api(`/api/people/${encodeURIComponent(name)}`, { method: "DELETE" });
    toast(`Removed ${name}`, "ok"); loadPeople();
  } catch (e) { toast(e.message, "err"); }
}

// ── Wiring ─────────────────────────────────────────────────────────────────
function init() {
  $("videoStream").src = "/api/stream";

  $("btnStart").onclick = () => api("/api/control/start", { method: "POST" }).catch((e) => toast(e.message, "err"));
  $("btnStop").onclick = () => api("/api/control/stop", { method: "POST" }).catch((e) => toast(e.message, "err"));

  $("btnSource").onclick = async () => {
    const source = $("sourceInput").value.trim();
    if (!source) return toast("Enter a source first", "err");
    try { await api("/api/control/source", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source }) });
      toast("Source updated", "ok");
    } catch (e) { toast(e.message, "err"); }
  };

  $("btnClearAlerts").onclick = () => {
    $("alertList").innerHTML = `<p class="empty">No alerts yet. The feed updates in real time.</p>`;
  };

  // file label feedback
  $("enrollFiles").onchange = (e) => {
    const n = e.target.files.length;
    $("fileLabel").querySelector("span").textContent = n ? `${n} photo${n > 1 ? "s" : ""} selected` : "Choose photos…";
  };

  // enrollment
  $("enrollForm").onsubmit = async (e) => {
    e.preventDefault();
    const name = $("enrollName").value.trim();
    const files = $("enrollFiles").files;
    if (!name || !files.length) return;
    const fd = new FormData();
    fd.append("name", name);
    for (const f of files) fd.append("files", f);
    $("btnEnroll").disabled = true; $("btnEnroll").textContent = "Enrolling…";
    try {
      const res = await api("/api/people", { method: "POST", body: fd });
      let msg = `Enrolled ${res.name} (${res.saved} photo${res.saved > 1 ? "s" : ""})`;
      if (res.skipped?.length) msg += `, ${res.skipped.length} skipped (no face)`;
      toast(msg, "ok");
      $("enrollForm").reset();
      $("fileLabel").querySelector("span").textContent = "Choose photos…";
      loadPeople();
    } catch (e) { toast(e.message, "err"); }
    finally { $("btnEnroll").disabled = false; $("btnEnroll").textContent = "Add person"; }
  };

  wireSettings();

  // lightbox
  $("alertList").addEventListener("click", (e) => {
    const full = e.target.dataset?.full;
    if (full) { $("lightboxImg").src = full; $("lightbox").classList.remove("hidden"); }
  });
  $("lightbox").onclick = () => $("lightbox").classList.add("hidden");

  loadPeople();
  connectEvents();
  setInterval(refreshStatus, 1000);   // live metrics (fps, cooldown)
}

function wireSettings() {
  const fmts = {
    matchThreshold: ["matchVal", (v) => v.toFixed(2)],
    detectScore: ["detectVal", (v) => v.toFixed(2)],
    cooldownSeconds: ["cooldownVal", (v) => v + "s"],
  };
  let saveTimer;
  const queueSave = () => { settingsDirty = true; clearTimeout(saveTimer); saveTimer = setTimeout(saveSettings, 400); };

  for (const [id, [valId, fmt]] of Object.entries(fmts)) {
    $(id).addEventListener("input", () => { $(valId).textContent = fmt(Number($(id).value)); queueSave(); });
  }
  for (const id of ["onUnknownFace", "onPersonNoFace", "mLog", "mSnapshot", "mSound", "mEmail"]) {
    $(id).addEventListener("change", queueSave);
  }
}

async function saveSettings() {
  const patch = {
    faces: {
      match_threshold: Number($("matchThreshold").value),
      detect_score: Number($("detectScore").value),
    },
    alarm: {
      cooldown_seconds: Number($("cooldownSeconds").value),
      on_unknown_face: $("onUnknownFace").checked,
      on_person_no_face: $("onPersonNoFace").checked,
      methods: {
        log: { enabled: $("mLog").checked },
        snapshot: { enabled: $("mSnapshot").checked },
        sound: { enabled: $("mSound").checked },
        email: { enabled: $("mEmail").checked },
      },
    },
  };
  try { await api("/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
  } catch (e) { toast(e.message, "err"); }
  finally { settingsDirty = false; }
}

async function refreshStatus() {
  try { renderStatus(await api("/api/status")); } catch { /* server momentarily busy */ }
}

// ── SSE ────────────────────────────────────────────────────────────────────
function connectEvents() {
  const es = new EventSource("/api/events");
  es.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    if (data.type === "alert") { addAlert(data); toast("⚠️ " + data.reason, "err"); }
    else if (data.type === "status") { renderStatus(data); renderSettings(data); if (data.known_reloaded != null) loadPeople(); }
  };
  es.onerror = () => { /* EventSource auto-reconnects */ };
}

document.addEventListener("DOMContentLoaded", init);
