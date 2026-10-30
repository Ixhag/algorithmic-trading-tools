# Unified Research MCP

A local MCP server for web research: one server, two tools, no Docker and no API keys.

| Tool | What it does |
|---|---|
| `searx_search(query, pageno=1, categories, time_range, language)` | Searches many engines at once (Google, Bing, DuckDuckGo, Brave, Wikipedia, GitHub, Reddit, arXiv, PubMed and more) through a bundled SearXNG. Returns about 20 results per page as title, URL and snippet. Raise `pageno` for more. |
| `deep_page_scrape(url, max_chars=15000, include_links=false)` | Opens one page in headless Chromium and waits for JavaScript to finish, so single-page apps and dynamic sites render fully. Strips menus, footers and cookie banners, and returns clean text. PDFs work too. |

The model decides how deep to go: search snippets first, and full pages only when the snippets aren't enough. It can go back and forth between the two tools as a task needs.

## Setup

Add this to your Claude config (`claude_desktop_config.json`) under `mcpServers`, replacing `<PATH-TO-REPO>` with where you cloned this repo. Then fully quit and reopen Claude:

```json
"unified-research-engine": {
  "command": "uv",
  "args": ["run", "--directory", "<PATH-TO-REPO>\\mcp-servers\\unified-research-mcp", "python", "main.py"]
}
```

On first start it installs its Python packages and downloads its own Chromium (about 150 MB, once).

## How SearXNG runs

- SearXNG is bundled as a prebuilt package in `vendor/`, pinned to version **2026.10.30+1cd13d9**. It never updates by itself.
- It isn't running until the first search. Then it starts in a few seconds on `127.0.0.1:8888`, reachable only from your own machine.
- It stops automatically when the MCP server exits, even if it's force-closed.
- SearXNG's own code is unchanged. `searxng/run_searxng.py` adds a small stand-in for one Unix-only module so it also runs on Windows.

## Files

```
unified-research-mcp/
├── main.py                  # MCP server (the two tools)
├── config.json              # port, timeouts, text limits
├── pyproject.toml, uv.lock  # pinned dependencies
├── vendor/                  # pinned SearXNG package
├── modules/
│   ├── searx_engine.py      # starts SearXNG on demand, queries it
│   └── page_scraper.py      # Playwright page reader + PDF text
└── searxng/
    ├── run_searxng.py       # launches SearXNG (no Docker)
    └── settings.yml         # JSON output on, rate limiter off
```

## Troubleshooting

- **Port 8888 already in use**: change `searxng_port` in `config.json`.
- **Search errors**: check `searxng/searxng.log`, which is rewritten on each start.
- **Use less context**: lower `scrape_max_chars` in `config.json`, or pass a smaller `max_chars`.
