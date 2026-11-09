from fastapi import FastAPI, UploadFile, File
from faster_whisper import WhisperModel
import tempfile
import os

app = FastAPI()

# Keep model hot (no reload per request)
model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")

@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    suffix = os.path.splitext(file.filename)[1] or ".wav"
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        data = await file.read()
        with open(path, "wb") as f:
            f.write(data)

        segments, info = model.transcribe(
            path,
            vad_filter=True,
            condition_on_previous_text=False,
            vad_parameters=dict(
                min_speech_duration_ms=250,
                min_silence_duration_ms=250,
                speech_pad_ms=100,
            ),
        )
        out = []
        for s in segments:
            out.append(s.text.strip())
        return {"text": " ".join([t for t in out if t])}
    finally:
        try:
            os.remove(path)
        except:
            pass
