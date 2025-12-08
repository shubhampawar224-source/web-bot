# voice_assistant.py

import asyncio
import io
import os
import json
import base64
import uuid
import time
from fastapi import WebSocket
from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI
from voice_config.simple_rag_agent import EnhancedRAGAgent
# from enhanced_rag_agent import EnhancedRAGAgent   # <--- NEW IMPORT

load_dotenv(override=True)

client_async = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class VoiceAssistant:

    def __init__(self):
        self.sessions = {}
        self.rag = EnhancedRAGAgent()

    # ===========================================================
    # WEBSOCKET HANDLER
    # ===========================================================
    async def handle_ws(self, ws: WebSocket):
        await ws.accept()
        session_id = str(uuid.uuid4())
        await ws.send_json({"info": "session_created", "session_id": session_id})
         # ✅ GREETING FIX
        await self.safe_send(
            ws,
            "Hello! I am your Law Firm voice assistant. How can I help you today?",
            None
        )
        silence = asyncio.create_task(self.silence_timeout(ws))

        try:
            while True:
                data = await ws.receive_text()
                msg = json.loads(data)

                if msg.get("stop"):
                    silence.cancel()
                    await ws.close()
                    break

                if msg.get("audio"):
                    silence.cancel()
                    silence = asyncio.create_task(self.silence_timeout(ws))
                    audio_bytes = base64.b64decode(msg["audio"])

                    await self.process_audio(ws, audio_bytes, session_id)

        except Exception:
            await ws.close()
            silence.cancel()

    # ===========================================================
    async def silence_timeout(self, ws):
        try:
            await asyncio.sleep(10)
            await ws.send_json({"bot_text": "No input detected. Closing session."})
            await ws.close()
        except:
            pass

    # ===========================================================
    async def process_audio(self, ws, audio_bytes, session_id):
        fname = f"temp_{uuid.uuid4()}.wav"
        open(fname, "wb").write(audio_bytes)

        try:
            # STT step
            with open(fname, "rb") as f:
                stt = await client_async.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language="en"
                )

            user_text = stt.text.strip()

            if not user_text:
                return

            print("User:", user_text)

            reply = await asyncio.to_thread(self.rag.search_and_respond, user_text)

            await self.safe_send(ws, reply, user_text)

        finally:
            if os.path.exists(fname):
                os.remove(fname)

    # ===========================================================
    # STREAMING TTS
    # ===========================================================
    async def safe_send(self, ws, text, user_text=None):

        await ws.send_json({
            "type": "text_start",
            "bot_text": text,
            "user_text": user_text
        })

        try:
            async with client_async.audio.speech.with_streaming_response.create(
                model="tts-1",
                voice="alloy",
                input=text,
                response_format="mp3"
            ) as resp:

                async for chunk in resp.iter_bytes(chunk_size=6000):
                    if not chunk:
                        continue

                    audio_b64 = base64.b64encode(chunk).decode()
                    await ws.send_json({
                        "type": "audio_chunk",
                        "audio": audio_b64
                    })
                    
            print("TTS stream complete")

        except Exception as e:
            print("TTS error:", e)
            if ws.client_state.name == "CONNECTED":
                await ws.send_json({"type": "error", "message": "TTS Failed"})
