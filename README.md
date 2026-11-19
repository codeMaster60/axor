# Axor

**A voice assistant that still works when the Wi-Fi doesn't.**

Most assistants send every request to a server. No internet, no assistant. Your voice also leaves your laptop every time.

Setting an alarm doesn't need a data centre. So I built one that doesn't use one.

Axor is a local-first voice and text assistant for macOS. The everyday commands run on your own machine. The internet is only used when a question really needs it.

Built as our Capstone Project at VIT-AP University (CSBS).

## What it does, with no internet

- Opens apps and websites
- Sets alarms, reminders and timers, and rings them out loud
- Takes notes and reads them back
- Schedules meetings as `.ics` files
- Solves maths: equations, derivatives, integrals, limits. Shown as typeset equations
- Controls volume, locks the screen, takes screenshots, tells battery, time and date
- Listens to your voice with Whisper, on your own machine

## What needs internet, and it says so

- Open questions and explanations (Groq Llama)
- Photos, sources, Gmail and Google Calendar
- Cloud sync

When you're offline and ask something that needs the internet, Axor tells you. It never pretends.

## How it works

1. You speak or type.
2. Whisper turns speech into text on your machine.
3. A rule-based engine cleans the sentence ("set and alarm" becomes "set an alarm") and runs the command.
4. If the rules fail and you're online, a language model rewrites the sentence once, and the rules try again.
5. If a model claims it did something it didn't, Axor replaces the claim with an honest message.
6. The result goes into SQLite. Every 4 seconds, anything unsynced goes to Axor Cloud.

Work done offline waits in the queue. When the connection comes back, it syncs, with no duplicates.

## Numbers I measured

| What | Result |
|---|---|
| Intent accuracy (63-command test set, offline) | 63 / 63 |
| Command engine latency, 378 runs | mean 0.4 ms, p95 1.3 ms, p99 4.6 ms |
| Automated checks | 393 passing |
| Cloud API | 35 endpoints |
| Our own security audit | 18 / 18 |
| Rate limit | 130 rapid requests: 100 OK, 30 rejected (429) |

The latency is the engine itself, with system calls stubbed. It does not include the time macOS takes to open an app.

Load test (20 concurrent clients, 10 s, 2-core sandbox, Flask dev server): 278 req/s mixed read/write, 471 req/s read-only dashboard. Writes slow down at the tail because SQLite has one writer. Postgres would fix that.

## Run it (Mac)

```bash
git clone https://github.com/codeMaster60/axor.git
cd axor
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
./start.sh
```

- Assistant (voice and text): http://localhost:8765
- Dashboard: http://localhost:8080

First run downloads the Whisper model once. After that, speech recognition is fully offline.
Allow Microphone for your browser in System Settings > Privacy.

## Dashboard

Axor Cloud keeps a copy of your history, reminders, notes, events and settings. A React dashboard shows it: Overview, History, Chats, Analytics, Calendar, Reminders, Notes, Files, Settings.

Passwords use PBKDF2 with a salt. Login tokens are signed JWTs. Every account only sees its own rows.

## Tests

```bash
python test_axor.py
python test_docgen.py
python test_integrations.py
python test_web.py
python test_chats.py
cd axor-cloud && python test_cloud.py && python security_audit.py
python bench.py
```

## What is not built

I'd rather say it here than have you find out.

- The backend is Flask, not Spring Boot
- No Windows version, only a design note
- Nothing is deployed to a hosting service
- Google, Firebase, Supabase and Cloudinary code was tested against simulated responses only
- The security audit was ours, not a third-party penetration test
- Alarms only fire while the Axor server is running

Full feature tables and setup notes: [docs/DETAILS.md](docs/DETAILS.md) and [SETUP.md](SETUP.md).

## Team

| Name | Reg. No. |
|---|---|
| Jidiga Charan Reddy | 23BCB7120 |
| Lingampally Sampath | 23BCB7136 |
| A. Sai Jayanth | 23BCB7169 |
| Nazeer Shaik | 23BCB7230 |

Guide: Dr. Balaraju Ramesh, School of Computer Science and Engineering, VIT-AP University.
