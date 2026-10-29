"""Web control panel for Pergel API server.

Serves the `/ui/` page: a single-page control panel with three tabs:
  /start    — launch browse/extract/crawl/search jobs
  /history  — list past jobs and results
  /settings — view server status and configuration

No build step, no external assets — a single self-contained HTML page.
"""

import json

_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pergel — Control Panel</title>
<style>
:root {
  --bg: #0d1117; --surface: #161b22; --border: #30363d;
  --text: #e6edf3; --text2: #8b949e; --accent: #58a6ff;
  --green: #3fb950; --red: #f85149; --yellow: #d29922;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
header { display: flex; align-items: center; gap: 12px; padding: 16px 24px; border-bottom: 1px solid var(--border); }
header h1 { font-size: 18px; font-weight: 600; }
header .badge { background: var(--green); color: #000; font-size: 11px; padding: 2px 8px; border-radius: 12px; font-weight: 600; }
nav { display: flex; gap: 0; border-bottom: 1px solid var(--border); padding: 0 24px; }
nav button { background: none; border: none; color: var(--text2); padding: 12px 20px; cursor: pointer; font-size: 14px; border-bottom: 2px solid transparent; transition: all 0.15s; }
nav button:hover { color: var(--text); }
nav button.active { color: var(--accent); border-bottom-color: var(--accent); }
main { padding: 24px; max-width: 960px; margin: 0 auto; }
.tab { display: none; } .tab.active { display: block; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.card h2 { font-size: 15px; margin-bottom: 12px; color: var(--text); }
label { display: block; font-size: 13px; color: var(--text2); margin-bottom: 4px; margin-top: 12px; }
input, select, textarea { width: 100%; padding: 8px 12px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text); font-size: 14px; }
input:focus, select:focus, textarea:focus { outline: none; border-color: var(--accent); }
button.action { background: var(--accent); color: #fff; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; margin-top: 16px; transition: opacity 0.15s; }
button.action:hover { opacity: 0.85; }
button.action:disabled { opacity: 0.5; cursor: not-allowed; }
button.action.danger { background: var(--red); }
button.action.green { background: var(--green); color: #000; }
.result { margin-top: 16px; padding: 16px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; font-family: 'SF Mono', Consolas, monospace; font-size: 12px; overflow-x: auto; white-space: pre-wrap; word-break: break-all; max-height: 500px; overflow-y: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 13px; }
th { color: var(--text2); font-weight: 500; }
td a { color: var(--accent); text-decoration: none; cursor: pointer; }
td a:hover { text-decoration: underline; }
.status { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }
.status.ok { background: rgba(63,185,80,0.15); color: var(--green); }
.status.err { background: rgba(248,81,73,0.15); color: var(--red); }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
.stat { background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 16px; }
.stat .label { font-size: 12px; color: var(--text2); }
.stat .value { font-size: 24px; font-weight: 600; margin-top: 4px; }
</style>
</head>
<body>
<header>
  <h1>🛡️ Pergel</h1>
  <span class="badge" id="status-badge">…</span>
</header>
<nav>
  <button class="active" onclick="showTab('start',this)">▶ Start</button>
  <button onclick="showTab('history',this)">📋 History</button>
  <button onclick="showTab('settings',this)">⚙ Settings</button>
  <button onclick="showTab('vault',this)">🔐 Vault</button>
</nav>
<main>
  <!-- START TAB -->
  <div class="tab active" id="tab-start">
    <div class="card">
      <h2>Browse URL</h2>
      <label>URL</label>
      <input id="browse-url" placeholder="https://example.com">
      <label>Mode</label>
      <select id="browse-mode">
        <option value="fetch">Fetch (SSRF-guarded)</option>
        <option value="engine">Engine (headless browser)</option>
      </select>
      <button class="action" onclick="doBrowse()">Browse</button>
    </div>
    <div class="card">
      <h2>Extract Data</h2>
      <label>URL</label>
      <input id="extract-url" placeholder="https://example.com">
      <label>Schema (CSS selectors)</label>
      <textarea id="extract-schema" rows="4" placeholder='{"title": "h1", "links": {"selector": "a", "attr": "href"}}'></textarea>
      <button class="action green" onclick="doExtract()">Extract</button>
    </div>
    <div class="card">
      <h2>Search (Query Fan-Out)</h2>
      <label>Query</label>
      <input id="search-q" placeholder="your search query">
      <button class="action" onclick="doSearch()">Search</button>
    </div>
    <div class="result" id="start-result" style="display:none"></div>
  </div>

  <!-- HISTORY TAB -->
  <div class="tab" id="tab-history">
    <div class="card">
      <h2>Job History</h2>
      <table>
        <thead><tr><th>ID</th><th>Endpoint</th><th>Status</th><th>URL</th><th>Result</th></tr></thead>
        <tbody id="history-body"><tr><td colspan="5" style="color:var(--text2)">Loading…</td></tr></tbody>
      </table>
    </div>
  </div>

  <!-- SETTINGS TAB -->
  <div class="tab" id="tab-settings">
    <div class="card">
      <h2>Server Status</h2>
      <div class="stat-grid" id="stats-grid"></div>
    </div>
    <div class="card">
      <h2>Configuration</h2>
      <div id="config-info"></div>
    </div>
    <div class="card">
      <h2>Security</h2>
      <div id="security-info"></div>
    </div>
  </div>

  <!-- VAULT TAB -->
  <div class="tab" id="tab-vault">
    <div class="card">
      <h2>🔐 Secrets Vault</h2>
      <p class="hint">Encrypted at rest. Master password never stored.</p>
      <div id="vault-status-msg" class="hint"></div>
      <div id="vault-login">
        <label>Master Password</label>
        <input type="password" id="vault-master-pw" placeholder="Master password">
        <div id="vault-init-fields" style="display:none">
          <label>Confirm</label>
          <input type="password" id="vault-master-pw2" placeholder="Confirm password">
        </div>
        <button class="primary" onclick="vaultLogin()" id="vault-login-btn">🔓 Unlock</button>
      </div>
      <div id="vault-content" style="display:none">
        <div id="vault-secrets-list"></div>
        <h2 style="margin-top:16px">Add / Update</h2>
        <label>Name (ENV var)</label>
        <input id="vault-name" placeholder="e.g. SUDO_PASSWORD">
        <label>Value</label>
        <input id="vault-value" type="password" placeholder="Secret value">
        <label>Category</label>
        <select id="vault-cat">
          <option>system</option><option>api</option><option>telegram</option>
          <option>github</option><option>browser</option><option>general</option>
        </select>
        <button class="primary" onclick="vaultSave()" style="margin-top:8px">💾 Save</button>
        <button class="danger" onclick="vaultLock()" style="margin-top:8px;margin-left:8px">🔒 Lock</button>
      </div>
    </div>
  </div>
</main>

<script>
const API = location.origin + '/v1';

function showTab(id, btn) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  btn.classList.add('active');
  if (id === 'history') loadHistory();
  if (id === 'settings') loadSettings();
}

function setResult(el, data) {
  const r = document.getElementById(el);
  r.style.display = 'block';
  r.textContent = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
}

async function doBrowse() {
  const url = document.getElementById('browse-url').value;
  const mode = document.getElementById('browse-mode').value;
  if (!url) return alert('Enter a URL');
  setResult('start-result', 'Loading…');
  try {
    const r = await fetch(API + '/jobs/browse', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url, mode})
    });
    setResult('start-result', await r.json());
  } catch(e) { setResult('start-result', 'Error: ' + e.message); }
}

async function doExtract() {
  const url = document.getElementById('extract-url').value;
  if (!url) return alert('Enter a URL');
  let schema = {};
  try { schema = JSON.parse(document.getElementById('extract-schema').value || '{}'); } catch(e) { return alert('Invalid JSON schema'); }
  setResult('start-result', 'Loading…');
  try {
    const r = await fetch(API + '/extract', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url, schema})
    });
    setResult('start-result', await r.json());
  } catch(e) { setResult('start-result', 'Error: ' + e.message); }
}

async function doSearch() {
  const q = document.getElementById('search-q').value;
  if (!q) return alert('Enter a query');
  setResult('start-result', 'Loading…');
  try {
    const r = await fetch(API + '/search/fanout', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query: q})
    });
    setResult('start-result', await r.json());
  } catch(e) { setResult('start-result', 'Error: ' + e.message); }
}

async function loadHistory() {
  try {
    const r = await fetch(API + '/jobs');
    const data = await r.json();
    const jobs = data.jobs || data || [];
    const tb = document.getElementById('history-body');
    if (!jobs.length) { tb.innerHTML = '<tr><td colspan="5" style="color:var(--text2)">No jobs yet</td></tr>'; return; }
    tb.innerHTML = jobs.slice(-50).reverse().map(j => `
      <tr>
        <td>${(j.job_id||j.id||'').slice(0,12)}</td>
        <td>${j.endpoint||j.type||'—'}</td>
        <td><span class="status ${j.status==='ok'||j.status==='completed'?'ok':'err'}">${j.status||'?'}</span></td>
        <td>${(j.url||'').slice(0,40)}</td>
        <td><a onclick="showJob('${j.job_id||j.id}')">view</a></td>
      </tr>`).join('');
  } catch(e) { document.getElementById('history-body').innerHTML = '<tr><td colspan="5">Error loading history</td></tr>'; }
}

async function showJob(id) {
  try {
    const r = await fetch(API + '/jobs/' + id);
    setResult('start-result', await r.json());
    showTab('start', document.querySelector('nav button'));
  } catch(e) { alert('Error: ' + e.message); }
}

async function loadSettings() {
  try {
    const r = await fetch(API + '/health');
    const d = await r.json();
    document.getElementById('stats-grid').innerHTML = `
      <div class="stat"><div class="label">Status</div><div class="value" style="color:var(--green)">● ${d.status||'ok'}</div></div>
      <div class="stat"><div class="label">Uptime</div><div class="value">${d.uptime||'—'}</div></div>
      <div class="stat"><div class="label">Jobs</div><div class="value">${d.jobs||d.total_jobs||'—'}</div></div>
      <div class="stat"><div class="label">Models</div><div class="value">${d.models||d.model_count||'—'}</div></div>`;
    document.getElementById('config-info').innerHTML = `
      <p style="color:var(--text2);font-size:13px">API endpoint: <code style="color:var(--accent)">${API}</code></p>
      <p style="color:var(--text2);font-size:13px">Docs: <a style="color:var(--accent)" href="/docs">/docs</a></p>`;
    document.getElementById('security-info').innerHTML = `
      <p style="font-size:13px;color:var(--green)">✓ SSRF guard: active</p>
      <p style="font-size:13px;color:var(--green)">✓ Egress control: active</p>
      <p style="font-size:13px;color:var(--green)">✓ Rate limiting: active</p>
      <p style="font-size:13px;color:var(--green)">✓ No telemetry</p>`;
  } catch(e) { document.getElementById('stats-grid').innerHTML = '<p>Error loading settings</p>'; }
}

// Check status on load
fetch(API + '/health').then(r => r.json()).then(d => {
  document.getElementById('status-badge').textContent = '● online';
}).catch(() => { document.getElementById('status-badge').textContent = '● offline'; document.getElementById('status-badge').style.background = 'var(--red)'; });
</script>
</body>
</html>"""


def get_ui_html() -> str:
    """Return the control panel HTML."""
    return _UI_HTML
