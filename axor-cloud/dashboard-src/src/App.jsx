import React, { useEffect, useState, useCallback } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, CartesianGrid } from "recharts";
const COLORS = ["#10a37f", "#5eead4", "#3b82f6", "#f59e0b", "#a855f7", "#ef5350", "#94a3b8"];
const tk = () => { try { return localStorage.getItem("axor_cloud_t") || ""; } catch { return ""; } };
async function api(path, opt = {}) {
  const r = await fetch("/api" + path, { ...opt, headers: { "Content-Type": "application/json", Authorization: "Bearer " + tk(), ...(opt.headers || {}) } });
  if (r.status === 401 && !path.startsWith("/auth/")) { try { localStorage.removeItem("axor_cloud_t"); } catch {} window.dispatchEvent(new Event("axor-logout")); throw new Error("auth"); }
  return r;
}
const j = async (p, o) => (await api(p, o)).json();
function Auth({ onIn }) {
  const [mode, setMode] = useState("login"), [u, setU] = useState(""), [p, setP] = useState(""), [err, setErr] = useState("");
  const go = async () => { const r = await fetch("/api/auth/" + (mode === "login" ? "login" : "register"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: u, password: p }) }); const d = await r.json();
    if (!r.ok) return setErr(d.error || "Failed"); try { localStorage.setItem("axor_cloud_t", d.token); } catch {} onIn(d.username); };
  return <div className="auth"><div className="box"><div className="logo" style={{ padding: 0 }}><img src="logo.svg" alt="" />Axor Cloud</div>
    <h1 style={{ marginTop: 14 }}>{mode === "login" ? "Welcome back" : "Create your account"}</h1><p className="sub">{mode === "login" ? "Sign in to your dashboard." : "Use the same username as your Axor app to see its synced data."}</p>
    <input placeholder="Username" value={u} onChange={e => setU(e.target.value)} /><input type="password" placeholder="Password" value={p} onChange={e => setP(e.target.value)} onKeyDown={e => e.key === "Enter" && go()} />
    <div className="err">{err}</div><button className="btn" onClick={go}>{mode === "login" ? "Sign in" : "Sign up"}</button>
    <p className="sub" style={{ textAlign: "center", marginTop: 14, marginBottom: 0 }}>{mode === "login" ? "New here? " : "Have an account? "}<span className="link" onClick={() => { setMode(mode === "login" ? "signup" : "login"); setErr(""); }}>{mode === "login" ? "Create an account" : "Sign in"}</span></p></div></div>;
}
const Empty = ({ t }) => <div className="empty">{t}</div>;
function Overview() {
  const [s, setS] = useState(null), [d, setD] = useState([]), [h, setH] = useState([]);
  useEffect(() => { j("/analytics/summary").then(setS); j("/analytics/daily").then(setD); j("/commands/history?limit=6").then(setH); }, []);
  if (!s) return null;
  return <><h1>Overview</h1><p className="sub">Everything Axor has synced from your Mac.</p>
    <div className="cards">{[["Commands", s.total], ["Avg response", Math.round(s.avg_ms) + " ms"], ["Success rate", s.success + "%"], ["Voice / Text", s.voice + " / " + s.text]].map(x => <div className="card" key={x[0]}><b>{x[1]}</b><span>{x[0]}</span></div>)}</div>
    <div className="panel"><h3>Commands per day</h3>{d.length ? <ResponsiveContainer width="100%" height={200}><BarChart data={d}><CartesianGrid stroke="#8884" vertical={false} /><XAxis dataKey="day" tick={{ fontSize: 11 }} tickFormatter={x => x.slice(5)} /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="n" fill="#10a37f" radius={[4, 4, 0, 0]} maxBarSize={56} /></BarChart></ResponsiveContainer> : <Empty t="No synced commands yet. Use Axor, then come back." />}</div>
    <div className="panel"><h3>Latest activity</h3>{h.length ? <table><tbody>{h.map(x => <tr key={x.id}><td><span className={"tag " + (x.source === "voice" ? "v" : "")}>{x.source}</span></td><td>{x.command}</td><td style={{ color: "var(--mut)" }}>{x.response}</td></tr>)}</tbody></table> : <Empty t="Nothing yet." />}</div></>;
}
function History() {
  const [q, setQ] = useState(""), [r, setR] = useState([]), [off, setOff] = useState(0), L = 20;
  const load = useCallback(() => j(`/commands/history?q=${encodeURIComponent(q)}&limit=${L}&offset=${off}`).then(setR), [q, off]); useEffect(() => { load(); }, [load]);
  const exp = async () => { const b = await (await api("/commands/export")).blob(); const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = "axor_history.csv"; a.click(); };
  const del = async i => { await api("/commands/" + i, { method: "DELETE" }); load(); };
  return <><h1>Command History</h1><p className="sub">Search, page through and export every command.</p>
    <div className="row"><input placeholder="Search…" value={q} onChange={e => { setQ(e.target.value); setOff(0); }} /><button className="btn" onClick={exp}>Export CSV</button></div>
    <div className="panel" style={{ overflowX: "auto" }}>{r.length ? <table><thead><tr><th>Time</th><th>Type</th><th>Command</th><th>Response</th><th>ms</th><th></th></tr></thead><tbody>{r.map(x => <tr key={x.id}><td style={{ whiteSpace: "nowrap", color: "var(--mut)" }}>{x.ts.replace("T", " ")}</td><td><span className={"tag " + (x.source === "voice" ? "v" : "")}>{x.source}</span></td><td>{x.command}</td><td>{x.response}</td><td>{x.ms}</td><td><button className="btn g" onClick={() => del(x.id)}>Delete</button></td></tr>)}</tbody></table> : <Empty t="No matching commands." />}</div>
    <div className="row"><button className="btn g" disabled={off === 0} onClick={() => setOff(Math.max(0, off - L))}>← Prev</button><button className="btn g" disabled={r.length < L} onClick={() => setOff(off + L)}>Next →</button></div></>;
}
function Analytics() {
  const [c, setC] = useState([]), [w, setW] = useState([]), [s, setS] = useState(null);
  useEffect(() => { j("/analytics/categories").then(setC); j("/analytics/weekly").then(setW); j("/analytics/summary").then(setS); }, []);
  return <><h1>Analytics</h1><p className="sub">Usage patterns across all synced commands.</p>
    <div className="grid2"><div className="panel"><h3>By category</h3>{c.length ? <ResponsiveContainer width="100%" height={240}><PieChart><Pie data={c} dataKey="n" nameKey="category" innerRadius={55} outerRadius={90} paddingAngle={2}>{c.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer> : <Empty t="No data." />}
      <div>{c.map((x, i) => <span key={x.category} style={{ marginRight: 12, fontSize: 12 }}><span style={{ color: COLORS[i % COLORS.length] }}>●</span> {x.category} {x.n}</span>)}</div></div>
    <div className="panel"><h3>Weekly volume & avg response (ms)</h3>{w.length ? <ResponsiveContainer width="100%" height={240}><LineChart data={w}><CartesianGrid stroke="#8884" vertical={false} /><XAxis dataKey="week" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Line dataKey="n" stroke="#10a37f" strokeWidth={2} name="commands" /><Line dataKey="avg_ms" stroke="#3b82f6" strokeWidth={2} name="avg ms" /></LineChart></ResponsiveContainer> : <Empty t="No data." />}</div></div>
    {s && <div className="panel"><h3>Voice vs text</h3><ResponsiveContainer width="100%" height={60}><BarChart layout="vertical" data={[{ n: "inputs", voice: s.voice, text: s.text }]}><XAxis type="number" hide /><YAxis type="category" dataKey="n" hide /><Tooltip /><Bar dataKey="voice" stackId="a" fill="#10a37f" /><Bar dataKey="text" stackId="a" fill="#3b82f6" /></BarChart></ResponsiveContainer></div>}</>;
}
function Simple({ name, title, sub, cols, render, fields }) {
  const [r, setR] = useState([]), [f, setF] = useState({}); const load = useCallback(() => j("/" + name).then(setR), [name]); useEffect(() => { load(); }, [load]);
  const add = async () => { await api("/" + name, { method: "POST", body: JSON.stringify(f) }); setF({}); load(); }; const del = async i => { await api(`/${name}/${i}`, { method: "DELETE" }); load(); };
  return <><h1>{title}</h1><p className="sub">{sub}</p>
    <div className="row">{fields.map(x => <input key={x.k} type={x.type || "text"} placeholder={x.p} value={f[x.k] || ""} onChange={e => setF({ ...f, [x.k]: e.target.value })} />)}<button className="btn" onClick={add}>Add</button></div>
    <div className="panel" style={{ overflowX: "auto" }}>{r.length ? <table><thead><tr>{cols.map(c => <th key={c}>{c}</th>)}<th></th></tr></thead><tbody>{r.map(x => <tr key={x.id}>{render(x)}<td><button className="btn g" onClick={() => del(x.id)}>Delete</button></td></tr>)}</tbody></table> : <Empty t="Nothing here yet." />}</div></>;
}
function Settings({ theme, setTheme }) {
  const [s, setS] = useState({}); useEffect(() => { j("/settings").then(setS); }, []); const put = async (k, v) => setS(await j("/settings", { method: "PUT", body: JSON.stringify({ [k]: v }) }));
  return <><h1>Settings</h1><p className="sub">Stored in the cloud, per account.</p><div className="panel">
    <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}><span>Theme</span><select value={theme} onChange={e => setTheme(e.target.value)}><option value="dark">Dark</option><option value="light">Light</option></select></div>
    <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}><span>Voice</span><select value={s.voice || "Daniel"} onChange={e => put("voice", e.target.value)}><option>Daniel</option><option>Tara</option><option>Samantha</option></select></div>
    <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}><span>Speak replies to voice commands</span><select value={s.speak || "1"} onChange={e => put("speak", e.target.value)}><option value="1">On</option><option value="0">Off</option></select></div></div></>;
}
function Chats() {
  const [r, setR] = useState(null); useEffect(() => { j("/conversations/list").then(setR); }, []);
  return <><h1>Chats</h1><p className="sub">Every conversation synced from Axor.</p>
    <div className="panel" style={{ overflowX: "auto" }}>{r && r.length ? <table><thead><tr><th>Title</th><th>Messages</th><th>Last activity</th></tr></thead><tbody>{r.map(x => <tr key={x.id}><td>{x.title}</td><td>{x.n}</td><td style={{ color: "var(--mut)", whiteSpace: "nowrap" }}>{(x.last || "").replace("T", " ")}</td></tr>)}</tbody></table> : <Empty t={r ? "No conversations synced yet." : "Loading..."} />}</div></>;
}
function Files() {
  const [r, setR] = useState(null), load = useCallback(() => j("/files").then(setR), []); useEffect(() => { load(); }, [load]);
  const del = async i => { await api("/files/" + i, { method: "DELETE" }); load(); };
  return <><h1>Files</h1><p className="sub">Screenshots and documents Axor uploaded to Cloudinary.</p>
    <div className="panel" style={{ overflowX: "auto" }}>{r && r.length ? <table><thead><tr><th>Name</th><th>Uploaded</th><th></th></tr></thead><tbody>{r.map(x => <tr key={x.id}><td><a className="link" href={x.url} target="_blank" rel="noreferrer">{x.name}</a></td><td style={{ color: "var(--mut)", whiteSpace: "nowrap" }}>{x.ts.replace("T", " ")}</td><td><button className="btn g" onClick={() => del(x.id)}>Remove</button></td></tr>)}</tbody></table> : <Empty t={r ? "No files uploaded yet. Say 'take a screenshot' in Axor." : "Loading..."} />}</div></>;
}
const IC = {
  overview: "M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z",
  history: "M13 3a9 9 0 1 0 9 9h-2a7 7 0 1 1-7-7V3zm-1 5v5l4 2 .8-1.5-3.3-1.6V8H12z",
  analytics: "M4 20h16v2H2V2h2v18zm4-4V9h3v7H8zm5 0V5h3v11h-3zm5 0v-5h3v5h-3z",
  calendar: "M7 2v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2V2h-2v2H9V2H7zm-2 8h14v10H5V10z",
  reminders: "M12 22a2 2 0 0 0 2-2h-4a2 2 0 0 0 2 2zm6-6V11a6 6 0 0 0-5-5.9V4a1 1 0 0 0-2 0v1.1A6 6 0 0 0 6 11v5l-2 2v1h16v-1l-2-2z",
  notes: "M6 2a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6H6zm7 1.5L18.5 9H13V3.5zM8 13h8v2H8v-2zm0 4h8v2H8v-2z",
  chats: "M4 4h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2z",
  files: "M4 4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-8l-2-2H4z",
  settings: "M19.4 13a7.6 7.6 0 0 0 0-2l2-1.6-2-3.4-2.4 1a7.4 7.4 0 0 0-1.7-1L15 3h-4l-.4 3a7.4 7.4 0 0 0-1.7 1l-2.4-1-2 3.4L6.6 11a7.6 7.6 0 0 0 0 2l-2 1.6 2 3.4 2.4-1c.5.4 1.1.7 1.7 1l.4 3h4l.4-3c.6-.3 1.2-.6 1.7-1l2.4 1 2-3.4-2.2-1.6zM12 15.5A3.5 3.5 0 1 1 12 8.5a3.5 3.5 0 0 1 0 7z",
};
const Icon = ({ k }) => <svg className="ico" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d={IC[k]} /></svg>;
const PAGES = [["overview", "Overview"], ["history", "History"], ["chats", "Chats"], ["analytics", "Analytics"], ["calendar", "Calendar"], ["reminders", "Reminders"], ["notes", "Notes"], ["files", "Files"], ["settings", "Settings"]];
export default function App() {
  const [user, setUser] = useState(null), [page, setPage] = useState("overview"), [theme, setTheme] = useState(() => { try { return localStorage.getItem("axor_theme") || "dark"; } catch { return "dark"; } });
  useEffect(() => { document.documentElement.dataset.theme = theme; try { localStorage.setItem("axor_theme", theme); } catch {} }, [theme]);
  useEffect(() => { if (tk()) api("/auth/me").then(r => r.ok ? r.json() : null).then(d => d && setUser(d.username)).catch(() => {}); const h = () => setUser(null); window.addEventListener("axor-logout", h); return () => window.removeEventListener("axor-logout", h); }, []);
  if (!user) return <Auth onIn={setUser} />;
  const out = () => { try { localStorage.removeItem("axor_cloud_t"); } catch {} setUser(null); };
  const P = { overview: <Overview />, history: <History />, analytics: <Analytics />, chats: <Chats />, files: <Files />, settings: <Settings theme={theme} setTheme={setTheme} />,
    calendar: <Simple key="events" name="events" title="Calendar" sub="Meetings Axor scheduled." cols={["When", "Title"]} fields={[{ k: "title", p: "Meeting title" }, { k: "start", type: "datetime-local" }]} render={x => <><td>{x.start.replace("T", " ")}</td><td>{x.title}</td></>} />,
    reminders: <Simple key="reminders" name="reminders" title="Reminders" sub="Reminders, alarms and timers." cols={["When", "What", "Status"]} fields={[{ k: "text", p: "Reminder text" }, { k: "due", type: "datetime-local" }]} render={x => <><td>{x.due.replace("T", " ")}</td><td>{x.text}</td><td><span className={"chip " + (x.fired ? "ok" : "wait")}>{x.fired ? "Done" : "Pending"}</span></td></>} />,
    notes: <Simple key="notes" name="notes" title="Notes" sub="Notes taken by voice or text." cols={["Saved", "Note"]} fields={[{ k: "text", p: "Write a note" }]} render={x => <><td style={{ color: "var(--mut)", whiteSpace: "nowrap" }}>{x.ts.replace("T", " ")}</td><td>{x.text}</td></>} /> };
  return <div className="app"><aside className="side"><div className="logo"><img src="logo.svg" alt="" />Axor Cloud</div>
    {PAGES.map(([k, n]) => <button key={k} className={"nav " + (page === k ? "on" : "")} onClick={() => setPage(k)}><Icon k={k} />{n}</button>)}
    <div className="foot"><span className="av">{user[0].toUpperCase()}</span><span className="un">{user}</span><span className="link" onClick={out}>Sign out</span></div></aside><main className="main">{P[page]}</main></div>;
}
