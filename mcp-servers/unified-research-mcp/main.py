"""Unified Research MCP server: SearXNG search + Playwright deep page reading, in one server."""

import asyncio
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastmcp import FastMCP
from pydantic import Field

from modules import log, page_scraper, searx_engine


async def _prepare_browser() -> None:
    """One-time Chromium download in the background (no browser is opened until a page is read)."""
    try:
        await page_scraper.ensure_chromium()
    except Exception as exc:
        log.warning("Chromium install did not finish: %s", exc)


@asynccontextmanager
async def lifespan(_server):
    task = asyncio.create_task(_prepare_browser())
    try:
        yield {}
    finally:
        task.cancel()
        await page_scraper.shutdown()
        searx_engine.shutdown()


mcp = FastMCP(
    "Unified-Research-Engine",
    instructions=(
        "Local web research in two levels. Start with searx_search: its titles and snippets are often "
        "enough on their own (quick facts, definitions, what a product or project is). Only call deep_page_scrape "
        "when the snippets don't contain what the task needs, such as exact figures, full study details, "
        "tables, or the body of a document, and then only on the most promising URLs. Search again with "
        "new wording or the next pageno whenever results fall short, and alternate between the two tools "
        "as often as the task requires. Use your judgment: reading full pages costs far more context "
        "than snippets."
    ),
    lifespan=lifespan,
)


@mcp.tool
async def searx_search(
    query: Annotated[str, Field(description="Search query")],
    pageno: Annotated[int, Field(ge=1, le=20, description="Results page. Use 2, 3, ... to see further results")] = 1,
    categories: Annotated[
        str | None,
        Field(description="Optional SearXNG categories, comma-separated: general, news, science, it, files, images, videos, social media"),
    ] = None,
    time_range: Annotated[Literal["day", "week", "month", "year"] | None, Field(description="Only recent results")] = None,
    language: Annotated[str | None, Field(description="Language code such as 'en' or 'fr'")] = None,
) -> dict:
    """Search the web through the local SearXNG meta-search engine (Google, Bing, DuckDuckGo, Brave,
    Wikipedia, GitHub, Reddit, arXiv, PubMed and more at once). Returns about 20 results per page with title,
    URL and snippet. Snippets are cheap; answer from them when they suffice. Use pageno or new wording to
    look further, and deep_page_scrape only when you need a page's full content."""
    return await searx_engine.search(query, pageno, categories, time_range, language)


@mcp.tool
async def deep_page_scrape(
    url: Annotated[str, Field(description="Full http(s) URL to read")],
    max_chars: Annotated[
        int, Field(ge=1000, le=100000, description="Most characters of page text to return; lower it to save context")
    ] = 15000,
    include_links: Annotated[bool, Field(description="Also return up to 50 links from the main content, to follow")] = False,
) -> dict:
    """Read one page in full. Opens the URL in headless Chromium, waits for JavaScript to finish
    (works on JavaScript-heavy single-page apps), removes menus, footers and
    cookie banners, and returns the main text. PDFs are converted to text. Use it when search snippets
    aren't enough; it returns much more text than a search does."""
    return await page_scraper.scrape(url, max_chars, include_links)


if __name__ == "__main__":
    mcp.run()
