const micBtn = document.getElementById("micBtn");
const statusEl = document.getElementById("status");
const botAudio = document.getElementById("botAudio");
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
let silenceInterval = null;
let currentStream = null;
let currentAudioContext = null;
let isProcessingQuery = false; // Flag to prevent overlapping queries

// Debug function to reset state (you can call this in console if stuck)
window.resetVoiceState = function() {
  console.log("Resetting voice state...");
  isProcessingQuery = false;
  
  // Clear any timeouts
  if (window.currentResponseTimeout) {
    clearTimeout(window.currentResponseTimeout);
    window.currentResponseTimeout = null;
  }
  if (window.waitingMessageTimeout) {
    clearTimeout(window.waitingMessageTimeout);
    window.waitingMessageTimeout = null;
  }
  if (window.offerNewQuestionTimeout) {
    clearTimeout(window.offerNewQuestionTimeout);
    window.offerNewQuestionTimeout = null;
  }
  
  // Force stop all recording activities
  forceStopRecording();
  
  statusEl.textContent = "🎙️ Ready to listen...";
  statusEl.className = "";
  
  // Force restart recording
  setTimeout(() => {
    startRecording();
    if (!animationInterval) {
      animationInterval = setInterval(animateWave, 100);
    }
  }, 500);
};

// Function to properly cleanup recording session
function cleanupRecordingSession() {
  console.log("Cleaning up recording session...");
  
  // Stop and cleanup media recorder
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    console.log("Stopping active media recorder");
    mediaRecorder.stop();
  }
  
  // Clear silence detection interval
  if (silenceInterval) {
    console.log("Clearing silence interval");
    clearInterval(silenceInterval);
    silenceInterval = null;
  }
  
  // Stop audio tracks from previous stream
  if (currentStream) {
    console.log("Stopping audio tracks from previous stream");
    currentStream.getTracks().forEach(track => track.stop());
    currentStream = null;
  }
  
  // Close audio context
  if (currentAudioContext && currentAudioContext.state !== 'closed') {
    console.log("Closing audio context");
    currentAudioContext.close();
    currentAudioContext = null;
  }
  
  // Reset audio chunks
  audioChunks = [];
  
  // Hide silence progress
  if (silenceProgress) {
    silenceProgress.style.display = "none";
  }
}

// Function to force stop all recording and microphone activities
function forceStopRecording() {
  console.log("Force stopping all recording activities...");
  
  // Stop media recorder immediately
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    console.log("Force stopping media recorder");
    try {
      mediaRecorder.stop();
    } catch (e) {
      console.log("Error stopping media recorder:", e);
    }
    mediaRecorder = null;
  }
  
  // Force stop silence detection
  if (silenceInterval) {
    console.log("Force stopping silence detection");
    clearInterval(silenceInterval);
    silenceInterval = null;
  }
  
  // Force stop microphone stream
  if (currentStream) {
    console.log("Force stopping microphone stream");
    currentStream.getTracks().forEach(track => {
      try {
        track.stop();
        console.log("Stopped track:", track.label || 'audio');
      } catch (e) {
        console.log("Error stopping track:", e);
      }
    });
    currentStream = null;
  }
  
  // Force close audio context
  if (currentAudioContext && currentAudioContext.state !== 'closed') {
    console.log("Force closing audio context");
    try {
      currentAudioContext.close();
    } catch (e) {
      console.log("Error closing audio context:", e);
    }
    currentAudioContext = null;
  }
  
  // Clear animation
  if (animationInterval) {
    clearInterval(animationInterval);
    animationInterval = null;
  }
  
  // Reset all flags
  isProcessingQuery = false;
  audioChunks = [];
  
  // Hide progress indicators
  if (silenceProgress) {
    silenceProgress.style.display = "none";
  }
  
  // Remove recording visual indicators
  micBtn.classList.remove("recording");
  statusEl.className = "";
  
  console.log("All recording activities stopped");
}

// Connection monitoring: Check WebSocket status periodically
setInterval(() => {
  if (ws && ws.readyState !== WebSocket.OPEN && ws.readyState !== WebSocket.CONNECTING) {
    console.log("WebSocket connection lost detected, force stopping all activities...");
    
    // Force stop all recording activities immediately
    forceStopRecording();
    
    // Clear all timeouts
    if (window.currentResponseTimeout) {
      clearTimeout(window.currentResponseTimeout);
      window.currentResponseTimeout = null;
    }
    if (window.waitingMessageTimeout) {
      clearTimeout(window.waitingMessageTimeout);
      window.waitingMessageTimeout = null;
    }
    if (window.offerNewQuestionTimeout) {
      clearTimeout(window.offerNewQuestionTimeout);
      window.offerNewQuestionTimeout = null;
    }
    
    // Update status if not already showing connection error
    if (!statusEl.textContent.includes("Connection") && !statusEl.textContent.includes("error") && !statusEl.textContent.includes("lost")) {
      statusEl.textContent = "🔌 Connection lost! Microphone stopped. Click to reconnect.";
      statusEl.className = "disconnected";
      micBtn.disabled = false; // Enable button for reconnection
    }
  }
}, 2000); // Check every 2 seconds

// Enhanced failsafe: Auto-reset if stuck in processing for too long
setInterval(() => {
  if (isProcessingQuery) {
    const timeDiff = Date.now() - (window.lastProcessingTime || 0);
    
    // Reset if stuck in "Processing your question..." for more than 10 seconds
    if (statusEl.textContent === "Processing your question..." && timeDiff > 10000) {
      console.log("Failsafe: Resetting stuck 'Processing your question...' state");
      window.resetVoiceState();
    }
    
    // Reset if stuck in "🤖 Thinking..." for more than 30 seconds
    else if (statusEl.textContent === "🤖 Thinking..." && timeDiff > 30000) {
      console.log("Failsafe: Resetting stuck 'Thinking...' state");
      window.resetVoiceState();
    }
    
    // Reset if stuck in any processing state for more than 45 seconds
    else if (timeDiff > 45000) {
      console.log("Failsafe: Resetting any stuck processing state after 45 seconds");
      window.resetVoiceState();
    }
  }
}, 3000); // Check every 3 seconds

// Create waveform bars
// for (let i = 0; i < 20; i++) {
//   const bar = document.createElement("div");
//   bar.classList.add("bar");
//   waveform.appendChild(bar);
// }

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
    return `ws://${host}:8001/ws/voice`;
  } else {
    return `wss://mickie-springy-unaccusingly.ngrok-free.dev/ws/voice`;
  }
}

// ----------------------
// Recording Function with Silence Detection
// ----------------------
async function startRecording() {
  console.log("startRecording called - isProcessingQuery:", isProcessingQuery);
  
  // First, clean up any previous recording session
  cleanupRecordingSession();
  
  // Clear any lingering timeouts
  if (window.currentResponseTimeout) {
    clearTimeout(window.currentResponseTimeout);
    window.currentResponseTimeout = null;
  }
  if (window.waitingMessageTimeout) {
    clearTimeout(window.waitingMessageTimeout);
    window.waitingMessageTimeout = null;
  }
  if (window.offerNewQuestionTimeout) {
    clearTimeout(window.offerNewQuestionTimeout);
    window.offerNewQuestionTimeout = null;
  }
  
  // Prevent new recording if already processing a query
  if (isProcessingQuery) {
    console.log("Query already in progress, ignoring startRecording call");
    statusEl.textContent = "⏳ Please wait for current response...";
    
    // But if we've been waiting too long, force reset
    const timeDiff = Date.now() - (window.lastProcessingTime || 0);
    if (timeDiff > 8000) { // Force reset after 8 seconds
      console.log("Force resetting stuck processing flag in startRecording");
      isProcessingQuery = false;
    } else {
      return;
    }
  }

  try {
    console.log("Getting new audio stream...");
    const stream = await navigator.mediaDevices.getUserMedia({ 
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        channelCount: 1,
        sampleRate: 44100
      } 
    });
    
    // Store current stream for cleanup
    currentStream = stream;
    
    console.log("Creating new audio context...");
    const audioContext = new AudioContext();
    currentAudioContext = audioContext;
    
    const source = audioContext.createMediaStreamSource(stream);

    // ✅ Create analyser for advanced voice detection
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 4096; // Higher resolution for better voice detection
    analyser.smoothingTimeConstant = 0.8; // Smooth out noise spikes
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Float32Array(bufferLength);
    const frequencyData = new Uint8Array(bufferLength);
    source.connect(analyser);

    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    let hasSound = false;
    let silenceCount = 0;
    let isRecording = true;
    let silenceThreshold = 15; // 3 seconds (15 * 200ms checks) - optimized for close voice
    let lastSoundTime = Date.now();
    let voiceConfidenceCount = 0; // Track consecutive voice detections
    let firstRecordingAttempt = true; // Flag to help with first recording

    function detectSilence() {
      if (!isRecording) return;
      
      // Get both time domain and frequency domain data
      analyser.getFloatTimeDomainData(dataArray);
      analyser.getByteFrequencyData(frequencyData);
      
      // Calculate RMS for volume
      const rms = Math.sqrt(dataArray.reduce((sum, v) => sum + v * v, 0) / bufferLength);
      const db = 20 * Math.log10(rms + 1e-8);
      
      // Enhanced voice frequency analysis for close-distance detection
      const voiceFreqStart = Math.floor(300 * bufferLength / (audioContext.sampleRate / 2));
      const voiceFreqEnd = Math.floor(3400 * bufferLength / (audioContext.sampleRate / 2));
      const lowFreqEnd = Math.floor(85 * bufferLength / (audioContext.sampleRate / 2));
      const midFreqStart = Math.floor(800 * bufferLength / (audioContext.sampleRate / 2));
      const midFreqEnd = Math.floor(2000 * bufferLength / (audioContext.sampleRate / 2));
      
      // Calculate energy in different frequency ranges for close voice detection
      let voiceEnergy = 0;
      let totalEnergy = 0;
      let lowFreqEnergy = 0;
      let midFreqEnergy = 0; // Key range for close conversational voice
      let backgroundNoise = 0;
      
      for (let i = 0; i < bufferLength; i++) {
        const energy = frequencyData[i];
        totalEnergy += energy;
        
        if (i >= voiceFreqStart && i <= voiceFreqEnd) {
          voiceEnergy += energy;
        }
        if (i <= lowFreqEnd) {
          lowFreqEnergy += energy;
        }
        if (i >= midFreqStart && i <= midFreqEnd) {
          midFreqEnergy += energy; // Critical for close voice detection
        }
        if (i < Math.floor(200 * bufferLength / (audioContext.sampleRate / 2))) {
          backgroundNoise += energy;
        }
      }
      
      // Enhanced voice detection criteria - optimized for close-distance conversational voice (60-70 dB)
      const voiceRatio = totalEnergy > 0 ? voiceEnergy / totalEnergy : 0;
      const midFreqRatio = totalEnergy > 0 ? midFreqEnergy / totalEnergy : 0;
      const signalToNoiseRatio = backgroundNoise > 0 ? voiceEnergy / backgroundNoise : 0;
      
      // Multi-criteria detection for close microphone usage:
      // 1. Strong signal (-25 dB minimum for close voice)
      // 2. Good voice frequency presence (>20%)
      // 3. Strong mid-frequency content (>15% for clear speech)
      // 4. Low background noise ratio (<30%)
      // 5. Good signal-to-noise ratio (>2.0 for close voice)
      const isLikelyVoice = 
        db > -25 &&                           // Close-distance voice threshold
        voiceRatio > 0.2 &&                   // Strong voice frequency presence
        midFreqRatio > 0.15 &&                // Clear speech characteristics
        lowFreqEnergy < totalEnergy * 0.3 &&  // Limited low-frequency interference
        signalToNoiseRatio > 2.0;             // Good signal quality for close voice
      
      // Fallback detection for first question (less strict criteria)
      const isBasicVoice = 
        db > -40 &&                           // Even more lenient dB threshold
        (voiceRatio > 0.05 || totalEnergy > 50); // Very low requirements
      
      // Emergency fallback - detect any reasonable audio activity (especially for first recording)
      const hasAudioActivity = 
        db > -50 && totalEnergy > 20;         // Minimal requirements for any audio
      
      // For first recording, be extra lenient
      const firstRecordingFallback = firstRecordingAttempt && (db > -60 || totalEnergy > 10);
      
      // Sound detected (enhanced close-distance voice detection)
      if (isLikelyVoice || (!hasSound && isBasicVoice) || (!hasSound && hasAudioActivity) || firstRecordingFallback) {
        voiceConfidenceCount++;
        console.log(`Voice detection: dB=${db.toFixed(1)}, voiceRatio=${voiceRatio.toFixed(2)}, totalEnergy=${totalEnergy.toFixed(1)}, method=${isLikelyVoice ? 'strict' : (isBasicVoice ? 'basic' : (hasAudioActivity ? 'emergency' : 'first-recording'))}`);
        
        // For close-distance voice, require fewer confirmations (more responsive)
        if (voiceConfidenceCount >= 1) { // Reduced from 2 to 1 for close voice responsiveness
          hasSound = true;
          silenceCount = 0;
          lastSoundTime = Date.now();
          firstRecordingAttempt = false; // No longer the first attempt
          
          // Show different status based on detection method
          if (isLikelyVoice && db > -15) {
            statusEl.textContent = "🎙️ Listening... (Clear close voice)";
          } else if (isLikelyVoice) {
            statusEl.textContent = "🎙️ Listening... (Voice detected)";
          } else if (isBasicVoice) {
            statusEl.textContent = "🎙️ Listening... (Audio detected)";
          } else {
            statusEl.textContent = "🎙️ Listening... (Sound detected)";
          }
          statusEl.className = "speaking";
          if (silenceProgress) silenceProgress.style.display = "none";
        }
      } else {
        // Gradually reduce confidence for more stable detection
        if (voiceConfidenceCount > 0) {
          voiceConfidenceCount = Math.max(0, voiceConfidenceCount - 0.5); // Slower decay for stability
        }
        
        // Only count as silence if confidence is very low
        if (voiceConfidenceCount < 0.5) {
          silenceCount++;
        }
        
        if (hasSound && silenceCount >= silenceThreshold) {
          // User has spoken and now been silent for 3 seconds
          console.log("3 seconds of silence detected after speech - sending audio");
          console.log("MediaRecorder state before stop:", mediaRecorder.state);
          isProcessingQuery = true; // Block new recordings
          window.lastProcessingTime = Date.now(); // Track when processing started
          isRecording = false;
          statusEl.textContent = "Processing your question...";
          statusEl.className = "processing";
          silenceProgress.style.display = "none";
          console.log("Set status to 'Processing your question...', about to stop mediaRecorder");
          
          // Clear the silence interval immediately
          if (silenceInterval) {
            console.log("Clearing silence interval during processing");
            clearInterval(silenceInterval);
            silenceInterval = null;
          }
          
          // Add timeout in case onstop doesn't fire
          setTimeout(() => {
            if (statusEl.textContent === "Processing your question...") {
              console.log("Timeout: onstop didn't fire, manually processing audio");
              processAudioManually();
            }
          }, 3000);
          
          mediaRecorder.stop();
        } else if (silenceCount > 0 && hasSound) {
          // Show countdown during silence
          const remainingTime = Math.max(0, silenceThreshold - silenceCount);
          const secondsLeft = Math.ceil(remainingTime * 0.2);
          const progressPercent = ((silenceThreshold - remainingTime) / silenceThreshold) * 100;
          
          statusEl.textContent = `🔇 Waiting for silence...`;
          statusEl.className = "waiting";
          if (silenceProgress) {
            silenceProgress.style.display = "block";
            if (progressFill) progressFill.style.width = `${progressPercent}%`;
            if (progressText) progressText.textContent = `${secondsLeft}s remaining`;
          }
        }
      }
      
      // Maximum recording time: 30 seconds
      if (Date.now() - lastSoundTime > 30000) {
        console.log("Maximum recording time reached");
        isRecording = false;
        if (silenceInterval) {
          console.log("Clearing silence interval due to timeout");
          clearInterval(silenceInterval);
          silenceInterval = null;
        }
        mediaRecorder.stop();
      }
    }

    // Start silence detection with a clean interval
    console.log("Starting new silence detection interval...");
    silenceInterval = setInterval(detectSilence, 200); // Check every 200ms

    // Function to process audio manually if onstop doesn't fire
    async function processAudioManually() {
      console.log("Processing audio manually");
      
      // Clear silence interval
      if (silenceInterval) {
        clearInterval(silenceInterval);
        silenceInterval = null;
      }
      isRecording = false;
      
      const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
      console.log("Manual processing - Audio blob size:", audioBlob.size, "hasSound:", hasSound);
      
      // Very lenient check for audio blobs - allow very small recordings for first questions
      if (!hasSound || audioBlob.size < 500) {
        console.log(`No meaningful audio detected in manual processing - hasSound: ${hasSound}, size: ${audioBlob.size}`);
        // For very first recording, be extra lenient
        if (audioBlob.size >= 100) {
          console.log("Attempting to send small audio blob anyway (first recording fallback)");
          await sendAudioToServer(audioBlob);
          return;
        }
        statusEl.textContent = "No speech detected. Try again...";
        statusEl.className = "";
        isProcessingQuery = false;
        
        // Use cleanup function instead of manual cleanup
        cleanupRecordingSession();
        
        setTimeout(() => {
          statusEl.textContent = "🎙️ Listening...";
          startRecording();
        }, 2000);
      } else {
        await sendAudioToServer(audioBlob);
        // Cleanup will be done after response or timeout
      }
    }

    // Function to send audio to server
    async function sendAudioToServer(audioBlob) {
      console.log("sendAudioToServer called - isProcessingQuery:", isProcessingQuery);
      
      const arrayBuffer = await audioBlob.arrayBuffer();
      const base64Audio = btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)));
      
      if (ws && ws.readyState === WebSocket.OPEN) {
        console.log("WebSocket is ready, sending audio...");
        ws.send(JSON.stringify({ audio: base64Audio, session_id: sessionId }));
        console.log("Audio sent to server for processing");
        statusEl.textContent = "🤖 Thinking...";
        statusEl.className = "processing";
        
        // Clear any previous timeouts before setting new ones
        if (window.currentResponseTimeout) {
          clearTimeout(window.currentResponseTimeout);
        }
        if (window.waitingMessageTimeout) {
          clearTimeout(window.waitingMessageTimeout);
        }
        
        // First timeout - show waiting message after 8 seconds
        const waitingTimeout = setTimeout(() => {
          if (isProcessingQuery && statusEl.textContent === "🤖 Thinking...") {
            statusEl.textContent = "⏳ Please wait, response is taking longer than usual...";
            statusEl.className = "waiting";
            console.log("Showing extended wait message after 8 seconds");
          }
        }, 8000);
        
        // Second timeout - offer to ask another question after 15 seconds
        const offerNewQuestionTimeout = setTimeout(() => {
          if (isProcessingQuery) {
            statusEl.textContent = "⏳ Still processing... You can ask another question if needed.";
            statusEl.className = "waiting";
            console.log("Offering new question option after 15 seconds");
            // Allow new questions by resetting the flag after showing the message
            setTimeout(() => {
              if (isProcessingQuery && statusEl.textContent.includes("You can ask another question")) {
                isProcessingQuery = false;
                statusEl.textContent = "🎙️ Ready for your next question...";
                statusEl.className = "";
                startRecording();
                animationInterval = setInterval(animateWave, 100);
                console.log("Allowing new question after extended wait");
              }
            }, 3000);
          }
        }, 15000);
        
        // Final timeout - reset everything if no response in 25 seconds
        const finalTimeout = setTimeout(() => {
          console.log("No response from server in 25 seconds, resetting flag");
          if (isProcessingQuery) {
            isProcessingQuery = false;
            statusEl.textContent = "Server took too long. Please ask your question again.";
            statusEl.className = "";
            setTimeout(() => {
              statusEl.textContent = "🎙️ Listening...";
              startRecording();
              animationInterval = setInterval(animateWave, 100);
            }, 3000);
          }
        }, 25000);
        
        // Store timeouts so they can be cleared when response arrives
        window.waitingMessageTimeout = waitingTimeout;
        window.offerNewQuestionTimeout = offerNewQuestionTimeout;
        window.currentResponseTimeout = finalTimeout;
        
      } else {
        console.log("WebSocket not connected, readyState:", ws ? ws.readyState : "ws is null");
        
        // Stop all recording activities when connection is lost
        cleanupRecordingSession();
        
        // Clear animation interval
        if (animationInterval) {
          clearInterval(animationInterval);
          animationInterval = null;
        }
        
        statusEl.textContent = "🔌 Connection lost! Click mic to c.";
        statusEl.className = "disconnected";
        micBtn.classList.remove("recording");
        isProcessingQuery = false;
      }
    }

    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);

    mediaRecorder.onstop = async () => {
      console.log("MediaRecorder.onstop triggered");
      
      // Clear silence interval
      if (silenceInterval) {
        clearInterval(silenceInterval);
        silenceInterval = null;
      }
      isRecording = false;
      
      const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
      console.log("Audio blob size:", audioBlob.size, "hasSound:", hasSound);

      // Very lenient check for audio blobs - allow very small recordings for first questions
      if (!hasSound || audioBlob.size < 500) {
        console.log(`No meaningful audio detected - hasSound: ${hasSound}, size: ${audioBlob.size}`);
        // For very first recording, be extra lenient
        if (audioBlob.size >= 100) {
          console.log("Attempting to send small audio blob anyway (first recording fallback)");
          await sendAudioToServer(audioBlob);
          return;
        }
        statusEl.textContent = "No speech detected. Try again...";
        statusEl.className = "";
        isProcessingQuery = false;
        
        // Use cleanup function
        cleanupRecordingSession();
        
        setTimeout(() => {
          statusEl.textContent = "🎙️ Listening...";
          startRecording();
        }, 2000);
      } else {
        await sendAudioToServer(audioBlob);
        // Cleanup will be done after response or timeout
      }
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
  // Check if already connected or connecting
  if (ws && ws.readyState === WebSocket.OPEN) {
    console.warn("WebSocket already open");
    return;
  }
  
  // If currently connecting, don't start another connection
  if (ws && ws.readyState === WebSocket.CONNECTING) {
    console.log("WebSocket already connecting");
    return;
  }
  
  // Clean up any previous connection/recording state
  if (ws && ws.readyState === WebSocket.CLOSED) {
    console.log("Cleaning up previous closed WebSocket");
    cleanupRecordingSession();
  }

  micBtn.disabled = true;
  micBtn.classList.add("recording");
  statusEl.textContent = "🔄 Connecting...";
  statusEl.className = "connecting";

  try {
    ws = new WebSocket(getWsUrl());

    ws.onopen = () => {
      console.log("WS Connected.");
      statusEl.textContent = "⏳ Waiting for session...";
      statusEl.className = "connecting";
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
      console.log("Received bot response, clearing processing flag and timeout");
      
      // Clear all response timeouts since we got a response
      if (window.currentResponseTimeout) {
        clearTimeout(window.currentResponseTimeout);
        window.currentResponseTimeout = null;
      }
      if (window.waitingMessageTimeout) {
        clearTimeout(window.waitingMessageTimeout);
        window.waitingMessageTimeout = null;
      }
      if (window.offerNewQuestionTimeout) {
        clearTimeout(window.offerNewQuestionTimeout);
        window.offerNewQuestionTimeout = null;
      }
      
      isProcessingQuery = false; // Clear immediately when response received
      clearInterval(animationInterval);
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
        console.log("Bot audio ended, resetting flags and restarting recording");
        statusEl.textContent = "🎙️ Listening... (Ask another question)";
        statusEl.className = "";
        
        // Force clear processing flag
        isProcessingQuery = false;
        
        // Clear all timeouts
        if (window.currentResponseTimeout) {
          clearTimeout(window.currentResponseTimeout);
          window.currentResponseTimeout = null;
        }
        if (window.waitingMessageTimeout) {
          clearTimeout(window.waitingMessageTimeout);
          window.waitingMessageTimeout = null;
        }
        if (window.offerNewQuestionTimeout) {
          clearTimeout(window.offerNewQuestionTimeout);
          window.offerNewQuestionTimeout = null;
        }
        
        // Remove text after speaking
        setTimeout(() => {
          if (textDiv.parentNode) {
            textDiv.parentNode.removeChild(textDiv);
          }
        }, 3000);
        
        // Start listening again with delay to ensure clean state
        setTimeout(() => {
          console.log("Restarting recording after bot response");
          startRecording();
          animationInterval = setInterval(animateWave, 100);
        }, 1000);
      };

      botAudio.onerror = () => {
        console.log("Bot audio error, resetting flags and restarting recording");
        statusEl.textContent = "🎙️ Audio playback error. Listening again...";
        statusEl.className = "";
        
        // Force clear processing flag
        isProcessingQuery = false;
        
        // Clear all timeouts
        if (window.currentResponseTimeout) {
          clearTimeout(window.currentResponseTimeout);
          window.currentResponseTimeout = null;
        }
        if (window.waitingMessageTimeout) {
          clearTimeout(window.waitingMessageTimeout);
          window.waitingMessageTimeout = null;
        }
        if (window.offerNewQuestionTimeout) {
          clearTimeout(window.offerNewQuestionTimeout);
          window.offerNewQuestionTimeout = null;
        }
        
        // Start listening again with delay
        setTimeout(() => {
          console.log("Restarting recording after audio error");
          startRecording();
          animationInterval = setInterval(animateWave, 100);
        }, 1000);
      };
    }

    // Text-only response (fallback)
    if (data.bot_text && !data.audio) {
      console.log("Received text-only response, clearing processing flag and timeout");
      
      // Clear all response timeouts since we got a response
      if (window.currentResponseTimeout) {
        clearTimeout(window.currentResponseTimeout);
        window.currentResponseTimeout = null;
      }
      if (window.waitingMessageTimeout) {
        clearTimeout(window.waitingMessageTimeout);
        window.waitingMessageTimeout = null;
      }
      if (window.offerNewQuestionTimeout) {
        clearTimeout(window.offerNewQuestionTimeout);
        window.offerNewQuestionTimeout = null;
      }
      
      isProcessingQuery = false; // Clear flag
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
    
    // Clear all pending response timeouts
    if (window.currentResponseTimeout) {
      clearTimeout(window.currentResponseTimeout);
      window.currentResponseTimeout = null;
    }
    if (window.waitingMessageTimeout) {
      clearTimeout(window.waitingMessageTimeout);
      window.waitingMessageTimeout = null;
    }
    if (window.offerNewQuestionTimeout) {
      clearTimeout(window.offerNewQuestionTimeout);
      window.offerNewQuestionTimeout = null;
    }
    
    // Force stop all recording activities immediately
    console.log("Connection error - force stopping all recording activities");
    forceStopRecording();
    
    statusEl.textContent = "❌ Connection error! Microphone stopped.";
    statusEl.className = "error";
    micBtn.disabled = false;
    isProcessingQuery = false; // Clear flag on error
  };

  ws.onclose = () => {
    console.log("WS Closed.");
    
    // Clear any pending response timeouts
    if (window.currentResponseTimeout) {
      clearTimeout(window.currentResponseTimeout);
      window.currentResponseTimeout = null;
    }
    if (window.waitingMessageTimeout) {
      clearTimeout(window.waitingMessageTimeout);
      window.waitingMessageTimeout = null;
    }
    if (window.offerNewQuestionTimeout) {
      clearTimeout(window.offerNewQuestionTimeout);
      window.offerNewQuestionTimeout = null;
    }
    
    // Stop microphone and silence detection completely
    console.log("Connection closed - force stopping all recording activities");
    forceStopRecording();
    
    statusEl.textContent = "🔌 Connection lost! Click to mic.";
    statusEl.className = "disconnected";
    micBtn.disabled = false;
    isProcessingQuery = false; // Clear flag on close
  };

  } catch (error) {
    console.error("Failed to create WebSocket connection:", error);
    statusEl.textContent = "❌ Failed to connect! Check your internet connection.";
    statusEl.className = "error";
    micBtn.disabled = false;
    micBtn.classList.remove("recording");
  }
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
  isProcessingQuery = false; // Clear flag when manually stopped
};
