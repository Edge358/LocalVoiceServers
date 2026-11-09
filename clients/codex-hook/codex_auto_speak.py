"""Codex notify hook: read Codex's finished replies aloud through the speaker queue.

Codex runs this after each turn, passing a JSON payload as the first argument.
The reply text is handed to the Claude Code hook's --say-file entry with the
"female" voice, so Codex and Claude Code sound different. See README.md.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SPEAK_HOOK = os.path.join(HERE, "..", "claude-code-hook", "speak_hook.py")
VOICE = "female"


def final_message(payload):
    if not isinstance(payload, dict):
        return None
    if payload.get("type") not in {"agent-turn-complete", "agent_turn_complete"}:
        return None

    for key in ("last-assistant-message", "last_assistant_message"):
        message = payload.get(key)
        if isinstance(message, str) and message:
            return message
    return None


def main():
    # T3 Code sends its own replies to the queue; skip them here to avoid double speech.
    if os.environ.get("T3CODE_APP_SPEECH_MANAGED") == "1":
        return
    try:
        payload = json.loads(sys.argv[1])
        message = final_message(payload)
        if message is None:
            return

        file_descriptor, text_path = tempfile.mkstemp(prefix="codex_say_", suffix=".txt")
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="") as text_file:
            text_file.write(message)

        try:
            # Same Python that Codex used to run this file (the localvoice environment).
            subprocess.Popen(
                [sys.executable, SPEAK_HOOK, "--say-file", text_path, VOICE],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            os.unlink(text_path)
    except Exception:
        pass


if __name__ == "__main__":
    main()
