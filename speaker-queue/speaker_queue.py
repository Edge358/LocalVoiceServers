"""Speaker queue service (port 8011): serialized speech for multiple terminals.

Owns ALL spoken playback. Clients (the Claude Code hook, other programs) POST text
to /say and never play audio themselves. Items play in arrival order (FIFO); a
dictation hold pauses playback without discarding waiting items. See README.md.

Run as service:  uvicorn speaker_queue:app --host 127.0.0.1 --port 8011
Child mode:      python speaker_queue.py --play <utf8 text file> <voice>
                 (spawned by the service; plays one item then exits; its PID is
                 what speak_worker.pid names, so a client app can stop or kill
                 the current reply without touching the service)

Working files live in STATE_DIR, not next to this script, so the code folder
stays clean and clients (Remember This Please, the Claude Code hook) find them in
one fixed place: WisperLocal, then tts, under %LOCALAPPDATA%. Remember This
Please has the same folder built in, so it is not configurable here.
  hook_off    exists = auto-speak OFF: /say rejects, queue flushes, nothing plays
  speak_stop  stop the CURRENT item only; the queue continues with the next
  speak_worker.pid  PID of the playback child while something plays
  play_last.log     per-chunk timing log of the most recent playback child
  dictation_*.hold  a client is recording; playback waits until these are gone
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import msvcrt

SYNTH_SERVER = "http://127.0.0.1:8009/speak"
TTL_SECONDS = 120         # drop items older than this at dequeue time (stale news)
SAFETY_CAP = 20           # queue depth that should never be hit; log if it is
SPEAK_MAX_CHARS = 10000   # scrubbed chars; ~10 min of speech, then spoken truncation
FIRST_CHUNK_CHARS = 80    # small first chunk -> audio starts sooner
SECOND_CHUNK_CHARS = 120  # ramp: a short first sentence can't cover a full 200-char synth
CHUNK_CHARS = 200
VOICE_MAP = {"claude": "male", "codex": "female"}
DEFAULT_VOICE = "male"
STATE_DIR = os.path.join(os.environ["LOCALAPPDATA"], "WisperLocal", "tts")
os.makedirs(STATE_DIR, exist_ok=True)
PIDFILE = os.path.join(STATE_DIR, "speak_worker.pid")
OFF_SWITCH = os.path.join(STATE_DIR, "hook_off")
STOP_FILE = os.path.join(STATE_DIR, "speak_stop")
PLAY_LOG = os.path.join(STATE_DIR, "play_last.log")
STOP_KEYS = (0x78,)  # VK_F9 skips the current reply; set to () to turn this off


@contextmanager
def speech_gate(timeout: float = 0.25):
    # Shared with client apps that hold the queue while recording.
    # Hold through child creation AND PID publication.
    with open(os.path.join(STATE_DIR, "speech_gate.lock"), "a+b") as gate:
        deadline = time.monotonic() + timeout
        while True:
            try:
                gate.seek(0)
                msvcrt.locking(gate.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("speech coordination gate is busy")
                time.sleep(0.01)
        try:
            yield
        finally:
            gate.seek(0)
            msvcrt.locking(gate.fileno(), msvcrt.LK_UNLCK, 1)


def dictation_held():
    with os.scandir(STATE_DIR) as entries:
        for entry in entries:
            if not (entry.name.startswith("dictation_") and entry.name.endswith(".hold")):
                continue
            try:
                # A live client handle denies deletion. A remnant after a power loss does not.
                os.remove(entry.path)
            except FileNotFoundError:
                continue
            except PermissionError:
                return True
    return False


_kernel = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel.OpenProcess.restype = wintypes.HANDLE
_kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel.WaitForSingleObject.restype = wintypes.DWORD
_kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                             wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
_kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
_kernel.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel.CloseHandle.restype = wintypes.BOOL


def worker_alive():
    # Preserve a playback child across a queue-service restart instead of hiding its PID.
    try:
        with open(PIDFILE) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return False
    handle = _kernel.OpenProcess(0x100000 | 0x1000, False, pid)
    if not handle:
        # Includes access denied: a PID we cannot open is never our own python child
        # (same user), so treating it as alive would silence the queue forever.
        return False
    try:
        path = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(path))
        return (_kernel.WaitForSingleObject(handle, 0) == 258
                and _kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length))
                and os.path.basename(path.value).lower() == "python.exe")
    finally:
        _kernel.CloseHandle(handle)



def claim_playback():
    # A service crash between Popen and publishing the PID must not leave an unheard child
    # free to start speaking after a client has acquired a recording hold.
    # The child is its own process, so a longer wait here blocks nobody; a 250 ms miss
    # would kill the child and silently lose this reply.
    with speech_gate(timeout=2.0):
        if dictation_held() or os.path.exists(OFF_SWITCH) or os.path.exists(STOP_FILE):
            return False
        if worker_alive():
            with open(PIDFILE) as f:
                if int(f.read().strip()) != os.getpid():
                    return False
        with open(PIDFILE, "w") as f:
            f.write(str(os.getpid()))
        return True


def _log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------- markdown scrubber: turns Markdown into speakable text. Its rules
# were tuned by listening to real replies; change them by ear, not by eye. --------

EXT_SPOKEN = {
    "py": "p y", "md": "m d", "cs": "c s", "js": "j s", "ts": "t s",
    "ps1": "p s 1", "json": "jason", "txt": "text", "wav": "wave",
    "exe": "e x e", "dll": "d l l", "csv": "c s v", "yml": "yamel",
    "yaml": "yamel", "html": "h t m l", "css": "c s s", "xml": "x m l",
    "sln": "solution", "csproj": "c s project", "cmd": "c m d",
}
FILE_EXTS = set(EXT_SPOKEN) | {
    "log", "zip", "onnx", "pid", "config", "settings", "resx", "ini",
    "toml", "bat", "sh", "png", "jpg", "ico", "pdf",
}
_FILENAME_RE = re.compile(
    r"\b([A-Za-z_][\w.-]*)\.(" + "|".join(sorted(FILE_EXTS)) + r")\b", re.I
)

_ORDINALS = ["First", "Second", "Third", "Fourth", "Fifth",
             "Sixth", "Seventh", "Eighth", "Ninth", "Tenth"]


def _ordinal(n: int) -> str:
    return f"{_ORDINALS[n - 1]}, " if 1 <= n <= 10 else f"Number {n}, "


def _spoken_filename(m: re.Match) -> str:
    stem, ext = m.group(1), m.group(2)
    stem = re.sub(r"[_.\-]+", " ", stem)
    stem = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", stem)
    return f"{stem} dot {EXT_SPOKEN.get(ext.lower(), ext)}"


def scrub(md: str) -> str:
    t = md
    # fenced code blocks -> short spoken placeholder
    t = re.sub(r"```[\w]*\n.*?```", " (code block omitted) ", t, flags=re.S)
    # tables -> drop entirely; they do not read aloud usefully
    t = re.sub(r"^\|.*\|\s*$", "", t, flags=re.M)
    t = re.sub(r"^\s*\|?[\s:-]+\|[\s:|-]*$", "", t, flags=re.M)
    # horizontal rules and blockquote markers
    t = re.sub(r"^\s*[-*_]{3,}\s*$", "", t, flags=re.M)
    t = re.sub(r"^\s*>\s?", "", t, flags=re.M)
    # Keep Markdown link labels before replacing bare URLs. Support angle-bracket
    # destinations (paths with spaces) and balanced parentheses in ordinary URLs.
    t = re.sub(r'!?\[([^\]\n]+)\]\(\s*(?:<[^>\n]*>|(?:[^()\n]|\([^()\n]*\))*)\s*\)',
               r"\1", t)
    # urls -> spoken stand-in
    t = re.sub(r"https?://\S+", " (link) ", t)
    # windows / env-var paths -> just the final segment
    t = re.sub(r"[A-Za-z]:\\[^\s`)]+", lambda m: m.group(0).rstrip("\\").split("\\")[-1], t)
    t = re.sub(r"%[A-Za-z_]+%[\\/][^\s`)]+",
               lambda m: re.split(r"[\\/]", m.group(0).rstrip("\\/"))[-1], t)
    # forward-slash paths: keep the trailing filename, or the last segment of bare dirs
    t = re.sub(r"\b[\w.-]+(?:/[\w.-]+)*/([\w-]+\.[A-Za-z]\w{0,6})\b", r"\1", t)
    t = re.sub(r"\b[\w-]+(?:/[\w-]+){2,}\b", lambda m: m.group(0).split("/")[-1], t)
    # file.py:123 -> file.py, line 123 (letter before the colon, so times like 3:30 survive)
    t = re.sub(r"(?<=[A-Za-z]):(\d+)\b", r", line \1", t)
    # filenames -> speakable (split stem, spell the extension)
    t = _FILENAME_RE.sub(_spoken_filename, t)

    # join wrapped lines into paragraphs BEFORE terminal punctuation. Within a
    # blank-line block, a line that does not start a header/list item is a
    # continuation of the previous line.
    joined = []
    for block in re.split(r"\n\s*\n", t):
        merged = []
        for ln in block.splitlines():
            s = ln.strip()
            if not s:
                continue
            starts_new = re.match(r"^(#{1,6}\s|\d+\.\s+|[-*+]\s+)", s)
            if merged and not starts_new:
                merged[-1] += " " + s
            else:
                merged.append(s)
        joined.extend(merged)

    lines = []
    for ln in joined:
        # headers -> plain sentence; numbered items get ordinals, bullets stripped
        ln = re.sub(r"^#{1,6}\s*(.+)$", r"\1.", ln)
        ln = re.sub(r"^(\d+)\.\s+", lambda m: _ordinal(int(m.group(1))), ln)
        ln = re.sub(r"^[-*+]\s+", "", ln)
        # inline code / emphasis markers
        ln = re.sub(r"`([^`]*)`", r"\1", ln)
        ln = re.sub(r"\*\*([^*]+)\*\*", r"\1", ln)
        ln = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", ln)
        # symbols that read badly
        ln = ln.replace("—", ", ").replace("–", ", ").replace("~", "about ")
        ln = ln.replace("->", " to ").replace("=>", " to ").replace("→", " to ")
        ln = ln.replace("&", " and ")
        ln = re.sub(r"(?<=\d)\s*%", " percent", ln)
        ln = re.sub(r"(\d)x\b", r"\1 times", ln)
        # abbreviations -> spoken forms
        ln = re.sub(r"\be\.g\.,?\s*", "for example, ", ln)
        ln = re.sub(r"\bi\.e\.,?\s*", "that is, ", ln)
        ln = re.sub(r"\bvs\.?\s+", "versus ", ln)
        ln = re.sub(r"\betc\.", "et cetera.", ln)
        # numeric ranges 10-30 -> "10 to 30" (lookarounds keep dates like 2026-07-21 intact)
        ln = re.sub(r"(?<![\d-])(\d{1,3})\s?-\s?(\d{1,3})(?![\d-])", r"\1 to \2", ln)
        ln = re.sub(r"\+cu\d+", "", ln)
        # git-style hex hashes (must contain both a digit and a letter)
        ln = re.sub(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b",
                    "a commit hash", ln)
        # identifiers: snake_case -> spaces, CamelCase -> split words
        ln = ln.replace("_", " ")
        ln = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", " ", ln)
        # dotted version numbers / decimals -> "point"; word/word -> "or"
        ln = re.sub(r"(\d)\.(?=\d)", r"\1 point ", ln)
        ln = re.sub(r"(?<![\w./\\])([A-Za-z][\w+-]*)/([A-Za-z][\w+-]*)(?![\w./\\])", r"\1 or \2", ln)
        ln = re.sub(r"\s+", " ", ln).strip()
        if not ln:
            continue
        if ln[-1] not in ".!?:,":
            ln += "."
        lines.append(ln)
    return " ".join(lines)


def _clause_split(sentence: str) -> list[str]:
    # An oversized "sentence" (scrubbed bullet lists produce 300-char blobs with
    # no period until the end) synthesizes far longer than earlier audio covers,
    # leaving mid-response dead air. Split it at clause punctuation; a clause
    # still over the cap is cut at a word boundary.
    parts = []
    for clause in re.split(r"(?<=[,;:])\s+", sentence):
        while len(clause) > CHUNK_CHARS:
            cut = clause.rfind(" ", 0, CHUNK_CHARS)
            if cut <= 0:
                cut = CHUNK_CHARS
            parts.append(clause[:cut])
            clause = clause[cut:].strip()
        if clause:
            parts.append(clause)
    return parts


def make_chunks(text: str) -> list[str]:
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s]
    pieces = []
    for s in sentences:
        pieces.extend(_clause_split(s) if len(s) > CHUNK_CHARS else [s])
    ramp = (FIRST_CHUNK_CHARS, SECOND_CHUNK_CHARS)
    chunks, cur = [], ""
    for p in pieces:
        limit = ramp[len(chunks)] if len(chunks) < len(ramp) else CHUNK_CHARS
        if cur and len(cur) + len(p) + 1 > limit:
            chunks.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        chunks.append(cur)
    return chunks


# ---------------- playback child (--play): one item, then exit ----------------
# The WAV handling encodes hard-won gotchas (float32 format tag 3, placeholder
# data sizes, the SND_PURGE same-thread rule); test by ear after any change.

def synth(text: str, voice: str) -> bytes:
    req = urllib.request.Request(
        SYNTH_SERVER,
        data=json.dumps({"text": text, "voice": voice}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read()


def play_item(text_path: str, voice: str):
    import ctypes
    import queue as _q
    import tempfile
    import winsound

    try:
        with open(text_path, encoding="utf-8") as f:
            spoken = f.read()
    except OSError:
        return
    try:
        os.remove(text_path)
    except OSError:
        pass
    chunks = make_chunks(spoken)
    if not chunks or not claim_playback():
        return

    q: _q.Queue = _q.Queue()
    stop = threading.Event()

    def watch_stop():
        # passive poll (never blocks or swallows keys). hook_off appearing also
        # stops us: an app's master off switch must silence playback even if
        # its kill misses. speak_stop is deleted after use; hook_off is left alone.
        user32 = ctypes.windll.user32
        while not stop.wait(0.05):
            key_hit = any(user32.GetAsyncKeyState(k) & 0x8000 for k in STOP_KEYS)
            if key_hit or os.path.exists(STOP_FILE) or os.path.exists(OFF_SWITCH):
                stop.set()
        try:
            os.remove(STOP_FILE)
        except OSError:
            pass

    def wav_duration(path):
        # wave.open cannot read the server's float32 WAVs (format tag 3), so read
        # the RIFF header directly. The server sometimes writes a placeholder data
        # size (streaming-style header), so trust the bytes on disk when larger.
        with open(path, "rb") as f:
            if f.read(12)[:4] != b"RIFF":
                raise ValueError("not a RIFF file")
            byte_rate = None
            while True:
                hdr = f.read(8)
                if len(hdr) < 8:
                    raise ValueError("no data chunk")
                size = int.from_bytes(hdr[4:8], "little")
                if hdr[:4] == b"fmt ":
                    byte_rate = int.from_bytes(f.read(size)[8:12], "little")
                elif hdr[:4] == b"data" and byte_rate:
                    bytes_on_disk = os.path.getsize(path) - f.tell()
                    return max(size, bytes_on_disk) / byte_rate
                else:
                    f.seek(size + (size & 1), 1)

    def play_interruptible(path):
        # SND_PURGE only reliably cancels sounds started by the SAME thread, so
        # play async and watch the clock here instead of blocking in PlaySound.
        try:
            duration = wav_duration(path)
            print(f"[{time.monotonic():.2f}] play {os.path.basename(path)}: "
                  f"size={os.path.getsize(path)} dur={duration:.2f}s", flush=True)
        except Exception as e:
            print(f"play {os.path.basename(path)}: duration unknown ({e}); blocking",
                  flush=True)
            winsound.PlaySound(path, winsound.SND_FILENAME)
            return
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            if stop.wait(0.05):
                winsound.PlaySound(None, winsound.SND_PURGE)
                print(f"[{time.monotonic():.2f}] stopped by stop event", flush=True)
                return
        print(f"[{time.monotonic():.2f}] chunk finished (deadline reached)", flush=True)

    def produce():
        try:
            for i, c in enumerate(chunks):
                if stop.is_set():
                    break
                wav = synth(c, voice)
                fd, path = tempfile.mkstemp(prefix=f"queue_tts_{i}_", suffix=".wav")
                with os.fdopen(fd, "wb") as f:
                    f.write(wav)
                q.put(path)
        except Exception as e:
            print(f"synth failed: {e}", flush=True)
        finally:
            q.put(None)

    threading.Thread(target=produce, daemon=True).start()
    threading.Thread(target=watch_stop, daemon=True).start()
    # exit promptly on stop (never wait out an in-flight synth call) so the
    # service moves to the next queued item fast
    while not stop.is_set():
        try:
            path = q.get(timeout=0.1)
        except _q.Empty:
            continue
        if path is None:
            break
        try:
            play_interruptible(path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
    stop.set()
    while True:
        try:
            leftover = q.get_nowait()
        except _q.Empty:
            break
        if leftover:
            try:
                os.remove(leftover)
            except OSError:
                pass


# ---------------- queue service (imported by uvicorn, never in --play mode) ---

if __name__ != "__main__":
    from fastapi import FastAPI
    from pydantic import BaseModel

    app = FastAPI()

    _lock = threading.RLock()
    _queue: deque = deque()
    _current = None
    _wake = threading.Event()
    _stopping = threading.Event()
    _thread = None
    _clock = 0.0
    _last_tick = time.monotonic()
    _was_held = dictation_held()

    class SayRequest(BaseModel):
        text: str
        source: str = "claude"
        session: str = ""
        scrubbed: bool = False

    def _update_clock():
        global _clock, _last_tick, _was_held
        now = time.monotonic()
        held = dictation_held()
        # Do not charge either edge of a sampled hold against a reply's lifetime.
        if not held and not _was_held:
            _clock += max(0, now - _last_tick)
        _last_tick, _was_held = now, held
        return held

    def _kill_current_locked():
        if _current:
            try:
                _current["proc"].kill()
            except OSError:
                pass
        elif worker_alive():
            # An orphan child from a previous service instance still honors this file.
            with open(STOP_FILE, "w"):
                pass

    def _remove(path):
        try:
            os.remove(path)
        except OSError:
            pass

    @app.get("/health")
    def health():
        with _lock, speech_gate():
            held = _update_clock()
            return {"ok": True, "queue_len": len(_queue),
                    "playing": _current is not None or worker_alive(),
                    "dictation_held": held, "dictation_hold_supported": True}

    @app.post("/say")
    def say(req: SayRequest):
        spoken = req.text if req.scrubbed else scrub(req.text)
        if len(spoken) > SPEAK_MAX_CHARS:
            spoken = spoken[:SPEAK_MAX_CHARS].rsplit(" ", 1)[0] + ". Message truncated."
        if not spoken.strip():
            return {"queued": False, "reason": "empty after scrub"}
        with _lock, speech_gate():
            _update_clock()
            if os.path.exists(OFF_SWITCH):
                return {"queued": False, "reason": "auto-speak off"}
            if len(_queue) >= SAFETY_CAP:
                _log(f"SAFETY CAP hit ({SAFETY_CAP}); rejecting item from "
                     f"{req.source!r}/{req.session!r}")
                return {"queued": False, "reason": "queue full"}
            _queue.append({"text": spoken, "source": req.source, "session": req.session,
                           "ts": _clock})
            pos = len(_queue) - 1
        _wake.set()
        _log(f"queued [{pos}] {req.source!r}/{req.session!r} ({len(spoken)} chars)")
        return {"queued": True, "position": pos}

    @app.post("/skip")
    def skip():
        with _lock, speech_gate():
            playing = _current is not None or worker_alive()
            _kill_current_locked()
        _wake.set()
        return {"skipped": playing}

    @app.post("/flush")
    def flush():
        with _lock, speech_gate():
            n = len(_queue)
            _queue.clear()
            _kill_current_locked()
        _wake.set()
        return {"flushed": n}

    def _spawn(item):
        text_path = None
        proc = None
        try:
            fd, text_path = __import__("tempfile").mkstemp(
                prefix="queue_say_", suffix=".txt", dir=STATE_DIR)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(item["text"])
            voice = VOICE_MAP.get(item["source"], DEFAULT_VOICE)
            with open(PLAY_LOG, "w") as log:
                proc = subprocess.Popen(
                    [sys.executable, os.path.abspath(__file__), "--play", text_path, voice],
                    creationflags=0x08000000,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            with open(PIDFILE, "w") as f:
                f.write(str(proc.pid))
            _log(f"playing {item['source']!r}/{item['session']!r} "
                 f"voice={voice} pid={proc.pid}")
            return {"item": item, "proc": proc, "text_path": text_path}
        except BaseException:
            if proc is not None:
                proc.kill()
                proc.wait(timeout=2)
            if text_path:
                _remove(text_path)
            raise

    def _playback_step():
        global _current
        with _lock, speech_gate():
            held = _update_clock()
            if os.path.exists(OFF_SWITCH):
                if _queue:
                    _log(f"auto-speak off: flushed {len(_queue)} queued item(s)")
                    _queue.clear()
                _kill_current_locked()
            if _current is not None:
                if _current["proc"].poll() is None:
                    return
                _remove(_current["text_path"])
                _current = None
                _remove(PIDFILE)
            if worker_alive():
                return
            _remove(PIDFILE)
            if held or os.path.exists(OFF_SWITCH):
                return
            while _queue:
                item = _queue[0]
                if _clock - item["ts"] > TTL_SECONDS:
                    _queue.popleft()
                    _log(f"dropped stale item from {item['source']!r}/{item['session']!r}")
                    continue
                _remove(STOP_FILE)
                _current = _spawn(item)
                _queue.popleft()
                return

    def _playback_loop():
        while not _stopping.is_set():
            try:
                _playback_step()
            except Exception as exc:
                _log(f"playback coordination failed: {exc}")
                _stopping.wait(1)
            _wake.wait(timeout=0.1)
            _wake.clear()

    @app.on_event("startup")
    def _startup():
        global _thread
        _stopping.clear()
        with _lock, speech_gate():
            if not worker_alive():
                _remove(PIDFILE)
                _remove(STOP_FILE)
        _thread = threading.Thread(target=_playback_loop, daemon=True)
        _thread.start()
        _log("speaker queue service started (dictation hold supported)")

    @app.on_event("shutdown")
    def _shutdown():
        _stopping.set()
        _wake.set()
        if _thread is not None:
            _thread.join(timeout=3)
        with _lock, speech_gate():
            _kill_current_locked()
            if _current is not None:
                _current["proc"].wait(timeout=2)
                _remove(_current["text_path"])
                _remove(PIDFILE)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--play":
        play_item(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else DEFAULT_VOICE)
