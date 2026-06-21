# AWM AI Utils

Financial analysis toolkit with two independent modules — an MCP-based stock query chatbot (Alpha Vantage) and a Bloomberg-style terminal dashboard (Yahoo Finance).

## Modules

| Module | Directory | Interface | Data Source | Runtime |
|---|---|---|---|---|
| Alpha Vantage MCP | `alpha-vantage/` | Gradio ChatInterface | Alpha Vantage MCP server (Streamable HTTP) | `asyncio` |
| Yahoo Finance Dashboard | `yahoo-finance-wrap/` | Streamlit web app | Yahoo Finance API (`yfinance`) | Synchronous |

The modules share no dependencies and can be deployed independently.

## Quick Start

### Alpha Vantage MCP Integration

```bash
cd alpha-vantage
pip install -r requirements.txt
python hello-alpha-python-gradio.py
```

Requires `.vscode/mcp.json` with the Alpha Vantage server endpoint. See [alpha-vantage/README.md](alpha-vantage/README.md) for configuration details.

### Yahoo Finance Dashboard

```bash
cd yahoo-finance-wrap
pip install -r requirements.txt
streamlit run yf.py
```

Auto-creates `tickers_config.json` with defaults if missing. See [yahoo-finance-wrap/README.md](yahoo-finance-wrap/README.md) for customization.

## Key Design Decisions

### MCP Meta-Tool Architecture

The Alpha Vantage MCP server exposes a meta-tool interface (`TOOL_LIST` / `TOOL_GET` / `TOOL_CALL`) rather than individual tool endpoints. Stock quotes are retrieved by calling `TOOL_CALL` with `tool_name="GLOBAL_QUOTE"` and the inner arguments passed as a **JSON-encoded string** (the server schema defines `arguments` as `type: string`). The original implementation used a non-existent `get_stock_quote` tool, which caused HTTP 404 responses interpreted as transport failures.

### ExceptionGroup Recursive Unwrapping

The MCP streamable-HTTP transport wraps errors in nested `ExceptionGroup` instances (e.g. `ExceptionGroup(ExceptionGroup(McpError))`). The `_unwrap_exceptions()` function performs BFS traversal with cycle detection to surface the actionable leaf cause instead of the opaque "unhandled errors in a TaskGroup" wrapper message.

### Lower-Bound Version Pins

Dependencies use `>=` lower-bound pins rather than exact versions (`pandas>=2.0.0`, not `pandas==3.0.3`). Original exact pins referenced non-existent PyPI versions, causing install failures.

### Reverse-Scan Ticker Extraction

`extract_ticker()` scans candidate words in **reverse order** through a stop-word filter, because stock tickers typically appear at the end of user queries ("Show me the price of AAPL"). The 1–5 character range matches NYSE/NASDAQ constraints.

## Testing

```bash
# Alpha Vantage (21 tests, no gradio/mcp installation required)
cd alpha-vantage && pytest test_hello_alpha.py -v

# Yahoo Finance (30 tests, network calls mocked)
cd yahoo-finance-wrap && pytest test_yf.py -v

# Full suite
pytest alpha-vantage/test_hello_alpha.py yahoo-finance-wrap/test_yf.py -v
```

Expected: **51 passed** (21 + 30)

## Documentation

- **[techspec.md](techspec.md)** — Full technical specification: design decisions, protocol stack, error propagation chains, chart layering architecture, test architecture, and known limitations.
- **[alpha-vantage/README.md](alpha-vantage/README.md)** — Alpha Vantage module implementation details: MCP session lifecycle, meta-tool invocation, exception unwrapping, debug instrumentation.
- **[yahoo-finance-wrap/README.md](yahoo-finance-wrap/README.md)** — Yahoo Finance module implementation details: MultiIndex branching, technical indicator formulas, Altair chart composition, CSS theme injection.

## Project Structure

```
awm-ai-utils/
├── README.md                              # This file
├── techspec.md                            # Technical specification
├── LICENSE
├── .vscode/mcp.json                       # Root MCP config
│
├── alpha-vantage/
│   ├── README.md
│   ├── hello-alpha-python-gradio.py       # Main app (252 lines)
│   ├── test_hello_alpha.py                # 21 tests (382 lines)
│   ├── requirements.txt
│   ├── .env                               # Optional debug flag
│   └── .vscode/mcp.json                   # MCP server endpoint + API key
│
└── yahoo-finance-wrap/
    ├── README.md
    ├── yf.py                              # Main app (705 lines)
    ├── test_yf.py                         # 30 tests (446 lines)
    ├── requirements.txt
    └── tickers_config.json                # Watchlist
```

## Dependencies

### Alpha Vantage

| Package | Purpose |
|---|---|
| `gradio` | Chat interface framework |
| `mcp` | MCP client library (streamable HTTP transport) |
| `python-dotenv` | `.env` file loading |
| `pytest>=7.0.0` | Test runner |
| `pytest-asyncio>=0.21.0` | Async test support (strict mode) |

Note: `gradio` and `mcp` are **not** required at test time — the test suite injects module stubs.

### Yahoo Finance

| Package | Purpose |
|---|---|
| `streamlit>=1.30.0` | Web application framework |
| `yfinance>=1.4.0` | Yahoo Finance API wrapper |
| `altair>=5.0.0` | Declarative chart visualization |
| `pandas>=2.0.0` | Data manipulation and analysis |

## Configuration

### Alpha Vantage — `.vscode/mcp.json`

```json
{
  "servers": {
    "alphavantage": {
      "type": "http",
      "url": "https://mcp.alphavantage.co/mcp?apikey={YOUR_API_KEY}"
    }
  }
}
```

The `type` field must be `"http"`. The URL is cached globally after first load. Free API keys are limited to 25 requests/day.

### Yahoo Finance — `tickers_config.json`

```json
{
  "tickers": ["MSFT", "AAPL", "GOOG", "NVDA", "TSLA"]
}
```

Auto-created with `["MSFT", "AAPL", "GOOG"]` defaults if the file is missing or contains invalid JSON.

## Known Limitations

| ID | Module | Limitation |
|---|---|---|
| L1 | Alpha Vantage | Free API key: 25 requests/day — no programmatic throttling |
| L2 | Alpha Vantage | Ticker stop-words filter out real tickers (`NOW`, `INFO`) |
| L3 | Alpha Vantage | Transient sessions — no connection pooling |
| L4 | Yahoo Finance | No real-time streaming; data downloaded once per page load |
| L5 | Yahoo Finance | RSI uses simple moving average instead of Wilder's EMA smoothing |
| L7 | Both | No authentication or multi-user support |

Full limitation analysis and mitigations in [techspec.md §5.4](techspec.md#54-known-limitations).
