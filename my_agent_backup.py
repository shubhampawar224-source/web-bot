import io
import base64
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from voice_config.voice_helper import *
# ----------------------------------
# ENVIRONMENT SETUP
# ----------------------------------
load_dotenv(override=True)
# ========================================
# FASTAPI SETUP
# ========================================
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

voice_assistant = VoiceAssistant()

@app.get("/voice")
async def get_index():
    return FileResponse("static/voice.html")


@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    await voice_assistant.handle_ws(ws)

    try:
        # Send greeting
        greeting = "Hello! I’m your AI voice assistant. How can I help you today?"
        await voice_assistant.safe_send(ws, greeting)

        # Listen loop
        while True:
            try:
                data = await ws.receive_json()
            except WebSocketDisconnect:
                print("⚠️ Client disconnected during receive.")
                break

            if not data.get("audio") or data.get("silence"):
                continue

            audio_bytes = base64.b64decode(data["audio"])
            exit_signal = await voice_assistant.process_audio(ws, audio_bytes, session_id)
            if exit_signal == "exit":
                break

    except Exception as e:
        print(f"💥 WebSocket error: {e}")
    finally:
        if ws.client_state.name == "CONNECTED":
            await ws.close()
        print(f"🔒 Session {session_id} closed.")


        