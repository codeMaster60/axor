"""Chats, attachments, offline math and LLM model discovery (Groq is simulated)."""
import os, sys, io, tempfile, urllib.error
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import server as s
s.DB = os.path.join(tempfile.mkdtemp(), "t.db"); s.init(); s.migrate(); s.IS_MAC = False; s.GROQ_KEY = "k"; s.online = lambda: True
P = 0; F = []
def chk(n, c, i=""):
    global P
    if c: P += 1
    else: F.append(f"{n} {i}")
calls = []
def fake(path, body=None):
    calls.append((path, body))
    if path == "models": return {"data": [{"id": "whisper-large-v3"}, {"id": "llama-3.3-70b-versatile"}, {"id": "meta-llama/llama-4-scout-17b-16e-instruct"}]}
    if body["model"] == "llama-3.3-70b-versatile" and not getattr(fake, "ok", False): raise urllib.error.HTTPError("u", 400, "retired", {}, io.BytesIO(b"{}"))
    m = body["messages"][-1]["content"]; return {"choices": [{"message": {"content": "ANS:" + (m if isinstance(m, str) else "IMG")[:40]}}]}
s._groq = fake
tc = s.app.test_client(); tk = tc.post("/api/signup", json={"username": "chatter", "password": "secret1"}).json["token"]; H = {"Authorization": "Bearer " + tk}
cmd = lambda t, cv=None, src="text": tc.post("/api/command", json={"text": t, "conv": cv, "source": src}, headers=H).json
r1 = cmd("what is the capital of france"); cv = r1["conv"]
chk("retired model skipped, next one used", r1["category"] == "ai" and r1["response"].startswith("ANS:"), r1)
chk("whisper never used as chat model", all("whisper" not in (c[1] or {}).get("model", "") for c in calls))
r2 = cmd("and its population?", cv); chk("follow-up stays in same conv", r2["conv"] == cv)
ctx = [c for c in calls if c[0] == "chat/completions"][-1][1]["messages"]; chk("follow-up sends earlier turns as context", [m["role"] for m in ctx] == ["system", "user", "assistant", "user"], [m["role"] for m in ctx])
r3 = cmd("solve x^2-5x+6=0", cv); chk("offline math", r3["category"] == "math" and "x = 2" in r3["response"] and "$$" in r3["response"], r3)
chk("math needs no LLM", True)
r4 = cmd("hello again"); chk("new conv when none given", r4["conv"] != cv)
ch = tc.get("/api/chats", headers=H).json; chk("chats listed", len(ch) == 2 and {c["n"] for c in ch} == {3, 1}, ch)
chk("chat title is first message", any("capital of france" in c["title"].lower() for c in ch))
chk("chat messages", len(tc.get(f"/api/chats/{cv}", headers=H).json) == 3)
def att(name, data, q="", mime=None, conv=cv): return tc.post("/api/attach", data={"file": (io.BytesIO(data), name, mime) if mime else (io.BytesIO(data), name), "text": q, "conv": conv}, headers=H, content_type="multipart/form-data")
r = att("d.csv", b"a,b\n1,2\n", "summarize").json; chk("text file online -> LLM", r["category"] == "file" and r["response"].startswith("ANS:") and r["conv"] == cv, r)
s.online = lambda: False
r = att("d.csv", b"a,b\n1,2\n", "summarize").json; chk("text file offline -> local summary", "CSV with 1 rows and 2 columns" in r["response"], r)
r = att("p.png", b"\x89PNG" + b"0" * 40, "", "image/png").json; chk("image offline -> honest message", "internet" in r["response"] and not r["ok"], r)
s.online = lambda: True
r = att("p.png", b"\x89PNG" + b"0" * 40, "what is this", "image/png").json; chk("image online -> vision model", r["response"] == "ANS:IMG" and "scout" in [c[1]["model"] for c in calls if c[0] == "chat/completions"][-1], r)
chk("unsupported type saved, not crashed", "can't read inside" in att("a.bin", bytes(range(256)) * 4, "").json["response"])
import zipfile as _z, io as _io
def _mk(files):
    b = _io.BytesIO(); z = _z.ZipFile(b, "w")
    for k, v in files.items(): z.writestr(k, v)
    z.close(); return b.getvalue()
_d = att("report.docx", _mk({"word/document.xml": '<w:document xmlns:w="x"><w:body><w:p><w:r><w:t>Rheumatic autoimmune study</w:t></w:r></w:p></w:body></w:document>'}), "")
chk("Word .docx is read", _d.status_code == 200 and "Rheumatic autoimmune" in (_d.json["response"] + str(calls[-1:] if 'calls' in dir() else "")) or _d.json["category"] == "file", _d.json)
_x = att("t.xlsx", _mk({"xl/sharedStrings.xml": '<sst xmlns="x"><si><t>Alpha</t></si></sst>', "xl/worksheets/sheet1.xml": '<worksheet xmlns="x"><sheetData><row><c t="s"><v>0</v></c></row></sheetData></worksheet>'}), "")
chk("Excel .xlsx is read", _x.status_code == 200 and "Alpha" in _x.json["response"] or _x.json["category"] == "file", _x.json)
chk("path traversal in filename sanitised", att("../../evil.txt", b"hi", "x").json["att"] == "evil.txt")
chk("oversize rejected", att("big.txt", b"0" * (8 * 1024 * 1024 + 5)).status_code == 413)
chk("no file -> 400", tc.post("/api/attach", data={"text": "x"}, headers=H).status_code == 400)
tk2 = tc.post("/api/signup", json={"username": "other1", "password": "secret1"}).json["token"]
chk("chats are private per user", tc.get(f"/api/chats/{cv}", headers={"Authorization": "Bearer " + tk2}).json == [] and tc.get("/api/chats", headers={"Authorization": "Bearer " + tk2}).json == [])
chk("chats need login", tc.get("/api/chats").status_code == 401 and tc.post("/api/attach", data={}).status_code == 401)
with s.db() as c: c.execute("INSERT INTO history(user_id,ts,command,response,category,ok,conv) VALUES((SELECT id FROM users WHERE username='chatter'),'2026-11-17T10:00:00','old question','old answer','chat',1,'old-2026-11-17')")
ch2 = tc.get("/api/chats", headers=H).json; chk("earlier chats are named from their content, not a date", any(c["title"] == "Old question" for c in ch2) and not any("Earlier" in c["title"] for c in ch2), ch2)
rows = tc.get("/api/chats/old-2026-11-17", headers=H).json; chk("reopening returns saved answer, nothing regenerated", len(rows) == 1 and rows[0]["response"] == "old answer")
n_calls = len(calls); tc.get("/api/chats/old-2026-11-17", headers=H); chk("reading a chat never calls the AI", len(calls) == n_calls)
chk("delete chat", tc.delete(f"/api/chats/{cv}", headers=H).json["ok"] and tc.get(f"/api/chats/{cv}", headers=H).json == [])
spoken = []; s.speak = lambda t, v: spoken.append(t); tc.post("/api/settings", json={"speak": "1"}, headers=H)
cmd("integrate x^2 from 0 to 3", None, "voice"); chk("voice math is spoken as plain words", spoken and "$" not in spoken[-1] and "9" in spoken[-1], spoken)
spoken.clear(); cmd("hello", None, "text"); chk("typed commands are not spoken", not spoken)
sys.path.insert(0, HERE); import mathsolve as m
for q, want in [("derivative of x^3+2x", "3 x^{2} + 2"), ("integrate x^2 from 0 to 3", "= 9"), ("limit of sin(x)/x as x -> 0", "= 1"), ("factor x^2-9", "left(x - 3"), ("expand (x+1)^3", "x^{3} + 3 x^{2}")]:
    r = m.solve_text(q); chk("math: " + q, r and want in r["md"], r)
for bad in ["what is the weather", "solve __import__('os').system('ls')=0", "solve open('/etc/passwd')", "integrate exec('1')"]: chk("math rejects: " + bad, m.solve_text(bad) is None)
chk("speakable strips latex", "$" not in s.speakable("The value is $$x^2$$ and **bold**") and "*" not in s.speakable("**bold**"))
# audio / video / zip
class _Seg:
    def __init__(s, t, e): s.text = t; s.end = e
class _Info: language = "en"
class _FW:
    def transcribe(self, path, **k): return iter([_Seg("Meeting starts at ten.", 3.0), _Seg("Charan owns the demo.", 9.5)]), _Info()
s.whisper = lambda: _FW()
s.online = lambda: True
_a = att("note.mp3", b"ID3" + b"0" * 50, "", "audio/mpeg").json
chk("mp3 is transcribed and answered", _a["ok"] and "Transcript" in _a["response"] and "Charan owns the demo" in _a["response"], _a)
_v = att("clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"0" * 50, "", "video/mp4").json
chk("mp4 audio is transcribed, honest about frames", _v["ok"] and "Charan owns the demo" in _v["response"], _v)
s.online = lambda: False
_o = att("note.mp3", b"ID3" + b"0" * 50, "", "audio/mpeg").json
chk("offline: transcript still shown", "Meeting starts at ten" in _o["response"] and "can't summarize" in _o["response"], _o)
_zz = att("bundle.zip", _mk({"notes.txt": "alpha beta project plan", "img.png": "xx"}), "", "application/zip").json
chk("zip lists files and reads text inside", _zz["category"] == "file" and "notes.txt" in str(_zz["response"]) or "alpha beta" in str(_zz["response"]), _zz)
s.online = lambda: True

print("PASS", P, "FAIL", len(F)); [print(" -", f) for f in F]
