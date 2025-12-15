
def get_tools():
    return [RAG_TOOL, VOICE_TOOL, DB_TOOL]
# --- TOOL 1: RAG ---
RAG_TOOL = {
    "type": "function",
    "name": "query_knowledge_base",
    "description": "Use this tool to get information about DJF Law Firm cases, pricing, etc.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The user's question."}
        },
        "required": ["query"]
    }
}

# --- TOOL 2: VOICE CHANGER ---
VOICE_TOOL = {
    "type": "function",
    "name": "change_voice",
    "description": "Change the assistant's voice to a specific preset.",
    "parameters": {
        "type": "object",
        "properties": {
            "voice_name": {
                "type": "string",
                "enum": ["alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"],
                "description": "The name of the voice to switch to."
            }
        },
        "required": ["voice_name"]
    }
}

# --- TOOL 3: DB SAVE (Updated for your Model)---
DB_TOOL = {
    "type": "function",
    "name": "create_contact_entry",
    "description": "Save user's contact details into the database for a consultation callback.",
    "parameters": {
        "type": "object",
        "properties": {
            "first_name": {"type": "string", "description": "User's first name"},
            "last_name": {"type": "string", "description": "User's last name (if provided, else blank)"},
            "phone": {"type": "string", "description": "User's phone number"},
            "email": {"type": "string", "description": "User's email address"} # Description update
        },
        "required": ["first_name", "phone", "email"] 
    }
}


# NEW TOOL: CHANGE LANGUAGE 
LANGUAGE_TOOL = {
    "type": "function",
    "name": "change_language",
    "description": "Changes the speaking language of the assistant for the rest of the conversation.",
    "parameters": {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "description": "The language to switch to (e.g., Hindi, English, Spanish)."
            }
        },
        "required": ["language"]
    }
}


# ==========================================
# GLOBAL LANGUAGE MAP
# ==========================================
LANGUAGE_MAP = {
    # --- 1. ENGLISH (Default) ---
    "english": {
        "code": "en",
        "prompt": "Hello. I speak professional English. Legal terms included.",
        "instructions": "You must speak in ENGLISH only."
    },
    
    # --- 2. NORTH INDIAN LANGUAGES ---
    "hindi": {
        "code": "hi",
        "prompt": "Namaste. Main Hindi bolta hoon. Sirf Devanagari script use karein.",
        "instructions": "You must speak in HINDI only."
    },
    "urdu": {
        "code": "ur",
        "prompt": "Assalam-o-Alaikum. Main Urdu bolta hoon. Sirf Urdu script likhein.",
        "instructions": "You must speak in URDU only."
    },
    "hinglish": {
        "code": "hi",
        "prompt": "Hello, Namaste. I speak Hinglish (Mix of Hindi and English).",
        "instructions": "You must speak in HINGLISH (Mix of Hindi & English)."
    },

    # --- 3. SOUTH INDIAN LANGUAGES (New ---
    "tamil": {
        "code": "ta",
        "prompt": "Vanakkam. Naan Tamilil pesugiren. (Hello, I speak Tamil). Please use Tamil Script.",
        "instructions": "You must speak in TAMIL only."
    },
    "telugu": {
        "code": "te",
        "prompt": "Namaskaram. Nenu Telugu lo matladutunnanu. (Hello, I speak Telugu). Please use Telugu Script.",
        "instructions": "You must speak in TELUGU only."
    },
    "kannada": {
        "code": "kn",
        "prompt": "Namaskara. Naanu Kannadadalli matanaduttene. (Hello, I speak Kannada). Please use Kannada Script.",
        "instructions": "You must speak in KANNADA only."
    },

    # --- 4. INTERNATIONAL LANGUAGES ---
    "spanish": {
        "code": "es",
        "prompt": "Hola. Soy asistente legal. Hablo español.",
        "instructions": "You must speak in SPANISH only."
    },
    "chinese": {
        "code": "zh",
        "prompt": "你好。我是律师助手。请使用简体中文 (Simplified Chinese).",
        "instructions": "You must speak in CHINESE (Mandarin) only."
    },
    "japanese": {
        "code": "ja",
        "prompt": "こんにちは。法律事務所のアシスタントです。日本語で話してください。",
        "instructions": "You must speak in JAPANESE only."
    },
    "french": {
        "code": "fr",
        "prompt": "Bonjour. Je suis assistant juridique. Je parle français. (Hello, I speak French).",
        "instructions": "You must speak in FRENCH only."
    },
}

