/* Talk2Breath — Breezy the Lung Buddy (frontend logic) */

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

/* ---------- Text to Speech (Web Speech API, free) ---------- */
function pickVoice() {
  const voices = window.speechSynthesis.getVoices();
  // Prefer a friendly English voice; many browsers have a female/child-ish default.
  const preferred = voices.find(v => /en(-|_)/i.test(v.lang) && /female|zira|samantha|google/i.test(v.name))
                 || voices.find(v => /^en/i.test(v.lang))
                 || voices[0];
  return preferred;
}

function speak(text) {
  if (!ttsOn || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  // Strip emojis so the voice doesn't read them awkwardly.
  const clean = text.replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "").trim();
  if (!clean) return;
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

ttsToggle.addEventListener("click", () => {
  ttsOn = !ttsOn;
  ttsToggle.classList.toggle("on", ttsOn);
  ttsToggle.classList.toggle("off", !ttsOn);
  ttsToggle.querySelector(".tts-icon").textContent = ttsOn ? "🔊" : "🔇";
  ttsToggle.querySelector(".tts-label").textContent = ttsOn ? "Voice On" : "Voice Off";
  if (!ttsOn) window.speechSynthesis.cancel();
});

/* ---------- Sending messages ---------- */
async function sendText(text) {
  if (isBusy || !text) return;      // ignore while a message is already sending
  setBusy(true);
  window.speechSynthesis.cancel();  // stop any current speech before new turn
  addMessage(text, "user");
  history.push({ role: "user", content: text });
  showTyping();
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history: history.slice(0, -1) }),
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
  window.speechSynthesis.cancel();
  const dataUrl = await fileToDataUrl(file);
  addMessage(caption || "Look at this! 📷", "user", dataUrl);
  showTyping();
  try {
    const form = new FormData();
    form.append("image", file);
    form.append("message", caption || "What is in this picture?");
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

/* ---------- Speech to Text (mic, optional & free) ---------- */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let recog = null;
let isListening = false;

if (SR) {
  recog = new SR();
  recog.lang = "en-US";
  recog.continuous = false;      // one phrase at a time (prevents runaway loops)
  recog.interimResults = false;  // only final text
  recog.maxAlternatives = 1;

  recog.onresult = (ev) => {
    // Take only the LAST final result, once.
    const last = ev.results[ev.results.length - 1];
    if (!last || !last.isFinal) return;
    const said = (last[0].transcript || "").trim();
    stopListening();
    // Put the heard words in the box so the child can check/fix them
    // (voice recognition sometimes mishears, e.g. "vape" -> "wave") then press send.
    if (said) {
      messageInput.value = said;
      messageInput.focus();
    }
  };
  recog.onend = () => stopListening();
  recog.onerror = () => stopListening();

  micBtn.addEventListener("click", () => {
    if (isBusy) return;                 // don't listen while a reply is loading
    if (isListening) { stopListening(); return; }  // tap again to stop
    window.speechSynthesis.cancel();    // silence Breezy so the mic can't hear it
    startListening();
  });
} else {
  micBtn.style.display = "none"; // browser doesn't support it
}

function startListening() {
  if (!recog || isListening) return;
  try {
    recog.start();
    isListening = true;
    micBtn.classList.add("listening");
  } catch (e) {
    isListening = false;
    micBtn.classList.remove("listening");
  }
}
function stopListening() {
  if (!recog) return;
  isListening = false;
  micBtn.classList.remove("listening");
  try { recog.stop(); } catch (e) {}
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
window.addEventListener("load", () => {
  const hello = "Hi there! I'm Breezy, your lung buddy! I love clean air and healthy lungs. Ask me anything, or tap a bubble below to start! 🌬️😊";
  addMessage(hello, "bot");
  // Some browsers block auto-speech until the user interacts; that's fine.
  setTimeout(() => speak(hello), 400);
});
