# Voice Assistant default (can be overridden at runtime)

import os

# Path to store the permanent assistant voice
VOICE_FILE = os.path.join(os.path.dirname(__file__), "assistant_voice.txt")

def load_assistant_voice():
	if os.path.exists(VOICE_FILE):
		with open(VOICE_FILE, "r", encoding="utf-8") as f:
			return f.read().strip()
	return os.getenv("ASSISTANT_VOICE", "coral")

def save_assistant_voice(voice_name):
	with open(VOICE_FILE, "w", encoding="utf-8") as f:
		f.write(voice_name)

assistant_voice = load_assistant_voice()
