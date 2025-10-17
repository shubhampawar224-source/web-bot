# main.py
import os, io, base64, json, tempfile, subprocess, shutil
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
import numpy as np
import faiss
import torch
import torchaudio
from transformers import Wav2Vec2Processor, Wav2Vec2Model, AutoTokenizer, AutoModel
from elevenlabs import ElevenLabs, VoiceSettings
from sqlalchemy.orm import Session
from database.db import SessionLocal
from model.models import Website
from typing import List
from utils.data_convert import embed_text, build_faiss_from_db


load_dotenv(override=True)

# ---------------- ElevenLabs Setup ----------------

ELEVEN_API_KEY = os.getenv("ELEVENLABS_API_KEY", "sk_f6bfc2ce5bc40726870ea1ce6ba0bf8ce174b3bef9cc4281")
print("ELEVEN_API_KEY....",ELEVEN_API_KEY)
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
if not ELEVEN_API_KEY:
    raise RuntimeError("Set ELEVENLABS_API_KEY in .env")

eleven = ElevenLabs(api_key=ELEVEN_API_KEY)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/voice")
async def index():
    return FileResponse("static/voice.html")

# ---------------- models ----------------
# audio embedder (Wav2Vec2)
wav_processor = Wav2Vec2Processor.from_pretrained("facebook/wav2vec2-base-960h")
wav_model = Wav2Vec2Model.from_pretrained("facebook/wav2vec2-base-960h")
wav_model.eval()

# text embedder for FAISS (sentence-transformers)
text_tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
text_model = AutoModel.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
text_model.eval()

def embed_text(text: str):
    inputs = text_tokenizer(text, return_tensors="pt", truncation=True, padding=True)
    with torch.no_grad():
        out = text_model(**inputs).last_hidden_state
    return out.mean(dim=1).cpu().numpy().astype("float32")

def embed_audio_from_wav_bytes(wav_bytes: bytes):
    # load with torchaudio (wav PCM)
    waveform, sr = torchaudio.load(io.BytesIO(wav_bytes))
    if waveform.dim() > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    inputs = wav_processor(waveform.squeeze(0), sampling_rate=sr, return_tensors="pt", padding=True)
    with torch.no_grad():
        out = wav_model(**inputs).last_hidden_state
    return out.mean(dim=1).cpu().numpy().astype("float32")

# ---------------- FAISS build/load ----------------

faiss_index, faiss_texts, faiss_meta = build_faiss_from_db()

# ---------------- utilities ----------------
def webm_to_wav_bytes(webm_bytes: bytes) -> bytes:
    """
    Converts webm/opus (from MediaRecorder) to wav PCM bytes using ffmpeg.
    Returns wav bytes.
    """
    with tempfile.TemporaryDirectory() as td:
        in_path = os.path.join(td, "in.webm")
        out_path = os.path.join(td, "out.wav")
        with open(in_path, "wb") as f: f.write(webm_bytes)

        # ffmpeg command: convert to 16k mono wav (WAV PCM 16)
        cmd = [
            "ffmpeg", "-y", "-i", in_path,
            "-ar", "16000", "-ac", "1",
            "-vn", "-f", "wav", out_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        with open(out_path, "rb") as f: wav = f.read()
    return wav

def query_faiss_by_embedding(emb: np.ndarray, top_k=1):
    D, I = faiss_index.search(emb, k=top_k)
    results = []
    for idx in I[0]:
        results.append({"text": faiss_texts[idx], "meta": faiss_meta[idx]})
    return results

def synthesize_text_to_base64(text: str, voice_id: str = VOICE_ID) -> str:
    audio_bytes = eleven.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id="eleven_turbo_v2_5",
        output_format="mp3_22050_32",
        voice_settings=VoiceSettings(stability=0.75, similarity_boost=0.75, style=0.5, use_speaker_boost=True)
    )
    return base64.b64encode(audio_bytes).decode()

# ---------------- WebSocket streaming protocol ----------------
# frontend will send JSON messages:
# { type: "chunk", audio: "<base64 webm chunk>" }
# { type: "end" }    -> indicates end of utterance
# optional: { type:"hello" } ping
# backend response: { type: "response", text: "...", audio: "<base64 mp3>" }

@app.websocket("/ws/audio")
async def ws_audio(ws: WebSocket):
    await ws.accept()
    # we will collect incoming webm chunks into a temporary file
    tmp_chunks = []
    try:
        while True:
            msg = await ws.receive_text()
            payload = json.loads(msg)
            typ = payload.get("type","chunk")
            if typ == "hello":
                await ws.send_text(json.dumps({"type":"hello","status":"ok"}))
                continue

            if typ == "chunk":
                audio_b64 = payload.get("audio")
                if audio_b64:
                    chunk_bytes = base64.b64decode(audio_b64)
                    tmp_chunks.append(chunk_bytes)
                # optional: you could implement partial VAD-based processing here
                continue

            if typ == "end":
                # assemble full webm bytes
                webm_full = b"".join(tmp_chunks)
                tmp_chunks = []  # reset for next utterance

                # convert to wav PCM bytes
                try:
                    wav_bytes = webm_to_wav_bytes(webm_full)
                except Exception as e:
                    await ws.send_text(json.dumps({"type":"error","message":"ffmpeg conversion failed","detail":str(e)}))
                    continue

                # embed audio
                try:
                    audio_emb = embed_audio_from_wav_bytes(wav_bytes)  # shape (1, dim)
                except Exception as e:
                    await ws.send_text(json.dumps({"type":"error","message":"audio embed failed","detail":str(e)}))
                    continue

                # query FAISS
                results = query_faiss_by_embedding(audio_emb, top_k=1)
                best_text = results[0]["text"] if results else "Maaf — mujhe iska jawab nahi mila."

                # generate TTS via ElevenLabs
                try:
                    audio_b64_resp = synthesize_text_to_base64(best_text, voice_id=payload.get("voice_id", VOICE_ID))
                except Exception as e:
                    await ws.send_text(json.dumps({"type":"error","message":"TTS failed","detail":str(e)}))
                    continue

                # send response
                out_msg = {"type":"response","text":best_text,"audio":audio_b64_resp}
                await ws.send_text(json.dumps(out_msg))
                continue

            # unknown type
            await ws.send_text(json.dumps({"type":"error","message":"unknown message type"}))

    except Exception:
        await ws.close()
