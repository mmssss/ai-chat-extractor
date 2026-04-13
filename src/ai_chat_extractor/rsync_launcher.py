"""Launcher shim for the ai-chat-rsync bash script."""

import subprocess
import sys
from importlib.resources import as_file, files


def main():
    ref = files("ai_chat_extractor._scripts") / "ai-chat-rsync"
    try:
        with as_file(ref) as script_path:
            raise SystemExit(
                subprocess.call(["bash", str(script_path)] + sys.argv[1:])
            )
    except FileNotFoundError:
        print(
            "ai-chat-rsync: bash is required but was not found on PATH",
            file=sys.stderr,
        )
        raise SystemExit(1)
