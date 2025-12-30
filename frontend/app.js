// API Base URL
const API_BASE = '/api';

// State
let currentUser = null;
let accounts = [];
let groups = [];
let selectedAccountIds = new Set();
let currentMailAccount = null;
let currentFolder = 'inbox';
let currentMailPage = 0;
const MAIL_PAGE_SIZE = 50;
let importMode = 'text';
let importFileContent = '';

// DOM Elements
const loginPage = document.getElementById('login-page');
const mainApp = document.getElementById('main-app');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const logoutBtn = document.getElementById('logout-btn');
const currentUserSpan = document.getElementById('current-user');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    setupEventListeners();
});

// Auth Functions
async function checkAuth() {
    try {
        const res = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
        if (res.ok) {
            currentUser = await res.json();
            showMainApp();
        } else {
            showLoginPage();
        }
    } catch (e) {
        showLoginPage();
    }
}

function showLoginPage() {
    loginPage.classList.remove('hidden');
    mainApp.classList.add('hidden');
}

function showMainApp() {
    loginPage.classList.add('hidden');
    mainApp.classList.remove('hidden');
    currentUserSpan.textContent = currentUser.username;
    loadGroups();
    loadAccounts();
}

async function login(username, password) {
    try {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ username, password })
        });
        if (res.ok) {
            currentUser = await res.json();
            showMainApp();
            loginError.textContent = '';
        } else {
            const data = await res.json();
            loginError.textContent = data.detail || '登录失败';
        }
    } catch (e) {
        loginError.textContent = '网络错误';
    }
}

async function logout() {
    await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
    currentUser = null;
    showLoginPage();
}

// Event Listeners
function setupEventListeners() {
    // Login
    loginForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        login(username, password);
    });

    logoutBtn.addEventListener('click', logout);

    // Tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
            btn.classList.add('active');
            document.getElementById(`${btn.dataset.tab}-tab`).classList.remove('hidden');

            if (btn.dataset.tab === 'mail') {
                populateMailAccountSelect();
            }
        });
    });

    // Account Actions
    document.getElementById('add-account-btn').addEventListener('click', () => openModal('add-account-modal'));
    document.getElementById('batch-import-btn').addEventListener('click', () => openModal('batch-import-modal'));
    document.getElementById('batch-verify-btn').addEventListener('click', batchVerify);
    document.getElementById('export-btn').addEventListener('click', exportAccounts);
    document.getElementById('manage-groups-btn').addEventListener('click', () => {
        renderGroupsList();
        openModal('groups-modal');
    });

    // Search & Filter
    document.getElementById('account-search').addEventListener('input', debounce(loadAccounts, 300));
    document.getElementById('group-filter').addEventListener('change', loadAccounts);
    document.getElementById('status-filter').addEventListener('change', loadAccounts);

    // Select All
    document.getElementById('select-all').addEventListener('change', (e) => {
        const checkboxes = document.querySelectorAll('#accounts-tbody input[type="checkbox"]');
        checkboxes.forEach(cb => {
            cb.checked = e.target.checked;
            const id = cb.dataset.id;
            if (e.target.checked) {
                selectedAccountIds.add(id);
            } else {
                selectedAccountIds.delete(id);
            }
        });
        updateBatchActions();
    });

    // Batch Delete
    document.getElementById('batch-delete-btn').addEventListener('click', batchDeleteAccounts);

    // Forms
    document.getElementById('add-account-form').addEventListener('submit', addAccount);
    document.getElementById('batch-import-form').addEventListener('submit', batchImport);
    document.getElementById('edit-account-form').addEventListener('submit', updateAccount);

    // Groups
    document.getElementById('add-group-btn').addEventListener('click', addGroup);

    // Mail
    document.getElementById('mail-search').addEventListener('input', debounce(loadMails, 300));
    document.getElementById('refresh-mail-btn').addEventListener('click', loadMails);

    // Modal Close
    document.querySelectorAll('.modal .close-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.closest('.modal').classList.add('hidden');
        });
    });

    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.add('hidden');
            }
        });
    });

    // Delete Mail
    document.getElementById('delete-mail-btn').addEventListener('click', deleteCurrentMail);
    // Import mode tabs
    setupImportTabs();
}

// Groups Functions
async function loadGroups() {
    try {
        const res = await fetch(`${API_BASE}/groups`, { credentials: 'include' });
        if (res.ok) {
            groups = await res.json();
            populateGroupSelects();
        }
    } catch (e) {
        console.error('Failed to load groups:', e);
    }
}

function populateGroupSelects() {
    const selects = ['group-filter', 'acc-group', 'import-group', 'edit-acc-group'];
    selects.forEach(id => {
        const select = document.getElementById(id);
        if (!select) return;

        const currentValue = select.value;
        const isFilter = id === 'group-filter';

        select.innerHTML = isFilter ? '<option value="">全部分组</option>' : '<option value="">无分组</option>';
        groups.forEach(g => {
            select.innerHTML += `<option value="${g.id}">${g.name}</option>`;
        });

        select.value = currentValue;
    });
}

function renderGroupsList() {
    const list = document.getElementById('groups-list');
    list.innerHTML = groups.map(g => `
        <li>
            <span>${g.name}</span>
            <button class="btn btn-danger btn-small" onclick="deleteGroup('${g.id}')">删除</button>
        </li>
    `).join('');
}

async function addGroup() {
    const input = document.getElementById('new-group-name');
    const name = input.value.trim();
    if (!name) return;

    try {
        const res = await fetch(`${API_BASE}/groups`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ name })
        });
        if (res.ok) {
            input.value = '';
            await loadGroups();
            renderGroupsList();
            showToast('分组已添加', 'success');
        } else {
            const data = await res.json();
            showToast(data.detail || '添加失败', 'error');
        }
    } catch (e) {
        showToast('网络错误', 'error');
    }
}

async function deleteGroup(id) {
    if (!confirm('确定删除此分组？')) return;

    try {
        const res = await fetch(`${API_BASE}/groups/${id}`, {
            method: 'DELETE',
            credentials: 'include'
        });
        if (res.ok) {
            await loadGroups();
            renderGroupsList();
            loadAccounts();
            showToast('分组已删除', 'success');
        }
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

// Accounts Functions
async function loadAccounts() {
    const search = document.getElementById('account-search').value;
    const groupId = document.getElementById('group-filter').value;
    const status = document.getElementById('status-filter').value;

    const params = new URLSearchParams();
    if (search) params.append('search', search);
    if (groupId) params.append('group_id', groupId);
    if (status) params.append('status', status);

    try {
        const res = await fetch(`${API_BASE}/accounts?${params}`, { credentials: 'include' });
        if (res.ok) {
            accounts = await res.json();
            renderAccountsTable();
        }
    } catch (e) {
        console.error('Failed to load accounts:', e);
    }
}

function renderAccountsTable() {
    const tbody = document.getElementById('accounts-tbody');

    if (accounts.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="empty-state">
                    <p>暂无账号</p>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = accounts.map(a => {
        const group = groups.find(g => g.id === a.group_id);
        const statusClass = `status-${a.status}`;
        const statusText = { active: '有效', invalid: '失效', unknown: '未知' }[a.status] || '未知';
        const lastVerified = a.last_verified ? new Date(a.last_verified).toLocaleString() : '-';

        return `
            <tr>
                <td><input type="checkbox" data-id="${a.id}" ${selectedAccountIds.has(a.id) ? 'checked' : ''} onchange="toggleSelect('${a.id}')"></td>
                <td>${escapeHtml(a.email)}</td>
                <td>${escapeHtml(a.client_id.substring(0, 8))}...</td>
                <td>${group ? escapeHtml(group.name) : '-'}</td>
                <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                <td>${lastVerified}</td>
                <td>
                    <button class="btn btn-secondary btn-small" onclick="verifyAccount('${a.id}')">测活</button>
                    <button class="btn btn-secondary btn-small" onclick="editAccount('${a.id}')">编辑</button>
                    <button class="btn btn-danger btn-small" onclick="deleteAccount('${a.id}')">删除</button>
                </td>
            </tr>
        `;
    }).join('');
}

function toggleSelect(id) {
    if (selectedAccountIds.has(id)) {
        selectedAccountIds.delete(id);
    } else {
        selectedAccountIds.add(id);
    }
    updateBatchActions();
}

function updateBatchActions() {
    const batchActions = document.getElementById('batch-actions');
    const selectedCount = document.getElementById('selected-count');

    if (selectedAccountIds.size > 0) {
        batchActions.classList.remove('hidden');
        selectedCount.textContent = `已选择 ${selectedAccountIds.size} 项`;
    } else {
        batchActions.classList.add('hidden');
    }
}

async function addAccount(e) {
    e.preventDefault();

    const data = {
        email: document.getElementById('acc-email').value,
        password: document.getElementById('acc-password').value,
        refresh_token: document.getElementById('acc-refresh-token').value,
        client_id: document.getElementById('acc-client-id').value,
        group_id: document.getElementById('acc-group').value || null
    };

    try {
        const res = await fetch(`${API_BASE}/accounts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });
        if (res.ok) {
            closeModal('add-account-modal');
            e.target.reset();
            loadAccounts();
            showToast('账号已添加', 'success');
        } else {
            const err = await res.json();
            showToast(err.detail || '添加失败', 'error');
        }
    } catch (e) {
        showToast('网络错误', 'error');
    }
}

async function batchImport(e) {
    e.preventDefault();

    // Get data from either text mode or file mode
    let importData = '';
    if (importMode === 'file' && importFileContent) {
        importData = importFileContent;
    } else {
        importData = document.getElementById('import-data').value;
    }

    if (!importData.trim()) {
        showToast('请输入或上传导入数据', 'error');
        return;
    }

    const data = {
        data: importData,
        group_id: document.getElementById('import-group').value || null
    };

    try {
        const res = await fetch(`${API_BASE}/accounts/batch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });
        if (res.ok) {
            const result = await res.json();
            closeModal('batch-import-modal');
            e.target.reset();
            clearImportFile();
            loadAccounts();
            showToast(`导入成功: ${result.imported} 个, 跳过: ${result.skipped} 个, 错误: ${result.errors} 个`, 'success');
        } else {
            const err = await res.json();
            showToast(err.detail || '导入失败', 'error');
        }
    } catch (e) {
        showToast('网络错误', 'error');
    }
}

function editAccount(id) {
    const account = accounts.find(a => a.id === id);
    if (!account) return;

    document.getElementById('edit-acc-id').value = account.id;
    document.getElementById('edit-acc-email').value = account.email;
    document.getElementById('edit-acc-password').value = '';
    document.getElementById('edit-acc-refresh-token').value = '';
    document.getElementById('edit-acc-client-id').value = account.client_id;
    document.getElementById('edit-acc-group').value = account.group_id || '';

    openModal('edit-account-modal');
}

async function updateAccount(e) {
    e.preventDefault();

    const id = document.getElementById('edit-acc-id').value;
    const data = {};

    const email = document.getElementById('edit-acc-email').value;
    const password = document.getElementById('edit-acc-password').value;
    const refreshToken = document.getElementById('edit-acc-refresh-token').value;
    const clientId = document.getElementById('edit-acc-client-id').value;
    const groupId = document.getElementById('edit-acc-group').value;

    if (email) data.email = email;
    if (password) data.password = password;
    if (refreshToken) data.refresh_token = refreshToken;
    if (clientId) data.client_id = clientId;
    data.group_id = groupId || null;

    try {
        const res = await fetch(`${API_BASE}/accounts/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });
        if (res.ok) {
            closeModal('edit-account-modal');
            loadAccounts();
            showToast('账号已更新', 'success');
        } else {
            const err = await res.json();
            showToast(err.detail || '更新失败', 'error');
        }
    } catch (e) {
        showToast('网络错误', 'error');
    }
}

async function deleteAccount(id) {
    if (!confirm('确定删除此账号？')) return;

    try {
        const res = await fetch(`${API_BASE}/accounts/${id}`, {
            method: 'DELETE',
            credentials: 'include'
        });
        if (res.ok) {
            loadAccounts();
            showToast('账号已删除', 'success');
        }
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

async function batchDeleteAccounts() {
    if (!confirm(`确定删除选中的 ${selectedAccountIds.size} 个账号？`)) return;

    try {
        const res = await fetch(`${API_BASE}/accounts/batch-delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ ids: Array.from(selectedAccountIds) })
        });
        if (res.ok) {
            const result = await res.json();
            selectedAccountIds.clear();
            updateBatchActions();
            document.getElementById('select-all').checked = false;
            loadAccounts();
            showToast(`已删除 ${result.deleted} 个账号`, 'success');
        }
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

async function verifyAccount(id) {
    try {
        const res = await fetch(`${API_BASE}/accounts/${id}/verify`, {
            method: 'POST',
            credentials: 'include'
        });
        if (res.ok) {
            const result = await res.json();
            loadAccounts();
            if (result.valid) {
                showToast(`${result.email} 验证成功`, 'success');
            } else {
                showToast(`${result.email} 验证失败: ${result.error}`, 'error');
            }
        }
    } catch (e) {
        showToast('验证失败', 'error');
    }
}

async function batchVerify() {
    openModal('verify-modal');
    const progressInner = document.getElementById('verify-progress-inner');
    const statusText = document.getElementById('verify-status');
    const resultsDiv = document.getElementById('verify-results');

    progressInner.style.width = '0%';
    statusText.textContent = '正在验证...';
    resultsDiv.innerHTML = '';

    try {
        const res = await fetch(`${API_BASE}/accounts/batch-verify`, {
            method: 'POST',
            credentials: 'include'
        });

        if (res.ok) {
            const results = await res.json();
            progressInner.style.width = '100%';

            const valid = results.filter(r => r.valid).length;
            const invalid = results.filter(r => !r.valid).length;

            statusText.textContent = `验证完成: ${valid} 有效, ${invalid} 失效`;

            resultsDiv.innerHTML = results.map(r => `
                <div class="verify-result-item">
                    <span>${escapeHtml(r.email)}</span>
                    <span class="status-badge ${r.valid ? 'status-active' : 'status-invalid'}">
                        ${r.valid ? '有效' : '失效'}
                    </span>
                </div>
            `).join('');

            loadAccounts();
        }
    } catch (e) {
        statusText.textContent = '验证失败';
    }
}

async function exportAccounts() {
    const groupId = document.getElementById('group-filter').value;
    const params = groupId ? `?group_id=${groupId}` : '';

    try {
        const res = await fetch(`${API_BASE}/accounts/export${params}`, { credentials: 'include' });
        if (res.ok) {
            const text = await res.text();
            const blob = new Blob([text], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'accounts.txt';
            a.click();
            URL.revokeObjectURL(url);
            showToast('导出成功', 'success');
        }
    } catch (e) {
        showToast('导出失败', 'error');
    }
}

// Mail Functions
function populateMailAccountSelect() {
    const container = document.getElementById('account-list');

    if (accounts.length === 0) {
        container.innerHTML = `
            <div class="empty-state" style="padding: 20px;">
                <p>暂无可用邮箱</p>
                <p style="font-size: 12px; margin-top: 8px;">请先添加邮箱</p>
            </div>
        `;
        return;
    }

    container.innerHTML = accounts.map(a => {
        const statusText = { active: '有效', invalid: '失效', unknown: '未验证' }[a.status] || '未知';
        const isActive = currentMailAccount === a.id;
        return `
            <div class="account-item ${isActive ? 'active' : ''}" onclick="selectMailAccount('${a.id}')">
                <div class="account-item-email">${escapeHtml(a.email)}</div>
                <div class="account-item-status">
                    <span class="status-badge status-${a.status}">${statusText}</span>
                </div>
            </div>
        `;
    }).join('');
}

function selectMailAccount(accountId) {
    currentMailAccount = accountId;
    currentFolder = 'inbox';
    currentMailPage = 0;
    populateMailAccountSelect(); // Re-render to update active state
    loadFolders();
    loadMails();
}

async function loadFolders() {
    if (!currentMailAccount) return;

    try {
        const res = await fetch(`${API_BASE}/accounts/${currentMailAccount}/folders`, { credentials: 'include' });
        if (res.ok) {
            const folders = await res.json();
            renderFolders(folders);
        }
    } catch (e) {
        console.error('Failed to load folders:', e);
    }
}

function renderFolders(folders) {
    const list = document.getElementById('folder-list');
    list.innerHTML = folders.map(f => `
        <li class="${f.id === currentFolder || f.name.toLowerCase() === currentFolder ? 'active' : ''}"
            onclick="selectFolder('${f.id}')">
            <span>${escapeHtml(f.name)}</span>
            <span class="folder-count">${f.unread_count > 0 ? f.unread_count : ''}</span>
        </li>
    `).join('');
}

function selectFolder(folderId) {
    currentFolder = folderId;
    currentMailPage = 0;
    loadFolders();
    loadMails();
}

async function loadMails() {
    if (!currentMailAccount) return;

    const search = document.getElementById('mail-search').value;
    const params = new URLSearchParams({
        folder: currentFolder,
        limit: MAIL_PAGE_SIZE,
        skip: currentMailPage * MAIL_PAGE_SIZE
    });
    if (search) params.append('search', search);

    try {
        const res = await fetch(`${API_BASE}/accounts/${currentMailAccount}/messages?${params}`, { credentials: 'include' });
        if (res.ok) {
            const data = await res.json();
            renderMails(data.items, data.total);
        }
    } catch (e) {
        console.error('Failed to load mails:', e);
        document.getElementById('mail-list').innerHTML = '<div class="empty-state"><p>加载失败</p></div>';
    }
}

function renderMails(mails, total) {
    const list = document.getElementById('mail-list');

    if (mails.length === 0) {
        list.innerHTML = '<div class="empty-state"><p>暂无邮件</p></div>';
        return;
    }

    list.innerHTML = mails.map(m => `
        <div class="mail-item ${m.is_read ? '' : 'unread'}" onclick="openMail('${m.id}')">
            <div class="mail-item-header">
                <span class="mail-item-from">${escapeHtml(m.from_name || m.from_address || '未知')}</span>
                <span class="mail-item-date">${formatDate(m.received_at)}</span>
            </div>
            <div class="mail-item-subject">${escapeHtml(m.subject || '(无主题)')}</div>
            <div class="mail-item-preview">${escapeHtml(m.body_preview || '')}</div>
        </div>
    `).join('');

    renderPagination(total);
}

function renderPagination(total) {
    const pagination = document.getElementById('mail-pagination');
    const totalPages = Math.ceil(total / MAIL_PAGE_SIZE);

    if (totalPages <= 1) {
        pagination.innerHTML = '';
        return;
    }

    let html = '';
    if (currentMailPage > 0) {
        html += `<button class="btn btn-secondary btn-small" onclick="goToPage(${currentMailPage - 1})">上一页</button>`;
    }
    html += `<span>第 ${currentMailPage + 1} / ${totalPages} 页</span>`;
    if (currentMailPage < totalPages - 1) {
        html += `<button class="btn btn-secondary btn-small" onclick="goToPage(${currentMailPage + 1})">下一页</button>`;
    }
    pagination.innerHTML = html;
}

function goToPage(page) {
    currentMailPage = page;
    loadMails();
}

let currentMailId = null;

async function openMail(messageId) {
    currentMailId = messageId;

    try {
        const res = await fetch(`${API_BASE}/accounts/${currentMailAccount}/messages/${messageId}`, { credentials: 'include' });
        if (res.ok) {
            const mail = await res.json();

            document.getElementById('mail-subject').textContent = mail.subject || '(无主题)';
            document.getElementById('mail-from').textContent = `${mail.from_name || ''} <${mail.from_address || ''}>`;
            document.getElementById('mail-to').textContent = mail.to.join(', ') || '-';
            document.getElementById('mail-cc').textContent = mail.cc.join(', ') || '-';
            document.getElementById('mail-date').textContent = formatDate(mail.received_at);

            const bodyDiv = document.getElementById('mail-body');
            if (mail.body_type === 'html') {
                // Use iframe for HTML content (security)
                // Note: srcdoc needs the raw HTML, not escaped
                const iframe = document.createElement('iframe');
                iframe.sandbox = 'allow-same-origin';
                iframe.srcdoc = mail.body_content || '';
                bodyDiv.innerHTML = '';
                bodyDiv.appendChild(iframe);
            } else {
                bodyDiv.innerHTML = `<pre>${escapeHtml(mail.body_content || '')}</pre>`;
            }

            openModal('mail-detail-modal');
        }
    } catch (e) {
        showToast('加载邮件失败', 'error');
    }
}

async function deleteCurrentMail() {
    if (!currentMailId || !confirm('确定删除此邮件？')) return;

    try {
        const res = await fetch(`${API_BASE}/accounts/${currentMailAccount}/messages/${currentMailId}`, {
            method: 'DELETE',
            credentials: 'include'
        });
        if (res.ok) {
            closeModal('mail-detail-modal');
            loadMails();
            showToast('邮件已删除', 'success');
        }
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

// Utility Functions
function openModal(id) {
    document.getElementById(id).classList.remove('hidden');
}

function closeModal(id) {
    document.getElementById(id).classList.add('hidden');
}

function showToast(message, type = '') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.classList.remove('hidden');

    setTimeout(() => {
        toast.classList.add('hidden');
    }, 3000);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    const now = new Date();

    if (date.toDateString() === now.toDateString()) {
        return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    }
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

function debounce(func, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

// Make functions available globally for onclick handlers
window.toggleSelect = toggleSelect;
window.editAccount = editAccount;
window.deleteAccount = deleteAccount;
window.verifyAccount = verifyAccount;
window.deleteGroup = deleteGroup;
window.selectFolder = selectFolder;
window.selectMailAccount = selectMailAccount;
window.openMail = openMail;
window.goToPage = goToPage;

// Import Tabs Setup
function setupImportTabs() {
    const tabs = document.querySelectorAll('.import-tab');
    const textMode = document.getElementById('import-text-mode');
    const fileMode = document.getElementById('import-file-mode');
    const fileInput = document.getElementById('import-file');
    const uploadArea = document.getElementById('file-upload-area');
    const clearFileBtn = document.getElementById('clear-file');

    if (!tabs.length) return;

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            importMode = tab.dataset.mode;

            if (importMode === 'text') {
                textMode.classList.remove('hidden');
                fileMode.classList.add('hidden');
            } else {
                textMode.classList.add('hidden');
                fileMode.classList.remove('hidden');
            }
        });
    });

    uploadArea.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) handleFileSelect(file);
    });

    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file && file.name.endsWith('.txt')) {
            handleFileSelect(file);
        } else {
            showToast('请选择 .txt 文件', 'error');
        }
    });

    clearFileBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        clearImportFile();
    });
}

function handleFileSelect(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        importFileContent = e.target.result;
        document.getElementById('file-name').textContent = file.name;
        document.querySelector('.file-upload-content').classList.add('hidden');
        document.getElementById('file-selected').classList.remove('hidden');
    };
    reader.readAsText(file);
}

function clearImportFile() {
    importFileContent = '';
    document.getElementById('import-file').value = '';
    document.querySelector('.file-upload-content').classList.remove('hidden');
    document.getElementById('file-selected').classList.add('hidden');
}

