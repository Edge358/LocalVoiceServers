"""Focused regressions; no models, network requests or audio playback."""
import ast
import io
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]


def definitions(path, names, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class TextTests(unittest.TestCase):
    def test_long_sentences_keep_every_word_and_obey_limit(self):
        ns = definitions("text-to-speech/tts_server.py", {"chunk_text"}, {"re": re, "MAX_CHUNK_CHARS": 400})
        for text in ["word " * 300, "x" * 1201, "Short. " + "word " * 250, "", "One sentence. Another sentence!", "word " * 80]:
            with self.subTest(text=text[:30]):
                chunks = ns["chunk_text"](text)
                self.assertTrue(all(0 < len(c) <= 400 for c in chunks))
                self.assertEqual("".join("".join(chunks).split()), "".join(text.split()))

    def test_all_text_blocks_in_last_text_reply_are_kept(self):
        ns = definitions("clients/claude-code-hook/speak_hook.py", {"last_assistant_text"}, {"json": json})
        messages = [
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Old reply"}]}},
            {"type": "user", "message": {"content": "Question"}},
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "First part."},
                {"type": "thinking", "thinking": "Private reasoning"},
                {"type": "text", "text": "Second part."}]}},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "tool"}]}},
        ]
        with patch("builtins.open", return_value=io.StringIO("\n".join(map(json.dumps, messages)))):
            self.assertEqual(ns["last_assistant_text"]("unused"), "First part.\n\nSecond part.")

    def test_markdown_links_keep_labels_without_syntax(self):
        path = ROOT / "speaker-queue/speaker_queue.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {"EXT_SPOKEN", "FILE_EXTS", "_FILENAME_RE", "_ORDINALS"}
        functions = {"scrub", "_ordinal", "_spoken_filename"}
        nodes = [n for n in tree.body if
                 (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets))
                 or (isinstance(n, ast.FunctionDef) and n.name in functions)]
        ns = {"re": re}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), ns)
        for source, expected in [
            ("Read [the guide](https://example.com/guide).", "Read the guide."),
            ("Read [the guide](https://example.com/a_(b)).", "Read the guide."),
            ("Read [the guide](<C:/My Files/guide.md>).", "Read the guide."),
            ("![A diagram](diagram.png)", "A diagram."),
            ("Use 10-30 seconds.", "Use 10 to 30 seconds."),
            ("Input -> output.", "Input to output."),
        ]:
            with self.subTest(source=source):
                self.assertEqual(ns["scrub"](source), expected)


if __name__ == "__main__":
    unittest.main()
