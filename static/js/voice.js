const micBtn = document.getElementById("micBtn");
const statusEl = document.getElementById("status");
const botAudio = document.getElementById("botAudio");
const botSpeaking = document.getElementById("botSpeaking");
const waveform = document.getElementById("waveform");
const pauseBtn = document.getElementById("pauseBtn");
const resumeBtn = document.getElementById("resumeBtn");
const stopBtn = document.getElementById("stopBtn");
const silenceProgress = document.getElementById("silenceProgress");
const progressFill = document.getElementById("progressFill");
const progressText = document.getElementById("progressText");

let ws = null;
let mediaRecorder = null;
let audioChunks = [];
let sessionId = null;
let animationInterval = null;

// Create waveform bars
for (let i = 0; i < 20; i++) {
  const bar = document.createElement("div");
  bar.classList.add("bar");
  waveform.appendChild(bar);
}

function animateWave() {
  const bars = document.querySelectorAll(".bar");
  bars.forEach(bar => {
    bar.style.height = `${10 + Math.random() * 40}px`;
  });
}

// ----------------------
// Dynamic WS URL
// ----------------------
function getWsUrl() {
  const host = window.location.hostname;
  if (host === "localhost" || host === "127.0.0.1") {
    return `ws://${host}:8000/ws/voice`;
  } else {
    return `wss://mickie-springy-unaccusingly.ngrok-free.dev/ws/voice`;
  }
}

// ----------------------
// Recording Function with Silence Detection
// ----------------------
async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(stream);

    // ✅ Create analyser for silence detection
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    const bufferLength = analyser.fftSize;
    const dataArray = new Float32Array(bufferLength);
    source.connect(analyser);

    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    let hasSound = false;
    let silenceCount = 0;
    let isRecording = true;
    let silenceThreshold = 15; // 3 seconds (15 * 200ms checks)
    let lastSoundTime = Date.now();

    function detectSilence() {
      if (!isRecording) return;
      
      analyser.getFloatTimeDomainData(dataArray);
      const rms = Math.sqrt(dataArray.reduce((sum, v) => sum + v * v, 0) / bufferLength);
      const db = 20 * Math.log10(rms + 1e-8);
      
      // Sound detected (above threshold)
      if (db > -50) {
        hasSound = true;
        silenceCount = 0;
        lastSoundTime = Date.now();
        statusEl.textContent = "🎙️ Listening... (Speaking detected)";
        statusEl.className = "speaking";
        silenceProgress.style.display = "none";
      } else {
        // Silence detected
        silenceCount++;
        
        if (hasSound && silenceCount >= silenceThreshold) {
          // User has spoken and now been silent for 3 seconds
          console.log("3 seconds of silence detected after speech - sending audio");
          mediaRecorder.stop();
          isRecording = false;
          statusEl.textContent = "Processing your question...";
          statusEl.className = "processing";
          silenceProgress.style.display = "none";
        } else if (silenceCount > 0 && hasSound) {
          // Show countdown during silence
          const remainingTime = Math.max(0, silenceThreshold - silenceCount);
          const secondsLeft = Math.ceil(remainingTime * 0.2);
          const progressPercent = ((silenceThreshold - remainingTime) / silenceThreshold) * 100;
          
          statusEl.textContent = `🔇 Waiting for silence...`;
          statusEl.className = "waiting";
          silenceProgress.style.display = "block";
          progressFill.style.width = `${progressPercent}%`;
          progressText.textContent = `${secondsLeft}s remaining`;
        }
      }
      
      // Maximum recording time: 30 seconds
      if (Date.now() - lastSoundTime > 30000) {
        console.log("Maximum recording time reached");
        mediaRecorder.stop();
        isRecording = false;
      }
    }

    const silenceInterval = setInterval(detectSilence, 200); // Check every 200ms

    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);

    mediaRecorder.onstop = async () => {
      clearInterval(silenceInterval);
      isRecording = false;
      
      const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });

      if (!hasSound || audioBlob.size < 2000) {
        console.log("No meaningful audio detected");
        statusEl.textContent = "No speech detected. Try again...";
        statusEl.className = "";
        // Restart recording after a brief pause
        setTimeout(() => {
          statusEl.textContent = "🎙️ Listening...";
          statusEl.className = "";
          startRecording();
        }, 2000);
      } else {
        const arrayBuffer = await audioBlob.arrayBuffer();
        const base64Audio = btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)));
        ws?.send(JSON.stringify({ audio: base64Audio, session_id: sessionId }));
        console.log("Audio sent to server for processing");
        statusEl.textContent = "🤖 Thinking...";
        statusEl.className = "processing";
      }

      // Clean up audio stream
      stream.getTracks().forEach(t => t.stop());
    };

    mediaRecorder.start();
    statusEl.textContent = "🎙️ Listening... (Start speaking)";
    statusEl.className = "";

  } catch (err) {
    console.error("Microphone error:", err);
    statusEl.textContent = "Microphone access denied!";
  }
}

// ----------------------
// MIC CLICK → Create WebSocket Connection
// ----------------------
micBtn.onclick = async () => {
  if (ws && ws.readyState === 1) {
    console.warn("WebSocket already open");
    return;
  }

  micBtn.disabled = true;
  micBtn.classList.add("recording");
  statusEl.textContent = "Connecting...";

  ws = new WebSocket(getWsUrl());

  ws.onopen = () => {
    console.log("WS Connected.");
    statusEl.textContent = "Waiting for session...";
  };

  ws.onmessage = async (event) => {
    const data = JSON.parse(event.data);

    // First message = session ID
    if (data.session_id) {
      sessionId = data.session_id;
      console.log("Session started:", sessionId);
      statusEl.textContent = "🎙️ Ready! Start speaking...";
      animationInterval = setInterval(animateWave, 100);
      startRecording();
      return;
    }

    // Voice response from server
    if (data.audio && data.bot_text) {
      clearInterval(animationInterval);
      botSpeaking.classList.add("active");
      statusEl.textContent = "🤖 Speaking...";

      // Show text response temporarily
      const textDiv = document.createElement("div");
      textDiv.className = "bot-response";
      textDiv.textContent = data.bot_text;
      textDiv.style.cssText = `
        position: fixed; top: 20px; left: 50%; transform: translateX(-50%);
        background: rgba(0,0,0,0.8); color: white; padding: 10px 20px;
        border-radius: 20px; max-width: 80%; z-index: 1000;
        font-size: 14px; text-align: center;
      `;
      document.body.appendChild(textDiv);

      const audioBlob = new Blob(
        [Uint8Array.from(atob(data.audio), c => c.charCodeAt(0))],
        { type: "audio/wav" }
      );
      botAudio.src = URL.createObjectURL(audioBlob);
      botAudio.play();

      botAudio.onended = () => {
        botSpeaking.classList.remove("active");
        statusEl.textContent = "🎙️ Listening... (Ask another question)";
        statusEl.className = "";
        
        // Remove text after speaking
        setTimeout(() => {
          if (textDiv.parentNode) {
            textDiv.parentNode.removeChild(textDiv);
          }
        }, 3000);
        
        // Start listening again
        startRecording();
        animationInterval = setInterval(animateWave, 100);
      };

      botAudio.onerror = () => {
        botSpeaking.classList.remove("active");
        statusEl.textContent = "🎙️ Audio playback error. Listening again...";
        statusEl.className = "";
        startRecording();
        animationInterval = setInterval(animateWave, 100);
      };
    }

    // Text-only response (fallback)
    if (data.bot_text && !data.audio) {
      statusEl.textContent = data.bot_text;
      setTimeout(() => {
        statusEl.textContent = "🎙️ Listening...";
        startRecording();
      }, 3000);
    }

    // Handle info messages
    if (data.info) {
      console.log("Info:", data.info);
    }
  };

  ws.onerror = (err) => {
    console.error("WS Error:", err);
    statusEl.textContent = "WebSocket error!";
    micBtn.disabled = false;
    micBtn.classList.remove("recording");
  };

  ws.onclose = () => {
    console.log("WS Closed.");
    micBtn.disabled = false;
    micBtn.classList.remove("recording");
    clearInterval(animationInterval);
    statusEl.textContent = "Connection closed.";
  };
};

// ----------------------
// STOP BUTTON
// ----------------------
stopBtn.onclick = () => {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
  if (ws && ws.readyState === 1) {
    ws.send(JSON.stringify({ stop: true, session_id: sessionId }));
    ws.close();
  }
  micBtn.disabled = false;
  statusEl.textContent = "Stopped.";
};
