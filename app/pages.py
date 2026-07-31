"""HTML page builders for the admin panel and the web chat demo.

Plain f-string templates (no template engine) — kept out of app/main.py so
routing/logic stays readable.
"""
from app import config
from app.utils import resolve_media_url

_BASE_STYLE = """
body{font-family:system-ui,Segoe UI,Arial;margin:0;background:#0f1220;color:#e8e9f0}
.wrap{max-width:960px;margin:0 auto;padding:24px}
h1{font-size:20px} h2{font-size:16px;margin-top:28px}
.nav{display:flex;gap:14px;margin-bottom:18px}
.nav a{color:#9aa3ff;text-decoration:none;font-size:14px}
.nav a:hover{text-decoration:underline}
.ok{background:#173a2a;border:1px solid #2e7d52;padding:10px 14px;border-radius:8px;margin:12px 0}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:13px}
td,th{padding:8px;border-bottom:1px solid #262a40;text-align:left;vertical-align:middle}
th{color:#aeb2cc;font-weight:600}
form{background:#171a2e;padding:16px;border-radius:12px;margin-top:12px}
label{display:block;margin:8px 0 4px;font-size:13px;color:#aeb2cc}
input,select{width:100%;padding:9px;border-radius:8px;border:1px solid #2a2f4a;background:#0f1220;color:#fff;box-sizing:border-box}
button{margin-top:14px;padding:10px 18px;border:0;border-radius:8px;background:#5b6cff;color:#fff;font-weight:600;cursor:pointer}
small{color:#8a8fb0}
.badge{padding:3px 9px;border-radius:999px;font-size:12px;font-weight:600;color:#0f1220}
"""

_NAV = (
    '<div class="nav">'
    '<a href="/admin/leads">📊 Leads Dashboard</a>'
    '<a href="/admin/properties">🏠 Property Inventory</a>'
    '<a href="/demo" target="_blank">💬 Open Web Demo</a>'
    "</div>"
)


_VIDEO_EXT = (".mp4", ".mov", ".webm")

_PROPERTY_TYPES = [
    "1BHK", "2BHK", "3BHK", "4BHK+", "Studio", "Villa", "Plot/Land", "Farmhouse",
    "Shop", "Showroom", "Office Space", "Commercial Space", "Warehouse/Godown",
    "Industrial Shed", "PG/Hostel", "Other",
]


def _media_thumb_html(url: str) -> str:
    if url.lower().endswith(_VIDEO_EXT):
        return f'<video src="{url}" style="width:90px;height:70px;object-fit:cover;border-radius:6px" muted></video>'
    return f'<img src="{url}" alt="" style="width:90px;height:70px;object-fit:cover;border-radius:6px">'


def render_properties_page(rows: list[dict], message: str = "") -> str:
    cards = ""
    for p in rows:
        media = p.get("media") or ([resolve_media_url(p["image_url"])] if p.get("image_url") else [])
        thumbs = "".join(_media_thumb_html(resolve_media_url(u) or u) for u in media) or "—"
        thumbs_wrapped = f'<div style="display:flex;gap:4px;flex-wrap:wrap">{thumbs}</div>' if media else "—"
        cards += f"""<tr>
          <td>{thumbs_wrapped}</td>
          <td><b>{p.get('title','')}</b><br><small>{p.get('id','')}</small></td>
          <td>{p.get('type','')}</td>
          <td>{p.get('location','')}</td>
          <td>{p.get('price','')}</td>
          <td>{p.get('available','')}</td>
        </tr>"""

    type_options = "".join(f'<option value="{t}">{t}</option>' for t in _PROPERTY_TYPES)
    banner = f'<div class="ok">{message}</div>' if message else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{config.BUILDER_NAME} — Inventory</title>
    <style>{_BASE_STYLE}</style></head><body><div class="wrap">
    {_NAV}
    <h1>🏠 {config.BUILDER_NAME} — Property Inventory</h1>
    {banner}
    <h2>Add a property</h2>
    <form action="/admin/properties" method="post" enctype="multipart/form-data">
      <label>Title</label><input name="title" required placeholder="3BHK Apartment, Jagatpura">
      <label>Type</label>
      <select name="type" required>
        <option value="" disabled selected>Select type…</option>
        {type_options}
      </select>
      <label>Location</label><input name="location" placeholder="Jagatpura, Jaipur">
      <label>Price</label><input name="price" placeholder="₹60 lakh">
      <label>Available</label>
      <select name="available"><option value="yes">yes</option><option value="no">no</option></select>
      <label>Photos / Videos (multiple allowed)</label>
      <input type="file" name="photos" accept="image/*,video/mp4,video/quicktime,video/webm" multiple>
      <button type="submit">Add property</button>
    </form>
    <h2>Current inventory ({len(rows)})</h2>
    <table><tr><th>Media</th><th>Title</th><th>Type</th><th>Location</th><th>Price</th><th>Available</th></tr>
    {cards or '<tr><td colspan=6><small>No properties yet — add one above.</small></td></tr>'}
    </table>
    <p><small>Tip: you can also edit the <b>properties</b> tab in your Google Sheet directly — the
    <code>media_urls</code> column holds a list of links, or just paste one plain URL.</small></p>
    </div></body></html>"""


_SCORE_COLORS = {"HOT": "#ff6b6b", "WARM": "#f5c451", "COLD": "#8fa3c4"}


def render_leads_page(leads: list[dict]) -> str:
    rows_html = ""
    for lead in reversed(leads):  # newest first
        score = (lead.get("score") or "").strip()
        color = _SCORE_COLORS.get(score.upper(), "#3a3f5c")
        badge = f'<span class="badge" style="background:{color}">{score or "—"}</span>'
        last_msg = (lead.get("last_message") or "")[:60]
        updated = (lead.get("updated_at") or "")[:19].replace("T", " ")
        rows_html += f"""<tr>
          <td><b>{lead.get('name','') or '—'}</b><br><small>{lead.get('phone','')}</small></td>
          <td><small>{lead.get('source','')}</small></td>
          <td>{lead.get('status','')}</td>
          <td>{badge}</td>
          <td>{lead.get('stage','')}</td>
          <td>{lead.get('location_pref','')}</td>
          <td>{lead.get('property_type','')}</td>
          <td>{lead.get('budget','')}</td>
          <td>{lead.get('timeline','')}</td>
          <td><small>{last_msg}</small></td>
          <td><small>{updated}</small></td>
        </tr>"""

    return f"""<!doctype html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="8">
    <title>{config.BUILDER_NAME} — Leads Dashboard</title>
    <style>{_BASE_STYLE}
    table{{font-size:12px}}
    </style></head><body><div class="wrap">
    {_NAV}
    <h1>📊 {config.BUILDER_NAME} — Leads Dashboard</h1>
    <p><small>Auto-refreshes every 8s · {len(leads)} lead(s) total</small></p>
    <table><tr>
      <th>Lead</th><th>Source</th><th>Status</th><th>Score</th><th>Stage</th>
      <th>Location</th><th>Type</th><th>Budget</th><th>Timeline</th><th>Last message</th><th>Updated</th>
    </tr>
    {rows_html or '<tr><td colspan=11><small>No leads yet.</small></td></tr>'}
    </table>
    </div></body></html>"""


def render_demo_chat_page() -> str:
    builder = config.BUILDER_NAME
    return f"""<!doctype html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{builder} — Chat</title>
    <style>
      html,body{{height:100%;margin:0;font-family:Segoe UI,Helvetica,Arial,sans-serif}}
      body{{display:flex;flex-direction:column;background:#e5ddd5}}
      .header{{background:#075E54;color:#fff;padding:14px 16px;display:flex;align-items:center;gap:12px;box-shadow:0 1px 4px rgba(0,0,0,.3)}}
      .header .avatar{{width:38px;height:38px;border-radius:50%;background:#25D366;display:flex;align-items:center;justify-content:center;font-weight:700}}
      .header .title{{font-size:16px;font-weight:600}}
      .header .sub{{font-size:12px;opacity:.85}}
      #messages{{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:6px}}
      .bubble{{max-width:75%;padding:8px 12px;border-radius:8px;font-size:14px;line-height:1.35;box-shadow:0 1px 1px rgba(0,0,0,.15);white-space:pre-wrap}}
      .in{{align-self:flex-start;background:#fff;border-top-left-radius:2px}}
      .out{{align-self:flex-end;background:#dcf8c6;border-top-right-radius:2px}}
      .bubble img{{max-width:100%;border-radius:6px;margin-top:6px;display:block}}
      .typing{{align-self:flex-start;background:#fff;padding:8px 12px;border-radius:8px;font-size:13px;color:#888}}
      .inputbar{{display:flex;gap:8px;padding:10px;background:#f0f0f0}}
      .inputbar input{{flex:1;padding:11px 14px;border-radius:20px;border:1px solid #ccc;font-size:14px;outline:none}}
      .inputbar button{{background:#25D366;color:#fff;border:0;border-radius:50%;width:42px;height:42px;font-size:18px;cursor:pointer}}
      .chiprow{{align-self:flex-start;max-width:85%;display:flex;flex-wrap:wrap;gap:6px;margin-top:-2px}}
      .chip{{padding:7px 14px;border-radius:16px;border:1.5px solid #25D366;background:#fff;color:#075E54;font-size:13px;font-weight:600;cursor:pointer}}
      .chip:hover{{background:#e9fbf0}}
      #nameModal{{position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:10}}
      #nameModal .card{{background:#fff;padding:22px;border-radius:12px;width:280px;text-align:center}}
      #nameModal input{{width:100%;padding:10px;border-radius:8px;border:1px solid #ccc;margin:12px 0;box-sizing:border-box;font-size:14px}}
      #nameModal button{{width:100%;padding:10px;border:0;border-radius:8px;background:#25D366;color:#fff;font-weight:600;cursor:pointer;font-size:14px}}
      .demo-tag{{position:fixed;top:6px;right:10px;background:#000a;color:#fff;font-size:10px;padding:3px 8px;border-radius:6px;z-index:5}}
    </style></head><body>
    <div class="demo-tag">DEMO — not a real phone number</div>
    <div id="nameModal"><div class="card">
      <div style="font-size:32px">🏠</div>
      <h3 style="margin:8px 0">{builder}</h3>
      <p style="font-size:13px;color:#555;margin:0">Enter your name to start chatting with our property assistant.</p>
      <input id="nameInput" placeholder="Your name" autofocus>
      <button onclick="beginChat()">Start Chat</button>
    </div></div>
    <div class="header">
      <div class="avatar">🏠</div>
      <div><div class="title">{builder}</div><div class="sub">online · property assistant</div></div>
    </div>
    <div id="messages"></div>
    <div class="inputbar">
      <input id="msgInput" placeholder="Type a message" onkeydown="if(event.key==='Enter')send()">
      <button onclick="send()">➤</button>
    </div>
    <script>
      const SESSION_KEY = 'demo_session_id', NAME_KEY = 'demo_name';
      let sessionId = localStorage.getItem(SESSION_KEY);
      if (!sessionId) {{
        sessionId = 'sess-' + Date.now() + '-' + Math.random().toString(36).slice(2);
        localStorage.setItem(SESSION_KEY, sessionId);
      }}
      let userName = localStorage.getItem(NAME_KEY) || '';
      const messagesEl = document.getElementById('messages');
      const modal = document.getElementById('nameModal');

      const VIDEO_EXT = ['.mp4', '.mov', '.webm'];
      function isVideo(url) {{ return VIDEO_EXT.some(ext => url.toLowerCase().includes(ext)); }}

      function addBubble(text, who, mediaUrls) {{
        const div = document.createElement('div');
        div.className = 'bubble ' + who;
        div.textContent = text || '';
        for (const url of (mediaUrls || [])) {{
          if (!url) continue;
          const el = isVideo(url) ? document.createElement('video') : document.createElement('img');
          el.src = url;
          if (isVideo(url)) el.controls = true;
          div.appendChild(el);
        }}
        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }}

      function clearChips() {{
        const old = document.getElementById('chipRow');
        if (old) old.remove();
      }}

      function addChips(options) {{
        clearChips();
        if (!options || !options.length) return;
        const row = document.createElement('div');
        row.id = 'chipRow';
        row.className = 'chiprow';
        for (const opt of options) {{
          const btn = document.createElement('button');
          btn.className = 'chip';
          btn.textContent = opt;
          btn.onclick = () => {{ clearChips(); sendText(opt); }};
          row.appendChild(btn);
        }}
        messagesEl.appendChild(row);
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }}

      function showTyping() {{
        const t = document.createElement('div');
        t.className = 'typing'; t.id = 'typingIndicator'; t.textContent = 'typing…';
        messagesEl.appendChild(t);
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }}
      function hideTyping() {{
        const t = document.getElementById('typingIndicator');
        if (t) t.remove();
      }}

      async function beginChat() {{
        const val = document.getElementById('nameInput').value.trim();
        if (!val) return;
        userName = val;
        localStorage.setItem(NAME_KEY, userName);
        modal.style.display = 'none';
        showTyping();
        const res = await fetch('/demo/start', {{
          method: 'POST', headers: {{'Content-Type':'application/json'}},
          body: JSON.stringify({{session_id: sessionId, name: userName}})
        }});
        const data = await res.json();
        hideTyping();
        addBubble(data.reply_text, 'in');
        addChips(data.quick_replies);
      }}

      function send() {{
        const input = document.getElementById('msgInput');
        const text = input.value.trim();
        if (!text) return;
        input.value = '';
        sendText(text);
      }}

      async function sendText(text) {{
        clearChips();
        addBubble(text, 'out');
        showTyping();
        try {{
          const res = await fetch('/demo/chat', {{
            method: 'POST', headers: {{'Content-Type':'application/json'}},
            body: JSON.stringify({{session_id: sessionId, name: userName, message: text}})
          }});
          const data = await res.json();
          hideTyping();
          addBubble(data.reply_text, 'in', data.media_urls);
          addChips(data.quick_replies);
        }} catch (e) {{
          hideTyping();
          addBubble('(connection error, please try again)', 'in');
        }}
      }}

      async function restoreOrPrompt() {{
        if (!userName) {{ modal.style.display = 'flex'; return; }}
        const res = await fetch('/demo/history?session_id=' + encodeURIComponent(sessionId));
        const data = await res.json();
        if (!data.exists) {{ modal.style.display = 'flex'; return; }}
        modal.style.display = 'none';
        for (const turn of data.history) {{
          if (turn.role === 'user') addBubble(turn.content, 'out');
          else addBubble(turn.content, 'in');
        }}
      }}
      restoreOrPrompt();
    </script>
    </body></html>"""
