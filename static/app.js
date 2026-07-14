/* Talk2Breath — Breezy the Lung Buddy (frontend logic) */

const idGate = document.getElementById("idGate");
const idGateForm = document.getElementById("idGateForm");
const participantIdInput = document.getElementById("participantIdInput");
const idGateError = document.getElementById("idGateError");
const idGateSubmit = document.getElementById("idGateSubmit");
const appRoot = document.getElementById("appRoot");

let participantId = null;

/* ---------- Participant ID gate ---------- */
// Every session (including re-opening the browser) requires the ID again, on purpose:
// re-entering the same ID appends to that participant's existing transcript on the
// server, so an accidental close/crash never loses the research recording.
idGateForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = participantIdInput.value.trim();
  idGateError.classList.add("hidden");
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(id)) {
    idGateError.textContent = "Please use only letters, numbers, - or _ (1-64 characters).";
    idGateError.classList.remove("hidden");
    return;
  }
  idGateSubmit.disabled = true;
  idGateSubmit.textContent = "Starting…";
  try {
    const res = await fetch("/api/session/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ participant_id: id }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      idGateError.textContent = data.error || "Couldn't start the session. Please try again.";
      idGateError.classList.remove("hidden");
      return;
    }
    participantId = data.participant_id;
    idGate.classList.add("hidden");
    appRoot.classList.remove("hidden");
    startChat();
  } catch (e) {
    idGateError.textContent = "Couldn't reach Breezy. Please check your connection and try again.";
    idGateError.classList.remove("hidden");
  } finally {
    idGateSubmit.disabled = false;
    idGateSubmit.textContent = "Start Chatting 🌬️";
  }
});

const chat = document.getElementById("chat");
const composer = document.getElementById("composer");
const messageInput = document.getElementById("messageInput");
const imageInput = document.getElementById("imageInput");
const imgPreview = document.getElementById("imgPreview");
const previewImg = document.getElementById("previewImg");
const clearImgBtn = document.getElementById("clearImg");
const ttsToggle = document.getElementById("ttsToggle");
const micBtn = document.getElementById("micBtn");
const mascot = document.getElementById("mascot");
const chips = document.getElementById("chips");

let history = []; // {role, content}
let pendingImage = null;
let ttsOn = true;
let isBusy = false; // lock: only one message in flight at a time

function setBusy(state) {
  isBusy = state;
  document.getElementById("sendBtn").disabled = state;
  micBtn.disabled = state;
  micBtn.style.opacity = state ? 0.5 : 1;
}

/* ---------- Message rendering ---------- */
function addMessage(text, who, imageDataUrl) {
  const div = document.createElement("div");
  div.className = `msg ${who}`;
  if (imageDataUrl) {
    const img = document.createElement("img");
    img.src = imageDataUrl;
    div.appendChild(img);
  }
  if (text) div.appendChild(document.createTextNode(text));
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

// Add a generated picture into a bot bubble, with a gentle loading state.
function addBotImage(bubble, url) {
  const wrap = document.createElement("div");
  wrap.className = "bot-art loading";
  const img = document.createElement("img");
  img.alt = "A picture from Breezy";
  img.onload = () => wrap.classList.remove("loading");
  img.onerror = () => { wrap.remove(); };
  img.src = url;
  img.addEventListener("click", () => openLightbox(url));
  wrap.appendChild(img);
  bubble.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
}

function showTyping() {
  const t = document.createElement("div");
  t.className = "typing";
  t.id = "typing";
  t.innerHTML = "<span></span><span></span><span></span>";
  chat.appendChild(t);
  chat.scrollTop = chat.scrollHeight;
}
function hideTyping() {
  const t = document.getElementById("typing");
  if (t) t.remove();
}

/* ---------- Text to Speech ----------
   Breezy's voice is generated on the SERVER (Groq TTS) and played back with a plain
   <audio> element — that works identically on every tablet/browser, unlike the
   browser's built-in speechSynthesis, which is missing or broken on many Android
   tablets and kiosk/in-app browsers. If the server voice can't be reached (offline,
   rate-limited), we fall back to the browser's own speech engine when available, so
   voice degrades gracefully instead of just failing silently. */
let currentAudio = null;

function stopSpeaking() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  mascot.classList.remove("talking");
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}

function pickVoice() {
  const voices = window.speechSynthesis.getVoices();
  // Prefer a friendly English voice; many browsers have a female/child-ish default.
  const preferred = voices.find(v => /en(-|_)/i.test(v.lang) && /female|zira|samantha|google/i.test(v.name))
                 || voices.find(v => /^en/i.test(v.lang))
                 || voices[0];
  return preferred;
}

function speakWithBrowserFallback(clean) {
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(clean);
  const v = pickVoice();
  if (v) u.voice = v;
  u.rate = 0.95;   // a touch slower for kids
  u.pitch = 1.25;  // higher, friendlier pitch
  u.onstart = () => mascot.classList.add("talking");
  u.onend = () => mascot.classList.remove("talking");
  window.speechSynthesis.speak(u);
}
// Voices load async in some browsers
if ("speechSynthesis" in window) {
  window.speechSynthesis.onvoiceschanged = pickVoice;
}

async function speak(text) {
  if (!ttsOn) return;
  stopSpeaking();
  // Strip emojis so the voice doesn't read them awkwardly.
  const clean = text.replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "").trim();
  if (!clean) return;
  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: clean }),
    });
    if (!res.ok) throw new Error("tts failed");
    const data = await res.json();
    if (!data.audio_url) throw new Error("no audio");
    const audio = new Audio(data.audio_url);
    currentAudio = audio;
    audio.onplay = () => mascot.classList.add("talking");
    audio.onended = () => mascot.classList.remove("talking");
    audio.onerror = () => { mascot.classList.remove("talking"); speakWithBrowserFallback(clean); };
    await audio.play();
  } catch (e) {
    speakWithBrowserFallback(clean);
  }
}

ttsToggle.addEventListener("click", () => {
  ttsOn = !ttsOn;
  ttsToggle.classList.toggle("on", ttsOn);
  ttsToggle.classList.toggle("off", !ttsOn);
  ttsToggle.querySelector(".tts-icon").textContent = ttsOn ? "🔊" : "🔇";
  ttsToggle.querySelector(".tts-label").textContent = ttsOn ? "Voice On" : "Voice Off";
  if (!ttsOn) stopSpeaking();
});

/* ---------- Sending messages ---------- */
async function sendText(text) {
  if (isBusy || !text) return;      // ignore while a message is already sending
  setBusy(true);
  stopSpeaking();  // stop any current speech before new turn
  addMessage(text, "user");
  history.push({ role: "user", content: text });
  showTyping();
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history: history.slice(0, -1), participant_id: participantId }),
    });
    const data = await res.json();
    hideTyping();
    const reply = data.reply || data.error || "Oops! Let's try again. 🌬️";
    const bubble = addMessage(reply, "bot");
    if (data.image_url) addBotImage(bubble, data.image_url);
    if (data.reply) history.push({ role: "assistant", content: reply });
    speak(reply);
  } catch (e) {
    hideTyping();
    addMessage("Breezy lost the breeze for a second! Please try again. 🌬️", "bot");
  } finally {
    setBusy(false);
  }
}

async function sendImage(file, caption) {
  if (isBusy) return;
  setBusy(true);
  stopSpeaking();
  const dataUrl = await fileToDataUrl(file);
  addMessage(caption || "Look at this! 📷", "user", dataUrl);
  showTyping();
  try {
    const form = new FormData();
    form.append("image", file);
    form.append("message", caption || "What is in this picture?");
    form.append("participant_id", participantId || "");
    const res = await fetch("/api/chat-image", { method: "POST", body: form });
    const data = await res.json();
    hideTyping();
    const reply = data.reply || data.error || "Oops! Let's try again. 🖼️";
    const bubble = addMessage(reply, "bot");
    if (data.image_url) addBotImage(bubble, data.image_url);
    if (data.reply) {
      history.push({ role: "user", content: "[sent a picture] " + (caption || "") });
      history.push({ role: "assistant", content: reply });
    }
    speak(reply);
  } catch (e) {
    hideTyping();
    addMessage("Breezy couldn't peek at the picture. Try again! 🖼️", "bot");
  } finally {
    setBusy(false);
  }
}

function fileToDataUrl(file) {
  return new Promise((resolve) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.readAsDataURL(file);
  });
}

/* ---------- Composer submit ---------- */
composer.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = messageInput.value.trim();
  if (pendingImage) {
    sendImage(pendingImage, text);
    clearImage();
    messageInput.value = "";
    return;
  }
  if (!text) return;
  messageInput.value = "";
  sendText(text);
});

/* ---------- Suggestion chips ---------- */
chips.addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  sendText(chip.dataset.say);
});

/* ---------- Image upload ---------- */
imageInput.addEventListener("change", () => {
  const file = imageInput.files[0];
  if (!file) return;
  pendingImage = file;
  fileToDataUrl(file).then((url) => {
    previewImg.src = url;
    imgPreview.classList.remove("hidden");
  });
});
function clearImage() {
  pendingImage = null;
  imageInput.value = "";
  imgPreview.classList.add("hidden");
}
clearImgBtn.addEventListener("click", clearImage);

/* ---------- Voice messages: record audio -> Groq Whisper (works in all browsers) ---------- */
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

micBtn.addEventListener("click", async () => {
  if (isBusy) return;
  if (isRecording) { stopRecording(); return; }  // tap again to stop & send

  // The microphone only works on a secure (https) page — or on localhost.
  if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    addMessage(
      "To talk to me with your voice, this page needs a secure (https) connection. 🌬️ " +
      "It works on a computer, and on phones once the site is on https. For now, you can type to me! 😊",
      "bot"
    );
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());  // release the mic
      handleRecording();
    };
    stopSpeaking();  // stop Breezy talking while recording
    mediaRecorder.start();
    isRecording = true;
    micBtn.classList.add("listening");
  } catch (e) {
    addMessage("I couldn't reach the microphone. Please allow mic access and try again. 🎤", "bot");
  }
});

function stopRecording() {
  if (mediaRecorder && isRecording) {
    isRecording = false;
    micBtn.classList.remove("listening");
    try { mediaRecorder.stop(); } catch (e) {}
  }
}

async function handleRecording() {
  const type = (mediaRecorder && mediaRecorder.mimeType) || "audio/webm";
  const blob = new Blob(audioChunks, { type });
  if (!blob.size) return;

  let ext = "webm";
  if (type.includes("mp4") || type.includes("m4a")) ext = "mp4";
  else if (type.includes("ogg")) ext = "ogg";
  else if (type.includes("wav")) ext = "wav";

  const form = new FormData();
  form.append("audio", blob, "audio." + ext);

  const oldPlaceholder = messageInput.placeholder;
  messageInput.placeholder = "✍️ Turning your voice into words…";
  micBtn.disabled = true;
  try {
    const res = await fetch("/api/transcribe", { method: "POST", body: form });
    const data = await res.json();
    if (data.text) {
      // Put the words in the box so the child can check/fix them, then press send.
      messageInput.value = data.text;
      messageInput.focus();
    } else {
      addMessage(data.error || "I couldn't hear that clearly. Please try again! 🎤", "bot");
    }
  } catch (e) {
    addMessage("Voice isn't working right now — please type to me instead! 🎤", "bot");
  } finally {
    messageInput.placeholder = oldPlaceholder;
    micBtn.disabled = false;
  }
}

/* ---------- Tap a drawing to see it bigger ---------- */
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightboxImg");
const lightboxClose = document.getElementById("lightboxClose");

function openLightbox(url) {
  lightboxImg.src = url;
  lightbox.classList.remove("hidden");
}
function closeLightbox() {
  lightbox.classList.add("hidden");
  lightboxImg.src = "";
}
// Tap anywhere on the backdrop (or the ✖) to close.
lightbox.addEventListener("click", closeLightbox);
lightboxClose.addEventListener("click", closeLightbox);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeLightbox();
});

/* ---------- Welcome message ---------- */
// Runs once the participant ID has been accepted (see the idGateForm handler above),
// not on page load — the chat itself only starts after that gate is passed.
function startChat() {
  const hello = "Hi there! I'm Breezy, your lung buddy! I love clean air and healthy lungs. Ask me anything, or tap a bubble below to start! 🌬️😊";
  addMessage(hello, "bot");
  // Some browsers block auto-speech until the user interacts; that's fine.
  setTimeout(() => speak(hello), 400);
}
