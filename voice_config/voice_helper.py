import asyncio
import os
import json
import logging
import websockets
import re
import config
from fastapi import WebSocket, WebSocketDisconnect
from dotenv import load_dotenv

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
            current_voice = config.assistant_voice if config.assistant_voice else "shimmer"
            print(f"Using Voice: {current_voice}")

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
                        "silence_duration_ms": 1000 
                    },
                    
                    "tools": [RAG_TOOL, VOICE_TOOL, DB_TOOL, LANGUAGE_TOOL],
                    "tool_choice": "auto",
                    
                    # UPDATED INSTRUCTIONS: NO DATE/TIME
                    "instructions": f"""
                    You are a smart voice assistant for DJF Law Firm.
                    **STRICT CONTEXT RULE:**
                    - Answer ONLY questions related to Legal Matters or DJF Law Firm.
                    - If user asks about anything else (e.g. Weather, Coding, Jokes), REFUSE politely.
                    - Do NOT generate information outside the provided context.

                    **STRICT RULE: NO DATE OR TIME BOOKING**
                    - You do NOT schedule calendar appointments.
                    - You ONLY collect contact details for a **CALLBACK**.
                    - **NEVER ask for Date or Time.**
                    
                    **PRIORITY 1: DEFAULT INTERACTION**
                    - If user asks a question -> Use `query_knowledge_base`.
                    - Summarize answer in **2 lines max**.
                    
                    **PRIORITY 2: BOOKING (CALLBACK REQUEST)**
                    - Only if user says "Book appointment" or "Schedule call":
                    1. Say: "I can have our team call you back. What is your **Full Name**?" -> Wait.
                    2. Ask: "What is your **Phone Number**?" -> Wait.
                    3. Ask: "And your **Email**?" -> Wait.
                    4. **STOP.** Do not ask for Date/Time. Call `create_contact_entry` immediately.
                    
                    **DATA RULES:**
                    1. Phone: Treat digits as STRING. Copy exactly.
                    2. Save: Call tool immediately after getting Name, Phone, Email.
                    
                    **LANGUAGE RULES:**
                    1. Start in English.
                    2. If user speaks English, reply in English.
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
                                print(f"🎤 [USER SAID]: {transcript}") 
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
                                await websocket.send_json({"type": "log", "message": f"Thinking..."})
                                
                                new_instructions = f"""
                                You are a smart voice assistant for DJF Law Firm.
                                User switched to {req_lang.upper()}.
                                1. {lang_settings['instructions']}
                                2. RULE: NO DATE/TIME. Just Name, Phone, Email for callback.
                                3. Phone: Copy digits exactly.
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
                                
                                # Phone Cleaning
                                if raw_phone.startswith("00") or raw_phone.startswith("+"):
                                    cleaned_phone = re.sub(r'\D', '', raw_phone)
                                    if len(cleaned_phone) > 10:
                                        cleaned_phone = cleaned_phone[-10:]
                                    args['phone'] = cleaned_phone
                                phone = args['phone']
                                email = args.get("email", None)
                                
                                await websocket.send_json({"type": "log", "message": f"Thinking..."})
                                try:
                                    success = await asyncio.to_thread(save_contact_to_db, fname, lname, phone, email)
                                    output_result = "Success. Callback details saved." if success else "Failed to save."
                                except:
                                    output_result = "Error saving details."

                            elif tool_name == "change_voice":
                                new_voice = args.get("voice_name")
                                current_voice = new_voice
                                await websocket.send_json({"type": "log", "message": f"Changing voice..."})
                                await openai_ws.send(json.dumps({
                                    "type": "session.update",
                                    "session": { "voice": new_voice }
                                }))
                                await asyncio.sleep(0.5)
                                output_result = f"Voice changed."

                            elif tool_name == "query_knowledge_base":
                                await websocket.send_json({"type": "log", "message": "Thinking..."})
                                query = args.get("query")
                                output_result = await RAG.search_and_respond(query)
                                
                                if not output_result or "not found" in output_result.lower():
                                    output_result = "No info found."

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