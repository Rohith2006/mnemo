"""
Local web UI for the proactive PA — runs while Telegram is blocked.

Same brain (brain.py) and memory (store.py) as the Telegram bot, served as a
single-page app: chat on the left, a live "what I'm tracking" dashboard on
the right that refreshes after every turn, proactive briefing/insights
buttons, an alert banner for overdue tasks / at-risk streaks, and in-browser
reminder toasts.

Run:    python web.py     →    open http://127.0.0.1:8000
Uses the local Anthropic proxy configured in brain.py (claude-opus-4-8).
"""

import os
import json
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import brain
from store import get_store, reminder_store, DEFAULT_TZ
from zoneinfo import ZoneInfo

WEB_USER_ID = os.getenv("PA_WEB_USER", "web-rohith")
WEB_CHAT_ID = 0
TZ = ZoneInfo(os.getenv("PA_TZ", DEFAULT_TZ))
PORT = int(os.getenv("PA_WEB_PORT", "8000"))

_history: list[dict] = []


# ── domain helpers ──────────────────────────────────────────────────────────
def state_dict() -> dict:
    s = get_store(WEB_USER_ID)
    mood = s.recent_mood(7)
    pending = reminder_store.get_all_for_chat(WEB_CHAT_ID)
    overdue = s.overdue_tasks(TZ)
    at_risk = s.habits_at_risk(TZ)

    alerts = []
    for t in overdue:
        alerts.append(f"⚠️ \"{t['task']}\" was due {t['due_dt'].strftime('%H:%M %a')}")
    for h in at_risk:
        if h.get("streak", 0) >= 2 and datetime.now(TZ).hour >= 12:
            alerts.append(f"🔥 {h['name']} streak (day {h['streak']}) — not done today yet")

    return {
        "profile": s.facts(),
        "habits": [
            {"name": h["name"], "streak": h.get("streak", 0), "best": h.get("best_streak", 0)}
            for h in s.active_habits()
        ],
        "tasks": [{"task": t["task"], "due": t.get("due")} for t in s.open_tasks()],
        "trends": s.trends(),
        "log": [
            {"category": e["category"], "key": e["key"], "value": e.get("value"), "unit": e.get("unit", "")}
            for e in s.recent_log(7)[-10:]
        ],
        "mood": (
            {"avg": round(sum(m["mood"] for m in mood) / len(mood), 1), "count": len(mood)}
            if mood else None
        ),
        "reminders": [
            {"task": r["task"], "at": r["fire_at_dt"].astimezone(TZ).strftime("%H:%M %a %d %b")}
            for r in pending
        ],
        "alerts": alerts,
    }


def do_chat(message: str) -> dict:
    s = get_store(WEB_USER_ID)
    reminder = brain.detect_reminder(message, TZ)
    pending = reminder_store.get_all_for_chat(WEB_CHAT_ID)

    reply = brain.build_reply(s, message, _history, TZ,
                              pending_reminders=pending, new_reminder=reminder)

    new_rem = None
    if reminder:
        fire_at = datetime.now().astimezone() + timedelta(seconds=reminder["seconds"])
        reminder_store.add(WEB_CHAT_ID, reminder["task"], fire_at)
        new_rem = {"task": reminder["task"], "seconds": reminder["seconds"]}

    _history.append({"role": "user", "content": message})
    _history.append({"role": "assistant", "content": reply})
    del _history[:-20]

    brain.apply_extraction(s, brain.extract(message, reply, s, TZ))
    return {"reply": reply, "reminder": new_rem, "state": state_dict()}


def do_digest(kind: str) -> dict:
    s = get_store(WEB_USER_ID)
    if not s.facts() and not s.recent_log(30) and not s.open_tasks():
        return {"text": "I don't have enough to go on yet — tell me about your day first 🙂"}
    return {"text": brain.build_digest(s, TZ, kind)}


def do_forget() -> dict:
    s = get_store(WEB_USER_ID)
    s.forget_all()
    _history.clear()
    return {"state": state_dict()}


# ── HTTP server ─────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # quiet

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json_body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (json.JSONDecodeError, ValueError):
            return {}

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._send(200, json.dumps(state_dict()))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        try:
            if self.path == "/api/chat":
                msg = (self._json_body().get("message") or "").strip()
                if not msg:
                    self._send(400, json.dumps({"error": "empty"}))
                    return
                self._send(200, json.dumps(do_chat(msg)))
            elif self.path == "/api/digest":
                kind = self._json_body().get("kind", "ondemand")
                self._send(200, json.dumps(do_digest(kind)))
            elif self.path == "/api/forget":
                self._send(200, json.dumps(do_forget()))
            else:
                self._send(404, json.dumps({"error": "not found"}))
        except Exception as e:
            self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}))


PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Proactive PA</title>
<style>
  :root{
    --bg:#0e1116; --panel:#161b22; --panel2:#1c232d; --line:#2a323d;
    --text:#e6edf3; --muted:#8b98a8; --accent:#6ea8fe; --accent2:#3fb950;
    --warn:#e3b341; --bubble-u:#214a8a; --bubble-a:#1c232d;
  }
  *{box-sizing:border-box} html,body{height:100%}
  body{margin:0;font:15px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
       background:var(--bg);color:var(--text);display:flex;flex-direction:column}
  header{display:flex;align-items:center;gap:12px;padding:12px 18px;border-bottom:1px solid var(--line);
         background:var(--panel)}
  header h1{font-size:16px;margin:0;font-weight:650;letter-spacing:.2px}
  header .dot{width:9px;height:9px;border-radius:50%;background:var(--accent2);box-shadow:0 0 8px var(--accent2)}
  header .sp{flex:1}
  header button{background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:8px;
         padding:7px 12px;font-size:13px;cursor:pointer}
  header button:hover{border-color:var(--accent);color:var(--accent)}
  header button.danger:hover{border-color:#f85149;color:#f85149}
  main{flex:1;display:flex;min-height:0}
  /* chat */
  .chat{flex:1;display:flex;flex-direction:column;min-width:0}
  #banner{margin:10px 14px 0;padding:0}
  #banner .alert{background:rgba(227,179,65,.12);border:1px solid rgba(227,179,65,.4);color:#f0d68a;
        padding:8px 12px;border-radius:8px;font-size:13px;margin-bottom:6px}
  #log{flex:1;overflow-y:auto;padding:16px 14px;display:flex;flex-direction:column;gap:12px}
  .msg{max-width:78%;padding:10px 14px;border-radius:14px;white-space:normal;word-wrap:break-word}
  .msg.u{align-self:flex-end;background:var(--bubble-u);border-bottom-right-radius:4px}
  .msg.a{align-self:flex-start;background:var(--bubble-a);border:1px solid var(--line);border-bottom-left-radius:4px}
  .msg.a.digest{border-color:var(--accent);background:rgba(110,168,254,.08)}
  .msg h4{margin:.1em 0 .4em;font-size:14px;color:var(--accent)}
  .msg ul{margin:.3em 0;padding-left:1.2em} .msg li{margin:.15em 0}
  .msg code{background:#0c0f14;padding:1px 5px;border-radius:5px;font-size:13px}
  .typing{align-self:flex-start;color:var(--muted);font-size:13px;padding:4px 8px}
  form{display:flex;gap:10px;padding:12px 14px;border-top:1px solid var(--line);background:var(--panel)}
  #inp{flex:1;background:var(--panel2);border:1px solid var(--line);border-radius:10px;color:var(--text);
       padding:11px 14px;font-size:15px;resize:none;font-family:inherit;max-height:120px}
  #inp:focus{outline:none;border-color:var(--accent)}
  form button{background:var(--accent);color:#06101f;border:none;border-radius:10px;padding:0 18px;
       font-weight:650;cursor:pointer;font-size:15px}
  form button:disabled{opacity:.5;cursor:default}
  /* dashboard */
  aside{width:330px;border-left:1px solid var(--line);background:var(--panel);overflow-y:auto;padding:14px}
  aside h2{font-size:12px;text-transform:uppercase;letter-spacing:.7px;color:var(--muted);
        margin:18px 0 8px;font-weight:650}
  aside h2:first-child{margin-top:2px}
  .card{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:8px}
  .pill{display:inline-block;background:#0c0f14;border:1px solid var(--line);border-radius:20px;
        padding:3px 10px;font-size:12px;margin:0 4px 5px 0;color:var(--muted)}
  .streak{display:flex;justify-content:space-between;align-items:center;font-size:14px}
  .streak .n{color:var(--accent2);font-weight:700}
  .task{font-size:14px;margin:5px 0;display:flex;gap:6px}
  .task .due{color:var(--muted);font-size:12px;margin-left:auto;white-space:nowrap}
  .trend{font-size:13px;font-family:ui-monospace,Menlo,Consolas,monospace;color:var(--muted);margin:3px 0}
  .rem{font-size:13px;margin:4px 0}.rem .t{color:var(--muted);font-size:12px}
  .empty{color:var(--muted);font-size:13px;font-style:italic}
  .mood-big{font-size:26px;font-weight:700;color:var(--accent2)}
  /* toast */
  #toasts{position:fixed;bottom:18px;right:18px;display:flex;flex-direction:column;gap:8px;z-index:50}
  .toast{background:var(--panel2);border:1px solid var(--accent);border-radius:10px;padding:12px 16px;
        box-shadow:0 8px 24px rgba(0,0,0,.4);max-width:320px;animation:pop .25s ease}
  @keyframes pop{from{transform:translateY(10px);opacity:0}to{transform:none;opacity:1}}
  @media (max-width:760px){aside{display:none}}
</style></head>
<body>
<header>
  <span class="dot"></span><h1>Proactive PA</h1>
  <span style="color:var(--muted);font-size:12px">claude-opus-4-8 · local</span>
  <span class="sp"></span>
  <button onclick="digest('morning')">☀️ Briefing</button>
  <button onclick="digest('ondemand')">💡 Insights</button>
  <button class="danger" onclick="forget()">🗑 Reset</button>
</header>
<main>
  <section class="chat">
    <div id="banner"></div>
    <div id="log"></div>
    <form id="f">
      <textarea id="inp" rows="1" placeholder="Tell me about your day…  (e.g. 'ran 5k, remind me to call mom at 6pm')"></textarea>
      <button id="send" type="submit">Send</button>
    </form>
  </section>
  <aside id="dash"></aside>
</main>
<div id="toasts"></div>

<script>
const $ = s => document.querySelector(s);
const logEl = $('#log'), inp = $('#inp'), form = $('#f');

function mdToHtml(t){
  const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const lines = esc(t).split('\n'); let out=[], inList=false;
  for(let line of lines){
    let m;
    line = line.replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/`(.+?)`/g,'<code>$1</code>')
               .replace(/(?<!\w)\*(.+?)\*(?!\w)/g,'<i>$1</i>');
    if(m = line.match(/^\s*#{1,4}\s+(.*)/)){ if(inList){out.push('</ul>');inList=false;} out.push('<h4>'+m[1]+'</h4>'); continue; }
    if(m = line.match(/^\s*[-*•]\s+(.*)/)){ if(!inList){out.push('<ul>');inList=true;} out.push('<li>'+m[1]+'</li>'); continue; }
    if(inList){out.push('</ul>');inList=false;}
    out.push(line.trim()? '<div>'+line+'</div>' : '<div style="height:6px"></div>');
  }
  if(inList) out.push('</ul>');
  return out.join('');
}
function bubble(text, who, digest){
  const d = document.createElement('div');
  d.className = 'msg '+who+(digest?' digest':'');
  d.innerHTML = mdToHtml(text);
  logEl.appendChild(d); logEl.scrollTop = logEl.scrollHeight; return d;
}
function typing(){ const d=document.createElement('div'); d.className='typing'; d.textContent='PA is thinking…';
  logEl.appendChild(d); logEl.scrollTop=logEl.scrollHeight; return d; }

function renderDash(s){
  const dash = $('#dash'); let h='';
  h += '<h2>Profile</h2>';
  h += s.profile.length ? s.profile.map(f=>'<span class="pill">'+f+'</span>').join('') : '<div class="empty">nothing yet</div>';
  h += '<h2>🔥 Habits</h2>';
  h += s.habits.length ? s.habits.map(x=>'<div class="card streak"><span>'+x.name+'</span><span class="n">day '+x.streak+' <span style="color:var(--muted);font-weight:400">/ best '+x.best+'</span></span></div>').join('') : '<div class="empty">none tracked</div>';
  h += '<h2>✅ Open tasks</h2>';
  h += s.tasks.length ? '<div class="card">'+s.tasks.map(t=>'<div class="task"><span>•</span><span>'+t.task+'</span>'+(t.due?'<span class="due">'+t.due.slice(0,16).replace('T',' ')+'</span>':'')+'</div>').join('')+'</div>' : '<div class="empty">all clear</div>';
  if(s.trends.length){ h += '<h2>📈 Trends</h2><div class="card">'+s.trends.map(t=>'<div class="trend">'+t+'</div>').join('')+'</div>'; }
  if(s.mood){ h += '<h2>🙂 Mood (7d)</h2><div class="card"><span class="mood-big">'+s.mood.avg+'</span> <span style="color:var(--muted)">/10 · '+s.mood.count+' entries</span></div>'; }
  if(s.log.length){ h += '<h2>Recent log</h2><div class="card">'+s.log.slice().reverse().map(e=>'<div class="trend">['+e.category+'] '+e.key+(e.value!=null?': '+e.value+' '+(e.unit||''):'')+'</div>').join('')+'</div>'; }
  if(s.reminders.length){ h += '<h2>⏰ Reminders</h2><div class="card">'+s.reminders.map(r=>'<div class="rem">'+r.task+' <span class="t">· '+r.at+'</span></div>').join('')+'</div>'; }
  dash.innerHTML = h;

  const ban = $('#banner');
  ban.innerHTML = (s.alerts||[]).map(a=>'<div class="alert">'+a+'</div>').join('');
}

async function refresh(){ try{ renderDash(await (await fetch('/api/state')).json()); }catch(e){} }

function toast(msg){
  const t = document.createElement('div'); t.className='toast'; t.innerHTML='🔔 '+mdToHtml(msg);
  $('#toasts').appendChild(t); setTimeout(()=>t.remove(), 12000);
  if(window.Notification && Notification.permission==='granted') new Notification('PA reminder', {body:msg});
}
function scheduleReminder(task, seconds){
  if(seconds>0 && seconds < 24*3600){ setTimeout(()=>toast('⏰ '+task), seconds*1000); }
}

async function send(msg){
  bubble(msg,'u'); inp.value=''; inp.style.height='auto';
  $('#send').disabled=true; const t=typing();
  try{
    const r = await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg})});
    const d = await r.json(); t.remove();
    if(d.error){ bubble('⚠️ '+d.error,'a'); }
    else{
      bubble(d.reply,'a');
      renderDash(d.state);
      if(d.reminder){ scheduleReminder(d.reminder.task, d.reminder.seconds); }
    }
  }catch(e){ t.remove(); bubble('⚠️ '+e,'a'); }
  $('#send').disabled=false; inp.focus();
}
async function digest(kind){
  const t=typing();
  try{ const d = await (await fetch('/api/digest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind})})).json();
       t.remove(); bubble(d.text,'a',true); }
  catch(e){ t.remove(); bubble('⚠️ '+e,'a'); }
}
async function forget(){
  if(!confirm('Wipe everything I have tracked?')) return;
  const d = await (await fetch('/api/forget',{method:'POST'})).json();
  logEl.innerHTML=''; bubble("Fresh start — I've cleared everything. Tell me about your day 🙂",'a');
  renderDash(d.state);
}

form.addEventListener('submit', e=>{ e.preventDefault(); const v=inp.value.trim(); if(v) send(v); });
inp.addEventListener('keydown', e=>{ if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); form.requestSubmit(); }});
inp.addEventListener('input', ()=>{ inp.style.height='auto'; inp.style.height=Math.min(inp.scrollHeight,120)+'px'; });
if(window.Notification && Notification.permission==='default') Notification.requestPermission();

bubble("Hey Rohith 👋 I'm your proactive PA. Just tell me about your day — runs, tasks, deadlines, mood, anything — and I'll track it and reach out with insights. Try the **☀️ Briefing** and **💡 Insights** buttons up top.",'a');
refresh();
</script>
</body></html>"""


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Proactive PA web UI -> http://127.0.0.1:{PORT}")
    print(f"  user={WEB_USER_ID}  model={brain.MODEL}  proxy={brain.ANTHROPIC_BASE_URL}")
    print("  Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
