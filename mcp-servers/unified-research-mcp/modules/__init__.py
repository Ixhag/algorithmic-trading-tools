"""Shared config and logging for the Unified Research MCP server."""

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# MCP uses stdout for the protocol, so all logging goes to stderr.
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [unified-research] %(levelname)s %(message)s",
)
log = logging.getLogger("unified-research")

DEFAULTS = {
    "searxng_port": 8888,
    "searxng_start_timeout_seconds": 60,
    "search_timeout_seconds": 20,
    "max_results_per_page": 20,
    "scrape_timeout_seconds": 30,
    "scrape_render_wait_seconds": 8,
    "scrape_max_chars": 15000,
    "auto_install_chromium": True,
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    path = ROOT / "config.json"
    try:
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        pass
    except Exception as exc:  # a bad config.json should not kill the server
        log.warning("Could not read %s (%s); using defaults", path, exc)
    return cfg


CONFIG = load_config()
