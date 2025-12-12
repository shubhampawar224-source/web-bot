import asyncio
import os
import json
import logging
import websockets
from fastapi import WebSocket, WebSocketDisconnect
from dotenv import load_dotenv

# --- IMPORTS ---
from voice_config.simple_rag_agent import EnhancedRAGAgent
from voice_config.services.contact_service import save_contact_to_db 
from voice_config.services.my_tools import RAG_TOOL, VOICE_TOOL, DB_TOOL, LANGUAGE_TOOL, LANGUAGE_MAP

# Load Environment Variables
load_dotenv(override=True)
API_KEY = os.getenv("OPENAI_API_KEY")

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VoiceServer")

# Initialize RAG
RAG = EnhancedRAGAgent()

# OpenAI WebSocket URL
OPENAI_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"

# ==========================================
# MAIN COMMUNICATION FUNCTION 
# ==========================================

async def communication(websocket: WebSocket):
    await websocket.accept()
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }

    try:
        async with websockets.connect(OPENAI_URL, additional_headers=headers) as openai_ws:
            
            # Default Settings
            default_lang = "english"
            default_config = LANGUAGE_MAP[default_lang]
            
            # 1. VARIABLE FOR DYNAMIC VOICE
            current_voice = "verse"  # Default Voice

            # 2. Initialize Session
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    
                    # Voice is now Dynamic
                    "voice": current_voice,
                    
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    
                    "input_audio_transcription": {
                        "model": "whisper-1",
                        "prompt": default_config["prompt"]
                    },
                    
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 200
                    },
                    
                    "tools": [RAG_TOOL, VOICE_TOOL, DB_TOOL, LANGUAGE_TOOL],
                    "tool_choice": "auto",
                    
                    # MAIN INSTRUCTIONS (KEPT EXACTLY AS REQUESTED)
                    # MAIN INSTRUCTIONS (UPDATED FOR BOOKING)
                    "instructions": f"""
                    You are a smart voice assistant for DJF Law Firm.
                    
                    🔴 **CRITICAL RULE FOR BOOKING/CONSULTATION:**
                    If the user asks **"How to schedule?"**, **"Appointment"**, or **"Consultation details"**:
                    1. **DO NOT** say "I don't know" or search the database.
                    2. **INSTEAD, REPLY:** "I can schedule that for you right now. Please tell me your **Full Name**, **Phone Number**, and **Email**."
                    3. Once the user provides these 3 details, call the `create_contact_entry` tool immediately.
                    
                    🔴 **KNOWLEDGE BOUNDARIES:**
                    1. For general questions (services, pricing, laws), use 'query_knowledge_base'.
                    2. If the tool returns "No info", apologize.
                    3. DO NOT answer legal questions from your own general knowledge.
                    
                    **LANGUAGE RULES:**
                    1. Start in English.
                    2. If user speaks Hindi, reply in Hindi.
                    3. Keep answers short.
                    """
                }
            }
            await openai_ws.send(json.dumps(session_config))

            # 2. Welcome Message
            await openai_ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": "Say 'Hello! I am your DJF Law Firm assistant. I can help with firm-specific queries only.'"
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

                        # HANDLE TOOL CALLS
                        elif evt_type == "response.function_call_arguments.done":
                            call_id = event["call_id"]
                            tool_name = event["name"]
                            args = json.loads(event["arguments"])
                            
                            logger.info(f"Tool Triggered: {tool_name}")
                            output_result = "Done."

                            # ---------------------------------------
                            # 1. HANDLE LANGUAGE CHANGE
                            # ---------------------------------------
                            if tool_name == "change_language":
                                req_lang = args.get("language", "english").lower()
                                lang_settings = LANGUAGE_MAP.get(req_lang, LANGUAGE_MAP["english"])
                                
                                await websocket.send_json({"type": "log", "message": f"Switching to {req_lang}..."})
                                
                                # Only changing Transcription Prompt & Instructions (Voice Remains Same)
                                new_instructions = f"""
                                You are a smart voice assistant for DJF Law Firm.
                                🔴 CRITICAL UPDATE: User switched to {req_lang.upper()}.
                                
                                1. {lang_settings['instructions']}
                                2. Translate everything to {req_lang.upper()}.
                                
                                🔴 KNOWLEDGE BOUNDARY:
                                - USE 'query_knowledge_base' for ALL information.
                                - DO NOT use your own outside knowledge.
                                - If info is missing in tool output, say "I don't have that info".
                                """
                                
                                await openai_ws.send(json.dumps({
                                    "type": "session.update",
                                    "session": { 
                                        "instructions": new_instructions,
                                        "input_audio_transcription": {
                                            "model": "whisper-1",
                                            "prompt": lang_settings["prompt"]
                                        }
                                    }
                                }))
                                
                                output_result = f"Language switched to {req_lang}. Strict RAG mode active."

                            # ---------------------------------------
                            # 2. HANDLE LEAD CAPTURE
                            # ---------------------------------------
                            elif tool_name == "create_contact_entry":
                                fname = args.get("first_name", "Unknown")
                                lname = args.get("last_name", "")
                                phone = args.get("phone", "")
                                email = args.get("email", None)
                                await websocket.send_json({"type": "log", "message": f"Saving {fname}..."})
                                try:
                                    success = await asyncio.to_thread(save_contact_to_db, fname, lname, phone, email)
                                    output_result = "Success. Details saved." if success else "Failed to save."
                                except:
                                    output_result = "Error saving details."

                            # ---------------------------------------
                            # 3. VOICE CHANGE (Dynamic & Fixed)
                            # ---------------------------------------
                            elif tool_name == "change_voice":
                                new_voice = args.get("voice_name")
                                current_voice = new_voice # Update variable locally
                                
                                await websocket.send_json({"type": "log", "message": f"Voice: {new_voice}"})
                                
                                # Update Session
                                await openai_ws.send(json.dumps({
                                    "type": "session.update",
                                    "session": { "voice": new_voice }
                                }))
                                
                                # FIX: Wait for server to update voice before speaking
                                await asyncio.sleep(0.5)
                                
                                output_result = f"Voice changed to {new_voice}."

                            # ---------------------------------------
                            # 4. RAG
                            # ---------------------------------------
                            elif tool_name == "query_knowledge_base":
                                await websocket.send_json({"type": "log", "message": "Thinking..."})
                                query = args.get("query")
                                output_result = await RAG.search_and_respond(query)
                                
                                if not output_result or "not found" in output_result.lower():
                                    output_result = "SYSTEM: No information found in knowledge. Politely tell user you don't know."

                            # Send Output
                            await openai_ws.send(json.dumps({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": call_id,
                                    "output": output_result
                                }
                            }))
                            
                            # Force Response
                            await openai_ws.send(json.dumps({"type": "response.create"}))
                            
                except Exception as e:
                    logger.error(f"OpenAI Error: {e}")

            await asyncio.gather(receive_from_client(), receive_from_openai())

    except Exception as e:
        logger.error(f"Connection Error: {e}")
        await websocket.close()