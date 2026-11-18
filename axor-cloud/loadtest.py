"""Load test for the Axor cloud API. Usage: python loadtest.py [base_url] [workers] [seconds]
Measures real latency percentiles on whatever machine you run it on."""
import sys, time, json, threading, statistics, urllib.request
B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
W = int(sys.argv[2]) if len(sys.argv) > 2 else 20
S = int(sys.argv[3]) if len(sys.argv) > 3 else 10
READONLY = len(sys.argv) > 4 and sys.argv[4] == "readonly"   # dashboard-viewing scenario: no writes
def call(path, tok=None, body=None):
    h = {"Content-Type": "application/json"}
    if tok: h["Authorization"] = "Bearer " + tok
    r = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=10) as x: return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, {}
u = "load%d" % int(time.time()); st, d = call("/api/auth/register", body={"username": u, "password": "secret1"}); tok = d.get("token")
for i in range(50): call("/api/commands/save", tok, {"command": f"c{i}", "category": "system", "ms": 5, "ok": 1})
lat = {"analytics": [], "history": [], "write": []}; codes = {}; stop = time.time() + S; lock = threading.Lock()
def worker(n):
    i = 0
    while time.time() < stop:
        i += 1; k = ["analytics", "history", "write"][i % (2 if READONLY else 3)]
        p, b = {"analytics": ("/api/analytics/summary", None), "history": ("/api/commands/history", None), "write": ("/api/commands/save", {"command": f"w{n}-{i}", "category": "system", "ms": 3, "ok": 1})}[k]
        t = time.perf_counter(); c, _ = call(p, tok, b); dt = (time.perf_counter() - t) * 1000
        with lock: lat[k].append(dt); codes[c] = codes.get(c, 0) + 1
ts = [threading.Thread(target=worker, args=(n,)) for n in range(W)]; t0 = time.time(); [t.start() for t in ts]; [t.join() for t in ts]; el = time.time() - t0
al = sum(lat.values(), []); q = lambda a, p: sorted(a)[min(len(a) - 1, int(len(a) * p))]
print(f"workers={W} duration={el:.1f}s requests={len(al)} throughput={len(al)/el:.0f} req/s status_codes={codes}")
for k, a in lat.items():
    if a: print(f"  {k:9s} n={len(a):5d} p50={q(a,.5):7.1f}ms p95={q(a,.95):7.1f}ms p99={q(a,.99):7.1f}ms")
print(f"  overall   p50={q(al,.5):.1f}ms p95={q(al,.95):.1f}ms p99={q(al,.99):.1f}ms")
print("  cache:", call("/api/cache/stats", tok)[1])
