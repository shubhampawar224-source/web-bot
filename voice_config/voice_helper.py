import asyncio
import os
import json
import logging
import websockets
import re
import config
from fastapi import WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from typing import Optional, Tuple

# --- IMPORTS ---
from voice_config.simple_rag_agent import EnhancedRAGAgent
from voice_config.services.contact_service import save_contact_to_db 
from voice_config.services.my_tools import RAG_TOOL, VOICE_TOOL, DB_TOOL, LANGUAGE_TOOL, LANGUAGE_MAP

load_dotenv(override=True)
API_KEY = os.getenv("OPENAI_API_KEY")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VoiceServer")

RAG = EnhancedRAGAgent()
OPENAI_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"


def _extract_texts_from_response_output(output_items) -> list[str]:
    """Extract all textual content from a realtime response.output array."""
    texts: list[str] = []
    if not isinstance(output_items, list):
        return texts

    for item in output_items:
        if not isinstance(item, dict):
            continue
        content_list = item.get("content")
        if not isinstance(content_list, list):
            continue
        for content in content_list:
            if not isinstance(content, dict):
                continue
            # Different event types use different fields
            if "transcript" in content and isinstance(content.get("transcript"), str):
                texts.append(content.get("transcript") or "")
            if "text" in content and isinstance(content.get("text"), str):
                texts.append(content.get("text") or "")
    return [t for t in texts if t]


def _normalize_phone(raw_phone: str) -> str:
    # Keep digits only; take last 10 digits if longer (handles +91 etc.)
    digits = re.sub(r"\D", "", raw_phone or "")
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


def _extract_contact_from_json_text(text: str) -> Optional[Tuple[str, str, Optional[str]]]:
    """If text is a JSON object containing contact details, return (first_name, phone, email).

    The model sometimes responds with tool-arguments as text like:
    {"first_name":"Pavan Kumar","phone":"9413944510"}
    """
    if not text:
        return None
    s = text.strip()
    if not (s.startswith("{") and s.endswith("}")):
        return None
    try:
        obj = json.loads(s)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None

    first_name = obj.get("first_name") or obj.get("name") or ""
    phone = obj.get("phone") or obj.get("phone_number") or ""
    email = obj.get("email")

    if not first_name or not phone:
        return None

    phone = _normalize_phone(str(phone))
    if len(phone) < 10:
        return None
    return (str(first_name).strip(), phone, (str(email).strip() if email else None))

async def communication(websocket: WebSocket):
    await websocket.accept()
    headers = {"Authorization": f"Bearer {API_KEY}", "OpenAI-Beta": "realtime=v1"}

    # Track if contact info was provided but tool not called
    contact_info_provided = {
        "name": None,
        "phone": None,
        "email": None,
        "tool_called": True,
        "last_saved_key": None,
    }

    try:
        async with websockets.connect(OPENAI_URL, additional_headers=headers) as openai_ws:
            
            # Guard against invalid voice names (invalid preset can lead to cancelled responses)
            allowed_voices = {"alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"}
            current_voice = config.assistant_voice if config.assistant_voice else "shimmer"
            if current_voice not in allowed_voices:
                print(f"⚠️ Invalid voice preset '{current_voice}', falling back to 'shimmer'")
                current_voice = "shimmer"
            print(f"Using Voice: {current_voice}")

            # 1. SESSION CONFIG
            tools_list = [RAG_TOOL, VOICE_TOOL, DB_TOOL, LANGUAGE_TOOL]
            tool_names = [tool['name'] for tool in tools_list]
            print(f"🔧 Registering {len(tools_list)} tools: {tool_names}")
            print(f"📋 DB_TOOL details: {DB_TOOL}")
            
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "voice": current_voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {"model": "whisper-1", "language": "en"},
                    "turn_detection": {"type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300, "silence_duration_ms": 1000},
                    "tools": tools_list,
                    "tool_choice": "auto",
                }
            }
            await openai_ws.send(json.dumps(session_config))

            # ⭐ 2. MASTER PROMPT (Modified for Default English) ⭐
            master_system_msg = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": """
                            You are the AI Receptionist for DJF Law Firm.
                            
                            **🛑 STRICT CONTEXT RULES:**
                            1. **Legal Questions:** Use `query_knowledge_base`. NEVER answer from memory.
                            2. **Out of Scope:** If user talks about weather/coding/jokes, REFUSE politely.
                            
                            **📝 BOOKING RULES (PRIORITY):**
                            - **Trigger:** "Book call", "Schedule appointment", "Callback", "Contact me", "Call back", "I want to book", "Schedule me".
                            - **Step 1:** Ask "What's your name?" -> Wait for response.
                            - **Step 2:** Ask "What's your phone number?" -> Wait for response.
                                                        - **PHONE VALIDATION:** Only accept a phone number if you clearly have at least 10 digits.
                                                            If the user gives fewer than 10 digits or an unclear number, ask them to repeat it.
                                                            NEVER guess, invent, or "fix" missing digits.
                            - **Step 3:** Ask "Email address?" (Optional, if user wants) -> Wait.
                                                        - **Step 4:** **IMMEDIATELY CALL `create_contact_entry` TOOL AS SOON AS YOU HAVE NAME AND A VALID (>=10 digits) PHONE.**
                            - **MANDATORY:** Once you have first_name and phone, YOU MUST call the create_contact_entry tool immediately.
                            - **NO DELAYS:** Do not ask additional questions after getting name and phone. Call the tool right away.
                            - **CRITICAL:** DO NOT ask for Date/Time (No calendar access). Save contact immediately after getting name and phone.
                            
                            **🌐 LANGUAGE PROTOCOL:**
                            - **Default Language:** English.
                            - **Switching Rule:** ONLY if the user explicitly speaks in Hindi or asks to switch -> Call `change_language` tool.
                            - Once switched, reply in that language.
                            
                            **⚡ IMMEDIATE ACTION RULE:**
                            If user provides name AND a VALID (>=10 digits) phone in ANY message, IMMEDIATELY call create_contact_entry tool.
                            If the phone is shorter than 10 digits or unclear, ask them to repeat it. NEVER guess digits.
                            
                            **🚫 NEVER SAY CALLBACK WITHOUT TOOL:**
                            NEVER say "we will call you" or "someone will contact you" WITHOUT calling create_contact_entry tool first.
                            If you say callback promises, you MUST call the tool.
                            
                            **EXAMPLE:** 
                            User: "Hi, I want to schedule a callback. My name is John and my number is 9876543210"
                            YOU: Immediately call create_contact_entry with first_name="John", phone="9876543210"
                            THEN say: "Thank you John, your callback is scheduled."
                            """
                        }
                    ]
                }
            }
            await openai_ws.send(json.dumps(master_system_msg))
            await openai_ws.send(json.dumps({"type": "response.create"}))

            # 3. GREETING
            await openai_ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": "Say 'Hello! Welcome to DJF Law Firm. How can I help you today?'"
                }
            }))

            # --- Tasks ---
            async def receive_from_client():
                try:
                    while True:
                        data = await websocket.receive_text()
                        msg = json.loads(data)
                        if "audio" in msg:
                            await openai_ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": msg["audio"]}))
                except WebSocketDisconnect:
                    pass
                except Exception:
                    pass

            async def receive_from_openai():
               
                try:
                    async for message in openai_ws:
                        event = json.loads(message)
                        evt_type = event.get("type")
                        # print(f"🔔 OpenAI Event: {evt_type}")
                        # print(f"Full Event Data: {event}")
                        # Debugging
                        if evt_type == "response.audio_transcript.done":
                            print(f"🤖 AI SAID: {event['transcript']}")

                        # Track response generation
                        elif evt_type == "response.created":
                            print(f"🔄 RESPONSE STARTED: {event.get('response', {}).get('id', 'Unknown')}")
                            
                        elif evt_type == "response.done":
                            response_data = event.get('response', {})
                            print(f"✅ RESPONSE COMPLETED: {response_data.get('id', 'Unknown')}")
                            print(f"📊 Status: {response_data.get('status', 'Unknown')}")
                            if 'output' in response_data:
                                print(f"📤 Response output: {response_data['output']}")
                                
                            # ⚡ CHECK IF RESPONSE COMPLETED WITHOUT TOOL CALL
                            output_items = response_data.get("output", [])
                            texts = _extract_texts_from_response_output(output_items)
                            response_text = "\n".join(texts)

                            # If model returned contact details as JSON text (common failure mode),
                            # save it and force a friendly spoken confirmation so the UI doesn't stall.
                            extracted = _extract_contact_from_json_text(response_text)
                            if extracted:
                                extracted_name, extracted_phone, extracted_email = extracted
                                save_key = f"{extracted_name}|{extracted_phone}|{extracted_email or ''}"

                                if contact_info_provided.get("last_saved_key") != save_key:
                                    print("🚨 Detected contact JSON inside response.done output. Persisting...")
                                    try:
                                        name_parts = [p for p in extracted_name.split() if p]
                                        first = name_parts[0] if name_parts else extracted_name
                                        last = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

                                        success = await asyncio.to_thread(
                                            save_contact_to_db,
                                            first,
                                            last,
                                            extracted_phone,
                                            extracted_email,
                                        )
                                        print(f"✅ Manual save result: {success}")
                                        contact_info_provided["last_saved_key"] = save_key
                                        contact_info_provided["tool_called"] = True
                                        contact_info_provided["name"] = extracted_name
                                        contact_info_provided["phone"] = extracted_phone
                                        contact_info_provided["email"] = extracted_email
                                    except Exception as manual_err:
                                        print(f"💥 Manual save error: {manual_err}")

                                    confirm_text = (
                                        f"Thank you {extracted_name}! Your callback request is scheduled. "
                                        "Our team will contact you soon."
                                    )

                                    # Send transcript to UI immediately
                                    try:
                                        await websocket.send_json({"type": "transcript", "role": "assistant", "text": confirm_text})
                                    except Exception:
                                        pass

                                    # Force TTS/audio response (avoid raw JSON output)
                                    try:
                                        await openai_ws.send(json.dumps({
                                            "type": "response.create",
                                            "response": {
                                                "modalities": ["text", "audio"],
                                                "instructions": confirm_text,
                                            },
                                        }))
                                    except Exception as tts_err:
                                        print(f"⚠️ Failed forcing audio confirmation: {tts_err}")

                                    # Done handling this response
                                    continue
                            
                            # If AI says something about calling back but no tool was called, force it
                            callback_phrases = ["call you", "touch with you", "contact you", "get back", "reach out"]
                            has_callback_promise = any(phrase in response_text.lower() for phrase in callback_phrases)
                            
                            if (has_callback_promise and 
                                contact_info_provided["name"] and 
                                contact_info_provided["phone"] and 
                                not contact_info_provided["tool_called"]):
                                
                                print(f"🚨 AI PROMISED CALLBACK BUT NO TOOL CALL!")
                                print(f"🔥 MANUALLY CALLING create_contact_entry...")
                                
                                # Manually call the database save function
                                try:
                                    success = await asyncio.to_thread(
                                        save_contact_to_db, 
                                        contact_info_provided["name"], 
                                        "", 
                                        contact_info_provided["phone"], 
                                        None
                                    )
                                    if success:
                                        print(f"✅ MANUAL SAVE SUCCESS for {contact_info_provided['name']}")
                                    else:
                                        print(f"❌ MANUAL SAVE FAILED for {contact_info_provided['name']}")
                                        
                                    contact_info_provided["tool_called"] = True
                                except Exception as manual_err:
                                    print(f"💥 MANUAL SAVE ERROR: {str(manual_err)}")
                            # NOTE: Do NOT force additional tool calls just because the assistant used
                            # callback language. If the tool already ran, forcing here creates loops.

                        if evt_type == "response.audio.delta":
                            await websocket.send_json({"type": "audio_chunk", "audio": event["delta"]})

                        elif evt_type == "response.audio_transcript.done":
                            await websocket.send_json({"type": "transcript", "role": "assistant", "text": event["transcript"]})

                        # If the model outputs text (sometimes happens instead of audio), forward it so UI doesn't stall.
                        # Additionally, if it outputs contact JSON instead of calling the DB tool, persist it and force
                        # a natural language audio confirmation.
                        elif evt_type == "response.text.done":
                            text_out = event.get("text", "")
                            extracted = _extract_contact_from_json_text(text_out)

                            if extracted and not contact_info_provided.get("tool_called", True):
                                extracted_name, extracted_phone, extracted_email = extracted
                                contact_info_provided["name"] = extracted_name
                                contact_info_provided["phone"] = extracted_phone
                                contact_info_provided["email"] = extracted_email

                                print("🚨 Model returned contact JSON as text (no tool call). Persisting manually...")
                                try:
                                    # Split full name best-effort
                                    name_parts = [p for p in extracted_name.split() if p]
                                    first = name_parts[0] if name_parts else extracted_name
                                    last = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

                                    success = await asyncio.to_thread(
                                        save_contact_to_db,
                                        first,
                                        last,
                                        extracted_phone,
                                        extracted_email,
                                    )
                                    contact_info_provided["tool_called"] = True
                                    print(f"✅ Manual save result: {success}")
                                except Exception as manual_err:
                                    print(f"💥 Manual save error: {manual_err}")

                                # Force assistant to speak a friendly confirmation (avoid raw JSON output)
                                confirm_text = (
                                    f"Thank you {extracted_name}! Your callback request is scheduled. "
                                    "Our team will contact you soon."
                                )

                                try:
                                    await websocket.send_json({"type": "transcript", "role": "assistant", "text": confirm_text})
                                except Exception:
                                    pass

                                force_say_msg = {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "message",
                                        "role": "system",
                                        "content": [{
                                            "type": "input_text",
                                            "text": (
                                                "You previously output contact details as JSON. "
                                                "Those details are now saved. "
                                                "Now respond to the user with a short friendly confirmation sentence. "
                                                "DO NOT output JSON."
                                            )
                                        }]
                                    }
                                }
                                await openai_ws.send(json.dumps(force_say_msg))
                                await openai_ws.send(json.dumps({
                                    "type": "response.create",
                                    "response": {
                                        "modalities": ["text", "audio"],
                                        "instructions": confirm_text
                                    }
                                }))

                            else:
                                # Normal text response: forward to UI for visibility
                                if text_out:
                                    await websocket.send_json({"type": "transcript", "role": "assistant", "text": text_out})

                        elif evt_type == "conversation.item.input_audio_transcription.completed":
                            transcript = event.get("transcript", "")
                            if transcript:
                                print(f"🎤 USER SAID: {transcript}") 
                                await websocket.send_json({"type": "transcript", "role": "user", "text": transcript})
                                
                                # Check if this looks like appointment booking
                                transcript_lower = transcript.lower()
                                booking_keywords = ["book", "schedule", "appointment", "callback", "call back", "contact me"]
                                name_phone_pattern = any(keyword in transcript_lower for keyword in booking_keywords)
                                
                                if name_phone_pattern:
                                    print(f"🔔 DETECTED POTENTIAL BOOKING REQUEST: {transcript}")
                                    
                                # Also check if name and phone are provided
                                phone_pattern = re.search(r'\b\d{10,12}\b', transcript)
                                name_pattern = re.search(r'name.{0,20}([A-Za-z]{2,})', transcript_lower)
                                
                                if phone_pattern:
                                    print(f"📱 PHONE NUMBER DETECTED: {phone_pattern.group()}")
                                    contact_info_provided["phone"] = phone_pattern.group()
                                    
                                if name_pattern:
                                    print(f"👤 POSSIBLE NAME DETECTED: {name_pattern.group(1)}")
                                    contact_info_provided["name"] = name_pattern.group(1)
                                    
                                # Check if both name and phone are in same message
                                if phone_pattern and name_pattern:
                                    print(f"🚨 BOTH NAME & PHONE DETECTED - AI SHOULD CALL create_contact_entry TOOL!")
                                    print(f"Expected tool call: create_contact_entry(first_name='{name_pattern.group(1)}', phone='{phone_pattern.group()}')")

                                    # Mark tool pending so fallback logic can trigger if model doesn't call the tool.
                                    contact_info_provided["tool_called"] = False
                                    
                                    # MANUAL TRIGGER - Force tool call if AI doesn't do it
                                    manual_tool_call = {
                                        "type": "conversation.item.create",
                                        "item": {
                                            "type": "message",
                                            "role": "user", 
                                            "content": [{
                                                "type": "input_text",
                                                "text": f"Please save my details: Name is {name_pattern.group(1)} and phone is {phone_pattern.group()}. Call the create_contact_entry tool now."
                                            }]
                                        }
                                    }
                                    await openai_ws.send(json.dumps(manual_tool_call))
                                    await openai_ws.send(json.dumps({"type": "response.create"}))
                                    
                        # ⭐ Log when function call starts
                        elif evt_type == "response.function_call_arguments.delta":
                            print(f"📝 TOOL ARGS BUILDING: {event.get('name', 'Unknown')} | Delta: {event.get('delta', '')}")

                        # ⭐ TOOL LOGIC
                        elif evt_type == "response.function_call_arguments.done":
                            call_id = event["call_id"]
                            tool_name = event["name"]
                            print(f"🚀 TOOL CALL COMPLETE: {tool_name} | Call ID: {call_id}")
                            raw_args = event["arguments"]
                            
                            print(f"\n🚀 ===== TOOL CALL DETECTED ===== ")
                            print(f"📛 Tool Name: {tool_name}")
                            print(f"🆔 Call ID: {call_id}")
                            print(f"📄 Raw Arguments: {raw_args}")
                            
                            try:
                                args = json.loads(raw_args)
                                print(f"✅ Parsed Arguments: {args}")
                            except json.JSONDecodeError as parse_err:
                                print(f"❌ JSON Parse Error: {parse_err}")
                                args = {}
                            
                            # print(f"🔍 Full event data: {event}")
                            print(f"================================\n")
                            
                            output_result = "Done."
                            # --- 1. LANGUAGE ---
                            if tool_name == "change_language":
                                req_lang = args.get("language", "english").lower()
                                new_code = "hi" if "hindi" in req_lang else "en"
                                await websocket.send_json({"type": "log", "message": f"Language: {req_lang}"})
                                
                                # Update Whisper
                                await openai_ws.send(json.dumps({"type": "session.update", "session": {"input_audio_transcription": {"model": "whisper-1", "language": new_code}}}))
                                
                                # Reinforce Language Rule
                                update_sys = {"type": "conversation.item.create", "item": {"type": "message", "role": "system", "content": [{"type": "input_text", "text": f"User switched to {req_lang}. Reply ONLY in {req_lang}."}]}}
                                await openai_ws.send(json.dumps(update_sys))
                                output_result = f"Language switched to {req_lang}."

                            # --- 2. DB SAVE ---
                            elif tool_name == "create_contact_entry":
                                contact_info_provided["tool_called"] = True  # Mark tool as called
                                
                                arg_fname = args.get("first_name", "Unknown") 
                                arg_lname = args.get("last_name", "")
                                arg_phone = str(args.get("phone", ""))
                                arg_email = args.get("email", None)

                                # Track latest known contact info for fallback
                                contact_info_provided["name"] = arg_fname
                                contact_info_provided["phone"] = arg_phone
                                contact_info_provided["email"] = arg_email
                                
                                # Clean Phone - Better logic
                                try:
                                    # Remove all non-digit characters
                                    clean_phone = re.sub(r'\D', '', arg_phone)
                                    
                                    # Handle international numbers (+91, +1, etc.)
                                    if len(clean_phone) > 10:
                                        # Take last 10 digits for Indian numbers
                                        clean_phone = clean_phone[-10:]
                                    
                                    arg_phone = clean_phone
                                    print(f"📞 Phone cleaned: {arg_phone}")
                                except Exception as phone_err:
                                    print(f"⚠️ Phone cleaning error: {phone_err}")
                                    # Keep original phone if cleaning fails
                                    pass

                                # Validate: do NOT save if number is too short; never "fix" missing digits.
                                if len(arg_phone) < 10:
                                    print(f"⚠️ Phone too short to save: '{arg_phone}'")
                                    contact_info_provided["tool_called"] = False
                                    output_result = (
                                        "Invalid phone number. TELL USER: 'I may have missed a digit. "
                                        "Please repeat your full 10-digit phone number.'"
                                    )
                                else:

                                    # De-dupe: if the model repeats the same tool call, don't insert again.
                                    save_key = f"{arg_fname}|{arg_phone}|{arg_email or ''}"
                                    if contact_info_provided.get("last_saved_key") == save_key:
                                        print(f"ℹ️ Duplicate create_contact_entry ignored for key={save_key}")
                                        output_result = (
                                            f"Already saved. TELL USER: 'Thanks {arg_fname}! We already have your callback request. "
                                            "Our team will contact you soon.'"
                                        )
                                    elif output_result == "Done.":

                                        await websocket.send_json({"type": "log", "message": "Saving appointment data..."})

                                        try:
                                            print(f"🔄 Calling save_contact_to_db with: {arg_fname}, {arg_lname}, {arg_phone}, {arg_email}")
                                            success = await asyncio.to_thread(
                                                save_contact_to_db, arg_fname, arg_lname, arg_phone, arg_email
                                            )

                                            if success:
                                                contact_info_provided["last_saved_key"] = save_key
                                                output_result = (
                                                    f"Success! Contact saved. TELL USER: 'Thank you {arg_fname}! "
                                                    f"Your callback request has been confirmed for {arg_phone}. "
                                                    "Our team will contact you soon.'"
                                                )
                                                print(f"✅ Database save successful for {arg_fname}")
                                            else:
                                                output_result = (
                                                    "Sorry, there was an issue saving your details. Please try again or contact us directly."
                                                )
                                                print(f"❌ Database save failed for {arg_fname}")

                                        except Exception as db_err:
                                            output_result = "Sorry, there was a technical issue. Please try again later."
                                            print(f"💥 Database error: {str(db_err)}")

                            # --- 3. RAG QUERY ---
                            elif tool_name == "query_knowledge_base":
                                query = args.get("query")
                                await websocket.send_json({"type": "log", "message": "Checking..."})
                                output_result = await RAG.search_and_respond(query)
                                if not output_result: output_result = "No info found."

                            # --- 4. VOICE CHANGE ---
                            elif tool_name == "change_voice":
                                new_voice = args.get("voice_name")
                                await openai_ws.send(json.dumps({"type": "session.update", "session": { "voice": new_voice }}))
                                output_result = "Voice changed."

                            # Send Output
                            await openai_ws.send(json.dumps({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": call_id,
                                    "output": output_result
                                }
                            }))
                            await openai_ws.send(json.dumps({"type": "response.create"}))
                            
                except Exception as e:
                    logger.error(f"OpenAI Error: {e}")

            await asyncio.gather(receive_from_client(), receive_from_openai())

    except Exception as e:
        logger.error(f"Connection Error: {e}")
        await websocket.close()