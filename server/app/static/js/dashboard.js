/**
 * Dashboard Docente — Lógica en Tiempo Real (Polling, Acciones y Proxmox VE)
 */

let devices = [];
let currentFilter = 'all';
let searchQuery = '';
let proxmoxVmsCache = [];

document.addEventListener('DOMContentLoaded', () => {
  fetchDevices();
  checkProxmoxStatus();
  setInterval(fetchDevices, 4000);
  setInterval(checkProxmoxStatus, 15000);
});

// =============================================================================
// API & NETWORK CALLS
// =============================================================================

function getHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (window.APP_CONFIG && window.APP_CONFIG.csrfToken) {
    headers['X-CSRFToken'] = window.APP_CONFIG.csrfToken;
  }
  return headers;
}

async function fetchDevices() {
  try {
    const res = await fetch('/api/admin/devices');
    if (res.status === 401) {
      window.location.href = '/login';
      return;
    }
    const data = await res.json();
    devices = data.devices || [];
    updateStatsRibbon();
    renderGrid();
  } catch (err) {
    console.error('Error obteniendo lista de dispositivos:', err);
  }
}

async function checkProxmoxStatus() {
  const badge = document.getElementById('proxmox-status-badge');
  const dot = badge ? badge.querySelector('.pulse-dot') : null;
  const statusText = document.getElementById('pve-status-text');

  try {
    const res = await fetch('/api/admin/proxmox/status');
    const data = await res.json();

    if (data.connected) {
      dot.className = 'pulse-dot connected';
      statusText.textContent = `Online (PVE ${data.version || ''})`;
      statusText.style.color = '#34d399';
    } else {
      dot.className = 'pulse-dot disconnected';
      statusText.textContent = 'Sin Conexión';
      statusText.style.color = '#f87171';
    }
  } catch (err) {
    if (dot) dot.className = 'pulse-dot disconnected';
    if (statusText) {
      statusText.textContent = 'Inalcanzable';
      statusText.style.color = '#f87171';
    }
  }
}

// =============================================================================
// STATS & FILTERING
// =============================================================================

function updateStatsRibbon() {
  const total = devices.length;
  const online = devices.filter(d => d.connection_status === 'connected').length;
  const locked = devices.filter(d => d.lock_status === 'locked').length;
  const withPve = devices.filter(d => d.proxmox_vmid != null).length;

  document.getElementById('stat-total').textContent = total;
  document.getElementById('stat-online').textContent = online;
  document.getElementById('stat-locked').textContent = locked;
  document.getElementById('stat-proxmox').textContent = withPve;

  document.getElementById('count-all').textContent = total;
  document.getElementById('count-online').textContent = online;
  document.getElementById('count-offline').textContent = total - online;
  document.getElementById('count-locked').textContent = locked;
  document.getElementById('count-proxmox').textContent = withPve;
}

function setFilter(filterType, element) {
  currentFilter = filterType;
  document.querySelectorAll('.filter-pills .pill').forEach(p => p.classList.remove('active'));
  if (element) element.classList.add('active');
  renderGrid();
}

function applyFilters() {
  searchQuery = (document.getElementById('filter-search').value || '').trim().toLowerCase();
  renderGrid();
}

function getFilteredDevices() {
  return devices.filter(d => {
    // Filtro por estado
    if (currentFilter === 'online' && d.connection_status !== 'connected') return false;
    if (currentFilter === 'offline' && d.connection_status === 'connected') return false;
    if (currentFilter === 'locked' && d.lock_status !== 'locked') return false;
    if (currentFilter === 'proxmox' && d.proxmox_vmid == null) return false;

    // Filtro de búsqueda textual
    if (searchQuery) {
      const name = (d.name || '').toLowerCase();
      const host = (d.hostname || '').toLowerCase();
      const ip = (d.ip_address || '').toLowerCase();
      const vmid = d.proxmox_vmid ? String(d.proxmox_vmid) : '';
      if (!name.includes(searchQuery) && !host.includes(searchQuery) && !ip.includes(searchQuery) && !vmid.includes(searchQuery)) {
        return false;
      }
    }
    return true;
  });
}

// =============================================================================
// GRID RENDERING
// =============================================================================

function renderGrid() {
  const container = document.getElementById('devices-grid');
  const items = getFilteredDevices();

  if (items.length === 0) {
    container.innerHTML = `
      <div class="empty-state glass-panel" style="grid-column: 1 / -1; padding: 3rem; text-align: center; color: var(--text-muted);">
        <p style="font-size: 1.1rem; margin-bottom: 0.5rem;">No se encontraron equipos bajo los criterios seleccionados.</p>
        <small>Verifica los filtros activos o asegúrate de que el agente esté enrolado y ejecutándose.</small>
      </div>
    `;
    return;
  }

  const now = Date.now();
  container.innerHTML = items.map(d => {
    const isOnline = d.connection_status === 'connected';
    const isLocked = d.lock_status === 'locked';
    const screenshotUrl = `/api/admin/devices/${d.id}/screenshot?t=${now}`;

    // Color de barras de métricas
    const cpu = d.cpu_percent != null ? Math.round(d.cpu_percent) : 0;
    const ram = d.ram_percent != null ? Math.round(d.ram_percent) : 0;
    const disk = d.disk_percent != null ? Math.round(d.disk_percent) : 0;

    const cpuColor = cpu > 80 ? 'meter-red' : (cpu > 60 ? 'meter-amber' : 'meter-blue');
    const ramColor = ram > 85 ? 'meter-red' : (ram > 70 ? 'meter-amber' : 'meter-green');

    return `
      <div class="device-card ${isOnline ? 'status-online' : 'status-offline'} ${isLocked ? 'status-locked' : ''}" id="card-device-${d.id}">
        <!-- Header -->
        <div class="card-header">
          <div class="card-title-group">
            <div>
              <div class="device-name">${escapeHtml(d.name)}</div>
              <div class="device-ip">${escapeHtml(d.ip_address || d.hostname)}</div>
            </div>
          </div>
          <div class="card-badges">
            ${d.proxmox_vmid ? `<span class="badge badge-purple" title="VM en Proxmox">VM #${d.proxmox_vmid}</span>` : ''}
            <span class="badge ${isOnline ? 'badge-green' : 'badge-gray'}">${isOnline ? 'En Línea' : 'Offline'}</span>
            ${isLocked ? `<span class="badge badge-red">Bloqueado</span>` : ''}
          </div>
        </div>

        <!-- Pantalla en Vivo -->
        <div class="screen-preview-container" onclick="openScreenZoom('${d.id}', '${escapeHtml(d.name)}')">
          <img src="${screenshotUrl}" alt="Pantalla de ${escapeHtml(d.name)}" class="screen-img" loading="lazy">
          <div class="screen-overlay-expand" title="Ver pantalla completa">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 3 21 3 21 9"></polyline>
              <polyline points="9 21 3 21 3 15"></polyline>
              <line x1="21" y1="3" x2="14" y2="10"></line>
              <line x1="3" y1="21" x2="10" y2="14"></line>
            </svg>
          </div>
          ${isLocked ? `
            <div class="screen-status-overlay lock-overlay">
              <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
              </svg>
              <span>PANTALLA BLOQUEADA</span>
            </div>
          ` : ''}
        </div>

        <!-- Métricas psutil -->
        <div class="card-metrics">
          <div class="metric-row">
            <span class="metric-label">CPU</span>
            <div class="meter-track">
              <div class="meter-fill ${cpuColor}" style="width: ${cpu}%"></div>
            </div>
            <span class="metric-val">${cpu}%</span>
          </div>
          <div class="metric-row">
            <span class="metric-label">RAM</span>
            <div class="meter-track">
              <div class="meter-fill ${ramColor}" style="width: ${ram}%"></div>
            </div>
            <span class="metric-val">${ram}%</span>
          </div>
          <div class="metric-row">
            <span class="metric-label">Disco</span>
            <div class="meter-track">
              <div class="meter-fill meter-blue" style="width: ${disk}%"></div>
            </div>
            <span class="metric-val">${disk}%</span>
          </div>
        </div>

        <!-- Acciones Rápidas -->
        <div class="card-actions">
          <div class="card-actions-left">
            ${isLocked ? `
              <button class="btn btn-sm btn-success" onclick="sendCommand(${d.id}, 'unlock')" title="Desbloquear pantalla">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                  <path d="M7 11V7a5 5 0 0 1 9.9-1"></path>
                </svg>
                Liberar
              </button>
            ` : `
              <button class="btn btn-sm btn-warning" onclick="sendCommand(${d.id}, 'lock')" title="Bloquear pantalla del alumno">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                  <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                </svg>
                Bloquear
              </button>
            `}
            <button class="btn btn-sm btn-outline" onclick="openMessageModal(${d.id}, '${escapeHtml(d.name)}')" title="Enviar mensaje">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
              </svg>
              Mensaje
            </button>
          </div>

          <div class="card-actions-right">
            ${d.proxmox_vmid ? `
              <button class="btn btn-sm btn-purple" onclick="openRestoreModal(${d.id}, '${escapeHtml(d.name)}', ${d.proxmox_vmid}, '${d.proxmox_node || 'pve'}')" title="Rollback Proxmox al estado limpio">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="23 4 23 10 17 10"></polyline>
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                </svg>
                Recuperar
              </button>
            ` : `
              <button class="btn btn-sm btn-outline" onclick="openAssignModal(${d.id}, '${escapeHtml(d.name)}')" title="Vincular a VM de Proxmox">
                + Proxmox
              </button>
            `}
            <button class="btn btn-sm btn-outline-danger" onclick="confirmPowerAction(${d.id}, '${escapeHtml(d.name)}')" title="Reiniciar o Apagar">
              ⚡
            </button>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// =============================================================================
// COMMANDS (INDIVIDUAL & GLOBAL)
// =============================================================================

async function sendCommand(deviceId, type, payload = {}) {
  try {
    const res = await fetch(`/api/admin/devices/${deviceId}/command`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ type, payload }),
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Orden '${type}' enviada con éxito`, 'success');
      fetchDevices();
    } else {
      showToast(`Error: ${data.error || 'No se pudo enviar la orden'}`, 'error');
    }
  } catch (err) {
    showToast('Fallo de comunicación con el servidor', 'error');
  }
}

async function confirmGlobalCommand(type, message) {
  if (!confirm(message)) return;
  try {
    const res = await fetch('/api/admin/devices/command-all', {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ type }),
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Orden masiva '${type}' enviada a ${data.commands_dispatched} equipos`, 'success');
      fetchDevices();
    } else {
      showToast(`Error: ${data.error}`, 'error');
    }
  } catch (err) {
    showToast('Error enviando orden masiva', 'error');
  }
}

function confirmPowerAction(deviceId, name) {
  const action = prompt(`Acciones de energía para ${name}:\nEscribe 'reboot' para reiniciar o 'poweroff' para apagar:`, 'reboot');
  if (!action) return;
  const act = action.trim().toLowerCase();
  if (act === 'reboot' || act === 'poweroff' || act === 'shutdown') {
    sendCommand(deviceId, act);
  } else {
    alert("Acción no válida. Usa 'reboot' o 'poweroff'.");
  }
}

// =============================================================================
// PROXMOX RESTORE MODAL & WORKFLOW
// =============================================================================

function openRestoreModal(deviceId, name, vmid, node) {
  document.getElementById('modal-restore-device-id').value = deviceId;
  document.getElementById('modal-restore-name').textContent = name;
  document.getElementById('modal-restore-vmid').textContent = vmid;
  document.getElementById('modal-restore-node').textContent = node || 'pve';

  document.getElementById('restore-progress-box').classList.add('hidden');
  document.getElementById('btn-confirm-restore').disabled = false;
  document.getElementById('btn-cancel-restore').disabled = false;

  openModal('modal-restore');
}

async function submitProxmoxRestore() {
  const deviceId = document.getElementById('modal-restore-device-id').value;
  const progressBox = document.getElementById('restore-progress-box');
  const btnConfirm = document.getElementById('btn-confirm-restore');
  const btnCancel = document.getElementById('btn-cancel-restore');

  progressBox.classList.remove('hidden');
  btnConfirm.disabled = true;
  btnCancel.disabled = true;

  try {
    const res = await fetch(`/api/admin/devices/${deviceId}/proxmox-restore`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ snapshot: 'estado_limpio' }),
    });
    const data = await res.json();

    if (res.ok) {
      showToast(`VM restaurada a 'estado_limpio' e iniciada`, 'success');
      closeModal('modal-restore');
      fetchDevices();
    } else {
      showToast(`Error de Proxmox: ${data.message || data.error}`, 'error');
      btnConfirm.disabled = false;
      btnCancel.disabled = false;
      progressBox.classList.add('hidden');
    }
  } catch (err) {
    showToast('Error de conexión durante el rollback de Proxmox', 'error');
    btnConfirm.disabled = false;
    btnCancel.disabled = false;
    progressBox.classList.add('hidden');
  }
}

async function confirmGlobalRestore() {
  const withVm = devices.filter(d => d.proxmox_vmid != null);
  if (withVm.length === 0) {
    alert("No hay equipos con VM de Proxmox vinculada.");
    return;
  }

  const ok = confirm(`¿Estás seguro de restaurar simultáneamente ${withVm.length} máquinas virtuales de estudiantes al snapshot 'estado_limpio'? Esta acción borrará cambios no guardados en las VMs.`);
  if (!ok) return;

  try {
    const res = await fetch('/api/admin/devices/proxmox-restore-all', {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ snapshot: 'estado_limpio' }),
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Rollback ejecutado en ${data.restored.length} VMs`, 'success');
      fetchDevices();
    } else {
      showToast(`Error: ${data.error}`, 'error');
    }
  } catch (err) {
    showToast('Error en recuperación masiva de Proxmox', 'error');
  }
}

// =============================================================================
// ASSIGN PROXMOX VM MODAL
// =============================================================================

async function openAssignModal(deviceId, name) {
  document.getElementById('modal-assign-device-id').value = deviceId;
  document.getElementById('modal-assign-name').textContent = `Asignar máquina virtual Proxmox a ${name}`;
  document.getElementById('modal-assign-vmid').value = '';

  const select = document.getElementById('modal-assign-select');
  select.innerHTML = '<option value="">-- Cargando VMs de Proxmox... --</option>';

  openModal('modal-assign-vm');

  try {
    const res = await fetch('/api/admin/proxmox/vms');
    const data = await res.json();
    proxmoxVmsCache = data.vms || [];

    if (proxmoxVmsCache.length > 0) {
      select.innerHTML = '<option value="">-- Selecciona una VM de Proxmox --</option>' +
        proxmoxVmsCache.map(vm => `<option value="${vm.vmid}" data-node="${vm.node || 'pve'}">VM #${vm.vmid} - ${vm.name || 'Sin nombre'} (${vm.status || 'unknown'})</option>`).join('');
    } else {
      select.innerHTML = '<option value="">(No se encontraron VMs en Proxmox o error de conexión)</option>';
    }
  } catch (err) {
    select.innerHTML = '<option value="">Error cargando VMs de Proxmox</option>';
  }
}

function syncVmSelect() {
  const select = document.getElementById('modal-assign-select');
  const selectedOption = select.options[select.selectedIndex];
  if (selectedOption && selectedOption.value) {
    document.getElementById('modal-assign-vmid').value = selectedOption.value;
    const node = selectedOption.getAttribute('data-node') || 'pve';
    document.getElementById('modal-assign-node').value = node;
  }
}

async function submitAssignProxmox() {
  const deviceId = document.getElementById('modal-assign-device-id').value;
  const vmid = document.getElementById('modal-assign-vmid').value;
  const node = document.getElementById('modal-assign-node').value;

  if (!vmid) {
    alert("Debes ingresar un VMID.");
    return;
  }

  try {
    const res = await fetch(`/api/admin/devices/${deviceId}/assign-proxmox`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ proxmox_vmid: parseInt(vmid, 10), proxmox_node: node }),
    });
    if (res.ok) {
      showToast('Asociación con Proxmox guardada', 'success');
      closeModal('modal-assign-vm');
      fetchDevices();
    } else {
      showToast('Error asignando VMID', 'error');
    }
  } catch (err) {
    showToast('Fallo al guardar VMID', 'error');
  }
}

// =============================================================================
// MESSAGE MODAL
// =============================================================================

function openMessageModal(deviceId, name) {
  document.getElementById('modal-msg-device-id').value = deviceId;
  document.getElementById('modal-msg-title').textContent = `Enviar Mensaje a ${name}`;
  document.getElementById('modal-msg-target-desc').textContent = `El mensaje aparecerá como una ventana emergente en el escritorio de ${name}.`;
  document.getElementById('modal-msg-text').value = '';
  openModal('modal-message');
}

function openGlobalMessageModal() {
  document.getElementById('modal-msg-device-id').value = 'all';
  document.getElementById('modal-msg-title').textContent = 'Enviar Mensaje a Toda el Aula';
  document.getElementById('modal-msg-target-desc').textContent = 'El mensaje aparecerá simultáneamente en las pantallas de todos los estudiantes.';
  document.getElementById('modal-msg-text').value = '';
  openModal('modal-message');
}

async function submitMessage() {
  const deviceId = document.getElementById('modal-msg-device-id').value;
  const text = document.getElementById('modal-msg-text').value.trim();

  if (!text) {
    alert("Por favor escribe el mensaje a enviar.");
    return;
  }

  if (deviceId === 'all') {
    await confirmGlobalCommand('message', '¿Enviar este mensaje a toda el aula?');
  } else {
    await sendCommand(deviceId, 'message', { message: text });
  }
  closeModal('modal-message');
}

// =============================================================================
// AUDIT & PROXMOX MODALS
// =============================================================================

async function openEventsModal() {
  openModal('modal-events');
  loadEvents();
}

async function loadEvents() {
  const tbody = document.getElementById('events-table-body');
  tbody.innerHTML = '<tr><td colspan="4" class="text-center">Cargando eventos de auditoría...</td></tr>';

  try {
    const res = await fetch('/api/admin/events?limit=50');
    const data = await res.json();
    const list = data.events || [];

    if (list.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="text-center">No hay eventos registrados.</td></tr>';
      return;
    }

    tbody.innerHTML = list.map(ev => {
      const date = new Date(ev.created_at).toLocaleString();
      const dev = devices.find(d => d.id === ev.device_id);
      const devName = dev ? dev.name : (ev.device_id ? `PC #${ev.device_id}` : 'General / Servidor');
      const details = JSON.stringify(ev.details || {});

      return `
        <tr>
          <td class="font-mono">${date}</td>
          <td><span class="badge badge-purple">${escapeHtml(ev.event_type)}</span></td>
          <td>${escapeHtml(devName)}</td>
          <td><code class="font-mono" style="font-size: 0.75rem;">${escapeHtml(details)}</code></td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="4" class="text-center text-danger">Error cargando eventos.</td></tr>';
  }
}

async function openProxmoxModal() {
  openModal('modal-proxmox');
  loadProxmoxModalData();
}

async function loadProxmoxModalData() {
  const statusDiv = document.getElementById('pve-detailed-status');
  const tbody = document.getElementById('pve-vms-table-body');

  statusDiv.className = 'alert alert-info';
  statusDiv.textContent = 'Comprobando conexión con Proxmox VE...';
  tbody.innerHTML = '<tr><td colspan="5" class="text-center">Cargando lista de máquinas virtuales...</td></tr>';

  try {
    const [statusRes, vmsRes] = await Promise.all([
      fetch('/api/admin/proxmox/status'),
      fetch('/api/admin/proxmox/vms'),
    ]);

    const statusData = await statusRes.json();
    const vmsData = await vmsRes.json();

    if (statusData.connected) {
      statusDiv.className = 'alert alert-purple';
      statusDiv.innerHTML = `<strong>Conectado a Proxmox VE:</strong> Servidor ${statusData.host} &bull; Versión: ${statusData.version || 'PVE'} (Release ${statusData.release || ''})`;
    } else {
      statusDiv.className = 'alert alert-danger';
      statusDiv.innerHTML = `<strong>Sin Conexión a Proxmox:</strong> ${escapeHtml(statusData.error || 'Verifica la IP, puerto 8006 y credenciales en .env')}`;
    }

    const vms = vmsData.vms || [];
    if (vms.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-center">No se encontraron VMs o Proxmox no respondió.</td></tr>';
      return;
    }

    tbody.innerHTML = vms.map(vm => `
      <tr>
        <td class="font-mono text-purple">#${vm.vmid}</td>
        <td><strong>${escapeHtml(vm.name || 'Sin nombre')}</strong></td>
        <td>${escapeHtml(vm.node || 'pve')}</td>
        <td><span class="badge ${vm.status === 'running' ? 'badge-green' : 'badge-gray'}">${escapeHtml(vm.status || 'unknown')}</span></td>
        <td class="font-mono" style="font-size: 0.8rem;">${vm.cpus ? vm.cpus + ' vCPU' : '-'} / ${vm.maxmem ? Math.round(vm.maxmem / (1024*1024*1024)) + ' GB' : '-'}</td>
      </tr>
    `).join('');
  } catch (err) {
    statusDiv.className = 'alert alert-danger';
    statusDiv.textContent = 'Error consultando la API de Proxmox.';
    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Fallo de red al consultar Proxmox.</td></tr>';
  }
}

// =============================================================================
// SCREEN ZOOM MODAL
// =============================================================================

function openScreenZoom(deviceId, name) {
  const modal = document.getElementById('modal-screen-zoom');
  const img = document.getElementById('zoom-image');
  const title = document.getElementById('zoom-title');

  title.textContent = `Pantalla de ${name} (En Vivo)`;
  img.src = `/api/admin/devices/${deviceId}/screenshot?t=${Date.now()}`;
  openModal('modal-screen-zoom');
}

// =============================================================================
// UI HELPERS (MODALS, TOASTS, ESCAPING)
// =============================================================================

function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('hidden');
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('hidden');
}

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
