# Codex hook

Reads Codex's replies aloud through the [speaker queue](../../speaker-queue), in the
`female` voice so you can tell Codex from Claude Code. It hands each finished reply
to the [Claude Code hook](../claude-code-hook)'s `--say-file` entry, so keep both
folders together.

## Setup

1. Set up and start [text to speech](../../text-to-speech) and the
   [speaker queue](../../speaker-queue).
2. Add a `notify` line to your Codex settings, `%USERPROFILE%\.codex\config.toml`,
   near the top (before any `[section]`), using the Python from the `localvoice`
   environment and the full path to this file. Run `conda env list` to find Python
   and replace both example paths:

   ```toml
   notify = [
     'C:\Users\YOU\miniconda3\envs\localvoice\python.exe',
     'C:\path\to\LocalVoiceServers\clients\codex-hook\codex_auto_speak.py',
   ]
   ```

   The single quotes keep the backslashes as they are; paths may contain spaces.
   Save a copy of your settings first. If `notify` already exists, do not add a second
   one. Codex accepts one notification command: replacing it replaces that existing
   integration. To keep both, a notification script must call both commands;
   do not combine two commands into one `notify` array.

3. Start a new Codex session. Its next finished reply is spoken. There is nothing to
   ask for after that: every finished reply is read aloud.

To turn speech off, use the same `hook_off` file as the
[Claude Code hook](../claude-code-hook/README.md#turning-speech-off).

If the environment variable `T3CODE_APP_SPEECH_MANAGED` is `1`, the hook does
nothing, because the T3 Code custom build sends its replies to the queue itself.

To remove only this integration, restore your previous `notify` setting or remove
the entry you added. Keep the rest of `config.toml` unchanged.
