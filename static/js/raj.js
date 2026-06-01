// === RAJ WEB APP - FRONTEND ===

const API_BASE = '';

// === STATE ===
let engineRunning = false;
let refreshInterval = null;

// === INIT ===
document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
    loadActivityLog();
    startAutoRefresh();
    checkEngineStatus();
});

// === AUTO REFRESH ===
function startAutoRefresh() {
    refreshInterval = setInterval(() => {
        loadDashboard();
        loadActivityLog();
    }, 5000); // Refresh every 5 seconds
}

// === DASHBOARD ===
async function loadDashboard() {
    try {
        const res = await fetch(`${API_BASE}/api/dashboard`);
        const data = await res.json();

        renderStats(data.days);
        renderPipeline(data.families);
        engineRunning = data.engine_running;
        updateEngineButton();
    } catch (e) {
        console.error('Dashboard load error:', e);
    }
}

function renderStats(days) {
    const container = document.getElementById('stats-body');
    if (!container) return;

    const dayLabels = ['Day 1', 'Day 3', 'Day 5', 'Day 7', 'Day 10'];
    const dayMap = {1: 'Day 1', 3: 'Day 3', 5: 'Day 5', 7: 'Day 7', 10: 'Day 10'};

    let html = '';
    dayLabels.forEach(label => {
        const sent = days?.sent || 0;
        const total = days?.total || 0;
        const bounced = days?.bounced || 0;
        const replied = days?.replied || 0;
        const status = sent >= total && total > 0 ? 'done' : 'pending';

        html += `
            <div class="stats-row">
                <span class="day">${label}</span>
                <span>${total}</span>
                <span class="sent">${sent}</span>
                <span class="bounced">${bounced}</span>
                <span class="replied">${replied}</span>
                <span>
                    <span class="status-badge ${status === 'done' ? 'status-done' : 'status-pending'}">
                        ${status === 'done' ? '✅ Done' : '⏳ Pending'}
                    </span>
                </span>
            </div>
        `;
    });

    container.innerHTML = html;
}

function renderPipeline(families) {
    const container = document.getElementById('pipeline-container');
    if (!container) return;

    let html = '';

    for (const [familyName, days] of Object.entries(families)) {
        // Determine sequence and total
        let seqId = '';
        let familyTotal = 0;

        for (const dayCode of ['D1', 'D3', 'D5', 'D7', 'D10']) {
            const b = days[dayCode];
            if (b) {
                if (!seqId) seqId = (b.sequence_id || '').toUpperCase();
                familyTotal = Math.max(familyTotal, b.total || 0);
            }
        }

        if (familyTotal === 0) {
            // Try to get from any batch
            for (const dayCode of ['D1', 'D3', 'D5', 'D7', 'D10']) {
                const b = days[dayCode];
                if (b && b.total) {
                    familyTotal = b.total;
                    break;
                }
            }
        }

        const nameColorClass = seqId === 'CSR' ? 'csr' : '';

        html += `
            <div class="family-card">
                <div class="family-header">
                    <span class="family-name ${nameColorClass}">${familyName}</span>
                    <span class="family-count">• ${familyTotal} recipients</span>
                </div>
                <div class="pills-row">
                    ${renderPill('D1', 1, days.D1, familyTotal)}
                    ${renderPill('D3', 3, days.D3, familyTotal)}
                    ${renderPill('D5', 5, days.D5, familyTotal)}
                    ${renderPill('D7', 7, days.D7, familyTotal)}
                    ${renderPill('D10', 10, days.D10, familyTotal)}
                </div>
            </div>
        `;
    }

    container.innerHTML = html;
}

function renderPill(dayLabel, dayNum, batch, familyTotal) {
    if (!batch) {
        // Not created - Queue state
        const projectedDate = getProjectedDate(dayNum);
        return `
            <div class="pill queue">
                <div class="pill-day">
                    <span class="pill-day-label">${dayLabel}</span>
                    <span class="pill-date">${projectedDate}</span>
                </div>
                <div class="pill-count">0/${familyTotal}</div>
                <div class="pill-status-text due">${familyTotal} to send</div>
                <div class="pill-state">Queue</div>
                <div class="pill-actions">
                    <button class="pill-btn pill-btn-run" onclick="createDayBatch('${dayLabel}', ${dayNum})">
                        ▶ Create
                    </button>
                    <button class="pill-btn pill-btn-report" onclick="showReport(null, '${dayLabel}')">
                        📊
                    </button>
                </div>
            </div>
        `;
    }

    const sent = batch.sent || 0;
    const total = familyTotal || batch.total || 0;
    const due = total - sent;
    const status = (batch.status || 'draft').toUpperCase();
    const scheduled = batch.scheduled_at || '';

    // Determine actual status
    let actualStatus = status;
    if (status === 'COMPLETED' && sent < total && total > 0) {
        actualStatus = 'DRAFT';
    }
    if (actualStatus === 'RUNNING' && sent === 0) {
        actualStatus = 'DRAFT';
    }

    // Get date
    const dateText = parseDate(scheduled) || getProjectedDate(dayNum);

    // Pill class
    let pillClass = 'queue';
    if (actualStatus === 'COMPLETED') pillClass = 'done';
    else if (actualStatus === 'RUNNING') pillClass = 'sending';
    else if (actualStatus === 'DRAFT') pillClass = 'ready';
    else if (actualStatus === 'PAUSED') pillClass = 'paused';

    // Status text
    let statusText = '';
    let statusClass = '';
    if (actualStatus === 'COMPLETED') {
        statusText = 'All sent';
        statusClass = 'sent';
    } else if (due > 0) {
        statusText = `${due} due`;
        statusClass = 'due';
    } else {
        statusText = `${total} to send`;
        statusClass = 'due';
    }

    // State label
    const stateLabels = {
        'COMPLETED': 'Done',
        'RUNNING': 'Sending',
        'SCHEDULED': 'Scheduled',
        'DRAFT': 'Ready',
        'PAUSED': 'Paused',
        'NONE': 'Queue'
    };
    const stateLabel = stateLabels[actualStatus] || 'Queue';

    // Buttons
    let actionBtn = '';
    if (actualStatus === 'COMPLETED') {
        actionBtn = `<button class="pill-btn pill-btn-placeholder" disabled>—</button>`;
    } else if (actualStatus === 'RUNNING') {
        actionBtn = `<button class="pill-btn pill-btn-pause" onclick="pauseBatch(${batch.id})">⏸ Pause</button>`;
    } else {
        actionBtn = `<button class="pill-btn pill-btn-run" onclick="startBatch(${batch.id})">▶ Run</button>`;
    }

    return `
        <div class="pill ${pillClass}">
            <div class="pill-day">
                <span class="pill-day-label">${dayLabel}</span>
                <span class="pill-date">${dateText}</span>
            </div>
            <div class="pill-count">${sent}/${total}</div>
            <div class="pill-status-text ${statusClass}">${statusText}</div>
            <div class="pill-state">${stateLabel}</div>
            <div class="pill-actions">
                ${actionBtn}
                <button class="pill-btn pill-btn-report" onclick="showReport(${batch.id}, '${dayLabel}')">📊</button>
            </div>
        </div>
    `;
}

// === DATE HELPERS ===
function parseDate(dateStr) {
    if (!dateStr) return null;
    const formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
        '%Y-%m-%d %H:%M:%S.%f',
        '%d %b %Y',
        '%d %B %Y',
    ];

    // Try ISO
    try {
        const d = new Date(dateStr);
        if (!isNaN(d.getTime())) {
            return d.toLocaleDateString('en-GB', {day: '2-digit', month: 'short'});
        }
    } catch (e) {}

    return null;
}

function getProjectedDate(dayNum) {
    const d = new Date();
    d.setDate(d.getDate() + dayNum);
    return d.toLocaleDateString('en-GB', {day: '2-digit', month: 'short'});
}

// === ACTIONS ===
async function startBatch(batchId) {
    try {
        const res = await fetch(`${API_BASE}/api/batch/${batchId}/start`, {method: 'POST'});
        const data = await res.json();
        if (data.success) {
            loadDashboard();
        }
    } catch (e) {
        console.error('Start batch error:', e);
    }
}

async function pauseBatch(batchId) {
    try {
        const res = await fetch(`${API_BASE}/api/batch/${batchId}/pause`, {method: 'POST'});
        const data = await res.json();
        if (data.success) {
            loadDashboard();
        }
    } catch (e) {
        console.error('Pause batch error:', e);
    }
}

function createDayBatch(dayLabel, dayNum) {
    alert(`Create ${dayLabel} batch - coming soon!`);
}

function showReport(batchId, dayLabel) {
    if (batchId) {
        window.open(`${API_BASE}/api/batch/${batchId}/recipients`, '_blank');
    } else {
        alert(`No data for ${dayLabel} yet`);
    }
}

// === ENGINE ===
async function checkEngineStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/engine/status`);
        const data = await res.json();
        engineRunning = data.running;
        updateEngineButton();
    } catch (e) {}
}

async function toggleEngine() {
    const endpoint = engineRunning ? '/api/engine/stop' : '/api/engine/start';
    try {
        const res = await fetch(`${API_BASE}${endpoint}`, {method: 'POST'});
        const data = await res.json();
        engineRunning = data.running;
        updateEngineButton();
    } catch (e) {
        console.error('Engine toggle error:', e);
    }
}

function updateEngineButton() {
    const icon = document.getElementById('engine-icon');
    const text = document.getElementById('engine-text');
    if (icon && text) {
        icon.textContent = engineRunning ? '⏸' : '▶';
        text.textContent = engineRunning ? 'Stop Engine' : 'Start Engine';
    }
}

// === BOUNCE SCAN ===
async function scanBounces() {
    try {
        const res = await fetch(`${API_BASE}/api/scan/bounces`, {method: 'POST'});
        const data = await res.json();
        alert(data.message || 'Bounce scan started');
    } catch (e) {
        console.error('Bounce scan error:', e);
    }
}

// === ACTIVITY LOG ===
async function loadActivityLog() {
    try {
        const res = await fetch(`${API_BASE}/api/activity`);
        const logs = await res.json();
        renderActivityLog(logs);
    } catch (e) {}
}

function renderActivityLog(logs) {
    const container = document.getElementById('activity-log');
    if (!container) return;

    const html = logs.slice(0, 20).map(log => {
        const time = new Date(log.created_at).toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit'});
        return `<div class="activity-item"><span class="activity-time">${time}</span><span>${log.message}</span></div>`;
    }).join('');

    container.innerHTML = html || '<div class="activity-item">No activity yet</div>';
}

// === MODALS ===
function showImportModal() {
    document.getElementById('import-modal').classList.add('active');
}

function showTemplatesModal() {
    document.getElementById('templates-modal').classList.add('active');
    loadTemplates();
}

function showBatchesModal() {
    alert('Batches view - coming soon!');
}

function showRepliesModal() {
    alert('Replies view - coming soon!');
}

function showBlacklistModal() {
    alert('Blacklist view - coming soon!');
}

function showSettingsModal() {
    alert('Settings - coming soon!');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

async function loadTemplates() {
    try {
        const res = await fetch(`${API_BASE}/api/templates`);
        const templates = await res.json();
        const container = document.getElementById('templates-list');
        if (container) {
            container.innerHTML = templates.map(t => `
                <div style="padding: 10px; border-bottom: 1px solid var(--border-color);">
                    <strong>${t.name}</strong> (${t.sequence_id} Day ${t.day_num})
                    <div style="font-size: 12px; color: var(--text-dim); margin-top: 4px;">${t.subject || 'No subject'}</div>
                </div>
            `).join('') || '<div>No templates found</div>';
        }
    } catch (e) {}
}

async function handleImport(e) {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);

    try {
        const res = await fetch(`${API_BASE}/api/import`, {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        alert(data.message || 'Import started');
        closeModal('import-modal');
    } catch (e) {
        alert('Import failed: ' + e.message);
    }
}

// Close modal on outside click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        e.target.classList.remove('active');
    }
});
