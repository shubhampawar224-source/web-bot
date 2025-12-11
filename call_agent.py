import os
import datetime
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import JSONResponse, Response, HTMLResponse
from pydantic import BaseModel
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

app = FastAPI()

# --- CONFIGURATION ---
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
SERVER_BASE_URL = os.getenv('SERVER_BASE_URL')

# Initialize Clients
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# --- MEMORY STORE ---
call_sessions = {}

# --- DATA MODELS ---
class CallRequest(BaseModel):
    phone: str
    name: str = "Valued Customer"
    email: str = "Not Provided"

# --- 0. FRONTEND ROUTE ---
@app.get("/")
async def index():
    # Read the index.html file manually to serve it
    try:
        with open("templates/index.html", "r") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        return Response("index.html not found. Make sure 'templates/index.html' exists.", status_code=404)

# --- 1. CALL INITIATE API ---
@app.post("/make-call")
async def make_call(request: CallRequest):
    if not request.phone:
        raise HTTPException(status_code=400, detail="Phone number is required")

    try:
        # Twilio Call
        call = client.calls.create(
            to=request.phone,
            from_=TWILIO_PHONE_NUMBER,
            url=f"{SERVER_BASE_URL}/incoming-voice"
        )
        
        # Session Data
        call_sessions[call.sid] = {
            "user_name": request.name,
            "user_email": request.email,
            "transcript": [
                {
                    "role": "system", 
                    "text": f"Call Initiated. User: {request.name}, Email: {request.email}", 
                    "timestamp": str(datetime.datetime.now())
                }
            ]
        }
        
        return {"status": "Call Queued", "callSid": call.sid}
    except Exception as e:
        print(f"Error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

# --- 2. JAB USER CALL UTHAYEGA ---
@app.post("/incoming-voice")
async def incoming_voice(CallSid: str = Form(...)):
    # Note: Twilio sends data as Form Data, not JSON
    resp = VoiceResponse()
    
    user_name = "there"
    if CallSid in call_sessions:
        user_name = call_sessions[CallSid].get('user_name', 'there')
        
        greeting = f"Hello {user_name}, I am an AI Assistant. I received your request. How can I help you today?"
        
        call_sessions[CallSid]['transcript'].append(
            {"role": "ai", "text": greeting, "timestamp": str(datetime.datetime.now())}
        )
    else:
        greeting = "Hello, I am an AI Assistant. How can I help you?"

    resp.say(greeting, voice='alice', language='en-US')

    gather = Gather(
        input='speech',
        action=f"{SERVER_BASE_URL}/handle-speech",
        timeout=3,
        language='en-US'
    )
    resp.append(gather)
    
    # Loop back
    resp.redirect(f"{SERVER_BASE_URL}/incoming-voice")

    # Return XML Response
    return Response(content=str(resp), media_type="application/xml")

# --- 3. JAB USER BOLEGA (AI Logic) ---
@app.post("/handle-speech")
async def handle_speech(CallSid: str = Form(...), SpeechResult: str = Form(None)):
    resp = VoiceResponse()

    if SpeechResult:
        print(f"User ({CallSid}): {SpeechResult}")
        
        # Ensure session exists
        if CallSid not in call_sessions:
            call_sessions[CallSid] = {"transcript": [], "user_name": "User", "user_email": "Unknown"}
        
        # 1. User Speech Log
        call_sessions[CallSid]['transcript'].append(
            {"role": "user", "text": SpeechResult, "timestamp": str(datetime.datetime.now())}
        )

        # 2. Context
        user_name = call_sessions[CallSid].get('user_name', 'User')
        user_email = call_sessions[CallSid].get('user_email', 'Unknown')

        # 3. Prompt
        messages = [
            {
                "role": "system", 
                "content": f"You are a helpful AI support agent speaking to {user_name} (Email: {user_email}). "
                           f"Keep answers short, professional, and conversational in English."
            }
        ]
        
        # History
        for entry in call_sessions[CallSid]['transcript']:
            if entry['role'] == 'user':
                messages.append({"role": "user", "content": entry['text']})
            elif entry['role'] == 'ai':
                messages.append({"role": "assistant", "content": entry['text']})

        try:
            # OpenAI
            completion = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages
            )
            ai_reply = completion.choices[0].message.content
            
            # AI Log
            call_sessions[CallSid]['transcript'].append(
                {"role": "ai", "text": ai_reply, "timestamp": str(datetime.datetime.now())}
            )

            # Speak
            resp.say(ai_reply, voice='alice', language='en-US')
            
            # Listen Again
            gather = Gather(
                input='speech',
                action=f"{SERVER_BASE_URL}/handle-speech",
                timeout=3,
                language='en-US'
            )
            resp.append(gather)

        except Exception as e:
            print(f"AI Error: {e}")
            resp.say("I am facing a technical issue, please try again later.", language='en-US')

    else:
        resp.say("I didn't catch that, could you repeat?", language='en-US')
        resp.redirect(f"{SERVER_BASE_URL}/incoming-voice")

    return Response(content=str(resp), media_type="application/xml")

# --- 4. TRANSCRIPT API ---
@app.get("/transcript/{call_sid}")
async def get_transcript(call_sid: str):
    if call_sid in call_sessions:
        return {"success": True, "data": call_sessions[call_sid]}
    else:
        return JSONResponse(status_code=404, content={"success": False, "message": "Session not found"})

# Run with: uvicorn server:app --reload