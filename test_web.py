"""Tests for webtools + new server features. No network: http_get is mocked."""
import os, sys, json, tempfile, importlib
os.environ["AXOR_TEST"] = "1"
import webtools as wt
P = F = 0
def ok(c, m):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL", m)

WIKI = {"query": {"pages": {"1": {"index": 1, "title": "A. R. Rahman", "fullurl": "https://en.wikipedia.org/wiki/A._R._Rahman",
        "extract": "Allah Rakha Rahman is an Indian composer, singer and music producer. Born 6 January 1967.", "thumbnail": {"source": "https://upload.wikimedia.org/a.jpg"}}}}}
COM = {"query": {"pages": {"5": {"index": 1, "title": "File:Rahman live.jpg", "imageinfo": [{"thumburl": "https://upload.wikimedia.org/b.jpg", "url": "https://upload.wikimedia.org/b_full.jpg",
       "descriptionurl": "https://commons.wikimedia.org/wiki/File:Rahman_live.jpg", "mime": "image/jpeg", "width": 2000, "height": 1500,
       "extmetadata": {"Artist": {"value": "<a href='x'>Jane Doe</a>"}, "LicenseShortName": {"value": "CC BY-SA 4.0"}}}]}}}}
DDG = '<div class="result results_links results_links_deep web-result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fp&rut=1">Example <b>Page</b></a><a class="result__snippet">Some snippet text</a></div>'
def fake(url, timeout=6, headers=None):
    if "commons.wikimedia" in url: return json.dumps(COM)
    if "wikipedia.org" in url: return json.dumps(WIKI)
    if "duckduckgo" in url: return DDG
    raise OSError("blocked")
wt.http_get = fake

ok(wt.image_intent("can u give me an image of AR RAHMAN??") == ("photo", "AR RAHMAN", 3), "intent photo")
ok(wt.image_intent("show me photos of the Taj Mahal")[2] == 6, "plural count")
ok(wt.image_intent("generate an image of a dragon over mountains")[0] == "generate", "gen")
ok(wt.image_intent("what is the capital of france") is None, "no intent")
ok(wt.image_intent("what does a red panda look like")[1] == "a red panda", "look like")
a = wt.image_flow("photo", "AR RAHMAN", 3)
ok("![" in a and "upload.wikimedia.org/a.jpg" in a and "Jane Doe" in a, "photo answer has images+credit")
g = wt.image_flow("generate", "a dragon", 1)
ok("image.pollinations.ai" in g, "generated for non person")
g2 = wt.image_flow("generate", "A. R. Rahman", 1)
ok("don't generate pictures of real people" in g2 and "image.pollinations.ai" not in g2, "no real-person generation")
s = wt.build_sources("who is ar rahman")
ok(len(s) >= 2 and s[0]["source"] == "Wikipedia" and any(x["url"] == "https://example.com/p" for x in s), "sources")
f = wt.finish_with_sources("He is a composer [1]. Also known for film scores [2].", s)
ok("[1](https://en.wikipedia.org" in f and "**Sources**" in f, "citations linked")
ok(wt.wants_sources("who is the prime minister of india") and wt.wants_sources("latest news about electric cars") and wt.wants_sources("explain photosynthesis with sources"), "wants_sources yes")
ok(wt.wants_sources("malaika arora") and wt.wants_sources("taj mahal") and wt.wants_sources("elon musk"), "bare names are lookups")
ok(wt.image_intent("can u show me her photos?", lambda: "Malaika Arora") == ("photo", "Malaika Arora", 6), "pronoun image request uses the topic")
ok(wt.image_intent("show me her photos") is None, "pronoun without topic falls through")
ok(wt.image_intent("show me malaika arora photos") == ("photo", "malaika arora", 6), "name photos")
ok(wt.image_intent("more pictures", "Taj Mahal")[1] == "Taj Mahal", "more pictures")
ok(wt.image_intent("show me my photos") is None, "my photos is not a web search")
for q in ("How are you, bro?", "How's life? How's your girlfriend?", "hello there", "write a poem about rain", "what is the time", "can you help me plan my day?", "why is the sky blue?", "good morning", "yes please", "open chrome", "thank you", "what next"): ok(not wt.wants_sources(q), "no sources: " + q)
ok("Sources searched" in wt.finish_with_sources("No citations here.", s), "uncited answers still show the sources searched")
ok(wt.smart_title("can you please tell me what is photosynthesis?") == "What is photosynthesis", wt.smart_title("can you please tell me what is photosynthesis?"))
ok(len(wt.smart_title("explain " + "word " * 30)) <= 41, "title length")
ok(wt.clean_ai_title('Title: "Photosynthesis basics".') == "Photosynthesis basics", "clean title")
wt.http_get = lambda *a, **k: (_ for _ in ()).throw(OSError("down"))
ok("couldn't fetch" in wt.image_flow("photo", "x", 3) or "couldn't find" in wt.image_flow("photo", "x", 3), "offline fail soft")

# server-level
d = tempfile.mkdtemp(); os.chdir(d)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server as sv
sv.DB = os.path.join(d, "t.db"); sv.init(); sv.migrate()
sv.GROQ_KEY = ""; sv.online = lambda: True
c = sv.app.test_client()
r = c.post("/api/signup", json={"username": "tester1", "password": "secret12"}).get_json(); H = {"Authorization": "Bearer " + r["token"]}
wt.http_get = fake
j = c.post("/api/command", json={"text": "can u give me an image of AR RAHMAN??", "conv": "c1"}, headers=H).get_json()
ok(j["category"] == "image" and "![" in j["response"], "server image route")
ok(j["title"].lower().startswith("can u give") or j["title"], "title returned")
ch = c.get("/api/chats", headers=H).get_json(); ok(ch and ch[0]["title"] and "Earlier" not in ch[0]["title"], "chat auto title")
ok(c.put("/api/chats/c1", json={"title": "Rahman pics"}, headers=H).get_json()["title"] == "Rahman pics", "rename")
ok(c.get("/api/chats?q=Rahman", headers=H).get_json()[0]["title"] == "Rahman pics", "chat search + renamed")
sv.online = lambda: False
j = c.post("/api/command", json={"text": "show me photos of cats", "conv": "c2"}, headers=H).get_json(); ok("internet" in j["response"], "offline image honest")
# notes / reminders / analytics
c.post("/api/notes", json={"text": "buy milk"}, headers=H); n = c.get("/api/notes", headers=H).get_json(); ok(n and n[0]["text"] == "buy milk", "note add")
c.delete(f"/api/notes/{n[0]['id']}", headers=H); ok(c.get("/api/notes", headers=H).get_json() == [], "note del")
rm = c.post("/api/reminders", json={"text": "x", "due": "2030-01-01T10:00"}, headers=H).get_json()[0]["id"]
c.patch(f"/api/reminders/{rm}", json={"snooze": 10}, headers=H); ok(c.get("/api/reminders", headers=H).get_json()[0]["due"] == "2030-01-01T10:10", "snooze")
c.patch(f"/api/reminders/{rm}", json={"done": True}, headers=H); ok(c.get("/api/reminders", headers=H).get_json()[0]["fired"] == 1, "done")
a = c.get("/api/analytics", headers=H).get_json(); ok(a["total"] >= 2 and "top" in a and a["chats"] >= 2 and a["today"] >= 2, "analytics")
# legacy split
import sqlite3
with sv.db() as cx:
    for ts, cmd in (("2026-11-10T09:00:00", "a"), ("2026-11-10T09:05:00", "b"), ("2026-11-10T15:00:00", "c")):
        cx.execute("INSERT INTO history(user_id,ts,source,command,response,category,ms,ok,conv) VALUES(1,?,?,?,?,?,?,?,?)", (ts, "text", cmd, "r", "x", 1, 1, "old-2026-11-10"))
sv.split_legacy(); cs = {x["conv"] for x in c.get("/api/chats", headers=H).get_json()}
ok({"old-2026-11-10-1", "old-2026-11-10-2"} <= cs, f"legacy split {cs}")
ok(wt.wants_sources("give me details about Rahul Madeti"), "details-about triggers search")
sv.conv_context = lambda n=8: [{"role": "user", "content": "who is rahul madeti"}, {"role": "assistant", "content": "x"}]
ok(sv.search_query("yeah please give me") == "who is rahul madeti yeah please give me", "follow-up inherits topic")
ok(sv.search_query("what is the capital of france") == "what is the capital of france", "normal question unchanged")

# skills
sk = c.get("/api/skills", headers=H).get_json(); ok(len(sk["skills"]) >= 20 and not any(x["installed"] for x in sk["skills"]), "skills catalog, none installed")
ok(c.post("/api/skills/tutor/install", headers=H, json={}).get_json()["enabled"], "install enables")
sv.CUR.uid = c.get("/api/me", headers=H).get_json().get("id", 1)
with sv.app.test_request_context(headers=H): pass
ok("Study Tutor" in c.get("/api/skills", headers=H).get_json()["skills"][5]["name"] and c.get("/api/skills", headers=H).get_json()["active"] == 1, "active count")
ids = ["email-writer", "proofreader", "rewriter", "social-posts"]
for i in ids: c.post(f"/api/skills/{i}/install", headers=H, json={})
r = c.post("/api/skills/storyteller/install", headers=H, json={}).get_json(); ok(r["enabled"] is False and r["note"], "6th skill added but not enabled (cap 5)")
ok(c.post("/api/skills/storyteller/toggle", headers=H, json={"enabled": True}).status_code == 409, "cap blocks enabling")
c.post("/api/skills/proofreader/toggle", headers=H, json={"enabled": False}); ok(c.post("/api/skills/storyteller/toggle", headers=H, json={"enabled": True}).get_json()["enabled"], "toggle after freeing a slot")
cu = c.post("/api/skills", headers=H, json={"name": "Pirate Mode", "desc": "Talks like a pirate", "instructions": "Answer every question like a cheerful pirate."}).get_json(); ok(cu["ok"], "custom skill")
ok(c.post("/api/skills", headers=H, json={"name": "x", "instructions": "y"}).status_code == 400, "custom validation")
c.delete("/api/skills/" + cu["id"], headers=H); ok(all(x["id"] != cu["id"] for x in c.get("/api/skills", headers=H).get_json()["skills"] if x["custom"]), "custom removed")
c.delete("/api/skills/tutor", headers=H); ok(not [x for x in c.get("/api/skills", headers=H).get_json()["skills"] if x["id"] == "tutor"][0]["installed"], "uninstall")
import skills_catalog as _k; ok(all(len(x["instructions"]) > 40 for x in _k.CATALOG), "catalog instructions present")

cap = {}
sv.online = lambda: True; sv.GROQ_KEY = "k"
sv._chat = lambda msgs, vision=False: ((cap.update(sys=msgs[0]["content"]) if msgs[0]["content"].startswith("You are Axor") else None) or ("ok answer", None))
c.post("/api/skills/email-writer/toggle", headers=H, json={"enabled": True})
c.post("/api/command", json={"text": "explain how recursion works in programming", "conv": "sk1"}, headers=H)
ok("Email Writer" in cap.get("sys", "") and "switched on these skills" in cap.get("sys", ""), "enabled skill reaches the prompt")
c.post("/api/skills/email-writer/toggle", headers=H, json={"enabled": False}); c.post("/api/skills/storyteller/toggle", headers=H, json={"enabled": False})
for i in ("social-posts", "rewriter"): c.post(f"/api/skills/{i}/toggle", headers=H, json={"enabled": False})
c.post("/api/command", json={"text": "explain how loops work in programming", "conv": "sk2"}, headers=H)
ok("Email Writer" not in cap.get("sys", ""), "disabled skill is not in the prompt")
import docreader, zipfile
def mk(name, files):
    pth = os.path.join(d, name); z = zipfile.ZipFile(pth, "w")
    for k, v in files.items(): z.writestr(k, v)
    z.close(); return pth
t, n = docreader.read_text(mk("a.docx", {"word/document.xml": '<w:document xmlns:w="x"><w:body><w:p><w:r><w:t>Rheumatic autoimmune</w:t></w:r></w:p><w:p><w:r><w:t>Second para</w:t></w:r></w:p></w:body></w:document>'}), "a.docx")
ok(t == "Rheumatic autoimmune\nSecond para", "docx text " + repr(t))
t, n = docreader.read_text(mk("b.pptx", {"ppt/slides/slide1.xml": '<p:sld xmlns:a="y" xmlns:p="x"><a:p><a:r><a:t>Slide one</a:t></a:r></a:p></p:sld>'}), "b.pptx"); ok("Slide one" in t, "pptx")
t, n = docreader.read_text(mk("c.xlsx", {"xl/sharedStrings.xml": '<sst xmlns="x"><si><t>Name</t></si></sst>', "xl/worksheets/sheet1.xml": '<worksheet xmlns="x"><sheetData><row><c t="s"><v>0</v></c><c><v>7</v></c></row></sheetData></worksheet>'}), "c.xlsx"); ok("Name | 7" in t, "xlsx")
open(os.path.join(d, "r.rtf"), "w").write(r"{\\rtf1\\ansi Hello \\b world\\b0\\par Line two}"); ok("Hello" in docreader.read_text(os.path.join(d, "r.rtf"), "r.rtf")[0], "rtf")
open(os.path.join(d, "x.weird"), "w").write("plain words in odd extension"); ok("plain words" in docreader.read_text(os.path.join(d, "x.weird"), "x.weird")[0], "unknown ext text")
ok(docreader.read_text(mk("bad.docx", {"x": "y"}), "bad.docx")[0] == "" , "docx without document.xml fails soft")
print(f"{P} passed, {F} failed"); sys.exit(1 if F else 0)
