const WAVELENGTHS = [
  410, 435, 460, 485, 510, 535,
  560, 585, 610, 645, 680, 705,
  730, 760, 810, 860, 900, 940,
];

const CHANNEL_KEYS = WAVELENGTHS.map((w) => `nm${w}`);

const elements = {
  portSelect: document.querySelector("#portSelect"),
  connectButton: document.querySelector("#connectButton"),
  connectionLight: document.querySelector("#connectionLight"),
  deviceName: document.querySelector("#deviceName"),
  sensorStatus: document.querySelector("#sensorStatus"),
  fruitId: document.querySelector("#fruitId"),
  scanButton: document.querySelector("#scanButton"),
  scanButtonText: document.querySelector("#scanButtonText"),
  totalScans: document.querySelector("#totalScans"),
  totalFruitText: document.querySelector("#totalFruitText"),
  unlabeledCount: document.querySelector("#unlabeledCount"),
  lastStatus: document.querySelector("#lastStatus"),
  lastStatusDetail: document.querySelector("#lastStatusDetail"),
  measurementRows: document.querySelector("#measurementRows"),
  liveClock: document.querySelector("#liveClock"),
  toast: document.querySelector("#toast"),

  // Error Inspector Elements
  errorInspector: document.querySelector("#errorInspector"),
  errorInspectorTitle: document.querySelector("#errorInspectorTitle"),
  errorInspectorTime: document.querySelector("#errorInspectorTime"),
  errorInspectorMsg: document.querySelector("#errorInspectorMsg"),
  errorRawBoxWrap: document.querySelector("#errorRawBoxWrap"),
  errorRawData: document.querySelector("#errorRawData"),
  rawLengthInfo: document.querySelector("#rawLengthInfo"),
  copyErrorBtn: document.querySelector("#copyErrorBtn"),
  viewInConsoleBtn: document.querySelector("#viewInConsoleBtn"),
  closeErrorBtn: document.querySelector("#closeErrorBtn"),

  // Debug Console Elements
  openDebugNavBtn: document.querySelector("#openDebugNavBtn"),
  quickDebugBtn: document.querySelector("#quickDebugBtn"),
  debugModal: document.querySelector("#debugModal"),
  closeDebugModalBtn: document.querySelector("#closeDebugModalBtn"),
  debugLogList: document.querySelector("#debugLogList"),
  copyAllLogsBtn: document.querySelector("#copyAllLogsBtn"),
  clearLogsBtn: document.querySelector("#clearLogsBtn"),
  debugBadge: document.querySelector("#debugBadge"),
  debugSystemInfo: document.querySelector("#debugSystemInfo"),
  autoRefreshCheck: document.querySelector("#autoRefreshCheck"),
  countAll: document.querySelector("#countAll"),
  countError: document.querySelector("#countError"),
  countSerial: document.querySelector("#countSerial"),
  countParser: document.querySelector("#countParser"),
  countDevice: document.querySelector("#countDevice"),
};

const state = {
  connected: false,
  port: null,
  scanning: false,
  measurements: [],
  debugLogs: [],
  activeFilter: "all",
  lastErrorData: null,
};

let toastTimer;
let debugPollTimer;

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || `Permintaan gagal (${response.status})`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function showToast(message, type = "success") {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.className = `toast visible${type === "error" ? " error" : ""}`;
  toastTimer = setTimeout(() => {
    elements.toast.className = "toast";
  }, 5000);
}

function showErrorInspector(title, error) {
  const nowStr = new Date().toLocaleTimeString("id-ID");
  const payload = error.payload || {};
  const details = payload.details || {};
  const rawLine = details.raw_line || payload.last_raw_line || error.raw_line || "";

  state.lastErrorData = {
    title,
    time: nowStr,
    message: error.message,
    status: error.status,
    rawLine,
    details,
    device: payload.device || { port: state.port, connected: state.connected },
  };

  elements.errorInspectorTitle.textContent = title;
  elements.errorInspectorTime.textContent = nowStr;
  elements.errorInspectorMsg.textContent = error.message;

  if (rawLine) {
    elements.errorRawBoxWrap.style.display = "block";
    elements.errorRawData.textContent = rawLine;
    const len = rawLine.length;
    const cols = details.field_count || (rawLine.startsWith("DATA,") ? rawLine.split(",").length : null);
    elements.rawLengthInfo.textContent = `${len} karakter${cols ? ` · ${cols} kolom` : ""}`;
  } else {
    elements.errorRawBoxWrap.style.display = "none";
  }

  elements.errorInspector.classList.remove("hidden");
  elements.errorInspector.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function hideErrorInspector() {
  elements.errorInspector.classList.add("hidden");
}

async function copyErrorDetails() {
  if (!state.lastErrorData) return;
  const d = state.lastErrorData;
  const report = [
    `=== BUAHSAFE ERROR REPORT ===`,
    `Waktu       : ${d.time}`,
    `Judul       : ${d.title}`,
    `Pesan Error : ${d.message}`,
    `Port Serial : ${d.device?.port || "Tidak terhubung"}`,
    `Status Dev  : ${d.device?.connected ? "Connected" : "Disconnected"}`,
    d.details?.field_count ? `Kolom Diterima : ${d.details.field_count} (Diharapkan: ${d.details.expected_count || 20})` : null,
    d.rawLine ? `\n--- DATA MENTAH SERIAL (${d.rawLine.length} chars) ---\n${d.rawLine}` : null,
  ].filter(Boolean).join("\n");

  try {
    await navigator.clipboard.writeText(report);
    const origText = elements.copyErrorBtn.textContent;
    elements.copyErrorBtn.textContent = "✔️ Tersalin ke Clipboard!";
    setTimeout(() => { elements.copyErrorBtn.textContent = origText; }, 2000);
    showToast("Detail error berhasil disalin ke clipboard");
  } catch {
    showToast("Gagal menyalin otomatis, silakan pilih dan salin teks secara manual.", "error");
  }
}

function updateClock() {
  const now = new Date();
  elements.liveClock.textContent = new Intl.DateTimeFormat("id-ID", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).format(now).replaceAll(".", "");
}

function applyDeviceStatus(device) {
  state.connected = Boolean(device.connected);
  state.port = device.port || null;
  elements.connectionLight.classList.toggle("online", state.connected);
  elements.deviceName.textContent = state.connected ? `ESP32 · ${state.port}` : "ESP32 belum terhubung";
  elements.sensorStatus.textContent = state.connected ? "AS7265x siap · 115200 baud" : (device.last_error || "Pilih port serial");
  elements.connectButton.textContent = state.connected ? "Putuskan koneksi" : "Hubungkan ESP32";
  elements.connectButton.classList.toggle("connected", state.connected);
  elements.portSelect.disabled = state.connected;
  updateScanAvailability();
}

function updateScanAvailability() {
  const validId = /^[A-Za-z0-9][A-Za-z0-9_-]{0,30}$/.test(elements.fruitId.value.trim());
  elements.scanButton.disabled = !state.connected || !validId || state.scanning;
}

function applySummary(summary) {
  elements.totalScans.textContent = String(summary.total_scans || 0).padStart(3, "0");
  elements.unlabeledCount.textContent = String(summary.unlabeled || 0).padStart(3, "0");
  elements.totalFruitText.textContent = `${summary.total_fruits || 0} jambu tersimpan`;
}

function updateSpectrum(measurement) {
  const values = CHANNEL_KEYS.map((channel) => Number(measurement[channel] || 0));
  const maximum = Math.max(...values, 0.000001);

  CHANNEL_KEYS.forEach((channel, index) => {
    const bar = document.querySelector(`[data-channel="${channel}"]`);
    if (!bar) return;
    const column = bar.closest(".bar-column");
    const valText = values[index] >= 100 ? values[index].toFixed(1) : values[index].toFixed(2);
    column.querySelector(".bar-value").textContent = valText;
    bar.style.height = `${Math.max((values[index] / maximum) * 100, 2)}%`;
  });
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);
}

function formatTimestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("id-ID", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).format(date);
}

function renderMeasurements() {
  if (!state.measurements.length) {
    elements.measurementRows.innerHTML = '<tr><td class="empty-state" colspan="22">Belum ada data pengukuran.</td></tr>';
    return;
  }

  elements.measurementRows.innerHTML = state.measurements.map((row) => `
    <tr>
      <td>${escapeHtml(formatTimestamp(row.timestamp))}</td>
      <td class="fruit-code">${escapeHtml(row.fruit_id)}</td>
      <td>#${String(row.scan_no).padStart(3, "0")}</td>
      ${CHANNEL_KEYS.map((key) => `<td class="numeric">${Number(row[key] || 0).toFixed(4)}</td>`).join("")}
      <td>
        <select class="label-select" data-measurement-id="${row.id}" value="${escapeHtml(row.label)}" aria-label="Label ${escapeHtml(row.fruit_id)}">
          <option value="" ${row.label === "" ? "selected" : ""}>Kosong</option>
          <option value="bagus" ${row.label === "bagus" ? "selected" : ""}>Bagus</option>
          <option value="rusak" ${row.label === "rusak" ? "selected" : ""}>Rusak</option>
        </select>
      </td>
    </tr>`).join("");
}

async function loadPorts() {
  try {
    const payload = await api("/api/ports");
    elements.portSelect.innerHTML = payload.ports.length
      ? '<option value="">Pilih port COM</option>' + payload.ports.map((port) => `<option value="${escapeHtml(port.device)}">${escapeHtml(port.device)} · ${escapeHtml(port.description)}</option>`).join("")
      : '<option value="">Tidak ada port terdeteksi</option>';
  } catch (err) {
    console.error("Gagal load ports:", err);
  }
}

async function loadInitialData() {
  try {
    const [statusPayload, measurementPayload] = await Promise.all([
      api("/api/status"), api("/api/measurements?limit=250"), loadPorts(),
    ]);
    applyDeviceStatus(statusPayload.device);
    applySummary(statusPayload.summary);
    state.measurements = measurementPayload.measurements;
    renderMeasurements();
    if (state.measurements[0]) updateSpectrum(state.measurements[0]);
    fetchDebugLogs();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function toggleConnection() {
  elements.connectButton.disabled = true;
  hideErrorInspector();
  try {
    if (state.connected) {
      const payload = await api("/api/disconnect", { method: "POST", body: "{}" });
      applyDeviceStatus(payload.device);
      showToast("Koneksi ESP32 diputuskan");
    } else {
      if (!elements.portSelect.value) throw new Error("Pilih port COM terlebih dahulu");
      elements.connectButton.textContent = "Menghubungkan...";
      const payload = await api("/api/connect", {
        method: "POST", body: JSON.stringify({ port: elements.portSelect.value }),
      });
      applyDeviceStatus(payload.device);
      showToast(`ESP32 terhubung melalui ${payload.device.port}`);
    }
  } catch (error) {
    showErrorInspector("Koneksi ESP32 Gagal", error);
    showToast(error.message, "error");
    const status = await api("/api/status").catch(() => null);
    if (status) applyDeviceStatus(status.device);
  } finally {
    elements.connectButton.disabled = false;
    fetchDebugLogs();
  }
}

async function scan() {
  state.scanning = true;
  hideErrorInspector();
  elements.scanButton.classList.add("loading");
  elements.scanButtonText.textContent = "Sedang memindai...";
  elements.lastStatus.textContent = "Memindai";
  elements.lastStatusDetail.textContent = "Tunggu bunyi buzzer dan pembacaan 18 kanal AS7265x";
  updateScanAvailability();

  try {
    const payload = await api("/api/scan", {
      method: "POST", body: JSON.stringify({ fruit_id: elements.fruitId.value.trim() }),
    });
    state.measurements.unshift(payload.measurement);
    renderMeasurements();
    updateSpectrum(payload.measurement);
    applySummary(payload.summary);
    elements.lastStatus.textContent = "Berhasil";
    elements.lastStatusDetail.textContent = `Scan #${payload.measurement.scan_no} tersimpan · baru saja`;
    showToast(`Data ${payload.measurement.fruit_id} (#${payload.measurement.scan_no}) berhasil disimpan`);
  } catch (error) {
    elements.lastStatus.textContent = "Gagal";
    elements.lastStatusDetail.textContent = error.message;
    showErrorInspector("Scan Spektrum Gagal", error);
    showToast(error.message, "error");
  } finally {
    state.scanning = false;
    elements.scanButton.classList.remove("loading");
    elements.scanButtonText.textContent = "Ambil satu scan";
    updateScanAvailability();
    fetchDebugLogs();
  }
}

async function updateLabel(select) {
  const previous = state.measurements.find((row) => row.id === Number(select.dataset.measurementId));
  try {
    const payload = await api(`/api/measurements/${select.dataset.measurementId}/label`, {
      method: "PATCH", body: JSON.stringify({ label: select.value }),
    });
    if (previous) Object.assign(previous, payload.measurement);
    select.setAttribute("value", select.value);
    applySummary(payload.summary);
    showToast("Label diperbarui");
  } catch (error) {
    if (previous) select.value = previous.label;
    showToast(error.message, "error");
  }
}

// ============================================================
// Debug Console Management
// ============================================================

async function fetchDebugLogs() {
  try {
    const data = await api("/api/debug?limit=200");
    state.debugLogs = data.logs || [];
    renderDebugLogs();

    if (data.system) {
      elements.debugSystemInfo.textContent = `Python ${data.system.python} · ${data.system.platform} · Port: ${data.system.port || "None"} · Scans: ${data.system.summary?.total_scans || 0}`;
    }

    const errCount = state.debugLogs.filter((l) => l.level === "ERROR").length;
    elements.debugBadge.textContent = String(errCount);
    elements.debugBadge.classList.toggle("has-errors", errCount > 0);
  } catch (err) {
    console.debug("Fetch debug logs error:", err);
  }
}

function renderDebugLogs() {
  const logs = state.debugLogs;
  elements.countAll.textContent = String(logs.length);
  elements.countError.textContent = String(logs.filter((l) => l.level === "ERROR").length);
  elements.countSerial.textContent = String(logs.filter((l) => l.category.startsWith("SERIAL")).length);
  elements.countParser.textContent = String(logs.filter((l) => l.category === "PARSER").length);
  elements.countDevice.textContent = String(logs.filter((l) => l.category === "DEVICE").length);

  const filter = state.activeFilter;
  const filtered = logs.filter((log) => {
    if (filter === "all") return true;
    if (filter === "ERROR") return log.level === "ERROR";
    if (filter === "SERIAL") return log.category.startsWith("SERIAL");
    if (filter === "PARSER") return log.category === "PARSER";
    if (filter === "DEVICE") return log.category === "DEVICE";
    return true;
  });

  if (!filtered.length) {
    elements.debugLogList.innerHTML = '<div class="log-empty">Tidak ada log untuk filter ini.</div>';
    return;
  }

  elements.debugLogList.innerHTML = filtered.map((entry) => {
    const lvlClass = entry.level === "ERROR" ? "log-error" : (entry.level === "WARN" ? "log-warn" : "log-info");
    const catClass = `cat-${entry.category.toLowerCase().replace(/[^a-z0-9]/g, "-")}`;
    const rawPreview = entry.raw_data ? `<div class="log-raw">${escapeHtml(entry.raw_data)}</div>` : "";
    return `
      <div class="log-entry ${lvlClass}">
        <span class="log-time">${escapeHtml(entry.timestamp.split(" ")[1] || entry.timestamp)}</span>
        <span class="log-cat ${catClass}">${escapeHtml(entry.category)}</span>
        <span class="log-msg">${escapeHtml(entry.message)}</span>
        ${rawPreview}
      </div>
    `;
  }).join("");
}

function openDebugModal() {
  elements.debugModal.classList.remove("hidden");
  fetchDebugLogs();
  startDebugPolling();
}

function closeDebugModal() {
  elements.debugModal.classList.add("hidden");
  stopDebugPolling();
}

function startDebugPolling() {
  stopDebugPolling();
  debugPollTimer = setInterval(() => {
    if (elements.autoRefreshCheck.checked && !elements.debugModal.classList.contains("hidden")) {
      fetchDebugLogs();
    }
  }, 2000);
}

function stopDebugPolling() {
  if (debugPollTimer) clearInterval(debugPollTimer);
  debugPollTimer = null;
}

async function copyAllDebugLogs() {
  if (!state.debugLogs.length) {
    showToast("Belum ada log untuk disalin.");
    return;
  }
  const lines = state.debugLogs.map((l) => `[${l.timestamp}] [${l.level}] [${l.category}] ${l.message}${l.raw_data ? ` | RAW: ${l.raw_data}` : ""}`);
  const report = [
    `=== BUAHSAFE FULL DEBUG LOG (${new Date().toLocaleString("id-ID")}) ===`,
    `System: ${elements.debugSystemInfo.textContent}`,
    `Total Entries: ${state.debugLogs.length}`,
    `\n` + lines.join("\n"),
  ].join("\n");

  try {
    await navigator.clipboard.writeText(report);
    const orig = elements.copyAllLogsBtn.textContent;
    elements.copyAllLogsBtn.textContent = "✔️ Log Tersalin!";
    setTimeout(() => { elements.copyAllLogsBtn.textContent = orig; }, 2000);
    showToast("Seluruh log debugging berhasil disalin ke clipboard");
  } catch {
    showToast("Gagal menyalin otomatis ke clipboard.", "error");
  }
}

async function clearDebugLogs() {
  await api("/api/debug/clear", { method: "POST" }).catch(() => {});
  state.debugLogs = [];
  renderDebugLogs();
  showToast("Log debugging dibersihkan.");
}

// Event Listeners
elements.connectButton.addEventListener("click", toggleConnection);
elements.scanButton.addEventListener("click", scan);
elements.fruitId.addEventListener("input", () => {
  elements.fruitId.value = elements.fruitId.value.toUpperCase().replace(/[^A-Z0-9_-]/g, "");
  updateScanAvailability();
});
elements.measurementRows.addEventListener("change", (event) => {
  if (event.target.matches(".label-select")) updateLabel(event.target);
});

// Error Inspector Actions
elements.copyErrorBtn.addEventListener("click", copyErrorDetails);
elements.viewInConsoleBtn.addEventListener("click", () => {
  hideErrorInspector();
  openDebugModal();
});
elements.closeErrorBtn.addEventListener("click", hideErrorInspector);

// Debug Modal Actions
elements.openDebugNavBtn.addEventListener("click", openDebugModal);
elements.quickDebugBtn.addEventListener("click", openDebugModal);
elements.closeDebugModalBtn.addEventListener("click", closeDebugModal);
elements.copyAllLogsBtn.addEventListener("click", copyAllDebugLogs);
elements.clearLogsBtn.addEventListener("click", clearDebugLogs);

document.querySelectorAll(".filter-chip").forEach((chip) => {
  chip.addEventListener("click", (e) => {
    document.querySelectorAll(".filter-chip").forEach((c) => c.classList.remove("active"));
    const btn = e.currentTarget;
    btn.classList.add("active");
    state.activeFilter = btn.dataset.filter;
    renderDebugLogs();
  });
});

// Close modal on Escape key or outside click
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !elements.debugModal.classList.contains("hidden")) {
    closeDebugModal();
  }
});
elements.debugModal.addEventListener("click", (e) => {
  if (e.target === elements.debugModal) closeDebugModal();
});

updateClock();
setInterval(updateClock, 1000);
loadInitialData();
