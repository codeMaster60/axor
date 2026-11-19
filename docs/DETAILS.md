# Axor — local voice assistant with offline-first cloud sync

## Run (Mac)
```
cd ~/axor && source venv/bin/activate
pip install -r requirements.txt
./start.sh            # starts both services
```
- Assistant (voice + text): http://localhost:8765
- Web dashboard (React):    http://localhost:8080
- First run: Whisper downloads its model once (needs internet). After that speech recognition is fully offline.
- System Settings -> Privacy: allow Microphone for your browser, Accessibility for Terminal (WhatsApp auto-send), Contacts.

## What works offline and what needs internet
| Feature | Offline | Online |
|---|---|---|
| Typed and spoken commands (apps, volume, screenshot, notes, reminders, timers, meetings as .ics, time, date, battery, calculator) | Yes | Yes |
| Speech recognition (Whisper, after its one-time download) | Yes | Yes |
| Maths: solve, differentiate, integrate, limits, factor, expand, simplify (SymPy), shown as typeset equations | Yes | Yes |
| Equations and Markdown rendering (KaTeX is bundled in `static/vendor`, no CDN) | Yes | Yes |
| Chats (auto-named, searchable, renameable), Today agenda, Skills, Insights, Save as image / Save text | Yes | Yes |
| Attach and read: PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), OpenDocument, EPUB, RTF, CSV, JSON, Markdown, HTML, text, code, notebooks (text extraction is offline; basic summary offline, full AI analysis online) | Yes | Full AI analysis |
| Attach images (PNG, JPG, WebP, GIF) | Saved only, honest message | AI reads them (cloud vision model) |
| Old binary Office files (.doc .xls .ppt) | Approximate text only (said in the reply) | Same |
| Pictures: real photos from Wikipedia / Wikimedia Commons with credits; generated artwork (Pollinations, never real people) | No (honest message) | Yes, no key needed |
| Factual answers with a numbered Sources list (Wikipedia + DuckDuckGo results, switch off in Settings) | No | Yes |
| Audio and video files (MP3, MP4, WAV, M4A...): transcribed on this Mac with Whisper, then summarized (summary needs internet; sound only, video frames are not viewed) | Transcript yes | Transcript + summary |
| ZIP files: file list plus the text of readable files inside | Yes | Yes |
| Open questions, step-by-step solutions to any problem, explanations | No | Yes (Groq) |
| Gmail, Google Calendar, Firebase, Supabase, Cloudinary sync | Queued / skipped | Yes |

## Brand
`brand/` holds the logo (SVG, PNG 64 to 1024) and light/dark lockups. The same SVG is `static/logo.svg` (used by the app, dashboard and landing page).

## Chats
Each conversation is one chat. Follow-up questions are sent with the earlier messages as context. "New chat" starts a fresh one; old chats are listed in the sidebar, can be reopened and deleted. Older history is grouped into one chat per day automatically.

## What is built
| Part | Tech | Notes |
|---|---|---|
| Voice input | Browser mic -> faster-whisper (base, int8) | Offline. Hindi/English/auto in Settings. |
| Command engine | Python rule-based router | open/close apps, websites, YouTube/Google search, volume, screenshot, lock, battery, time/date, calculator, notes, reminders/alarms/timers, meetings (.ics into Calendar, works offline), WhatsApp send (Contacts + AppleScript) |
| AI answers | Groq Llama (online only) | Tries several model names. Offline: clear message. |
| Local store | SQLite | history, analytics, reminders, notes, events, settings, per-user |
| Auth | PBKDF2 passwords + signed tokens | sign-up / sign-in on the assistant |
| Cloud backend | Python (Flask) REST API | 25 endpoints, JWT (HS256), rate limit 100 req/min, security headers, idempotent sync |
| Sync | SQLite queue -> /api/sync | Works offline; catches up on reconnect. Status shown in sidebar. |
| Dashboard | React 18 + Recharts (Vite build) | Login/Sign-up, Overview, History, Analytics, Calendar, Reminders, Notes, Settings; dark/light; mobile responsive |

## Integrations (code written; need YOUR accounts/keys, see SETUP.md)
| Part | Status |
|---|---|
| Gmail read/summary, Google Calendar events (OAuth 2.0 + PKCE) | Written. Tested against **simulated** Google responses (token exchange, refresh, request shape). Not yet run against real Google. |
| Firebase Auth + Firestore sync | Written (REST). Tested against simulated responses only. |
| Supabase (PostgREST upsert) | Written. Tested against simulated responses only. |
| Cloudinary screenshot upload | Written (signed upload, signature verified in test). Not run against real Cloudinary. |
| Redis cache for analytics | **Tested against a real redis-server** (hit ratio measured). Falls back to in-memory. |
| Selenium web search | Written. Real-browser test skipped here (driver/Chrome version mismatch); run on your Mac. |
| Deploy files (Procfile, Dockerfile) | Written. Not deployed. |

## Calendar, documents, editing and colours
- "What's on my calendar today / tomorrow / on 18 November / this week" reads your Google Calendar (after `connect Google`).
- Asking for an assignment, essay, report or letter produces an editable document card with Copy and Download .docx. The AI writes placeholders for anything it does not know; check facts and references before submitting.
- Hover a message you sent and press Edit to change it. The old reply is dropped and a new one is generated.
- Settings > Appearance: presets and three colour pickers (accent, glow, background); saved in this browser.
- Text replies have Copy only. Downloads exist for images, documents and files.

## Images, sources and chat names
Ask for pictures in plain words ("show me photos of the Taj Mahal", "generate an image of a dragon"). Photos come from Wikipedia and Wikimedia Commons and every picture carries its credit and a source link. Generated images use Pollinations (free, no key); Axor does not generate pictures of real people and shows real photos instead. Click a picture to enlarge, then Save image. Factual questions are answered from search results with [1], [2] citations and a Sources list. Chats are named from what you discussed (a short AI title when online, a smart local title offline); double-click a chat in the sidebar to rename it. Image and source lookups were tested against mocked responses only; they depend on those public sites being reachable from your Mac.

## Skills
The Skills page has a library of 23 skills (writing, study, coding, research, work, everyday), a My skills tab, and a Commands tab. Press Add to install a skill, switch it on or off from the page or from the sparkle button in the chat box, remove it, or write your own. Up to 5 can be on at once; each one adds its instructions to Axor's AI prompt while on. The library is Axor's own set of skill packs, not a live download from an outside marketplace, and skills affect AI answers only (not local commands such as opening apps).

## What is NOT built (do not claim)
Spring Boot (backend is Flask), Windows version (design doc only), Framer landing page (HTML landing page only), any real Railway/Vercel deployment, third-party penetration test (we ran our own audit).

## Tests and measurements (all run in a Linux sandbox; rerun on your Mac)
- `python test_axor.py`            99 checks (assistant API, auth, commands) - system calls stubbed
- `python test_docgen.py`          18 checks (dates, document detection, .docx)
- `python test_integrations.py`    36 checks (simulated Google/Firebase/Supabase/Cloudinary)
- `python test_web.py`             27 checks (image intent, photo/generate flows, citations, titles, Today API; HTTP mocked)
- `python test_chats.py`           36 checks (chats, attachments, offline maths, model discovery; Groq simulated)
- `cd axor-cloud && python test_cloud.py`  73 checks (cloud API, JWT, rate limit, sync)
- `cd axor-cloud && python security_audit.py`  18 checks (our own audit: auth, JWT tamper/alg=none, isolation, SQLi, headers, hashing). Rate limit verified: 130 rapid requests -> 100 OK, 30 x 429.
- `cd axor-cloud && python loadtest.py http://127.0.0.1:8080 20 10 [readonly]`  load test
- `python bench.py` intent accuracy + engine latency; `python bench.py --stt` (Mac) Whisper WER + latency
- Postman: import `axor-cloud/Axor_Cloud.postman_collection.json` (25 requests)

### Measured load test (2-core sandbox, Flask dev server, 20 concurrent clients, 10 s)
| Scenario | Throughput | p50 | p95 | p99 | Cache hit |
|---|---|---|---|---|---|
| Mixed read/write, memory cache | 278 req/s | 21.7 ms | 240 ms | 1059 ms | 0.5% |
| Mixed read/write, Redis | 258 req/s | 25.2 ms | 208 ms | 1299 ms | 0.7% |
| Read-only dashboard, memory | 471 req/s | 39.7 ms | 65.7 ms | 77.8 ms | 100% |
| Read-only dashboard, Redis | 408 req/s | 46.1 ms | 72.5 ms | 97.7 ms | 99.9% |
Honest reading: caching only helps read-heavy dashboards; any write invalidates the user's cache. Write tail latency (p99 > 1 s) comes from SQLite's single writer; Postgres would fix that. Use these numbers, not invented ones.
