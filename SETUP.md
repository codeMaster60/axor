# Axor: what YOU must do (the code is written; these steps need your own accounts)

Everything below is optional. Axor runs fully offline without it. Do them in this order; each step is independent.
After editing `.env`, restart `./start.sh`. Check status in Axor → Settings → Integrations.

## 1. Google (Gmail + Calendar)  ~10 min
1. console.cloud.google.com → New Project "Axor".
2. APIs & Services → Library → enable **Gmail API** and **Google Calendar API**.
3. OAuth consent screen → External → app name Axor → add your Gmail as a **Test user**.
4. Credentials → Create credentials → **OAuth client ID** → type **Desktop app** → Download JSON.
5. Save it as `~/axor/credentials.json`.
6. Say or type **"connect google"** to Axor. Browser opens, approve once. Token is saved to `google_token.json`.
7. Try: "read my emails", "summarize my emails", "schedule a meeting with Rahul tomorrow at 5 pm".

## 2. Firebase  ~10 min
1. console.firebase.google.com → Add project.
2. Build → Authentication → Get started → enable **Email/Password**.
3. Build → Firestore Database → Create (test mode is fine for the demo).
4. Project settings → General → copy **Web API Key** and **Project ID**.
5. Put them in `.env` as FIREBASE_API_KEY and FIREBASE_PROJECT_ID.
Data appears under `users/{uid}/commands|reminders|events|notes`.

## 3. Supabase  ~10 min
1. supabase.com → New project. Project Settings → API → copy **URL** and **anon key** → `.env`.
2. SQL editor, paste and run (columns match exactly what Axor sends):
```sql
create table if not exists commands (cid text primary key, username text, ts text, source text, command text, response text, category text, ms int, ok int);
create table if not exists reminders (cid text primary key, username text, text text, due text, fired int, kind text);
create table if not exists events (cid text primary key, username text, title text, start text);
create table if not exists notes (cid text primary key, username text, ts text, text text);
alter table commands enable row level security; alter table reminders enable row level security;
alter table events enable row level security; alter table notes enable row level security;
create policy "demo all" on commands for all using (true) with check (true);
create policy "demo all" on reminders for all using (true) with check (true);
create policy "demo all" on events for all using (true) with check (true);
create policy "demo all" on notes for all using (true) with check (true);
```
The "demo all" policies let anyone with the anon key read/write; fine for a demo, tighten before real use.

## 4. Cloudinary  ~3 min
cloudinary.com free account → Dashboard → copy the **API Environment variable** (`cloudinary://key:secret@cloud`) → `CLOUDINARY_URL` in `.env`. Say "take a screenshot"; the URL is returned.

## 5. Redis (optional)
`brew install redis && brew services start redis`, then `REDIS_URL=redis://127.0.0.1:6379/0` before starting `axor-cloud/cloud.py`.

## 6. Deploy the cloud API (optional)
- **Railway:** new project from the `axor-cloud` folder (Procfile included). Set `AXOR_JWT_SECRET` to a long random value. Copy the URL, then set it as the cloud URL in Axor.
- **Docker:** `docker build -t axor-cloud axor-cloud && docker run -p 8080:8080 -e AXOR_JWT_SECRET=... axor-cloud`.

## 7. Must-dos on your Mac
- Rotate your Groq key (it was shared in chat) at console.groq.com; paste the new one in `.env`.
- Run Axor once WITH internet so Whisper can download its model (~150 MB), then it works offline.
- Grant Terminal: Microphone, Accessibility, Contacts (System Settings → Privacy & Security).
- Run `python bench.py --stt` once on the Mac and use those numbers in the report.

## Starting Axor
`./start.sh` (uses the venv automatically). If you prefer two windows: `cd axor-cloud && ../venv/bin/python cloud.py` and, in a second window, `./venv/bin/python server.py`. If packages are missing: `./venv/bin/python -m pip install -r requirements.txt`.

## Test scripts
`python test_axor.py` (99) · `python test_integrations.py` (35, simulated services) · `python test_chats.py` (33) · `cd axor-cloud && python test_cloud.py` (73) · `python security_audit.py` · `python loadtest.py`
