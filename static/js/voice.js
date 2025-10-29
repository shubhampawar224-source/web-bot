const micBtn = document.getElementById("micBtn");
const statusEl = document.getElementById("status");
const botAudio = document.getElementById("botAudio");
const botSpeaking = document.getElementById("botSpeaking");
const waveform = document.getElementById("waveform");
const pauseBtn = document.getElementById("pauseBtn");
const resumeBtn = document.getElementById("resumeBtn");
const stopBtn = document.getElementById("stopBtn");

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
// Recording Function
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

    function detectSilence() {
      analyser.getFloatTimeDomainData(dataArray);
      const rms = Math.sqrt(dataArray.reduce((sum, v) => sum + v * v, 0) / bufferLength);
      const db = 20 * Math.log10(rms + 1e-8);
      if (db > -50) hasSound = true;
    }

    const silenceInterval = setInterval(detectSilence, 200);

    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);

    mediaRecorder.onstop = async () => {
      clearInterval(silenceInterval);
      const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });

      if (!hasSound || audioBlob.size < 2000) {
        console.log("Silence detected — no audio sent");
        ws?.send(JSON.stringify({ silence: true, session_id: sessionId }));
      } else {
        const arrayBuffer = await audioBlob.arrayBuffer();
        const base64Audio = btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)));
        ws?.send(JSON.stringify({ audio: base64Audio, session_id: sessionId }));
        console.log("Audio sent to server.");
      }

      hasSound = false;
      stream.getTracks().forEach(t => t.stop());
    };

    mediaRecorder.start();
    statusEl.textContent = "🎙️ Listening...";
    setTimeout(() => mediaRecorder.stop(), 5000);

  } catch (err) {
    console.error("Mic error:", err);
    statusEl.textContent = "Microphone error!";
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
      statusEl.textContent = "Listening...";
      animationInterval = setInterval(animateWave, 100);
      startRecording();
      return;
    }

    // Voice response from server
    if (data.audio) {
      clearInterval(animationInterval);
      botSpeaking.classList.add("active");

      const audioBlob = new Blob(
        [Uint8Array.from(atob(data.audio), c => c.charCodeAt(0))],
        { type: "audio/wav" }
      );
      botAudio.src = URL.createObjectURL(audioBlob);
      botAudio.play();

      botAudio.onended = () => {
        botSpeaking.classList.remove("active");
        statusEl.textContent = "Listening...";
        startRecording();
        animationInterval = setInterval(animateWave, 100);
      };
    }

    if (data.text) {
      console.log("Text response:", data.text);
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
