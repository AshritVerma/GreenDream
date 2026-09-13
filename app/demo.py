"""A single self-contained page for trying the API by hand, served at /demo.

Not the product frontend: it is the operator's bench. One query box with a word counter, the
gate banner, the two switches, the resulting draft field by field, and the day's arc.
No build step, no dependencies, no framework, so it cannot rot separately from the API it
exercises.

It shows palette swatches, the beat timeline, and a rough 9x17 animation of the draft, because a
scene that happens over time cannot be judged from a table of numbers. That animation is a sketch
for reading drafts, not the facade renderer, and it deliberately makes no attempt to be one: the
real renderer lives in GreenDream and owns every pixel decision.
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
  .wrap { max-width: 900px; margin: 0 auto; padding: 28px 20px 80px; }
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
  #q { font-size: 20px; padding: 14px 16px; letter-spacing: .3px; }
  input:focus, select:focus { outline: none; border-color: #33507a; }
  .count { font-variant-numeric: tabular-nums; }
  .count.over { color: var(--bad); }
  .actions { display: flex; gap: 12px; align-items: center; margin-top: 12px; flex-wrap: wrap; }
  button { background: var(--accent); color: #04150c; border: 0; border-radius: 8px;
           padding: 10px 18px; font: inherit; font-weight: 650; cursor: pointer; }
  button.ghost { background: transparent; color: var(--ink); border: 1px solid var(--line); font-weight: 500; }
  button.tiny { padding: 3px 9px; font-size: 12px; font-weight: 500; }
  button:disabled { opacity: .45; cursor: not-allowed; }
  .ops { display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; }
  .ops > div { flex: 1 1 130px; }
  .scene { display: grid; grid-template-columns: 1fr auto; gap: 18px; }
  .scene h2 { margin: 0 0 2px; font-size: 20px; font-weight: 620; }
  .said { color: var(--dim); font-size: 13px; font-style: italic; margin: 0 0 10px; }
  .badge { display: inline-block; font-size: 11px; letter-spacing: .06em; text-transform: uppercase;
           border: 1px solid var(--line); border-radius: 999px; padding: 2px 9px; color: var(--dim); }
  .badge.model { color: var(--accent); border-color: #1e4a35; }
  .badge.blocked { color: var(--bad); border-color: #4a1e28; }
  .badge.partial { color: var(--warn); border-color: #4a3c17; }
  .unused { color: var(--warn); font-size: 13px; margin: 10px 0 0; }
  .unused s { color: var(--dim); }
  .kv { display: grid; grid-template-columns: 92px 1fr; gap: 2px 10px; font-size: 13px; }
  .kv div:nth-child(odd) { color: var(--dim); }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; margin: 8px 0 0; }
  .chip { background: #0a0f19; border: 1px solid var(--line); border-radius: 6px; padding: 1px 7px; font-size: 12px; }
  .chip.try { cursor: pointer; }
  .chip.try:hover { border-color: #33507a; color: var(--accent); }
  .side { display: grid; gap: 10px; justify-items: center; align-content: start; }
  .swatches { display: flex; gap: 4px; }
  .sw { width: 24px; height: 24px; border-radius: 5px; border: 1px solid rgba(255,255,255,.14); }
  .sprite { display: grid; grid-template-columns: repeat(9, 9px); gap: 1px; }
  .sprite i { width: 9px; height: 9px; border-radius: 1px; background: #131a27; }
  .facade { display: grid; grid-template-columns: repeat(9, 13px); gap: 2px;
            background: #04060b; border: 1px solid var(--line); border-radius: 7px; padding: 7px; }
  .facade i { width: 13px; height: 13px; border-radius: 2px; background: #080c14; }
  .cap { text-align: center; font-size: 12px; min-height: 34px; }
  .cap b { color: var(--ink); font-weight: 600; }
  .timeline { display: flex; gap: 3px; margin-top: 14px; }
  .timeline div { flex-grow: 1; flex-basis: 0; background: #0a0f19; border: 1px solid var(--line);
                  border-radius: 6px; padding: 4px 6px; font-size: 12px; color: var(--dim);
                  text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
                  transition: background .12s, color .12s, border-color .12s; }
  .timeline div.on { background: #10203a; border-color: #33507a; color: var(--ink); }
  .bar { width: 130px; height: 5px; background: #131a27; border-radius: 3px; overflow: hidden; }
  .bar i { display: block; height: 100%; background: var(--accent); }
  .arc { border-left: 3px solid var(--accent); }
  .arc h2 { margin: 0 0 4px; font-size: 18px; letter-spacing: .1em; }
  pre { background: #060910; border: 1px solid var(--line); border-radius: 10px; padding: 12px;
        overflow: auto; max-height: 340px; font-size: 12px; color: #9fb0cd; }
  .err { color: var(--bad); }
  .hide { display: none; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Tell the building what you want to see</h1>
  <p class="sub">One thing, in up to five words. It comes back as an interpretation and one
     scene draft. Nothing is rendered here &mdash; this is the language half.</p>

  <div class="panel banner" id="banner">
    <span class="dot" id="dot"></span>
    <b id="bmsg">checking&hellip;</b>
    <span class="meta" id="bmeta"></span>
    <a id="blive" class="hide" target="_blank" rel="noreferrer">watch the building</a>
  </div>

  <div class="panel">
    <label class="small">your five words</label>
    <input type="text" id="q" maxlength="60" placeholder="a rocket launch" autocomplete="off">
    <div class="actions">
      <button id="send">Show me</button>
      <button class="ghost" id="peek" title="a cheap fast guess; nothing is logged">Preview</button>
      <span class="meta count" id="count">0 / 5 words</span>
      <span class="meta" id="status"></span>
    </div>
    <div class="chips" id="tries"></div>
  </div>

  <div id="out"></div>

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

  <div class="panel">
    <label class="small">tonight's dream, from everything said today
      <button class="ghost tiny" id="arcbtn" style="margin-left:8px">refresh</button></label>
    <div id="arcout" class="meta">nothing yet today</div>
  </div>

  <div class="panel hide" id="rawpanel">
    <label class="small">raw response</label>
    <pre id="raw"></pre>
  </div>
</div>

<script>
const TRIES = ["a thunderstorm", "my heart is racing", "a rocket launch", "the first snow",
               "lebron dunk", "take me to space", "finals week", "the T is late"];
const q = document.getElementById('q');
const tries = document.getElementById('tries');
for (const t of TRIES) {
  const chip = document.createElement('span');
  chip.className = 'chip try';
  chip.textContent = t;
  chip.onclick = () => { q.value = t; count(); q.focus(); };
  tries.appendChild(chip);
}

let MAXW = 5;

function words() {
  return q.value.trim().split(/\\s+/).filter(Boolean);
}

function count() {
  const n = words().length;
  const el = document.getElementById('count');
  el.textContent = `${n} / ${MAXW} words`;
  el.className = 'meta count' + (n > MAXW ? ' over' : '');
}
q.addEventListener('input', count);
q.addEventListener('keydown', e => { if (e.key === 'Enter') document.getElementById('send').click(); });

async function refreshState() {
  try {
    const s = await (await fetch('/api/state')).json();
    MAXW = s.max_words;
    q.maxLength = s.max_chars;
    count();
    document.getElementById('dot').className = 'dot ' + (s.accepting ? 'open' : 'shut');
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
  if (!sprite || !sprite.rows.length) return null;
  const box = document.createElement('div');
  box.className = 'sprite';
  const lit = sprite.color || palette.glow;
  for (const row of sprite.rows) {
    for (const ch of row) {
      const cell = document.createElement('i');
      if (ch === '#') cell.style.background = lit;
      box.appendChild(cell);
    }
  }
  return box;
}

/* ------------------------------------------------------------------ facade sketch
   A rough 9x17 read-through of a draft, so a scene can be judged as something that happens
   rather than as a list of numbers. This is NOT the building's renderer and does not try to
   be: it is one plausible reading of the same vocabulary, thrown away every time you submit.
*/
const FR = 17, FC = 9;
let anim = null;

const rgb = h => { const n = parseInt(String(h).slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; };
const mix = (a, b, t) => [0, 1, 2].map(i => a[i] + (b[i] - a[i]) * t);
const css = c => `rgb(${Math.min(255, c[0] | 0)},${Math.min(255, c[1] | 0)},${Math.min(255, c[2] | 0)})`;

function playFacade(d, host) {
  const box = document.createElement('div');
  box.className = 'facade';
  const cells = [];
  for (let i = 0; i < FR * FC; i++) { const c = document.createElement('i'); cells.push(c); box.appendChild(c); }
  host.appendChild(box);
  const cap = document.createElement('div');
  cap.className = 'meta cap';
  host.appendChild(cap);

  const base = rgb(d.palette.base), accent = rgb(d.palette.accent), glow = rgb(d.palette.glow);
  const sprite = d.sprite, spriteCol = sprite ? rgb(sprite.color) : glow;
  const held = { at: 0, label: 'held', motion: d.motion, particles: d.particles,
                 flash: d.flash, brightness: 1, word: d.word };
  const beats = (d.beats && d.beats.length) ? d.beats : [held];
  const strip = document.getElementById('strip');
  const segs = strip ? [...strip.children] : [];

  let parts = [], flashUntil = 0, t0 = performance.now(), last = 0;

  function frame(now) {
    anim = requestAnimationFrame(frame);
    if (now - last < 45) return;              // ~22 fps is plenty for a sketch
    last = now;

    const dur = d.duration_s * 1000;
    const t = ((now - t0) % dur) / dur;
    let bi = 0;
    for (let k = 0; k < beats.length; k++) if (beats[k].at <= t) bi = k;
    const b = beats[bi], nb = beats[bi + 1];
    const span = ((nb ? nb.at : 1) - b.at) || 1;
    const into = Math.min(1, Math.max(0, (t - b.at) / span));
    const bright = nb ? b.brightness + (nb.brightness - b.brightness) * into : b.brightness;
    const mo = b.motion, pa = b.particles, fl = b.flash;

    segs.forEach((s, i) => s.className = i === bi ? 'on' : '');
    cap.innerHTML = `<b>${b.label || d.title}</b><br>${b.word ? 'showing ' + b.word : 'no text'}`;

    // background: the palette's dark base, lifted by this beat's brightness
    let k = 0.3 + 0.7 * bright;
    const secs = now / 1000, beat = d.tempo_bpm / 60;
    if (mo.kind === 'pulse' || mo.kind === 'breathe') {
      k *= 1 - mo.amount * 0.45 * (1 - Math.sin(secs * beat * Math.PI * (mo.kind === 'pulse' ? 2 : 0.6)));
    }
    const field = [];
    for (let i = 0; i < FR * FC; i++) field.push(base.map(v => v * k));

    // shake displaces the whole facade a window or two, per frame
    const dx = mo.kind === 'shake' ? Math.round((Math.random() * 2 - 1) * (1 + 2 * mo.amount) * mo.speed) : 0;

    // the moving band: what the motion field actually looks like
    const phase = (secs * (0.15 + mo.speed * 0.85)) % 1;
    const reach = 1.4 + 3.2 * mo.amount;
    if (['rise', 'fall', 'sweep', 'spiral'].includes(mo.kind)) {
      for (let r = 0; r < FR; r++) for (let c = 0; c < FC; c++) {
        let dist;
        if (mo.kind === 'rise') dist = Math.abs(r - (1 - phase) * (FR - 1));
        else if (mo.kind === 'fall') dist = Math.abs(r - phase * (FR - 1));
        else if (mo.kind === 'sweep') dist = Math.abs(c - phase * (FC - 1));
        else {
          const ang = Math.atan2(r - FR / 2, c - FC / 2) / (Math.PI * 2) + 0.5;
          dist = Math.min(Math.abs(ang - phase), 1 - Math.abs(ang - phase)) * 8;
        }
        const lit = Math.max(0, 1 - dist / reach);
        if (lit > 0) {
          const i = r * FC + Math.min(FC - 1, Math.max(0, c + dx));
          field[i] = mix(field[i], accent, lit * 0.85 * k);
        }
      }
    }

    // particles
    if (pa.kind !== 'none') {
      if (Math.random() < pa.density) parts.push({ c: Math.random() * FC, r: pa.direction === 'down' ? -1 : FR, life: 1 });
      const vy = (pa.direction === 'down' ? 1 : -1) * (0.35 + 1.3 * pa.density);
      const pcol = pa.kind === 'stars' || pa.kind === 'sparks' ? glow : accent;
      parts = parts.filter(p => { p.r += vy; return p.r > -2 && p.r < FR + 1; }).slice(-90);
      for (const p of parts) {
        const r = Math.round(p.r), c = Math.round(p.c) + dx;
        if (r >= 0 && r < FR && c >= 0 && c < FC) {
          const i = r * FC + c;
          field[i] = mix(field[i], pcol, 0.8 * k);
        }
      }
    }

    // sprite, moved by its anim
    if (sprite) {
      const h = sprite.rows.length, mid = Math.round((FR - h) / 2);
      let top = mid;
      if (sprite.anim === 'rise') top = Math.round((1 - phase) * (FR - h));
      else if (sprite.anim === 'fall') top = Math.round(phase * (FR - h));
      else if (sprite.anim === 'bounce') top = mid + Math.round(Math.sin(secs * beat * Math.PI * 2) * Math.min(3, mid));
      const sk = sprite.anim === 'pulse' ? 0.55 + 0.45 * (0.5 + 0.5 * Math.sin(secs * beat * Math.PI * 2)) : 1;
      sprite.rows.forEach((row, ri) => {
        const r = top + ri;
        if (r < 0 || r >= FR) return;
        [...row].forEach((ch, ci) => {
          const c = ci + dx;
          if (ch === '#' && c >= 0 && c < FC) field[r * FC + c] = spriteCol.map(v => v * k * sk);
        });
      });
    }

    // flash: the one thing that should make you flinch
    if (fl.kind !== 'none' && Math.random() < fl.rate * 0.14) flashUntil = now + (fl.kind === 'lightning' ? 70 : 120);
    if (now < flashUntil) for (let i = 0; i < field.length; i++) field[i] = mix(field[i], glow, 0.8);

    for (let i = 0; i < field.length; i++) cells[i].style.background = css(field[i]);
  }
  if (anim) cancelAnimationFrame(anim);
  anim = requestAnimationFrame(frame);
}

function beatStrip(d) {
  const strip = document.createElement('div');
  strip.className = 'timeline';
  strip.id = 'strip';
  const beats = (d.beats && d.beats.length) ? d.beats : [];
  if (!beats.length) {
    strip.innerHTML = `<div>one held picture for ${d.duration_s}s &mdash; no beats</div>`;
    return strip;
  }
  beats.forEach((b, i) => {
    const seg = document.createElement('div');
    const end = i + 1 < beats.length ? beats[i + 1].at : 1;
    seg.style.flexGrow = String(Math.max(0.08, end - b.at));
    seg.textContent = b.label || `beat ${i + 1}`;
    seg.title = `${(b.at * d.duration_s).toFixed(1)}s · brightness ${b.brightness}`;
    strip.appendChild(seg);
  });
  return strip;
}

function render(body) {
  const r = body.result, d = r.spec_draft, it = r.interpretation;
  const out = document.getElementById('out');
  out.innerHTML = '';

  const panel = document.createElement('div');
  panel.className = 'panel scene';
  const tierClass = r.tier === 'blocked' ? 'blocked'
                  : (r.tier === 'library' || r.tier === 'lexicon') ? '' : 'model';

  const spent = (r.unused_words || []).length
    ? `<p class="unused">could not use ${r.unused_words.map(w => `<b>${w}</b>`).join(', ')} &mdash;
       this scene covers ${(r.coverage * 100) | 0}% of what you said</p>`
    : '';

  const left = document.createElement('div');
  left.innerHTML = `
    <h2>${it.title || d.title}</h2>
    <p class="said">&ldquo;${r.query.replace(/</g, '&lt;')}&rdquo; &middot; ${r.words.length} words</p>
    ${body.preview ? '<span class="badge partial">preview &middot; not logged</span>' : ''}
    <span class="badge ${tierClass}">${r.tier}</span>
    ${r.match && r.match !== r.tier ? `<span class="badge ${(r.unused_words || []).length ? 'partial' : ''}">${r.match} match</span>` : ''}
    <span class="badge">${it.theme}</span>
    ${d.word ? `<span class="badge">shows ${d.word}</span>` : '<span class="badge">no text</span>'}
    <div class="chips">${(it.keywords || []).map(k => `<span class="chip">${k}</span>`).join('')}</div>
    ${spent}
    <div class="kv" style="margin-top:12px">
      <div>world</div><div>${d.world}</div>
      <div>motion</div><div>${d.motion.kind} · speed ${d.motion.speed.toFixed(2)} · amount ${d.motion.amount.toFixed(2)}</div>
      <div>particles</div><div>${d.particles.kind}${d.particles.kind === 'none' ? '' : ` · ${d.particles.density.toFixed(2)} ${d.particles.direction}`}</div>
      <div>flash</div><div>${d.flash.kind}${d.flash.kind === 'none' ? '' : ` · ${d.flash.rate.toFixed(2)}`}</div>
      <div>tempo</div><div>${Math.round(d.tempo_bpm)} bpm · ${d.duration_s}s</div>
      <div>sprite</div><div>${d.sprite ? `${d.sprite.rows.length} rows · ${d.sprite.anim}` : 'none — the whole facade carries it'}</div>
      <div>notes</div><div>${it.notes || '&mdash;'}</div>
    </div>
    <p class="meta" style="margin:12px 0 0">answered by ${body.tier} in ${body.latency_ms} ms ·
       ${body.channel} · priority ${body.priority}</p>`;

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
  const stage = document.createElement('div');
  stage.className = 'side';
  side.appendChild(stage);
  const bars = document.createElement('div');
  bars.innerHTML = `
    <div class="meta">recognizable ${(it.recognizability * 100) | 0}%</div>
    <div class="bar"><i style="width:${it.recognizability * 100}%"></i></div>
    <div class="meta" style="margin-top:6px">arousal ${it.mood.arousal.toFixed(2)} · valence ${it.mood.valence.toFixed(2)}</div>
    <div class="bar"><i style="width:${it.mood.arousal * 100}%"></i></div>`;
  side.appendChild(bars);

  panel.appendChild(left);
  panel.appendChild(side);
  out.appendChild(panel);
  left.appendChild(beatStrip(d));   // in the DOM before the player looks for it
  playFacade(d, stage);

  document.getElementById('rawpanel').className = 'panel';
  document.getElementById('raw').textContent = JSON.stringify(body, null, 2);
}

async function refreshArc() {
  const el = document.getElementById('arcout');
  try {
    const a = await (await fetch('/api/arc')).json();
    if (!a.count) { el.className = 'meta'; el.textContent = 'nothing yet today'; return; }
    el.className = '';
    el.innerHTML = `
      <div class="arc" style="padding-left:12px">
        <h2>${a.arc.title}</h2>
        <p style="margin:0 0 6px">${a.arc.logline}</p>
        <p class="meta" style="margin:0">${a.arc.through_line}</p>
        <div class="chips">${a.arc.order.map((i, n) =>
          `<span class="chip">${n + 1}. ${a.scenes[i] || '?'}</span>`).join('')}</div>
      </div>`;
  } catch (e) {
    el.className = 'meta err';
    el.textContent = String(e);
  }
}
document.getElementById('arcbtn').onclick = refreshArc;

async function submit(kind) {
  const status = document.getElementById('status');
  const list = words();
  if (!list.length) { status.innerHTML = '<span class="err">say something</span>'; return; }
  if (list.length > MAXW) { status.innerHTML = `<span class="err">${MAXW} words at most</span>`; return; }
  status.textContent = kind === 'preview' ? 'guessing\\u2026' : 'the tower is thinking\\u2026';
  document.getElementById('send').disabled = true;
  document.getElementById('peek').disabled = true;
  try {
    const res = await fetch(kind === 'preview' ? '/api/preview' : '/api/ingest', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ query: q.value.trim(), source: 'web' })
    });
    const body = await res.json();
    if (res.status === 423) {
      status.innerHTML = `<span class="err">${body.message}</span>`;
      document.getElementById('rawpanel').className = 'panel';
      document.getElementById('raw').textContent = JSON.stringify(body, null, 2);
      document.getElementById('out').innerHTML = '';
    } else if (!res.ok) {
      const why = body.detail ? (body.detail[0] ? body.detail[0].msg : body.detail) : (body.message || 'rejected');
      status.innerHTML = `<span class="err">${res.status}: ${why}</span>`;
    } else {
      status.textContent = '';
      render(body);
      if (!body.preview) refreshArc();   // a preview is not part of tonight
    }
  } catch (e) {
    status.innerHTML = `<span class="err">${e}</span>`;
  }
  document.getElementById('peek').disabled = false;
  refreshState();
}

document.getElementById('send').onclick = () => submit('submit');
document.getElementById('peek').onclick = () => submit('preview');

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
refreshArc();
setInterval(refreshState, 20000);
</script>
</body>
</html>
"""
