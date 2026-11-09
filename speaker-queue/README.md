# Speaker queue (port 8011)

Send text, and it is spoken on this computer's speakers. When several programs send
text at once, the replies take turns instead of talking over each other. The queue
turns Markdown into speakable text, sends it to the [text-to-speech](../text-to-speech)
server in small pieces and plays the audio as it becomes available. The first
piece usually starts within a few seconds on the tested RTX 4080; other hardware
and the first request after startup may take longer.

## Setup

It uses the same `localvoice` environment, so there is nothing new to install. It
expects text to speech on port 8009 (`SYNTH_SERVER` in `speaker_queue.py`). Start
text to speech first. Once its health check passes, start from the project's main folder:

```powershell
cd .\speaker-queue
.\start_speaker.ps1
Invoke-RestMethod http://127.0.0.1:8011/health
```

The health check should show `ok: True`. If it reports a connection error just
after starting, wait a moment and try again. Then send a sentence:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8011/say -ContentType 'application/json' -Body '{"text": "Hello. This is the speaker queue."}'
```

You should hear the sentence through your Windows output device and receive
`queued: True`. Return to the main folder with `cd ..` afterward.

`start_speaker.ps1` options: `-Port` (default 8011), `-CondaEnv` (default
`localvoice`), `-PythonExe`, and `-BindHost` (default `127.0.0.1`, this computer only;
the sound plays here, so there is rarely a reason to change it). Stop it with
`stop_speaker.ps1`.

Logs go to `%LOCALAPPDATA%\WisperLocal\tts`: `start_speaker_last.log` (start
problems such as Python not found), `speaker_err.log` (the server's own output and
errors), `speaker_out.log` (queue activity, a few lines per reply), and
`play_last.log` (timing of the most recent reply).

## API

| Request | Body | Answer |
| --- | --- | --- |
| `POST /say` | `{"text": "...", "source": "claude", "session": "", "scrubbed": false}` | `{"queued": true, "position": 0}`, or `{"queued": false, "reason": "..."}` |
| `POST /skip` | none | `{"skipped": true}` if a reply was playing. It stops; the next one starts. |
| `POST /flush` | none | `{"flushed": 3}`, the number of waiting replies removed. The current reply stops too. |
| `GET /health` | none | `{"ok": true, "queue_len": 0, "playing": false, "dictation_held": false, ...}` |

- Only `text` is required.
- `source` picks the voice: `codex` speaks with the `female` voice, anything else
  with `male` (see `VOICE_MAP` in `speaker_queue.py`).
- `session` is only written to the log.
- Send `"scrubbed": true` if your text is already plain speech and should not be
  cleaned up.

## How the queue behaves

- Replies play in the order they arrive.
- A reply that waits more than 120 seconds is dropped as stale. Time spent waiting
  on a dictation hold (below) does not count.
- At most 20 replies wait at once; more are refused.
- Over 10,000 characters, the text is cut off and ends with "Message truncated."
- Pressing **F9** while a reply is playing skips it. To turn that off, set
  `STOP_KEYS = ()` in `speaker_queue.py`.

## Speech controls

**F9** skips the current reply. To turn all queued speech off, run:

```powershell
New-Item -ItemType File -Force "$env:LOCALAPPDATA\WisperLocal\tts\hook_off"
```

To turn it back on:

```powershell
Remove-Item -LiteralPath "$env:LOCALAPPDATA\WisperLocal\tts\hook_off"
```

This switch affects every client using the queue, including both hooks and T3 Code.
The servers keep running. Turning speech back on does not replay discarded replies.

## Control files

Other programs can control the queue with files in `%LOCALAPPDATA%\WisperLocal\tts`:

| File | Effect |
| --- | --- |
| `hook_off` | While it exists, nothing is spoken: the current reply stops, waiting replies are discarded, and new text is refused. Delete it to turn speech back on. |
| `speak_stop` | Create it to skip the current reply (same as `/skip`). |
| `speak_worker.pid` | Process ID of the reply being played, present only while something plays. |
| `dictation_<anything>.hold` | A dictation app holds this file open while recording. No new reply starts while it exists; waiting replies play in order once it closes. A reply already playing is not stopped, so create `speak_stop` too if you need silence at once. |

The hold uses a shared lock file, `speech_gate.lock`, so that a recording and a
reply can never start at the same moment. A program that wants to hold the queue
locks byte 0 of that file, creates its hold file opened without delete sharing and
deleted on close, then releases the lock. The queue checks for holds by trying to
delete them, so a hold left behind by a crashed program clears itself.

Windows only: playback uses Windows' built-in sound player.
