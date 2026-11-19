"""Axor backend: offline voice+text assistant. Run: python server.py  ->  http://localhost:8765"""
import integrations as ig
import mathsolve
import webtools as wt
import docgen as dg
import docreader
import skills_catalog as SK
import uuid
import os, re, json, hmac, hashlib, base64, secrets, ast, time, sqlite3, shutil, tempfile, threading, subprocess, operator, csv, io, urllib.request, urllib.parse
from datetime import datetime, timedelta, date
from flask import Flask, request, jsonify, send_from_directory, Response, g

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "axor.db")
IS_MAC = shutil.which("osascript") is not None
try:
    from dotenv import load_dotenv; load_dotenv(os.path.join(BASE, ".env"))
except Exception: pass
GROQ_KEY = os.getenv("GROQ_API_KEY", "")
OWNER = os.getenv("OWNER_NAME", "Jayanth")
app = Flask(__name__, static_folder="static")
lock = threading.Lock()
CUR = threading.local()
def uid(): return getattr(CUR, "uid", 0)
SECRET = (os.getenv("AXOR_SECRET") or secrets.token_hex(16)).encode()

def db():
    c = sqlite3.connect(DB, timeout=10); c.row_factory = sqlite3.Row; return c
def init():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, salt TEXT, pw TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, start TEXT, synced INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, user_id INTEGER, ts TEXT, source TEXT, command TEXT, response TEXT, category TEXT, ms INTEGER, ok INTEGER, synced INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY, user_id INTEGER, text TEXT, due TEXT, fired INTEGER DEFAULT 0, kind TEXT DEFAULT 'reminder', synced INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, user_id INTEGER, ts TEXT, text TEXT, synced INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS cloud(user_id INTEGER PRIMARY KEY, token TEXT);
        CREATE TABLE IF NOT EXISTS settings(user_id INTEGER, k TEXT, v TEXT, PRIMARY KEY(user_id,k));
        CREATE TABLE IF NOT EXISTS user_skills(user_id INTEGER, sid TEXT, enabled INTEGER DEFAULT 1, custom INTEGER DEFAULT 0, name TEXT, cat TEXT, descr TEXT, instr TEXT, PRIMARY KEY(user_id,sid));
        CREATE TABLE IF NOT EXISTS chat_titles(user_id INTEGER, conv TEXT, title TEXT, auto INTEGER DEFAULT 1, PRIMARY KEY(user_id,conv));""")
init()
def migrate():
    """Upgrade an older axor.db in place (safe to run every start)."""
    for col in ("conv TEXT", "att TEXT"):
        try:
            with db() as c: c.execute("ALTER TABLE history ADD COLUMN " + col)
        except Exception: pass
    with db() as c: c.execute("UPDATE history SET conv='old-'||substr(ts,1,10) WHERE conv IS NULL")
    split_legacy()
def split_legacy(gap_min=20):
    """Old rows were one blob per day (old-YYYY-MM-DD). Split each into sessions wherever there is a pause of gap_min minutes."""
    with db() as c:
        rows = c.execute("SELECT id,user_id,ts,conv FROM history WHERE length(conv)=14 AND conv LIKE 'old-____-__-__' ORDER BY user_id,ts,id").fetchall()
        last = {}; n = {}
        for r in rows:
            key = (r["user_id"], r["conv"])
            try: t = datetime.fromisoformat(r["ts"])
            except Exception: t = None
            if key not in last or (t and last[key] and (t - last[key]).total_seconds() > gap_min * 60): n[key] = n.get(key, 0) + 1
            if t: last[key] = t
            c.execute("UPDATE history SET conv=? WHERE id=?", (f"{r['conv']}-{n[key]}", r["id"]))
migrate()
for _t in ("history","reminders","events","notes"):
    try:
        with db() as _c: _c.execute(f"ALTER TABLE {_t} ADD COLUMN synced INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
for _t in ("reminders", "events"):
    try:
        with db() as _c: _c.execute(f"ALTER TABLE {_t} ADD COLUMN gcal_id TEXT")
    except sqlite3.OperationalError: pass
DEFAULTS = {"speak": "1", "voice": "Daniel", "browser": "Arc", "lang": "en", "cite": "1"}
def get_settings():
    s = dict(DEFAULTS)
    with db() as c:
        for r in c.execute("SELECT k,v FROM settings WHERE user_id=?", (uid(),)): s[r["k"]] = r["v"]
    return s

def sh(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout or r.stderr).strip()
    except Exception as e: return False, str(e)
def osa(script): return sh(["osascript", "-e", script])
def speak(text, voice):
    if IS_MAC and text:
        subprocess.Popen(["say", "-v", voice, text[:600]])
def lock_screen():
    """Lock the Mac: Control+Command+Q first, then CGSession, then display sleep (locks if a password is required)."""
    if not IS_MAC: return False
    ok, _ = osa('tell application "System Events" to keystroke "q" using {control down, command down}')
    if ok: return True
    cg = "/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession"
    if os.path.exists(cg):
        ok, _ = sh([cg, "-suspend"])
        if ok: return True
    ok, _ = sh(["pmset", "displaysleepnow"]); return ok
def notify(title, msg):
    if IS_MAC: osa(f'display notification {json.dumps(msg)} with title {json.dumps(title)} sound name "Glass"')
def online():
    try: urllib.request.urlopen("https://api.groq.com", timeout=2); return True
    except urllib.error.HTTPError: return True
    except Exception: return False

# ---------- helpers ----------
APPS = {"whatsapp":"WhatsApp","safari":"Safari","chrome":"Google Chrome","arc":"Arc","notes":"Notes","calendar":"Calendar",
 "mail":"Mail","messages":"Messages","music":"Music","spotify":"Spotify","terminal":"Terminal","vs code":"Visual Studio Code",
 "vscode":"Visual Studio Code","code":"Visual Studio Code","finder":"Finder","calculator":"Calculator","settings":"System Settings",
 "system settings":"System Settings","photos":"Photos","telegram":"Telegram","facetime":"FaceTime","reminders":"Reminders",
 "clock":"Clock","maps":"Maps","preview":"Preview","zoom":"zoom.us","slack":"Slack","word":"Microsoft Word","excel":"Microsoft Excel",
 "powerpoint":"Microsoft PowerPoint","discord":"Discord","teams":"Microsoft Teams","brave":"Brave Browser","firefox":"Firefox"}
SITES = {"youtube":"https://www.youtube.com","gmail":"https://mail.google.com","google":"https://www.google.com",
 "github":"https://github.com","linkedin":"https://www.linkedin.com","instagram":"https://www.instagram.com",
 "twitter":"https://x.com","x":"https://x.com","facebook":"https://www.facebook.com","netflix":"https://www.netflix.com",
 "chatgpt":"https://chatgpt.com","claude":"https://claude.ai","drive":"https://drive.google.com","maps":"https://maps.google.com",
 "vtop":"https://vtop.vitap.ac.in","vit":"https://vitap.ac.in","canva":"https://www.canva.com","amazon":"https://www.amazon.in"}
def open_url(url):
    b = get_settings()["browser"]
    ok, _ = sh(["open", "-a", b, url]) if IS_MAC else (False, "")
    if not ok: sh(["open", url])
    return ok

NUMW = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty five": 45, "sixty": 60}
_REL = re.compile(r"\b(?:in|after|within)\s+(?:the\s+|just\s+)?(?:(?:next|another|coming|about|around|extra)\s+)*(\d+(?:\.\d+)?|an?|half an?|" + "|".join(sorted(NUMW, key=len, reverse=True)) + r")\s*(second|sec|minute|min|hour|hr)s?\b|\b(\d+(?:\.\d+)?|an?|" + "|".join(NUMW) + r")\s*(second|sec|minute|min|hour|hr)s?\s+(?:from now|later)\b")
_MIRRORED = set()   # (user, text, due) already pushed to Google Calendar
CALCLAUSE = re.compile(r"[,.;]?\s*(?:and\s+|also\s+|please\s+)*(?:add|put|save|sync)(?:\s+(?:it|this|that))?\s+(?:in|to|on|into)\s+(?:my\s+)?(?:the\s+)?(?:go+gle\s+)?cal[a-z]{3,8}\b|[,.;]?\s*(?:and\s+)?(?:in|on)\s+(?:my\s+)?google\s+cal[a-z]{3,8}\b")
DELETE_RE = re.compile(r"\b(?:delete|remove|cancel|clear|undo|get rid of|take (?:it )?off)\b", re.I)
DEL_TARGET = re.compile(r"\b(?:reminders?|events?|tasks?|meetings?|birthday|it|that|this|those|cal[a-z]{3,8}|the one)\b", re.I)
DEL_OTHER = re.compile(r"\b(?:chat|chats|notes?|files?|messages?|history|account|folder|skill|skills|image|photo|draft)\b", re.I)
FOLLOWCAL = re.compile(r"\b(?:add|put|save|sync)\s+(?:it|this|that|the (?:reminder|task|event))\b|\b(?:add|put|save)\s+(?:it\s+)?(?:in|to|on|into)\s+(?:my\s+)?(?:go+gle\s+)?cal[a-z]{3,8}\b|\bin (?:my )?(?:go+gle )?cal[a-z]{3,8}\b")
def parse_when(t):
    now = datetime.now(); m = _REL.search(t)
    if m:
        w, u = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        n = 1 if w in ("a", "an") else 0.5 if w.startswith("half") else NUMW.get(w) or float(w)
        d = timedelta(seconds=n) if u.startswith("sec") else timedelta(minutes=n) if u.startswith("min") else timedelta(hours=n)
        return now + d, t.replace(m.group(0), "").strip()
    m = re.search(r"\b(?:at )?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", t) or re.search(r"\bat (\d{1,2})(?::(\d{2}))?()\b", t)
    if m:
        h = int(m.group(1)); mi = int(m.group(2) or 0); ap = (m.group(3) or "").replace(".", "")
        if ap == "pm" and h < 12: h += 12
        if ap == "am" and h == 12: h = 0
        dt = now.replace(hour=h % 24, minute=mi, second=0, microsecond=0)
        if "tomorrow" in t: dt += timedelta(days=1)
        elif dt <= now: dt += timedelta(days=1)
        return dt, t.replace(m.group(0), "").replace("tomorrow", "").strip()
    if "tomorrow" in t:
        return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0), t.replace("tomorrow","").strip()
    return None, t

OPS = {ast.Add:operator.add, ast.Sub:operator.sub, ast.Mult:operator.mul, ast.Div:operator.truediv, ast.Pow:operator.pow, ast.Mod:operator.mod, ast.USub:operator.neg}
def safe_eval(n):
    if isinstance(n, ast.Expression): return safe_eval(n.body)
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)): return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in OPS: return OPS[type(n.op)](safe_eval(n.left), safe_eval(n.right))
    if isinstance(n, ast.UnaryOp) and type(n.op) in OPS: return OPS[type(n.op)](safe_eval(n.operand))
    raise ValueError

def contact_phone(name):
    if not IS_MAC: return None
    ok, out = osa(f'tell application "Contacts" to get value of first phone of (first person whose name contains {json.dumps(name)})')
    if not ok: return None
    d = re.sub(r"[^\d+]", "", out)
    if len(d) == 10: d = "91" + d
    return d.lstrip("+") or None

_GROQ_MODELS = []   # chat models Groq says are available right now
_VISION = []
PREFER = ("llama-3.3-70b", "llama-3.1-70b", "gpt-oss-120b", "llama-4", "qwen", "llama-3.1-8b", "gpt-oss-20b", "llama")
SKIP = ("whisper", "guard", "tts", "playai", "distil-whisper", "compound", "prompt-guard", "safeguard", "orpheus")
VISION_HINTS = ("llama-4", "scout", "maverick", "vision", "-vl")
def _groq(path, body=None):
    req = urllib.request.Request("https://api.groq.com/openai/v1/" + path, json.dumps(body).encode() if body else None,
        {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json", "User-Agent": "axor/1.0"})
    return json.load(urllib.request.urlopen(req, timeout=60))
def _all_models():
    return [m["id"] for m in _groq("models")["data"] if m.get("active", True) and not any(k in m["id"].lower() for k in SKIP)]
def groq_models(vision=False):
    global _GROQ_MODELS, _VISION
    if not _GROQ_MODELS:
        ids = _all_models(); rank = lambda i: next((n for n, p in enumerate(PREFER) if p in i.lower()), len(PREFER))
        _GROQ_MODELS = sorted(ids, key=rank)[:4]; _VISION = [i for i in ids if any(h in i.lower() for h in VISION_HINTS)]
    return _VISION if vision else _GROQ_MODELS
def _chat(msgs, vision=False):
    """Try the available Groq models in turn. Returns (answer, error)."""
    if not GROQ_KEY: return None, "I can only run built-in commands right now. For open questions, add a Groq key to .env and connect to the internet."
    if not online(): return None, "You're offline, so I can only run built-in commands right now."
    try: models = groq_models(vision)
    except urllib.error.HTTPError as e:
        return None, "Groq rejected the API key (check GROQ_API_KEY in .env, no quotes or spaces)." if e.code in (401, 403) else f"Cloud AI error {e.code} while listing models."
    except Exception: return None, "Couldn't reach the cloud AI."
    if not models: return None, "No image-capable cloud model is available for this key." if vision else "No cloud model is available for this key."
    last = ""
    for model in list(models):
        try: return _groq("chat/completions", {"model": model, "messages": msgs, "temperature": 0.5})["choices"][0]["message"]["content"].strip(), None
        except urllib.error.HTTPError as e:
            last = f"{model}: {e.code} {e.read().decode(errors='ignore')[:120]}"; print("groq:", last)
            if e.code in (400, 404, 429):
                if e.code != 429 and model in models: models.remove(model)
                continue
            return None, f"Cloud AI error {e.code}."
        except Exception: return None, "Couldn't reach the cloud AI."
    return None, "The cloud AI didn't accept any model right now. " + last[:140]
def system_prompt():
    if getattr(CUR, "source", "text") == "voice":
        return f"You are Axor, a voice assistant for {OWNER}. Reply in plain spoken English, at most 3 short sentences. No markdown, no symbols, no LaTeX."
    return (f"You are Axor, a warm, quick and clear assistant for {OWNER}. Today is {datetime.now():%A, %d %B %Y}. Never invent facts about a specific real person, company or event. If you are not sure, say so plainly. Talk like a friendly, capable person: lead with the answer, then add detail only if it helps. Answer clearly. For math, science or technical answers give the full worked solution step by step. "
            "Write formulas in LaTeX using $...$ for inline and $$...$$ for display. Use Markdown for headings, lists and bold. Keep simple answers short. You are part of Axor, which CAN add reminders and Google Calendar events when the person gives a task with a date or time (for example: add dentist on friday at 10 am to my calendar, or remind me to call mom in 10 minutes). Never say you cannot create calendar events or reminders; if a detail is missing, ask for it in one short question. You cannot delete, edit or send anything yourself, so NEVER claim you deleted, removed, changed, sent or set something: only Axor's own command engine does that and reports it in its own message. If asked to do such an action and no result was shown, say plainly that it was not done." + skills_prompt())
MAX_ACTIVE = 5
def skills_prompt():
    try:
        with db() as c: rows = c.execute("SELECT sid,custom,name,instr FROM user_skills WHERE user_id=? AND enabled=1", (uid(),)).fetchall()
    except Exception: return ""
    parts = []
    for r in rows:
        if r["custom"]: parts.append(f"### {r['name']}\n{r['instr']}")
        elif r["sid"] in SK.BY_ID: parts.append(f"### {SK.BY_ID[r['sid']]['name']}\n{SK.BY_ID[r['sid']]['instructions']}")
    return ("\n\nThe user has switched on these skills. Follow them when the request fits; ignore a skill that does not apply to the current request:\n" + "\n\n".join(parts)) if parts else ""
def conv_context(n=8):
    cv = getattr(CUR, "conv", None)
    if not cv: return []
    with db() as c: rows = c.execute("SELECT command,response FROM history WHERE user_id=? AND conv=? AND ok=1 ORDER BY id DESC LIMIT ?", (uid(), cv, n)).fetchall()
    out = []
    for r in reversed(rows): out += [{"role": "user", "content": r["command"] or ""}, {"role": "assistant", "content": (r["response"] or "")[:1500]}]
    return out
FOLLOW = re.compile(r"^(yeah|yes|yep|yup|ok|okay|sure|please|more|and|also|go on|continue|give me|show me|do it|tell me more|why|how come)\b", re.I)
def search_query(raw):
    """Short follow-ups like 'yeah please give me' inherit the topic of the previous question so the web search is about the right thing."""
    if len(raw.split()) <= 6 and FOLLOW.match(raw.strip()):
        for m in reversed(conv_context(6)):
            if m["role"] == "user" and len(m["content"].split()) >= 3 and not FOLLOW.match(m["content"].strip()): return m["content"] + " " + raw
    return raw
def llm(q):
    return _chat([{"role": "system", "content": system_prompt()}] + conv_context() + [{"role": "user", "content": q}])


# ---------- Hindi / Hinglish -> canonical English commands ----------
H_OPEN = r"(?:khol do|kholo|khol dijiye|खोलो|खोल दो|खोलिए|chalu karo|शुरू करो)"
H_CLOSE = r"(?:band karo|band kar do|बंद करो|बंद कर दो)"
H_RULES = [(r"^(?:namaste|namaskar|नमस्ते|नमस्कार)$", "hello"), (r"(?:samay kya hai|abhi kitne baje|kitne baje hain|टाइम क्या है|समय क्या है|कितने बजे)", "what time is it"),
 (r"(?:aaj ki tarikh|aaj kya tarikh|आज की तारीख|आज क्या तारीख)", "what's today's date"), (r"(?:awaaz badhao|volume badhao|आवाज़ बढ़ाओ|आवाज बढ़ाओ)", "volume up"),
 (r"(?:awaaz kam karo|volume kam karo|आवाज़ कम करो|आवाज कम करो)", "volume down"), (r"(?:screenshot lo|screenshot le lo|स्क्रीनशॉट लो)", "take a screenshot"), (r"(?:mute karo|म्यूट करो)", "mute")]
def hindi_norm(t):
    for pat, out in H_RULES:
        if re.search(pat, t): return out
    m = re.match(r"(.+?)\s+" + H_OPEN + r"$", t)
    if m: return "open " + m.group(1).strip()
    m = re.match(r"(.+?)\s+" + H_CLOSE + r"$", t)
    if m: return "close " + m.group(1).strip()
    return t

# ---------- command engine: returns (category, response, ok) ----------
def delete_item(t):
    """Delete the reminder or event the person means (the latest one, or the one whose words match), here and in Google Calendar."""
    words = [w for w in re.findall(r"[a-z]{3,}", DELETE_RE.sub(" ", t)) if w not in {"the", "reminder", "reminders", "event", "events", "task", "tasks", "from", "google", "calendar", "caledar", "that", "this", "please", "and", "also", "which", "added", "meeting", "one", "can", "you", "again", "still", "there", "not", "yet", "now", "just", "off", "set"}]
    want_event = bool(re.search(r"\b(events?|meetings?|birthday)\b", t)) and not re.search(r"\breminders?\b", t)
    with db() as c:
        rows = [("reminders", r) for r in c.execute("SELECT id,text,due,gcal_id FROM reminders WHERE user_id=? AND kind='reminder' ORDER BY id DESC LIMIT 15", (uid(),)).fetchall()]
        evs = [("events", r) for r in c.execute("SELECT id,title AS text,start AS due,gcal_id FROM events WHERE user_id=? ORDER BY id DESC LIMIT 15", (uid(),)).fetchall()]
    pool = (evs + rows) if want_event else (rows + evs)
    pick = next((x for x in pool if words and any(w in (x[1]["text"] or "").lower() for w in words)), None) or (pool[0] if pool and not words else None)
    if not pick:
        return "calendar", ("I couldn't find a reminder or event called that. I can only delete things I added." if words else "There's no reminder or event of mine to delete."), False
    tbl, r = pick; title = r["text"]; due = datetime.fromisoformat(r["due"]); gone = None
    if ig.google_connected() and online():
        try:
            if r["gcal_id"]: ig.calendar_delete(r["gcal_id"]); gone = 1
            else: gone = ig.calendar_delete_matching(title, due)
        except Exception as e: return "calendar", f"I couldn't reach Google Calendar to delete '{title}': {e}. Nothing was removed.", False
    with db() as c: c.execute(f"DELETE FROM {tbl} WHERE id=?", (r["id"],))
    for k in [k for k in _MIRRORED if k[0] == uid() and k[1] == title]: _MIRRORED.discard(k)
    when = f"{due:%a %d %b %I:%M %p}"
    if not (ig.google_connected() and online()): return "calendar", f"Deleted '{title}' ({when}) from Axor. I'm not connected to Google, so I couldn't touch Google Calendar.", True
    if gone: return "calendar", f"Deleted '{title}' ({when}) from Axor and from Google Calendar. Refresh the calendar to see it disappear.", True
    return "calendar", f"Deleted '{title}' ({when}) from Axor. I couldn't find a matching event that Axor created in Google Calendar, so if one is still there, delete it by hand (open it, then Delete).", True
def run_command(raw):
    t = raw.lower().strip().rstrip(".!?")
    t = re.sub(r"^(hey |hi |ok |okay )?axor[, ]*", "", t).replace("please", "").strip()
    t = hindi_norm(t)
    s = get_settings()
    if not t and re.search(r"\baxor\b", raw.lower()): return "chat", f"Yes {OWNER}? I'm listening.", True
    if not t: return "system", "I didn't catch anything.", False
    if re.fullmatch(r"(hi|hello|hey|yo|good (morning|afternoon|evening|night))( there)?", t): return "chat", f"Hello {OWNER}! What can I do for you?", True
    if "who are you" in t or "your name" in t: return "chat", "I'm Axor, your local voice assistant. Speech recognition runs on your Mac, offline.", True
    if re.search(r"\b(thank you|thanks)\b", t): return "chat", "Anytime.", True
    # time/date
    if re.search(r"\bwhat('?s| is)( the)? time|\bwhat time\b|\btell me the time\b|\bthe time\b|\btime now\b|^time$|current time", t): return "info", datetime.now().strftime("It's %I:%M %p."), True
    if re.search(r"\b(date|day) (is it|today)|today'?s date|what day", t): return "info", datetime.now().strftime("Today is %A, %d %B %Y."), True
    # battery
    if "battery" in t:
        ok, o = sh(["pmset", "-g", "batt"]); m = re.search(r"(\d+)%", o)
        chg = " and charging" if re.search(r"AC Power|charging", o) and "discharging" not in o else ""
        return "system", (f"Battery is at {m.group(1)} percent{chg}." if m else "I couldn't read the battery."), bool(m)
    # calculator
    m = re.match(r"(?:calculate|what is|what's|compute)?\s*([\d\.\s\+\-\*/x%\(\)\^]+|[\d\.\s]+(?:plus|minus|times|divided by|multiplied by|into)[\w\.\s]+)$", t)
    if m and re.search(r"\d", t) and re.search(r"[\+\-\*/x%\^]|plus|minus|times|divided|multiplied|into", t):
        e = m.group(1)
        for a, b in (("plus","+"),("minus","-"),("multiplied by","*"),("times","*"),("divided by","/"),("into","*"),("x","*"),("^","**")): e = e.replace(a, b)
        try:
            v = safe_eval(ast.parse(e.strip(), mode="eval")); v = round(v, 6)
            return "calc", f"{e.strip()} = {int(v) if v == int(v) else v}", True
        except Exception: pass
    # volume
    m = re.search(r"(?:set )?volume (?:to )?(\d+)", t)
    if m:
        v = max(0, min(100, int(m.group(1)))); osa(f"set volume output volume {v}"); return "system", f"Volume set to {v}.", True
    if re.search(r"\b(mute)\b", t): osa("set volume output muted true"); return "system", "Muted.", True
    if "unmute" in t: osa("set volume output muted false"); return "system", "Unmuted.", True
    if re.search(r"volume up|louder|increase volume", t):
        osa("set volume output volume ((output volume of (get volume settings)) + 15)"); return "system", "Volume up.", True
    if re.search(r"volume down|quieter|decrease volume|lower volume", t):
        osa("set volume output volume ((output volume of (get volume settings)) - 15)"); return "system", "Volume down.", True
    # screenshot
    if "screenshot" in t or "screen shot" in t:
        p = os.path.expanduser(f"~/Desktop/Axor_{datetime.now():%Y%m%d_%H%M%S}.png"); ok, _ = sh(["screencapture", "-x", p])
        extra = ""
        if ok and ig.cloudinary_configured() and online():
            try:
                url = ig.cloudinary_upload(p); extra = " Uploaded: " + url
                try:
                    with db() as c: tk = c.execute("SELECT token FROM cloud WHERE user_id=?", (uid(),)).fetchone()
                    if tk: cloud_req("/api/files/upload", {"name": os.path.basename(p), "url": url}, tk["token"])
                except Exception: pass
            except Exception as e: extra = " (Cloud upload failed.)"
        return "system", (("Screenshot saved to your Desktop." + extra) if ok else "Screenshot failed. Allow Screen Recording for your terminal."), ok
    if re.search(r"\block\b.{0,25}\b(screen|mac|macbook|laptop|computer|pc|system|it)\b|^lock( now| up)?$", t):
        ok = lock_screen(); return "system", ("Locking your Mac." if ok else "I couldn't lock the screen. Allow Accessibility for your terminal in System Settings."), ok
    # "it's still there" right after a delete: look again in Google Calendar and say honestly what happened
    if re.search(r"\b(still|not|nt|never|hasn'?t|didn'?t|isn'?t|wasn'?t)\b.{0,30}\b(there|deleted|removed|gone|showing|appear\w*|updated)\b", t) and not DELETE_RE.search(t):
        with db() as c: lastr = c.execute("SELECT response FROM history WHERE user_id=? AND conv=? ORDER BY id DESC LIMIT 1", (uid(), getattr(CUR, "conv", None))).fetchone()
        mm = re.match(r"Deleted '(.+?)'", (lastr["response"] if lastr else "") or "")
        if mm:
            if not (ig.google_connected() and online()): return "calendar", "I can't reach Google Calendar right now, so I can't check. Pull down to refresh the calendar, or delete the event by hand.", False
            try: n = ig.calendar_delete_matching(mm.group(1), datetime.now(), hours=96)
            except Exception as e: return "calendar", f"I couldn't reach Google Calendar: {e}", False
            return "calendar", (f"Found and deleted {n} more matching event{'s' if n != 1 else ''} that Axor had created. Pull down to refresh your calendar." if n else "I can't find any more events that Axor created with that name. Pull down to refresh the calendar. If one still shows, it wasn't made by Axor or is on another calendar, so delete it by hand (open it, then Delete)."), True
    # delete a reminder / calendar event that Axor created
    if DELETE_RE.search(t) and DEL_TARGET.search(t) and not DEL_OTHER.search(t):
        return delete_item(t)
    # google (gmail + calendar), selenium
    if re.search(r"\b(connect|link|sign in (to|with)|log in (to|with)) (to )?google\b", t):
        if not ig.google_configured(): return "google", "Google isn't set up yet. Put credentials.json from Google Cloud Console in the Axor folder. See SETUP.md.", False
        threading.Thread(target=lambda: notify("Axor", ig.google_connect()[1]), daemon=True).start()
        return "google", "Opening Google sign-in in your browser. Approve access and I'll be connected.", True
    if (re.search(r"\b(calendar|agenda|schedule)\b", t) or re.search(r"\b(planned|events?|meetings?)\b.{0,40}\b(today|tomorrow|yesterday|week|date|on|my)\b", t)) \
            and not re.search(r"\b(add|schedule a|set up|create|book|remind|open|launch)\b", t) and not dg.is_event_request(raw):
        if not ig.google_connected(): return "google", "I'm not connected to Google Calendar yet. Say 'connect Google' first.", False
        try:
            d0, n, lab = dg.parse_day(t); ev = ig.calendar_agenda(d0, n)
            if not ev: return "google", f"Nothing on your calendar {lab}.", True
            if n == 1: return "google", f"You have {len(ev)} thing{'s' if len(ev) != 1 else ''} {lab}: " + "; ".join(f"{w}, {x}" for _, w, x in ev) + ".", True
            return "google", f"Your calendar {lab}:\n\n" + "\n".join(f"- **{dd:%a %d %b}**, {w}: {x}" for dd, w, x in ev), True
        except Exception as e: return "google", f"I couldn't reach Google Calendar: {e}", False
    if re.search(r"(read|check|any|new|unread|show|summari[sz]e).{0,25}\b(e-?mails?|mail|inbox|gmail)\b", t) and not re.search(r"open (gmail|mail)", t):
        if not ig.google_connected(): return "google", "I'm not connected to Gmail yet. Say 'connect Google' first.", False
        try: return "google", ig.gmail_summary(5, lambda q: llm(q)[0] if online() else None), True
        except Exception as e: return "google", f"I couldn't reach Gmail: {e}", False
    m = re.search(r"(?:selenium|automat\w*)\b.*?\b(?:search|for|look up)\s+(?:for\s+)?(.+)", t) or re.match(r"search (.+?) (?:using|with|via|through) (?:selenium|automation)", t)
    if m:
        q = m.group(1).strip()
        try: res = ig.selenium_search(q, headless=False if IS_MAC else True)
        except Exception as e: return "automation", f"Browser automation failed: {str(e)[:120]}", False
        return "automation", (f"Top results for {q}: " + "; ".join(res[:3]) + ".") if res else f"I searched for {q} but found no results.", True
    # notes
    m = re.match(r"(?:take|make|add|write|save)(?: a)? note(?: that| to| saying)?[: ]*(.*)", t) or re.match(r"note (?:down )?(.*)", t)
    if m and m.group(1):
        txt = m.group(1).strip(); 
        with db() as c: c.execute("INSERT INTO notes(user_id,ts,text) VALUES(?,?,?)", (uid(), datetime.now().isoformat(timespec="seconds"), txt))
        if IS_MAC: osa(f'tell application "Notes" to make new note with properties {{name:"Axor note", body:{json.dumps(txt)}}}')
        return "notes", f"Noted: {txt}", True
    if re.search(r"(read|show|list) (my )?notes", t):
        with db() as c: rows = c.execute("SELECT text FROM notes WHERE user_id=? ORDER BY id DESC LIMIT 5", (uid(),)).fetchall()
        return "notes", ("Your latest notes: " + "; ".join(r["text"] for r in rows)) if rows else "You have no notes yet.", True
    # reminders / alarm / timer
    _t0 = t; t = CALCLAUSE.sub(" ", t).strip(" ,.")
    m = re.match(r"(?:(?:set|start) (?:a |an )?)?(reminder|alarm|timer)(?: for| to| me)?\s*(.*)", t) or re.match(r"remind me (?:to |about )?(.*)", t)
    if m:
        kind = m.group(1) if m.lastindex and m.group(1) in ("reminder", "alarm", "timer") else "reminder"
        body = m.group(2) if kind != "reminder" or t.startswith(("set", "reminder")) else m.group(1)
        if not t.startswith("remind me") and m.lastindex == 1: body = ""
        if kind == "timer": body = re.sub(r"^(for |in )?", "in ", body.strip())
        dt, rest = parse_when(t if t.startswith("remind") else body)
        rest = re.sub(r"^(remind me (to |about )?|set (a |an )?(reminder|alarm|timer) (for |to )?|reminder (to |for )?|alarm |timer )", "", rest).strip(" ,")
        rest = re.sub(r"^(?:that\s+)?(?:i\s+)?(?:have|need|want|got|am supposed)\s+to\s+|^(?:that|to|about)\s+", "", rest.strip(" ,.")).strip(" ,.")
        rest = re.sub(r"[.,;]?\s*(?:that is|i mean|sorry)\b.*$", "", rest, flags=re.I).strip(" ,.;")
        rest = (rest[:1].upper() + rest[1:]) if rest else ""
        rest = rest or ("Alarm" if kind == "alarm" else "Timer" if kind == "timer" else "Reminder")
        if not dt: return "reminder", "When should I remind you? Try: remind me to call mom in 10 minutes.", False
        rest = re.sub(r"\s+([.,;])", r"\1", rest).strip(" ,.;")
        with db() as c: rid = c.execute("INSERT INTO reminders(user_id,text,due,kind) VALUES(?,?,?,?)", (uid(), rest, dt.isoformat(timespec="seconds"), kind)).lastrowid
        msg = f"Okay, {kind} set for {dt:%I:%M %p, %d %b}: {rest}."
        if kind == "reminder" and ig.google_connected() and online():
            try:
                gid = ig.calendar_insert_id(rest, dt, 15, notes="Reminder set in Axor", remind_at_start=True); _MIRRORED.add((uid(), rest, dt.isoformat(timespec="minutes")))
                with db() as c: c.execute("UPDATE reminders SET gcal_id=? WHERE id=?", (gid, rid))
                msg += " Also added to your Google Calendar."
            except Exception as e: print("google calendar:", e)
        return "reminder", msg, True
    t = _t0
    # "add it to google calendar" / "add it for thu 19 nov 1:18 am": refers to the reminder or event we just talked about
    if FOLLOWCAL.search(t) and not re.search(r"\bnotes?\b", t):
        with db() as c:
            last = c.execute("SELECT category FROM history WHERE user_id=? AND conv=? ORDER BY id DESC LIMIT 1", (uid(), getattr(CUR, "conv", None))).fetchone()
            item = c.execute("SELECT id,text,due FROM reminders WHERE user_id=? AND kind='reminder' ORDER BY id DESC LIMIT 1", (uid(),)).fetchone()
        if re.search(r"cal[a-z]{3,8}\b", t) or (last and last["category"] in ("calendar", "reminder")):
            ev = dg.parse_event(raw)
            if item or ev:
                if not ig.google_connected(): return "calendar", "I'm not connected to Google Calendar yet. Say 'connect Google' first.", False
                if not online(): return "calendar", "I need internet to reach Google Calendar. Try again when you're online.", False
                title = item["text"] if item else (ev["title"] if ev else "Reminder")
                dt = ev["start"] if ev else datetime.fromisoformat(item["due"]); allday = bool(ev and ev["all_day"])
                key = (uid(), title, dt.isoformat(timespec="minutes"))
                if key in _MIRRORED: return "calendar", f"'{title}' is already in your Google Calendar for {dt:%a %d %b}" + ("" if allday else f" at {dt:%I:%M %p}") + ". Check the calendar you have open (My calendar) and refresh it.", True
                try:
                    gid = ig.calendar_insert_id(title, dt, 15, all_day=allday, notes="Added by Axor from your reminder", remind_at_start=True); _MIRRORED.add(key)
                    if item and not ev:
                        with db() as c: c.execute("UPDATE reminders SET gcal_id=? WHERE id=?", (gid, item["id"]))
                except Exception as e: return "calendar", f"I couldn't reach Google Calendar: {e}", False
                return "calendar", f"Added '{title}' to Google Calendar for {dt:%a %d %b}" + ("" if allday else f" at {dt:%I:%M %p}") + ".", True
    # add an event / task / birthday to the calendar from plain words
    if dg.is_event_request(raw):
        ev = dg.parse_event(raw)
        if ev:
            title, dt = ev["title"], ev["start"]; mins = int((ev["end"] - dt).total_seconds() // 60)
            when = f"{dt:%a %d %b}" + ("" if ev["all_day"] else f" at {dt:%I:%M %p}")
            with db() as c: eid = c.execute("INSERT INTO events(user_id,title,start) VALUES(?,?,?)", (uid(), title, dt.isoformat(timespec="minutes"))).lastrowid
            if ig.google_connected() and online():
                try:
                    gid = ig.calendar_insert_id(title, dt, mins, all_day=ev["all_day"], repeat=ev["repeat"], notes="Added by Axor from: " + ev["notes"], remind_at_start=ev["remind"])
                    with db() as c: c.execute("UPDATE events SET gcal_id=? WHERE id=?", (gid, eid))
                    return "calendar", f"Added '{title}' to Google Calendar for {when}." + (" It repeats every year." if ev["repeat"] else ""), True
                except Exception as e: print("google calendar:", e)
            f = lambda d: d.strftime("%Y%m%dT%H%M%S"); os.makedirs(os.path.join(BASE, "meetings"), exist_ok=True)
            p = os.path.join(BASE, "meetings", f"meeting_{dt:%Y%m%d_%H%M}.ics")
            times = f"DTSTART;VALUE=DATE:{dt:%Y%m%d}\r\nDTEND;VALUE=DATE:{dt + timedelta(days=1):%Y%m%d}" if ev["all_day"] else f"DTSTART:{f(dt)}\r\nDTEND:{f(ev['end'])}"
            ics = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Axor//EN\r\nBEGIN:VEVENT\r\nUID:" + secrets.token_hex(8) + "@axor\r\nDTSTAMP:" + f(datetime.utcnow()) + "Z\r\n" + times + "\r\nSUMMARY:" + title.replace(",", " ") + ("\r\nRRULE:FREQ=YEARLY" if ev["repeat"] else "") + "\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
            open(p, "w").write(ics); ok, _ = sh(["open", "-a", "Calendar", p]) if IS_MAC else (False, "")
            return "calendar", f"Added '{title}' for {when}. " + ("It's in your Calendar app. Say 'connect Google' to put it in Google Calendar too." if ok else "Saved as an .ics file in the meetings folder. Say 'connect Google' to add it to Google Calendar."), True
        if not re.search(r"\b(meeting|event|call)\b", t): return "calendar", "When should I add it? For example: add dentist on friday at 10 am to my calendar.", False
    # meeting
    if re.search(r"\b(schedule|set up|create|book|add)\b.*\b(meeting|event|call)\b", t):
        dt, rest = parse_when(t); dt = dt or (datetime.now() + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        m2 = re.search(r"(?:meeting|event|call)(?: with| about| for| called| named| on)?\s+(.+)", rest); title = (m2.group(1).strip() if m2 else "Meeting").title() or "Meeting"
        title = f"Meeting - {title}" if title != "Meeting" else "Meeting"
        f = lambda d: d.strftime("%Y%m%dT%H%M%S")
        url = "https://calendar.google.com/calendar/render?action=TEMPLATE&text=" + urllib.parse.quote(title) + f"&dates={f(dt)}/{f(dt + timedelta(hours=1))}"
        with db() as c: c.execute("INSERT INTO events(user_id,title,start) VALUES(?,?,?)", (uid(), title, dt.isoformat(timespec="minutes")))
        if ig.google_connected() and online():
            try:
                link = ig.calendar_insert(title, dt)
                with db() as c: c.execute("INSERT INTO events(user_id,title,start) VALUES(?,?,?)", (uid(), title, dt.isoformat(timespec="minutes")))
                return "calendar", f"Added '{title}' to Google Calendar on {dt:%d %b at %I:%M %p}.", True
            except Exception as e: print("google calendar:", e)
        os.makedirs(os.path.join(BASE, "meetings"), exist_ok=True); p = os.path.join(BASE, "meetings", f"meeting_{dt:%Y%m%d_%H%M}.ics")
        ics = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Axor//EN\r\nBEGIN:VEVENT\r\nUID:" + secrets.token_hex(8) + "@axor\r\nDTSTAMP:" + f(datetime.utcnow()) + "Z\r\nDTSTART:" + f(dt) + "\r\nDTEND:" + f(dt + timedelta(hours=1)) + "\r\nSUMMARY:" + title.replace(",", " ") + "\r\nBEGIN:VALARM\r\nTRIGGER:-PT10M\r\nACTION:DISPLAY\r\nDESCRIPTION:Axor\r\nEND:VALARM\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        open(p, "w").write(ics); ok, _ = sh(["open", "-a", "Calendar", p]) if IS_MAC else (False, "")
        if not ok and online(): open_url(url)
        return "calendar", f"Scheduled '{title}' on {dt:%d %b at %I:%M %p}. " + ("Added to your Calendar app (works offline)." if ok else "Saved as an .ics file in the meetings folder."), True
    # images: photos or generated artwork
    def _ctx():
        for m in reversed(conv_context(8)):
            if m["role"] == "user" and not wt.image_intent(m["content"]) and len(m["content"].split()) <= 12:
                tp = wt.topic_from(m["content"])
                if tp: return tp
        return None
    ii = wt.image_intent(raw, _ctx)
    if ii:
        if not online(): return "image", "Pictures need an internet connection. Everything else, including maths, reminders and apps, still works offline.", False
        return "image", wt.image_flow(*ii), True
    # whatsapp / message
    m = re.search(r"(?:send|text|message|whatsapp)(?: a)?(?: whatsapp)?(?: message)?(?: to)?\s+([a-z][a-z ]*?)\s+(?:saying|that says|that|say|message|:)\s+(.+)", t) or re.search(r"(?:message|whatsapp|text) ([a-z]+)$", t)
    if m and ("whatsapp" in t or "message" in t or "text" in t or t.startswith("send")):
        name = m.group(1).strip(); msg = m.group(2).strip() if m.lastindex > 1 else ""
        ph = contact_phone(name)
        if not ph: return "message", f"I couldn't find a phone number for {name} in your Contacts.", False
        url = f"whatsapp://send?phone={ph}&text={urllib.parse.quote(msg)}"; sh(["open", url])
        if msg:
            time.sleep(3.5); ok, _ = osa('tell application "System Events" to keystroke return')
            return "message", (f"WhatsApp message sent to {name.title()}: {msg}" if ok else f"Opened chat with {name.title()}; press Return to send. Enable Accessibility for auto-send."), True
        return "message", f"Opened WhatsApp chat with {name.title()}.", True
    # youtube / google search
    m = re.match(r"(?:play|search|watch)\s+(.+?)\s+(?:on|in)\s+youtube", t) or re.match(r"youtube (?:search )?(.+)", t)
    if m: open_url("https://www.youtube.com/results?search_query=" + urllib.parse.quote(m.group(1))); return "web", f"Searching YouTube for {m.group(1)}.", True
    m = re.match(r"(?:google|search(?: for)?|search google for|look up)\s+(.+)", t)
    if m: open_url("https://www.google.com/search?q=" + urllib.parse.quote(m.group(1))); return "web", f"Searching Google for {m.group(1)}.", True
    # close
    m = re.match(r"(?:close|quit|exit)\s+(.+)", t)
    if m:
        a = APPS.get(m.group(1).strip(), m.group(1).strip().title()); ok, _ = osa(f'tell application "{a}" to quit')
        return "apps", (f"Closed {a}." if ok else f"Couldn't close {a}."), ok
    # open
    m = re.match(r"(?:open|launch|start|go to)\s+(.+)", t)
    if m:
        x = m.group(1).strip().replace(" website", "").replace(" app", "")
        if x in SITES and x not in ("maps",): open_url(SITES[x]); return "web", f"Opening {x.title()} in {s['browser']}.", True
        if re.match(r"[\w\-]+\.[a-z]{2,}", x): open_url("https://" + x); return "web", f"Opening {x}.", True
        a = APPS.get(x, x.title()); ok, _ = sh(["open", "-a", a]); return "apps", (f"Opening {a}." if ok else f"I couldn't find an app called {x}."), ok
    # documents: assignments, essays, reports, letters -> a full editable document
    if dg.is_doc_request(raw) and online() and not getattr(CUR, "voice_only", False):
        ans, err = _chat([{"role": "system", "content": system_prompt() + " " + dg.DOC_PROMPT}] + conv_context() + [{"role": "user", "content": raw}])
        if ans:
            ans = re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", ans.strip())
            CUR.say = "I've written your document. It's on screen, and you can edit or download it."
            return "document", ans, True
        # offline math (SymPy)
    mr = mathsolve.solve_text(raw)
    if mr: CUR.say = mr["say"]; return "math", mr["md"], True
    # LLM fallback (web-grounded with citations when the question is factual)
    if s.get("cite", "1") == "1" and getattr(CUR, "source", "text") != "voice" and online() and (getattr(CUR, "web", False) or wt.wants_sources(search_query(raw))):
        sq = search_query(raw)
        try: src = wt.build_sources(sq)
        except Exception: src = []
        if src:
            ans, err = _chat([{"role": "system", "content": system_prompt() + " Web search results are provided as numbered sources. Use them for facts and cite with [1], [2] right after the claim. Only state facts the sources support. If they do not cover something, say you could not find it instead of guessing. Never invent employers, degrees, links, profiles or any other detail. Never reveal or guess home addresses, phone numbers, emails or other private details of private individuals; stick to what is publicly and professionally known."}]
                             + conv_context() + [{"role": "user", "content": "Question: " + sq + "\n\nSources:\n" + wt.sources_block(src)}])
            if ans: return "ai", wt.finish_with_sources(ans, src), True
    ans, err = llm(raw)
    return ("ai", ans, True) if ans else ("offline", err or "I don't know that one.", False)

def speakable(t):
    t = re.sub(r"\$\$.*?\$\$|\$[^$]*\$", " the formula ", t, flags=re.S); t = re.sub(r"[*#`_>|\\]", "", t)
    return re.sub(r"\s+", " ", t).strip()
def log_msg(cmd, source, cat, resp, ok, ms, conv, att=None):
    with db() as c: c.execute("INSERT INTO history(user_id,ts,source,command,response,category,ms,ok,conv,att) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (uid(), datetime.now().isoformat(timespec="seconds"), source, cmd, resp, cat, ms, int(ok), conv, att))
def say_out(resp, source):
    s = get_settings()
    if source == "voice" and s["speak"] == "1": speak(getattr(CUR, "say", None) or speakable(resp), s["voice"])
def ensure_title(conv, cmd, resp):
    """Name a chat after its first message at once; upgrade it with a short LLM title in the background when online."""
    u = uid()
    with db() as c:
        r = c.execute("SELECT title FROM chat_titles WHERE user_id=? AND conv=?", (u, conv)).fetchone()
        if r: return r["title"]
        title = wt.smart_title(cmd); c.execute("INSERT INTO chat_titles(user_id,conv,title,auto) VALUES(?,?,?,1)", (u, conv, title))
    if GROQ_KEY and online() and len(cmd) > 12:
        def job():
            try:
                CUR.uid = u; CUR.source = "text"; CUR.conv = None
                a, _ = _chat([{"role": "system", "content": "Write a 2 to 5 word title for this chat. Reply with the title only, no quotes, no punctuation at the end."},
                              {"role": "user", "content": f"User: {cmd[:300]}\nAssistant: {resp[:300]}"}])
                t = wt.clean_ai_title(a)
                if t:
                    with db() as c: c.execute("UPDATE chat_titles SET title=? WHERE user_id=? AND conv=? AND auto=1", (t, u, conv))
            except Exception as e: print("title:", e)
        threading.Thread(target=job, daemon=True).start()
    return title
def handle(cmd, source, conv=None):
    t0 = time.time(); conv = conv or uuid.uuid4().hex[:12]; CUR.conv = conv; CUR.source = source; CUR.say = None
    run_text = cmd
    try:   # a bare "in 10 minutes" answers an earlier "When should I remind you?"
        with db() as c: last = c.execute("SELECT command,response FROM history WHERE user_id=? AND conv=? ORDER BY id DESC LIMIT 1", (uid(), conv)).fetchone()
        if last and (last["response"] or "").startswith("When should I remind you") and not re.search(r"\bremind|reminder|alarm|timer\b", cmd, re.I) and parse_when(cmd.lower())[0]:
            run_text = (last["command"] or "") + " " + cmd
    except Exception: pass
    try: cat, resp, ok = run_command(run_text)
    except Exception as e: cat, resp, ok = "error", f"Something went wrong: {e}", False
    ms = int((time.time() - t0) * 1000); log_msg(cmd, source, cat, resp, ok, ms, conv); say_out(resp, source)
    title = ensure_title(conv, cmd, resp)
    return {"response": resp, "category": cat, "ok": ok, "ms": ms, "source": source, "conv": conv, "title": title}

# ---------- whisper ----------
_wm = None
def whisper():
    global _wm
    with lock:
        if _wm is None:
            from faster_whisper import WhisperModel; _wm = WhisperModel("base", device="cpu", compute_type="int8")
    return _wm
def loaded(): return _wm is not None


# ---------- offline-first cloud sync (SQLite -> Axor Cloud) ----------
CLOUD = os.getenv("AXOR_CLOUD_URL", "http://127.0.0.1:8080")
SYNC = {"last": None, "error": None}
def cloud_req(path, data=None, token=None, timeout=4):
    req = urllib.request.Request(CLOUD + path, json.dumps(data).encode() if data is not None else None, {"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
    return json.load(urllib.request.urlopen(req, timeout=timeout))
def cloud_link(user_id, username, password):
    """Log in to the cloud with the same credentials (register on first use). Silent if the cloud is unreachable."""
    try:
        try: tok = cloud_req("/api/auth/login", {"username": username, "password": password})["token"]
        except urllib.error.HTTPError as e:
            if e.code != 401: raise
            tok = cloud_req("/api/auth/register", {"username": username, "password": password})["token"]
        with db() as c: c.execute("INSERT OR REPLACE INTO cloud VALUES(?,?)", (user_id, tok))
        return True
    except Exception: return False
def cloud_link_retry(user_id, username, password, tries=20):
    for _ in range(tries):
        if cloud_link(user_id, username, password): return
        time.sleep(5)
def pending(user_id):
    with db() as c: return sum(c.execute(f"SELECT COUNT(*) FROM {t} WHERE user_id=? AND synced=0", (user_id,)).fetchone()[0] for t in ("history", "reminders", "events", "notes"))
def ext_login(username, password):
    try:
        if ig.firebase_configured(): ig.firebase_login(username, password)
    except Exception as e: print("firebase login:", e)
def ext_push(username, pay):
    try:
        if ig.firebase_configured() and username in ig._fb:
            for kind, rows in pay.items():
                try:
                    for x in rows: ig.firebase_push(username, kind, x["cid"], {k: v for k, v in x.items() if k != "cid"})
                except Exception as e: print(f"external sync (firebase {kind}):", e)
        if ig.supabase_configured():
            for kind, rows in pay.items():
                try: ig.supabase_push(username, kind, rows)
                except Exception as e: print(f"external sync (supabase {kind}):", e)
    except Exception as e: print("external sync:", e)
def sync_user(user_id, token):
    with db() as c:
        h = c.execute("SELECT * FROM history WHERE user_id=? AND synced=0 LIMIT 200", (user_id,)).fetchall()
        r = c.execute("SELECT * FROM reminders WHERE user_id=? AND synced=0 LIMIT 200", (user_id,)).fetchall()
        e = c.execute("SELECT * FROM events WHERE user_id=? AND synced=0 LIMIT 200", (user_id,)).fetchall()
        n = c.execute("SELECT * FROM notes WHERE user_id=? AND synced=0 LIMIT 200", (user_id,)).fetchall()
    if not (h or r or e or n): return
    pay = {"commands": [{"cid": f"{user_id}-h-{x['id']}", **{k: x[k] for k in ("ts", "source", "command", "response", "category", "ms", "ok")}} for x in h],
           "reminders": [{"cid": f"{user_id}-r-{x['id']}", "text": x["text"], "due": x["due"], "fired": x["fired"], "kind": x["kind"]} for x in r],
           "events": [{"cid": f"{user_id}-e-{x['id']}", "title": x["title"], "start": x["start"]} for x in e],
           "notes": [{"cid": f"{user_id}-n-{x['id']}", "ts": x["ts"], "text": x["text"]} for x in n]}
    with db() as c:
        cv = c.execute("""SELECT h.conv, COUNT(*) n, MAX(h.ts) last, (SELECT title FROM chat_titles t WHERE t.user_id=h.user_id AND t.conv=h.conv) title,
            (SELECT command FROM history x WHERE x.user_id=h.user_id AND x.conv=h.conv ORDER BY x.id LIMIT 1) first
            FROM history h WHERE h.user_id=? AND h.conv IS NOT NULL GROUP BY h.conv ORDER BY MAX(h.id) DESC LIMIT 100""", (user_id,)).fetchall()
    pay["conversations"] = [{"cid": f"{user_id}-c-{x['conv']}", "title": x["title"] or wt.smart_title(x["first"] or ""), "n": x["n"], "last": x["last"]} for x in cv]
    cloud_req("/api/sync", pay, token)
    with db() as c: un = c.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
    if un and (ig.firebase_configured() or ig.supabase_configured()): ext_push(un["username"], pay)
    with db() as c:
        for t, rs in (("history", h), ("reminders", r), ("events", e), ("notes", n)):
            for x in rs: c.execute(f"UPDATE {t} SET synced=1 WHERE id=?", (x["id"],))
def sync_all():
    with db() as c: users = c.execute("SELECT * FROM cloud").fetchall()
    for u in users:
        try: sync_user(u["user_id"], u["token"]); SYNC.update(last=datetime.now().isoformat(timespec="seconds"), error=None)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                with db() as c: c.execute("DELETE FROM cloud WHERE user_id=?", (u["user_id"],))
            SYNC["error"] = f"http {e.code}"
        except Exception as e: SYNC["error"] = "offline"
def sync_loop():
    while True:
        try: sync_all()
        except Exception as e: print("sync:", e)
        time.sleep(4)
threading.Thread(target=sync_loop, daemon=True).start()

# ---------- reminder scheduler ----------
def scheduler():
    while True:
        try:
            with db() as c:
                for r in c.execute("SELECT * FROM reminders WHERE fired=0 AND due<=?", (datetime.now().isoformat(timespec="seconds"),)).fetchall():
                    c.execute("UPDATE reminders SET fired=1, synced=0 WHERE id=?", (r["id"],))
                    notify("Axor " + r["kind"], r["text"]); CUR.uid = r["user_id"]; s = get_settings()
                    if s["speak"] == "1": speak(f"Reminder: {r['text']}", s["voice"])
        except Exception as e: print("scheduler:", e)
        time.sleep(3)
threading.Thread(target=scheduler, daemon=True).start()

# ---------- routes ----------
# ---------- auth: PBKDF2 password hashing + HMAC-signed tokens (stdlib only) ----------
def make_token(u): 
    p = base64.urlsafe_b64encode(json.dumps({"u": u, "exp": time.time() + 86400 * 7}).encode()).decode()
    return p + "." + hmac.new(SECRET, p.encode(), hashlib.sha256).hexdigest()
def check_token(t):
    try:
        p, sig = t.rsplit(".", 1)
        if not hmac.compare_digest(sig, hmac.new(SECRET, p.encode(), hashlib.sha256).hexdigest()): return None
        d = json.loads(base64.urlsafe_b64decode(p)); return d["u"] if d["exp"] > time.time() else None
    except Exception: return None
def hpw(pw, salt): return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 120000).hex()
OPEN = ("/api/signup", "/api/login", "/api/status")
@app.before_request
def guard():
    CUR.uid = 0
    if request.path.startswith("/api/") and request.path not in OPEN:
        u = check_token(request.headers.get("Authorization", "").replace("Bearer ", ""))
        if not u: return jsonify(error="auth"), 401
        CUR.uid = u
@app.post("/api/signup")
def api_signup():
    d = request.get_json(force=True); n = (d.get("username") or "").strip().lower(); p = d.get("password") or ""
    if not re.fullmatch(r"[a-z0-9_.]{3,20}", n): return jsonify(error="Username: 3-20 letters, numbers, . or _"), 400
    if len(p) < 6: return jsonify(error="Password must be at least 6 characters"), 400
    salt = secrets.token_hex(16)
    try:
        with db() as c: cur = c.execute("INSERT INTO users(username,salt,pw,created) VALUES(?,?,?,?)", (n, salt, hpw(p, salt), datetime.now().isoformat(timespec="seconds")))
    except sqlite3.IntegrityError: return jsonify(error="That username is taken"), 409
    threading.Thread(target=cloud_link_retry, args=(cur.lastrowid, n, p), daemon=True).start(); threading.Thread(target=ext_login, args=(n, p), daemon=True).start()
    return jsonify(token=make_token(cur.lastrowid), username=n)
@app.post("/api/login")
def api_login():
    d = request.get_json(force=True); n = (d.get("username") or "").strip().lower()
    with db() as c: r = c.execute("SELECT * FROM users WHERE username=?", (n,)).fetchone()
    if not r or not hmac.compare_digest(r["pw"], hpw(d.get("password") or "", r["salt"])): return jsonify(error="Wrong username or password"), 401
    threading.Thread(target=cloud_link_retry, args=(r["id"], n, d.get("password") or ""), daemon=True).start(); threading.Thread(target=ext_login, args=(n, d.get("password") or ""), daemon=True).start()
    return jsonify(token=make_token(r["id"]), username=n)
@app.get("/api/me")
def api_me():
    with db() as c: r = c.execute("SELECT username FROM users WHERE id=?", (uid(),)).fetchone()
    return jsonify(username=r["username"] if r else None)
@app.get("/api/integrations")
def api_integrations():
    return jsonify([
        {"name": "Google (Gmail + Calendar)", "state": "connected" if ig.google_connected() else ("ready" if ig.google_configured() else "not_set_up"), "hint": "Say 'connect Google'"},
        {"name": "Firebase (Auth + Firestore)", "state": "on" if ig.firebase_configured() else "not_set_up", "hint": "FIREBASE_API_KEY, FIREBASE_PROJECT_ID in .env"},
        {"name": "Supabase (Postgres)", "state": "on" if ig.supabase_configured() else "not_set_up", "hint": "SUPABASE_URL, SUPABASE_KEY in .env"},
        {"name": "Cloudinary (file storage)", "state": "on" if ig.cloudinary_configured() else "not_set_up", "hint": "CLOUDINARY_URL in .env"},
        {"name": "Browser automation (Selenium)", "state": "on", "hint": "Say 'search AI news using selenium'"}])
@app.get("/api/sync/status")
def api_sync_status():
    with db() as c: linked = c.execute("SELECT 1 FROM cloud WHERE user_id=?", (uid(),)).fetchone() is not None
    p = pending(uid())
    state = "not_linked" if not linked else ("offline" if SYNC["error"] == "offline" else ("synced" if p == 0 else "pending"))
    return jsonify(state=state, pending=p, last=SYNC["last"], cloud=CLOUD)
@app.post("/api/sync/now")
def api_sync_now():
    sync_all(); return api_sync_status()
@app.get("/api/events")
def api_events():
    with db() as c: return jsonify([dict(r) for r in c.execute("SELECT * FROM events WHERE user_id=? ORDER BY start", (uid(),))])
@app.delete("/api/events/<int:i>")
def api_ev_del(i):
    with db() as c: c.execute("DELETE FROM events WHERE id=? AND user_id=?", (i, uid()))
    return jsonify(ok=True)
@app.get("/api/notes")
def api_notes():
    with db() as c: return jsonify([dict(r) for r in c.execute("SELECT * FROM notes WHERE user_id=? ORDER BY id DESC", (uid(),))])

def _skill_rows():
    with db() as c: st = {r["sid"]: dict(r) for r in c.execute("SELECT * FROM user_skills WHERE user_id=?", (uid(),))}
    out = []
    for k in SK.CATALOG:
        r = st.get(k["id"]); out.append({"id": k["id"], "name": k["name"], "cat": k["cat"], "desc": k["desc"], "custom": False, "installed": bool(r), "enabled": bool(r and r["enabled"])})
    for r in st.values():
        if r["custom"]: out.append({"id": r["sid"], "name": r["name"], "cat": r["cat"] or "Custom", "desc": r["descr"], "custom": True, "installed": True, "enabled": bool(r["enabled"]), "instructions": r["instr"]})
    return out
def _active_count():
    with db() as c: return c.execute("SELECT COUNT(*) FROM user_skills WHERE user_id=? AND enabled=1", (uid(),)).fetchone()[0]
@app.get("/api/skills")
def api_skills(): return jsonify(skills=_skill_rows(), cats=SK.CATS + ["Custom"], limit=MAX_ACTIVE, active=_active_count())
@app.post("/api/skills")
def api_skill_create():
    d = request.get_json(force=True); name = (d.get("name") or "").strip()[:40]; desc = (d.get("desc") or "").strip()[:160]; instr = (d.get("instructions") or "").strip()[:2000]
    if len(name) < 2 or len(instr) < 10: return jsonify(error="Give the skill a name and at least a sentence of instructions."), 400
    sid = "c-" + uuid.uuid4().hex[:8]; on = 1 if _active_count() < MAX_ACTIVE else 0
    with db() as c: c.execute("INSERT INTO user_skills(user_id,sid,enabled,custom,name,cat,descr,instr) VALUES(?,?,?,1,?,?,?,?)", (uid(), sid, on, name, "Custom", desc or "Your own skill", instr))
    return jsonify(ok=True, id=sid, enabled=bool(on))
@app.post("/api/skills/<sid>/install")
def api_skill_install(sid):
    if sid not in SK.BY_ID: return jsonify(error="Unknown skill"), 404
    on = 1 if _active_count() < MAX_ACTIVE else 0
    with db() as c: c.execute("INSERT OR IGNORE INTO user_skills(user_id,sid,enabled,custom) VALUES(?,?,?,0)", (uid(), sid, on))
    return jsonify(ok=True, enabled=bool(on), note=None if on else f"Added, but {MAX_ACTIVE} skills are already on. Switch one off to use this one.")
@app.post("/api/skills/<sid>/toggle")
def api_skill_toggle(sid):
    want = 1 if request.get_json(force=True).get("enabled") else 0
    if want and _active_count() >= MAX_ACTIVE:
        with db() as c: cur = c.execute("SELECT enabled FROM user_skills WHERE user_id=? AND sid=?", (uid(), sid)).fetchone()
        if not cur or not cur["enabled"]: return jsonify(ok=False, error=f"You can have {MAX_ACTIVE} skills on at once. Switch one off first."), 409
    with db() as c: n = c.execute("UPDATE user_skills SET enabled=? WHERE user_id=? AND sid=?", (want, uid(), sid)).rowcount
    return (jsonify(ok=True, enabled=bool(want)) if n else (jsonify(error="Add the skill first"), 404))
@app.delete("/api/skills/<sid>")
def api_skill_remove(sid):
    with db() as c: c.execute("DELETE FROM user_skills WHERE user_id=? AND sid=?", (uid(), sid))
    return jsonify(ok=True)
@app.post("/api/notes")
def api_note_add():
    t = (request.get_json(force=True).get("text") or "").strip()
    if t:
        with db() as c: c.execute("INSERT INTO notes(user_id,ts,text) VALUES(?,?,?)", (uid(), datetime.now().isoformat(timespec="seconds"), t))
    return api_notes()
@app.delete("/api/notes/<int:i>")
def api_note_del(i):
    with db() as c: c.execute("DELETE FROM notes WHERE id=? AND user_id=?", (i, uid()))
    return jsonify(ok=True)
@app.post("/api/speak")
def api_speak():
    d = request.get_json(force=True) or {}
    if d.get("stop"):
        if IS_MAC: sh(["pkill", "say"])
        return jsonify(ok=True)
    txt = speakable(d.get("text") or "")
    if not (IS_MAC and txt): return jsonify(ok=False, mac=IS_MAC)
    if IS_MAC: sh(["pkill", "say"])
    speak(txt, get_settings()["voice"]); return jsonify(ok=True)
@app.route("/")
def index(): return send_from_directory(BASE, "index.html")
@app.post("/api/command")
def api_command():
    d = request.get_json(force=True); CUR.web = bool(d.get("web")); return jsonify(handle((d.get("text") or "").strip(), d.get("source", "text"), d.get("conv")))
@app.get("/api/gmail/unread")
def api_gmail_unread():
    if not ig.google_connected(): return jsonify(error="Google not connected"), 409
    try: return jsonify(ig.gmail_unread(5))
    except Exception as e: return jsonify(error=str(e)[:150]), 502
@app.post("/api/calendar/event")
def api_calendar_event():
    d = request.get_json(force=True); t = (d.get("title") or "").strip(); st = d.get("start")
    if not (t and st): return jsonify(error="title and start required"), 400
    if not ig.google_connected(): return jsonify(error="Google not connected"), 409
    try: return jsonify(ok=True, link=ig.calendar_insert(t, datetime.fromisoformat(st)))
    except Exception as e: return jsonify(error=str(e)[:150]), 502
@app.get("/api/chats")
def api_chats():
    q = request.args.get("q", "").strip()
    with db() as c:
        rows = c.execute("""SELECT h.conv, COUNT(*) n, MAX(h.id) last_id, MAX(h.ts) ts,
            (SELECT command FROM history x WHERE x.user_id=h.user_id AND x.conv=h.conv ORDER BY x.id LIMIT 1) first,
            (SELECT title FROM chat_titles t WHERE t.user_id=h.user_id AND t.conv=h.conv) title
            FROM history h WHERE h.user_id=? AND h.conv IS NOT NULL AND (?='' OR h.command LIKE ? OR h.response LIKE ?)
            GROUP BY h.conv ORDER BY last_id DESC LIMIT 80""", (uid(), q, f"%{q}%", f"%{q}%")).fetchall()
    out = []
    for r in rows:
        d = dict(r); d["title"] = d["title"] or wt.smart_title(d.pop("first") or ""); d.pop("first", None); out.append(d)
    return jsonify(out)
@app.put("/api/chats/<conv>")
def api_chat_rename(conv):
    t = (request.get_json(force=True).get("title") or "").strip()[:60]
    if not t: return jsonify(ok=False), 400
    with db() as c: c.execute("INSERT OR REPLACE INTO chat_titles(user_id,conv,title,auto) VALUES(?,?,?,0)", (uid(), conv, t))
    return jsonify(ok=True, title=t)
@app.post("/api/chats/<conv>/truncate")
def api_chat_truncate(conv):
    """Edit-a-message support: drop the n-th exchange and everything after it (n counts from 0)."""
    n = max(0, int((request.get_json(force=True) or {}).get("from", 0)))
    with db() as c: c.execute("DELETE FROM history WHERE id IN (SELECT id FROM history WHERE user_id=? AND conv=? ORDER BY id LIMIT -1 OFFSET ?)", (uid(), conv, n))
    return jsonify(ok=True)
@app.post("/api/docx")
def api_docx():
    d = request.get_json(force=True); md = (d.get("text") or "")[:200000]
    return Response(dg.make_docx(md), mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
@app.get("/api/chats/<conv>")
def api_chat_get(conv):
    with db() as c: rows = c.execute("SELECT id,ts,source,command,response,category,ms,ok,att FROM history WHERE user_id=? AND conv=? ORDER BY id", (uid(), conv)).fetchall()
    return jsonify([dict(r) for r in rows])
@app.delete("/api/chats/<conv>")
def api_chat_del(conv):
    with db() as c: c.execute("DELETE FROM history WHERE user_id=? AND conv=?", (uid(), conv)); c.execute("DELETE FROM chat_titles WHERE user_id=? AND conv=?", (uid(), conv))
    return jsonify(ok=True)

# ---------- attachments ----------
UPLOADS = os.path.join(BASE, "uploads"); MAXB = 8 * 1024 * 1024; MAXAV = 60 * 1024 * 1024
AV_EXT = {".mp3", ".mp4", ".m4a", ".wav", ".aac", ".ogg", ".oga", ".opus", ".flac", ".webm", ".mov", ".mkv", ".avi", ".m4v", ".wma", ".amr"}
TEXT_EXT = {".txt", ".md", ".csv", ".json", ".py", ".js", ".html", ".css", ".java", ".c", ".cpp", ".log", ".xml", ".yml", ".yaml", ".sql", ".ts", ".tsx", ".jsx", ".sh", ".ini", ".tex"}
def pdf_text(path):
    try:
        from pypdf import PdfReader; return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
    except Exception: pass
    if shutil.which("pdftotext"):
        try: return subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=30).stdout
        except Exception: pass
    return ""
def local_summary(name, text):
    lines = text.splitlines(); words = len(text.split()); out = f"**{name}**: {len(lines)} lines, {words} words."
    if name.lower().endswith(".csv") and lines:
        cols = [c.strip() for c in lines[0].split(",")]; out += f" CSV with {len(lines) - 1} rows and {len(cols)} columns: {', '.join(cols[:12])}."
    head = "\n".join(lines[:6])
    return out + (f"\n\nFirst lines:\n```\n{head[:600]}\n```" if head.strip() else "")
def transcribe_media(path, limit_s=900):
    """Offline speech-to-text for audio and video (Whisper decodes the audio track itself). Returns (text, seconds_covered, language)."""
    segs, info = whisper().transcribe(path, language=None, beam_size=1, vad_filter=True)
    out, end = [], 0
    for sg in segs:
        out.append(sg.text.strip()); end = sg.end
        if end > limit_s: break
    return " ".join(out).strip(), end, getattr(info, "language", "")
def analyze_file(path, name, mime, q):
    ext = os.path.splitext(name)[1].lower()
    if mime.startswith("image/"):
        if os.path.getsize(path) > 4 * 1024 * 1024: return "file", "That image is larger than 4 MB. Please attach a smaller one.", False
        data = "data:%s;base64,%s" % (mime, base64.b64encode(open(path, "rb").read()).decode())
        ans, err = _chat([{"role": "system", "content": system_prompt()}, {"role": "user", "content": [{"type": "text", "text": q or "Describe this image. If it contains a question or math problem, solve it step by step."}, {"type": "image_url", "image_url": {"url": data}}]}], vision=True)
        if ans: return "file", ans, True
        return "file", f"Saved {name}. Reading images needs the internet (a cloud vision model), so I can't look inside it right now. {err or ''}".strip(), False
    if ext in AV_EXT or mime.startswith(("audio/", "video/")):
        try: tx, secs, lang = transcribe_media(path)
        except ImportError: return "file", f"Saved {name}. Listening needs the speech engine (faster-whisper), which isn't installed here.", False
        except Exception as e: return "file", f"Saved {name}, but I couldn't listen to it ({type(e).__name__}). It may be damaged or use an unusual codec.", False
        kind = "video" if mime.startswith("video/") or ext in (".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm") else "audio"
        if not tx: return "file", f"Saved {name}. I listened to it but heard no speech" + (" (video frames can't be viewed, only the sound)." if kind == "video" else "."), False
        head = f"Transcript of {name} ({int(secs // 60)}:{int(secs % 60):02d}{', language: ' + lang if lang else ''}{'; sound only, I cannot see video frames' if kind == 'video' else ''})"
        ans, err = llm_file(q or "Summarize what is said: the main points, any decisions, names, dates or action items.", name, head + "\n\n" + tx)
        if ans: return "file", ans + f"\n\n**Transcript**\n\n{tx[:6000]}" + ("..." if len(tx) > 6000 else ""), True
        return "file", f"**{head}**\n\n{tx[:6000]}\n\nI can't summarize it offline. {err or ''}".rstrip(), True
    text, note = docreader.read_text(path, name, pdf_text)
    if not text.strip() and not note:
        kind = "audio or video" if mime.startswith(("audio/", "video/")) else "this kind of file"
        return "file", f"Saved {name}. I can't read inside {kind}. I can read: {docreader.SUPPORTED_LABEL}", False
    if not text.strip(): return "file", f"Saved {name}. {note or 'I could not extract any text from it (it may be a scanned PDF or contain only pictures).'}", False
    ans, err = llm_file(q, name, text)
    pre = (note + "\n\n") if note else ""
    return ("file", pre + ans, True) if ans else ("file", pre + local_summary(name, text) + f"\n\nI can't analyse the contents offline. {err or ''}".rstrip(), True)
def llm_file(q, name, text):
    return _chat([{"role": "system", "content": system_prompt()}] + conv_context(4) + [{"role": "user", "content": f"{q or 'Summarize this file.'}\n\nFile: {name}\n---\n{text[:12000]}"}])
@app.post("/api/attach")
def api_attach():
    f = request.files.get("file"); q = (request.form.get("text") or "").strip(); conv = request.form.get("conv") or uuid.uuid4().hex[:12]
    if not f: return jsonify(error="no file"), 400
    isav = os.path.splitext(f.filename or "")[1].lower() in AV_EXT or (f.mimetype or "").startswith(("audio/", "video/"))
    cap = MAXAV if isav else MAXB; data = f.read(cap + 1)
    if len(data) > cap: return jsonify(error=f"File is larger than {cap // 1048576} MB."), 413
    name = re.sub(r"[^\w.\- ]", "_", os.path.basename(f.filename or "file"))[:80] or "file"
    d = os.path.join(UPLOADS, str(uid())); os.makedirs(d, exist_ok=True); path = os.path.join(d, f"{int(time.time())}_{name}"); open(path, "wb").write(data)
    mime = f.mimetype or "application/octet-stream"; t0 = time.time(); CUR.conv = conv; CUR.source = "text"; CUR.say = None
    cat, resp, ok = analyze_file(path, name, mime, q); ms = int((time.time() - t0) * 1000)
    log_msg(q, "text", cat, resp, ok, ms, conv, name)
    return jsonify(response=resp, category=cat, ok=ok, ms=ms, conv=conv, att=name)
@app.post("/api/transcribe")
def api_transcribe():
    f = request.files.get("audio")
    if not f: return jsonify(error="no audio"), 400
    p = tempfile.mktemp(suffix=".webm"); f.save(p); t0 = time.time()
    try:
        lang = {"en": "en", "hi": "hi"}.get(get_settings()["lang"])  # "auto" -> Whisper detects (English/Hindi mix)
        segs, _ = whisper().transcribe(p, language=lang, beam_size=1, vad_filter=True)
        text = " ".join(s.text.strip() for s in segs).strip()
    except Exception as e: return jsonify(error=str(e)), 500
    finally: os.path.exists(p) and os.remove(p)
    return jsonify(text=text, ms=int((time.time() - t0) * 1000))
@app.get("/api/history")
def api_history():
    q = request.args.get("q", ""); 
    with db() as c: rows = c.execute("SELECT * FROM history WHERE user_id=? AND (command LIKE ? OR response LIKE ?) ORDER BY id DESC LIMIT 500", (uid(), f"%{q}%", f"%{q}%")).fetchall()
    return jsonify([dict(r) for r in rows])
@app.get("/api/export")
def api_export():
    with db() as c: rows = c.execute("SELECT * FROM history WHERE user_id=? ORDER BY id", (uid(),)).fetchall()
    o = io.StringIO(); w = csv.writer(o); w.writerow(["id","time","source","command","response","category","ms","ok"])
    for r in rows: w.writerow([r[k] for k in ("id","ts","source","command","response","category","ms","ok")])
    return Response(o.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=axor_history.csv"})
@app.get("/api/analytics")
def api_analytics():
    now = datetime.now(); today = now.strftime("%Y-%m-%d"); wk = (now - timedelta(days=6)).strftime("%Y-%m-%d")
    with db() as c:
        tot = c.execute("SELECT COUNT(*) n, COALESCE(AVG(ms),0) a, COALESCE(SUM(ok),0) o FROM history WHERE user_id=?", (uid(),)).fetchone()
        cats = [dict(r) for r in c.execute("SELECT category, COUNT(*) n FROM history WHERE user_id=? GROUP BY category ORDER BY n DESC", (uid(),))]
        src = {r["source"]: r["n"] for r in c.execute("SELECT source, COUNT(*) n FROM history WHERE user_id=? GROUP BY source", (uid(),))}
        days = [dict(r) for r in c.execute("SELECT substr(ts,1,10) d, COUNT(*) n FROM history WHERE user_id=? GROUP BY d ORDER BY d DESC LIMIT 7", (uid(),))][::-1]
        td = c.execute("SELECT COUNT(*) FROM history WHERE user_id=? AND substr(ts,1,10)=?", (uid(), today)).fetchone()[0]
        wkn = c.execute("SELECT COUNT(*) FROM history WHERE user_id=? AND substr(ts,1,10)>=?", (uid(), wk)).fetchone()[0]
        hrs = [dict(r) for r in c.execute("SELECT substr(ts,12,2) h, COUNT(*) n FROM history WHERE user_id=? GROUP BY h ORDER BY n DESC LIMIT 1", (uid(),))]
        top = [dict(r) for r in c.execute("SELECT command, COUNT(*) n FROM history WHERE user_id=? AND command!='' GROUP BY lower(command) ORDER BY n DESC, id DESC LIMIT 5", (uid(),))]
        chats = c.execute("SELECT COUNT(DISTINCT conv) FROM history WHERE user_id=?", (uid(),)).fetchone()[0]
        fast = c.execute("SELECT COALESCE(AVG(ms),0) FROM history WHERE user_id=? AND category NOT IN ('ai','image')", (uid(),)).fetchone()[0]
        slow = c.execute("SELECT COALESCE(AVG(ms),0) FROM history WHERE user_id=? AND category IN ('ai','image')", (uid(),)).fetchone()[0]
        localn = c.execute("SELECT COUNT(*) FROM history WHERE user_id=? AND category NOT IN ('ai','image','offline')", (uid(),)).fetchone()[0]
        rem = c.execute("SELECT COUNT(*) FROM reminders WHERE user_id=? AND fired=0", (uid(),)).fetchone()[0]
        notes = c.execute("SELECT COUNT(*) FROM notes WHERE user_id=?", (uid(),)).fetchone()[0]
    n = tot["n"]
    return jsonify(total=n, avg_ms=round(tot["a"]), success=round(100 * tot["o"] / n) if n else 0, categories=cats, sources=src, days=days,
                   today=td, week=wkn, chats=chats, busiest_hour=(int(hrs[0]["h"]) if hrs and hrs[0]["h"] else None), top=top,
                   local_pct=round(100 * localn / n) if n else 0, local_ms=round(fast), cloud_ms=round(slow), open_reminders=rem, notes=notes)
@app.route("/api/reminders", methods=["GET", "POST"])
def api_reminders():
    with db() as c:
        if request.method == "POST":
            d = request.get_json(force=True); c.execute("INSERT INTO reminders(user_id,text,due,kind) VALUES(?,?,?,?)", (uid(), d["text"], d["due"], d.get("kind", "reminder")))
        return jsonify([dict(r) for r in c.execute("SELECT * FROM reminders WHERE user_id=? ORDER BY fired, due", (uid(),))])
@app.delete("/api/reminders/<int:i>")
def api_rem_del(i):
    with db() as c: c.execute("DELETE FROM reminders WHERE id=? AND user_id=?", (i, uid()))
    return jsonify(ok=True)
@app.patch("/api/reminders/<int:i>")
def api_rem_patch(i):
    d = request.get_json(force=True)
    with db() as c:
        if "done" in d: c.execute("UPDATE reminders SET fired=? WHERE id=? AND user_id=?", (1 if d["done"] else 0, i, uid()))
        if d.get("snooze"):
            r = c.execute("SELECT due FROM reminders WHERE id=? AND user_id=?", (i, uid())).fetchone()
            if r:
                try: base = max(datetime.fromisoformat(r["due"]), datetime.now())
                except Exception: base = datetime.now()
                c.execute("UPDATE reminders SET due=?, fired=0 WHERE id=? AND user_id=?", ((base + timedelta(minutes=int(d["snooze"]))).isoformat(timespec="minutes"), i, uid()))
    return jsonify(ok=True)
@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        with db() as c:
            for k, v in request.get_json(force=True).items():
                if k in DEFAULTS: c.execute("INSERT OR REPLACE INTO settings VALUES(?,?,?)", (uid(), k, str(v)))
    return jsonify(get_settings())
@app.get("/api/status")
def api_status():
    return jsonify(whisper_loaded=loaded(), online=online(), groq=bool(GROQ_KEY), mac=IS_MAC, owner=OWNER)

if __name__ == "__main__":
    threading.Thread(target=whisper, daemon=True).start()
    print("\n  Axor running ->  http://localhost:8765\n")
    app.run(host="127.0.0.1", port=8765, threaded=True)
