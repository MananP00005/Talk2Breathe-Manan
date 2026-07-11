# 🌬️ Talk2Breath — AI Chatbot for Kids' Smoking Prevention

Meet **Breezy**, a friendly cartoon lung-buddy who teaches children (ages 3–15) why
healthy lungs are wonderful and why smoking/vaping is harmful — in a warm, playful,
age-aware way. Built for **Phase 1**: runs locally on your computer.

## ✨ Features
- 💬 Free, open chat with a kid-safe AI (powered by free Groq Llama models)
- 🔊 **Text-to-Speech** — Breezy reads answers out loud (browser Web Speech API, no cost)
- 🎤 **Talk with your voice** — optional speech-to-text mic button
- 📷 **Photo upload** — kids can send a picture and Breezy responds kindly
- 🧒 Playful, colorful, bubbly kid theme with an animated mascot
- 🛡️ Safety-first system prompt (gentle, age-aware, steers away from unsafe topics)

## 🧱 Tech Stack
- **Backend:** FastAPI (Python) — hides your API key, serves the app
- **Frontend:** single-page HTML + CSS + vanilla JS (fast, easy to theme)
- **AI:** Groq API — `llama-3.3-70b-versatile` (chat) + a Llama vision model (photos)
- **Voice:** Browser Web Speech API (free)

## 🚀 Run it locally (about 5 minutes)

1. **Get a free Groq API key** at https://console.groq.com/keys

2. **Install dependencies** (Python 3.10+):
   ```bash
   pip install -r requirements.txt
   ```

3. **Add your key:**
   ```bash
   cp .env.example .env
   ```
   Open `.env` and paste your key after `GROQ_API_KEY=`.

4. **Start the app:**
   ```bash
   uvicorn main:app --reload
   ```

5. Open **http://localhost:8000** 🎉

> Tip: Use **Chrome** for the best Text-to-Speech and microphone support.

## 📁 Project structure
```
Talk2Breath/
├── main.py            # FastAPI backend (chat + vision + serves frontend)
├── requirements.txt
├── .env.example       # copy to .env and add your Groq key
├── static/
│   ├── index.html     # the app UI
│   ├── style.css      # kid-friendly theme
│   └── app.js         # chat, TTS, mic, image upload logic
└── README.md
```

## 🔒 Safety notes
- Breezy never gives harmful instructions and steers gently back to health topics.
- If a child mentions distress or danger, Breezy encourages talking to a trusted grown-up.
- Never commit your `.env` file (it's already in `.gitignore`).

## 🗺️ Phase 2 (later)
- Dockerize and deploy to **Google Cloud (GCP)** — Cloud Run is a great fit.
- Optional upgrade to a higher-quality cloud TTS voice.
- Add simple parent/teacher settings and content logging.

---
Made with 💙 for healthy little lungs.
