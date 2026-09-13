"""A single self-contained page for trying the API by hand, served at /demo.

Not the product frontend: it is the operator's bench. Five inputs, the gate banner, the two
switches, and the full response laid out field by field. No build step, no dependencies, no
framework, so it cannot rot separately from the API it exercises.

It shows palette swatches and the sprite silhouette because those are draft *fields* worth
reading. It is not a facade renderer; nothing here pretends to be the building.
"""

from __future__ import annotations

DEMO_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GreenDream &middot; say something</title>
<style>
  :root {
    --bg: #080b12; --panel: #0e1420; --line: #1d2637; --ink: #dbe4f5; --dim: #7d8ba5;
    --accent: #5cffa6; --warn: #ffd166; --bad: #ff6b81;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink);
         font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
  a { color: var(--accent); }
  .wrap { max-width: 980px; margin: 0 auto; padding: 28px 20px 80px; }
  h1 { font-size: 22px; margin: 0 0 4px; font-weight: 650; letter-spacing: .2px; }
  .sub { color: var(--dim); margin: 0 0 22px; font-size: 14px; }
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px; margin-bottom: 18px; }
  .banner { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--dim); flex: none; }
  .dot.open { background: var(--accent); box-shadow: 0 0 10px var(--accent); }
  .dot.shut { background: var(--bad); box-shadow: 0 0 10px var(--bad); }
  .banner b { font-weight: 600; }
  .meta { color: var(--dim); font-size: 13px; }
  label.small { display: block; color: var(--dim); font-size: 12px; text-transform: uppercase;
                letter-spacing: .08em; margin: 0 0 8px; }
  input[type=text], input[type=password], select {
    width: 100%; background: #0a0f19; color: var(--ink); border: 1px solid var(--line);
    border-radius: 8px; padding: 10px 12px; font: inherit; }
  input:focus, select:focus { outline: none; border-color: #33507a; }
  .rows { display: grid; gap: 8px; }
  .row { display: flex; gap: 10px; align-items: center; }
  .row span.n { color: var(--dim); width: 16px; text-align: right; font-variant-numeric: tabular-nums; }
  .actions { display: flex; gap: 12px; align-items: center; margin-top: 14px; flex-wrap: wrap; }
  button { background: var(--accent); color: #04150c; border: 0; border-radius: 8px;
           padding: 10px 18px; font: inherit; font-weight: 650; cursor: pointer; }
  button.ghost { background: transparent; color: var(--ink); border: 1px solid var(--line); font-weight: 500; }
  button:disabled { opacity: .45; cursor: not-allowed; }
  .ops { display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; }
  .ops > div { flex: 1 1 130px; }
  .cards { display: grid; gap: 12px; }
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px;
          display: grid; grid-template-columns: 1fr auto; gap: 14px; }
  .card h3 { margin: 0 0 2px; font-size: 16px; font-weight: 620; }
  .phrase { color: var(--dim); font-size: 13px; font-style: italic; margin: 0 0 10px; }
  .badge { display: inline-block; font-size: 11px; letter-spacing: .06em; text-transform: uppercase;
           border: 1px solid var(--line); border-radius: 999px; padding: 2px 9px; color: var(--dim); }
  .badge.model { color: var(--accent); border-color: #1e4a35; }
  .badge.blocked { color: var(--bad); border-color: #4a1e28; }
  .kv { display: grid; grid-template-columns: 92px 1fr; gap: 2px 10px; font-size: 13px; }
  .kv div:nth-child(odd) { color: var(--dim); }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; margin: 8px 0 0; }
  .chip { background: #0a0f19; border: 1px solid var(--line); border-radius: 6px; padding: 1px 7px; font-size: 12px; }
  .side { display: grid; gap: 10px; justify-items: center; align-content: start; }
  .swatches { display: flex; gap: 4px; }
  .sw { width: 22px; height: 22px; border-radius: 5px; border: 1px solid rgba(255,255,255,.14); }
  .sprite { display: grid; grid-template-columns: repeat(9, 7px); gap: 1px; }
  .sprite i { width: 7px; height: 7px; border-radius: 1px; background: #131a27; }
  .bar { width: 120px; height: 5px; background: #131a27; border-radius: 3px; overflow: hidden; }
  .bar i { display: block; height: 100%; background: var(--accent); }
  .arc { border-left: 3px solid var(--accent); }
  .arc h2 { margin: 0 0 4px; font-size: 18px; letter-spacing: .1em; }
  pre { background: #060910; border: 1px solid var(--line); border-radius: 10px; padding: 12px;
        overflow: auto; max-height: 380px; font-size: 12px; color: #9fb0cd; }
  .err { color: var(--bad); }
  .hide { display: none; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Tell the building what you want to see</h1>
  <p class="sub">Five phrases. Each one comes back as an interpretation and a scene draft.
     Nothing is rendered here &mdash; this is the language half.</p>

  <div class="panel banner" id="banner">
    <span class="dot" id="dot"></span>
    <b id="bmsg">checking&hellip;</b>
    <span class="meta" id="bmeta"></span>
    <a id="blive" class="hide" target="_blank" rel="noreferrer">watch the building</a>
  </div>

  <div class="panel">
    <label class="small">your five phrases</label>
    <div class="rows" id="rows"></div>
    <div class="actions">
      <button id="send">Send to the building</button>
      <button class="ghost" id="fill">Fill with examples</button>
      <span class="meta" id="status"></span>
    </div>
  </div>

  <div class="panel">
    <label class="small">operator switches</label>
    <div class="ops">
      <div>
        <label class="small">gate</label>
        <select id="gate">
          <option value="">(leave)</option>
          <option value="auto">auto &mdash; closes at sunset</option>
          <option value="open">open</option>
          <option value="closed">closed &mdash; kill switch</option>
        </select>
      </div>
      <div>
        <label class="small">claude tier</label>
        <select id="llm">
          <option value="">(leave)</option>
          <option value="on">on</option>
          <option value="off">off &mdash; local fallback</option>
        </select>
      </div>
      <div>
        <label class="small">admin token</label>
        <input type="password" id="admin" placeholder="X-Admin-Token">
      </div>
      <div style="flex:0 0 auto"><button class="ghost" id="flip">Apply</button></div>
    </div>
    <p class="meta" id="opsmsg" style="margin:10px 0 0"></p>
  </div>

  <div id="out"></div>

  <div class="panel hide" id="rawpanel">
    <label class="small">raw response</label>
    <pre id="raw"></pre>
  </div>
</div>

<script>
const EXAMPLES = [
  "a thunderstorm over the river",
  "my heart is racing",
  "a rocket launch",
  "the first snow day",
  "i miss my dog"
];
const rows = document.getElementById('rows');
for (let i = 0; i < 5; i++) {
  const row = document.createElement('div');
  row.className = 'row';
  row.innerHTML = `<span class="n">${i + 1}</span><input type="text" maxlength="120" placeholder="${EXAMPLES[i]}">`;
  rows.appendChild(row);
}
const inputs = [...rows.querySelectorAll('input')];

function phrases() {
  return inputs.map(i => i.value.trim()).filter(Boolean);
}

async function refreshState() {
  try {
    const s = await (await fetch('/api/state')).json();
    const dot = document.getElementById('dot');
    dot.className = 'dot ' + (s.accepting ? 'open' : 'shut');
    document.getElementById('bmsg').textContent = s.message;
    document.getElementById('bmeta').textContent =
      `${s.phase} · ${s.now.replace('T', ' ')} · sunset ${(s.sunset || '?').slice(11, 16)} · ` +
      `gate ${s.gate_mode} · tier ${s.tier}` +
      (s.accepting ? (s.closes_at ? ` · closes ${s.closes_at.slice(11, 16)}` : '')
                   : (s.reopens_at ? ` · reopens ${s.reopens_at.replace('T', ' ').slice(0, 16)}` : ''));
    const live = document.getElementById('blive');
    live.href = s.live_view_url || '#';
    live.className = s.accepting ? 'hide' : '';
    document.getElementById('send').disabled = !s.accepting;
    if (!s.accepting) document.getElementById('status').textContent = 'intake is closed';
  } catch (e) {
    document.getElementById('bmsg').textContent = 'cannot reach the service';
  }
}

function spriteGrid(sprite, palette) {
  const box = document.createElement('div');
  box.className = 'sprite';
  const rows = sprite ? sprite.rows : [];
  const lit = sprite ? (sprite.color || palette.glow) : null;
  for (const row of rows) {
    for (const ch of row) {
      const cell = document.createElement('i');
      if (ch === '#') cell.style.background = lit;
      box.appendChild(cell);
    }
  }
  return rows.length ? box : null;
}

function card(r) {
  const d = r.spec_draft, it = r.interpretation;
  const el = document.createElement('div');
  el.className = 'card';

  const tierClass = r.tier === 'blocked' ? 'blocked'
                  : (r.tier === 'library' || r.tier === 'lexicon') ? '' : 'model';
  const left = document.createElement('div');
  left.innerHTML = `
    <h3>${it.title || d.title}</h3>
    <p class="phrase">&ldquo;${r.phrase.replace(/</g, '&lt;')}&rdquo;</p>
    <span class="badge ${tierClass}">${r.tier}</span>
    <span class="badge">${it.theme}</span>
    ${d.word ? `<span class="badge">word ${d.word}</span>` : ''}
    <div class="chips">${(it.keywords || []).map(k => `<span class="chip">${k}</span>`).join('')}</div>
    <div class="kv" style="margin-top:10px">
      <div>world</div><div>${d.world}</div>
      <div>motion</div><div>${d.motion.kind} · speed ${d.motion.speed.toFixed(2)} · amount ${d.motion.amount.toFixed(2)}</div>
      <div>particles</div><div>${d.particles.kind}${d.particles.kind === 'none' ? '' : ` · ${d.particles.density.toFixed(2)} ${d.particles.direction}`}</div>
      <div>flash</div><div>${d.flash.kind}${d.flash.kind === 'none' ? '' : ` · ${d.flash.rate.toFixed(2)}`}</div>
      <div>tempo</div><div>${Math.round(d.tempo_bpm)} bpm · ${d.duration_s}s</div>
      <div>notes</div><div>${it.notes || '&mdash;'}</div>
    </div>`;

  const side = document.createElement('div');
  side.className = 'side';
  const sw = document.createElement('div');
  sw.className = 'swatches';
  for (const key of ['base', 'accent', 'glow']) {
    const c = document.createElement('div');
    c.className = 'sw';
    c.style.background = d.palette[key];
    c.title = `${key} ${d.palette[key]}`;
    sw.appendChild(c);
  }
  side.appendChild(sw);
  const grid = spriteGrid(d.sprite, d.palette);
  if (grid) side.appendChild(grid);
  const bars = document.createElement('div');
  bars.innerHTML = `
    <div class="meta">recognizable ${(it.recognizability * 100) | 0}%</div>
    <div class="bar"><i style="width:${it.recognizability * 100}%"></i></div>
    <div class="meta" style="margin-top:6px">arousal ${it.mood.arousal.toFixed(2)} · valence ${it.mood.valence.toFixed(2)}</div>
    <div class="bar"><i style="width:${it.mood.arousal * 100}%"></i></div>`;
  side.appendChild(bars);

  el.appendChild(left);
  el.appendChild(side);
  return el;
}

function render(body) {
  const out = document.getElementById('out');
  out.innerHTML = '';

  const arc = document.createElement('div');
  arc.className = 'panel arc';
  arc.innerHTML = `
    <h2>${body.arc.title}</h2>
    <p style="margin:0 0 8px">${body.arc.logline}</p>
    <p class="meta" style="margin:0">${body.arc.through_line}</p>
    <div class="chips">${body.arc.order.map((i, n) =>
      `<span class="chip">${n + 1}. phrase ${i + 1}</span>`).join('')}</div>
    <p class="meta" style="margin:10px 0 0">tier ${body.tier} · ${body.latency_ms} ms ·
       ${body.channel} · priority ${body.priority}</p>`;
  out.appendChild(arc);

  const cards = document.createElement('div');
  cards.className = 'cards';
  body.results.forEach(r => cards.appendChild(card(r)));
  out.appendChild(cards);

  document.getElementById('rawpanel').className = 'panel';
  document.getElementById('raw').textContent = JSON.stringify(body, null, 2);
}

document.getElementById('fill').onclick = () => {
  inputs.forEach((el, i) => el.value = EXAMPLES[i]);
};

document.getElementById('send').onclick = async () => {
  const list = phrases();
  const status = document.getElementById('status');
  if (!list.length) { status.innerHTML = '<span class="err">say at least one thing</span>'; return; }
  status.textContent = 'the tower is thinking\\u2026';
  document.getElementById('send').disabled = true;
  try {
    const res = await fetch('/api/ingest', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ phrases: list, source: 'web' })
    });
    const body = await res.json();
    if (res.status === 423) {
      status.innerHTML = `<span class="err">${body.message}</span>`;
      document.getElementById('rawpanel').className = 'panel';
      document.getElementById('raw').textContent = JSON.stringify(body, null, 2);
      document.getElementById('out').innerHTML = '';
    } else if (!res.ok) {
      status.innerHTML = `<span class="err">${res.status}: ${body.detail || body.message || 'rejected'}</span>`;
    } else {
      status.textContent = `answered by ${body.tier} in ${body.latency_ms} ms`;
      render(body);
    }
  } catch (e) {
    status.innerHTML = `<span class="err">${e}</span>`;
  }
  refreshState();
};

document.getElementById('flip').onclick = async () => {
  const body = {};
  const gate = document.getElementById('gate').value;
  const llm = document.getElementById('llm').value;
  if (gate) body.gate = gate;
  if (llm) body.llm = llm;
  const msg = document.getElementById('opsmsg');
  if (!Object.keys(body).length) { msg.textContent = 'pick a switch first'; return; }
  const res = await fetch('/api/admin/switch', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-admin-token': document.getElementById('admin').value },
    body: JSON.stringify(body)
  });
  const out = await res.json();
  msg.innerHTML = res.ok
    ? `gate <b>${out.gate_mode}</b> · claude tier <b>${out.llm_enabled ? 'on' : 'off'}</b>` +
      (out.llm_enabled && !out.llm_available ? ' (no API key, so still local)' : '')
    : `<span class="err">${out.detail || 'rejected'}</span>`;
  refreshState();
};

refreshState();
setInterval(refreshState, 20000);
</script>
</body>
</html>
"""
