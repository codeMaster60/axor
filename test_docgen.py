import io, zipfile
from datetime import date
import docgen as g
n = f = 0
def ok(c, m):
    global n, f; n += 1
    if not c: f += 1; print("FAIL", m)
T = date(2026, 11, 19)
ok(g.parse_day("on november 18, 2026", T)[0] == date(2026, 11, 18), "month day year")
ok(g.parse_day("18 nov", T)[0] == date(2026, 11, 18), "day month")
ok(g.parse_day("calendar for 18/11", T)[0] == date(2026, 11, 18), "dd/mm")
ok(g.parse_day("tomorrow", T)[0] == date(2026, 11, 20) and g.parse_day("yesterday", T)[0] == date(2026, 11, 18), "tomorrow yesterday")
ok(g.parse_day("this week", T)[1] == 7, "week range")
ok(g.parse_day("what's on friday", T)[0] == date(2026, 11, 20), "weekday")
ok(g.parse_day("my schedule", T)[0] == T, "default today")
for q in ("write my assignment on machine learning", "give me an essay about climate change", "help me write a cover letter for an internship", "write a report on solar energy in 500 words"): ok(g.is_doc_request(q), q)
for q in ("open chrome", "what is an essay", "add a note buy milk", "make a logo", "tell me a joke"): ok(not g.is_doc_request(q), q)
b = g.make_docx("# T\n\n## H\nHello **b** *i*.\n\n- x\n1. y\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
z = zipfile.ZipFile(io.BytesIO(b)); ok("word/document.xml" in z.namelist() and b"<w:tbl>" in z.read("word/document.xml"), "docx structure")
try:
    import docx; d = docx.Document(io.BytesIO(b)); ok(d.paragraphs[0].text == "T" and len(d.tables) == 1, "python-docx opens it")
except ImportError: pass
from datetime import datetime as _dt
N = _dt(2026, 11, 19, 0, 50)
e = g.parse_event("add a task submit DAA assignment on 25 november at 5 pm to my google calendar", N); ok(e and e["title"] == "Submit DAA assignment" and e["start"] == _dt(2026, 11, 25, 17, 0) and not e["all_day"], "event title+time")
e = g.parse_event("add birthday of Rahul on 25 december", N); ok(e and e["all_day"] and e["repeat"] and e["start"].date() == date(2026, 12, 25), "birthday all-day yearly")
e = g.parse_event("schedule a meeting with rahul tomorrow at 5 pm", N); ok(e and e["title"] == "Meeting with rahul" and e["start"] == _dt(2026, 11, 20, 17, 0), "meeting tomorrow")
e = g.parse_event("create an event team lunch on 22nd at 1 pm for 2 hours", N); ok(e and (e["end"] - e["start"]).seconds == 7200 and e["title"] == "Team lunch", "duration")
ok(not g.is_event_request("what's on my calendar tomorrow") and not g.is_event_request("add a note buy milk") and not g.is_event_request("open calendar"), "not an event")
ok(g.is_event_request("put dentist appointment on friday at 10:30 am in calendar"), "put in calendar")
e = g.parse_event("On 20th November, it is my girlfriend's birthday. Can you please add a reminder at 6 pm that it is a birthday and I have to wish her? Added for 6 pm on 20th November.", N)
ok(e["title"] == "My girlfriend's birthday: wish her" and e["start"] == _dt(2026, 11, 20, 18, 0) and e["remind"] and e["repeat"], e)
ok(g.parse_event("remind me to call mom on 22 november at 7 pm, add it to calendar", N)["title"] == "Call mom", "remind me to")
ok(g.parse_event("Tomorrow at 4 pm I have a viva, please add it to my calendar", N)["title"] == "Viva", "i have a viva")
print(f"{n - f} passed, {f} failed")
