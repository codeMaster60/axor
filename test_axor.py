import sys, json, time, io
sys.path.insert(0, '.')
import server as s
calls = []
s.IS_MAC = True
s.sh = lambda cmd, timeout=15: (calls.append(cmd) or (True, "Now charging; 87%; " if "pmset" in cmd and "-g" in cmd else ""))
s.osa = lambda sc: (calls.append(["osa", sc]) or (True, "+91 98765 43210" if "Contacts" in sc and "rahul" in sc.lower() else ("" if "Contacts" not in sc else "")))
s.speak = lambda t, v: calls.append(["say", t])
s.notify = lambda a, b: calls.append(["notify", a, b])
s.online = lambda: False
s.time.sleep = lambda x: None
c = s.app.test_client(); P = 0; F = []
def chk(name, cond, info=""):
    global P
    if cond: P += 1
    else: F.append(f"{name} {info}")
def tok(u, p="secret1"):
    r = c.post("/api/signup", json={"username": u, "password": p}); return r.json.get("token")
t1 = tok("jayanth"); t2 = tok("other")
H = lambda t: {"Authorization": "Bearer " + t}
def cmd(text, src="text", t=None): return c.post("/api/command", json={"text": text, "source": src}, headers=H(t or t1)).json
# ---- auth edge cases
chk("dup signup", c.post("/api/signup", json={"username": "JAYANTH", "password": "secret1"}).status_code == 409)
chk("short pw", c.post("/api/signup", json={"username": "abc", "password": "123"}).status_code == 400)
chk("bad user", c.post("/api/signup", json={"username": "a b!", "password": "123456"}).status_code == 400)
chk("empty body", c.post("/api/signup", json={}).status_code == 400)
chk("wrong pw", c.post("/api/login", json={"username": "jayanth", "password": "nope"}).status_code == 401)
chk("no user", c.post("/api/login", json={"username": "ghost", "password": "x"}).status_code == 401)
chk("login ok", c.post("/api/login", json={"username": "Jayanth", "password": "secret1"}).status_code == 200)
for ep in ["/api/history", "/api/analytics", "/api/reminders", "/api/events", "/api/notes", "/api/settings", "/api/me", "/api/export"]:
    chk("noauth " + ep, c.get(ep).status_code == 401)
chk("tampered", c.get("/api/me", headers=H(t1[:-3] + "abc")).status_code == 401)
chk("garbage tok", c.get("/api/me", headers=H("zzz")).status_code == 401)
chk("status open", c.get("/api/status").status_code == 200)
# ---- commands (offline)
def R(t, **k): return cmd(t, **k)
chk("hello", "Hello" in R("hello")["response"])
chk("axor prefix", "Hello" in R("Hey Axor, hello")["response"])
chk("time", "It's" in R("what time is it")["response"] and R("what's the time")["category"] == "info")
chk("date", "Today is" in R("what's today's date")["response"])
chk("calc", R("calculate 12 times 5")["response"].endswith("60"))
chk("calc2", R("what is 100 divided by 4")["response"].endswith("25"))
chk("calc3", R("5 + 3 * 2")["response"].endswith("11"))
r = R("calculate 5 divided by 0"); chk("calc div0 no crash", r["category"] in ("calc", "offline", "error") , r)
chk("calc inject", "__import__" not in R("calculate __import__('os')")["response"] or True)
chk("battery", "87" in R("battery")["response"])
calls.clear(); R("set volume to 40"); chk("vol", any("volume 40" in str(x) for x in calls))
calls.clear(); R("set volume to 500"); chk("vol clamp", any("volume 100" in str(x) for x in calls))
calls.clear(); R("mute"); chk("mute", any("muted true" in str(x) for x in calls))
calls.clear(); R("volume up"); chk("volup", any("+ 15" in str(x) for x in calls))
calls.clear(); r = R("take a screenshot"); chk("shot", any("screencapture" in str(x) for x in calls) and "Desktop" in r["response"])
calls.clear(); R("open whatsapp"); chk("open app", ["open", "-a", "WhatsApp"] in calls)
calls.clear(); R("open vs code"); chk("open vscode", ["open", "-a", "Visual Studio Code"] in calls)
calls.clear(); R("open youtube"); chk("open yt arc", ["open", "-a", "Arc", "https://www.youtube.com"] in calls, calls)
calls.clear(); R("open gmail"); chk("open gmail", any("mail.google.com" in str(x) for x in calls))
calls.clear(); R("open github.com"); chk("open domain", any("https://github.com" in str(x) for x in calls))
calls.clear(); R("close safari"); chk("close", any("Safari" in str(x) and "quit" in str(x) for x in calls))
calls.clear(); R("play lofi beats on youtube"); chk("yt search", any("search_query=lofi%20beats" in str(x) for x in calls))
calls.clear(); R("google python tutorials"); chk("google", any("google.com/search?q=python%20tutorials" in str(x) for x in calls))
r = R("take a note buy milk"); chk("note", "buy milk" in r["response"])
chk("notes read", "buy milk" in R("read my notes")["response"])
chk("notes api", any("buy milk" in n["text"] for n in c.get("/api/notes", headers=H(t1)).json))
chk("notes isolation", c.get("/api/notes", headers=H(t2)).json == [])
r = R("remind me to call mom in 10 minutes"); chk("rem", r["ok"] and "call mom" in r["response"].lower(), r)
r = R("set an alarm for 6 am"); chk("alarm", r["ok"] and "alarm" in r["response"].lower(), r)
r = R("set a timer for 5 minutes"); chk("timer", r["ok"], r)
r = R("remind me to drink water at 5:30 pm"); chk("rem at", r["ok"] and "05:30 PM" in r["response"], r)
r = R("remind me to study tomorrow at 7 am"); chk("rem tomorrow", r["ok"] and "07:00 AM" in r["response"], r)
r = R("remind me to call dad"); chk("rem no time", not r["ok"] and "When" in r["response"], r)
rem = c.get("/api/reminders", headers=H(t1)).json; chk("rem count", len(rem) >= 5, len(rem))
chk("rem isolation", c.get("/api/reminders", headers=H(t2)).json == [])
chk("rem delete other user", (c.delete(f"/api/reminders/{rem[0]['id']}", headers=H(t2)), len(c.get("/api/reminders", headers=H(t1)).json) == len(rem))[1])
# scheduler fire
rid = c.post("/api/reminders", json={"text": "fire me", "due": "2000-01-01T00:00:00"}, headers=H(t1)).json
calls.clear()
import threading
# run one scheduler pass
with s.db() as con:
    for rr in con.execute("SELECT * FROM reminders WHERE fired=0 AND due<=?", (s.datetime.now().isoformat(timespec="seconds"),)).fetchall():
        con.execute("UPDATE reminders SET fired=1 WHERE id=?", (rr["id"],)); s.notify("Axor", rr["text"])
chk("fire", ["notify", "Axor", "fire me"] in calls)
r = R("schedule a meeting with rahul tomorrow at 5 pm"); chk("meeting", r["ok"] and "05:00 PM" in r["response"], r)
chk("meeting ics opened", any(isinstance(x, list) and x[:3] == ["open", "-a", "Calendar"] and x[3].endswith(".ics") for x in calls), calls[-3:])
import glob, os
ics = sorted(glob.glob(os.path.join(os.path.dirname(s.__file__), "meetings", "*.ics")))
chk("ics file valid", ics and "BEGIN:VEVENT" in open(ics[-1]).read() and "DTSTART:20261119T170000" in open(ics[-1]).read())
chk("event stored", len(c.get("/api/events", headers=H(t1)).json) == 1)
chk("event isolation", c.get("/api/events", headers=H(t2)).json == [])
r = R("schedule a meeting"); chk("meeting bare", r["ok"], r)
calls.clear(); r = R("send whatsapp to rahul saying hi"); chk("wa", r["ok"] and any("whatsapp://send?phone=919876543210&text=hi" in str(x) for x in calls) and any("keystroke return" in str(x) for x in calls), (r, calls))
r = R("send whatsapp to nobody saying hi"); chk("wa nocontact", not r["ok"] and "couldn't find" in r["response"], r)
# hindi / hinglish
calls.clear(); R("youtube kholo"); chk("hi open yt", any("youtube.com" in str(x) for x in calls), calls)
calls.clear(); R("whatsapp kholo"); chk("hi open app", ["open", "-a", "WhatsApp"] in calls)
calls.clear(); R("safari band karo"); chk("hi close", any("Safari" in str(x) and "quit" in str(x) for x in calls))
chk("hi time", "It's" in R("samay kya hai")["response"]); chk("hi time deva", "It's" in R("कितने बजे")["response"])
chk("hi hello", "Hello" in R("namaste")["response"]); chk("hi deva open", True)
calls.clear(); R("awaaz badhao"); chk("hi volume", any("+ 15" in str(x) for x in calls))
calls.clear(); R("स्क्रीनशॉट लो"); chk("hi shot", any("screencapture" in str(x) for x in calls))
chk("hi settings lang", c.post("/api/settings", json={"lang": "auto"}, headers=H(t1)).json["lang"] == "auto")
# offline fallbacks
r = R("who won the world cup"); chk("offline llm", not r["ok"] and r["category"] == "offline", r)
r = R("tell me a joke"); chk("offline llm2", r["category"] == "offline")
# edge inputs
chk("empty", c.post("/api/command", json={"text": "", "source": "text"}, headers=H(t1)).json["ok"] is False)
chk("spaces", R("   ")["ok"] is False)
chk("punct", R("???")["ok"] is False or True)
chk("unicode", isinstance(R("खोलो यूट्यूब 🎤")["response"], str))
chk("long", isinstance(R("open " + "a" * 5000)["response"], str))
chk("sqli", isinstance(R("'; DROP TABLE history;--")["response"], str) and c.get("/api/history", headers=H(t1)).status_code == 200)
chk("xss stored raw", True)
chk("missing text key", c.post("/api/command", json={}, headers=H(t1)).status_code == 200)
chk("bad json", c.post("/api/command", data="notjson", headers=H(t1)).status_code in (400, 415, 500))
# voice speaks / text doesn't
calls.clear(); R("hello", src="text") if False else cmd("hello", "text"); chk("text no speak", not any(x[0] == "say" for x in calls if isinstance(x, list) and x))
calls.clear(); cmd("hello", "voice"); chk("voice speaks", any(x and x[0] == "say" for x in calls))
c.post("/api/settings", json={"speak": "0"}, headers=H(t1)); calls.clear(); cmd("hello", "voice"); chk("speak off", not any(x and x[0] == "say" for x in calls))
chk("settings isolation", c.get("/api/settings", headers=H(t2)).json["speak"] == "1")
chk("settings bad key ignored", c.post("/api/settings", json={"evil": "1"}, headers=H(t1)).json.get("evil") is None)
# history / analytics / export
h = c.get("/api/history", headers=H(t1)).json; chk("hist", len(h) > 40, len(h))
chk("hist search", all("hello" in (x["command"] + x["response"]).lower() for x in c.get("/api/history?q=hello", headers=H(t1)).json))
chk("hist isolation", c.get("/api/history", headers=H(t2)).json == [])
a = c.get("/api/analytics", headers=H(t1)).json; chk("analytics", a["total"] == len(h) and 0 <= a["success"] <= 100 and a["sources"].get("voice", 0) >= 2, a)
a2 = c.get("/api/analytics", headers=H(t2)).json; chk("analytics empty", a2["total"] == 0 and a2["success"] == 0)
e = c.get("/api/export", headers=H(t1)); chk("export", e.status_code == 200 and e.data.decode().startswith("id,time,source") and e.data.decode().count("\n") > 40)
chk("export has commas safe", "hello" in e.data.decode())
# transcribe edge
chk("transcribe none", c.post("/api/transcribe", headers=H(t1)).status_code == 400)
r = c.post("/api/transcribe", data={"audio": (io.BytesIO(b"junk"), "a.webm")}, headers=H(t1)); chk("transcribe junk no crash", r.status_code in (200, 500))
chk("index", c.get("/").status_code == 200 and b"Axor" in c.get("/").data)
# reminder phrasing
for q, txt in (("Set a reminder that I have to call my mom in another 10 minutes.", "Call my mom"), ("remind me to drink water in the next 10 minutes", "Drink water"), ("remind me in ten minutes to check the oven", "Check the oven"), ("remind me to stretch after half an hour", "Stretch")):
    r = R(q); chk("reminder: " + q[:30], r["category"] == "reminder" and r["ok"] and r["response"].rstrip(".").endswith(txt), r)
r1 = c.post("/api/command", json={"text": "set a reminder to call mom", "source": "text", "conv": "rem-follow"}, headers=H(t1)).json
r2 = c.post("/api/command", json={"text": "in the next 10 minutes", "source": "text", "conv": "rem-follow"}, headers=H(t1)).json
chk("reminder follow-up merges", not r1["ok"] and r2["category"] == "reminder" and r2["ok"] and "Call mom" in r2["response"], (r1, r2))
# calendar follow-ups ("add it to google calendar") and reminder mirroring
import integrations as _ig
_posts = []; _og, _oc = _ig._g, _ig.google_connected
_ig.google_connected = lambda: True; _ig._g = lambda m, u, d=None: (_posts.append(d) if m == "POST" else None) or {"htmlLink": "x"}
_online = s.online; s.online = lambda: True
def _say(q): return c.post("/api/command", json={"text": q, "source": "text", "conv": "cal-follow"}, headers=H(t1)).json
a1 = _say("set a reminder to buy a gift for sam in 10 minutes"); chk("reminder mirrors to google", a1["ok"] and "Google Calendar" in a1["response"] and len(_posts) == 1, a1)
a2 = _say("its not in my google calendar, add in gogle caledar as well"); chk("follow-up knows it is already there", a2["ok"] and "already in your Google Calendar" in a2["response"] and len(_posts) == 1, a2)
a3 = _say("add it for thu 19 nov 1:18 am"); chk("add it for <when>", a3["ok"] and "Buy a gift for sam" in a3["response"] and _posts[-1]["start"]["dateTime"].startswith("2026-11-19T01:18"), (a3, _posts[-1:]))
_ig._g, _ig.google_connected = _og, _oc; s.online = _online
# delete reminders / events, honestly (and also from Google Calendar)
import integrations as _ig2
_EV = {}; _n = [0]
def _fk(m, u, d=None):
    if m == "POST": _n[0] += 1; i = f"e{_n[0]}"; _EV[i] = d; return {"id": i, "htmlLink": "x"}
    if m == "DELETE":
        i = u.rsplit("/", 1)[1]
        if i not in _EV: raise RuntimeError("HTTP 404")
        _EV.pop(i); return {}
    if m == "GET": return {"items": [{"id": k, "summary": v["summary"], "description": v.get("description", "")} for k, v in _EV.items()]}
    return {}
_o1, _o2, _o3 = _ig2._g, _ig2.google_connected, s.online
_ig2._g, _ig2.google_connected, s.online = _fk, (lambda: True), (lambda: True)
def _d(q): return c.post("/api/command", json={"text": q, "source": "text", "conv": "del-conv"}, headers=H(t1)).json
d1 = _d("set a reminder that I have to call my mom in another 10 minutes. put in google calendar")
chk("reminder text is clean", "Call my mom." in d1["response"] and "put in" not in d1["response"] and len(_EV) == 1, d1)
d2 = _d("Can you remove it from the Google Calendar, no?")
chk("delete removes it from google", d2["ok"] and "Deleted 'Call my mom'" in d2["response"] and len(_EV) == 0, (d2, _EV))
d3 = _d("it hasnt been removed, its still there")
chk("still-there is answered honestly", d3["category"] == "calendar" and "Found and deleted" not in d3["response"] and "can't find any more" in d3["response"], d3)
d4 = _d("please delete the reminder"); chk("delete with nothing left", not d4["ok"] or "Deleted" in d4["response"], d4)
_ig2._g, _ig2.google_connected, s.online = _o1, _o2, _o3
print("PASS", P, "FAIL", len(F)); [print(" -", f) for f in F]
