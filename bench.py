"""Axor benchmark: measured numbers for the report.  Run:  python bench.py            (engine latency + intent accuracy)
                                                          python bench.py --stt      (Mac only: offline Whisper accuracy + latency using `say`)"""
import os, sys, time, statistics, tempfile, subprocess
os.environ.setdefault("AXOR_NO_WHISPER", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server as s
STT = "--stt" in sys.argv
if not STT:  # stub system calls so this also runs off-Mac; engine logic and parsing are what is measured
    s.IS_MAC = True; s.sh = lambda cmd, timeout=15: (True, "87%"); s.osa = lambda sc: (True, "+91 98765 43210"); s.speak = lambda *a: None; s.online = lambda: False; s.time.sleep = lambda x: None
CASES = [  # (utterance, expected category)
 ("what time is it", "info"), ("what's the time", "info"), ("tell me the time", "info"), ("what is today's date", "info"), ("what day is it", "info"),
 ("calculate 12 times 5", "calc"), ("what is 100 divided by 4", "calc"), ("5 plus 3", "calc"), ("compute 9 minus 2", "calc"),
 ("open youtube", "web"), ("open gmail", "web"), ("go to github.com", "web"), ("open linkedin", "web"), ("open github", "web"),
 ("open whatsapp", "apps"), ("open spotify", "apps"), ("launch safari", "apps"), ("open vs code", "apps"), ("open calculator", "apps"), ("start terminal", "apps"),
 ("close safari", "apps"), ("quit spotify", "apps"), ("close whatsapp", "apps"),
 ("play lofi on youtube", "web"), ("search python tutorials on youtube", "web"), ("google machine learning", "web"), ("search for ai news", "web"), ("look up vit ap", "web"),
 ("set volume to 40", "system"), ("volume up", "system"), ("volume down", "system"), ("mute", "system"), ("louder", "system"), ("take a screenshot", "system"), ("battery", "system"), ("lock the screen", "system"),
 ("take a note buy milk", "notes"), ("note down call mom", "notes"), ("read my notes", "notes"),
 ("remind me to call mom in 10 minutes", "reminder"), ("set an alarm for 6 am", "reminder"), ("set a timer for 5 minutes", "reminder"), ("remind me to study tomorrow at 7 am", "reminder"), ("set a reminder to drink water at 5:30 pm", "reminder"),
 ("schedule a meeting with rahul tomorrow at 5 pm", "calendar"), ("set up a meeting at 3 pm", "calendar"), ("book a call with the team tomorrow at 11 am", "calendar"),
 ("send whatsapp to rahul saying hi", "message"), ("message rahul saying i am late", "message"), ("text rahul that i will call you", "message"),
 ("hello", "chat"), ("hey axor", "chat"), ("who are you", "chat"), ("thank you", "chat"),
 ("youtube kholo", "web"), ("whatsapp kholo", "apps"), ("safari band karo", "apps"), ("samay kya hai", "info"), ("awaaz badhao", "system"), ("namaste", "chat"),
 ("who won the world cup", "offline"), ("explain quantum computing", "offline"), ("tell me a joke", "offline"),
]
def pct(a, p): a = sorted(a); return a[min(len(a) - 1, int(len(a) * p))]
if not STT:
    s.CUR.uid = 0; ok = 0; wrong = []; lat = []
    for u, exp in CASES:
        t0 = time.perf_counter(); cat, resp, _ = s.run_command(u); lat.append((time.perf_counter() - t0) * 1000)
        if cat == exp: ok += 1
        else: wrong.append((u, exp, cat))
    for _ in range(5):
        for u, _e in CASES:
            t0 = time.perf_counter(); s.run_command(u); lat.append((time.perf_counter() - t0) * 1000)
    print(f"Intent accuracy (our {len(CASES)}-command test set, offline): {ok}/{len(CASES)} = {100*ok/len(CASES):.1f}%")
    for w in wrong: print("   miss:", w)
    print(f"Command engine latency over {len(lat)} runs (ms): mean {statistics.mean(lat):.1f} | p50 {pct(lat,.5):.1f} | p95 {pct(lat,.95):.1f} | p99 {pct(lat,.99):.1f}")
    print("NOTE: system actions are stubbed here; the latency is parsing + database logging, not the time macOS takes to open an app.")
else:
    from faster_whisper import WhisperModel
    m = WhisperModel("base", device="cpu", compute_type="int8"); phrases = [u for u, _ in CASES[:12]] + ["open youtube", "set volume to forty", "remind me to call mom in ten minutes"]
    import re; norm = lambda x: re.sub(r"[^a-z0-9 ]", "", x.lower()).split()
    def wer(ref, hyp):
        r, h = norm(ref), norm(hyp); d = [[i + j if i * j == 0 else 0 for j in range(len(h) + 1)] for i in range(len(r) + 1)]
        for i in range(1, len(r) + 1):
            for j in range(1, len(h) + 1): d[i][j] = min(d[i-1][j] + 1, d[i][j-1] + 1, d[i-1][j-1] + (r[i-1] != h[j-1]))
        return d[-1][-1] / max(1, len(r))
    ws, ts = [], []
    for ph in phrases:
        f = tempfile.mktemp(suffix=".aiff"); subprocess.run(["say", "-v", "Samantha", "-o", f, ph], check=True)
        t0 = time.perf_counter(); segs, _ = m.transcribe(f, language="en", beam_size=1); txt = " ".join(x.text for x in segs); ts.append(time.perf_counter() - t0); ws.append(wer(ph, txt)); print(f"  '{ph}' -> '{txt.strip()}'")
    print(f"Whisper base int8 on {len(phrases)} synthetic phrases: word error rate {100*statistics.mean(ws):.1f}% | latency mean {statistics.mean(ts):.2f}s, max {max(ts):.2f}s")
    print("NOTE: synthetic (text-to-speech) audio, not live human speech. Say this when you quote it.")
