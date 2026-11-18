"""Axor integrations: Google (Gmail + Calendar via OAuth 2.0), Firebase (Auth + Firestore), Supabase (PostgREST),
Cloudinary (signed upload) and Selenium browser automation.  Every call needs YOUR credentials (see SETUP.md);
without them each function returns a clear message instead of failing.  Pure standard library except Selenium."""
import os, re, json, time, hmac, base64, hashlib, secrets, threading, urllib.request, urllib.parse, urllib.error, webbrowser, subprocess
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
env = lambda k, d="": os.getenv(k, d)

# ---------- tiny HTTP helper (tests replace this) ----------
def http(method, url, headers=None, data=None, form=None, timeout=15):
    h = dict(headers or {}); body = None
    if form is not None: body = urllib.parse.urlencode(form).encode(); h["Content-Type"] = "application/x-www-form-urlencoded"
    elif isinstance(data, (dict, list)): body = json.dumps(data).encode(); h["Content-Type"] = "application/json"
    elif isinstance(data, bytes): body = data
    req = urllib.request.Request(url, body, h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: raw = r.read()
    except urllib.error.HTTPError as e: raise RuntimeError(f"HTTP {e.code}: {e.read()[:200].decode(errors='ignore')}")
    return json.loads(raw) if raw else {}

# =====================================================  GOOGLE (OAuth 2.0 installed-app flow)
SCOPES = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.events"
CRED = lambda: env("GOOGLE_CREDENTIALS", os.path.join(BASE, "credentials.json"))
TOKEN_FILE = lambda: os.path.join(BASE, "google_token.json")
def google_configured(): return os.path.exists(CRED())
def google_connected(): return os.path.exists(TOKEN_FILE())
def _client():
    c = json.load(open(CRED())); return c.get("installed") or c.get("web")
def google_connect(open_browser=True, timeout=180):
    """Opens the Google consent page, receives the code on a local port, stores the refresh token."""
    if not google_configured(): return False, "Google isn't set up yet. Put credentials.json from Google Cloud Console in the Axor folder (see SETUP.md)."
    c = _client(); got = {}
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); got.update({k: v[0] for k, v in q.items()})
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
            self.wfile.write(b"<h2>Axor is connected to Google. You can close this tab.</h2>")
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H); port = srv.server_port; redirect = f"http://127.0.0.1:{port}"
    state = secrets.token_urlsafe(12); verifier = secrets.token_urlsafe(48); chal = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    url = c["auth_uri"] + "?" + urllib.parse.urlencode({"client_id": c["client_id"], "redirect_uri": redirect, "response_type": "code", "scope": SCOPES, "access_type": "offline", "prompt": "consent", "state": state, "code_challenge": chal, "code_challenge_method": "S256"})
    if open_browser: subprocess.run(["open", url]) if os.path.exists("/usr/bin/open") else webbrowser.open(url)
    srv.timeout = timeout; end = time.time() + timeout
    while "code" not in got and "error" not in got and time.time() < end: srv.handle_request()
    srv.server_close()
    if got.get("state") != state or "code" not in got: return False, "Google sign-in was cancelled or timed out."
    tok = http("POST", c["token_uri"], form={"code": got["code"], "client_id": c["client_id"], "client_secret": c.get("client_secret", ""), "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier})
    tok["expires_at"] = time.time() + tok.get("expires_in", 3600) - 60
    with open(TOKEN_FILE(), "w") as f: json.dump(tok, f)
    os.chmod(TOKEN_FILE(), 0o600); return True, "Connected to Google."
def google_token():
    if not google_connected(): raise RuntimeError("Not connected to Google. Say 'connect Google' first.")
    t = json.load(open(TOKEN_FILE()))
    if t.get("expires_at", 0) < time.time():
        c = _client(); n = http("POST", c["token_uri"], form={"client_id": c["client_id"], "client_secret": c.get("client_secret", ""), "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
        t.update(n); t["expires_at"] = time.time() + n.get("expires_in", 3600) - 60; json.dump(t, open(TOKEN_FILE(), "w"))
    return t["access_token"]
def _g(method, url, data=None):
    return http(method, url, {"Authorization": "Bearer " + google_token()}, data)

# ---- Gmail
def gmail_unread(n=5):
    r = _g("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages?" + urllib.parse.urlencode({"q": "is:unread in:inbox", "maxResults": n}))
    out = []
    for m in r.get("messages", []):
        d = _g("GET", f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}?format=metadata&metadataHeaders=From&metadataHeaders=Subject")
        hd = {h["name"]: h["value"] for h in d.get("payload", {}).get("headers", [])}
        out.append({"from": re.sub(r"<.*?>", "", hd.get("From", "")).strip().strip('"'), "subject": hd.get("Subject", "(no subject)"), "snippet": d.get("snippet", "")})
    return out
def gmail_summary(n=5, summarize=None):
    mails = gmail_unread(n)
    if not mails: return "You have no unread emails."
    if summarize:
        try:
            s = summarize("Summarize these unread emails in 2-3 short sentences for a voice assistant:\n" + "\n".join(f"From {m['from']}: {m['subject']} - {m['snippet']}" for m in mails))
            if s: return s
        except Exception: pass
    return f"You have {len(mails)} unread emails. " + " ".join(f"From {m['from']}: {m['subject']}." for m in mails)
# ---- Calendar
BDAY_CAL = "addressbook%23contacts%40group.v.calendar.google.com"   # Google's built-in "Birthdays" calendar
def calendar_agenda(day=None, days=1, tz_off="+05:30"):
    """Events (including contact birthdays) for `days` day(s) from `day` (default today).
    Returns [(day_date, when, title)] sorted by time."""
    from datetime import date
    d = day or date.today(); end = d + timedelta(days=days)
    q = urllib.parse.urlencode({"timeMin": f"{d:%Y-%m-%d}T00:00:00{tz_off}", "timeMax": f"{end:%Y-%m-%d}T00:00:00{tz_off}", "singleEvents": "true", "orderBy": "startTime", "maxResults": 25})
    seen, out = set(), []
    for cal in ("primary", BDAY_CAL):
        try: r = _g("GET", f"https://www.googleapis.com/calendar/v3/calendars/{cal}/events?" + q)
        except Exception:
            if cal == "primary": raise
            continue
        for e in r.get("items", []):
            st = e.get("start", {}); raw = st.get("dateTime") or st.get("date")
            dt = datetime.fromisoformat(raw); when = dt.strftime("%I:%M %p").lstrip("0") if st.get("dateTime") else "All day"
            row = (dt.date(), when, e.get("summary", "(no title)"))
            if row not in seen: seen.add(row); out.append(row)
    return sorted(out, key=lambda x: (x[0], x[1] != "All day", x[1]))
def _cal_post(title, start, minutes=60, tz="Asia/Kolkata", all_day=False, repeat=False, notes="", remind_at_start=False):
    f = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S")
    if all_day: body = {"summary": title, "start": {"date": f"{start:%Y-%m-%d}"}, "end": {"date": f"{start + timedelta(days=1):%Y-%m-%d}"}}
    else:
        end = start + timedelta(minutes=minutes)
        body = {"summary": title, "start": {"dateTime": f(start), "timeZone": tz}, "end": {"dateTime": f(end), "timeZone": tz}, "reminders": {"useDefault": True}}
    if notes: body["description"] = notes
    if remind_at_start and not all_day: body["reminders"] = {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]}
    if repeat: body["recurrence"] = ["RRULE:FREQ=YEARLY"]
    return _g("POST", "https://www.googleapis.com/calendar/v3/calendars/primary/events", body)
def calendar_insert(title, start, minutes=60, tz="Asia/Kolkata", all_day=False, repeat=False, notes="", remind_at_start=False):
    """Create an event on the primary Google Calendar; returns its link."""
    return _cal_post(title, start, minutes, tz, all_day, repeat, notes, remind_at_start).get("htmlLink", "")
def calendar_insert_id(*a, **k):
    """Same, but returns the event id so it can be deleted later."""
    return _cal_post(*a, **k).get("id", "")
def calendar_delete(event_id):
    try: _g("DELETE", "https://www.googleapis.com/calendar/v3/calendars/primary/events/" + urllib.parse.quote(event_id)); return True
    except RuntimeError as e:
        if "HTTP 404" in str(e) or "HTTP 410" in str(e): return True      # already gone
        raise
def calendar_delete_matching(title, around, hours=36):
    """Delete events Axor created (description mentions Axor) whose title matches, near `around`. Returns how many."""
    q = urllib.parse.urlencode({"timeMin": (around - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S+05:30"), "timeMax": (around + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S+05:30"), "singleEvents": "true", "q": " ".join(title.split()[:3]), "maxResults": 25})
    r = _g("GET", "https://www.googleapis.com/calendar/v3/calendars/primary/events?" + q); n = 0
    for e in r.get("items", []):
        if "axor" in (e.get("description") or "").lower() and e.get("id"): calendar_delete(e["id"]); n += 1
    return n
# =====================================================  FIREBASE (Auth + Firestore REST)
def firebase_configured(): return bool(env("FIREBASE_API_KEY") and env("FIREBASE_PROJECT_ID"))
def _fs_val(v):
    if isinstance(v, bool): return {"booleanValue": v}
    if isinstance(v, int): return {"integerValue": str(v)}
    if isinstance(v, float): return {"doubleValue": v}
    return {"stringValue": str(v)}
_fb = {}
def firebase_login(username, password):
    key = env("FIREBASE_API_KEY"); email = f"{username}@axor.app"
    for ep in ("signInWithPassword", "signUp"):
        try:
            r = http("POST", f"https://identitytoolkit.googleapis.com/v1/accounts:{ep}?key={key}", data={"email": email, "password": password, "returnSecureToken": True})
            _fb[username] = {"id": r["idToken"], "uid": r["localId"], "exp": time.time() + int(r.get("expiresIn", 3600)) - 60}; return True
        except RuntimeError as e:
            if ep == "signUp": raise
    return False
def firebase_push(username, kind, cid, fields):
    t = _fb.get(username)
    if not t: raise RuntimeError("Firebase login missing")
    p = env("FIREBASE_PROJECT_ID")
    url = f"https://firestore.googleapis.com/v1/projects/{p}/databases/(default)/documents/users/{t['uid']}/{kind}/{cid}"
    return http("PATCH", url, {"Authorization": "Bearer " + t["id"]}, {"fields": {k: _fs_val(v) for k, v in fields.items()}})

# =====================================================  SUPABASE (PostgREST)
def supabase_configured(): return bool(env("SUPABASE_URL") and env("SUPABASE_KEY"))
def supabase_push(username, table, rows):
    if not rows: return
    k = env("SUPABASE_KEY")
    hd = {"apikey": k, "Prefer": "resolution=merge-duplicates,return=minimal"}
    if k.startswith("eyJ"): hd["Authorization"] = "Bearer " + k      # legacy anon keys are JWTs; new sb_publishable_ keys go in apikey only
    http("POST", f"{env('SUPABASE_URL').rstrip('/')}/rest/v1/{table}?on_conflict=cid", hd,
         [{**r, "username": username} for r in rows])

# =====================================================  CLOUDINARY (signed upload)
def cloudinary_configured(): return bool(re.match(r"cloudinary://[^:]+:[^@]+@.+", env("CLOUDINARY_URL")))
def cloudinary_upload(path, folder="axor"):
    m = re.match(r"cloudinary://([^:]+):([^@]+)@(.+)", env("CLOUDINARY_URL")); key, secret, cloud = m.groups()
    ts = str(int(time.time())); sig = hashlib.sha1(f"folder={folder}&timestamp={ts}{secret}".encode()).hexdigest()
    b = "----axor" + secrets.token_hex(8); parts = []
    for k, v in {"api_key": key, "timestamp": ts, "folder": folder, "signature": sig}.items(): parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{os.path.basename(path)}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + open(path, "rb").read() + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    r = http("POST", f"https://api.cloudinary.com/v1_1/{cloud}/auto/upload", {"Content-Type": f"multipart/form-data; boundary={b}"}, b"".join(parts), timeout=60)
    return r.get("secure_url", "")

# =====================================================  SELENIUM browser automation
def selenium_search(query, headless=True, limit=5, url=None, selector="a h2, h3 a, h2 a"):
    """Opens a real Chrome via Selenium, runs a web search and returns result titles."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    o = Options()
    if headless: o.add_argument("--headless=new")
    o.add_argument("--no-sandbox"); o.add_argument("--disable-dev-shm-usage")
    if env("CHROME_BINARY"): o.binary_location = env("CHROME_BINARY")
    svc = None
    if env("CHROMEDRIVER"):
        from selenium.webdriver.chrome.service import Service; svc = Service(env("CHROMEDRIVER"))
    d = webdriver.Chrome(options=o, service=svc) if svc else webdriver.Chrome(options=o)
    try:
        d.get(url or "https://duckduckgo.com/html/?q=" + urllib.parse.quote(query)); time.sleep(1)
        titles = [e.text.strip() for e in d.find_elements(By.CSS_SELECTOR, selector) if e.text.strip()]
        return titles[:limit]
    finally: d.quit()
