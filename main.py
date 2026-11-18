import tkinter as tk
from tkinter import font as tkfont
import threading
import os
import webbrowser
import datetime
import time
import math
import wave
import tempfile
import pyaudio
import struct
import subprocess
from faster_whisper import WhisperModel
from pynput import keyboard as kb_listener
from config import OWNER_NAME, AGENT_NAME

# ════════════════════════════════════════
# WHISPER
# ════════════════════════════════════════
print("Loading Whisper model...")
whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
print("✅ Whisper ready!")

def speak(text):
    clean = text.replace('"','').replace("'",'').replace('\n',' ')
    os.system(f'say -v Daniel "{clean}"')

def play_ding():
    os.system("afplay /System/Library/Sounds/Tink.aiff")

# ════════════════════════════════════════
# STATE
# ════════════════════════════════════════
is_recording  = [False]
is_processing = [False]
bar_target    = [0.0]
_opt          = [False]
_ctrl         = [False]
_active       = [False]
chat_sessions = [{"title": "Welcome", "messages": []}]
active_session= [0]

# ════════════════════════════════════════
# AUDIO
# ════════════════════════════════════════
RATE=16000; CHANNELS=1; CHUNK=512; FORMAT=pyaudio.paInt16
pa=pyaudio.PyAudio()
audio_frames=[]
pa_stream=[None]

def audio_callback(in_data, frame_count, time_info, status):
    audio_frames.append(in_data)
    try:
        samples=struct.unpack(f'{len(in_data)//2}h',in_data)
        amp=max(abs(s) for s in samples)/32768.0
        bar_target[0]=min(1.0,bar_target[0]*0.5+amp*4.5*0.5)
    except: pass
    return (in_data, pyaudio.paContinue)

def start_audio():
    audio_frames.clear()
    s=pa.open(format=FORMAT,channels=CHANNELS,rate=RATE,
        input=True,frames_per_buffer=CHUNK,stream_callback=audio_callback)
    pa_stream[0]=s; s.start_stream()

def stop_audio():
    if pa_stream[0]:
        try: pa_stream[0].stop_stream(); pa_stream[0].close()
        except: pass
        pa_stream[0]=None

def save_wav():
    tmp=tempfile.NamedTemporaryFile(suffix=".wav",delete=False)
    with wave.open(tmp.name,'wb') as wf:
        wf.setnchannels(CHANNELS); wf.setsampwidth(pa.get_sample_size(FORMAT))
        wf.setframerate(RATE); wf.writeframes(b''.join(audio_frames))
    return tmp.name

def transcribe(filepath):
    segs,_=whisper_model.transcribe(filepath,language="en",beam_size=5,vad_filter=True,
        vad_parameters={"min_silence_duration_ms":300})
    return " ".join(s.text for s in segs).strip()

# ════════════════════════════════════════
# MAC TOOLS
# ════════════════════════════════════════
def run_apple(script):
    try:
        r=subprocess.run(["osascript","-e",script],capture_output=True,text=True)
        return r.stdout.strip()
    except: return ""

def open_app(name):
    result=subprocess.run(["open","-a",name],capture_output=True,text=True)
    if result.returncode!=0:
        run_apple(f'tell application "{name}" to activate')

def close_app(name):
    run_apple(f'quit app "{name}"')

def open_url(url):
    if not url.startswith("http"): url="https://"+url
    subprocess.run(["open","-a","Arc",url])

def control_volume(action):
    cmds={
        "up":"set volume output volume (output volume of (get volume settings) + 10)",
        "down":"set volume output volume (output volume of (get volume settings) - 10)",
        "mute":"set volume with output muted",
        "unmute":"set volume without output muted"
    }
    if action in cmds: os.system(f"osascript -e '{cmds[action]}'")

def get_time():
    n=datetime.datetime.now()
    return f"It's {n.strftime('%I:%M %p')} on {n.strftime('%A, %B %d, %Y')}"

def take_screenshot():
    ts=datetime.datetime.now().strftime('%H%M%S')
    p=os.path.expanduser(f"~/Desktop/axor_{ts}.png")
    os.system(f"screencapture {p}")
    return "Screenshot saved to Desktop!"

def create_reminder(title):
    script=f'''
    tell application "Reminders"
        set newReminder to make new reminder
        set name of newReminder to "{title}"
        activate
    end tell'''
    run_apple(script)
    return f"Reminder set: {title}"

def send_whatsapp(contact, message):
    open_app("WhatsApp")
    time.sleep(2)
    script=f'''
    tell application "System Events"
        tell process "WhatsApp"
            keystroke "f" using command down
            delay 0.6
            keystroke "{contact}"
            delay 1.2
            key code 36
            delay 0.6
            keystroke "{message}"
            delay 0.4
            key code 36
        end tell
    end tell'''
    run_apple(script)
    return f"Message sent to {contact} on WhatsApp!"

def schedule_meeting(title):
    url=f"https://calendar.google.com/calendar/r/eventedit?text={title.replace(' ','+')}"
    open_url(url)
    return f"Google Calendar opened to schedule: {title}"

# ════════════════════════════════════════
# COMMAND ENGINE
# ════════════════════════════════════════
def run_command(command):
    cmd=command.lower().strip()
    response=""
    try:
        # TIME
        if any(x in cmd for x in ["what time","time is it","current time","what date","today's date","what day"]):
            response=get_time()
        # VOICE SWITCH
        elif any(x in cmd for x in ["female voice","girl voice","switch to female"]):
            os.system('say -v Tara "Switched to female voice!"'); response="Switched to female voice!"
        elif any(x in cmd for x in ["male voice","switch to male"]):
            response="Switched to male voice!"
        # SPECIFIC APPS
        elif any(x in cmd for x in ["open chrome","launch chrome"]):
            open_app("Google Chrome"); response="Chrome is open!"
        elif any(x in cmd for x in ["open safari","launch safari"]):
            open_app("Safari"); response="Safari is open!"
        elif any(x in cmd for x in ["open arc","launch arc"]):
            open_app("Arc"); response="Arc is open!"
        elif any(x in cmd for x in ["open spotify","launch spotify","play spotify"]):
            open_app("Spotify"); response="Spotify is open!"
        elif "whatsapp" in cmd and not any(x in cmd for x in ["send","message","text","tell"]):
            open_app("WhatsApp"); response="WhatsApp is open!"
        elif any(x in cmd for x in ["open telegram","launch telegram"]):
            open_app("Telegram"); response="Telegram is open!"
        elif any(x in cmd for x in ["open notes","launch notes"]):
            open_app("Notes"); response="Notes is open!"
        elif "calendar" in cmd and not any(x in cmd for x in ["schedule","meeting","event"]):
            open_app("Calendar"); response="Calendar is open!"
        elif any(x in cmd for x in ["vs code","vscode","visual studio"]):
            open_app("Visual Studio Code"); response="VS Code is open!"
        elif any(x in cmd for x in ["open finder","launch finder"]):
            open_app("Finder"); response="Finder is open!"
        elif any(x in cmd for x in ["open zoom","launch zoom"]):
            open_app("Zoom"); response="Zoom is open!"
        elif any(x in cmd for x in ["open slack","launch slack"]):
            open_app("Slack"); response="Slack is open!"
        elif any(x in cmd for x in ["open notion","launch notion"]):
            open_app("Notion"); response="Notion is open!"
        elif any(x in cmd for x in ["open maps","launch maps"]):
            open_app("Maps"); response="Maps is open!"
        # GENERIC OPEN
        elif cmd.startswith("open ") and not any(x in cmd for x in ["website","youtube","gmail","instagram","twitter"]):
            app=command[5:].strip().title(); open_app(app); response=f"{app} is open!"
        elif cmd.startswith("launch "):
            app=command[7:].strip().title(); open_app(app); response=f"{app} is open!"
        # CLOSE
        elif any(cmd.startswith(x) for x in ["close ","quit "]):
            app=cmd.replace("close ","").replace("quit ","").strip().title()
            close_app(app); response=f"Closed {app}!"
        # YOUTUBE
        elif "youtube" in cmd:
            q=cmd.replace("youtube","").replace("play","").replace("search","").replace("open","").replace("on","").replace("arc","").replace("browser","").replace("in","").strip()
            if q and len(q)>2:
                open_url(f"https://www.youtube.com/search?search_query={q.replace(' ','+')}"); response=f"Searching YouTube for: {q}"
            else:
                open_url("https://www.youtube.com"); response="YouTube is open!"
        # GOOGLE SEARCH
        elif any(x in cmd for x in ["search for","search on google","google search"]):
            q=cmd.replace("search for","").replace("search on google","").replace("google search","").strip()
            open_url(f"https://www.google.com/search?q={q.replace(' ','+')}"); response=f"Searching Google for: {q}"
        # WEBSITES
        elif any(x in cmd for x in ["go to","open website","navigate to","visit"]):
            site=cmd.replace("go to","").replace("open website","").replace("navigate to","").replace("visit","").strip()
            open_url(site); response=f"Opening {site}!"
        # GMAIL
        elif "gmail" in cmd and not any(x in cmd for x in ["send","compose","write"]):
            open_url("https://mail.google.com"); response="Gmail is open!"
        elif any(x in cmd for x in ["send email","compose email","write email"]):
            open_url("https://mail.google.com/mail/?view=cm"); response="Gmail compose is open!"
        # SOCIAL
        elif "instagram" in cmd:
            open_url("https://www.instagram.com"); response="Instagram is open!"
        elif "twitter" in cmd:
            open_url("https://www.twitter.com"); response="Twitter is open!"
        elif "linkedin" in cmd:
            open_url("https://www.linkedin.com"); response="LinkedIn is open!"
        # WHATSAPP MESSAGE
        elif any(x in cmd for x in ["send","message","text","whatsapp"]) and any(x in cmd for x in ["send","message","tell","say","text"]):
            contact=""
            msg_text=""
            words=cmd.split()
            if "to" in words:
                idx=words.index("to")
                if idx+1<len(words): contact=words[idx+1].title()
            for kw in ["saying","say that","tell him","tell her","that","saying"]:
                if kw in cmd: msg_text=cmd.split(kw)[-1].strip(); break
            if not msg_text:
                for kw in ["message","send","text"]:
                    parts=cmd.split(kw)
                    if len(parts)>1 and "to" in parts[-1]:
                        after_to=parts[-1].split("to")
                        if len(after_to)>1: msg_text=after_to[0].strip()
            if contact and msg_text:
                response=send_whatsapp(contact,msg_text)
            elif contact:
                open_app("WhatsApp"); response=f"WhatsApp open! Search for {contact}."
            else:
                open_app("WhatsApp"); response="WhatsApp is open!"
        # SCHEDULE MEETING
        elif any(x in cmd for x in ["schedule meeting","schedule a meeting","create meeting","set up meeting","google meet"]):
            title="Meeting"
            for kw in ["about","for","titled","called"]:
                if kw in cmd: title=cmd.split(kw)[-1].strip().title(); break
            response=schedule_meeting(title)
        # REMINDER
        elif any(x in cmd for x in ["remind me","set reminder","add reminder"]):
            text=cmd
            for kw in ["remind me to","remind me about","remind me at","set reminder to"]:
                if kw in cmd: text=cmd.split(kw)[-1].strip(); break
            response=create_reminder(text.title())
        # ALARM
        elif any(x in cmd for x in ["set alarm","alarm for","alarm at","wake me"]):
            open_app("Clock"); response="Clock app is open — set your alarm!"
        # NOTES
        elif any(x in cmd for x in ["take a note","add note","note this","create note"]):
            content=cmd.replace("take a note","").replace("add note","").replace("note this","").replace("create note","").strip()
            open_app("Notes")
            if content:
                time.sleep(1)
                run_apple(f'tell application "System Events" to tell process "Notes" to keystroke "n" using command down')
                time.sleep(0.3)
                run_apple(f'tell application "System Events" to tell process "Notes" to keystroke "{content}"')
                response=f"Note created!"
            else:
                response="Notes is open!"
        # SCREENSHOT
        elif "screenshot" in cmd:
            response=take_screenshot()
        # VOLUME
        elif any(x in cmd for x in ["volume up","increase volume","louder","turn up"]):
            control_volume("up"); response="Volume increased!"
        elif any(x in cmd for x in ["volume down","decrease volume","quieter","turn down"]):
            control_volume("down"); response="Volume decreased!"
        elif "unmute" in cmd:
            control_volume("unmute"); response="Unmuted!"
        elif "mute" in cmd:
            control_volume("mute"); response="Muted!"
        # BRIGHTNESS
        elif any(x in cmd for x in ["brightness up","brighter"]):
            run_apple('tell application "System Events" to key code 144'); response="Brightness increased!"
        elif any(x in cmd for x in ["brightness down","dimmer"]):
            run_apple('tell application "System Events" to key code 145'); response="Brightness decreased!"
        # SYSTEM
        elif "lock screen" in cmd or "lock mac" in cmd:
            run_apple('tell application "System Events" to keystroke "q" using {control down, command down}')
            response="Screen locked!"
        elif "empty trash" in cmd:
            run_apple('tell application "Finder" to empty trash'); response="Trash emptied!"
        elif "shutdown" in cmd or "shut down" in cmd:
            speak("Shutting down your Mac!"); os.system("sudo shutdown -h now"); response="Shutting down!"
        elif "restart" in cmd or "reboot" in cmd:
            speak("Restarting!"); os.system("sudo shutdown -r now"); response="Restarting!"
        elif "sleep" in cmd and any(x in cmd for x in ["mac","laptop","computer"]):
            os.system("pmset sleepnow"); response="Mac is sleeping!"
        # AI FALLBACK
        else:
            try:
                from agent import ask_axor
                response=ask_axor(command)
            except:
                response=f"I heard: '{command}'. I'm working on handling that!"
    except Exception as e:
        response=f"Error: {str(e)}"
        print(f"Command error: {e}")
    return response if response else "Done!"

# ════════════════════════════════════════
# ROOT WINDOW
# ════════════════════════════════════════
root=tk.Tk()
root.title("Axor")
root.geometry("1000x680")
root.configure(bg="#080808")
root.resizable(True,True)
root.minsize(700,500)

# ════════════════════════════════════════
# LAYOUT
# ════════════════════════════════════════
outer=tk.Frame(root,bg="#080808")
outer.pack(fill="both",expand=True)

sidebar_frame=tk.Frame(outer,bg="#0c0c0c",width=220)
sidebar_frame.pack(side="left",fill="y")
sidebar_frame.pack_propagate(False)

main_frame=tk.Frame(outer,bg="#080808")
main_frame.pack(side="left",fill="both",expand=True)

sb_visible=[True]

# ════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════
sb_top=tk.Frame(sidebar_frame,bg="#0c0c0c",height=50)
sb_top.pack(fill="x"); sb_top.pack_propagate(False)

tk.Label(sb_top,text="History",font=("Helvetica Neue",10,"bold"),
    fg="#333",bg="#0c0c0c").pack(side="left",padx=14,pady=14)

sb_new_btn=tk.Button(sb_top,text="+",font=("Helvetica Neue",18),
    fg="#10a37f",bg="#0c0c0c",activebackground="#0d1a14",
    activeforeground="#10a37f",borderwidth=0,relief="flat",cursor="hand2")
sb_new_btn.pack(side="right",padx=12)

tk.Frame(sidebar_frame,bg="#161616",height=1).pack(fill="x")

sb_scroll=tk.Frame(sidebar_frame,bg="#0c0c0c")
sb_scroll.pack(fill="both",expand=True)

sb_canvas=tk.Canvas(sb_scroll,bg="#0c0c0c",highlightthickness=0,borderwidth=0)
sb_canvas.pack(side="left",fill="both",expand=True)

sb_list=tk.Frame(sb_canvas,bg="#0c0c0c")
sb_win=sb_canvas.create_window((0,0),window=sb_list,anchor="nw")

def on_sb_conf(e):
    sb_canvas.configure(scrollregion=sb_canvas.bbox("all"))
    sb_canvas.itemconfig(sb_win,width=sb_canvas.winfo_width())
sb_list.bind("<Configure>",on_sb_conf)

tk.Frame(sidebar_frame,bg="#161616",height=1).pack(fill="x",side="bottom")
sb_footer=tk.Frame(sidebar_frame,bg="#0c0c0c",height=44)
sb_footer.pack(side="bottom",fill="x"); sb_footer.pack_propagate(False)

settings_btn=tk.Button(sb_footer,text="⚙  Settings",
    font=("Helvetica Neue",11),fg="#2a2a2a",bg="#0c0c0c",
    activebackground="#141414",activeforeground="#666",
    borderwidth=0,relief="flat",cursor="hand2",anchor="w",padx=14)
settings_btn.pack(fill="x",pady=6)

def refresh_sidebar():
    for w in sb_list.winfo_children(): w.destroy()
    sessions=chat_sessions[:]
    today_label=False; earlier_label=False
    for i,s in enumerate(reversed(sessions)):
        ridx=len(sessions)-1-i
        is_active=(ridx==active_session[0])
        if not today_label:
            lbl=tk.Label(sb_list,text="TODAY",font=("Helvetica Neue",8,"bold"),
                fg="#252525",bg="#0c0c0c",anchor="w",padx=14)
            lbl.pack(fill="x",pady=(8,2)); today_label=True
        bg="#0d1a14" if is_active else "#0c0c0c"
        fg="#10a37f" if is_active else "#3a3a3a"
        title=s["title"][:24]+("…" if len(s["title"])>24 else "")
        frm=tk.Frame(sb_list,bg=bg,cursor="hand2")
        frm.pack(fill="x",padx=8,pady=1)
        dot=tk.Label(frm,text="●",font=("Helvetica Neue",7),
            fg=("#10a37f" if is_active else "#1a1a1a"),bg=bg)
        dot.pack(side="left",padx=(8,4),pady=8)
        lbl=tk.Label(frm,text=title,font=("Helvetica Neue",11),
            fg=fg,bg=bg,anchor="w")
        lbl.pack(side="left",fill="x",expand=True,pady=8,padx=(0,8))
        def click(idx=ridx):
            active_session[0]=idx
            load_session(idx)
            refresh_sidebar()
        frm.bind("<Button-1>",lambda e,f=click:f())
        lbl.bind("<Button-1>",lambda e,f=click:f())
        dot.bind("<Button-1>",lambda e,f=click:f())

def load_session(idx):
    chat_display.config(state=tk.NORMAL)
    chat_display.delete(1.0,tk.END)
    chat_display.config(state=tk.DISABLED)
    for msg in chat_sessions[idx]["messages"]:
        _insert_message(msg["sender"],msg["text"],msg["tag"],msg["color"],save=False)

def new_session():
    chat_sessions.append({"title":"New Chat","messages":[]})
    active_session[0]=len(chat_sessions)-1
    chat_display.config(state=tk.NORMAL)
    chat_display.delete(1.0,tk.END)
    chat_display.config(state=tk.DISABLED)
    refresh_sidebar()
    add_system_msg("New conversation started.")

sb_new_btn.config(command=new_session)

# ════════════════════════════════════════
# HEADER
# ════════════════════════════════════════
header=tk.Frame(main_frame,bg="#0a0a0a",height=54)
header.pack(fill="x"); header.pack_propagate(False)

ham_btn=tk.Button(header,text="☰",font=("Helvetica Neue",15),
    fg="#333",bg="#0a0a0a",activebackground="#141414",activeforeground="#aaa",
    borderwidth=0,relief="flat",cursor="hand2")
ham_btn.pack(side="left",padx=16)

def toggle_sidebar():
    if sb_visible[0]:
        sidebar_frame.pack_forget(); sb_visible[0]=False
        ham_btn.config(fg="#10a37f")
    else:
        sidebar_frame.pack(side="left",fill="y",before=main_frame)
        sb_visible[0]=True; ham_btn.config(fg="#333")

ham_btn.config(command=toggle_sidebar)

hdr_center=tk.Frame(header,bg="#0a0a0a")
hdr_center.place(relx=0.5,rely=0.5,anchor="center")
tk.Label(hdr_center,text="Axor",font=("Helvetica Neue",16,"bold"),
    fg="#f0f0f0",bg="#0a0a0a").pack(side="left")
tk.Label(hdr_center,text="  AI",font=("Helvetica Neue",11,"bold"),
    fg="#10a37f",bg="#0a0a0a").pack(side="left",pady=(2,0))

hdr_right=tk.Frame(header,bg="#0a0a0a")
hdr_right.pack(side="right",padx=18)
status_dot=tk.Label(hdr_right,text="●",font=("Helvetica Neue",10),
    fg="#10a37f",bg="#0a0a0a")
status_dot.pack(side="left")
status_lbl=tk.Label(hdr_right,text=" Ready",font=("Helvetica Neue",11),
    fg="#333",bg="#0a0a0a")
status_lbl.pack(side="left")

tk.Frame(main_frame,bg="#141414",height=1).pack(fill="x")

def set_status(text,color="#10a37f",txt_color="#333"):
    status_lbl.config(text=f" {text}",fg=txt_color)
    status_dot.config(fg=color)

# Pulse
_p=[0]; _pc=["#10a37f","#0ecf96","#0baa7a","#0ecf96","#10a37f"]
def pulse():
    status_dot.config(fg=_pc[_p[0]%len(_pc)]); _p[0]+=1; root.after(700,pulse)
pulse()

# ════════════════════════════════════════
# CHAT DISPLAY
# ════════════════════════════════════════
chat_outer=tk.Frame(main_frame,bg="#080808")
chat_outer.pack(fill="both",expand=True)

chat_display=tk.Text(chat_outer,wrap=tk.WORD,bg="#080808",fg="#c0c0c0",
    font=("Helvetica Neue",13),borderwidth=0,highlightthickness=0,
    padx=28,pady=20,spacing1=2,spacing3=8,relief="flat",
    cursor="arrow",state=tk.DISABLED)

chat_scroll_bar=tk.Scrollbar(chat_outer,command=chat_display.yview,
    bg="#080808",troughcolor="#080808",width=4,
    highlightthickness=0,borderwidth=0)
chat_display.configure(yscrollcommand=chat_scroll_bar.set)
chat_scroll_bar.pack(side="right",fill="y")
chat_display.pack(fill="both",expand=True)

# Tags
chat_display.tag_configure("you_name",foreground="#3a3a3a",font=("Helvetica Neue",10,"bold"))
chat_display.tag_configure("axor_name",foreground="#10a37f",font=("Helvetica Neue",10,"bold"))
chat_display.tag_configure("sys_name",foreground="#1e1e1e",font=("Helvetica Neue",9,"bold"))
chat_display.tag_configure("voice_tag",foreground="#10a37f",font=("Helvetica Neue",8,"bold"),
    background="#0d1a14")
chat_display.tag_configure("text_tag",foreground="#2a2a2a",font=("Helvetica Neue",8,"bold"),
    background="#111111")
chat_display.tag_configure("you_msg",foreground="#e0e0e0",font=("Helvetica Neue",13))
chat_display.tag_configure("axor_msg",foreground="#b8b8b8",font=("Helvetica Neue",13))
chat_display.tag_configure("sys_msg",foreground="#1e1e1e",font=("Helvetica Neue",10,"italic"))
chat_display.tag_configure("err_msg",foreground="#ef4444",font=("Helvetica Neue",13))
chat_display.tag_configure("divider",foreground="#141414",font=("Helvetica Neue",9))
chat_display.tag_configure("space",font=("Helvetica Neue",4))

def _insert_message(sender,text,tag,color,save=True):
    chat_display.config(state=tk.NORMAL)
    chat_display.insert(tk.END,"\n","space")
    chat_display.insert(tk.END,f"{sender} ",tag)
    chat_display.insert(tk.END,"\n",tag)
    chat_display.insert(tk.END,f"{text}\n",color)
    chat_display.see(tk.END)
    chat_display.config(state=tk.DISABLED)
    if save and chat_sessions:
        chat_sessions[active_session[0]]["messages"].append({
            "sender":sender,"text":text,"tag":tag,"color":color})
        if len(chat_sessions[active_session[0]]["messages"])==1:
            chat_sessions[active_session[0]]["title"]=text[:28]
            refresh_sidebar()

def add_you(text,is_voice=False):
    tag="voice_tag" if is_voice else "text_tag"
    label="You  [VOICE]" if is_voice else "You  [TEXT]"
    _insert_message(label,text,"you_name","you_msg")

def add_axor(text):
    _insert_message("Axor",text,"axor_name","axor_msg")

def add_system_msg(text):
    _insert_message("System",text,"sys_name","sys_msg")

def add_error(text):
    _insert_message("Error",text,"sys_name","err_msg")

# Typing indicator
typing_active=[False]
def show_typing():
    typing_active[0]=True
    def animate_typing():
        dots=["   ", ".  ", ".. ", "..."]
        i=[0]
        def tick():
            if not typing_active[0]: return
            chat_display.config(state=tk.NORMAL)
            # Update last line if it's typing
            last=chat_display.get("end-2l","end-1c")
            if "Axor is thinking" in last:
                chat_display.delete("end-2l","end-1c")
                chat_display.insert(tk.END,f"Axor is thinking{dots[i[0]%4]}\n","sys_msg")
            chat_display.see(tk.END)
            chat_display.config(state=tk.DISABLED)
            i[0]+=1
            if typing_active[0]: root.after(400,tick)
        chat_display.config(state=tk.NORMAL)
        chat_display.insert(tk.END,"\nAxor is thinking...\n","sys_msg")
        chat_display.see(tk.END)
        chat_display.config(state=tk.DISABLED)
        root.after(400,tick)
    root.after(0,animate_typing)

def hide_typing():
    typing_active[0]=False
    chat_display.config(state=tk.NORMAL)
    last=chat_display.get("end-2l","end-1c")
    if "Axor is thinking" in last:
        chat_display.delete("end-2l","end-1c")
        chat_display.delete("end-2l","end-1c")
    chat_display.config(state=tk.DISABLED)

# ════════════════════════════════════════
# INPUT AREA
# ════════════════════════════════════════
tk.Frame(main_frame,bg="#141414",height=1).pack(fill="x")

input_outer=tk.Frame(main_frame,bg="#080808",padx=28,pady=14)
input_outer.pack(fill="x")

input_border=tk.Frame(input_outer,bg="#1e1e1e",padx=1,pady=1)
input_border.pack(fill="x")

input_inner=tk.Frame(input_border,bg="#0f0f0f")
input_inner.pack(fill="x")

text_input=tk.Text(input_inner,font=("Helvetica Neue",13),
    bg="#0f0f0f",fg="#e0e0e0",insertbackground="#10a37f",
    borderwidth=0,highlightthickness=0,relief="flat",
    wrap=tk.WORD,height=1,padx=16,pady=12)
text_input.pack(side="left",fill="x",expand=True)
text_input.insert("1.0","")

def auto_resize(e=None):
    lines=int(text_input.index('end-1c').split('.')[0])
    text_input.configure(height=min(max(lines,1),5))

text_input.bind("<KeyRelease>",auto_resize)

inp_btns=tk.Frame(input_inner,bg="#0f0f0f")
inp_btns.pack(side="right",padx=8,pady=8)

mic_btn=tk.Button(inp_btns,text="🎙",font=("Helvetica Neue",15),
    fg="#333",bg="#0f0f0f",activebackground="#0f0f0f",activeforeground="#10a37f",
    borderwidth=0,relief="flat",cursor="hand2",padx=6)
mic_btn.pack(side="left")

send_btn=tk.Button(inp_btns,text="↑",font=("Helvetica Neue",14,"bold"),
    fg="#fff",bg="#10a37f",activebackground="#0d8f6e",activeforeground="#fff",
    borderwidth=0,relief="flat",cursor="hand2",
    padx=10,pady=4)
send_btn.pack(side="left",padx=(6,0))

hint_lbl=tk.Label(main_frame,
    text="Enter to send  ·  Shift+Enter for new line  ·  Ctrl+Option to speak from anywhere",
    font=("Helvetica Neue",9),fg="#1a1a1a",bg="#080808")
hint_lbl.pack(pady=(0,10))

# Focus fix for text input
def on_input_click(e):
    text_input.focus_force()
    input_border.config(bg="#1a3028")

def on_input_leave(e):
    input_border.config(bg="#1e1e1e")

text_input.bind("<Button-1>",on_input_click)
text_input.bind("<FocusOut>",on_input_leave)

# ════════════════════════════════════════
# EXECUTE + DISPLAY
# ════════════════════════════════════════
def execute_and_display(command,use_voice=False):
    if is_processing[0]: return
    is_processing[0]=True
    root.after(0,lambda t=command: add_you(t,use_voice))
    set_status("Thinking...","#f59e0b","#f59e0b")
    root.after(0,show_typing)

    def do_work():
        response=run_command(command)
        root.after(0,hide_typing)
        root.after(0,lambda r=response: add_axor(r))
        root.after(0,lambda: set_status("Ready","#10a37f","#333"))
        if use_voice:
            threading.Thread(target=speak,args=(response,),daemon=True).start()
        if response.strip().endswith("?"):
            play_ding()
        is_processing[0]=False

    threading.Thread(target=do_work,daemon=True).start()

# ════════════════════════════════════════
# SEND TEXT
# ════════════════════════════════════════
def send_text(event=None):
    command=text_input.get("1.0",tk.END).strip()
    if not command: return "break"
    text_input.delete("1.0",tk.END)
    text_input.configure(height=1)
    execute_and_display(command,use_voice=False)
    return "break"

text_input.bind("<Return>",send_text)
text_input.bind("<Shift-Return>",lambda e:None)
send_btn.config(command=send_text)

# ════════════════════════════════════════
# VOICE
# ════════════════════════════════════════
def begin_recording():
    if is_processing[0] or is_recording[0]: return
    is_recording[0]=True
    bar_target[0]=0.8
    mic_btn.config(fg="#ef4444")
    set_status("Listening...","#ef4444","#ef4444")
    start_audio()

def end_recording():
    if not is_recording[0]: return
    is_recording[0]=False
    stop_audio()
    bar_target[0]=0.15
    mic_btn.config(fg="#333")
    set_status("Transcribing...","#f59e0b","#f59e0b")
    threading.Thread(target=voice_session,daemon=True).start()

def voice_session():
    if len(audio_frames)<3:
        root.after(0,lambda: add_system_msg("Too short — hold longer!"))
        root.after(0,lambda: set_status("Ready","#10a37f","#333"))
        is_processing[0]=False; return

    filepath=save_wav()
    try:
        text=transcribe(filepath); os.unlink(filepath)
        print(f"Heard: '{text}'")
    except Exception as e:
        root.after(0,lambda: add_error(f"Transcription error: {str(e)}"))
        root.after(0,lambda: set_status("Ready","#10a37f","#333"))
        is_processing[0]=False; return

    if not text or len(text.strip())<2:
        root.after(0,lambda: add_system_msg("Nothing heard — try again"))
        root.after(0,lambda: set_status("Ready","#10a37f","#333"))
        is_processing[0]=False; return

    execute_and_display(text,use_voice=True)

def toggle_mic():
    if is_recording[0]: end_recording()
    elif not is_processing[0]:
        is_processing[0]=True; begin_recording()

mic_btn.config(command=toggle_mic)

# ════════════════════════════════════════
# KEYBOARD
# ════════════════════════════════════════
def _on_press(key):
    try:
        if key in (kb_listener.Key.alt_l,kb_listener.Key.alt_r): _opt[0]=True
        if key in (kb_listener.Key.ctrl_l,kb_listener.Key.ctrl_r): _ctrl[0]=True
        if _opt[0] and _ctrl[0] and not _active[0] and not is_processing[0]:
            _active[0]=True; root.after(0,begin_recording)
    except: pass

def _on_release(key):
    try:
        if key in (kb_listener.Key.alt_l,kb_listener.Key.alt_r): _opt[0]=False
        if key in (kb_listener.Key.ctrl_l,kb_listener.Key.ctrl_r): _ctrl[0]=False
        if _active[0] and (not _opt[0] or not _ctrl[0]):
            _active[0]=False; root.after(0,end_recording)
    except: pass

kb=kb_listener.Listener(on_press=_on_press,on_release=_on_release)
kb.daemon=True; kb.start()

# ════════════════════════════════════════
# STARTUP
# ════════════════════════════════════════
def startup():
    time.sleep(0.5)
    greeting=f"Hello {OWNER_NAME}! I'm Axor, your personal AI assistant. Type below or hold Ctrl+Option to speak. I'll respond in text for typed commands and voice for spoken ones."
    root.after(0,lambda: add_axor(greeting))
    speak(greeting)

refresh_sidebar()
add_system_msg("Axor initialized — Whisper model ready.")
threading.Thread(target=startup,daemon=True).start()

print(f"\n✅ {AGENT_NAME} is running.")
print(f"   Hold Ctrl+Option to speak, release when done.")
print(f"   Or type in the box and press Enter.\n")

root.lift()
root.attributes('-topmost',True)
root.after(300,lambda: root.attributes('-topmost',False))
root.mainloop()