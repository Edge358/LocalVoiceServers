# Claude Code hook

Reads Claude Code's replies aloud through the [speaker queue](../../speaker-queue).
When Claude finishes a reply, this hook sends the reply text to the queue and
returns at once, so Claude Code is never slowed down.

## Setup

1. Set up and start [text to speech](../../text-to-speech) and the
   [speaker queue](../../speaker-queue).
2. Add a Stop hook to your Claude Code settings, `%USERPROFILE%\.claude\settings.json`,
   using the Python from the `localvoice` environment and the full path to this file
   (forward slashes work and avoid escaping). Run `conda env list` to find Python.
   Replace both example paths, keeping the escaped quotes around them:

   ```json
   {
     "hooks": {
       "Stop": [
         {
           "hooks": [
             {
               "type": "command",
               "command": "\"C:/Users/YOU/miniconda3/envs/localvoice/python.exe\" \"C:/path/to/LocalVoiceServers/clients/claude-code-hook/speak_hook.py\"",
               "timeout": 30
             }
           ]
         }
       ]
     }
   }
   ```

   Keep your existing settings. If there is already a `hooks` object, add to that
   object. If `Stop` already exists, append the new entry to its array; do not create
   a second `Stop` key or replace other hooks. Save a copy of your settings first.

3. Start a new Claude Code session. Its next reply is spoken. There is nothing to
   ask for after that: every finished reply is read aloud.

## Turning speech off

Use the queue's [speech controls](../../speaker-queue/README.md#speech-controls).
This silences every client using the queue, not just Claude Code. The hook stays
installed. To remove only this integration, remove the command you added from
`settings.json`, preserving all other hooks.

## Other programs

Any program can speak through the same file without using the queue's web API:

```powershell
& "C:\Users\YOU\miniconda3\envs\localvoice\python.exe" "C:\path\to\LocalVoiceServers\clients\claude-code-hook\speak_hook.py" --say-file "C:\path\to\text.txt" female
```

The text file is read, deleted, and queued. The voice `female` is sent with the
source `codex`; anything else is sent as `claude` (the `male` voice).

If the environment variable `T3CODE_APP_SPEECH_MANAGED` is `1`, the hook speaks
nothing (a `--say-file` text file is still deleted). The T3 Code custom build sets it
in its sessions because it sends replies to the queue itself.

The hook writes its last result to `hook_last.log` in `%LOCALAPPDATA%\WisperLocal\tts`.
