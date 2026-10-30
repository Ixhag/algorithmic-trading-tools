"""Runs the bundled SearXNG (no Docker) on 127.0.0.1. Started by the MCP server on the first search.

Usage: python run_searxng.py <port>
Exits on its own when the MCP server goes away (normal exit, crash, or Claude being closed).
"""

import os
import secrets
import sys
import threading
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent

# SearXNG imports the Unix-only `pwd` module (used only by its optional Valkey database,
# which is off here). A tiny stand-in lets it load on Windows; SearXNG's code is unchanged.
try:
    import pwd  # noqa: F401
except ImportError:
    _pwd = types.ModuleType("pwd")
    _pwd.getpwuid = lambda uid: types.SimpleNamespace(pw_name=os.environ.get("USERNAME", "user"))
    sys.modules["pwd"] = _pwd

os.environ["SEARXNG_SETTINGS_PATH"] = str(HERE / "settings.yml")
# Fresh random secret on every start, so no secret is ever stored in the repo.
os.environ.setdefault("SEARXNG_SECRET", secrets.token_hex(32))


def _exit_when_parent_dies() -> None:
    # The MCP server holds our stdin open; it closes when that process ends for any reason.
    try:
        sys.stdin.buffer.read()
    finally:
        os._exit(0)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    threading.Thread(target=_exit_when_parent_dies, daemon=True).start()

    from searx.webapp import app
    from waitress import serve

    serve(app, host="127.0.0.1", port=port, threads=8, ident="searxng")


if __name__ == "__main__":
    main()
