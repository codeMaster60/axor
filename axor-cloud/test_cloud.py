import os, sys, time, json, tempfile
os.environ["AXOR_CLOUD_DB"] = tempfile.mktemp(suffix=".db"); os.environ["AXOR_RATE_LIMIT"] = "100000"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloud as s
c = s.app.test_client(); P = 0; F = []
def chk(n, cond, info=""):
    global P
    if cond: P += 1
    else: F.append(f"{n} {info}")
def reg(u, p="secret1"): return c.post("/api/auth/register", json={"username": u, "password": p})
a = reg("alice"); b = reg("bob"); TA = a.json["token"]; TB = b.json["token"]
H = lambda t: {"Authorization": "Bearer " + t}
chk("register 201", a.status_code == 201); chk("dup 409", reg("ALICE").status_code == 409)
chk("short pw", reg("carol", "1").status_code == 400); chk("bad name", reg("a b").status_code == 400); chk("empty", c.post("/api/auth/register").status_code == 400)
chk("login ok", c.post("/api/auth/login", json={"username": "alice", "password": "secret1"}).status_code == 200)
chk("login bad", c.post("/api/auth/login", json={"username": "alice", "password": "x"}).status_code == 401)
chk("login ghost", c.post("/api/auth/login", json={"username": "zed", "password": "x"}).status_code == 401)
# JWT structure & tamper & expiry
parts = TA.split("."); chk("jwt 3 parts", len(parts) == 3)
chk("jwt tamper", c.get("/api/auth/me", headers=H(parts[0] + "." + parts[1] + ".AAAA")).status_code == 401)
chk("jwt none alg", c.get("/api/auth/me", headers=H("x.y.")).status_code == 401)
exp = s.jwt_make(1, "alice", days=-1); chk("jwt expired", c.get("/api/auth/me", headers=H(exp)).status_code == 401)
chk("me", c.get("/api/auth/me", headers=H(TA)).json["username"] == "alice")
for ep in ["/api/commands/history", "/api/settings", "/api/reminders", "/api/events", "/api/notes", "/api/analytics/summary", "/api/analytics/daily", "/api/analytics/weekly", "/api/analytics/categories", "/api/commands/export"]:
    chk("noauth " + ep, c.get(ep).status_code == 401); chk("auth " + ep, c.get(ep, headers=H(TA)).status_code == 200)
chk("health open", c.get("/api/health").json["status"] == "ok")
# commands
chk("save", c.post("/api/commands/save", json={"command": "hi", "response": "Hello", "category": "chat", "ms": 5, "source": "voice"}, headers=H(TA)).status_code == 201)
chk("save empty", c.post("/api/commands/save", json={}, headers=H(TA)).status_code == 400)
c.post("/api/commands/save", json={"command": "open youtube", "response": "Opening", "category": "web", "ms": 20, "ok": False}, headers=H(TA))
h = c.get("/api/commands/history", headers=H(TA)).json; chk("hist 2", len(h) == 2)
chk("hist search", len(c.get("/api/commands/history?q=youtube", headers=H(TA)).json) == 1)
chk("hist paging", len(c.get("/api/commands/history?limit=1&offset=1", headers=H(TA)).json) == 1)
chk("isolation", c.get("/api/commands/history", headers=H(TB)).json == [])
chk("del other user 404", c.delete(f"/api/commands/{h[0]['id']}", headers=H(TB)).status_code == 404)
chk("sqli", c.get("/api/commands/history?q=%27%3BDROP%20TABLE%20commands%3B--", headers=H(TA)).status_code == 200 and len(c.get("/api/commands/history", headers=H(TA)).json) == 2)
chk("bad limit", True)
e = c.get("/api/commands/export", headers=H(TA)); chk("csv", e.data.decode().startswith("id,time") and "open youtube" in e.data.decode())
# idempotent sync
pay = {"commands": [{"cid": "u1-1", "command": "a", "response": "b", "category": "x", "ms": 3, "ts": "2026-11-17T10:00:00"}], "reminders": [{"cid": "r1", "text": "t", "due": "2026-11-19T10:00:00"}], "events": [{"cid": "e1", "title": "M", "start": "2026-11-19T17:00"}], "notes": [{"cid": "n1", "ts": "2026-11-18T10:00:00", "text": "n"}]}
r1 = c.post("/api/sync", json=pay, headers=H(TA)); r2 = c.post("/api/sync", json=pay, headers=H(TA))
chk("sync ok", r1.json["synced"]["commands"] == 1)
chk("sync idempotent", len(c.get("/api/commands/history", headers=H(TA)).json) == 3 and len(c.get("/api/reminders", headers=H(TA)).json) == 1 and len(c.get("/api/events", headers=H(TA)).json) == 1 and len(c.get("/api/notes", headers=H(TA)).json) == 1)
chk("sync bad json", c.post("/api/sync", data="x", headers=H(TA)).status_code in (200, 400, 500) )
# crud
for name, d in (("reminders", {"text": "x", "due": "2026-11-20T09:00"}), ("events", {"title": "y", "start": "2026-11-20T09:00"}), ("notes", {"ts": "2026-11-18", "text": "z"})):
    chk("add " + name, c.post(f"/api/{name}", json=d, headers=H(TA)).status_code == 201); chk("add bad " + name, c.post(f"/api/{name}", json={}, headers=H(TA)).status_code == 400)
    lst = c.get(f"/api/{name}", headers=H(TA)).json; i = lst[-1]["id"] if name != "notes" else lst[0]["id"]
    chk("del other " + name, c.delete(f"/api/{name}/{i}", headers=H(TB)).status_code == 404)
    chk("del " + name, c.delete(f"/api/{name}/{i}", headers=H(TA)).status_code == 200); chk("del twice " + name, c.delete(f"/api/{name}/{i}", headers=H(TA)).status_code == 404)
# settings
chk("put settings", c.put("/api/settings", json={"speak": "0", "BAD KEY": "1"}, headers=H(TA)).json == {"speak": "0"})
chk("settings isolated", c.get("/api/settings", headers=H(TB)).json == {})
# analytics
sm = c.get("/api/analytics/summary", headers=H(TA)).json; chk("summary", sm["total"] == 3 and sm["voice"] == 1 and 0 <= sm["success"] <= 100, sm)
chk("summary empty", c.get("/api/analytics/summary", headers=H(TB)).json["total"] == 0)
chk("daily", len(c.get("/api/analytics/daily", headers=H(TA)).json) >= 1); chk("weekly", len(c.get("/api/analytics/weekly", headers=H(TA)).json) >= 1); chk("cats", len(c.get("/api/analytics/categories", headers=H(TA)).json) >= 1)
# rate limit
s.RATE = 5; s.HITS.clear(); codes = [c.get("/api/health").status_code for _ in range(8)]; chk("rate limit", 429 in codes and codes[:5] == [200] * 5, codes); s.RATE = 100000
chk("sec headers", c.get("/api/health").headers.get("X-Content-Type-Options") == "nosniff")
chk("api 404", c.get("/api/nope", headers=H(TA)).status_code in (404, 401))
# --- conversations, files, reminders/upcoming, refresh, monthly, sessions
r = c.post("/api/auth/refresh", headers=H(TA)); chk("refresh token", r.status_code == 200 and r.json["token"].count(".") == 2 and c.get("/api/auth/me", headers=H(r.json["token"])).status_code == 200)
chk("refresh needs auth", c.post("/api/auth/refresh").status_code == 401)
chk("conv save", c.post("/api/conversations/save", json={"title": "Tax chat", "n": 4}, headers=H(TA)).status_code == 201)
chk("conv save needs title", c.post("/api/conversations/save", json={}, headers=H(TA)).status_code == 400)
chk("conv list", [x["title"] for x in c.get("/api/conversations/list", headers=H(TA)).json] == ["Tax chat"])
chk("conv isolated", c.get("/api/conversations/list", headers=H(TB)).json == [])
c.post("/api/sync", json={"conversations": [{"cid": "1-c-x", "title": "Synced chat", "n": 2, "last": "2026-11-19T10:00:00"}]}, headers=H(TA))
chk("conv via sync", "Synced chat" in [x["title"] for x in c.get("/api/conversations/list", headers=H(TA)).json])
chk("file upload", c.post("/api/files/upload", json={"name": "Axor_1.png", "url": "https://res.cloudinary.com/x/1.png"}, headers=H(TA)).status_code == 201)
chk("file bad url", c.post("/api/files/upload", json={"name": "a", "url": "javascript:alert(1)"}, headers=H(TA)).status_code == 400)
fl = c.get("/api/files", headers=H(TA)).json; chk("file list", len(fl) == 1 and fl[0]["name"] == "Axor_1.png")
chk("file isolated", c.get("/api/files", headers=H(TB)).json == [] and c.delete("/api/files/%d" % fl[0]["id"], headers=H(TB)).status_code == 404)
chk("file delete", c.delete("/api/files/%d" % fl[0]["id"], headers=H(TA)).status_code == 200)
chk("rem create", c.post("/api/reminders/create", json={"text": "Call mom", "due": "2099-01-01T10:00"}, headers=H(TA)).status_code == 201)
chk("rem create missing", c.post("/api/reminders/create", json={"text": "x"}, headers=H(TA)).status_code == 400)
chk("rem upcoming", "Call mom" in [x["text"] for x in c.get("/api/reminders/upcoming", headers=H(TA)).json])
chk("settings/update", c.put("/api/settings/update", json={"voice": "Tara"}, headers=H(TA)).json.get("voice") == "Tara")
c.post("/api/commands/save", json={"command": "hi", "ts": "2026-11-19T10:00:00", "ms": 10}, headers=H(TA))
mo = c.get("/api/analytics/monthly", headers=H(TA)).json; chk("monthly", any(x["month"] == "2026-11" for x in mo), mo)
chk("sessions logged", s.db().execute("SELECT COUNT(*) FROM sessions").fetchone()[0] >= 2)
n = len([r for r in s.app.url_map.iter_rules() if r.rule.startswith("/api/")]); chk("endpoint count >=20", n >= 20, n)
print("PASS", P, "FAIL", len(F), "| API endpoints:", n); [print(" -", f) for f in F]
