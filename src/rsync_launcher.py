"""Launcher shim for the ai-chat-rsync bash script."""

import os
import sys
import importlib.resources


def main():
    script = importlib.resources.files("_rsync_data") / "ai-chat-rsync.sh"
    os.execvp("bash", ["bash", str(script)] + sys.argv[1:])
