// ── State ──────────────────────────────────────────────────
const state = {
  connected:     false,
  installing:    false,
  pendingModule: null,
  searchTimeout: null,
};

// ── Socket.IO ──────────────────────────────────────────────
const socket = io();

socket.on("connect", () => {
  console.log("Socket connected");
});

socket.on("disconnect", () => {
  console.log("Socket disconnected");
  setConnectionStatus("disconnected");
  showToast("⚠️ Connection lost", "warn");
});

socket.on("phone_connected", (data) => {
  console.log("[SOCKET] phone_connected:", data);
  state.connected = true;
  setConnectionStatus("connected");
  
  // Safe element updates - check if elements exist
  const infoBar = document.getElementById("infoBar");
  if (infoBar) {
    infoBar.style.display = "grid";
    
    // Update device info (using correct IDs from HTML)
    const modelEl = document.getElementById("infoModel");
    const androidEl = document.getElementById("infoAndroid");
    const magiskEl = document.getElementById("infoMagisk");
    const batteryEl = document.getElementById("infoBattery");
    const storageEl = document.getElementById("infoStorage");
    
    if (modelEl) modelEl.textContent = data.model || "Unknown";
    if (androidEl) androidEl.textContent = data.android || "N/A";
    if (magiskEl) magiskEl.textContent = data.magisk || "N/A";
    if (batteryEl) batteryEl.textContent = (data.battery || "N/A") + "%";
    if (storageEl) storageEl.textContent = data.storage || "N/A";
  }
  
  showToast("✅ Phone connected!", "success");
  loadInstalledModules();
});

socket.on("phone_disconnected", () => {
  console.log("[SOCKET] phone_disconnected");
  state.connected = false;
  setConnectionStatus("disconnected");
  
  const infoBar = document.getElementById("infoBar");
  if (infoBar) infoBar.style.display = "none";
  
  showToast("❌ Phone disconnected", "error");
});

socket.on("install_log", ({ message, level }) => {
  appendLog(message, level || "info");
});

socket.on("install_progress", ({ percent, status }) => {
  setProgress(percent, status);
});

socket.on("install_done", ({ success, message }) => {
  state.installing = false;
  setProgress(success ? 100 : 0, success ? "Complete!" : "Failed");

  if (success) {
    appendLog("", "info");
    appendLog("══════════════════════════════", "success");
    appendLog("  Installation Complete! 🎉", "success");
    appendLog("══════════════════════════════", "success");
    showToast("✅ " + message, "success");
    document.getElementById("rebootBtn").style.display = "flex";
    setTimeout(() => loadInstalledModules(), 500);
  } else {
    appendLog("Installation failed: " + message, "error");
    showToast("❌ " + message, "error");
  }

  // Re-enable all install buttons
  document.querySelectorAll(".btn-install").forEach(btn => {
    btn.disabled = false;
    btn.textContent = "⚡ Install";
  });
});


// ── Init ───────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  connectPhone();
  searchModules();
  setupEventListeners();
});

// ── Event Listeners Setup ──────────────────────────────────
function setupEventListeners() {
  // Search debounce
  const searchInput = document.querySelector('.search-field input');
  if (searchInput) {
    searchInput.addEventListener('input', debounce(() => {
      searchModules();
    }, 300));
  }

  // Auto-refresh installed modules every 30s
  setInterval(() => {
    if (state.connected && !state.installing) {
      loadInstalledModules();
    }
  }, 30000);
}

function debounce(fn, delay) {
  let timeout;
  return function(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
}

async function connectPhone() {
  setDeviceStatus('Connecting...', false);
  document.getElementById('retryBtn').style.display = 'none';

  try {
    const res  = await fetch('/api/connect', { method: 'POST' });
    const data = await res.json();

    if (data.success) {
      const info = data.info || {};
      const magisk = data.magisk || 'Unknown';

      document.getElementById('deviceInfo').classList.add('connected');

      document.getElementById('deviceModel').textContent   = info.model   || 'Unknown Device';
      document.getElementById('deviceStatus').textContent  = '● Connected via WiFi';
      document.getElementById('statAndroid').textContent   = info.android || '?';
      document.getElementById('statMagisk').textContent    = magisk;
      document.getElementById('statBattery').textContent   = info.battery || '--';
      document.getElementById('statStorage').textContent   = info.storage || '--';
      document.getElementById('retryBtn').style.display    = 'none';
      showToast('✅ Device connected!', 'success');
    } else {
      document.getElementById('deviceModel').textContent  = 'Connection Failed';
      document.getElementById('deviceStatus').textContent = data.message || 'Could not connect';
      document.getElementById('retryBtn').style.display   = 'inline-flex';
      showToast('❌ ' + (data.message || 'Connection failed'), 'error');
    }
  } catch (e) {
    document.getElementById('deviceModel').textContent  = 'Connection Error';
    document.getElementById('deviceStatus').textContent = e.message;
    document.getElementById('retryBtn').style.display   = 'inline-flex';
    showToast('❌ ' + e.message, 'error');
  }
}



function setConnectionStatus(status) {
  const dot     = document.getElementById("statusDot");
  const label   = document.getElementById("connectionStatus");

  dot.className = "status-dot " + status;

  const labels = {
    connecting:    "Connecting...",
    connected:    "Connected",
    disconnected: "Disconnected",
  };

  label.textContent = labels[status] || status;
  state.connected   = status === "connected";
}

function updatePhoneInfo(info, magisk) {
  document.getElementById("deviceName").textContent  = info.model || "Unknown";
  document.getElementById("androidVersion").textContent = "Android " + (info.version || "?");
  document.getElementById("magiskVersion").textContent  = magisk.version || "—";
}

// ── Search & Modules ───────────────────────────────────────
async function searchModules() {
  const query = document.querySelector('.search-field input')?.value || "";
  try {
    const res  = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    const data = await res.json();
    renderModuleList(data.modules || []);
  } catch (e) {
    console.error("Search error:", e);
    showToast("❌ Search failed", "error");
  }
}

function renderModuleList(modules) {
  const list = document.getElementById("moduleList");
  
  if (!modules.length) {
    list.innerHTML = emptyState("🔍", "No modules found", "Try a different search");
    return;
  }

  list.innerHTML = modules.map(m => `
    <div class="module-card" onclick="openInstallModal(${escAttr(JSON.stringify(m))})">
      <div class="module-card-header">
        <div class="module-card-title">${escHtml(m.name)}</div>
        <div class="module-version-chip">${escHtml(m.version)}</div>
      </div>
      <div class="module-card-desc">${escHtml(m.description)}</div>
      <div class="module-card-footer">
        <div class="module-author">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
          ${escHtml(m.author)}
        </div>
        <button class="btn-install" onclick="event.stopPropagation(); openInstallModal(${escAttr(JSON.stringify(m))})">
          ⚡ Install
        </button>
      </div>
    </div>
  `).join("");
}

// ── Modal ──────────────────────────────────────────────────
function openInstallModal(module) {
  state.pendingModule = module;
  document.getElementById("modalModuleInfo").innerHTML = `
    <div class="modal-mod-name">${escHtml(module.name)}</div>
    <div class="modal-mod-desc">${escHtml(module.description)}</div>
    <div class="modal-mod-meta">
      <span>📌 ${escHtml(module.version)}</span>
      <span>👤 ${escHtml(module.author)}</span>
    </div>
  `;
  document.getElementById("installModal").style.display = "flex";
}

function closeModal() {
  document.getElementById("installModal").style.display = "none";
  state.pendingModule = null;
}

function confirmInstall() {
  if (!state.pendingModule) return;
  installModule(state.pendingModule.id);
  closeModal();
}

// Click outside modal to close
document.addEventListener("click", (e) => {
  const modal = document.getElementById("installModal");
  if (e.target === modal) closeModal();
});

// ── Installation ───────────────────────────────────────────
async function installModule(moduleId) {
  state.installing = true;
  document.querySelectorAll(".btn-install").forEach(btn => {
    btn.disabled    = true;
    btn.textContent = "⏳ Installing...";
  });

  document.getElementById("progressWrap").style.display = "flex";
  appendLog(`Starting installation of module ${moduleId}...`, "info");

  try {
    const res = await fetch(`/api/install`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module_id: moduleId }),
    });
    const data = await res.json();
    if (!data.success) {
      appendLog(`Error: ${data.message}`, "error");
      showToast("❌ " + data.message, "error");
      state.installing = false;
      document.querySelectorAll(".btn-install").forEach(btn => {
        btn.disabled    = false;
        btn.textContent = "⚡ Install";
      });
    }
  } catch (e) {
    appendLog("Error: " + e.message, "error");
    showToast("❌ " + e.message, "error");
    state.installing = false;
  }
}

// ── Installed Modules ──────────────────────────────────────
async function loadInstalledModules() {
  try {
    const res  = await fetch("/api/installed");
    const data = await res.json();
    renderInstalledList(data.modules || []);
  } catch (e) {
    console.error("Load installed error:", e);
  }
}

function renderInstalledList(modules) {
  const list = document.getElementById("installedList");
  
  if (!modules.length) {
    list.innerHTML = emptyState("📦", "No modules installed", "Install one from the left panel");
    return;
  }

  list.innerHTML = modules.map(m => `
    <div class="installed-card ${m.enabled ? "" : "disabled"}">
      <div class="installed-module-icon">📦</div>
      <div class="installed-info">
        <div class="installed-name">${escHtml(m.name)}</div>
        <div class="installed-meta">
          <span class="status-badge badge-${m.enabled ? "active" : "disabled"}">
            ${m.enabled ? "✓ Active" : "◯ Disabled"}
          </span>
          <span>${escHtml(m.version)}</span>
        </div>
      </div>
      <div class="installed-actions">
        <button class="btn btn-sm btn-ghost" onclick="toggleModule(${escAttr(m.id)})">
          ${m.enabled ? "Disable" : "Enable"}
        </button>
        <button class="btn btn-sm btn-danger-soft" onclick="removeModule(${escAttr(m.id)})">
          Remove
        </button>
      </div>
    </div>
  `).join("");
}

async function toggleModule(moduleId) {
  try {
    const res = await fetch(`/api/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module_id: moduleId }),
    });
    const data = await res.json();
    if (data.success) {
      loadInstalledModules();
      showToast("✅ Module toggled", "success");
    }
  } catch (e) {
    showToast("❌ " + e.message, "error");
  }
}

async function removeModule(moduleId) {
  if (!confirm("Remove this module?")) return;
  try {
    const res = await fetch(`/api/remove`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module_id: moduleId }),
    });
    const data = await res.json();
    if (data.success) {
      loadInstalledModules();
      showToast("✅ Module removed", "success");
    }
  } catch (e) {
    showToast("❌ " + e.message, "error");
  }
}

// ── Reboot ────────────────────────────────────────────────
async function rebootPhone() {
  if (!confirm("Reboot phone?")) return;
  try {
    const res = await fetch("/api/reboot", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast("🔄 Rebooting...", "success");
      setConnectionStatus("disconnected");
      appendLog("Phone rebooting. Reconnecting in 45s...", "info");
      setTimeout(() => {
        appendLog("Attempting reconnect...", "info");
        connectPhone();
      }, 45000);
    } else {
      showToast("❌ " + data.error, "error");
    }
  } catch (e) {
    showToast("❌ " + e.message, "error");
  }
}

// ── Log ────────────────────────────────────────────────────
function appendLog(message, level = "info") {
  const log  = document.getElementById("logOutput");
  const line = document.createElement("div");
  line.className = `log-line ${level}`;

  const ts = document.createElement("span");
  ts.className   = "log-ts";
  ts.textContent = new Date().toLocaleTimeString();

  const msg = document.createElement("span");
  msg.textContent = message;

  line.append(ts, msg);
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

function clearLog() {
  document.getElementById("logOutput").innerHTML = '<div class="log-line info"><span class="log-ts">' +
    new Date().toLocaleTimeString() + '</span><span>[ Log cleared ]</span></div>';
}

// ── Progress ───────────────────────────────────────────────
function setProgress(percent, status) {
  const fill  = document.getElementById("progressFill");
  const pct   = document.getElementById("progressPct");
  const label = document.getElementById("progressLabel");

  fill.style.width  = percent + "%";
  if (pct) pct.textContent = percent + "%";
  if (label) label.textContent = status || "";

  if (percent >= 100) {
    fill.style.background = "linear-gradient(90deg, var(--green), #10b981)";
  } else if (status?.includes("Failed")) {
    fill.style.background = "linear-gradient(90deg, var(--red), #fb7185)";
  } else {
    fill.style.background = "linear-gradient(90deg, var(--accent), var(--blue))";
  }
}

// ── Toast ──────────────────────────────────────────────────
function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  const toast     = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("show"));
  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 350);
  }, 3500);
}

// ── Helpers ────────────────────────────────────────────────
function emptyState(icon, msg, sub = "") {
  return `<div class="empty-state">
    <div class="empty-icon">${icon}</div>
    <p>${escHtml(msg)}</p>
    ${sub ? `<small>${escHtml(sub)}</small>` : ""}
  </div>`;
}

function escHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escAttr(str) {
  if (!str) return "''";
  return "'" + String(str)
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'")
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "\\r") + "'";
}

// Auto-connect on page load
window.addEventListener('load', () => {
  connectPhone();
});
