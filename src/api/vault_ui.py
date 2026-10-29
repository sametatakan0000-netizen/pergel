"""Vault Web UI — responsive, dark-themed, mobile-friendly secrets manager."""

def get_vault_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pergel Vault</title>
<style>
:root {
    --bg: #0d1117; --surface: #161b22; --surface2: #1c2333;
    --border: #30363d; --text: #e6edf3; --text2: #8b949e;
    --accent: #58a6ff; --green: #3fb950; --red: #f85149;
    --yellow: #d29922; --radius: 12px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; min-height: 100vh; }
.container { max-width: 600px; margin: 0 auto; padding: 16px; }

/* Header */
.header { display: flex; justify-content: space-between; align-items: center; padding: 16px 0; }
.header h1 { font-size: 1.3rem; }
.header .lock-btn { background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 8px 16px; border-radius: var(--radius); cursor: pointer; font-size: 0.85rem; }

/* Tabs */
.tabs { display: flex; gap: 8px; margin-bottom: 16px; overflow-x: auto; }
.tabs button {
    padding: 10px 18px; border: 1px solid var(--border); background: var(--surface);
    color: var(--text2); border-radius: var(--radius); cursor: pointer; white-space: nowrap;
    font-size: 0.9rem; transition: all 0.2s;
}
.tabs button.active { background: var(--accent); color: #fff; border-color: var(--accent); }

/* Cards */
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; margin-bottom: 12px; }
.card h3 { font-size: 1rem; margin-bottom: 12px; color: var(--accent); }

/* Forms */
.form-group { margin-bottom: 12px; }
.form-group label { display: block; font-size: 0.85rem; color: var(--text2); margin-bottom: 4px; }
.form-group input, .form-group select, .form-group textarea {
    width: 100%; padding: 10px 12px; background: var(--surface2); border: 1px solid var(--border);
    border-radius: 8px; color: var(--text); font-size: 0.95rem;
}
.form-group textarea { min-height: 60px; resize: vertical; }
.btn {
    padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer;
    font-size: 0.95rem; font-weight: 500; transition: all 0.2s;
}
.btn-primary { background: var(--accent); color: #fff; }
.btn-danger { background: var(--red); color: #fff; }
.btn-success { background: var(--green); color: #fff; }
.btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text); }
.btn:hover { opacity: 0.9; transform: translateY(-1px); }
.btn:active { transform: translateY(0); }

/* Secret list */
.secret-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px; border-bottom: 1px solid var(--border);
}
.secret-item:last-child { border-bottom: none; }
.secret-info { flex: 1; }
.secret-name { font-weight: 600; font-size: 0.95rem; }
.secret-meta { font-size: 0.8rem; color: var(--text2); }
.secret-actions { display: flex; gap: 6px; }
.secret-actions button {
    padding: 6px 10px; border: 1px solid var(--border); background: var(--surface2);
    color: var(--text); border-radius: 6px; cursor: pointer; font-size: 0.8rem;
}

/* Status */
.status { padding: 12px 16px; border-radius: var(--radius); margin-bottom: 12px; font-size: 0.9rem; }
.status.success { background: #1a3a2a; border: 1px solid var(--green); color: var(--green); }
.status.error { background: #3a1a1a; border: 1px solid var(--red); color: var(--red); }
.status.warning { background: #3a2a1a; border: 1px solid var(--yellow); color: var(--yellow); }
.status:empty { display: none; }

/* Modal */
.modal-overlay {
    display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7);
    z-index: 100; align-items: center; justify-content: center; padding: 16px;
}
.modal-overlay.show { display: flex; }
.modal { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 24px; width: 100%; max-width: 500px; }
.modal h2 { margin-bottom: 16px; font-size: 1.1rem; }

/* Password toggle */
.pw-wrapper { position: relative; }
.pw-wrapper input { padding-right: 44px; }
.pw-toggle {
    position: absolute; right: 10px; top: 50%; transform: translateY(-50%);
    background: none; border: none; color: var(--text2); cursor: pointer; font-size: 1.1rem;
}

/* Responsive */
@media (max-width: 480px) {
    .container { padding: 12px; }
    .tabs button { padding: 8px 12px; font-size: 0.82rem; }
    .secret-item { flex-direction: column; align-items: flex-start; gap: 8px; }
    .secret-actions { width: 100%; }
    .secret-actions button { flex: 1; text-align: center; }
}

/* Audit log */
.audit-item { padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 0.85rem; }
.audit-item:last-child { border-bottom: none; }
.audit-time { color: var(--text2); font-size: 0.75rem; }

/* Login */
.login-container { max-width: 400px; margin: 10vh auto; padding: 16px; }
.login-container .card { padding: 32px 24px; }
.login-container h1 { text-align: center; margin-bottom: 24px; }
.login-container .btn { width: 100%; padding: 12px; font-size: 1rem; }
</style>
</head>
<body>
<div id="loginView" class="login-container">
    <div class="card">
        <h1>🔐 Pergel Vault</h1>
        <div id="loginStatus" class="status"></div>
        <div id="initForm" style="display:none">
            <p style="color:var(--text2);margin-bottom:16px;font-size:0.9rem">First time? Set a master password. This password is never stored — if you lose it, your secrets are gone.</p>
            <div class="form-group">
                <label>Master Password</label>
                <div class="pw-wrapper">
                    <input type="password" id="initPassword" placeholder="Min 8 characters" autocomplete="new-password">
                    <button class="pw-toggle" onclick="togglePw('initPassword', this)">👁</button>
                </div>
            </div>
            <div class="form-group">
                <label>Confirm Password</label>
                <input type="password" id="initPassword2" placeholder="Repeat" autocomplete="new-password">
            </div>
            <button class="btn btn-primary" onclick="initVault()">Initialize Vault</button>
        </div>
        <div id="unlockForm" style="display:none">
            <div class="form-group">
                <label>Master Password</label>
                <div class="pw-wrapper">
                    <input type="password" id="unlockPassword" placeholder="Enter master password" autocomplete="current-password">
                    <button class="pw-toggle" onclick="togglePw('unlockPassword', this)">👁</button>
                </div>
            </div>
            <button class="btn btn-primary" onclick="unlockVault()">Unlock</button>
        </div>
    </div>
</div>

<div id="mainView" class="container" style="display:none">
    <div class="header">
        <h1>🔐 Vault</h1>
        <button class="lock-btn" onclick="lockVault()">🔒 Lock</button>
    </div>

    <div id="status" class="status"></div>

    <div class="tabs">
        <button class="active" onclick="switchTab('secrets', this)">🔑 Secrets</button>
        <button onclick="switchTab('add', this)">➕ Add</button>
        <button onclick="switchTab('audit', this)">📋 Audit</button>
        <button onclick="switchTab('export', this)">📤 Export</button>
    </div>

    <div id="secretsTab">
        <div class="card">
            <h3>Stored Secrets</h3>
            <div id="secretList"><p style="color:var(--text2)">Loading...</p></div>
        </div>
    </div>

    <div id="addTab" style="display:none">
        <div class="card">
            <h3>Add / Update Secret</h3>
            <div class="form-group">
                <label>Name (ENV variable name)</label>
                <input type="text" id="secretName" placeholder="e.g. SUDO_PASSWORD, API_KEY">
            </div>
            <div class="form-group">
                <label>Value</label>
                <div class="pw-wrapper">
                    <input type="password" id="secretValue" placeholder="Secret value">
                    <button class="pw-toggle" onclick="togglePw('secretValue', this)">👁</button>
                </div>
            </div>
            <div class="form-group">
                <label>Category</label>
                <select id="secretCategory">
                    <option value="system">System</option>
                    <option value="api">API Keys</option>
                    <option value="telegram">Telegram</option>
                    <option value="github">GitHub</option>
                    <option value="browser">Browser</option>
                    <option value="general" selected>General</option>
                </select>
            </div>
            <div class="form-group">
                <label>Description (optional)</label>
                <input type="text" id="secretDesc" placeholder="What is this for?">
            </div>
            <button class="btn btn-primary" onclick="saveSecret()">💾 Save</button>
        </div>
    </div>

    <div id="auditTab" style="display:none">
        <div class="card">
            <h3>Audit Log</h3>
            <div id="auditList"><p style="color:var(--text2)">Loading...</p></div>
        </div>
    </div>

    <div id="exportTab" style="display:none">
        <div class="card">
            <h3>Export / Import</h3>
            <p style="color:var(--text2);margin-bottom:12px;font-size:0.85rem">Export all secrets as .env format. Use for backup or migration.</p>
            <button class="btn btn-ghost" onclick="exportEnv()">📋 Copy .env to Clipboard</button>
            <pre id="exportOutput" style="margin-top:12px;background:var(--surface2);padding:12px;border-radius:8px;font-size:0.8rem;overflow-x:auto;display:none"></pre>
        </div>
    </div>
</div>

<!-- Edit Modal -->
<div id="editModal" class="modal-overlay">
    <div class="modal">
        <h2>✏️ Edit Secret</h2>
        <div class="form-group">
            <label>Name</label>
            <input type="text" id="editName" readonly>
        </div>
        <div class="form-group">
            <label>New Value (leave empty to keep current)</label>
            <div class="pw-wrapper">
                <input type="password" id="editValue" placeholder="New value">
                <button class="pw-toggle" onclick="togglePw('editValue', this)">👁</button>
            </div>
        </div>
        <div class="form-group">
            <label>Category</label>
            <select id="editCategory">
                <option value="system">System</option>
                <option value="api">API Keys</option>
                <option value="telegram">Telegram</option>
                <option value="github">GitHub</option>
                <option value="browser">Browser</option>
                <option value="general">General</option>
            </select>
        </div>
        <div style="display:flex;gap:8px">
            <button class="btn btn-primary" onclick="updateSecret()" style="flex:1">💾 Save</button>
            <button class="btn btn-ghost" onclick="closeModal()" style="flex:1">Cancel</button>
        </div>
    </div>
</div>

<script>
const API = '/v1/vault';
let sessionToken = localStorage.getItem('vault_token') || '';

function $(id) { return document.getElementById(id); }

function showStatus(msg, type='success') {
    const el = $('status');
    el.textContent = msg;
    el.className = 'status ' + type;
    setTimeout(() => { el.textContent = ''; el.className = 'status'; }, 4000);
}

function showLoginStatus(msg, type='error') {
    const el = $('loginStatus');
    el.textContent = msg;
    el.className = 'status ' + type;
}

function togglePw(id, btn) {
    const input = $(id);
    input.type = input.type === 'password' ? 'text' : 'password';
    btn.textContent = input.type === 'password' ? '👁' : '🙈';
}

async function apiCall(method, path, body=null) {
    const headers = {'Content-Type': 'application/json'};
    if (sessionToken) headers['X-Vault-Token'] = sessionToken;
    const opts = {method, headers};
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(API + path, opts);
    return r.json();
}

async function checkVault() {
    const r = await apiCall('GET', '/status');
    if (r.initialized) {
        $('initForm').style.display = 'none';
        $('unlockForm').style.display = 'block';
    } else {
        $('initForm').style.display = 'block';
        $('unlockForm').style.display = 'none';
    }
    // Check if we have a valid session
    if (sessionToken) {
        const check = await apiCall('GET', '/check');
        if (check.valid) {
            $('loginView').style.display = 'none';
            $('mainView').style.display = 'block';
            loadSecrets();
            return;
        }
        sessionToken = '';
        localStorage.removeItem('vault_token');
    }
}

async function initVault() {
    const pw = $('initPassword').value;
    const pw2 = $('initPassword2').value;
    if (pw.length < 8) return showLoginStatus('Password must be at least 8 characters');
    if (pw !== pw2) return showLoginStatus('Passwords do not match');
    const r = await apiCall('POST', '/init', {password: pw});
    if (r.error) return showLoginStatus(r.error);
    sessionToken = r.token;
    localStorage.setItem('vault_token', sessionToken);
    $('loginView').style.display = 'none';
    $('mainView').style.display = 'block';
    loadSecrets();
}

async function unlockVault() {
    const pw = $('unlockPassword').value;
    if (!pw) return showLoginStatus('Enter password');
    const r = await apiCall('POST', '/unlock', {password: pw});
    if (r.error) return showLoginStatus(r.error);
    sessionToken = r.token;
    localStorage.setItem('vault_token', sessionToken);
    $('loginView').style.display = 'none';
    $('mainView').style.display = 'block';
    loadSecrets();
}

async function lockVault() {
    await apiCall('POST', '/lock');
    sessionToken = '';
    localStorage.removeItem('vault_token');
    $('mainView').style.display = 'none';
    $('loginView').style.display = 'block';
    checkVault();
}

function switchTab(tab, btn) {
    ['secrets', 'add', 'audit', 'export'].forEach(t => $(t + 'Tab').style.display = 'none');
    $(tab + 'Tab').style.display = 'block';
    document.querySelectorAll('.tabs button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    if (tab === 'secrets') loadSecrets();
    if (tab === 'audit') loadAudit();
}

async function loadSecrets() {
    const r = await apiCall('GET', '/secrets');
    if (r.error) return showStatus(r.error, 'error');
    const list = $('secretList');
    if (!r.secrets || r.secrets.length === 0) {
        list.innerHTML = '<p style="color:var(--text2)">No secrets yet. Add one!</p>';
        return;
    }
    list.innerHTML = r.secrets.map(s => `
        <div class="secret-item">
            <div class="secret-info">
                <div class="secret-name">${esc(s.name)}</div>
                <div class="secret-meta">${esc(s.category)} · Updated ${new Date(s.updated_at * 1000).toLocaleDateString()}</div>
            </div>
            <div class="secret-actions">
                <button onclick="viewSecret('${esc(s.name)}')">👁 View</button>
                <button onclick="editSecret('${esc(s.name)}', '${esc(s.category)}')">✏️ Edit</button>
                <button onclick="deleteSecret('${esc(s.name)}')">🗑</button>
            </div>
        </div>
    `).join('');
}

function esc(s) { return String(s).replace(/</g, '&lt;').replace(/'/g, "\'"); }

async function viewSecret(name) {
    const r = await apiCall('GET', '/secret/' + encodeURIComponent(name));
    if (r.error) return showStatus(r.error, 'error');
    const val = r.value;
    const masked = val.length > 8 ? val.slice(0, 4) + '••••' + val.slice(-4) : '••••••';
    const show = confirm(name + ':\n\n' + masked + '\n\nShow full value?');
    if (show) alert(name + ':\n\n' + val);
}

function editSecret(name, category) {
    $('editName').value = name;
    $('editCategory').value = category;
    $('editValue').value = '';
    $('editModal').classList.add('show');
}

function closeModal() { $('editModal').classList.remove('show'); }

async function updateSecret() {
    const name = $('editName').value;
    const value = $('editValue').value;
    const category = $('editCategory').value;
    const body = {name, category};
    if (value) body.value = value;
    const r = await apiCall('POST', '/secret', body);
    if (r.error) return showStatus(r.error, 'error');
    closeModal();
    showStatus('Updated: ' + name);
    loadSecrets();
}

async function saveSecret() {
    const name = $('secretName').value.trim();
    const value = $('secretValue').value;
    const category = $('secretCategory').value;
    const description = $('secretDesc').value;
    if (!name || !value) return showStatus('Name and value required', 'error');
    const r = await apiCall('POST', '/secret', {name, value, category, description});
    if (r.error) return showStatus(r.error, 'error');
    showStatus('Saved: ' + name);
    $('secretName').value = '';
    $('secretValue').value = '';
    $('secretDesc').value = '';
}

async function deleteSecret(name) {
    if (!confirm('Delete "' + name + '"? This cannot be undone.')) return;
    const r = await apiCall('DELETE', '/secret/' + encodeURIComponent(name));
    if (r.error) return showStatus(r.error, 'error');
    showStatus('Deleted: ' + name);
    loadSecrets();
}

async function loadAudit() {
    const r = await apiCall('GET', '/audit');
    if (r.error) return showStatus(r.error, 'error');
    const list = $('auditList');
    if (!r.log || r.log.length === 0) {
        list.innerHTML = '<p style="color:var(--text2)">No audit entries</p>';
        return;
    }
    list.innerHTML = r.log.map(e => `
        <div class="audit-item">
            <div class="audit-time">${new Date(e.timestamp * 1000).toLocaleString()}</div>
            <div>${e.action} ${e.secret_name ? '· ' + e.secret_name : ''} ${e.detail ? '· ' + e.detail : ''}</div>
        </div>
    `).join('');
}

async function exportEnv() {
    const r = await apiCall('GET', '/export');
    if (r.error) return showStatus(r.error, 'error');
    const pre = $('exportOutput');
    pre.style.display = 'block';
    pre.textContent = r.env;
    navigator.clipboard.writeText(r.env).then(() => showStatus('Copied to clipboard'));
}

checkVault();
</script>
</body>
</html>"""
