# ----------------- Load FAISS -----------------
import os
try:
    # Newer openai package exposes OpenAI
    from openai import OpenAI
    from dotenv import load_dotenv
    load_dotenv(override=True)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    _uses_new_openai = True
except Exception:
    # Fallback to older openai package API
    import openai
    from dotenv import load_dotenv
    load_dotenv(override=True)
    openai.api_key = os.getenv("OPENAI_API_KEY")
    client = openai
    _uses_new_openai = False

from utils.data_convert import build_or_load_faiss, embed_text

faiss_index, faiss_texts, faiss_metadata = build_or_load_faiss()

# ----------------- Utilities -----------------
MAX_CHARS = 3500

def truncate_text(text: str, max_chars: int = MAX_CHARS) -> str:
    return text[:max_chars] + " …" if len(text) > max_chars else text

def retrieve_faiss_response(query: str, k: int = 1):
    query_emb = embed_text(query)
    D, I = faiss_index.search(query_emb, k)
    results = []
    for idx in I[0]:
        results.append({
            "text": faiss_texts[idx],
            "metadata": faiss_metadata[idx]
        })
    if results:
        results[0]["text"] = truncate_text(results[0]["text"])
        return results[0]
    return {"text": "No relevant data found.", "metadata": {}}

def _create_chat_completion(messages, model="gpt-4o-mini", temperature=0.7):
    if _uses_new_openai:
        return client.chat.completions.create(model=model, messages=messages, temperature=temperature)
    else:
        # Older openai package uses ChatCompletion.create
        return client.ChatCompletion.create(model=model, messages=messages, temperature=temperature)

def _extract_assistant_content(response):
    # New client: response.choices[0].message.content
    try:
        return response.choices[0].message.content
    except Exception:
        # Older client: response.choices[0]['message']['content']
        return response.choices[0]['message']['content']

def refine_text_with_gpt(user_text: str, faiss_text: str) -> str:
    """Refine the FAISS + STT response using GPT for contextual accuracy"""
    prompt = (
        f"You are a helpful assistant. The user said:\n{user_text}\n\n"
        f"FAISS retrieved this context:\n{faiss_text}\n\n"
        "Return a clear, natural response based on both."
    )
    response = _create_chat_completion(
        messages=[
            {"role": "system", "content": "You are an intelligent assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )
    return _extract_assistant_content(response)
