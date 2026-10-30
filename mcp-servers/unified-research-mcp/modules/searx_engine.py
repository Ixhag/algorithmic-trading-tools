"""SearXNG meta-search: runs the bundled SearXNG (no Docker) on demand and queries its JSON API."""

import asyncio
import subprocess
import sys
import time

import httpx

from . import CONFIG, ROOT, log

RUNNER = ROOT / "searxng" / "run_searxng.py"
LOG_FILE = ROOT / "searxng" / "searxng.log"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # no console window flashing on Windows

_proc: subprocess.Popen | None = None
_start_lock = asyncio.Lock()


class SearxError(RuntimeError):
    pass


def _base_url() -> str:
    return f"http://127.0.0.1:{int(CONFIG['searxng_port'])}"


async def _is_up(client: httpx.AsyncClient) -> bool:
    try:
        r = await client.get(f"{_base_url()}/healthz", timeout=2)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def _log_tail(n: int = 1500) -> str:
    try:
        return LOG_FILE.read_text(encoding="utf-8", errors="replace")[-n:]
    except OSError:
        return ""


def _launch() -> subprocess.Popen:
    log.info("Starting bundled SearXNG on %s", _base_url())
    logf = open(LOG_FILE, "w", encoding="utf-8")
    try:
        return subprocess.Popen(
            [sys.executable, str(RUNNER), str(int(CONFIG["searxng_port"]))],
            cwd=str(RUNNER.parent),
            stdin=subprocess.PIPE,  # kept open; SearXNG exits when this process ends
            stdout=logf,
            stderr=subprocess.STDOUT,
            creationflags=_NO_WINDOW,
        )
    finally:
        logf.close()  # the child keeps its own handle


async def ensure_searxng() -> None:
    """Start SearXNG on the first search; reuse it afterwards."""
    global _proc
    async with httpx.AsyncClient() as client:
        if await _is_up(client):
            return
        async with _start_lock:
            if await _is_up(client):
                return
            if _proc is None or _proc.poll() is not None:
                _proc = _launch()
            deadline = time.monotonic() + float(CONFIG["searxng_start_timeout_seconds"])
            while time.monotonic() < deadline:
                if await _is_up(client):
                    log.info("SearXNG ready")
                    return
                if _proc.poll() is not None:
                    tail = _log_tail()
                    hint = ""
                    if "address already in use" in tail.lower() or "only one usage of each socket" in tail.lower():
                        hint = f" Port {CONFIG['searxng_port']} is used by another program; change searxng_port in config.json."
                    raise SearxError(f"SearXNG stopped while starting.{hint}\nLog ({LOG_FILE}):\n{tail}")
                await asyncio.sleep(0.5)
            raise SearxError(f"SearXNG didn't start within {CONFIG['searxng_start_timeout_seconds']} s. Log: {LOG_FILE}")


def shutdown() -> None:
    global _proc
    if _proc and _proc.poll() is None:
        try:
            _proc.stdin.close()  # runner exits on EOF
            _proc.wait(timeout=5)
        except Exception:
            _proc.kill()
    _proc = None


def _clean(text: str | None, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def search(
    query: str,
    pageno: int = 1,
    categories: str | None = None,
    time_range: str | None = None,
    language: str | None = None,
    safesearch: int = 0,
) -> dict:
    await ensure_searxng()

    params: dict = {"q": query, "format": "json", "pageno": max(1, int(pageno)), "safesearch": safesearch}
    if categories:
        params["categories"] = categories
    if time_range:
        params["time_range"] = time_range
    if language:
        params["language"] = language

    async with httpx.AsyncClient(timeout=float(CONFIG["search_timeout_seconds"])) as client:
        r = await client.get(f"{_base_url()}/search", params=params)
    if r.status_code == 403:
        raise SearxError("SearXNG refused JSON output. Add 'json' under search.formats in searxng/settings.yml.")
    if r.status_code == 429:
        raise SearxError("SearXNG rate-limited the request. Set server.limiter to false in searxng/settings.yml.")
    r.raise_for_status()
    data = r.json()

    max_n = int(CONFIG["max_results_per_page"])
    results = []
    seen = set()
    for item in data.get("results", []):
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        entry = {
            "title": _clean(item.get("title"), 200),
            "url": url,
            "snippet": _clean(item.get("content"), 400),
        }
        if item.get("publishedDate"):
            entry["published"] = item["publishedDate"]
        results.append(entry)
        if len(results) >= max_n:
            break

    out: dict = {"query": query, "pageno": params["pageno"], "results": results}
    if data.get("answers"):
        out["answers"] = [_clean(a if isinstance(a, str) else a.get("answer"), 500) for a in data["answers"]]
    if data.get("infoboxes"):
        out["infoboxes"] = [
            {"title": ib.get("infobox"), "summary": _clean(ib.get("content"), 800), "url": ib.get("id")}
            for ib in data["infoboxes"][:2]
        ]
    if data.get("suggestions"):
        out["suggestions"] = list(data["suggestions"])[:6]
    if not results:
        dead = [e[0] if isinstance(e, (list, tuple)) else e for e in data.get("unresponsive_engines", [])]
        if dead:
            out["unresponsive_engines"] = dead
            out["note"] = "No results: the search engines listed didn't respond (check the internet connection or retry shortly)."
        else:
            out["note"] = "No results on this page. Try different wording, pageno=1, or another category."
    return out
