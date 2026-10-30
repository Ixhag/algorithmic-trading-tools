# Algorithmic Trading Tools

A toolkit for market research, analysis and trading. Each tool lives in its own folder.

| Folder | What it is |
|---|---|
| [`mcp-servers/`](mcp-servers/) | Local MCP servers that give Claude market data, SEC filings, options analysis, brokerage access and web research |

<details open>
<summary><h2>MCP server stack</h2></summary>

| Server | Folder | Source | What Claude uses it for |
|---|---|---|---|
| **sec-edgar-mcp** | `mcp-servers/sec-edgar-mcp` | [stefanoamorelli/sec-edgar-mcp](https://github.com/stefanoamorelli/sec-edgar-mcp) (linked) | Company financials, 10-K/10-Q/8-K filings, insider trades |
| **tradingview-mcp-analytics** | `mcp-servers/tradingview-mcp` | [atilaahmettaner/tradingview-mcp](https://github.com/atilaahmettaner/tradingview-mcp) (linked) | Prices, technicals, screeners, backtests, options chains, market news |
| **mcp-optionsflow** | `mcp-servers/mcp-optionsflow` | [twolven/mcp-optionsflow](https://github.com/twolven/mcp-optionsflow) (linked) | Options strategy analysis (credit spreads, cash-secured puts, covered calls) |
| **ibkr-canada-execution** | `mcp-servers/ibkr-mcp-server` | [arjundivecha/ibkr-mcp-server](https://github.com/arjundivecha/ibkr-mcp-server) (linked) | Interactive Brokers account, portfolio, margin, short availability |
| **unified-research-engine** | `mcp-servers/unified-research-mcp` | This repo | Web research: SearXNG meta-search plus a headless-browser page reader. No Docker, no API keys |

"Linked" folders are [git submodules](https://git-scm.com/book/en/v2/Git-Tools-Submodules): they point to the original project at a pinned version instead of copying it. All configuration lives in the Claude config, so none of their code is modified.

</details>

## Installation

Requires [git](https://git-scm.com/), [uv](https://docs.astral.sh/uv/) and the Claude desktop app.

1. Clone the repo into any folder you like. `--recurse-submodules` also downloads the linked servers:
   ```
   git clone --recurse-submodules https://github.com/Ixhag/algorithmic-trading-tools.git
   ```
2. Open [`mcp-servers/claude_desktop_config.example.json`](mcp-servers/claude_desktop_config.example.json) and replace every `<PATH-TO-REPO>` with the full path of the folder you cloned into. On macOS or Linux, also change the `\\` separators to `/`.
3. Fill in your own values:
   - `MARKETAUX_API_TOKEN` (optional): a token from [marketaux.com](https://www.marketaux.com/), for TradingView market news
   - `SEC_EDGAR_USER_AGENT`: your name and email, which the SEC requires for API access
   - The IBKR settings, explained at the top of the file
4. Merge the `mcpServers` section into Claude's config file, keeping any settings already in it:
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
5. Fully quit and reopen Claude. On first start, each server installs its own packages, which takes a few minutes.

For IBKR, Trader Workstation (TWS) or IB Gateway must be running with the API turned on.

API keys and account details belong only in your Claude config, never in this repo. The `.gitignore` keeps out Python environments, logs, `.env` files and `claude_desktop_config.json`.
