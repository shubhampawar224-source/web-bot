import asyncio
import os
import json
import logging
import websocket
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Import the robust RAG agent
from voice_config.simple_rag_agent import EnhancedRAGAgent

# Load Environment Variables
load_dotenv(override=True)
API_KEY = os.getenv("OPENAI_API_KEY")

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VoiceServer")
RAG = EnhancedRAGAgent()
# OpenAI WebSocket URL
OPENAI_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"

# Tool Definition
RAG_TOOL = {
    "type": "function",
    "name": "query_knowledge_base",
    "description": "Use this tool to get information about DJF Law Firm cases, pricing, or specific legal topics.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The user's question or topic to search for."}
        },
        "required": ["query"]
    }
}
async def communication (websocket: WebSocket):
    await websocket.accept()
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }

    try:
        async with websockets.connect(OPENAI_URL, additional_headers=headers) as openai_ws:
            
            # 1. Initialize Session
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "voice": "alloy",
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {
                        "model": "whisper-1",
                        "language": "en"
                    },
                    # -------------------------------

                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500
                    },
                    "tools": [RAG_TOOL],
                    "tool_choice": "auto",
                    "instructions": "You are a helpful assistant for DJF Law Firm. Keep answers short. If the user asks about cases or info, use the tool."
                }
            }
            await openai_ws.send(json.dumps(session_config))

            # 2. Trigger Welcome Greeting
            await openai_ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": "Say 'Hello! I am your DJF Law Firm assistant. How can I help you today?'"
                }
            }))

            # --- Concurrent Tasks ---
            
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
                    logger.info("Client disconnected (WebSocket).")
                except Exception as e:
                    logger.error(f"Error receiving from client: {e}")

            async def receive_from_openai():
                try:
                    async for message in openai_ws:
                        event = json.loads(message)
                        evt_type = event.get("type")

                        if evt_type == "response.audio.delta":
                            await websocket.send_json({
                                "type": "audio_chunk",
                                "audio": event["delta"]
                            })

                        elif evt_type == "response.audio_transcript.done":
                            await websocket.send_json({
                                "type": "transcript",
                                "role": "assistant",
                                "text": event["transcript"]
                            })

                        # ⭐ Ye event ab trigger hoga kyunki humne whisper-1 enable kiya hai
                        elif evt_type == "conversation.item.input_audio_transcription.completed":
                            transcript = event.get("transcript", "")
                            # Backgorund noise kabhi kabhi khali text bhejta hai, use filter karein
                            if transcript and transcript.strip() != "":
                                await websocket.send_json({
                                    "type": "transcript",
                                    "role": "user",
                                    "text": transcript
                                })

                        elif evt_type == "response.function_call_arguments.done":
                            call_id = event["call_id"]
                            args = json.loads(event["arguments"])
                            query = args.get("query")
                            
                            logger.info(f"Tool Triggered: {query}")
                            await websocket.send_json({"type": "log", "message": f"Thinking..."})

                            # RAG Execution
                            result = await RAG.search_and_respond(query)

                            await openai_ws.send(json.dumps({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": call_id,
                                    "output": result
                                }
                            }))
                            
                            await openai_ws.send(json.dumps({"type": "response.create"}))
                            
                except Exception as e:
                    logger.error(f"OpenAI Error: {e}")

            await asyncio.gather(receive_from_client(), receive_from_openai())

    except Exception as e:
        logger.error(f"Connection Error: {e}")
        await websocket.close()


