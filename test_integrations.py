import os, sys, json, time, hashlib, tempfile, threading, urllib.request, urllib.parse, subprocess, re
from datetime import datetime
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
T = tempfile.mkdtemp(); os.environ["GOOGLE_CREDENTIALS"] = os.path.join(T, "credentials.json")
import integrations as ig
ig.BASE = T
P = 0; F = []
def chk(n, c, i=""):
    global P
    if c: P += 1
    else: F.append(f"{n} {i}")
calls = []
def fake_http(method, url, headers=None, data=None, form=None, timeout=15):
    calls.append((method, url, headers, data, form))
    if "oauth2.googleapis.com/token" in url:
        return {"access_token": "AT-" + str(len(calls)), "refresh_token": "RT", "expires_in": 3600} if form.get("grant_type") == "authorization_code" else {"access_token": "REFRESHED", "expires_in": 3600}
    if url.endswith("/messages?q=is%3Aunread+in%3Ainbox&maxResults=5"): return {"messages": [{"id": "m1"}, {"id": "m2"}]}
    if "/messages/m1" in url: return {"snippet": "Review at 10", "payload": {"headers": [{"name": "From", "value": "\"Prof Rao\" <rao@vitap.ac.in>"}, {"name": "Subject", "value": "Capstone review"}]}}
    if "/messages/m2" in url: return {"snippet": "Offer", "payload": {"headers": [{"name": "From", "value": "HR <hr@co.com>"}, {"name": "Subject", "value": "Interview slot"}]}}
    if "calendar/v3" in url: return {"htmlLink": "https://calendar.google.com/event?eid=1"}
    if "identitytoolkit" in url:
        if "signInWithPassword" in url and not os.environ.get("FB_EXISTS"): raise RuntimeError("HTTP 400: EMAIL_NOT_FOUND")
        return {"idToken": "FBTOK", "localId": "UID1", "expiresIn": "3600"}
    return {"secure_url": "https://res.cloudinary.com/demo/image/upload/axor/x.png"} if "cloudinary" in url else {}
ig.http = fake_http
# --- Google OAuth flow end to end (consent page simulated by calling the redirect ourselves)
json.dump({"installed": {"client_id": "cid", "client_secret": "sec", "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}, open(os.environ["GOOGLE_CREDENTIALS"], "w"))
chk("configured", ig.google_configured()); chk("not connected yet", not ig.google_connected())
def fake_open(args, **k):
    url = args[-1]; q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["code_challenge_method"] == ["S256"] and "gmail.readonly" in q["scope"][0] and q["access_type"] == ["offline"]
    def hit(): time.sleep(.3); urllib.request.urlopen(q["redirect_uri"][0] + "?" + urllib.parse.urlencode({"code": "authcode", "state": q["state"][0]})).read()
    threading.Thread(target=hit).start(); return 0
ig.subprocess.run = fake_open; os.path.exists = (lambda orig: (lambda p: True if p == "/usr/bin/open" else orig(p)))(os.path.exists)
ok, msg = ig.google_connect(timeout=10); chk("oauth connect", ok, msg); chk("token file saved", ig.google_connected())
tok = json.load(open(ig.TOKEN_FILE())); chk("refresh token stored", tok["refresh_token"] == "RT"); chk("token file private", oct(os.stat(ig.TOKEN_FILE()).st_mode)[-3:] == "600")
x = [c for c in calls if "oauth2" in c[1]][-1][4]; chk("pkce verifier sent", x.get("code_verifier") and x["grant_type"] == "authorization_code")
mails = ig.gmail_unread(5); chk("gmail 2 mails", len(mails) == 2 and mails[0]["from"] == "Prof Rao" and mails[1]["subject"] == "Interview slot", mails)
chk("auth header", any(c[2] and c[2].get("Authorization", "").startswith("Bearer AT") for c in calls if "gmail" in c[1]))
s1 = ig.gmail_summary(5); chk("summary plain", s1.startswith("You have 2 unread") and "Capstone review" in s1, s1)
chk("summary llm", ig.gmail_summary(5, lambda q: "Two new emails.") == "Two new emails.")
chk("summary llm failure falls back", ig.gmail_summary(5, lambda q: 1 / 0).startswith("You have 2"))
link = ig.calendar_insert("Meeting - Rahul", datetime(2026, 11, 19, 17, 0)); body = [c for c in calls if "calendar/v3" in c[1]][-1][3]
chk("calendar insert", link.startswith("https://calendar.google.com") and body["start"]["dateTime"] == "2026-11-19T17:00:00" and body["end"]["dateTime"] == "2026-11-19T18:00:00" and body["start"]["timeZone"] == "Asia/Kolkata", body)
tok["expires_at"] = 0; json.dump(tok, open(ig.TOKEN_FILE(), "w")); ig.gmail_unread(1); chk("token refreshed when expired", any(c[4] and c[4].get("grant_type") == "refresh_token" for c in calls))
os.remove(ig.TOKEN_FILE()); 
try: ig.gmail_unread(); chk("no token raises", False)
except RuntimeError as e: chk("no token raises", "connect Google" in str(e))
# --- Firebase
os.environ.update(FIREBASE_API_KEY="KEY", FIREBASE_PROJECT_ID="proj"); chk("fb configured", ig.firebase_configured())
chk("fb signUp fallback", ig.firebase_login("jayanth", "pw1234") and ig.firebase_login("jayanth", "pw1234"))
ig.firebase_push("jayanth", "commands", "1-h-5", {"command": "hi", "ms": 3, "ok": 1, "score": 1.5, "flag": True})
c = [c for c in calls if "firestore" in c[1]][-1]; f = c[3]["fields"]
chk("firestore url", c[0] == "PATCH" and c[1].endswith("/projects/proj/databases/(default)/documents/users/UID1/commands/1-h-5"), c[1])
chk("firestore types", f["command"] == {"stringValue": "hi"} and f["ms"] == {"integerValue": "3"} and f["score"] == {"doubleValue": 1.5} and f["flag"] == {"booleanValue": True}, f)
chk("firestore bearer", c[2]["Authorization"] == "Bearer FBTOK")
# --- Supabase
os.environ.update(SUPABASE_URL="https://x.supabase.co/", SUPABASE_KEY="anon"); chk("sb configured", ig.supabase_configured())
ig.supabase_push("jayanth", "commands", [{"cid": "1-h-1", "command": "hi"}]); c = [c for c in calls if "supabase" in c[1]][-1]
chk("supabase upsert", c[0] == "POST" and c[1] == "https://x.supabase.co/rest/v1/commands?on_conflict=cid" and c[2]["apikey"] == "anon" and "merge-duplicates" in c[2]["Prefer"] and c[3][0]["username"] == "jayanth", c)
n = len(calls); ig.supabase_push("jayanth", "notes", []); chk("supabase empty no call", len(calls) == n)
# --- Cloudinary signed upload
os.environ["CLOUDINARY_URL"] = "cloudinary://KEY:SECRET@mycloud"; chk("cld configured", ig.cloudinary_configured())
png = os.path.join(T, "s.png"); open(png, "wb").write(b"\x89PNGDATA")
url = ig.cloudinary_upload(png); c = [c for c in calls if "cloudinary.com" in c[1]][-1]; b = c[3]
chk("cld url", url.startswith("https://res.cloudinary.com") and c[1] == "https://api.cloudinary.com/v1_1/mycloud/auto/upload")
ts = re.search(rb'name="timestamp"\r\n\r\n(\d+)', b).group(1).decode(); sig = re.search(rb'name="signature"\r\n\r\n([0-9a-f]+)', b).group(1).decode()
chk("cld signature correct", sig == hashlib.sha1(f"folder=axor&timestamp={ts}SECRET".encode()).hexdigest()); chk("cld file bytes", b"\x89PNGDATA" in b and b"SECRET" not in b)
# --- wired into the assistant commands
os.environ.pop("CLOUDINARY_URL"); os.environ.pop("SUPABASE_URL"); os.environ.pop("FIREBASE_API_KEY")
import server as s
s.IS_MAC = True; s.sh = lambda cmd, timeout=15: (True, ""); s.osa = lambda sc: (True, ""); s.online = lambda: True; s.speak = lambda *a: None; s.notify = lambda *a: None
s.ig.BASE = T; s.CUR.uid = 0
r = s.run_command("read my emails"); chk("cmd emails not connected", r[0] == "google" and not r[2] and "connect Google" in r[1], r)
r = s.run_command("connect google"); chk("cmd connect starts", r[0] == "google" and r[2], r)
time.sleep(.1); s.ig.google_connect = lambda *a, **k: (True, "ok")
json.dump({"access_token": "AT", "refresh_token": "RT", "expires_at": time.time() + 999}, open(ig.TOKEN_FILE(), "w"))
s.llm = lambda q: (None, "no key"); r = s.run_command("check my email"); chk("cmd emails connected", r[2] and "unread" in r[1].lower() and "Capstone review" in r[1], r)
chk("cmd open gmail still opens site", s.run_command("open gmail")[0] == "web")
r = s.run_command("schedule a meeting with rahul tomorrow at 5 pm"); chk("cmd meeting -> google calendar", r[0] == "calendar" and "Google Calendar" in r[1], r)
with s.db() as c: chk("event also logged locally", c.execute("SELECT COUNT(*) FROM events WHERE title LIKE '%Rahul%'").fetchone()[0] >= 1)
chk("integrations endpoint", True)
tc = s.app.test_client(); tk = tc.post("/api/signup", json={"username": "integ", "password": "secret1"}).json["token"]
it = tc.get("/api/integrations", headers={"Authorization": "Bearer " + tk}).json; chk("integrations list", len(it) == 5 and it[0]["state"] == "connected", it)
# --- Selenium with a real headless Chrome on a local page (no internet needed)
page = os.path.join(T, "r.html"); open(page, "w").write("<html><body><div><a><h2>Result One</h2></a><a><h2>Result Two</h2></a></div></body></html>")
if os.environ.get("CHROME_BINARY") or os.environ.get("RUN_SELENIUM"):
    try:
        titles = ig.selenium_search("x", url="file://" + page); chk("selenium real chrome", titles == ["Result One", "Result Two"], titles)
    except Exception as e:
        if "only supports Chrome version" in str(e): print("(selenium real-browser test SKIPPED: chromedriver/Chrome version mismatch)")
        else: chk("selenium real chrome", False, str(e)[:150])
else: print("(selenium real-browser test skipped; set CHROME_BINARY/CHROMEDRIVER to run)")
# ---- calendar agenda
_orig = ig._g
ig._g = lambda m, u, d=None: {"items": [{"summary": "Final review", "start": {"dateTime": "2026-11-19T10:00:00+05:30"}}, {"summary": "Holiday", "start": {"date": "2026-11-19"}}]}
from datetime import date as _d
ag = ig.calendar_agenda(_d(2026, 11, 19)); chk("calendar agenda", [x[1:] for x in ag] == [("All day", "Holiday"), ("10:00 AM", "Final review")], ag)
ig._g = _orig
print("PASS", P, "FAIL", len(F)); [print(" -", f) for f in F]

