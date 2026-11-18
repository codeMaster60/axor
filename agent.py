from groq import Groq
from config import GROQ_API_KEY, OWNER_NAME, AGENT_NAME
import subprocess
import os

client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = f"""You are {AGENT_NAME}, a powerful personal AI assistant for {OWNER_NAME}.
You run on {OWNER_NAME}'s Mac and have full control over it.
You can open/close apps, control the browser, manage files, send messages, read emails, set reminders, download apps, type documents, and literally anything a computer can do.
Always respond in a friendly, natural, conversational tone.
Keep responses short and clear — you speak them out loud.
If you can't do something, say so honestly in a simple sentence.
Always address the owner as {OWNER_NAME}."""

conversation_history = []

def ask_axor(user_input: str) -> str:
    conversation_history.append({
        "role": "user",
        "content": user_input
    })

    response = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            *conversation_history
        ],
        max_tokens=500,
        temperature=0.7
    )

    reply = response.choices[0].message.content

    conversation_history.append({
        "role": "assistant",
        "content": reply
    })

    return reply

def execute_mac_command(command: str) -> str:
    """Execute AppleScript or shell commands on Mac"""
    try:
        result = subprocess.run(
            ["osascript", "-e", command],
            capture_output=True, text=True
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {str(e)}"

def open_app(app_name: str):
    """Open any Mac application"""
    os.system(f"open -a '{app_name}'")

def close_app(app_name: str):
    """Close any Mac application"""
    execute_mac_command(f'quit app "{app_name}"')

def get_contacts_from_mac(name: str) -> str:
    """Get contact number from Mac Contacts app"""
    script = f'''
    tell application "Contacts"
        set thePeople to people whose name contains "{name}"
        if length of thePeople > 0 then
            set thePerson to item 1 of thePeople
            set thePhones to phones of thePerson
            if length of thePhones > 0 then
                return value of item 1 of thePhones
            end if
        end if
        return "Contact not found"
    end tell
    '''
    return execute_mac_command(script)