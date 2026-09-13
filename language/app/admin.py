"""The operator's review page, served at /admin. One person, a laptop, and a plaza.

Same construction as `demo.py` — one self-contained HTML string, server-rendered, vanilla JS,
no build step — because the thing that gets used on the night is the thing that cannot break
separately from the API it drives. It is built for the twenty minutes before dusk rather than
for completeness: what is waiting, enough of each reading to judge it, two buttons, and the
three switches. Everything else is `/demo`'s job.

Outdoors on a laptop, so: big type, one column, high contrast, no hover-only affordances, and
keys as well as buttons (`j`/`k` to move, `a` approve, `r` refuse) because a trackpad in the
dark is slower than a keyboard. Refreshes itself every 15 s and never while a decision is in
flight, so the row under the cursor cannot move out from under it.

The page holds no data. Every read and every write carries `X-Admin-Token`, which the operator
types once (or puts in the URL as `?key=` to bookmark it) and which lives in `sessionStorage`
for that tab only; a 401 anywhere puts the prompt back. So "behind the admin token" means the
same thing here as it does for the endpoints: there is nothing to see without it.
"""

from __future__ import annotations

ADMIN_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GreenDream &middot; review</title>
<style>
  :root {
    --bg: #06080e; --panel: #0e1420; --line: #23304a; --ink: #eaf0fb; --dim: #93a2bd;
    --ok: #5cffa6; --warn: #ffd166; --bad: #ff6b81;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink);
         font: 17px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
  a { color: var(--ok); }
  .wrap { max-width: 860px; margin: 0 auto; padding: 16px 16px 120px; }
  header { position: sticky; top: 0; z-index: 5; background: var(--bg);
           border-bottom: 1px solid var(--line); padding: 12px 0 10px; margin-bottom: 16px; }
  .bar { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
  h1 { font-size: 19px; margin: 0; font-weight: 650; letter-spacing: .2px; }
  .dot { width: 11px; height: 11px; border-radius: 50%; background: var(--dim); display: inline-block; }
  .dot.open { background: var(--ok); box-shadow: 0 0 9px var(--ok); }
  .dot.shut { background: var(--bad); box-shadow: 0 0 9px var(--bad); }
  /* Read at arm's length, outdoors, by somebody who is also watching a building: the whole
     page is a step up in size from the bench, and nothing here goes below 15px. */
  .meta { color: var(--dim); font-size: 15px; }
  .tabs { display: flex; gap: 8px; margin-top: 10px; }
  .tabs button { flex: 0 0 auto; }
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
           padding: 14px 16px; margin-bottom: 14px; }
  button { background: #1b2436; color: var(--ink); border: 1px solid var(--line);
           border-radius: 9px; padding: 11px 16px; font: inherit; font-weight: 600; cursor: pointer;
           min-height: 44px; }
  button:hover { border-color: #3f6ea8; }
  button.go { background: var(--ok); color: #04150c; border-color: transparent; }
  button.no { background: var(--bad); color: #240309; border-color: transparent; }
  button.on { border-color: var(--ok); color: var(--ok); }
  button.small { min-height: 36px; padding: 6px 12px; font-size: 15px; font-weight: 500; }
  button:disabled { opacity: .4; cursor: not-allowed; }
  input[type=text], input[type=password], select {
    background: #080d16; color: var(--ink); border: 1px solid var(--line);
    border-radius: 9px; padding: 11px 13px; font: inherit; min-height: 44px; width: 100%; }
  .card { background: var(--panel); border: 1px solid var(--line); border-left: 4px solid var(--line);
          border-radius: 12px; padding: 14px 16px; margin-bottom: 12px; }
  .card.sel { border-color: #3f6ea8; border-left-color: var(--ok); background: #101a2a; }
  .card.shrug { border-left-color: var(--warn); }
  .q { font-size: 24px; font-weight: 650; letter-spacing: .2px; margin: 0 0 4px;
       word-break: break-word; }
  .becomes { font-size: 18px; margin: 0 0 8px; }
  .becomes b { color: var(--ok); font-weight: 620; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; margin: 6px 0; align-items: center; }
  .chip { background: #0a1120; border: 1px solid var(--line); border-radius: 7px;
          padding: 3px 10px; font-size: 15px; color: var(--dim); }
  .chip.warn { color: var(--warn); border-color: #4a3c17; }
  .chip.bad { color: var(--bad); border-color: #4a1e28; }
  .chip.good { color: var(--ok); border-color: #1e4a35; }
  .sw { width: 26px; height: 26px; border-radius: 6px; border: 1px solid rgba(255,255,255,.22);
        display: inline-block; vertical-align: -7px; }
  .acts { display: flex; gap: 10px; margin-top: 12px; flex-wrap: wrap; }
  .acts button { flex: 1 1 140px; }
  .row { display: flex; gap: 12px; align-items: center; justify-content: space-between;
         padding: 9px 0; border-bottom: 1px solid #16202f; flex-wrap: wrap; }
  .row:last-child { border-bottom: 0; }
  .row .txt { flex: 1 1 220px; min-width: 0; }
  .ops { display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; }
  .ops > div { flex: 1 1 150px; }
  label.small { display: block; color: var(--dim); font-size: 15px; text-transform: uppercase;
                letter-spacing: .07em; margin: 0 0 6px; }
  .err { color: var(--bad); }
  .hide { display: none; }
  #gatecover { position: fixed; inset: 0; background: var(--bg); z-index: 20;
               display: grid; place-items: center; padding: 20px; }
  /* An id beats a class, so `.hide` alone would never dismiss this and the page would be
     unusable with the right token in it. */
  #gatecover.hide { display: none; }
  #gatecover .box { max-width: 420px; width: 100%; }
  kbd { background: #0a1120; border: 1px solid var(--line); border-bottom-width: 2px;
        border-radius: 5px; padding: 0 6px; font: inherit; font-size: 15px; color: var(--dim); }
</style>
</head>
<body>

<div id="gatecover">
  <div class="panel box">
    <h1 style="margin-bottom:6px">Review &mdash; operator only</h1>
    <p class="meta" style="margin-top:0">Nothing on this page loads without the admin token
       (<code>GD_ADMIN_TOKEN</code>). It is kept for this tab only.</p>
    <label class="small" for="tok">admin token</label>
    <input type="password" id="tok" placeholder="X-Admin-Token" autocomplete="off">
    <p class="err" id="gateerr" style="min-height:22px;margin:8px 0 10px"></p>
    <button class="go" id="gatego" style="width:100%">Unlock</button>
  </div>
</div>

<div class="wrap hide" id="main">
  <header>
    <div class="bar">
      <h1>Review</h1>
      <span><span class="dot" id="dot"></span> <b id="gatemsg">&hellip;</b></span>
      <span class="meta" id="statemeta"></span>
      <a id="live" target="_blank" rel="noreferrer" class="hide">watch the building</a>
    </div>
    <div class="tabs">
      <button id="tab-pending" class="on">Waiting <span id="n-pending"></span></button>
      <button id="tab-decided">Decided <span id="n-decided"></span></button>
      <button class="small" id="refresh" title="r&eacute;fresh">&#8635;</button>
      <span class="meta" id="tip" style="align-self:center">
        <kbd>j</kbd><kbd>k</kbd> move &middot; <kbd>a</kbd> approve &middot; <kbd>r</kbd> refuse</span>
    </div>
  </header>

  <p class="err" id="oops" style="min-height:22px;margin:0 0 8px"></p>
  <div id="list"></div>

  <div class="panel">
    <label class="small">switches &mdash; these take effect at once, no restart</label>
    <div class="ops">
      <div>
        <label class="small">intake gate</label>
        <select id="gate">
          <option value="">(leave)</option>
          <option value="auto">auto &mdash; closes at sunset</option>
          <option value="open">open</option>
          <option value="closed">closed &mdash; stop taking prompts</option>
        </select>
      </div>
      <div>
        <label class="small">model tier</label>
        <select id="llm">
          <option value="">(leave)</option>
          <option value="on">on</option>
          <option value="off">off &mdash; local library only</option>
        </select>
      </div>
      <div style="flex:0 0 auto"><button id="flip">Apply</button></div>
    </div>
    <p class="meta" id="opsmsg" style="margin:10px 0 0"></p>
    <p class="meta" style="margin:10px 0 0">The gate stops words coming <i>in</i>. To stop the
       building showing anything, freeze the runner: <code>touch FREEZE</code> beside it, or its
       control panel.</p>
  </div>
</div>

<script>
// Everything below is either somebody's query or something a model wrote, and it all reaches
// innerHTML. So it all goes through here first.
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

const $ = id => document.getElementById(id);
const KEYQ = new URLSearchParams(location.search).get('key') || '';
let TOKEN = KEYQ || sessionStorage.getItem('gd_admin') || '';
let VIEW = 'pending';      // pending | decided
let ROWS = [];
let SEL = 0;
let BUSY = false;          // a decision is in flight: do not move the ground under the cursor

async function api(path, opts) {
  const o = Object.assign({ headers: {} }, opts || {});
  o.headers = Object.assign({ 'x-admin-token': TOKEN }, o.headers || {});
  const res = await fetch(path, o);
  if (res.status === 401 || res.status === 403) { lock('that token was refused'); throw new Error('401'); }
  return res;
}

function lock(why) {
  TOKEN = '';
  sessionStorage.removeItem('gd_admin');
  $('main').className = 'wrap hide';
  $('gatecover').className = '';
  $('gateerr').textContent = why || '';
}

function unlock() {
  $('gatecover').className = 'hide';
  $('main').className = 'wrap';
  refreshState();
  load();
}

$('gatego').onclick = async () => {
  TOKEN = $('tok').value.trim();
  if (!TOKEN) { $('gateerr').textContent = 'the token, please'; return; }
  const res = await fetch('/api/admin/review?limit=1', { headers: { 'x-admin-token': TOKEN } });
  if (!res.ok) { $('gateerr').textContent = res.status === 403
      ? 'the admin routes are switched off here (GD_ADMIN_TOKEN is unset)'
      : 'that token was refused'; TOKEN = ''; return; }
  sessionStorage.setItem('gd_admin', TOKEN);
  unlock();
};
$('tok').addEventListener('keydown', e => { if (e.key === 'Enter') $('gatego').click(); });

/* ------------------------------------------------------------------ service state */

async function refreshState() {
  try {
    const s = await (await fetch('/api/state')).json();
    $('dot').className = 'dot ' + (s.accepting ? 'open' : 'shut');
    $('gatemsg').textContent = s.accepting ? 'taking prompts' : 'intake closed';
    $('statemeta').textContent =
      `${s.phase} \\u00b7 ${String(s.now).replace('T', ' ').slice(0, 16)} \\u00b7 gate ${s.gate_mode}` +
      ` \\u00b7 tier ${s.tier}${s.llm_enabled ? '' : ' (model off)'}` +
      (s.sunset ? ` \\u00b7 sunset ${String(s.sunset).slice(11, 16)}` : '');
    const live = $('live');
    live.href = s.live_view_url || '#';
    live.className = s.live_view_url ? '' : 'hide';
  } catch (e) {
    $('gatemsg').textContent = 'cannot reach the service';
  }
}

/* ------------------------------------------------------------------ the list */

function pct(x) { return x == null ? '?' : ((x * 100) | 0) + '%'; }

function card(r, i) {
  const sel = i === SEL ? ' sel' : '';
  const shrug = r.ok ? '' : ' shrug';
  const swatches = ['base', 'accent', 'glow'].filter(k => r.palette[k])
    .map(k => `<span class="sw" style="background:${esc(r.palette[k])}" title="${esc(k)} ${esc(r.palette[k])}"></span>`).join(' ');
  const unused = (r.unused_words || []).length
    ? `<span class="chip warn">could not use ${r.unused_words.map(esc).join(', ')}</span>` : '';
  const cov = (r.coverage != null && r.coverage < 1)
    ? `<span class="chip warn">covers ${pct(r.coverage)} of what they said</span>` : '';
  const decided = r.review === 'approved' || r.review === 'rejected';
  const acts = decided
    ? `<button class="small" data-id="${esc(r.id)}" data-decision="pending">put back in the queue</button>`
    : `<button class="go" data-id="${esc(r.id)}" data-decision="approved">Approve</button>
       <button class="no" data-id="${esc(r.id)}" data-decision="rejected">Refuse</button>`;
  return `<div class="card${sel}${shrug}" data-i="${i}">
    <p class="q">&ldquo;${esc(r.query)}&rdquo;</p>
    <p class="becomes">${r.ok
      ? `becomes <b>${esc(r.title)}</b> &mdash; ${esc(r.world)} world, ${r.duration_s}s${
          r.word ? `, showing <b>${esc(r.word)}</b>` : ', no text'}`
      : '<b style="color:var(--warn)">refused by the interpreter</b> &mdash; it would shrug'}</p>
    <div class="chips">
      ${swatches}
      ${r.theme ? `<span class="chip">${esc(r.theme)}</span>` : ''}
      <span class="chip ${r.recognizability >= 0.6 ? 'good' : (r.recognizability <= 0.35 ? 'bad' : '')}">
        recognizable ${pct(r.recognizability)}</span>
      ${cov}${unused}
      ${r.beats.length ? `<span class="chip">${r.beats.map(esc).join(' \\u2192 ')}</span>` : ''}
    </div>
    <div class="chips">
      ${(r.keywords || []).slice(0, 6).map(k => `<span class="chip">${esc(k)}</span>`).join('')}
    </div>
    ${r.notes ? `<p class="meta" style="margin:6px 0 0">${esc(r.notes)}</p>` : ''}
    <p class="meta" style="margin:8px 0 0">
      ${esc(String(r.received_at).replace('T', ' ').slice(0, 16))} &middot; ${esc(r.channel)} &middot;
      ${esc(r.tier)}${r.match ? ' / ' + esc(r.match) : ''} &middot; ${esc(r.priority)}
      ${decided ? ` &middot; <b>${esc(r.review)}</b>` : ''}</p>
    <div class="acts">${acts}</div>
  </div>`;
}

function paint() {
  $('list').innerHTML = ROWS.length
    ? ROWS.map(card).join('')
    : `<div class="panel meta">${VIEW === 'pending'
        ? 'Nothing waiting. Everything said remotely has been looked at.'
        : 'Nothing decided yet today.'}</div>`;
  for (const b of $('list').querySelectorAll('button[data-id]')) {
    b.onclick = () => decide(b.dataset.id, b.dataset.decision);
  }
  for (const c of $('list').querySelectorAll('.card')) {
    c.onclick = e => { if (e.target.tagName !== 'BUTTON') { SEL = +c.dataset.i; paint(); } };
  }
  const sel = $('list').querySelector('.card.sel');
  if (sel) sel.scrollIntoView({ block: 'nearest' });
}

async function load() {
  if (!TOKEN || BUSY) return;
  try {
    const body = await (await api(`/api/admin/review?state=${VIEW}&limit=200`)).json();
    ROWS = body.rows || [];
    if (VIEW === 'decided') ROWS = ROWS.slice().reverse();   // most recent decision first
    SEL = Math.min(SEL, Math.max(0, ROWS.length - 1));
    $('n-pending').textContent = VIEW === 'pending' ? `(${ROWS.length})` : '';
    $('n-decided').textContent = VIEW === 'decided' ? `(${ROWS.length})` : '';
    $('oops').textContent = '';
    paint();
  } catch (e) {
    if (String(e.message) !== '401') $('oops').textContent = 'could not load: ' + e.message;
  }
}

async function decide(id, decision) {
  if (BUSY) return;
  BUSY = true;
  try {
    const res = await api('/api/admin/review', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ id, decision })
    });
    if (!res.ok) { $('oops').textContent = `${res.status}: could not record that`; }
  } catch (e) {
    if (String(e.message) !== '401') $('oops').textContent = 'could not record that: ' + e.message;
  }
  BUSY = false;
  load();
}

/* ------------------------------------------------------------------ keys and tabs */

function setView(v) {
  VIEW = v; SEL = 0;
  $('tab-pending').className = v === 'pending' ? 'on' : '';
  $('tab-decided').className = v === 'decided' ? 'on' : '';
  load();
}
$('tab-pending').onclick = () => setView('pending');
$('tab-decided').onclick = () => setView('decided');
$('refresh').onclick = () => { refreshState(); load(); };

window.addEventListener('keydown', e => {
  if (!TOKEN || e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  const r = ROWS[SEL];
  if (e.key === 'j' || e.key === 'ArrowDown') { SEL = Math.min(ROWS.length - 1, SEL + 1); paint(); }
  else if (e.key === 'k' || e.key === 'ArrowUp') { SEL = Math.max(0, SEL - 1); paint(); }
  else if (e.key === 'a' && r) decide(r.id, VIEW === 'decided' ? 'pending' : 'approved');
  else if (e.key === 'r' && r) decide(r.id, 'rejected');
  else if (e.key === 'g') { refreshState(); load(); }
  else return;
  e.preventDefault();
});

$('flip').onclick = async () => {
  const body = {};
  if ($('gate').value) body.gate = $('gate').value;
  if ($('llm').value) body.llm = $('llm').value;
  if (!Object.keys(body).length) { $('opsmsg').textContent = 'pick a switch first'; return; }
  try {
    const res = await api('/api/admin/switch', {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body)
    });
    const out = await res.json();
    $('opsmsg').innerHTML = res.ok
      ? `gate <b>${esc(out.gate_mode)}</b> \\u00b7 model tier <b>${out.llm_enabled ? 'on' : 'off'}</b>` +
        (out.llm_enabled && !out.llm_available ? ' (no API key, so still local)' : '')
      : `<span class="err">${esc(out.detail || 'rejected')}</span>`;
    refreshState();
  } catch (e) { /* api() already put the token prompt back */ }
};

if (TOKEN) {
  fetch('/api/admin/review?limit=1', { headers: { 'x-admin-token': TOKEN } })
    .then(r => r.ok ? unlock() : lock(r.status === 403
      ? 'the admin routes are switched off here (GD_ADMIN_TOKEN is unset)' : ''))
    .catch(() => lock('cannot reach the service'));
}
setInterval(() => { if (TOKEN) { refreshState(); load(); } }, 15000);
</script>
</body>
</html>
"""
