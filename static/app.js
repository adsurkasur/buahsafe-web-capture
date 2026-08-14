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
};

const state = { connected: false, port: null, scanning: false, measurements: [] };
let toastTimer;

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Permintaan gagal (${response.status})`);
  return payload;
}

function showToast(message, type = "success") {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.className = `toast visible${type === "error" ? " error" : ""}`;
  toastTimer = setTimeout(() => { elements.toast.className = "toast"; }, 4200);
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
  const payload = await api("/api/ports");
  elements.portSelect.innerHTML = payload.ports.length
    ? '<option value="">Pilih port COM</option>' + payload.ports.map((port) => `<option value="${escapeHtml(port.device)}">${escapeHtml(port.device)} · ${escapeHtml(port.description)}</option>`).join("")
    : '<option value="">Tidak ada port terdeteksi</option>';
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
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function toggleConnection() {
  elements.connectButton.disabled = true;
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
    showToast(error.message, "error");
    const status = await api("/api/status").catch(() => null);
    if (status) applyDeviceStatus(status.device);
  } finally {
    elements.connectButton.disabled = false;
  }
}

async function scan() {
  state.scanning = true;
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
    showToast(`Data ${payload.measurement.fruit_id} berhasil disimpan`);
  } catch (error) {
    elements.lastStatus.textContent = "Gagal";
    elements.lastStatusDetail.textContent = error.message;
    showToast(error.message, "error");
  } finally {
    state.scanning = false;
    elements.scanButton.classList.remove("loading");
    elements.scanButtonText.textContent = "Ambil satu scan";
    updateScanAvailability();
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

elements.connectButton.addEventListener("click", toggleConnection);
elements.scanButton.addEventListener("click", scan);
elements.fruitId.addEventListener("input", () => {
  elements.fruitId.value = elements.fruitId.value.toUpperCase().replace(/[^A-Z0-9_-]/g, "");
  updateScanAvailability();
});
elements.measurementRows.addEventListener("change", (event) => {
  if (event.target.matches(".label-select")) updateLabel(event.target);
});

updateClock();
setInterval(updateClock, 1000);
loadInitialData();
