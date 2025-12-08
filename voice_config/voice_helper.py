# voice_assistant.py
"""
Optimized VoiceAssistant with:
- local STT via faster-whisper (tiny-int8)
- strict RAG (EnhancedRAGAgent)
- streaming TTS via OpenAI Async client
- tuned chunk size for smooth playback
"""

import asyncio
import io
import os
import json
import base64
import uuid
import logging
from fastapi import WebSocket
from dotenv import load_dotenv

# OpenAI async client for TTS and optional fallback STT
from openai import AsyncOpenAI

# RAG agent (strict) — your local file
from voice_config.simple_rag_agent import EnhancedRAGAgent

load_dotenv(override=True)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("VoiceAssistant")

# Async OpenAI
ASYNC_CLIENT = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Local STT settings (we selected tiny-int8)
USE_LOCAL_STT = True
LOCAL_STT_MODEL = os.getenv("LOCAL_STT_MODEL", "tiny-int8")  # tiny-int8 as requested

# Try initialize faster-whisper
whisper_model = None
if USE_LOCAL_STT:
    try:
        from faster_whisper import WhisperModel
        logger.info("Loading local Whisper model: %s (this may take a moment)...", LOCAL_STT_MODEL)
        whisper_model = WhisperModel(LOCAL_STT_MODEL, device="cpu", compute_type="int8")
        logger.info("Local Whisper loaded.")
    except Exception as e:
        logger.exception("Failed to load local whisper: %s. Falling back to OpenAI STT.", e)
        whisper_model = None
        USE_LOCAL_STT = False

class VoiceAssistant:
    def __init__(self):
        self.sessions = {}
        self.rag = EnhancedRAGAgent()
        # TTS settings
        self.tts_model = os.getenv("TTS_MODEL", "tts-1")
        self.tts_voice = os.getenv("TTS_VOICE", "alloy")
        # streaming chunk tuning
        self.chunk_size = int(os.getenv("TTS_CHUNK_SIZE", "4096"))

    async def handle_ws(self, ws: WebSocket):
        await ws.accept()
        session_id = str(uuid.uuid4())
        await ws.send_json({"info": "session_created", "session_id": session_id})

        # greeting (streamed)
        try:
            await self.safe_send(ws, "Hello! I am your Law Firm voice assistant. How can I help you today?")
        except Exception as e:
            logger.debug("Greeting failed: %s", e)

        silence = asyncio.create_task(self._silence_watchdog(ws))

        try:
            while True:
                data = await ws.receive_text()
                msg = json.loads(data)

                if msg.get("stop"):
                    silence.cancel()
                    await ws.close()
                    break

                audio_b64 = msg.get("audio")
                if audio_b64:
                    silence.cancel()
                    silence = asyncio.create_task(self._silence_watchdog(ws))
                    try:
                        audio_bytes = base64.b64decode(audio_b64)
                    except Exception:
                        logger.warning("Received invalid base64 audio")
                        continue

                    # process request (run in background)
                    await self.process_audio(ws, audio_bytes, session_id)

        except Exception as e:
            logger.exception("Websocket loop error: %s", e)
            try:
                await ws.close()
            except:
                pass
            silence.cancel()

    async def _silence_watchdog(self, ws: WebSocket, timeout: int = 10):
        try:
            await asyncio.sleep(timeout)
            if ws.client_state.name == "CONNECTED":
                await ws.send_json({"bot_text": "No input detected. Closing session."})
                await ws.close()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("watchdog error: %s", e)

    async def process_audio(self, ws: WebSocket, audio_bytes: bytes, session_id: str):
        # write temp file
        tmp = f"temp_{uuid.uuid4()}.wav"
        try:
            with open(tmp, "wb") as f:
                f.write(audio_bytes)
        except Exception as e:
            logger.exception("Failed to write temp audio: %s", e)
            return

        try:
            # 1) Transcribe (local faster-whisper if available)
            if USE_LOCAL_STT and whisper_model:
                user_text = await asyncio.to_thread(self._local_transcribe, tmp)
            else:
                # fallback to OpenAI API (async)
                try:
                    with open(tmp, "rb") as f:
                        resp = await ASYNC_CLIENT.audio.transcriptions.create(
                            model="whisper-1",
                            file=f,
                            language="en"
                        )
                    user_text = getattr(resp, "text", "") or ""
                except Exception as e:
                    logger.exception("OpenAI STT error: %s", e)
                    user_text = ""

            user_text = (user_text or "").strip()
            if not user_text:
                logger.info("Empty transcription result.")
                return

            logger.info("User said: %s", user_text)

            # 2) RAG search + answer (strict)
            # run in thread to avoid blocking
            reply = await asyncio.to_thread(self.rag.search_and_respond, user_text)
            if not reply:
                reply = "I couldn't find an answer right now. Could you try rephrasing?"

            # 3) Stream TTS
            await self.safe_send(ws, reply, user_text)

        except Exception as e:
            logger.exception("process_audio error: %s", e)
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    def _local_transcribe(self, path: str) -> str:
        try:
            segments, info = whisper_model.transcribe(path, beam_size=1)
            text = " ".join([s.text for s in segments]).strip()
            return text
        except Exception as e:
            logger.exception("Local transcribe failed: %s", e)
            return ""

    async def safe_send(self, ws: WebSocket, text: str, user_text: str = None):
        """
        Stream TTS to client:
        - Send text start so frontend can display immediately
        - Stream mp3 chunks (base64) to frontend as 'audio_chunk'
        """
        try:
            if ws.client_state.name != "CONNECTED":
                logger.debug("Client not connected, aborting safe_send.")
                return
        except Exception:
            # ws might not have client_state in certain frameworks - continue
            pass

        # immediate text event
        try:
            await ws.send_json({
                "type": "text_start",
                "bot_text": text,
                "user_text": user_text
            })
        except Exception as e:
            logger.debug("Could not send text_start: %s", e)

        # call OpenAI streaming TTS
        try:
            async with ASYNC_CLIENT.audio.speech.with_streaming_response.create(
                model=self.tts_model,
                voice=self.tts_voice,
                input=text,
                response_format="mp3"
            ) as resp:
                async for chunk in resp.iter_bytes(chunk_size=self.chunk_size):
                    if not chunk:
                        continue

                    # quick disconnected check
                    try:
                        if ws.client_state.name != "CONNECTED":
                            logger.debug("Client disconnected during TTS stream.")
                            break
                    except Exception:
                        # not all WS have client_state, ignore
                        pass

                    try:
                        audio_b64 = base64.b64encode(chunk).decode("utf-8")
                        await ws.send_json({"type": "audio_chunk", "audio": audio_b64})
                    except Exception as e:
                        logger.debug("Failed sending chunk: %s", e)
                        # break if ws closed
                        try:
                            if ws.client_state.name != "CONNECTED":
                                break
                        except Exception:
                            break

                    # tiny sleep to avoid backpressure on slower clients
                    await asyncio.sleep(0.0005)

            logger.info("TTS stream finished for text length %d", len(text))

        except Exception as e:
            logger.exception("TTS streaming failed: %s", e)
            try:
                if ws.client_state.name == "CONNECTED":
                    await ws.send_json({"type": "error", "message": "TTS failed"})
            except Exception:
                pass
