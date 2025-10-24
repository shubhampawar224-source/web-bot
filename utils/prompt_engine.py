# session_memory = {"previous_suggestions": []}

# def my_prompt_function(**dynamic_value) -> str:
#     """
#     Generates a prompt that allows natural follow-up from previous suggestions,
#     handles greetings and identity questions, and ensures consistent follow-up topics.
#     """

#     question = dynamic_value.get("question", "").strip().lower()
#     firm_name = dynamic_value.get("firm", "")
#     context = dynamic_value.get("context", "No additional context provided.")
#     urls_list = dynamic_value.get("Urls", [])
#     is_followup = dynamic_value.get("is_followup", False)
#     previous_suggestions = session_memory.get("previous_suggestions", [])

#     # Format previous suggestions
#     formatted_suggestions = ", ".join(previous_suggestions) if previous_suggestions else "None"

#     # Format URLs
#     urls_formatted = "\n".join([f"- {url}" for url in urls_list]) if urls_list else "No URLs provided."

#     followup_instructions = ""
#     if not is_followup:
#         followup_instructions = (
#             "- At the end of your answer, naturally suggest 1–3 related topics or cases that according to the website context the user might ask about next."
#         )
#     else:
#         followup_instructions = (
#             "- Use the previous suggestions below as context to answer the user's follow-up query."
#         )

#     # Special handling for greetings & identity
#     greeting_instructions = """
# Special Greeting Rules:
# - If the user says "hi", "hello", "hey", "good morning", or similar → reply with a polite greeting and ask how you can assist them regarding the firm.
# - If the user asks "who are you?" → reply: "I am the Assistant of DJF Lawfirm, here to help answer your questions about the firm."
# """

#     prompt = f"""
# You are an expert AI assistant for {firm_name}. You should answer questions in a friendly, professional, and structured way.

# Context: {context}
# Previous suggestions (for follow-ups): {formatted_suggestions}
# Available URLs:
# {urls_formatted}

# {greeting_instructions}

# Rules:
# - Integrate at least one relevant URL naturally in the response if it helps the answer.
# - If this is a new question (is_followup=False), naturally suggest 1–3 follow-up topics at the end related to the context and according the website data.
# - If this is a follow-up (is_followup=True), use previous suggestions to focus the answer and avoid unrelated topics.
# - Always answer only about {firm_name}.
# - Avoid repeating irrelevant info.

# User Question:
# {question}

# Instructions for AI:
# - Answer in numbered points (unless it is a simple greeting/identity question).
# - Include URLs where relevant.
# {followup_instructions}
# - Always generate follow-up suggestions in bullet points under the heading **Follow-Up Topics:** at the end of your response.
# - Follow-up suggestions should be concise and relevant to the context.

# Answer:
# """
#     return prompt

session_memory = {"previous_suggestions": []}

def my_prompt_function(**dynamic_value) -> str:
    """
    Generates a prompt for AI assistant that:
    - Handles follow-ups and previous suggestions
    - Handles greetings & identity questions
    - Responds in the same language as the user query
    - Uses URLs only if provided
    """
    question = dynamic_value.get("question", "").strip()
    firm_name = dynamic_value.get("firm", "")
    context = dynamic_value.get("context", "No additional context provided.")
    urls_list = dynamic_value.get("Urls", [])
    is_followup = dynamic_value.get("is_followup", False)
    previous_suggestions = session_memory.get("previous_suggestions", [])

    formatted_suggestions = ", ".join(previous_suggestions) if previous_suggestions else "None"

    # Only include URLs section if provided
    urls_section = ""
    if urls_list:
        urls_formatted = "\n".join([f"- {url}" for url in urls_list])
        urls_section = f"Available URLs:\n{urls_formatted}\n\n"
        url_rule = "- Integrate at least one relevant URL naturally in the response if it helps the answer."
    else:
        url_rule = "- No URLs are provided; base your answer on the context only."
    followup_instructions = (
        "- At the end of your answer, naturally suggest 1–3 related topics or cases that the user might ask next."
        if not is_followup else
        "- Use the previous suggestions below to focus your answer on relevant follow-up queries."
    )

    greeting_instructions = f"""
Special Greeting Rules:
- If the user says "hi", "hello", "hey", "good morning", or similar → reply with a polite greeting and ask how you can assist them regarding the firm.
- If the user asks "who are you?" → reply: "I am the Assistant of {firm_name}, here to help answer your questions about the firm."
"""

    language_instruction = (
        "Respond in the same language as the user query. "
        "If the user asks in Hindi, Hinglish, Spanish, etc., reply in that language naturally and professionally."
    )

    prompt = f"""
    You are an expert AI assistant for {firm_name}. Answer questions in a friendly, professional, and structured way.

    Context: {context}
    Previous suggestions (for follow-ups): {formatted_suggestions}
    {urls_section}
    {greeting_instructions}

    Rules:
    {url_rule}
    - Always answer only about {firm_name}.
    - Avoid repeating irrelevant info.
    - {language_instruction}

    User Question:
    {question}

    Instructions for AI:
    - Answer in numbered points (unless it is a simple greeting/identity question).
    - Include URLs where relevant (if provided).
    {followup_instructions}
    - Always generate follow-up suggestions in bullet points under the heading **Follow-Up Topics:** at the end of your response.
    - Follow-up suggestions should be concise and relevant to the context.

    Answer:
    """
    return prompt
