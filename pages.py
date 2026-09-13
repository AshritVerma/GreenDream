"""Phone pages served by the app: /say (tell the building something) and /journal (the day + dreams)."""

SAY_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>Tell Green something</title>
<style>
  body{margin:0;background:#07090f;color:#e6e9ef;font:17px/1.5 system-ui,-apple-system,sans-serif;display:flex;flex-direction:column;align-items:center;padding:22px 18px;min-height:100vh;box-sizing:border-box}
  h1{font-size:22px;margin:4px 0 2px} p{color:#8a94a6;margin:4px 0 14px;text-align:center;max-width:380px}
  form{width:100%;max-width:420px;display:flex;flex-direction:column;gap:10px}
  input{background:#0f131c;color:#e6e9ef;border:1px solid #27324a;border-radius:12px;padding:16px;font:inherit;font-size:19px}
  button{background:#ffb454;color:#1a1204;border:0;border-radius:12px;padding:16px;font:inherit;font-size:19px;font-weight:700}
  .st{font-size:13px;color:#8a94a6;text-align:center;margin-top:10px}
  ul{list-style:none;padding:0;margin:18px 0 0;width:100%;max-width:420px} li{padding:8px 0;border-top:1px solid #1d2431;font-size:15px;display:flex;justify-content:space-between;gap:10px}
  li span{color:#8a94a6;font-variant-numeric:tabular-nums}
  .phase{font-size:13px;color:#ffb454;letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px}
  a{color:#7cc4ff}
</style></head>
<body>
  <div class="phase" id="phase">…</div>
  <h1>Tell the Green Building something</h1>
  <p>A thing, a place, a feeling, a moment. By day it becomes it. Tonight it dreams everything back.</p>
  <form id="f"><input id="t" placeholder="e.g. a rocket launch" autocomplete="off" maxlength="120"><button>Say it</button></form>
  <div class="st" id="st"></div>
  <ul id="recent"></ul>
  <p style="margin-top:20px"><a href="/journal">Tonight's dream journal →</a></p>
  <script>
    const f=document.getElementById('f'), t=document.getElementById('t'), st=document.getElementById('st');
    let last=0;
    f.onsubmit=e=>{e.preventDefault(); const v=t.value.trim(); if(!v) return; if(Date.now()-last<10000){st.textContent='one thing every 10 s — give the building a moment'; return;} last=Date.now();
      fetch('/input',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'text',text:v,source:'phone'})}).then(()=>{st.textContent='heard: "'+v+'"'; t.value=''; refresh();}).catch(()=>{st.textContent='cannot reach the building'});};
    function refresh(){ fetch('/api/journal').then(r=>r.json()).then(j=>{ document.getElementById('phase').textContent = j.phase + ' · ' + String(Math.floor(j.hour)).padStart(2,'0') + ':' + String(Math.floor((j.hour%1)*60)).padStart(2,'0') + (j.phase==='NIGHT' ? ' · dreaming — what you say now goes into the next dream' : '');
      document.getElementById('recent').innerHTML = j.prompts.slice(-8).reverse().map(p=>'<li>'+p.text.replace(/</g,'&lt;')+'<span>'+p.when+'</span></li>').join(''); }).catch(()=>{}); }
    refresh(); setInterval(refresh, 8000);
  </script>
</body></html>
"""

JOURNAL_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Green's dream journal</title>
<style>
  body{margin:0;background:#07090f;color:#e6e9ef;font:16px/1.55 system-ui,-apple-system,sans-serif;padding:24px 18px 60px}
  .wrap{max-width:720px;margin:0 auto} h1{font-size:26px;margin:0 0 4px} .phase{color:#ffb454;letter-spacing:.12em;text-transform:uppercase;font-size:13px}
  h2{font-size:14px;letter-spacing:.12em;text-transform:uppercase;color:#8a94a6;margin:26px 0 8px}
  .dream{background:#0f131c;border:1px solid #1d2431;border-radius:10px;padding:14px 16px;margin:10px 0}
  .dream b{font-size:20px;letter-spacing:.06em} .dream i{color:#c6cddb;display:block;margin:4px 0 8px}
  .dream ol{margin:0 0 0 18px;padding:0;color:#8a94a6;font-size:14px} .dream li{margin:3px 0} .dream li em{color:#e6e9ef;font-style:normal}
  ul{list-style:none;padding:0;margin:0} ul li{padding:6px 0;border-top:1px solid #1d2431;display:flex;gap:12px;font-size:15px} ul li span{color:#8a94a6;font-variant-numeric:tabular-nums;min-width:48px}
  .now{color:#7cc4ff;font-size:14px}
  a{color:#7cc4ff}
</style></head>
<body><div class="wrap">
  <div class="phase" id="phase">…</div>
  <h1>Green's dream journal</h1>
  <div class="now" id="now"></div>
  <h2>Tonight's dreams</h2><div id="dreams"></div>
  <h2>What people said today</h2><ul id="prompts"></ul>
  <p style="margin-top:22px"><a href="/say">Tell it something →</a></p>
  <script>
    function esc(s){return String(s).replace(/</g,'&lt;')}
    function refresh(){ fetch('/api/journal').then(r=>r.json()).then(j=>{
      document.getElementById('phase').textContent = j.phase + ' · ' + String(Math.floor(j.hour)).padStart(2,'0') + ':' + String(Math.floor((j.hour%1)*60)).padStart(2,'0') + ' · sunrise ' + j.sunrise.toFixed(1) + ' · sunset ' + j.sunset.toFixed(1);
      document.getElementById('now').textContent = j.now ? 'now: ' + j.now : '';
      document.getElementById('dreams').innerHTML = j.dreams.length ? j.dreams.map(d=>'<div class="dream"><b>'+esc(d.title)+'</b> <span style="color:#8a94a6;font-size:12px">dream '+d.cycle+' · '+esc(d.tier)+'</span><i>'+esc(d.logline)+'</i><ol>'+d.scenes.map(s=>'<li><em>'+esc(s.act)+'</em> · '+esc(s.op)+' · '+esc(s.note||'')+'</li>').join('')+'</ol></div>').join('') : '<div class="dream"><i>No dreams yet — they begin at sunset.</i></div>';
      document.getElementById('prompts').innerHTML = j.prompts.slice().reverse().map(p=>'<li><span>'+p.when+'</span>'+esc(p.text)+' <span style="min-width:0">→ '+esc(p.title)+'</span></li>').join('') || '<li><span></span>Nothing yet today.</li>';
    }).catch(()=>{}); }
    refresh(); setInterval(refresh, 6000);
  </script>
</div></body></html>
"""
