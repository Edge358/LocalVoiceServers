import io
import os
import re
import threading

import torch
import torchaudio
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel

# perth watermarker is broken on Windows/Py3.11 -- patch before ChatterboxTTS import
import perth
if perth.PerthImplicitWatermarker is None:
    perth.PerthImplicitWatermarker = perth.DummyWatermarker
from chatterbox.tts import ChatterboxTTS
from chatterbox.tts_turbo import ChatterboxTurboTTS

HERE = os.path.dirname(os.path.abspath(__file__))
VOICES = {
    "male": os.path.join(HERE, "voices", "S_014437.wav"),
    # S_018536 and S_020502 in voices/ are alternates
    "female": os.path.join(HERE, "voices", "S_004168.wav"),
}
DEFAULT_VOICE = "male"
# NOTE: the Turbo engine IGNORES exaggeration and cfg_weight (it warns and
# discards them) -- pace and character come from the reference clip itself.
# These settings only take effect if ENGINE is switched back to "original".
VOICE_SETTINGS = {
    "male": {"exaggeration": 0.3, "cfg_weight": 0.3},
    "female": {"exaggeration": 0.3, "cfg_weight": 0.25},
}
# Chatterbox quality degrades on very long single generations; batch sentences.
MAX_CHUNK_CHARS = 400

app = FastAPI()

# ENGINE: "turbo" (350M single-step decoder, ~3x faster than realtime) or
# "original" (500M, ~1.3x slower than realtime -> audible gaps in auto-speak).
# Same voice reference clips work with both.
ENGINE = "turbo"

# Keep model hot (no reload per request)
if ENGINE == "turbo":
    model = ChatterboxTurboTTS.from_pretrained(device="cuda")
else:
    model = ChatterboxTTS.from_pretrained(device="cuda")
lock = threading.Lock()  # serialize GPU access across concurrent requests


class SpeakRequest(BaseModel):
    text: str
    voice: str = DEFAULT_VOICE


def chunk_text(text: str) -> list[str]:
    """Split sentences and long spans, keeping every chunk within the limit."""
    sentences = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        while len(sentence) > MAX_CHUNK_CHARS:
            cut = sentence.rfind(" ", 0, MAX_CHUNK_CHARS + 1)
            if cut <= 0:
                cut = MAX_CHUNK_CHARS
            sentences.append(sentence[:cut])
            sentence = sentence[cut:].lstrip()
        if sentence:
            sentences.append(sentence)
    chunks, cur = [], ""
    for s in sentences:
        if not s:
            continue
        if cur and len(cur) + len(s) + 1 > MAX_CHUNK_CHARS:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    return chunks


@app.get("/health")
def health():
    return {"status": "ok", "voices": list(VOICES)}


@app.post("/speak")
def speak(req: SpeakRequest):
    name = req.voice if req.voice in VOICES else DEFAULT_VOICE
    ref = VOICES[name]
    # A voice with no tuned settings uses Chatterbox's defaults (Turbo ignores them anyway).
    settings = VOICE_SETTINGS.get(name, {"exaggeration": 0.5, "cfg_weight": 0.5})
    chunks = chunk_text(req.text)
    if not chunks:
        return Response(status_code=400, content="empty text")
    with lock:
        parts = [
            model.generate(
                c,
                audio_prompt_path=ref,
                exaggeration=settings["exaggeration"],
                cfg_weight=settings["cfg_weight"],
            )
            for c in chunks
        ]
    wav = torch.cat(parts, dim=-1)
    buf = io.BytesIO()
    torchaudio.save(buf, wav.cpu(), model.sr, format="wav")
    return Response(content=buf.getvalue(), media_type="audio/wav")
