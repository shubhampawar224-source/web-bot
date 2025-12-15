
import asyncio
import os
import json
from dotenv import load_dotenv
from fastapi import WebSocket, WebSocketDisconnect
import logging
import websockets
import re
import config

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

async def communication(websocket: WebSocket):
    await websocket.accept()
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }


    try:
        async with websockets.connect(OPENAI_URL, additional_headers=headers) as openai_ws:
            default_lang = "english"
            default_config = LANGUAGE_MAP[default_lang]
            print(f"assistant_voice voice: {config.assistant_voice}")

            current_voice = config.assistant_voice if config.assistant_voice else "shimmer"
            print(f"Using voice: {current_voice}")
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "voice": current_voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {
                        "model": "whisper-1",
                        "language": default_config["code"],
                        "prompt": default_config["prompt"]
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 200
                    },
                    "tools": [RAG_TOOL, DB_TOOL, LANGUAGE_TOOL],
                    "tool_choice": "auto",
                    # ⭐ UPDATED LOGIC: DEFAULT vs EXPLICIT ⭐
                    "instructions": f"""
                    You are a smart voice assistant for DJF Law Firm.
                    
                    🛑 **STRICT SCOPE:** - You handle Legal Inquiries and Appointments ONLY.
                    - If user asks about unrelated topics (Weather, Coding, Movies), politely refuse.
                    
                    🔵 **PRIORITY 1: DEFAULT INTERACTION (THE CATCH-ALL)**
                    - If the user says "Hello", asks a question, seeks advice, or says ANYTHING that is NOT a direct request to book:
                    1. **ALWAYS** use the `query_knowledge_base` tool.
                    2. Converse naturally and answer their query.
                    3. **NEVER** assume they want to book. **NEVER** ask for name/phone yet.
                    
                    🔴 **PRIORITY 2: BOOKING (EXPLICIT TRIGGER ONLY)**
                    - Activate this mode **ONLY** if the user specifically uses words like: **"Book appointment"**, **"Schedule a call"**, **"I want to meet"**, or **"Take my details"**.
                    - If triggered, follow this EXACT sequence:
                    1. **Step 1:** Ask: "Sure. What is your **Full Name**?" -> WAIT.
                    2. **Step 2:** Ask: "Thanks. What is your **Phone Number**?" -> WAIT.
                    3. **Step 3:** Ask: "And your **Email Address**?" -> WAIT.
                    
                    ⚠️ **DATA RULES:**
                    1. **PHONE:** Copy exactly as spoken (String). Do not change digits.
                    2. **SAVE:** Call `create_contact_entry` ONLY after getting all 3 details.
                    
                    **LANGUAGE RULES:**
                    1. Start in English.
                    2. If user speaks English, reply in English.
                    3. Keep answers short.
                    """
                }
            }
            await openai_ws.send(json.dumps(session_config))

            await openai_ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": "Say 'Hello! I am your DJF Law Firm assistant. How can I help you today?'"
                }
            }))

            # --- Tasks ---
            async def receive_from_client():
                try:
                    while True:
                        data = await websocket.receive_text()
                        msg = json.loads(data)
                        if "audio" in msg:
                            await openai_ws.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": msg["audio"]
                            }))
                except WebSocketDisconnect:
                    logger.info("Client disconnected.")
                except Exception:
                    pass

            async def receive_from_openai():
                try:
                    async for message in openai_ws:
                        event = json.loads(message)
                        evt_type = event.get("type")

                        if evt_type == "response.audio.delta":
                            await websocket.send_json({"type": "audio_chunk", "audio": event["delta"]})

                        elif evt_type == "response.audio_transcript.done":
                            await websocket.send_json({"type": "transcript", "role": "assistant", "text": event["transcript"]})

                        elif evt_type == "conversation.item.input_audio_transcription.completed":
                            transcript = event.get("transcript", "")
                            if transcript:
                                await websocket.send_json({"type": "transcript", "role": "user", "text": transcript})

                        elif evt_type == "response.function_call_arguments.done":
                            call_id = event["call_id"]
                            tool_name = event["name"]
                            args = json.loads(event["arguments"])
                            
                            logger.info(f"Tool Triggered: {tool_name}")
                            output_result = "Done."

                            if tool_name == "change_language":
                                req_lang = args.get("language", "english").lower()
                                lang_settings = LANGUAGE_MAP.get(req_lang, LANGUAGE_MAP["english"])
                                await websocket.send_json({"type": "log", "message": f"Switching to {req_lang}..."})
                                
                                new_instructions = f"""
                                You are a smart voice assistant for DJF Law Firm.
                                CRITICAL UPDATE: User switched to {req_lang.upper()}.
                                1. {lang_settings['instructions']}
                                2. DEFAULT: Answer ALL questions using RAG.
                                3. BOOKING: Only start if explicitly requested (Name -> Phone -> Email).
                                4. RULE: Copy phone digits EXACTLY.
                                """
                                await openai_ws.send(json.dumps({
                                    "type": "session.update",
                                    "session": { 
                                        "instructions": new_instructions,
                                        "input_audio_transcription": {
                                            "model": "whisper-1",
                                            "language": lang_settings["code"], 
                                            "prompt": lang_settings["prompt"]
                                        }
                                    }
                                }))
                                output_result = f"Language switched to {req_lang}."

                            elif tool_name == "create_contact_entry":
                                fname = args.get("first_name", "Unknown")
                                lname = args.get("last_name", "")
                                raw_phone = str(args.get("phone", ""))
                                # Python Cleaning Logic
                                if raw_phone.startswith("00") or raw_phone.startswith("+"):
                                    cleaned_phone = re.sub(r'\D', '', raw_phone)
                                    if len(cleaned_phone) > 10:
                                        cleaned_phone = cleaned_phone[-10:]
                                    args['phone'] = cleaned_phone
                                phone = args['phone']
                                email = args.get("email", None)
                                
                                await websocket.send_json({"type": "log", "message": f"Saving {fname}..."})
                                try:
                                    success = await asyncio.to_thread(save_contact_to_db, fname, lname, phone, email)
                                    output_result = "Success. Details saved." if success else "Failed to save."
                                except:
                                    output_result = "Error saving details."

                            elif tool_name == "change_voice":
                                new_voice = args.get("voice_name")
                                current_voice = new_voice
                                await websocket.send_json({"type": "log", "message": f"Voice: {new_voice}"})
                                await openai_ws.send(json.dumps({
                                    "type": "session.update",
                                    "session": { "voice": new_voice }
                                }))
                                await asyncio.sleep(0.5)
                                output_result = f"Voice changed to {new_voice}."

                            elif tool_name == "query_knowledge_base":
                                await websocket.send_json({"type": "log", "message": "Thinking..."})
                                query = args.get("query")
                                output_result = await RAG.search_and_respond(query)
                                if not output_result or "not found" in output_result.lower():
                                    output_result = "SYSTEM: No info found. Apologize."

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