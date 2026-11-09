"""Windows tests using temporary servers, ports and state; no models or audio."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
ROOT = Path(__file__).resolve().parents[1]
PS = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"]


def quoted(value):
    return "'" + str(value).replace("'", "''") + "'"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Local Voice Test ")
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, LOCALAPPDATA=str(self.root / "state"), PYTHONDONTWRITEBYTECODE="1")
        self.children = []
        self.servers = []
        shutil.copy2(ROOT / "server_process.ps1", self.root)
        for folder, module, suffix in [("speech-to-text", "stt_server", "stt"), ("text-to-speech", "tts_server", "tts"), ("speaker-queue", "speaker_queue", "speaker")]:
            directory = self.root / folder
            directory.mkdir()
            for action in ["start", "stop"]:
                shutil.copy2(ROOT / folder / f"{action}_{suffix}.ps1", directory)
            (directory / f"{module}.py").write_bytes(
                b"from fastapi import FastAPI\r\napp = FastAPI()\r\n"
                b"@app.get('/health')\r\ndef health(): return {'ok': True}\r\n"
                b"@app.post('/flush')\r\ndef flush(): return {'flushed': 0}\r\n")

    def tearDown(self):
        for command in self.servers:
            self.run_ps(command, check=False)
        for proc in self.children:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
        self.temp.cleanup()

    def run_ps(self, command, check=True):
        # A hidden child can inherit pipe handles from PowerShell. File-backed
        # capture lets the shell return without waiting for that server to exit.
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            result = subprocess.run(PS + ["-Command", command], env=self.env,
                                    stdout=out, stderr=err, timeout=45)
            out.seek(0)
            err.seek(0)
            result.stdout = out.read().decode(errors="replace")
            result.stderr = err.read().decode(errors="replace")
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def wait_ready(self, port):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                    return
            except OSError:
                time.sleep(.1)
        self.fail("Test server did not start")

    def test_each_server_starts_once_and_stops_from_path_with_spaces(self):
        for folder, module, suffix, state in [("speech-to-text", "stt_server", "stt", "stt"), ("text-to-speech", "tts_server", "tts", "tts"), ("speaker-queue", "speaker_queue", "speaker", "tts")]:
            with self.subTest(server=module):
                port = free_port()
                directory = self.root / folder
                pid_file = self.root / "state/WisperLocal" / state / f"{module}.pid"
                stop = ". " + quoted(self.root / "server_process.ps1") + "\nStop-LocalVoiceServer -Module " + module + " -AppDirectory " + quoted(directory) + " -Port " + str(port) + " -PidFile " + quoted(pid_file)
                self.servers.append(stop)
                start = "& " + quoted(directory / f"start_{suffix}.ps1") + " -BindHost 127.0.0.1 -Port " + str(port) + " -PythonExe " + quoted(sys.executable)
                self.run_ps(start)
                self.wait_ready(port)
                before = pid_file.read_text().strip()
                self.run_ps(start)
                self.assertEqual(pid_file.read_text().strip(), before)
                # STT displays a modal popup; exercise its shared stop function directly.
                if module == "stt_server":
                    self.run_ps(stop)
                else:
                    self.run_ps("& " + quoted(directory / f"stop_{suffix}.ps1") + " -Port " + str(port))
                self.assertFalse(pid_file.exists())
                with socket.socket() as s:
                    self.assertNotEqual(s.connect_ex(("127.0.0.1", port)), 0)

    def test_unrelated_listener_survives_start_and_stop(self):
        port = free_port()
        proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        self.children.append(proc)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(.1)
        for folder, suffix in [("text-to-speech", "tts"), ("speaker-queue", "speaker")]:
            for action in ["start", "stop"]:
                result = self.run_ps("& " + quoted(self.root / folder / f"{action}_{suffix}.ps1") + " -Port " + str(port), check=False)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("Refusing to manage", result.stderr)
                self.assertIsNone(proc.poll())

    def test_stale_pid_cannot_kill_unrelated_process(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], creationflags=subprocess.CREATE_NO_WINDOW)
        self.children.append(proc)
        state = self.root / "state/WisperLocal/tts"
        state.mkdir(parents=True)
        (state / "tts_server.pid").write_bytes(str(proc.pid).encode())
        result = self.run_ps("& " + quoted(self.root / "text-to-speech/stop_tts.ps1") + " -Port " + str(free_port()), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(proc.poll())


if __name__ == "__main__":
    unittest.main()
