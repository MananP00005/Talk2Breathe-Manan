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

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from groq import Groq
from pydantic import BaseModel

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
VISION_MODEL = os.getenv(
    "GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"
)

# Groq client is created lazily so the app still boots without a key
# (so you can open the page and see a friendly message).
_client = None


def get_client():
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set. Add it to your .env file.")
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# The heart of the app: a warm, safe, age-aware system prompt.
# This is what keeps the bot gentle and always focused on the mission.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are "Breezy", a friendly, cheerful lung-shaped cartoon buddy for the \
Talk2Breath app. You teach children (ages 3 to 15) why smoking and vaping are harmful, and \
why fresh air and healthy lungs are wonderful.

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


def _clip_history(history: list[dict], max_turns: int = 10) -> list[dict]:
    """Keep only the last few turns, and only valid roles, to stay fast + safe."""
    cleaned = [
        {"role": m["role"], "content": str(m["content"])[:2000]}
        for m in history
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    return cleaned[-max_turns:]


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Text chat with Breezy."""
    try:
        client = get_client()
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += _clip_history(req.history)
        messages.append({"role": "user", "content": req.message[:2000]})

        completion = client.chat.completions.create(
            model=TEXT_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=400,
        )
        reply = completion.choices[0].message.content
        clean, image_url = extract_drawing(reply)
        return {"reply": clean, "image_url": image_url}
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "Breezy is taking a little breath. Please try again! 🌬️",
                     "detail": str(e)},
        )


@app.post("/api/chat-image")
async def chat_image(
    image: UploadFile = File(...),
    message: str = Form("What is in this picture?"),
):
    """Child uploads a photo; Breezy looks at it and responds kindly."""
    try:
        client = get_client()
        raw = await image.read()
        if len(raw) > 8 * 1024 * 1024:
            return JSONResponse(
                status_code=413,
                content={"error": "That picture is a bit too big! Try a smaller one. 📷"},
            )
        mime = image.content_type or "image/jpeg"
        b64 = base64.b64encode(raw).decode("utf-8")
        data_url = f"data:{mime};base64,{b64}"

        completion = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": message[:1000]},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            temperature=0.7,
            max_tokens=400,
        )
        reply = completion.choices[0].message.content
        clean, image_url = extract_drawing(reply)
        return {"reply": clean, "image_url": image_url}
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "Breezy couldn't see the picture. Please try again! 🖼️",
                     "detail": str(e)},
        )


@app.get("/api/health")
async def health():
    return {"status": "ok", "has_key": bool(GROQ_API_KEY)}


# Serve the frontend (index.html, style.css, app.js) at "/"
app.mount("/", StaticFiles(directory="static", html=True), name="static")
