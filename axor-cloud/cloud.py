"""Axor Cloud: REST backend (Flask). JWT (HS256) auth, 35 endpoints, rate limiting, offline-sync target.
Run: python cloud.py  ->  http://localhost:8080  (serves the React dashboard too)"""
import os, re, io, csv, json, time, hmac, base64, hashlib, secrets, sqlite3, collections
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, Response, g, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("AXOR_CLOUD_DB", os.path.join(BASE, "cloud.db"))
SECRET = (os.environ.get("AXOR_JWT_SECRET") or "axor-dev-secret-change-me").encode()
RATE = int(os.environ.get("AXOR_RATE_LIMIT", "100"))   # requests / minute / client
app = Flask(__name__, static_folder=None)

def db():
    c = sqlite3.connect(DB, timeout=10); c.row_factory = sqlite3.Row; return c
with db() as c: c.executescript("""
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, salt TEXT, pw TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS commands(id INTEGER PRIMARY KEY, user_id INT, cid TEXT, ts TEXT, source TEXT, command TEXT, response TEXT, category TEXT, ms INT, ok INT, UNIQUE(user_id,cid));
CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY, user_id INT, cid TEXT, text TEXT, due TEXT, fired INT DEFAULT 0, kind TEXT, UNIQUE(user_id,cid));
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, user_id INT, cid TEXT, title TEXT, start TEXT, UNIQUE(user_id,cid));
CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, user_id INT, cid TEXT, ts TEXT, text TEXT, UNIQUE(user_id,cid));
CREATE TABLE IF NOT EXISTS settings(user_id INT, k TEXT, v TEXT, PRIMARY KEY(user_id,k));
CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, user_id INT, ts TEXT, ip TEXT, agent TEXT);
CREATE TABLE IF NOT EXISTS conversations(id INTEGER PRIMARY KEY, user_id INT, cid TEXT, title TEXT, n INT, last TEXT, UNIQUE(user_id,cid));
CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, user_id INT, cid TEXT, name TEXT, url TEXT, ts TEXT, UNIQUE(user_id,cid));""")


# ---------- cache: Redis when REDIS_URL is set, otherwise in-process (same interface) ----------
class Cache:
    def __init__(self):
        self.r = None; self.mem = {}; self.hits = 0; self.misses = 0
        url = os.environ.get("REDIS_URL")
        if url:
            try:
                import redis; self.r = redis.Redis.from_url(url, decode_responses=True, socket_timeout=1); self.r.ping()
            except Exception as e: print("redis unavailable, using memory cache:", e); self.r = None
    backend = property(lambda self: "redis" if self.r else "memory")
    def ver(self, uid):
        try: return (self.r.get(f"v:{uid}") if self.r else self.mem.get(f"v:{uid}")) or "0"
        except Exception: return "0"
    def bump(self, uid):
        try:
            if self.r: self.r.incr(f"v:{uid}")
            else: self.mem[f"v:{uid}"] = str(int(self.mem.get(f"v:{uid}", "0")) + 1)
        except Exception: pass
    def get(self, key, ttl, fn):
        try:
            v = self.r.get(key) if self.r else (self.mem.get(key) if self.mem.get(key) and self.mem[key][1] > time.time() else None)
            if self.r is None and v: v = v[0]
        except Exception: v = None
        if v is not None: self.hits += 1; return json.loads(v)
        self.misses += 1; out = fn()
        try:
            if self.r: self.r.setex(key, ttl, json.dumps(out))
            else: self.mem[key] = (json.dumps(out), time.time() + ttl)
        except Exception: pass
        return out
    def stats(self): n = self.hits + self.misses; return {"backend": self.backend, "hits": self.hits, "misses": self.misses, "hit_ratio": round(100 * self.hits / n, 1) if n else 0}
CACHE = Cache()
def cached(name, fn): return jsonify(CACHE.get(f"a:{g.uid}:{CACHE.ver(g.uid)}:{name}", 60, fn))

# ---------- JWT HS256 ----------
b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def unb64(s): return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
def jwt_make(uid, name, days=7):
    h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()); p = b64(json.dumps({"sub": uid, "name": name, "exp": int(time.time() + days * 86400)}).encode())
    return f"{h}.{p}." + b64(hmac.new(SECRET, f"{h}.{p}".encode(), hashlib.sha256).digest())
def jwt_check(t):
    try:
        h, p, s = t.split("."); good = b64(hmac.new(SECRET, f"{h}.{p}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(s, good): return None
        d = json.loads(unb64(p)); return d if d["exp"] > time.time() else None
    except Exception: return None
hpw = lambda pw, salt: hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 120000).hex()

# ---------- rate limit + auth guard ----------
HITS = collections.defaultdict(list)
@app.before_request
def guard():
    g.uid = 0
    if not request.path.startswith("/api/"): return
    key = request.headers.get("Authorization", "")[-24:] or request.remote_addr; now = time.time()
    HITS[key] = [x for x in HITS[key] if now - x < 60]
    if len(HITS[key]) >= RATE: return jsonify(error="rate limit exceeded (%d/min)" % RATE), 429
    HITS[key].append(now)
    if request.path in ("/api/auth/register", "/api/auth/login", "/api/health"): return
    d = jwt_check(request.headers.get("Authorization", "").replace("Bearer ", ""))
    if not d: return jsonify(error="unauthorized"), 401
    g.uid = d["sub"]
@app.after_request
def sec(r):
    if request.method != "GET" and g.get("uid") and r.status_code < 400: CACHE.bump(g.uid)
    r.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store" if request.path.startswith("/api/") else "public, max-age=60"}); return r
def body(): return request.get_json(silent=True) or {}
rows = lambda q, a=(): [dict(r) for r in db().execute(q, a)]

# ---------- auth (4) ----------
def log_session(uid):
    try:
        with db() as c: c.execute("INSERT INTO sessions(user_id,ts,ip,agent) VALUES(?,?,?,?)", (uid, datetime.now().isoformat(timespec="seconds"), request.remote_addr, (request.headers.get("User-Agent") or "")[:120]))
    except Exception: pass
@app.post("/api/auth/register")
def register():
    d = body(); n = (d.get("username") or "").strip().lower(); p = d.get("password") or ""
    if not re.fullmatch(r"[a-z0-9_.]{3,20}", n): return jsonify(error="Username: 3-20 letters, numbers, . or _"), 400
    if len(p) < 6: return jsonify(error="Password must be at least 6 characters"), 400
    salt = secrets.token_hex(16)
    try:
        with db() as c: cur = c.execute("INSERT INTO users(username,salt,pw,created) VALUES(?,?,?,?)", (n, salt, hpw(p, salt), datetime.now().isoformat(timespec="seconds")))
    except sqlite3.IntegrityError: return jsonify(error="That username is taken"), 409
    log_session(cur.lastrowid); return jsonify(token=jwt_make(cur.lastrowid, n), username=n), 201
@app.post("/api/auth/login")
def login():
    d = body(); n = (d.get("username") or "").strip().lower(); r = db().execute("SELECT * FROM users WHERE username=?", (n,)).fetchone()
    if not r or not hmac.compare_digest(r["pw"], hpw(d.get("password") or "", r["salt"])): return jsonify(error="Wrong username or password"), 401
    log_session(r["id"]); return jsonify(token=jwt_make(r["id"], n), username=n)
@app.post("/api/auth/refresh")
def refresh():
    r = db().execute("SELECT username FROM users WHERE id=?", (g.uid,)).fetchone()
    return (jsonify(token=jwt_make(g.uid, r["username"]), username=r["username"]) if r else (jsonify(error="unauthorized"), 401))
@app.get("/api/auth/me")
def me():
    r = db().execute("SELECT id,username,created FROM users WHERE id=?", (g.uid,)).fetchone(); return jsonify(dict(r)) if r else (jsonify(error="unauthorized"), 401)

# ---------- commands (5) ----------
def save_cmd(c, d, cid=None):
    c.execute("INSERT OR IGNORE INTO commands(user_id,cid,ts,source,command,response,category,ms,ok) VALUES(?,?,?,?,?,?,?,?,?)",
        (g.uid, cid or secrets.token_hex(8), d.get("ts") or datetime.now().isoformat(timespec="seconds"), d.get("source", "text"), str(d.get("command", ""))[:2000], str(d.get("response", ""))[:4000], d.get("category", "other"), int(d.get("ms", 0)), int(bool(d.get("ok", True)))))
@app.post("/api/commands/save")
def cmd_save():
    d = body()
    if not d.get("command"): return jsonify(error="command required"), 400
    with db() as c: save_cmd(c, d, d.get("cid"))
    return jsonify(ok=True), 201
@app.get("/api/commands/history")
def cmd_hist():
    q = request.args.get("q", ""); lim = min(int(request.args.get("limit", 200)), 1000); off = int(request.args.get("offset", 0))
    return jsonify(rows("SELECT * FROM commands WHERE user_id=? AND (command LIKE ? OR response LIKE ?) ORDER BY id DESC LIMIT ? OFFSET ?", (g.uid, f"%{q}%", f"%{q}%", lim, off)))
@app.delete("/api/commands/<int:i>")
def cmd_del(i):
    with db() as c: n = c.execute("DELETE FROM commands WHERE id=? AND user_id=?", (i, g.uid)).rowcount
    return (jsonify(ok=True) if n else (jsonify(error="not found"), 404))
@app.get("/api/commands/export")
def cmd_export():
    o = io.StringIO(); w = csv.writer(o); w.writerow(["id", "time", "source", "command", "response", "category", "ms", "ok"])
    for r in rows("SELECT * FROM commands WHERE user_id=? ORDER BY id", (g.uid,)): w.writerow([r[k] for k in ("id", "ts", "source", "command", "response", "category", "ms", "ok")])
    return Response(o.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=axor_history.csv"})

# ---------- settings (2) ----------
@app.get("/api/settings")
def st_get(): return jsonify({r["k"]: r["v"] for r in rows("SELECT k,v FROM settings WHERE user_id=?", (g.uid,))})
@app.put("/api/settings")
def st_put():
    with db() as c:
        for k, v in body().items():
            if re.fullmatch(r"[a-z_]{1,30}", k): c.execute("INSERT OR REPLACE INTO settings VALUES(?,?,?)", (g.uid, k, str(v)[:200]))
    return st_get()

# ---------- reminders / events / notes (9) ----------
def crud(name, cols, order):
    def lst(): return jsonify(rows(f"SELECT * FROM {name} WHERE user_id=? ORDER BY {order}", (g.uid,)))
    def add():
        d = body()
        if name == "notes" and not d.get("ts"): d["ts"] = datetime.now().isoformat(timespec="seconds")
        miss = [k for k in cols if not d.get(k)]
        if miss: return jsonify(error="missing: " + ", ".join(miss)), 400
        with db() as c: c.execute(f"INSERT OR IGNORE INTO {name}(user_id,cid,{','.join(cols)}) VALUES(?,?,{','.join('?'*len(cols))})", (g.uid, d.get("cid") or secrets.token_hex(8), *[str(d[k]) for k in cols]))
        return jsonify(ok=True), 201
    def rm(i):
        with db() as c: n = c.execute(f"DELETE FROM {name} WHERE id=? AND user_id=?", (i, g.uid)).rowcount
        return (jsonify(ok=True) if n else (jsonify(error="not found"), 404))
    app.add_url_rule(f"/api/{name}", f"{name}_l", lst, methods=["GET"]); app.add_url_rule(f"/api/{name}", f"{name}_a", add, methods=["POST"]); app.add_url_rule(f"/api/{name}/<int:i>", f"{name}_d", rm, methods=["DELETE"])
crud("reminders", ["text", "due"], "fired, due"); crud("events", ["title", "start"], "start"); crud("notes", ["ts", "text"], "id DESC")

# ---------- sync (1): idempotent batch upload from the offline client ----------
@app.post("/api/sync")
def sync():
    d = body(); n = {"commands": 0, "reminders": 0, "events": 0, "notes": 0, "conversations": 0}
    with db() as c:
        for x in d.get("commands", [])[:500]: save_cmd(c, x, x.get("cid")); n["commands"] += 1
        for x in d.get("reminders", [])[:500]:
            c.execute("INSERT OR REPLACE INTO reminders(user_id,cid,text,due,fired,kind) VALUES(?,?,?,?,?,?)", (g.uid, x["cid"], x["text"], x["due"], int(x.get("fired", 0)), x.get("kind", "reminder"))); n["reminders"] += 1
        for x in d.get("events", [])[:500]:
            c.execute("INSERT OR REPLACE INTO events(user_id,cid,title,start) VALUES(?,?,?,?)", (g.uid, x["cid"], x["title"], x["start"])); n["events"] += 1
        for x in d.get("notes", [])[:500]:
            c.execute("INSERT OR REPLACE INTO notes(user_id,cid,ts,text) VALUES(?,?,?,?)", (g.uid, x["cid"], x["ts"], x["text"])); n["notes"] += 1
        for x in d.get("conversations", [])[:500]:
            c.execute("INSERT OR REPLACE INTO conversations(user_id,cid,title,n,last) VALUES(?,?,?,?,?)", (g.uid, x["cid"], str(x.get("title") or "Chat")[:120], int(x.get("n", 0)), x.get("last", ""))); n["conversations"] += 1
    return jsonify(ok=True, synced=n)

# ---------- conversations, files, reminders/settings aliases, monthly analytics (10) ----------
@app.post("/api/conversations/save")
def conv_save():
    d = body()
    if not d.get("title"): return jsonify(error="title required"), 400
    with db() as c: c.execute("INSERT OR REPLACE INTO conversations(user_id,cid,title,n,last) VALUES(?,?,?,?,?)", (g.uid, d.get("cid") or secrets.token_hex(8), str(d["title"])[:120], int(d.get("n", 0)), d.get("last") or datetime.now().isoformat(timespec="seconds")))
    return jsonify(ok=True), 201
@app.get("/api/conversations/list")
def conv_list(): return jsonify(rows("SELECT * FROM conversations WHERE user_id=? ORDER BY last DESC LIMIT 200", (g.uid,)))
@app.post("/api/files/upload")
def file_up():
    d = body()
    if not (d.get("name") and str(d.get("url", "")).startswith("https://")): return jsonify(error="name and https url required"), 400
    with db() as c: c.execute("INSERT OR IGNORE INTO files(user_id,cid,name,url,ts) VALUES(?,?,?,?,?)", (g.uid, d.get("cid") or secrets.token_hex(8), str(d["name"])[:200], d["url"][:500], datetime.now().isoformat(timespec="seconds")))
    return jsonify(ok=True), 201
@app.get("/api/files")
def file_list(): return jsonify(rows("SELECT * FROM files WHERE user_id=? ORDER BY id DESC LIMIT 200", (g.uid,)))
@app.delete("/api/files/<int:i>")
def file_del(i):
    with db() as c: n = c.execute("DELETE FROM files WHERE id=? AND user_id=?", (i, g.uid)).rowcount
    return (jsonify(ok=True) if n else (jsonify(error="not found"), 404))
@app.post("/api/reminders/create")
def rem_create():
    d = body(); miss = [k for k in ("text", "due") if not d.get(k)]
    if miss: return jsonify(error="missing: " + ", ".join(miss)), 400
    with db() as c: c.execute("INSERT OR IGNORE INTO reminders(user_id,cid,text,due,kind) VALUES(?,?,?,?,?)", (g.uid, d.get("cid") or secrets.token_hex(8), str(d["text"]), str(d["due"]), d.get("kind", "reminder")))
    return jsonify(ok=True), 201
@app.get("/api/reminders/upcoming")
def rem_upcoming(): return jsonify(rows("SELECT * FROM reminders WHERE user_id=? AND fired=0 AND due>=? ORDER BY due LIMIT 50", (g.uid, datetime.now().isoformat(timespec="minutes"))))
@app.put("/api/settings/update")
def st_update(): return st_put()
@app.get("/api/analytics/monthly")
def a_month(): return cached("month", lambda: rows("SELECT substr(ts,1,7) month, COUNT(*) n, ROUND(AVG(ms),1) avg_ms FROM commands WHERE user_id=? GROUP BY month ORDER BY month DESC LIMIT 12", (g.uid,))[::-1])

# ---------- analytics (4) + health (1) ----------
@app.get("/api/analytics/summary")
def a_sum(): return cached("sum", _sum)
def _sum():
    r = db().execute("SELECT COUNT(*) n, COALESCE(AVG(ms),0) a, COALESCE(SUM(ok),0) o, COALESCE(SUM(source='voice'),0) v FROM commands WHERE user_id=?", (g.uid,)).fetchone()
    n = r["n"]; return dict(total=n, avg_ms=round(r["a"], 1), success=round(100 * r["o"] / n) if n else 0, voice=r["v"], text=n - r["v"])
@app.get("/api/analytics/daily")
def a_day(): return cached("day", lambda: rows("SELECT substr(ts,1,10) day, COUNT(*) n FROM commands WHERE user_id=? GROUP BY day ORDER BY day DESC LIMIT 14", (g.uid,))[::-1])
@app.get("/api/analytics/weekly")
def a_week(): return cached("week", lambda: rows("SELECT strftime('%Y-W%W', ts) week, COUNT(*) n, ROUND(AVG(ms),1) avg_ms FROM commands WHERE user_id=? GROUP BY week ORDER BY week DESC LIMIT 8", (g.uid,))[::-1])
@app.get("/api/analytics/categories")
def a_cat(): return cached("cat", lambda: rows("SELECT category, COUNT(*) n FROM commands WHERE user_id=? GROUP BY category ORDER BY n DESC", (g.uid,)))
@app.get("/api/cache/stats")
def cache_stats(): return jsonify(CACHE.stats())
@app.get("/api/health")
def health(): return jsonify(status="ok", service="axor-cloud", time=datetime.now().isoformat(timespec="seconds"))

# ---------- dashboard (static React build) ----------
STATIC = os.path.join(BASE, "static")
@app.route("/", defaults={"p": ""})
@app.route("/<path:p>")
def spa(p):
    if p.startswith("api/"): return jsonify(error="not found"), 404
    f = os.path.join(STATIC, p)
    if p and os.path.isfile(f): return send_from_directory(STATIC, p)
    return send_from_directory(STATIC, "index.html") if os.path.exists(os.path.join(STATIC, "index.html")) else ("Dashboard not built", 404)

if __name__ == "__main__":
    print("\n  Axor Cloud -> http://localhost:8080\n"); app.run(host="127.0.0.1", port=8080, threaded=True)
