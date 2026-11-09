"""Claude Code Stop-hook: thin client for the speaker queue service (port 8011).

Registered in ~/.claude/settings.json (Stop hook). Reads the hook JSON on stdin,
relaunches itself detached (--worker) so Claude Code is never blocked, extracts
the last assistant text from the session transcript, and POSTs it raw to the
speaker queue service, which owns scrubbing, chunking, voices, queueing, and
playback (see README.md and the speaker queue's README).

Create a file named `hook_off` in the speaker queue's state folder (WisperLocal,
then tts, under %LOCALAPPDATA%) to disable speaking without unregistering the hook (the service enforces it too).
No client-side fallback: if the service is down, log to hook_last.log in that
same folder and exit silently.

Generic entry for other programs (for example a Codex hook):
  speak_hook.py --say-file <utf8 text file> [voice]
The file is read, deleted, and POSTed with source "codex" when voice is
"female" (else "claude").
"""
import json
import os
import subprocess
import sys
import urllib.request

QUEUE_SERVER = "http://127.0.0.1:8011/say"
VOICE = "male"
STATE_DIR = os.path.join(os.environ["LOCALAPPDATA"], "WisperLocal", "tts")
os.makedirs(STATE_DIR, exist_ok=True)
OFF_SWITCH = os.path.join(STATE_DIR, "hook_off")
LOG = os.path.join(STATE_DIR, "hook_last.log")


def last_assistant_text(transcript_path: str) -> str:
    last = ""
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "assistant":
                continue
            content = (obj.get("message") or {}).get("content") or []
            parts = [block["text"] for block in content
                     if isinstance(block, dict) and block.get("type") == "text"
                     and isinstance(block.get("text"), str) and block["text"].strip()]
            if parts:
                last = "\n\n".join(parts)
    return last


def post_say(text: str, source: str, session: str):
    if not text.strip():
        return
    req = urllib.request.Request(
        QUEUE_SERVER,
        data=json.dumps({"text": text, "source": source,
                         "session": session}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            print(f"POST /say {source!r}/{session!r}: {r.read().decode()}", flush=True)
    except OSError as e:
        print(f"POST /say failed (service down?): {e}", flush=True)


def worker(transcript_path: str):
    post_say(last_assistant_text(transcript_path), "claude", transcript_path)


def worker_file(text_path: str, voice: str):
    # generic entry: POST the contents of a UTF-8 text file (used by non-Claude
    # clients, e.g. a Codex hook). The file is deleted after reading.
    try:
        with open(text_path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return
    try:
        os.remove(text_path)
    except OSError:
        pass
    source = "codex" if voice == "female" else "claude"
    post_say(text, source, f"sayfile-{source}")


def spawn_detached(args: list):
    # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__)] + args,
        creationflags=0x00000008 | 0x00000200,
        stdin=subprocess.DEVNULL,
        stdout=open(LOG, "w"),
        stderr=subprocess.STDOUT,
    )


def main():
    # T3 Code sends its own replies to the queue; skip them here to avoid double speech.
    if os.environ.get("T3CODE_APP_SPEECH_MANAGED") == "1":
        if len(sys.argv) > 2 and sys.argv[1] in {"--say-file", "--worker-file"}:
            try:
                os.remove(sys.argv[2])
            except OSError:
                pass
        return
    if len(sys.argv) > 2 and sys.argv[1] == "--worker":
        worker(sys.argv[2])
        return
    if len(sys.argv) > 2 and sys.argv[1] == "--worker-file":
        worker_file(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else VOICE)
        return
    if len(sys.argv) > 2 and sys.argv[1] == "--say-file":
        # deletes the file even when auto-speak is off, so callers never leave litter
        if os.path.exists(OFF_SWITCH):
            try:
                os.remove(sys.argv[2])
            except OSError:
                pass
        else:
            spawn_detached(["--worker-file", sys.argv[2],
                            sys.argv[3] if len(sys.argv) > 3 else VOICE])
        return
    # hook entry: never block Claude Code -- hand off to a detached worker and exit
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    transcript_path = data.get("transcript_path", "")
    if not transcript_path or os.path.exists(OFF_SWITCH):
        return
    spawn_detached(["--worker", transcript_path])


if __name__ == "__main__":
    main()
