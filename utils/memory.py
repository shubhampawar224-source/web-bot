from collections import deque

# Global in-memory store for sessions (Fastest access)
# Format: { "session_id": deque([{role: "user", content: "..."}, ...], maxlen=10) }
SESSION_STORE = {}

def get_chat_history(session_id: str) -> list:
    """History fetch karo"""
    return list(SESSION_STORE.get(session_id, []))

def add_to_history(session_id: str, user_query: str, ai_response: str):
    """History update karo (Sirf last 10 messages rakhenge speed ke liye)"""
    if session_id not in SESSION_STORE:
        SESSION_STORE[session_id] = deque(maxlen=10) # Sirf last 10 messages yaad rakho
    
    SESSION_STORE[session_id].append({"role": "user", "content": user_query})
    SESSION_STORE[session_id].append({"role": "assistant", "content": ai_response})

def format_history_for_prompt(session_id: str) -> str:
    """LLM ke liye history ko string mein badlo"""
    history = get_chat_history(session_id)
    if not history:
        return "No previous conversation."
    
    formatted = []
    for msg in history:
        role = "User" if msg["role"] == "user" else "Assistant"
        formatted.append(f"{role}: {msg['content']}")
    
    return "\n".join(formatted)