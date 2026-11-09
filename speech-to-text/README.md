# Speech to text (port 8008)

Send a recording, get the words back. Runs Whisper `large-v3-turbo` through
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) on your NVIDIA graphics
card. The model stays loaded between requests, so there is no start-up wait each time.

## Setup

First create the `localvoice` Python environment (see the
[main README](../README.md#setup)).

1. **CUDA Toolkit 12.** faster-whisper needs NVIDIA's cuBLAS library. Install the
   [CUDA Toolkit 12.6](https://developer.nvidia.com/cuda-12-6-0-download-archive)
   for Windows x64. The start script adds its `bin` folder to the server's PATH. If
   you installed a different 12.x version, pass its folder with `-CudaBin`.
   (cuDNN is not needed separately; it comes with the Python package.)

2. **Download the model and check your graphics card.** In the Anaconda PowerShell
   Prompt, start from the project's main folder and run:

   ```powershell
   cd .\speech-to-text
   conda activate localvoice
   $env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin;" + $env:PATH
   python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo', device='cuda', compute_type='float16'); print('ready')"
   ```

   If your CUDA folder differs, change the path above as well as `-CudaBin` when
   starting the server.

   This downloads the model (about 1.6 GB) into `%USERPROFILE%\.cache\huggingface`
   and prints `ready`. If something is wrong with CUDA, the error shows here in plain
   view instead of inside a hidden server. Loading the model is only the first
   check; the transcription request below also exercises the audio processing.

3. **Start it:**

   ```powershell
   .\start_stt.ps1
   ```

   It takes a few seconds, is silent when it works, and shows a message box if it
   fails. Server output goes to `%LOCALAPPDATA%\WisperLocal\stt\server_err.log`.

4. **Try it** with any WAV file:

   ```powershell
   curl.exe -F "file=@C:\path\to\recording.wav" http://127.0.0.1:8008/transcribe
   ```

   Replace the example filename with your recording. The response should contain
   a `text` field with the spoken words. Return to the main folder with `cd ..`
   before following another component's guide.

## Scripts

| Script | What it does |
| --- | --- |
| `start_stt.ps1` | Starts the server hidden. Does nothing if it is already running. |
| `stop_stt.ps1` | Stops it and shows the result. |
| `status_stt.ps1` | Shows whether it is running and the addresses it answers on. |
| `toggle_stt.vbs` | Double-click: offers Start or Stop, whichever applies. |

`start_stt.ps1` options: `-Port` (default 8008), `-CondaEnv` (default `localvoice`),
`-PythonExe` (a full path, instead of finding the conda environment), `-CudaBin`,
and `-BindHost` (below).

## Using it from other computers

By default the server answers only programs on this computer. To let other
computers on your network use it:

1. Start it with `-BindHost 0.0.0.0`, or set the user environment variable
   `LOCALVOICE_STT_HOST` to `0.0.0.0` so every start uses it (including the toggle).
2. Allow the port through Windows Firewall, for private networks only. In an
   administrator PowerShell:

   ```powershell
   New-NetFirewallRule -DisplayName "Local Voice Servers STT 8008" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8008 -Profile Private
   ```

There is no password, so only do this on a network you trust.

## API

`POST /transcribe`, a multipart form upload with one field, `file` (WAV or any
format ffmpeg can read). Answer:

```json
{"text": "Testing one, two, three."}
```

## Settings in `stt_server.py`

- Model: `large-v3-turbo`, `float16` on the GPU. A smaller model such as `small`
  uses less memory but punctuates worse.
- `condition_on_previous_text=False` and the voice-activity settings
  (`min_silence_duration_ms=250`, `speech_pad_ms=100`) help reduce invented
  words after you stop talking, a known habit of the turbo model on short dictation.
