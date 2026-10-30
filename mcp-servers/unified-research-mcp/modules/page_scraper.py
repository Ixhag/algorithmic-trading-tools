"""Full-page reader: renders a URL in headless Chromium (Playwright) and returns clean main text."""

import asyncio
import io
import re
import subprocess
import sys
from urllib.parse import urlparse

import httpx
from playwright.async_api import Browser, Error as PlaywrightError, Playwright, async_playwright

from . import CONFIG, log

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_pw: Playwright | None = None
_browser: Browser | None = None
_browser_lock = asyncio.Lock()
_install_lock = asyncio.Lock()
_chromium_ready = False
_page_slots = asyncio.Semaphore(3)

# Removes page chrome (menus, footers, cookie banners, scripts) and returns the main readable text.
_EXTRACT_JS = r"""
(includeLinks) => {
  const kill = 'script,style,noscript,template,svg,canvas,iframe,nav,header,footer,aside,form,' +
    '[role=navigation],[role=banner],[role=contentinfo],[aria-hidden=true],' +
    '[id*=cookie i],[class*=cookie i],[id*=consent i],[class*=consent i],[class*=gdpr i]';
  document.querySelectorAll(kill).forEach(el => el.remove());
  const candidates = [...document.querySelectorAll('article, main, [role=main], #content, #main, .content, .main')];
  let best = null, bestLen = 0;
  for (const el of candidates) {
    const n = (el.innerText || '').length;
    if (n > bestLen) { best = el; bestLen = n; }
  }
  const root = (best && bestLen > 400) ? best : document.body;
  const text = root ? root.innerText : '';
  let links = [];
  if (includeLinks && root) {
    const seen = new Set();
    for (const a of root.querySelectorAll('a[href]')) {
      const href = a.href, label = (a.innerText || '').trim().replace(/\s+/g, ' ');
      if (!href.startsWith('http') || seen.has(href) || !label) continue;
      seen.add(href); links.push({text: label.slice(0, 120), url: href});
      if (links.length >= 50) break;
    }
  }
  const meta = document.querySelector('meta[name=description], meta[property="og:description"]');
  return {title: document.title || '', description: meta ? meta.content : '', text, links};
}
"""


def _install_chromium_blocking() -> None:
    log.info("Checking/installing Playwright Chromium (first run downloads ~150 MB)")
    res = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=900,
        creationflags=_NO_WINDOW,
    )
    if res.returncode != 0:
        raise RuntimeError(f"Playwright Chromium install failed:\n{res.stdout.strip()[-1500:]}")
    log.info("Playwright Chromium ready")


async def ensure_chromium() -> None:
    global _chromium_ready
    if _chromium_ready or not CONFIG["auto_install_chromium"] or CONFIG.get("chromium_executable_path"):
        return
    async with _install_lock:
        if not _chromium_ready:
            await asyncio.to_thread(_install_chromium_blocking)
            _chromium_ready = True


async def _get_browser() -> Browser:
    global _pw, _browser
    async with _browser_lock:
        if _browser and _browser.is_connected():
            return _browser
        exe = CONFIG.get("chromium_executable_path") or None  # optional: use an existing Chrome/Chromium
        if not exe:
            await ensure_chromium()
        if _pw is None:
            _pw = await async_playwright().start()
        _browser = await _pw.chromium.launch(
            headless=True, executable_path=exe, args=["--disable-blink-features=AutomationControlled"]
        )
        log.info("Headless Chromium launched")
        return _browser


async def shutdown() -> None:
    global _pw, _browser
    try:
        if _browser:
            await _browser.close()
        if _pw:
            await _pw.stop()
    except Exception:
        pass
    _browser = _pw = None


_LOADING_HINT = re.compile(r"^\s*(loading|please wait|just a moment)\b", re.I)


async def _wait_for_render(page, render_ms: float) -> None:
    """Let JavaScript apps (single-page apps, dashboards) finish rendering.

    Waits for network quiet, then until the visible text stops changing for ~1.5 s
    (or the render budget runs out), so late-filled content isn't missed.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + render_ms / 1000
    try:
        await page.wait_for_load_state("networkidle", timeout=render_ms)
    except PlaywrightError:
        pass
    last, stable = -1, 0
    while loop.time() < deadline:
        try:
            text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        except PlaywrightError:
            return
        n = len(text)
        if n == last and n > 200 and not _LOADING_HINT.search(text):
            stable += 1
            if stable >= 3:
                return
        else:
            stable = 0
        last = n
        await asyncio.sleep(0.5)


def _tidy(text: str) -> str:
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.splitlines()]
    out, blank = [], False
    for ln in lines:
        if not ln:
            if not blank and out:
                out.append("")
            blank = True
        else:
            out.append(ln)
            blank = False
    return "\n".join(out).strip()


def _finish(result: dict, max_chars: int) -> dict:
    text = _tidy(result.pop("text", ""))
    result["char_count"] = len(text)
    result["truncated"] = len(text) > max_chars
    result["content"] = text[:max_chars] + ("\n\n[...truncated]" if len(text) > max_chars else "")
    if not text:
        result["note"] = "No readable text found (page may be blocked, empty, or need a login)."
    return result


async def _scrape_pdf(url: str, max_chars: int) -> dict:
    from pypdf import PdfReader

    async with httpx.AsyncClient(follow_redirects=True, timeout=float(CONFIG["scrape_timeout_seconds"]),
                                 headers={"User-Agent": USER_AGENT}) as client:
        r = await client.get(url)
        r.raise_for_status()
    reader = PdfReader(io.BytesIO(r.content))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
        if sum(map(len, parts)) > max_chars * 2:
            break
    title = (reader.metadata.title if reader.metadata else None) or url.rsplit("/", 1)[-1]
    return _finish({"url": str(r.url), "title": title, "type": "pdf", "pages": len(reader.pages),
                    "text": "\n\n".join(parts)}, max_chars)


async def scrape(url: str, max_chars: int | None = None, include_links: bool = False) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("url must start with http:// or https://")
    max_chars = int(max_chars or CONFIG["scrape_max_chars"])

    if parsed.path.lower().endswith(".pdf"):
        return await _scrape_pdf(url, max_chars)

    timeout_ms = float(CONFIG["scrape_timeout_seconds"]) * 1000
    render_ms = float(CONFIG["scrape_render_wait_seconds"]) * 1000
    browser = await _get_browser()

    async with _page_slots:
        context = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1366, "height": 900},
                                            locale="en-US", java_script_enabled=True)
        try:
            # Skip heavy assets; text is all we need.
            await context.route("**/*", lambda route: route.abort()
                                if route.request.resource_type in ("image", "media", "font")
                                else route.continue_())
            page = await context.new_page()
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except PlaywrightError as exc:
                if "Download is starting" in str(exc):
                    return await _scrape_pdf(url, max_chars)
                raise
            ctype = (response.headers.get("content-type", "") if response else "").lower()
            if "application/pdf" in ctype:
                return await _scrape_pdf(url, max_chars)
            await _wait_for_render(page, render_ms)
            data = await page.evaluate(_EXTRACT_JS, include_links)
            result = {
                "url": page.url,
                "status": response.status if response else None,
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "type": "html",
                "text": data.get("text", ""),
            }
            if include_links:
                result["links"] = data.get("links", [])
            return _finish(result, max_chars)
        finally:
            await context.close()
