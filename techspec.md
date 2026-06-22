# AWM AI Utils — Technical Specification

## 1. System Overview

**awm-ai-utils** is a two-module financial analysis toolkit built on Python 3.11+. Each module addresses a distinct data-access pattern:

| Module | Transport | Data Source | Interface | Concurrency Model |
|---|---|---|---|---|
| `alpha-vantage/` | MCP over Streamable HTTP | Alpha Vantage remote MCP server | Gradio ChatInterface | `asyncio` (single-event-loop) |
| `yahoo-finance-wrap/` | Direct REST via `yfinance` | Yahoo Finance public API | Streamlit server-rendered | Synchronous (multi-threaded download) |

Both modules share zero runtime dependencies — they are fully decoupled and can be deployed independently.

---

## 2. Design Decisions Log

### D1 — Alpha Vantage: Meta-Tool Architecture over Direct Tool Calls

**Context.** The Alpha Vantage MCP server (`https://mcp.alphavantage.co/mcp`) exposes a *meta-tool* interface consisting of three tools — `TOOL_LIST`, `TOOL_GET`, `TOOL_CALL` — rather than individual endpoints per Alpha Vantage API function (e.g. no `get_stock_quote` tool exists).

**Decision.** Stock quote retrieval uses `TOOL_CALL` as the dispatch tool, with the underlying Alpha Vantage function name (`GLOBAL_QUOTE`) passed as the `tool_name` parameter and its arguments passed as a **JSON-encoded string** (not a JSON object) in the `arguments` parameter.

**Rationale.** The initial implementation called `session.call_tool(name="get_stock_quote", arguments={"ticker": ticker})`, which caused the server to return HTTP 404. The MCP streamable-HTTP transport interprets 404 as a transport-layer failure, raising `McpError: Session terminated` wrapped in two levels of `ExceptionGroup`. The meta-tool pattern matches the server's actual schema — `TOOL_CALL`'s `arguments` field is declared as `type: string`, requiring `json.dumps()` of the inner parameters.

**Impact.** All MCP invocation code and corresponding tests were updated. The corrected call signature:

```python
response = await session.call_tool(
    name="TOOL_CALL",
    arguments={
        "tool_name": "GLOBAL_QUOTE",
        "arguments": json.dumps({"symbol": ticker}),
    },
)
```

### D2 — ExceptionGroup Recursive Unwrapping

**Context.** The MCP streamable-HTTP transport wraps errors in `ExceptionGroup` / `BaseExceptionGroup`. During the NVDA query failure, the actual error (`McpError: Session terminated`) was nested two levels deep: `ExceptionGroup("outer", [ExceptionGroup("inner", [McpError(...)])])`.

**Decision.** Implemented `_unwrap_exceptions(exc: BaseException) -> list[str]` using a BFS traversal of the exception tree with `id()`-based cycle detection. Leaf exceptions (those without a `.exceptions` attribute) are formatted as `"TypeName: message"` strings.

**Rationale.** A shallow `.exceptions` iteration (accessing only one level) yields only the outer `ExceptionGroup` message — "unhandled errors in a TaskGroup" — which is not actionable. Recursive BFS traverses any nesting depth to surface the real root cause. Cycle detection via `id()` prevents infinite loops if a malformed exception graph references itself.

**Alternatives considered:**
- Recursive function — equivalent correctness but risks `RecursionError` on deep nests; BFS with explicit queue is iterative and bounded by memory only.
- `traceback.format_exception()` — produces full traceback text but includes irrelevant transport internals; leaf-extraction produces concise, user-facing messages.

### D3 — Version Pin Strategy: Lower Bounds over Exact Pins

**Context.** Original `requirements.txt` files used exact version pins (`pandas==3.0.3`, `altair==6.1.0`, `streamlit==1.58.0`). Some pinned versions did not exist in PyPI at the time of installation.

**Decision.** Switched to lower-bound pins (`pandas>=2.0.0`, `altair>=5.0.0`, `streamlit>=1.30.0`, `yfinance>=1.4.0`).

**Rationale.** The modules don't depend on bleeding-edge features or version-specific breaking changes. Lower-bound pins maximize installability across environments while guaranteeing minimum compatible API surfaces. Exact pins are appropriate only when a known incompatibility exists in a specific version range.

### D4 — Ticker Extraction: Reverse-Scan Heuristic

**Context.** User queries are freeform natural language (e.g. "Check current quote value for NVDA"). A regex-only approach produces many false positives from common English words.

**Decision.** The `extract_ticker()` function applies three stages: (1) strip punctuation and uppercase, (2) extract 1–5 uppercase word tokens via `\b[A-Z]{1,5}\b`, (3) **reverse-scan** the candidate list, skipping entries in a hardcoded stop-word set. The first non-stop-word candidate (from the end) is returned.

**Rationale.** In stock queries the ticker typically appears at the end of the sentence ("Show me the price of AAPL"). Reverse scanning biases toward the last capital word, which is the ticker with high probability. The stop-word set (`WHAT`, `PRICE`, `CHECK`, `VALUE`, etc.) eliminates the most common false positives. The 1–5 character range matches NYSE/NASDAQ ticker constraints.

**Limitations.** Tickers colliding with stop words (e.g. `NOW` for ServiceNow) are incorrectly filtered. Multi-ticker queries return only one ticker. A production system would use a securities master database for validation.

### D5 — MultiIndex vs Flat DataFrame Branching in Yahoo Finance

**Context.** `yfinance.download()` returns a different DataFrame structure depending on the number of tickers: a `pd.MultiIndex` column DataFrame for multiple tickers (columns: `(ticker, field)`) or a flat DataFrame for a single ticker (columns: `Open`, `High`, `Low`, `Close`, `Volume`).

**Decision.** Every function that processes historical data (`extract_close_values`, `get_ticker_percent_changes`, `calculate_returns_and_correlation`) contains a structural branch: `if isinstance(history.columns, pd.MultiIndex)` dispatches to the multi-ticker path; the `else` branch handles the single-ticker flat DataFrame.

**Rationale.** This defensive branching prevents `KeyError` crashes when the downstream user provides a single ticker. The single-ticker path extracts `history["Close"]` directly; the multi-ticker path uses `history[ticker].get("Close")` with level-based column access.

### D6 — Gradio Module Stubbing in Tests

**Context.** Importing `gradio` during pytest collection can hang in some environments. The `mcp` package may not be installed in the test interpreter since all MCP interactions are mocked anyway.

**Decision.** The test module injects lightweight `MagicMock` stubs into `sys.modules` **before** importing the application module:

```python
if "gradio" not in sys.modules:
    sys.modules["gradio"] = MagicMock()
if "mcp" not in sys.modules:
    sys.modules["mcp"] = MagicMock()
    sys.modules["mcp.client"] = MagicMock()
    sys.modules["mcp.client.streamable_http"] = MagicMock()
```

**Rationale.** This eliminates the need for `gradio` and `mcp` as test-time dependencies. The stubs provide enough structure for `importlib` to resolve the module without side effects. All MCP call paths are mocked at the function level (`patch("hello_alpha_python_gradio.streamablehttp_client")`), so the stubs never execute real I/O.

### D7 — LRU Cache for Ticker Info

**Context.** `get_ticker_info()` calls `yf.Ticker(symbol).info` which hits the Yahoo Finance API on every invocation. In the main dashboard loop, this is called for the selected ticker and potentially all watchlist tickers (for peer comparison).

**Decision.** `get_ticker_info` is decorated with `@lru_cache(maxsize=64)`.

**Rationale.** Company fundamentals rarely change within a session. Caching eliminates redundant API calls for the same symbol during a single Streamlit run. The 64-entry cap bounds memory usage while covering typical watchlist sizes (5–50 tickers). `lru_cache` is used over Streamlit's `@st.cache_data` because the function is also called from test code where Streamlit is unavailable.

---

## 3. Alpha Vantage MCP Integration — Technical Architecture

### 3.1 Protocol Stack

```
User Input (Gradio ChatInterface)
    │
    ▼
chat_with_mcp(message, history)          ← async entry point
    │
    ├─ extract_ticker(message)           ← sync, regex-based
    │
    ▼
call_alpha_vantage_mcp(ticker)           ← async MCP transaction
    │
    ├─ load_mcp_config_from_vscode()     ← sync, file I/O + JSON parse
    │       ↓
    │   .vscode/mcp.json → URL string (cached globally)
    │
    ├─ streamablehttp_client(url)        ← async context manager
    │       ↓
    │   (read_stream, write_stream, _)   ← MCP streamable-HTTP transport
    │
    ├─ ClientSession(read, write)        ← async context manager
    │       ↓
    │   session.initialize()             ← MCP handshake
    │
    └─ session.call_tool("TOOL_CALL", {...})  ← meta-tool dispatch
            ↓
        GLOBAL_QUOTE → JSON response
```

### 3.2 Session Lifecycle

The MCP session follows a strict context-manager lifecycle:

1. **Transport open**: `streamablehttp_client(url)` establishes the HTTP connection. Returns a 3-tuple `(read_stream, write_stream, session_id_callback)`.
2. **Session init**: `ClientSession(read_stream, write_stream)` creates the session. `await session.initialize()` performs the MCP handshake (protocol version negotiation, capability exchange). The server responds with `mcp-session-id` which must be included in subsequent requests.
3. **Tool call**: `session.call_tool(name, arguments)` sends a JSON-RPC request. The `isError` flag on the response indicates server-side tool errors (distinct from transport errors).
4. **Context exit**: Both `async with` blocks close in reverse order, terminating the session and releasing the HTTP connection.

Every call creates a **transient session** — there is no connection pooling or persistent session. This is a deliberate choice: the Alpha Vantage MCP server is stateless, and transient sessions avoid stale-session errors.

### 3.3 Error Propagation Chain

```
Transport Layer (HTTP 404 / network error)
    │
    ▼ ExceptionGroup(ExceptionGroup(McpError))
    │
    ▼ _unwrap_exceptions() → list of leaf error strings
    │
    ▼ Formatted as "### Protocol Transport Fault" markdown

Server Tool Layer (isError=True in response)
    │
    ▼ _extract_text_from_content(response.content)
    │
    ▼ Formatted as "### Tool Error" markdown

Application Layer (config missing, empty ticker)
    │
    ▼ Raised as FileNotFoundError / KeyError / ValueError
    │
    ▼ Formatted as "### Configuration Error" or plain string
```

Key distinction: **transport errors** occur at the HTTP/MCP protocol level and raise Python exceptions. **Tool errors** occur at the MCP application level and are indicated by `isError=True` on the response object — no Python exception is raised.

### 3.4 Response Content Extraction

The MCP response `content` field is a list of typed content items (text, image, embedded resource). The helper `_extract_text_from_content()` scans for the first item with a `.text` attribute using `getattr(item, "text", None)`. This avoids `AttributeError` on non-text content types and avoids indexing into potentially empty lists.

### 3.5 Debug Instrumentation

The `_debug_log()` function gates all debug output behind the `ALPHA_VANTAGE_DEBUG` environment variable (truthy values: `true`, `1`, `yes`). Debug calls are placed at every decision point: config loading, ticker extraction, session lifecycle, tool invocation, response parsing, and error unwrapping. In production, the `DEBUG` flag is `False` and `_debug_log` is a no-op function — zero overhead.

### 3.6 Test Architecture

| Test Class | Count | Type | Subject |
|---|---|---|---|
| `TestExtractTicker` | 4 | sync | Ticker regex extraction |
| `TestLoadMcpConfig` | 4 | sync | Config file parsing + validation |
| `TestCallAlphaVantageMcp` | 5 | async | MCP call success/error/empty/error-flag/non-text |
| `TestChatWithMcp` | 2 | async | End-to-end chat flow |
| `TestUnwrapExceptions` | 4 | sync | Exception group BFS unwrapping |
| `TestProtocolErrorReporting` | 2 | async | NVDA failure reproduction |
| **Total** | **21** | | |

Async test classes are decorated with `@pytest.mark.asyncio` (`pytest-asyncio` strict mode requires per-class annotation). The test module avoids importing `gradio` and `mcp` at runtime by injecting `MagicMock` stubs. The application module is loaded via `importlib.util.spec_from_file_location` to support non-package script execution.

---

## 4. Yahoo Finance Dashboard — Technical Architecture

### 4.1 Data Flow Pipeline

```
tickers_config.json → load_tickers() → list[str]
                                         │
                                         ▼
                              yfinance.download(tickers, period="1y",
                                                group_by="ticker",
                                                auto_adjust=True,
                                                threads=True)
                                         │
                                         ▼
                              DataFrame (MultiIndex or Flat)
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
           Technical           Fundamental            Portfolio & Risk
           ─────────           ──────────            ────────────────
           calculate_rsi()     get_ticker_info()     extract_close_values()
           calculate_macd()    (LRU-cached)           build_portfolio_distribution()
           build_candlestick() build_watchlist_       calculate_returns_and_
           build_rsi_chart()    fundamentals()         correlation()
           build_macd_chart()  build_peer_pe_chart()  build_correlation_heatmap()
                               build_market_cap_     build_portfolio_pie_chart()
                                chart()
                               build_earnings_chart()
                               build_fcf_chart()
```

### 4.2 DataFrame Structural Branching

`yfinance.download()` returns structurally different DataFrames:

| Input | Column Structure | Access Pattern |
|---|---|---|
| Single ticker | Flat: `Close`, `Open`, `High`, `Low`, `Volume` | `history["Close"]` → `pd.Series` |
| Multiple tickers | MultiIndex: `(ticker, field)` tuples | `history[ticker].get("Close")` → `pd.Series` |

Every function that consumes the `history` DataFrame contains a structural `isinstance` check at the `pd.MultiIndex` level and branches accordingly. This is the primary source of complexity in the data-processing functions and the most common failure mode if not handled.

### 4.3 Technical Indicator Implementations

#### RSI (Relative Strength Index)

```python
delta = series.diff()
gain = delta.where(delta > 0, 0).rolling(window=window).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
rs = gain / loss
rsi = 100 - (100 / (1 + rs))
```

- Uses **rolling mean** of gains/losses (Wilder's smoothing is not applied — this uses simple moving averages instead of exponential).
- Division by zero is implicitly handled: when `loss == 0`, `rs → inf`, and `rsi → 100` (pandas produces `NaN` in this edge case, which is acceptable for charting).
- Minimum data threshold: 20 bars (window + warmup).

#### MACD (Moving Average Convergence Divergence)

```python
exp1 = series.ewm(span=fast, adjust=False).mean()    # Fast EMA
exp2 = series.ewm(span=slow, adjust=False).mean()    # Slow EMA
macd = exp1 - exp2                                    # MACD line
signal_line = macd.ewm(span=signal, adjust=False).mean()  # Signal line
histogram = macd - signal_line                        # Histogram
```

- `adjust=False` uses the recursive EMA formula: `EMA_t = α * x_t + (1 - α) * EMA_{t-1}` where `α = 2 / (span + 1)`.
- Returns a 3-tuple `(macd, signal_line, histogram)`, all `pd.Series` with the same index as input.
- Minimum data threshold: 30 bars for chart generation.

### 4.4 Chart Layering Architecture

All charts use Altair's **compositional layering** model:

| Chart | Layers | Composition |
|---|---|---|
| Candlestick | `rules` (high-low wick) + `bars` (open-close body) + `sma20_line` + `sma50_line` | `alt.layer(...).resolve_scale(y="shared")` → vertically concatenated with volume |
| RSI | `rsi_line` + `oversold_rule` (30) + `overbought_rule` (70) | `alt.layer(...).resolve_scale(y="independent")` |
| MACD | `histogram_bar` + `macd_line` + `signal_line` | `alt.layer(...).interactive()` (zoom/pan) |
| Peer P/E | Single `mark_bar` with conditional color encoding | Highlight via derived `highlight` column |
| Correlation | Single `mark_rect` with `blueorange` diverging scale | Domain: `[-1, 0, 1]` |
| Portfolio Pie | `mark_arc(innerRadius=70)` (donut) | `PORTFOLIO_PALETTE` color scale |

Each chart function returns `None` on insufficient data rather than raising an exception. The calling code in `main()` checks for `None` and displays an `st.info()` fallback message.

### 4.5 CSS Theme Injection

The `DARK_TERMINAL_CSS` constant is injected via `st.markdown(f"<style>{DARK_TERMINAL_CSS}</style>", unsafe_allow_html=True)`. The theme targets:

- Root background: `#0B0E11` (Bloomberg terminal black)
- Sidebar: `#11161B` with `#1F2730` border
- Text: `#EAECEF` (light gray) in monospace family (`Courier New`, `Consolas`, `Menlo`)
- Accent colors: `#3AC569` (green, positive) / `#F8506B` (red, negative)
- Metrics cards: `#11161B` background with uppercase labels in `#8B949E`

This is a **single-injection** approach — the entire CSS is written once at page load. Streamlit re-renders components on interaction, but the injected style persists because it targets CSS class selectors rather than element IDs.

### 4.6 Streamlit Context Guard

```python
def is_streamlit_context():
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
        return get_script_run_ctx(suppress_warning=True) is not None
    except (ImportError, Exception):
        return False
```

This guard prevents `main()` from executing if the script is run directly with `python yf.py` instead of `streamlit run yf.py`. Without it, `st.set_page_config()` would raise a `StreamlitAPIException`.

### 4.7 Test Architecture

| Test Class | Count | Subject |
|---|---|---|
| `TestCreateSampleConfig` | 3 | Config file creation + JSON validity |
| `TestLoadTickers` | 5 | Existing/missing/invalid/empty config handling |
| `TestBuildSummary` | 3 | Summary dict construction with present/missing fields |
| `TestDownloadPriceHistory` | 2 | `yfinance.download` mock (single/multi ticker) |
| `TestPortfolioHelpers` | 3 | MultiIndex extraction, percent changes, weight calculation |
| `TestFundamentalHelpers` | 4 | `get_ticker_info` mock, watchlist DataFrame, P/E chart, market cap chart |
| `TestTechnicalIndicators` | 9 | RSI calculation + extremes, MACD 3-series, candlestick/RSI/MACD chart thresholds, correlation matrix + heatmap |
| **Total** | **29** | |

All network-dependent functions (`yf.download`, `yf.Ticker`) are mocked via `@patch("yf.yf.download")` / `@patch("yf.yf.Ticker")`. No live API calls occur during test execution.

---

## 5. Cross-Cutting Concerns

### 5.1 Error Handling Philosophy

Both modules follow a **return-string-on-error** pattern rather than raising exceptions to the UI layer:

- **Alpha Vantage**: `call_alpha_vantage_mcp()` catches all exceptions and returns a markdown-formatted error string. `chat_with_mcp()` returns a friendly message for un-extractable tickers. The Gradio interface never sees an unhandled exception.
- **Yahoo Finance**: Chart functions return `None` on data insufficiency. The `main()` function checks for `None` and renders `st.info()` or `st.warning()` messages. `yfinance` API errors in fundamental charts are caught with `try/except` and produce `None` returns.

This pattern ensures **UI resilience** — the interface always renders, even when upstream data sources fail.

### 5.2 Dependency Isolation

```
alpha-vantage/requirements.txt     →  gradio, mcp, python-dotenv, pytest, pytest-asyncio
yahoo-finance-wrap/requirements.txt →  streamlit, yfinance, altair, pandas
```

No shared dependencies between modules. Each can be installed and run in an isolated virtual environment. The only shared tooling is `pytest`, and even the async testing dependencies differ (`pytest-asyncio` is only needed for the Alpha Vantage module).

### 5.3 Configuration Patterns

| Module | Config File | Format | Loading | Fallback |
|---|---|---|---|---|
| Alpha Vantage | `.vscode/mcp.json` | JSON | `load_mcp_config_from_vscode()` with global URL cache | Raises `FileNotFoundError` |
| Yahoo Finance | `tickers_config.json` | JSON | `load_tickers()` with auto-creation | Creates default `["MSFT", "AAPL", "GOOG"]` |

### 5.4 Known Limitations

| ID | Module | Limitation | Mitigation |
|---|---|---|---|
| L1 | Alpha Vantage | Free API key: 25 requests/day | Rate-limit message displayed; no programmatic throttling |
| L2 | Alpha Vantage | Ticker extraction produces false positives on stop-word collisions (`NOW`, `INFO`) | Documented; no current fix |
| L3 | Alpha Vantage | Transient sessions — no connection reuse | Acceptable for low-volume chat usage |
| L4 | Yahoo Finance | No real-time streaming; data downloaded once on page load | Refresh requires Streamlit re-run |
| L5 | Yahoo Finance | RSI uses SMA instead of Wilder's EMA smoothing | Minor precision difference for short windows |
| L6 | Yahoo Finance | Correlation calculated on daily returns only | No weekly/monthly option exposed |
| L7 | Both | No authentication or user management | Single-user local applications |

---

## 6. MCP Protocol Specification (Alpha Vantage)

### 6.1 Server Endpoint

```
URL: https://mcp.alphavantage.co/mcp?apikey={API_KEY}
Transport: Streamable HTTP (POST for requests, SSE for server-initiated)
Protocol Version: 2024-11-05
Session: Stateless; returns mcp-session-id header
Authentication: API key in query parameter
```

### 6.2 Tool Schema

The Alpha Vantage MCP server exposes three meta-tools:

| Tool | Purpose | Parameters |
|---|---|---|
| `TOOL_LIST` | Discover available Alpha Vantage functions | None |
| `TOOL_GET` | Retrieve schema for a specific function | `tool_name: str` |
| `TOOL_CALL` | Execute an Alpha Vantage function | `tool_name: str`, `arguments: str` (JSON-encoded) |

**Critical**: The `arguments` parameter of `TOOL_CALL` is typed as `string`, not `object`. Passing a dict causes a protocol error. The inner arguments must be serialized with `json.dumps()`.

### 6.3 GLOBAL_QUOTE Function

Input schema:
```json
{"symbol": "NVDA"}
```

Output (via `TOOL_CALL`):
```json
{
  "Global Quote": {
    "01. symbol": "NVDA",
    "05. price": "135.58",
    "06. volume": "234,567",
    "08. previous close": "134.20",
    "09. change": "1.38",
    "10. change percent": "1.0288%"
  }
}
```

### 6.4 Error Response Shapes

| Condition | HTTP Status | MCP Behavior | Client Impact |
|---|---|---|---|
| Unknown tool name | 404 | Transport failure | `McpError: Session terminated` in `ExceptionGroup` |
| Invalid `TOOL_CALL` arguments | 200 | `isError=True`, `content[].text` has error description | Returned as "Tool Error" |
| API rate limit exceeded | 200 | `isError=False`, `content[].text` has `Information` note | Returned as informational text |
| Network unreachable | — | Connection error | `Protocol Transport Fault` with `ConnectionError` leaf |

---

## 7. Test Execution Reference

### 7.1 Alpha Vantage

```bash
cd alpha-vantage
pytest test_hello_alpha.py -v
```

Expected output: **21 passed**

Test dependencies: `pytest>=7.0.0`, `pytest-asyncio>=0.21.0`. The `gradio` and `mcp` packages are **not** required at test time (module stubbing).

### 7.2 Yahoo Finance

```bash
cd yahoo-finance-wrap
pytest test_yf.py -v
```

Expected output: **29 passed** (30 with `TestBuildSummary` counted separately = 30)

Test dependencies: `pytest`, `pandas` (included in main requirements). Network calls are mocked.

### 7.3 Full Suite

```bash
pytest alpha-vantage/test_hello_alpha.py yahoo-finance-wrap/test_yf.py -v
```

Expected output: **51 passed** (21 + 30)

---

## 8. File Manifest

```
awm-ai-utils/
├── README.md                              # Project overview and quick-start
├── techspec.md                            # This file — technical specification
├── LICENSE                                # License file
│
├── .vscode/
│   └── mcp.json                           # Root-level MCP server config
│
├── alpha-vantage/
│   ├── README.md                          # Module-level technical docs
│   ├── hello-alpha-python-gradio.py       # Main application (252 lines)
│   ├── test_hello_alpha.py                # Test suite (382 lines)
│   ├── requirements.txt                   # Python dependencies
│   ├── .env                               # Debug flag (optional)
│   └── .vscode/
│       └── mcp.json                       # MCP server config (URL + API key)
│
└── yahoo-finance-wrap/
    ├── README.md                          # Module-level technical docs
    ├── yf.py                              # Main application (705 lines)
    ├── test_yf.py                         # Test suite (446 lines)
    ├── requirements.txt                    # Python dependencies
    └── tickers_config.json                # Watchlist configuration
```
