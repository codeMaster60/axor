import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OWNER_NAME = os.getenv("OWNER_NAME", "Jayanth")
AGENT_NAME = os.getenv("AGENT_NAME", "Axor")

CONTACTS = {
    # Add contacts later
}