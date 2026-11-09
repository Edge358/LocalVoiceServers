# Text to speech (port 8009)

Send text, get a WAV file back. Runs [Chatterbox Turbo](https://github.com/resemble-ai/chatterbox)
by Resemble AI on your NVIDIA graphics card, using a short reference clip to set the
voice. On the tested RTX 4080, generation was about three times faster than real time;
speed depends on your graphics card and the text.

## Setup

First create the `localvoice` Python environment (see the
[main README](../README.md#setup)). This server needs nothing else: PyTorch brings
its own CUDA libraries, so no CUDA Toolkit is needed for it.

1. **Start it.** From the project's main folder:

   ```powershell
   cd .\text-to-speech
   .\start_tts.ps1
   ```

   The script returns at once while the server loads in the background. The first
   start also downloads the model (about 3.8 GB) into your Hugging Face cache, which
   can take several minutes. Run this check again after waiting if it initially
   reports a connection error. It should return `status: ok` and the voice names:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8009/health
   ```

   If it never does, look in `%LOCALAPPDATA%\WisperLocal\tts`: `start_last.log`
   (for example, Python not found) and `server_err.log` (the server's own errors).

2. **Try it:**

   ```powershell
   Invoke-WebRequest -Method Post -Uri http://127.0.0.1:8009/speak -ContentType 'application/json' -Body '{"text": "Hello from my own computer."}' -OutFile hello.wav
   ```

   Open `hello.wav` in your audio player. You should hear "Hello from my own computer."
   The first request after a start takes longer while the model warms up.
   Delete the test WAV when finished. Return to the main folder with `cd ..`
   before following another component's guide.

## Scripts

| Script | What it does |
| --- | --- |
| `start_tts.ps1` | Starts the server hidden. Does nothing if it is already running. |
| `stop_tts.ps1` | Stops it. |

`start_tts.ps1` options: `-Port` (default 8009), `-CondaEnv` (default `localvoice`),
`-PythonExe`, and `-BindHost`. By default only this computer can connect; to allow
your network, use `-BindHost 0.0.0.0` or set the user environment variable
`LOCALVOICE_TTS_HOST=0.0.0.0`, and open port 8009 for private networks in Windows
Firewall (see the [speech-to-text README](../speech-to-text/README.md#using-it-from-other-computers)).

## Voices

| Name | Clip | Description |
| --- | --- | --- |
| `male` (default) | `voices/S_014437.wav` | English, England |
| `female` | `voices/S_004168.wav` | English, England |

Two more clips, `S_018536.wav` and `S_020502.wav`, are alternates. All four come from
the [GLOBE_V2](https://huggingface.co/datasets/MushanW/GLOBE_V2) dataset (CC0,
public domain), drawn from Mozilla Common Voice.

To add a voice, put a clean WAV of one person speaking in `voices` (the included
clips run 10 to 18 seconds), add a line to `VOICES` in `tts_server.py`, and restart
the server. On the Turbo model, the clip alone sets the voice's pace and character.
After the restart, ask for the new voice by name in `/speak`. The speaker queue
picks its voices in `VOICE_MAP` in `speaker_queue.py`. Only use voices you have the right to use.

## API

- `GET /health` answers `{"status": "ok", "voices": ["male", "female"]}`.
- `POST /speak` with JSON `{"text": "...", "voice": "male"}` answers with WAV audio.
  Text is split into chunks of at most 400 characters and the audio is joined.
  Long sentences split at spaces where possible; an oversized word is split too.
  An unknown voice falls back to `male`.

## Notes

- `ENGINE = "turbo"` in `tts_server.py`. Set it to `"original"` for the larger
  Chatterbox model, which honors the per-voice `exaggeration` and `cfg_weight`
  settings. It ran slower than real time on the tested PC.
- Resemble AI's Perth watermarker does not load on Windows with Python 3.11, so the
  server substitutes Perth's built-in no-op watermarker and the audio is not
  watermarked.
