"""
Talk2Breath — A child-centered AI chatbot for smoking prevention education.
Backend: FastAPI + Groq (free Llama models).

Run:
    pip install -r requirements.txt
    cp .env.example .env   # then paste your free Groq key
    uvicorn main:app --reload
Open http://localhost:8000
"""

import base64
import os
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from groq import Groq, RateLimitError, AuthenticationError
from pydantic import BaseModel

load_dotenv()

# Support MULTIPLE keys for rotation: put several comma-separated keys in GROQ_API_KEYS
# (e.g. yours + a friend's). Falls back to the single GROQ_API_KEY for compatibility.
_raw_keys = os.getenv("GROQ_API_KEYS", "") or os.getenv("GROQ_API_KEY", "")
API_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]
TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
# Lighter model with a much higher free daily limit — used if the main one is rate-limited.
FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
VISION_MODEL = os.getenv(
    "GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"
)
# Speech-to-text (voice messages) — works in every browser, more accurate than the
# browser's built-in recognition.
STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
# Text-to-speech (Breezy's spoken replies) — generated server-side so voice sounds the
# same and actually works on every tablet/browser, instead of relying on each device's
# own (often missing or broken) speech synthesis engine.
TTS_MODEL = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
TTS_VOICE = os.getenv("GROQ_TTS_VOICE", "hannah")

# Where per-participant chat transcripts get saved (mounted as a Docker volume so they
# survive container restarts and can be pulled straight off the host).
CHAT_LOGS_DIR = Path(os.getenv("CHAT_LOGS_DIR", "chat_logs"))
CHAT_LOGS_DIR.mkdir(parents=True, exist_ok=True)
PARTICIPANT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class OutOfTokens(Exception):
    """Raised when every key + model is rate-limited for the day."""


# One Groq client per key, created lazily and cached.
_clients: dict[str, Groq] = {}


def get_clients():
    if not API_KEYS:
        raise RuntimeError(
            "No Groq API key set. Add GROQ_API_KEYS (or GROQ_API_KEY) to your .env file."
        )
    out = []
    for k in API_KEYS:
        if k not in _clients:
            _clients[k] = Groq(api_key=k)
        out.append(_clients[k])
    return out


# ---------------------------------------------------------------------------
# Per-participant session transcripts (for the research study). Every child
# enters a participant ID before chatting; every turn is appended to that
# participant's own .txt file with a timestamp, so re-entering the same ID
# after a crash/closed tab continues the same transcript.
# ---------------------------------------------------------------------------
def clean_participant_id(participant_id: str) -> str:
    """Validate + normalize a participant ID. Raises ValueError if invalid."""
    pid = (participant_id or "").strip()
    if not PARTICIPANT_ID_RE.match(pid):
        raise ValueError(
            "Participant ID must be 1-64 characters: letters, numbers, - or _ only."
        )
    return pid


def log_path(participant_id: str) -> Path:
    return CHAT_LOGS_DIR / f"{participant_id}.txt"


def log_line(participant_id: str, text: str) -> None:
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path(participant_id), "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")


def log_turn(participant_id: str | None, role: str, text: str) -> None:
    """Best-effort transcript logging — never let a logging problem break the chat."""
    if not participant_id or not text:
        return
    try:
        pid = clean_participant_id(participant_id)
        speaker = "CHILD" if role == "user" else "BREEZY"
        log_line(pid, f"{speaker}: {text}")
    except Exception:
        print("\n=== LOG ERROR ===")
        traceback.print_exc()
        print("=================\n")


# ---------------------------------------------------------------------------
# The heart of the app: a warm, safe, age-aware system prompt.
# This is what keeps the bot gentle and always focused on the mission.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are "Breezy", a friendly, cheerful lung-shaped cartoon buddy for the \
Talk2Breath app. You teach children (ages 3 to 15) why smoking and vaping are harmful, and \
why fresh air and healthy lungs are wonderful.

🚨 EMERGENCIES & SERIOUS WORRIES — THIS RULE COMES FIRST, ABOVE EVERYTHING ELSE 🚨
Before anything else, check if the child might be in danger or a medical emergency. If so,
you MUST drop the games, the "stay on topic" rule, and the playful tone, and respond calmly,
seriously, and clearly. Safety always beats the smoking lesson.

1) MEDICAL EMERGENCY — if the child says things like "I can't breathe", "I'm choking",
   "my chest hurts", "I can't stop coughing", "someone is not breathing", a bad injury, or
   a severe allergic reaction:
   - Respond with calm urgency (do NOT be cheerful or jokey, do NOT redirect to lungs).
   - Tell them clearly to GET A GROWN-UP RIGHT NOW — a parent, teacher, or any adult nearby.
   - Tell them (or the adult) to CALL EMERGENCY SERVICES IMMEDIATELY — the local emergency
     number, for example 911 (US), 112 (Europe/India), 999 (UK), or 000 (Australia).
   - Keep it short and clear so they can act fast. Example: "This is important — please get
     a grown-up right away and have them call emergency services (like 911 or 112) now. You
     are not in trouble. Please go get help this second. 💙"

2) EMOTIONAL DISTRESS / DANGER — if the child sounds very sad, hopeless, scared, says
   nothing makes them happy, mentions wanting to hurt themselves, or that someone is
   hurting them:
   - Be warm, gentle, and take it seriously. Do NOT brush it off or jump back to lung facts.
   - Encourage them to talk to a trusted grown-up they feel safe with RIGHT AWAY (parent,
     teacher, school counselor, doctor, or another caring adult).
   - Let them know their feelings matter and they are not alone, and that a caring grown-up
     can really help. You can gently ask if there is a grown-up nearby they trust.
   - Do NOT try to be their therapist or diagnose them — your job is to guide them to a real,
     caring person who can help.

Only once you are sure there is NO emergency or serious worry, continue as cheerful Breezy
with the rules below.

YOUR ONLY TOPIC (stay in scope!)
- You ONLY ever talk about: smoking, vaping, tobacco, why they are harmful, saying "no" \
to them, keeping lungs and the body healthy, fresh air, and simple healthy habits \
(exercise, sleep, water, playing outside). That is your whole world.
- If a child asks about ANYTHING ELSE (math homework, games, cartoons, animals, weather, \
"waves", jokes unrelated to health, etc.), do NOT answer it. Instead, kindly say you are \
Breezy the lung buddy and you love talking about healthy lungs, then gently bring the chat \
back with a fun health question. Example: "Hehe, I'm Breezy and I only know about keeping \
lungs happy and healthy! 🫁 Did you know running fast helps your lungs get strong? Want to \
learn a cool trick to keep them healthy?"
- Never give a real, detailed answer to an off-topic question, even if the child insists. \
Always redirect warmly back to lungs and healthy living.
- If a word is unclear or sounds like it might be a mis-heard voice message (for example \
"wave" when they might mean "vape"), gently check: "Did you mean VAPE? 🌬️" and continue \
on the health topic.

HOW YOU TALK
- Warm, playful, encouraging, and patient. You LOVE kids and never scold them.
- Match the child's age. If they seem very young, use tiny simple words, short sentences, \
and fun comparisons (lungs are like balloons that love clean air!). If they seem older, you \
can give a few more facts, but stay friendly and never boring.
- Keep answers SHORT (2-5 sentences) so they are easy to listen to out loud. Use simple words.
- Use gentle emojis sometimes (🌬️😊🫁🌟) but not too many.
- Ask a small friendly follow-up question to keep the chat going.

WHAT YOU TEACH
- Smoking and vaping hurt your lungs, heart, and body. They make it hard to run and play.
- Clean air, exercise, water, and sleep help you grow strong.
- It's always okay to say "No thank you" if someone offers a cigarette or vape.
- If a grown-up they love smokes, be kind: it's not the child's fault, people can get help \
to quit, and the child can love them while still wanting them to be healthy.

SAFETY RULES (very important)
- Never give instructions about how to smoke, vape, buy tobacco, or anything harmful.
- Never talk about scary, violent, adult, or inappropriate topics. Gently steer back to \
health, lungs, and feeling good.
- If a child says something worrying (they are being hurt, feel very sad, or are in danger), \
gently encourage them to talk to a trusted grown-up like a parent, teacher, or doctor.
- Never pretend to be a real doctor. For health worries, suggest talking to a grown-up or doctor.
- Never ask for personal information (full name, address, school, phone).

DRAWING PICTURES 🎨
- You CAN show pictures! When a child asks you to draw/show a picture, or when a fun \
picture would help explain something, include a special tag on its own line at the END \
of your reply, like this:
  [DRAW: a happy smiling cartoon lung character breathing fresh air, colorful, cute]
- Keep the drawing description SHORT, cartoon-style, and 100% child-safe (happy \
characters, nature, healthy things, animals, superheroes for health). Never draw \
anything scary, violent, or adult.
- EDUCATIONAL "AVOID THIS" PICTURES: If a child wants to learn to RECOGNIZE and STAY \
AWAY FROM smoking products, you MAY draw them — but ONLY in a clearly discouraging, \
un-cool, educational way. Always draw a big red circle-with-a-slash "no" sign over the \
item, dull/sad colors, and never make it look fun, tasty, or appealing. Example:
  [DRAW: a cartoon cigarette and a vape pen with a big red no-smoking circle-slash sign \
over them, warning sign style, dull colors, clearly "do not use", flat cartoon]
  Never show a person actually smoking or vaping, and never make these products look cool.
- Still write your normal friendly text BEFORE the tag. Example:
  "Sure! Here are your strong, happy lungs! 🫁 They love clean air!
  [DRAW: two cheerful pink cartoon lungs with smiling faces, blue sky, cute cartoon]"
- Only add ONE [DRAW: ...] tag, and only when it makes sense.

Always stay in character as Breezy. Keep it fun, kind, and encouraging! 🌟"""


def extract_drawing(text: str):
    """Pull a [DRAW: ...] tag out of the model reply.
    Returns (clean_text, image_url_or_None) using the free Pollinations service."""
    import re
    import urllib.parse

    match = re.search(r"\[DRAW:\s*(.+?)\]", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return text.strip(), None

    prompt = match.group(1).strip()
    clean_text = re.sub(r"\[DRAW:\s*.+?\]", "", text, flags=re.IGNORECASE | re.DOTALL).strip()

    # Wrap the child's request in safe cartoon styling. Warning/"avoid this"
    # pictures get a plainer, discouraging style instead of a cheerful one.
    lower = prompt.lower()
    is_warning = any(
        w in lower for w in ("no-smoking", "no smoking", "circle-slash", "circle slash",
                             "warning", "do not", "cigarette", "vape", "tobacco")
    )
    if is_warning:
        safe_prompt = (
            f"simple flat cartoon warning illustration for kids, clear red no-symbol, "
            f"educational safety sign, not appealing, dull muted colors: {prompt}"
        )
    else:
        safe_prompt = (
            f"child friendly cartoon illustration, cute, colorful, wholesome, safe for kids, "
            f"storybook style: {prompt}"
        )
    encoded = urllib.parse.quote(safe_prompt)
    image_url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=512&height=512&nologo=true&safe=true"
    )
    return clean_text, image_url


app = FastAPI(title="Talk2Breath")


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []  # [{"role": "user"/"assistant", "content": "..."}]
    participant_id: str = ""


class SessionStartRequest(BaseModel):
    participant_id: str


class SpeakRequest(BaseModel):
    text: str


def _clip_history(history: list[dict], max_turns: int = 10) -> list[dict]:
    """Keep only the last few turns, and only valid roles, to stay fast + safe."""
    cleaned = [
        {"role": m["role"], "content": str(m["content"])[:2000]}
        for m in history
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    return cleaned[-max_turns:]


def groq_complete(messages, models, max_tokens=400):
    """Try every API key against every model until one works.
    Rotates to the next key when a key is rate-limited or invalid."""
    clients = get_clients()
    for i, client in enumerate(clients, start=1):
        for model in models:
            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=max_tokens,
                )
                return completion.choices[0].message.content
            except RateLimitError:
                print(f"[rate-limited] key #{i} / {model} is out of tokens, trying next...")
                continue
            except AuthenticationError:
                print(f"[bad key] key #{i} was rejected — skipping it.")
                break  # skip remaining models for this bad key, go to next key
    raise OutOfTokens()


def groq_chat(messages, max_tokens=400):
    """Text chat: main model first, then the lighter fallback, across all keys."""
    return groq_complete(messages, (TEXT_MODEL, FALLBACK_MODEL), max_tokens)


def groq_transcribe(filename, raw_bytes):
    """Turn a recorded voice clip into text using Groq Whisper, rotating keys."""
    clients = get_clients()
    for i, client in enumerate(clients, start=1):
        try:
            result = client.audio.transcriptions.create(
                file=(filename, raw_bytes),
                model=STT_MODEL,
                temperature=0,
            )
            return result.text.strip()
        except RateLimitError:
            print(f"[rate-limited] key #{i} / whisper is out of tokens, trying next...")
            continue
        except AuthenticationError:
            print(f"[bad key] key #{i} rejected — skipping.")
            continue
    raise OutOfTokens()


def groq_speech(text: str) -> bytes:
    """Turn Breezy's reply into spoken audio (WAV bytes) using Groq TTS, rotating keys.
    Generating the voice server-side means it sounds the same and actually plays on
    every tablet/browser, instead of depending on each device's own speech engine."""
    clients = get_clients()
    for i, client in enumerate(clients, start=1):
        try:
            response = client.audio.speech.create(
                model=TTS_MODEL,
                voice=TTS_VOICE,
                input=text,
                response_format="wav",
            )
            return response.read()
        except RateLimitError:
            print(f"[rate-limited] key #{i} / TTS is out of tokens, trying next...")
            continue
        except AuthenticationError:
            print(f"[bad key] key #{i} rejected — skipping.")
            continue
    raise OutOfTokens()


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Text chat with Breezy."""
    try:
        log_turn(req.participant_id, "user", req.message[:2000])

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += _clip_history(req.history)
        messages.append({"role": "user", "content": req.message[:2000]})

        reply = groq_chat(messages)
        clean, image_url = extract_drawing(reply)
        log_turn(req.participant_id, "assistant", clean)
        return {"reply": clean, "image_url": image_url}
    except OutOfTokens:
        return JSONResponse(
            status_code=429,
            content={"error": "Breezy has done SO much talking today that he needs a "
                              "big rest! 😴 Please come back a little later. 🌬️"},
        )
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        print("\n=== CHAT ERROR ===")
        traceback.print_exc()
        print("==================\n")
        return JSONResponse(
            status_code=500,
            content={"error": "Breezy is taking a little breath. Please try again! 🌬️",
                     "detail": str(e)},
        )


@app.post("/api/chat-image")
async def chat_image(
    image: UploadFile = File(...),
    message: str = Form("What is in this picture?"),
    participant_id: str = Form(""),
):
    """Child uploads a photo; Breezy looks at it and responds kindly."""
    try:
        log_turn(participant_id, "user", f"[sent a picture] {message[:1000]}")
        raw = await image.read()
        if len(raw) > 8 * 1024 * 1024:
            return JSONResponse(
                status_code=413,
                content={"error": "That picture is a bit too big! Try a smaller one. 📷"},
            )
        mime = image.content_type or "image/jpeg"
        b64 = base64.b64encode(raw).decode("utf-8")
        data_url = f"data:{mime};base64,{b64}"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": message[:1000]},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]
        reply = groq_complete(messages, (VISION_MODEL,))
        clean, image_url = extract_drawing(reply)
        log_turn(participant_id, "assistant", clean)
        return {"reply": clean, "image_url": image_url}
    except OutOfTokens:
        return JSONResponse(
            status_code=429,
            content={"error": "Breezy's eyes need a little rest! 😴 Please try again later. 🖼️"},
        )
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        print("\n=== IMAGE ERROR ===")
        traceback.print_exc()
        print("===================\n")
        return JSONResponse(
            status_code=500,
            content={"error": "Breezy couldn't see the picture. Please try again! 🖼️",
                     "detail": str(e)},
        )


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Turn a recorded voice clip into text (Groq Whisper). Works in all browsers."""
    try:
        raw = await audio.read()
        if len(raw) > 25 * 1024 * 1024:
            return JSONResponse(
                status_code=413,
                content={"error": "That voice message is too long! Try a shorter one. 🎤"},
            )
        # Give Groq a filename with the right extension so it detects the format.
        ct = (audio.content_type or "").lower()
        if "mp4" in ct or "m4a" in ct:
            ext = "mp4"
        elif "ogg" in ct:
            ext = "ogg"
        elif "wav" in ct:
            ext = "wav"
        elif "mpeg" in ct or "mp3" in ct:
            ext = "mp3"
        else:
            ext = "webm"
        text = groq_transcribe(f"audio.{ext}", raw)
        return {"text": text}
    except OutOfTokens:
        return JSONResponse(
            status_code=429,
            content={"error": "Breezy's ears need a little rest! 😴 Please try again later."},
        )
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        print("\n=== TRANSCRIBE ERROR ===")
        traceback.print_exc()
        print("========================\n")
        return JSONResponse(
            status_code=500,
            content={"error": "I couldn't hear that clearly. Please try again! 🎤",
                     "detail": str(e)},
        )


_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿]+")


@app.post("/api/session/start")
async def session_start(req: SessionStartRequest):
    """Called once when a child enters their participant ID, before the chat begins.
    Re-entering the same ID later (e.g. after the browser closed or crashed) appends
    to that participant's existing transcript instead of starting a new one."""
    try:
        pid = clean_participant_id(req.participant_id)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    is_new = not log_path(pid).exists()
    log_line(pid, "=== SESSION START ===")
    return {"ok": True, "participant_id": pid, "new_participant": is_new}


@app.post("/api/tts")
async def tts(req: SpeakRequest):
    """Turn Breezy's reply into audio server-side (Groq PlayAI TTS) so voice sounds
    the same and reliably plays back on every tablet/browser via a plain <audio> tag,
    instead of depending on each device's own (often missing) speech engine."""
    try:
        clean = _EMOJI_RE.sub("", req.text or "").strip()
        if not clean:
            return JSONResponse(status_code=400, content={"error": "Nothing to say."})
        audio_bytes = groq_speech(clean[:2000])
        b64 = base64.b64encode(audio_bytes).decode("utf-8")
        return {"audio_url": f"data:audio/wav;base64,{b64}"}
    except OutOfTokens:
        return JSONResponse(
            status_code=429,
            content={"error": "Breezy's voice needs a little rest! 😴"},
        )
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        print("\n=== TTS ERROR ===")
        traceback.print_exc()
        print("==================\n")
        return JSONResponse(
            status_code=500,
            content={"error": "Breezy's voice isn't working right now.", "detail": str(e)},
        )


@app.get("/api/health")
async def health():
    return {"status": "ok", "keys_loaded": len(API_KEYS)}


# Serve the frontend (index.html, style.css, app.js) at "/"
app.mount("/", StaticFiles(directory="static", html=True), name="static")
