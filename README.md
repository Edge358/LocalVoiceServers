# Local Voice Servers

Talk to your Windows PC and have it talk back. Speech to text, text to speech, and a
queue so spoken replies take turns. Speech recognition and generation run on your
own NVIDIA graphics card, without a cloud speech service or a speech-service account.
These servers do not send recordings or reply text to a cloud service. Internet
access is needed to install packages and download the models.

This project supplies the servers. A separate program records your microphone,
sends requests, or types the resulting words into another app. Connected AI
assistants have their own account and network requirements.

Each piece is a small local web server. Any program that can send a web request can
use them: a dictation app, a script, an AI coding assistant reading its answers aloud.

```
 your program ──audio──▶  speech-to-text  (port 8008)  ──text──▶ your program
 your program ──text───▶  speaker-queue   (port 8011)  ──text──▶ text-to-speech (port 8009)
                               │                                       │
                               └────────── plays the audio ◀──────────┘
```

| Folder | What it does | Port | Built on |
| --- | --- | --- | --- |
| [speech-to-text](speech-to-text) | Send a recording, get the words back | 8008 | [faster-whisper](https://github.com/SYSTRAN/faster-whisper), Whisper `large-v3-turbo` |
| [text-to-speech](text-to-speech) | Send text, get a WAV file back | 8009 | [Chatterbox Turbo](https://github.com/resemble-ai/chatterbox) |
| [speaker-queue](speaker-queue) | Send text, it gets spoken on your speakers, one reply at a time | 8011 | text-to-speech |
| [clients/claude-code-hook](clients/claude-code-hook) | Reads Claude Code's replies aloud through the queue | none | speaker-queue |
| [clients/codex-hook](clients/codex-hook) | Reads Codex's replies aloud, in the other voice | none | claude-code-hook |

## Choose what you need

| I want to... | Set up these parts |
| --- | --- |
| Turn recordings into text | [Speech to text](speech-to-text/README.md) |
| Create speech audio files | [Text to speech](text-to-speech/README.md) |
| Hear replies through my speakers | [Text to speech](text-to-speech/README.md), then [speaker queue](speaker-queue/README.md) |
| Hear terminal assistants | The two parts above, then the [Claude Code hook](clients/claude-code-hook/README.md) or [Codex hook](clients/codex-hook/README.md) |

Start with the shared setup below. Only run the servers you use.

## What you need

- Windows. Tested on Windows 11 with an NVIDIA RTX 4080.
- An NVIDIA graphics card supported by the pinned CUDA 12.4 PyTorch packages, and
  a compatible driver. On the tested PC, speech to text used about 2.1 GB of graphics
  memory and text to speech about 2.9 GB. These are measurements, not universal
  minimum requirements; leave room for other programs using the card.
- For speech to text, CUDA Toolkit 12.6 (details in its setup guide).
- Internet access for packages and first-time model downloads.
- [Miniconda](https://docs.anaconda.com/miniconda/) or Anaconda, to keep these
  Python packages apart from the rest of your system.
- About 15 GB of free disk space. The two speech models are about 5.5 GB; the rest
  is Python packages. Allow extra space for installer and download caches.

## Before you start

Keep the project in a permanent folder. If you downloaded a ZIP from GitHub's
**Code > Download ZIP** menu, extract it before running any scripts.

Open **Anaconda PowerShell Prompt** from the Start menu. Go to the folder containing
this README and `requirements.txt`. Replace this example with your actual folder:

```powershell
cd "C:\path\to\LocalVoiceServers"
```

All commands in this README start from that folder. Replace example paths and
keep the quotation marks, especially around paths containing spaces.

If PowerShell reports that running scripts is disabled, allow local scripts for
your account. A managed work computer may require help from its administrator:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

If you downloaded this project as a ZIP file, Windows also marks every file as
"from the internet". Unblock them once, from this folder:

```powershell
Get-ChildItem -File -Recurse | Unblock-File
```

## Setup

1. **One Python environment for everything.** In the Anaconda PowerShell Prompt,
   from this project's main folder, run:

   ```powershell
   conda create -n localvoice python=3.11 -y
   conda activate localvoice
   pip install -r requirements.txt
   ```

   This includes PyTorch built for CUDA 12.4 (about 2.5 GB).

2. **Set up the parts you chose above.** Follow each server's README and its test
   request. For spoken replies, get text to speech working before starting the queue.
   Speech to text is independent and can be skipped if you only want spoken replies.

Each server has a start and a stop script. The start scripts run the server hidden in
the background, so no window stays open.

If a start script cannot find Python, run `conda env list` to see where your
environment is, and pass the full path to its `python.exe` with `-PythonExe`:

```powershell
.\text-to-speech\start_tts.ps1 -PythonExe "D:\My Python\envs\localvoice\python.exe"
```

Use that option on each start script and when registering automatic startup below.

## Start them when you log on

Once each server starts by hand, let Windows start them for you. From this folder:

```powershell
.\register_logon_tasks.ps1
```

This creates three scheduled tasks for your user account. No administrator rights
are needed. Add `-AllowNetwork` if other computers on your network should reach
speech to text and text to speech (they also need a firewall rule; see
[Using it from other computers](speech-to-text/README.md#using-it-from-other-computers)),
and `-Remove` to delete the tasks again. Without `-AllowNetwork`, the tasks explicitly
bind to this computer only, even if manual starts use a network environment variable.

This registers all three servers. Use it once all three are set up; if you only need
some of them, use their manual start commands instead.

If manual startup needed custom Python or CUDA paths, pass those same values here:

```powershell
.\register_logon_tasks.ps1 -PythonExe "D:\My Python\envs\localvoice\python.exe" -CudaBin "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin"
```

`-CondaEnv` is available if you named your environment differently. Keep any
`-AllowNetwork` and custom path options when re-running this command; it replaces
the saved task settings. Run it again if you move the project folder. `-Remove`
removes automatic startup but does not stop servers already running.

## Everyday use

After setup, start just the servers you need from the main folder:

```powershell
.\speech-to-text\start_stt.ps1
.\text-to-speech\start_tts.ps1
```

For spoken replies, check text to speech before starting the queue:

```powershell
Invoke-RestMethod http://127.0.0.1:8009/health
.\speaker-queue\start_speaker.ps1
Invoke-RestMethod http://127.0.0.1:8011/health
```

The first check should show `status: ok`; the queue should show `ok: True`.
A connection error while a model is loading means it is not ready yet. Wait and try
again; if it keeps failing, use the troubleshooting table below.

To stop all three, stop the queue first. Speech to text displays a confirmation:

```powershell
.\speaker-queue\stop_speaker.ps1
.\text-to-speech\stop_tts.ps1
.\speech-to-text\stop_stt.ps1
```

These commands only stop the voice servers. A Windows restart is not needed for a
code change. If you used a nondefault `-Port`, pass it to the matching stop script
too. Keep custom Python, CUDA and network options on later starts.

Press **F9** to skip the current reply. To turn spoken replies off without stopping
the servers, see [speech controls](speaker-queue/README.md#speech-controls).

## Troubleshooting

| What you see | What to check |
| --- | --- |
| `conda` is not recognized | Use Anaconda PowerShell Prompt after installing Miniconda or Anaconda. |
| Python cannot be found | Run `conda env list`; use `-PythonExe` for a nonstandard installation. |
| Speech to text fails | Read `%LOCALAPPDATA%\WisperLocal\stt\server_err.log`; check the CUDA step in its guide. |
| Text to speech does not answer | First downloads can take several minutes. Check `start_last.log` and `server_err.log` in `%LOCALAPPDATA%\WisperLocal\tts`. |
| Text is queued but there is no sound | Check text-to-speech health, Windows' output device and volume, and `play_last.log` in the same `tts` folder. Check that `hook_off` is absent. |
| A script refuses to manage a process | Another program or copy may own the port. The scripts leave it alone; stop that program using its own controls or choose another port. |
| A hook is silent | Test the queue's example request first, then check the hook paths and `hook_last.log`. In T3 Code, use its own speech setting. |

Keep the folders together: start and stop scripts use `server_process.ps1` from
the main folder to verify which process they are managing.

## Working files

Logs, process ID files and the queue's control files go in
`%LOCALAPPDATA%\WisperLocal\stt` and `%LOCALAPPDATA%\WisperLocal\tts`, not in this
folder. The folder name is historical and is the same on every computer.

## Programs that use these servers

- **Remember This Please**, a Windows dictation and capture app: press a key or a
  mouse button, talk, and the words are typed where your cursor is.
- **Claude Code** and **Codex**: their replies are read aloud through the
  [Claude Code hook](clients/claude-code-hook) and the [Codex hook](clients/codex-hook),
  in different voices so you can tell the two apart. This works in any terminal,
  such as Windows Terminal or Wave, because the hooks belong to Claude Code and
  Codex, not to the terminal.
- **T3 Code**, a desktop app for AI coding agents: a
  [custom build](https://github.com/Edge358/t3code/tree/edge358-custom-build) sends
  its replies to the queue itself, so it needs no hook. In its Settings, under Chat,
  turn on **Read replies aloud** and set **Speech service address** to
  `http://127.0.0.1:8011/say`. Inside T3 Code the two hooks stay quiet, so you never
  hear a reply twice.

## Checking changes

The regression tests use temporary servers and spare ports; they do not load speech
models or play audio. In the `localvoice` environment, from the main folder:

```powershell
python -B -m unittest discover -s tests -v
.\tests\test_task_arguments.ps1
```

## Credits

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (MIT) and OpenAI's
  Whisper models (MIT).
- [Chatterbox](https://github.com/resemble-ai/chatterbox) by Resemble AI (MIT).
- The voices are clips from the [GLOBE_V2](https://huggingface.co/datasets/MushanW/GLOBE_V2)
  dataset (CC0), drawn from Mozilla Common Voice.

## License

MIT. See [LICENSE](LICENSE).
