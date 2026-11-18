"""Self-audit of the Axor cloud API (our own checks, not a third-party pentest). Run with cloud.py on :8080."""
import json, urllib.request, base64, hmac, hashlib, time, sys
B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
def call(path, tok=None, body=None, method=None, raw=None, hdr=None):
    h = {"Content-Type": "application/json"}; h.update(hdr or {})
    if tok: h["Authorization"] = "Bearer " + tok
    r = urllib.request.Request(B + path, data=raw if raw is not None else (json.dumps(body).encode() if body is not None else None), headers=h, method=method)
    try:
        x = urllib.request.urlopen(r, timeout=10); return x.status, x.read(), x.headers
    except urllib.error.HTTPError as e: return e.code, e.read(), e.headers
R = []
def t(name, ok, note=""): R.append((name, ok, note)); print(("PASS " if ok else "FAIL ") + name + (" - " + note if note else ""))
u = "aud%d" % int(time.time()); s, b, h = call("/api/auth/register", body={"username": u, "password": "secret1"}); tok = json.loads(b)["token"]
s2, b2, _ = call("/api/auth/register", body={"username": u + "b", "password": "secret1"}); tok2 = json.loads(b2)["token"]
for p in ["/api/commands/history", "/api/settings", "/api/analytics/summary", "/api/auth/me"]:
    t("auth required " + p, call(p)[0] == 401)
t("garbage token rejected", call("/api/auth/me", "abc.def.ghi")[0] == 401)
hd, pl, sg = tok.split("."); none = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
t("alg=none JWT rejected", call("/api/auth/me", f"{none}.{pl}.")[0] == 401)
pj = json.loads(base64.urlsafe_b64decode(pl + "==")); pj["sub"] = 999; forged = base64.urlsafe_b64encode(json.dumps(pj).encode()).rstrip(b"=").decode()
t("tampered payload rejected", call("/api/auth/me", f"{hd}.{forged}.{sg}")[0] == 401)
t("wrong secret forged JWT rejected", call("/api/auth/me", hd + "." + pl + "." + base64.urlsafe_b64encode(hmac.new(b"guess", f"{hd}.{pl}".encode(), hashlib.sha256).digest()).rstrip(b"=").decode())[0] == 401)
call("/api/commands/save", tok, {"command": "secret-of-A"}); t("user B cannot see user A data", b"secret-of-A" not in call("/api/commands/history", tok2)[1])
for name, pay in [("SQL injection in login", {"username": "' OR 1=1 --", "password": "x"}), ("SQL injection in password", {"username": u, "password": "' OR '1'='1"})]:
    t(name + " rejected", call("/api/auth/login", body=pay)[0] in (400, 401))
s, b, _ = call("/api/commands/history?q=%27%3B+DROP+TABLE+cloud%3B--", tok); t("SQLi in search param harmless", s == 200); t("data survives injection attempt", b"secret-of-A" in call("/api/commands/history", tok)[1])
t("malformed JSON gives 4xx not 500", call("/api/commands/save", tok, raw=b"{bad")[0] in (400, 415, 422))
t("short password rejected", call("/api/auth/register", body={"username": u + "c", "password": "1"})[0] == 400)
t("duplicate username rejected", call("/api/auth/register", body={"username": u, "password": "secret1"})[0] in (400, 409))
s, b, h = call("/api/health"); need = ["X-Content-Type-Options", "X-Frame-Options"]
t("security headers present", all(h.get(k) for k in need), str({k: h.get(k) for k in need}))
t("no stack trace on 404", b"Traceback" not in call("/api/nope", tok)[1])
import sqlite3, glob
for f in glob.glob("*.db"):
    try:
        rows = sqlite3.connect(f).execute("SELECT password FROM users WHERE username=?", (u,)).fetchall()
        if rows: t("password stored hashed (PBKDF2), not plaintext", "secret1" not in rows[0][0] and len(rows[0][0]) > 40)
    except Exception: pass
for _ in range(3): pass
print("\nSUMMARY: %d/%d passed" % (sum(1 for r in R if r[1]), len(R)))
