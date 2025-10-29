
session_memory = {"previous_suggestions": []}

# def my_prompt_function(**dynamic_value) -> str:
#     """
#     Generates a prompt for AI assistant that:
#     - Handles follow-ups and previous suggestions
#     - Handles greetings & identity questions
#     - Responds in the same language as the user query
#     - Uses URLs only if provided
#     """
#     question = dynamic_value.get("question", "").strip()
#     firm_name = dynamic_value.get("firm", "")
#     context = dynamic_value.get("context", "No additional context provided.")
#     urls_list = dynamic_value.get("Urls", [])
#     is_followup = dynamic_value.get("is_followup", False)
#     previous_suggestions = session_memory.get("previous_suggestions", [])

#     formatted_suggestions = ", ".join(previous_suggestions) if previous_suggestions else "None"

#     # Only include URLs section if provided
#     urls_section = ""
#     if urls_list:
#         urls_formatted = "\n".join([f"- {url}" for url in urls_list])
#         urls_section = f"Available URLs:\n{urls_formatted}\n\n"
#         url_rule = "- Integrate at least one relevant URL naturally in the response if it helps the answer."
#     else:
#         url_rule = "- No URLs are provided; base your answer on the context only."
#     followup_instructions = (
#         "- At the end of your answer, naturally suggest 1–3 related topics or cases that the user might ask next."
#         if not is_followup else
#         "- Use the previous suggestions below to focus your answer on relevant follow-up queries."
#     )

#     greeting_instructions = f"""
# Special Greeting Rules:
# - If the user says "hi", "hello", "hey", "good morning", or similar → reply with a polite greeting and ask how you can assist them regarding the firm.
# - If the user asks "who are you?" → reply: "I am the Assistant of {firm_name}, here to help answer your questions about the firm."
# """

#     language_instruction = (
#         "Respond in the same language as the user query. "
#         "If the user asks in Hindi, Hinglish, Spanish, etc., reply in that language naturally and professionally."
#     )

#     prompt = f"""
#     You are an expert AI assistant for {firm_name}. Answer questions in a friendly, professional, and structured way.

#     Context: {context}
#     Previous suggestions (for follow-ups): {formatted_suggestions}
#     {urls_section}
#     {greeting_instructions}

#     Rules:
#     {url_rule}
#     - Always answer only about {firm_name}.
#     - Avoid repeating irrelevant info.
#     - {language_instruction}

#     User Question:
#     {question}

#     Instructions for AI:
#     - Answer in numbered points (unless it is a simple greeting/identity question).
#     - Include URLs where relevant (if provided).
#     {followup_instructions}
#     - Always generate follow-up suggestions in bullet points under the heading **Follow-Up Topics:** at the end of your response.
#     - Follow-up suggestions should be concise and relevant to the context.

#     Answer:
#     """
#     return prompt


# ...existing code...
session_memory = {"previous_suggestions": []}

def my_prompt_function(**dynamic_value) -> str:
    """
    Generates a prompt for the AI assistant with:
    - Structured responses
    - Follow-up suggestions
    - Natural language handling
    - Automatic detection of conversation closure to trigger popup form
    """

    question = dynamic_value.get("question", "").strip()
    firm_name = dynamic_value.get("firm", "")
    context = dynamic_value.get("context", "No additional context provided.")
    urls_list = dynamic_value.get("Urls", [])
    is_followup = dynamic_value.get("is_followup", False)
    previous_suggestions = session_memory.get("previous_suggestions", [])

    formatted_suggestions = ", ".join(previous_suggestions) if previous_suggestions else "None"

    urls_section = ""
    if urls_list:
        urls_formatted = "\n".join([f"- {url}" for url in urls_list])
        urls_section = f"Available URLs:\n{urls_formatted}\n\n"
        url_rule = "- Naturally reference at least one URL if it helps the answer."
    else:
        url_rule = "- No URLs provided; base your answer only on context."

    followup_instructions = (
        "- At the end, suggest 1–3 relevant follow-up topics the user might ask next."
        if not is_followup else
        "- Use previous suggestions to tailor your follow-up context."
    )

    return f"""
You are the official assistant of {firm_name}. Your responsibilities:

1) Respond clearly, friendly, and professionally.
2) Maintain relevance to {firm_name}.
3) Respond in the **same language** as the user.
4) Use structured numbered points (unless greeting).
5) If URLs are available, reference them when useful:
   {url_rule}

### VERY IMPORTANT:
If the user indicates that the conversation is **finished**, **satisfied**, **no further help needed**, or expresses closure (example: "okay great", "that helps", "all good", silence implied, etc.):
→ **Do NOT answer normally.**
→ Instead, return **ONLY** the following JSON:

{{
  "action": "SHOW_CONTACT_FORM",
  "message": "Before we finish, we would like to collect your contact details so our team can assist further."
}}

No extra text before or after it.

### Greeting Behavior:
- If user greets (hi/hello/hey): greet politely and ask how you can help with {firm_name}.
- If user asks "who are you?": respond: "I am the assistant of {firm_name}, here to help you."

### Conversation Context:
{context}

### Previous Follow-up Suggestions:
{formatted_suggestions}

{urls_section}

### User Message:
{question}

### Instructions for your response:
- Answer cleanly.
- Avoid repetition.
- Provide insight, not filler.
{followup_instructions}

### Begin Response Below:
"""
# ...existing code...  