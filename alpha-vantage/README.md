# Alpha Vantage MCP Integration — Technical Implementation

Gradio-based chat interface that queries stock quotes through the Model Context Protocol (MCP) over a Streamable HTTP transport to an Alpha Vantage backend, with optional x.ai (Grok) social media sentiment analysis integration.

## Module Architecture

```
User message + use_grok flag (checkbox)
    │
    ▼
chat_with_mcp(message, history, use_grok=False)  ← async entry (Gradio hook)
    │
    ├─ extract_ticker(message)                    ← sync regex extraction
    │      │
    │      ├─ re.sub(r'[^\w\s]', '', message).upper()
    │      ├─ re.findall(r'\b[A-Z]{1,5}\b', cleaned)
    │      └─ reversed scan with stop-word filter → ticker or None
    │
    ▼
call_alpha_vantage_mcp(ticker)                    ← async MCP transaction
    │
    ├─ load_mcp_config_from_vscode()              ← sync file I/O
    │      ↓ .vscode/mcp.json → URL (cached globally)
    │
    ├─ streamablehttp_client(url)                 ← async context manager
    │      ↓ (read_stream, write_stream, _)
    │
    ├─ ClientSession(read, write)                 ← async context manager
    │      ↓ session.initialize()
    │
    └─ session.call_tool("TOOL_CALL", {            ← meta-tool dispatch
           "tool_name": "GLOBAL_QUOTE",
           "arguments": json.dumps({"symbol": ticker})
       })
           ↓
       MCP response → _extract_text_from_content() → quote_text
           ↓
       analyze_with_openai(quote_text, ticker)     ← OpenAI sentiment analysis
           ↓
       (if use_grok && openai_status != AI_STATUS_NO_KEY)
           analyze_with_grok(quote_text, ticker)    ← xAI Grok social sentiment
           ↓
       _merge_results(openai_parsed, grok_parsed) ← 50/50 blend of sentiment
           ↓
       render_analysis_markdown()                  ← includes social themes
       render_chartjs_html()                       ← blended sentiment visualization
```

## MCP Session Lifecycle

Each stock query creates a **transient session** — there is no connection pooling or persistent session reuse. The lifecycle:

1. **Transport open** — `streamablehttp_client(url)` establishes the HTTP connection. Returns `(read_stream, write_stream, session_id_callback)`.
2. **Session init** — `ClientSession(read_stream, write_stream)` wraps the streams. `await session.initialize()` performs the MCP protocol handshake (version negotiation, capability exchange). The server responds with a `mcp-session-id` header.
3. **Tool call** — `session.call_tool(name, arguments)` sends a JSON-RPC request. The `isError` flag on the response distinguishes server-side tool errors from transport-level failures.
4. **Context exit** — Both `async with` blocks close in reverse order, terminating the session and releasing the HTTP connection.

This transient approach avoids stale-session errors on the stateless Alpha Vantage server.

## Meta-Tool Invocation Pattern

The Alpha Vantage MCP server does **not** expose individual tool endpoints like `get_stock_quote`. Instead, it provides three meta-tools:

| Meta-Tool | Purpose | Parameters |
|---|---|---|
| `TOOL_LIST` | List available Alpha Vantage functions | None |
| `TOOL_GET` | Retrieve schema for a specific function | `tool_name: str` |
| `TOOL_CALL` | Execute an Alpha Vantage function | `tool_name: str`, `arguments: str` |

The invocation for a stock quote:

```python
response = await session.call_tool(
    name="TOOL_CALL",
    arguments={
        "tool_name": "GLOBAL_QUOTE",
        "arguments": json.dumps({"symbol": ticker}),
    },
)
```

**Critical**: `TOOL_CALL`'s `arguments` field is typed as `string` in the server schema, not `object`. Passing a dict causes a protocol error. The inner parameters must be serialized with `json.dumps()`.

The original implementation called `session.call_tool(name="get_stock_quote", arguments={"ticker": ticker})`, which caused the server to return HTTP 404. The streamable-HTTP transport interprets 404 as a transport failure, wrapping the resulting `McpError: Session terminated` in two levels of `ExceptionGroup`.

## xAI (Grok) Integration

### Grok Integration Architecture

When the "Use Grok social sentiment" checkbox is enabled, the system supplements OpenAI analysis with x.ai (Grok) social media sentiment:

```
[Alpha Vantage quote retrieved]
        │
        ├─ analyze_with_openai(quote, ticker)
        │      ↓
        │   OpenAI: StockAnalysis {analysis, metrics, sentiment}
        │
        └─ (if use_grok enabled)
               analyze_with_grok(quote, ticker)
                      ↓
                   xAI: {social_sources, sentiment, volume_bias}
                      ↓
               _merge_results(openai, grok)
                      ↓
               _blend_scores(openai_sent, grok_sent)
                      ↓
               Final: {analysis, metrics, sentiment, social_sources, volume_bias}
```

### xAI API Integration

The xAI integration uses a dedicated API client with the following characteristics:

| Property | Value |
|---|---|
| Endpoint | `https://api.x.ai/v1/chat/completions` |
| Model | `grok-4.3` (configurable via `XAI_MODEL` env var) |
| Auth | `Authorization: Bearer {XAI_API_KEY}` |
| Response Format | `json_object` (strict JSON output) |
| Timeout | 30 seconds |

**Request payload:**
```python
{
  "model": "grok-4.3",
  "messages": [
    {
      "role": "system",
      "content": "You are a financial sentiment analyst trained on social media discourse..."
    },
    {"role": "user", "content": f"Ticker: {ticker}\nContext:\n{quote_text[:400]}"}
  ],
  "temperature": 0.3,
  "response_format": {"type": "json_object"}
}
```

**Response structure:**
```json
{
  "social_sources": ["Reddit bullish options flow", "X/Twitter earnings optimism"],
  "sentiment": {"label": "bullish", "score": 0.73},
  "volume_bias": "high"
}
```

### Sentiment Blending Logic

When both OpenAI and Grok sentiment are available, they are blended with a 50/50 weight:

```python
def _blend_scores(openai_label, openai_score, grok_label, grok_score) -> dict:
    # Normalize labels to lowercase
    # Check agreement
    # If agreed: average the scores
    # If disagreed: apply 20% penalty, set label to "neutral", cap score at 0.5
    return {"label": final_label, "score": blended_score}
```

**Agreement penalties:**
- Labels agree → `score = 0.5 * openai + 0.5 * grok`
- Labels disagree → `score = (0.5 * openai + 0.5 * grok) * 0.8`, label = "neutral", minimum score 0.5

### Grok Fallback Behavior

| Scenario | Behavior |
|---|---|
| `use_grok=True`, `XAI_API_KEY` missing | Returns `AI_STATUS_GK_NO_KEY`, falls back to OpenAI-only with notice |
| `use_grok=True`, xAI API error | Returns `AI_STATUS_GK_ERROR`, falls back to OpenAI-only with notice |
| `use_grok=True`, `OPENAI_API_KEY` missing | Skips Grok call entirely, OpenAI analysis unavailable |
| `use_grok=False` | Grok not called, OpenAI-only analysis |

### xAI Key Fallback Mechanism

The `get_xai_api_key()` function implements a robust fallback:

1. **Primary**: `os.environ["XAI_API_KEY"]`
2. **Fallback**: Load `.env` file via `python-dotenv` with `override=False`
3. **Missing**: Returns `None`, triggers appropriate error status

Environment variable always takes precedence over `.env` file values.

## Error Propagation Chain

Errors are handled at multiple layers, with new status codes for Grok integration:

### Status Codes

| Status | Meaning | Handling |
|---|---|---|
| `AI_STATUS_OK` | All providers succeeded | Full rendering with blended sentiment |
| `AI_STATUS_NO_KEY` | `OPENAI_API_KEY` missing | Charts hidden, OpenAI unavailable notice |
| `AI_STATUS_ERROR` | OpenAI call failed | Charts hidden, error notice with debug hint |
| `AI_STATUS_GK_NO_KEY` | `XAI_API_KEY` missing | OpenAI-only with "key not configured" notice |
| `AI_STATUS_GK_ERROR` | xAI call failed | OpenAI-only with "request failed" notice |
| `AI_STATUS_DISABLED` | Grok toggle off | OpenAI-only, no notice needed |

### Transport Errors (Python exceptions)

```
HTTP 404 / network failure
    │
    ▼ ExceptionGroup(ExceptionGroup(McpError("Session terminated")))
    │
    ▼ _unwrap_exceptions() → ["McpError: Session terminated"]
    │
    ▼ "### Protocol Transport Fault\nUnable to fulfill network transaction.\n  - McpError: Session terminated"
```

### Server Tool Errors (isError=True on response)

```
response.isError == True
    │
    ▼ _extract_text_from_content(response.content)
    │
    ▼ "### Tool Error\nThe server reported an error executing the tool.\n{error_text}"
```

### Application Errors (config, validation)

```
FileNotFoundError / KeyError / ValueError
    │
    ▼ "### Configuration Error\n{message}"
```

Or for un-extractable tickers:

```
extract_ticker() → None
    │
    ▼ "I couldn't isolate a clean ticker tracking label in your input..."
```

The Gradio interface **never** receives an unhandled exception — all paths return a formatted string.

## Exception Unwrapping — `_unwrap_exceptions()`

The MCP streamable-HTTP transport wraps errors in nested `ExceptionGroup` / `BaseExceptionGroup`. A single-level `.exceptions` iteration only reveals the next wrapper, not the leaf cause. The unwrapper uses **BFS traversal** with cycle detection:

```python
def _unwrap_exceptions(exc: BaseException) -> list[str]:
    leaves = []
    queue = [exc]
    seen = set()
    while queue:
        current = queue.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        sub_excs = getattr(current, "exceptions", None)
        if sub_excs:
            queue.extend(sub_excs)
        else:
            leaves.append(f"{type(current).__name__}: {current}")
    return leaves
```

Design choices:
- **BFS over recursion**: Iterative, no `RecursionError` risk on deeply nested groups.
- **`id()` cycle detection**: Prevents infinite loops if an exception graph contains circular references.
- **`getattr(current, "exceptions", None)`**: Works for both `ExceptionGroup` and `BaseExceptionGroup` without type checking — only groups have the `.exceptions` attribute.

## Response Content Extraction — `_extract_text_from_content()`

The MCP response `content` field is a list of typed content items (text, image, embedded resource). The helper avoids `IndexError` and `AttributeError`:

```python
def _extract_text_from_content(content) -> str | None:
    if not content:
        return None
    for item in content:
        text = getattr(item, "text", None)
        if text is not None:
            return text
    return None
```

Returns the first text-bearing item, or `None` if the response contains only non-text content (e.g. images).

## Configuration System

### MCP Config — `.vscode/mcp.json`

```json
{
  "servers": {
    "alphavantage": {
      "type": "http",
      "url": "https://mcp.alphavantage.co/mcp?apikey={API_KEY}"
    }
  }
}
```

Validation rules enforced by `load_mcp_config_from_vscode()`:

| Check | Condition | Exception |
|---|---|---|
| File exists | `os.path.exists(config_path)` | `FileNotFoundError` |
| Server name found | `config["servers"].get(server_name)` | `KeyError` |
| Transport type | `server_info["type"] == "http"` | `ValueError` |
| URL present | `server_info.get("url")` truthy | `ValueError` |

The resolved URL is cached in the module-level `_cached_mcp_url` variable. Subsequent calls return the cached value without re-reading the file. To force a re-read (e.g. in tests), set `_cached_mcp_url = None`.

### Environment Variables — `.env`

```bash
# API Keys (both fallback to .env if not in system env)
OPENAI_API_KEY=sk-...
XAI_API_KEY=xai-...

# Model Configurations
OPENAI_MODEL=gpt-4o-mini
XAI_MODEL=grok-4.3
XAI_BASE_URL=https://api.x.ai/v1

# Debug Mode
ALPHA_VANTAGE_DEBUG=true
```

**API Key Resolution:**
1. System environment variable (highest priority)
2. `.env` file via `python-dotenv` (fallback)
3. `None` if missing from both

**Key priority rules:**
- Environment variables override `.env` file values
- `load_dotenv` called with `override=False` guarantees this
- Missing `python-dotenv` package is handled gracefully

### Debug Mode

The `_debug_log()` function gates all debug output behind the `ALPHA_VANTAGE_DEBUG` environment variable (truthy: `true`, `1`, `yes`). Debug calls are placed at every decision point: config resolution, ticker extraction, session lifecycle, tool invocation (including full argument dumps), Grok/xAI calls, response metadata, and error unwrapping. When `DEBUG=False`, `_debug_log` is a no-op — zero runtime overhead.

## Ticker Extraction Algorithm

```python
def extract_ticker(message: str) -> str | None:
    clean_message = re.sub(r'[^\w\s]', '', message).upper()
    words = re.findall(r'\b[A-Z]{1,5}\b', clean_message)

    common_words = {
        'WHATS', 'WHAT', 'THE', 'WITH', 'CHECK', 'HAPPENING', 'CURRENT', 'FOR',
        'VALUE', 'TODAY', 'TOMORROW', 'PRICE', 'QUOTE', 'HOW', 'IS', 'ARE', 'ABOUT',
        'OF', 'IN', 'MY', 'ON', 'AND', 'PLEASE', 'SHOW', 'ME', 'CAN', 'YOU', 'TELL',
        'LOOKING', 'REPORT', 'LATEST', 'UPDATE', 'OVERVIEW', 'NOW', 'HELLO', 'THERE',
        'THANKS', 'THANK', 'HEY', 'PLEASE', 'GIVE', 'ME', 'MORE', 'INFORMATION', 'INFO'
    }
    for word in reversed(words):
        if word not in common_words:
            return word
    return None
```

Pipeline:
1. **Sanitize** — strip punctuation (`[^\w\s]`), uppercase.
2. **Tokenize** — regex `\b[A-Z]{1,5}\b` extracts 1–5 character uppercase words (NYSE/NASDAQ range).
3. **Filter** — reverse scan skipping entries in the `common_words` set. Returns the first non-stop-word candidate.

**Known limitation**: Tickers that collide with stop-words (e.g. `NOW` for ServiceNow Inc., `INFO` for Informatica Inc.) are incorrectly filtered out.

## API Reference

### `load_mcp_config_from_vscode(server_name: str = "alphavantage") -> str`

Parses `.vscode/mcp.json` relative to the script directory. Returns the server URL string. Result is cached in `_cached_mcp_url`.

### `extract_ticker(message: str) -> str | None`

Extracts a stock ticker from free-form user input. Returns `None` if no valid candidate found.

### `async call_alpha_vantage_mcp(ticker: str) -> str`

Executes an MCP transaction: config load → transport open → session init → `TOOL_CALL(GLOBAL_QUOTE)` → response extraction. Returns the quote text or a markdown-formatted error string. Never raises — all exceptions are caught and formatted.

### `async chat_with_mcp(message: str, history: list, use_grok: bool = False) -> tuple[str, str]`

Gradio ChatInterface callback. Extracts ticker, calls MCP, optionally runs OpenAI and Grok analysis, returns:
- Markdown formatted analysis
- Chart.js HTML visualization

Returns error messages if ticker extraction fails.

### `async analyze_with_openai(quote_text: str, ticker: str) -> tuple[dict | None, str]`

Calls OpenAI's `gpt-4o-mini` model with structured outputs (Pydantic `StockAnalysis`). Returns `(parsed_dict, status)` where status is `AI_STATUS_OK`, `AI_STATUS_NO_KEY`, or `AI_STATUS_ERROR`.

### `async analyze_with_grok(quote_text: str, ticker: str) -> tuple[dict | None, str, list | None]`

Calls xAI's `grok-4.3` model for social media sentiment analysis. Returns `(parsed_dict, status, social_sources)` where status is `AI_STATUS_OK`, `AI_STATUS_GK_NO_KEY`, or `AI_STATUS_GK_ERROR`. The response includes social themes, sentiment label/score, and volume bias.

### `get_xai_api_key() -> str | None`

Retrieves the xAI API key with fallback: checks `os.environ["XAI_API_KEY"]` first, then falls back to `.env` file via `python-dotenv`. Returns `None` if missing from both sources.

### `_blend_scores(openai_label, openai_score, grok_label, grok_score) -> dict`

Blends OpenAI and Grok sentiment scores with 50/50 weighting. Applies 20% penalty on label disagreement, sets label to "neutral", and caps minimum score at 0.5. Returns `{"label": str, "score": float}`.

### `_merge_results(openai_parsed: dict, grok_parsed: dict) -> dict`

Merges OpenAI and Grok parsed outputs. Preserves OpenAI's `analysis` and `metrics`, merges sentiment via `_blend_scores`, and adds Grok's `social_sources` and `volume_bias`.

### `async _call_xai_chat_completions(payload: dict) -> dict`

Internal function that calls the xAI API using `httpx.AsyncClient`. Raises `RuntimeError` if `XAI_API_KEY` is not configured. Handles HTTP errors via `raise_for_status()`.

### `_unwrap_exceptions(exc: BaseException) -> list[str]`

Recursively flattens `ExceptionGroup` trees via BFS with `id()` cycle detection. Returns leaf exceptions as `"TypeName: message"` strings.

### `_extract_text_from_content(content) -> str | None`

Scans MCP response content list for the first item exposing a `.text` attribute. Safe against empty lists and non-text content types.

### `render_analysis_markdown(ticker, quote, parsed, status, social_notes=None, grok_status=AI_STATUS_DISABLED) -> str`

Renders markdown output including quote, AI analysis header, sentiment, optional social themes, and fallback notices for Grok unavailability.

### `render_chartjs_html(parsed, ticker, status) -> str`

Renders Chart.js visualization inside an iframe for sentiment and metrics. Shows a styled notice when AI output is unavailable.

## Test Suite

```bash
cd alpha-vantage
pytest test_hello_alpha.py -v
```

**54 tests**, all pass. `gradio` and `mcp` packages are **not** required at test time.

### Module Stubbing

The test module injects `MagicMock` stubs into `sys.modules` before importing the application:

```python
if "gradio" not in sys.modules:
    sys.modules["gradio"] = MagicMock()
if "mcp" not in sys.modules:
    sys.modules["mcp"] = MagicMock()
    sys.modules["mcp.client"] = MagicMock()
    sys.modules["mcp.client.streamable_http"] = MagicMock()
```

This eliminates the need for `gradio` and `mcp` as test-time dependencies. The application module is loaded via `importlib.util.spec_from_file_location` since it's a standalone script (not a package).

### Test Classes

| Class | Count | Type | Key Assertions |
|---|---|---|---|
| `TestExtractTicker` | 4 | sync | Valid symbol, multi-symbol, no-symbol, lowercase |
| `TestLoadMcpConfig` | 4 | sync | Success, file-not-found, server-not-found, invalid-type |
| `TestCallAlphaVantageMcp` | 5 | async | Success (verifies `TOOL_CALL`/`GLOBAL_QUOTE`/JSON args), config-error, empty-response, server-error (`isError`), non-text-content |
| `TestChatWithMcp` | 2 | async | Valid-ticker flow, invalid-input message |
| `TestAnalyzeWithOpenai` | 4 | async | No-key, success, error, response format is Pydantic |
| `TestRenderAnalysisMarkdown` | 4 | sync | Parsed, no-key, error, None payload |
| `TestRenderChartjsHtml` | 5 | sync | No-key, error, empty, includes CDN, payload escaped |
| `TestGetApiKey` | 6 | sync | Env priority, dotenv fallback, missing, no override, quoted, analyze uses it |
| `TestUnwrapExceptions` | 4 | sync | Single exception, one-level group, deeply nested groups, multi-leaf group |
| `TestProtocolErrorReporting` | 2 | async | NVDA failure reproduction (2-level nesting), plain exception |
| `TestBlendScores` | 4 | sync | Agreeing labels, disagreeing penalty, neutral cap, neutral agrees |
| `TestMergeResults` | 2 | sync | Both present, fallback to Grok sentiment |
| `TestGrokKeyResolution` | 2 | sync | Env priority, dotenv fallback for XAI_API_KEY |
| `TestAnalyzeWithGrok` | 3 | async | No-key, success, exception handling |
| `TestChatWithGrokToggle` | 3 | async | Toggle off, toggle on, no-key fallback |

### Async Test Configuration

`pytest-asyncio` is configured in **strict mode** (`mode=Mode.STRICT`), requiring `@pytest.mark.asyncio` on each async test class. Without the decorator, async test methods are not collected.

### Key Tests: MCP Invocation and Grok Integration

`test_call_alpha_vantage_mcp_success` asserts the exact call signature:

```python
mock_session.call_tool.assert_called_once()
call_kwargs = mock_session.call_tool.call_args
assert call_kwargs.kwargs.get("name") == "TOOL_CALL"
args = call_kwargs.kwargs.get("arguments")
assert args["tool_name"] == "GLOBAL_QUOTE"
parsed = json.loads(args["arguments"])
assert parsed == {"symbol": "AAPL"}
```

This test guards against regression to the pre-fix `get_stock_quote` invocation.

`test_toggle_on_calls_grok` verifies that when `use_grok=True`, the Grok analysis is called:

```python
mock_grok.assert_called_once()
assert md in output  # markdown includes social themes
```

`test_grok_no_key_uses_openai_only` ensures graceful fallback when `XAI_API_KEY` is missing:

```python
assert "XAI_API_KEY not configured" in md
assert "ok" in md  # OpenAI analysis still works
```

## Dependencies

```
gradio              # Chat interface framework
mcp                 # Model Context Protocol client (>=1.27.0, streamable_http transport)
openai>=1.40.0      # OpenAI API client
python-dotenv       # .env loading
httpx>=0.25.0,<1.0  # xAI API HTTP client
pytest>=7.0.0       # Test runner
pytest-asyncio>=0.21.0  # Async test support (strict mode)
```

## MCP Server Reference

| Property | Value |
|---|---|
| URL | `https://mcp.alphavantage.co/mcp?apikey={KEY}` |
| Transport | Streamable HTTP (POST requests, SSE for server-initiated) |
| Protocol Version | `2024-11-05` (auto-negotiated) |
| Session Model | Stateless; `mcp-session-id` header returned |
| Authentication | API key in query parameter |
| Rate Limit | 25 requests/day (free tier) |

## xAI Server Reference

| Property | Value |
|---|---|
| URL | `https://api.x.ai/v1` (configurable via `XAI_BASE_URL`) |
| Model | `grok-4.3` (configurable via `XAI_MODEL`) |
| Transport | HTTP via `httpx.AsyncClient` |
| Auth | `Authorization: Bearer {XAI_API_KEY}` header |
| Response Format | `json_object` (strict JSON) |
| Timeout | 30 seconds |
| Rate Limit | Varies by xAI tier; client-side failure is handled gracefully |

## Common Errors

### "Protocol Transport Fault: Session terminated"

Cause: HTTP 404 from unknown tool name. The streamable-HTTP transport interprets 404 as a transport failure. Fix: Use `TOOL_CALL` meta-tool, not direct function names like `get_stock_quote`.

### "Configuration profile missing at location"

Cause: `.vscode/mcp.json` not found relative to the script directory. Fix: Create the config file (see Configuration System above).

### "Invalid transport schema 'websocket'"

Cause: Server `type` field is not `"http"`. The application only supports HTTP transport. Fix: Set `"type": "http"` in the config.

### "XAI_API_KEY not configured"

Cause: `XAI_API_KEY` missing from both environment variables and `.env` file. Fix: Add `XAI_API_KEY=xai-...` to `.env` or set environment variable.

### "Social sentiment unavailable — xAI request failed"

Cause: xAI API call failed (network error, invalid key, rate limit). Fix: Verify `XAI_API_KEY` is valid, check network connectivity, or disable Grok checkbox.

### API Rate Limit

The Alpha Vantage free tier allows 25 requests/day. When exceeded, the server returns an `Information` note in the response text (not an error). This is surfaced as informational content, not as a `Protocol Transport Fault`.

### Grok Called Without OpenAI Key

If `OPENAI_API_KEY` is missing but `use_grok=True`, Grok is **not** called. The system requires OpenAI analysis to be available before supplementing with Grok social sentiment. Fix: Configure `OPENAI_API_KEY` to enable both analysis layers.

## UI Components

### ChatInterface

The main interface uses `gr.ChatInterface` with:

- `title`: "Alpha Vantage Assistant"
- `description`: "Async MCP stock quotes + OpenAI analysis with optional Grok social sentiment."
- `additional_inputs`: `[use_grok_cb]` — checkbox for Grok toggle
- `additional_outputs`: `[charts_output]` — Chart.js HTML visualization
- `examples`: Pre-filled query examples (TSLA, NVDA, AAPL)

### Grok Toggle Checkbox

```python
use_grok_cb = gr.Checkbox(label="Use Grok social sentiment", value=False)
```

When checked, enables xAI Grok social media sentiment analysis. When unchecked, uses OpenAI-only analysis.

### Charts Output

`gr.HTML(label="Charts", render=False)` component renders:
- Metrics bar chart (price, volume, P/E ratio, etc.)
- Sentiment doughnut chart (bullish/bearish/neutral)
- Social themes display (when Grok enabled)
- Styled notices when AI output unavailable

## Data Flow Summary

1. **User Input**: Message entered + Grok checkbox state
2. **Ticker Extraction**: Regex-based pattern matching from message
3. **Alpha Vantage Quote**: MCP call via streamable-HTTP to get stock data
4. **OpenAI Analysis** (if `OPENAI_API_KEY` configured): Sentiment and metrics from stock quote
5. **Grok Analysis** (if checkbox enabled and OpenAI key present): Social media sentiment from xAI
6. **Sentiment Blending**: 50/50 blend with 20% penalty on disagreement
7. **Rendering**: Markdown with social themes + Chart.js visualization
8. **Error Handling**: Graceful fallback with user-friendly notices

## Future Enhancements

Potential areas for improvement:
- Persistent caching of sentiment results across sessions
- Historical sentiment tracking and trend visualization
- Additional social media sources beyond xAI's real-time analysis
- Batch analysis for multiple tickers
- Configurable sentiment blend weights (e.g., 70% OpenAI, 30% Grok)
- Real-time sentiment streaming via SSE from xAI