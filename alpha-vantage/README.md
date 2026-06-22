# Alpha Vantage MCP Integration — Technical Implementation

Gradio-based chat interface that queries stock quotes through the Model Context Protocol (MCP) over a Streamable HTTP transport to an Alpha Vantage backend.

## Module Architecture

```
User message
    │
    ▼
chat_with_mcp(message, history)          ← async entry (Gradio hook)
    │
    ├─ extract_ticker(message)           ← sync regex extraction
    │      │
    │      ├─ re.sub(r'[^\w\s]', '', message).upper()
    │      ├─ re.findall(r'\b[A-Z]{1,5}\b', cleaned)
    │      └─ reversed scan with stop-word filter → ticker or None
    │
    ▼
call_alpha_vantage_mcp(ticker)           ← async MCP transaction
    │
    ├─ load_mcp_config_from_vscode()     ← sync file I/O
    │      ↓ .vscode/mcp.json → URL (cached globally)
    │
    ├─ streamablehttp_client(url)        ← async context manager
    │      ↓ (read_stream, write_stream, _)
    │
    ├─ ClientSession(read, write)        ← async context manager
    │      ↓ session.initialize()
    │
    └─ session.call_tool("TOOL_CALL", { ← meta-tool dispatch
           "tool_name": "GLOBAL_QUOTE",
           "arguments": json.dumps({"symbol": ticker})
       })
           ↓
       MCP response → _extract_text_from_content() → string
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

## Error Propagation Chain

Errors are handled at three distinct layers, each producing a markdown-formatted response string:

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

### Debug Mode — `.env`

```bash
ALPHA_VANTAGE_DEBUG=true
```

The `_debug_log()` function gates all debug output behind the `ALPHA_VANTAGE_DEBUG` environment variable (truthy: `true`, `1`, `yes`). Debug calls are placed at every decision point: config resolution, ticker extraction, session lifecycle, tool invocation (including full argument dumps), response metadata, and error unwrapping. When `DEBUG=False`, `_debug_log` is a no-op — zero runtime overhead.

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

### `async chat_with_mcp(message: str, history: list) -> str`

Gradio ChatInterface callback. Extracts ticker, calls MCP, formats result as:

```
### Analysis for **TICKER** via Workspace Protocol Hub:

{mcp_response}
```

Returns an error message if ticker extraction fails.

### `_unwrap_exceptions(exc: BaseException) -> list[str]`

Recursively flattens `ExceptionGroup` trees via BFS with `id()` cycle detection. Returns leaf exceptions as `"TypeName: message"` strings.

### `_extract_text_from_content(content) -> str | None`

Scans MCP response content list for the first item exposing a `.text` attribute. Safe against empty lists and non-text content types.

## Test Suite

```bash
cd alpha-vantage
pytest test_hello_alpha.py -v
```

**21 tests**, all pass. `gradio` and `mcp` packages are **not** required at test time.

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
| `TestUnwrapExceptions` | 4 | sync | Single exception, one-level group, deeply nested groups, multi-leaf group |
| `TestProtocolErrorReporting` | 2 | async | NVDA failure reproduction (2-level nesting), plain exception |

### Async Test Configuration

`pytest-asyncio` is configured in **strict mode** (`mode=Mode.STRICT`), requiring `@pytest.mark.asyncio` on each async test class. Without the decorator, async test methods are not collected.

### Key Test: Corrected MCP Invocation

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

## Dependencies

```
gradio              # Chat interface framework
mcp                 # Model Context Protocol client (>=1.27.0, streamable_http transport)
python-dotenv       # .env loading
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

## Common Errors

### "Protocol Transport Fault: Session terminated"

Cause: HTTP 404 from unknown tool name. The streamable-HTTP transport interprets 404 as a transport failure. Fix: Use `TOOL_CALL` meta-tool, not direct function names like `get_stock_quote`.

### "Configuration profile missing at location"

Cause: `.vscode/mcp.json` not found relative to the script directory. Fix: Create the config file (see Configuration System above).

### "Invalid transport schema 'websocket'"

Cause: Server `type` field is not `"http"`. The application only supports HTTP transport. Fix: Set `"type": "http"` in the config.

### API Rate Limit

The Alpha Vantage free tier allows 25 requests/day. When exceeded, the server returns an `Information` note in the response text (not an error). This is surfaced as informational content, not as a `Protocol Transport Fault`.
