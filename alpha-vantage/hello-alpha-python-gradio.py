import traceback
import os
import json
import re
import html
import gradio as gr
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from typing import List

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    # Load .env from the alpha-vantage directory (same location as this script)
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(env_path)
except ImportError:
    pass  # dotenv not installed, use environment variables as-is

# Global debug flag - set to True to enable verbose debug logging
DEBUG = os.environ.get("ALPHA_VANTAGE_DEBUG", "false").lower() in ("true", "1", "yes")

def _debug_log(*args, **kwargs):
    """Conditional debug logging. Only prints when DEBUG flag is True."""
    if DEBUG:
        print("[DEBUG]", *args, **kwargs)

_cached_mcp_url = None

# OpenAI model id, defaulting to the smallest/cheapest current OpenAI model.
# (OpenAI has no model literally named "nano"; gpt-4o-mini is the equivalent.)
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Status codes describing why AI analysis did (or did not) produce output.
# Returning a status alongside the payload lets the renderers show a precise,
# actionable warning (missing key vs. API failure) without disrupting the
# stock quote that was already retrieved.
AI_STATUS_OK = "ok"
AI_STATUS_NO_KEY = "no_key"
AI_STATUS_ERROR = "error"

# JSON contract enforced via OpenAI structured outputs. Pydantic models are
# passed directly into response_format so the SDK validates/parse the response
# into a typed object; we then .model_dump() it back to a plain dict so the
# existing chart/rendering code (which expects dicts) works unmodified.
class MetricItem(BaseModel):
    label: str
    value: float


class SentimentInfo(BaseModel):
    label: str
    score: float


class StockAnalysis(BaseModel):
    analysis: str
    metrics: List[MetricItem]
    sentiment: SentimentInfo

# Chart.js template rendered inside a gr.HTML component. The model's structured
# payload is injected as an escaped JSON string and decoded at runtime to avoid
# script-injection from model/user-controlled text.
_CHART_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
  .av-wrap{font-family:"Courier New","Consolas",monospace;color:#EAECEF;background:#0B0E11;padding:8px;display:flex;flex-wrap:wrap;gap:16px}
  .av-card{background:#11161B;border:1px solid #1F2730;border-radius:4px;padding:8px}
  .av-card h4{margin:0 0 6px;font-size:0.75rem;text-transform:uppercase;letter-spacing:0.08em;color:#8B949E}
  canvas{max-width:280px;max-height:200px}
  .av-sent{font-weight:700;text-transform:uppercase}
</style></head>
<body><div class="av-wrap">
  <div class="av-card"><h4>Metrics</h4><canvas id="av-metrics"></canvas></div>
  <div class="av-card"><h4>Sentiment</h4><canvas id="av-sentiment"></canvas><div id="av-sent-label" style="text-align:center;margin-top:4px"></div></div>
</div>
<script>
const DATA = __DATA__;
if (DATA.metrics && DATA.metrics.length) {
  new Chart(document.getElementById('av-metrics'), {
    type:'bar',
    data:{labels:DATA.metrics.map(m=>m.label),
          datasets:[{label:'Value',data:DATA.metrics.map(m=>m.value),
                     backgroundColor:'#1D4ED8'}]},
    options:{plugins:{legend:{display:false}},scales:{y:{ticks:{color:'#8B949E'}},x:{ticks:{color:'#8B949E'}}}}
  });
}
const s = (DATA.sentiment && typeof DATA.sentiment.score === 'number') ? Math.max(0,Math.min(1,DATA.sentiment.score)) : 0;
const sColor = s >= 0.6 ? '#3AC569' : (s <= 0.4 ? '#F8506B' : '#EAB308');
new Chart(document.getElementById('av-sentiment'), {
  type:'doughnut',
  data:{datasets:[{data:[s, Math.max(0,1-s)], backgroundColor:[sColor,'#1F2730']}]},
  options:{cutout:'70%',plugins:{legend:{display:false},tooltip:{enabled:false}}}
});
const lbl = document.getElementById('av-sent-label');
lbl.innerHTML = '<span class="av-sent" style="color:'+sColor+'">'+(DATA.sentiment && DATA.sentiment.label ? DATA.sentiment.label : 'n/a')+'</span> ('+(s*100).toFixed(0)+'%)';
</script></body></html>
"""

# Styled notice rendered into the Charts panel when AI output is unavailable,
# so the panel is never mysteriously blank. {reason} holds a static developer
# string (never user/model-controlled text), so it is not escaped.
_DISABLED_NOTICE_TEMPLATE = """<div style="font-family:'Courier New','Consolas',monospace;color:#8B949E;background:#11161B;border:1px solid #1F2730;border-radius:4px;padding:12px;max-width:520px">
<strong style="color:#EAECEF">Charts unavailable</strong><br>
<span>{reason}</span>
</div>"""


def load_mcp_config_from_vscode(server_name: str = "alphavantage") -> str:
    """Parses .vscode/mcp.json file synchronously to fetch deployment schema."""
    _debug_log(f"Loading MCP config for server: {server_name}")
    
    global _cached_mcp_url
    if _cached_mcp_url:
        _debug_log(f"Using cached MCP URL: {_cached_mcp_url}")
        return _cached_mcp_url
    
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".vscode", "mcp.json")
    _debug_log(f"Config path resolved to: {config_path}")
    
    if not os.path.exists(config_path):
        _debug_log(f"Configuration file NOT FOUND at: {config_path}")
        raise FileNotFoundError(f"Configuration profile missing at location: '{config_path}'")
    
    _debug_log(f"Opening configuration file: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        config_data = json.load(f)
    
    _debug_log(f"Raw config data: {json.dumps(config_data, indent=2)}")
    
    server_info = config_data.get("servers", {}).get(server_name)
    if not server_info:
        _debug_log(f"Server '{server_name}' not found in config")
        raise KeyError(f"Target profile label '{server_name}' not defined inside configuration mappings.")
    
    _debug_log(f"Server info found: {server_info}")
    
    server_type = server_info.get("type")
    if server_type != "http":
        _debug_log(f"Invalid server type: {server_type}, expected 'http'")
        raise ValueError(f"Invalid transport schema '{server_type}'. Expected 'http'.")
    
    url = server_info.get("url")
    if not url:
        _debug_log("Server URL is empty or missing")
        raise ValueError("Target endpoint connection URL string cannot be blank.")
    
    _debug_log(f"MCP endpoint URL resolved: {url}")
    _cached_mcp_url = url
    return url

def extract_ticker(message: str) -> str | None:
    """Extract a stock ticker symbol from user message using common ticker patterns."""
    _debug_log(f"Extracting ticker from message: '{message}'")
    
    clean_message = re.sub(r'[^\w\s]', '', message).upper()
    _debug_log(f"Cleaned message: '{clean_message}'")
    
    words = re.findall(r'\b[A-Z]{1,5}\b', clean_message)
    _debug_log(f"Found candidate words: {words}")
    
    # Tickers are typically at the end or standalone; scan in reverse
    common_words = {
        'WHATS', 'WHAT', 'THE', 'WITH', 'CHECK', 'HAPPENING', 'CURRENT', 'FOR',
        'VALUE', 'TODAY', 'TOMORROW', 'PRICE', 'QUOTE', 'HOW', 'IS', 'ARE', 'ABOUT',
        'OF', 'IN', 'MY', 'ON', 'AND', 'PLEASE', 'SHOW', 'ME', 'CAN', 'YOU', 'TELL',
        'LOOKING', 'REPORT', 'LATEST', 'UPDATE', 'OVERVIEW', 'NOW', 'HELLO', 'THERE',
        'THANKS', 'THANK', 'HEY', 'PLEASE', 'GIVE', 'ME', 'MORE', 'INFORMATION', 'INFO'
    }
    for word in reversed(words):
        if word not in common_words:
            _debug_log(f"Selected ticker: '{word}'")
            return word
    
    _debug_log("No valid ticker found in message")
    return None

def _extract_text_from_content(content) -> str | None:
    """Safely extract text from an MCP tool response content list.

    Scans content items for the first one exposing a ``.text`` attribute and
    returns it. Returns None if no text-bearing item is present, guarding
    against non-text content types (images, embedded resources, etc.).
    """
    if not content:
        return None
    for item in content:
        text = getattr(item, "text", None)
        if text is not None:
            return text
    return None


def _unwrap_exceptions(exc: BaseException) -> list[str]:
    """Recursively flatten an exception (and any nested ExceptionGroups).

    The MCP streamable-HTTP transport raises ``ExceptionGroup`` (a.k.a.
    ``BaseExceptionGroup``) instances that can wrap the real error multiple
    layers deep. Without recursive unwrapping the user only sees the useless
    "unhandled errors in a TaskGroup" message instead of the actionable root
    cause (e.g. ``McpError: Session terminated``). Returns a list of
    ``Type: message`` strings, one per leaf exception found.
    """
    leaves: list[str] = []
    queue: list[BaseException] = [exc]
    seen: set[int] = set()
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


def get_api_key(key_name: str = "OPENAI_API_KEY",
                env_path: str | None = None) -> str | None:
    """Return the requested API key, prioritizing the environment variable.

    Resolution order:
    1. The existing process environment variable (``os.environ``) — highest
       priority. If it is set to a non-empty value it is returned immediately
       and the ``.env`` file is never consulted.
    2. A value loaded from a ``.env`` file via python-dotenv, used only when
       the variable is absent from the environment.

    python-dotenv is invoked with ``override=False`` (its default), so a value
    already present in the environment is never clobbered by the ``.env`` file,
    preserving the required precedence. When python-dotenv is not installed,
    only the environment variable is consulted.

    Returns the key string when found, or None if it cannot be resolved from
    either source.
    """
    existing = os.environ.get(key_name)
    if existing:
        _debug_log(f"API key '{key_name}' resolved from environment variable")
        return existing

    try:
        from dotenv import load_dotenv
    except ImportError:
        _debug_log("python-dotenv unavailable; cannot read .env file")
        return None

    if env_path is None:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

    # override=False (the default) guarantees an existing environment variable
    # is never overwritten by a value from the .env file.
    load_dotenv(env_path, override=False)
    value = os.environ.get(key_name)
    _debug_log(f"API key '{key_name}' resolved from .env: {bool(value)}")
    return value


async def analyze_with_openai(quote_text: str, ticker: str) -> tuple[dict | None, str]:
    """Call the OpenAI model on a stock quote and return a structured payload.

    Uses OpenAI structured outputs (json_schema response_format) so the result
    matches the chart contract. Returns a ``(parsed, status)`` tuple where
    ``status`` is one of ``AI_STATUS_OK``, ``AI_STATUS_NO_KEY`` (no API key
    configured), or ``AI_STATUS_ERROR`` (key present but the request failed).
    In both non-OK cases ``parsed`` is None and the caller falls back
    gracefully to the raw quote with an informative warning.
    """
    api_key = get_api_key("OPENAI_API_KEY")
    if not api_key:
        _debug_log("OPENAI_API_KEY not set; skipping AI analysis")
        return None, AI_STATUS_NO_KEY

    _debug_log(f"Invoking OpenAI model {OPENAI_MODEL} for ticker {ticker}")
    try:
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.beta.chat.completions.parse(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a financial analyst. Given a stock quote, return: "
                        "(1) 'analysis': a concise 3-5 sentence market read; "
                        "(2) 'metrics': up to 6 numeric metrics derivable from the quote "
                        "(e.g. price, change_percent, volume_in_millions, pe_ratio, "
                        "day_range_midpoint). Only include numbers present in or directly "
                        "derivable from the quote text. If a metric cannot be derived, omit it. "
                        "(3) 'sentiment': a label (bullish|bearish|neutral) and a confidence "
                        "score between 0 and 1."
                    ),
                },
                {"role": "user", "content": f"Ticker: {ticker}\nQuote:\n{quote_text}"},
            ],
            response_format=StockAnalysis,
        )
        parsed = resp.choices[0].message.parsed
        # Convert the Pydantic object back to a dict so the existing rendering
        # code (which operates on dicts) works unmodified.
        parsed_dict = parsed.model_dump() if parsed else None
        _debug_log(f"OpenAI returned parsed payload: {parsed_dict}")
        return parsed_dict, AI_STATUS_OK
    except Exception as ai_err:
        _debug_log(f"OpenAI analysis failed: {type(ai_err).__name__}: {ai_err}")
        return None, AI_STATUS_ERROR


def render_analysis_markdown(ticker: str, quote: str, parsed: dict | None,
                             status: str = AI_STATUS_OK) -> str:
    """Render the textual analysis.

    The raw stock quote is ALWAYS shown. When AI analysis is unavailable a
    clear, actionable warning is appended (without obscuring the quote); the
    warning differs depending on whether the key is missing or the call failed.
    """
    base = f"### Analysis for **{ticker}** via Workspace Protocol Hub:\n\n{quote}"

    if status == AI_STATUS_NO_KEY:
        return (
            f"{base}\n\n"
            "> **AI analysis unavailable** — the `OPENAI_API_KEY` environment "
            "variable is not set, so the AI-powered summary and charts were "
            "skipped. The stock quote above is unaffected.\n\n"
            "> To enable AI analysis, add a valid key to `alpha-vantage/.env`:\n"
            ">\n> ```\n> OPENAI_API_KEY=sk-...\n> ```"
        )

    if status == AI_STATUS_ERROR or parsed is None:
        return (
            f"{base}\n\n"
            "> **AI analysis unavailable** — a key is configured, but the "
            "request to the OpenAI model could not be completed (network error, "
            "invalid key, rate limit, or model error). Charts were skipped.\n\n"
            "> Verify the key and `OPENAI_MODEL` value, or set "
            "`ALPHA_VANTAGE_DEBUG=true` for diagnostic details."
        )

    sentiment = parsed.get("sentiment", {}) or {}
    label = sentiment.get("label", "n/a")
    score = sentiment.get("score", "n/a")
    score_display = f"{score:.2f}" if isinstance(score, (int, float)) else score
    return (
        f"{base}\n\n"
        f"#### AI Analysis ({label.upper()}, confidence {score_display})\n\n"
        f"{parsed.get('analysis', '')}"
    )


def render_chartjs_html(parsed: dict | None, ticker: str,
                        status: str = AI_STATUS_OK) -> str:
    """Render the Chart.js visualization.

    When AI output is unavailable (no key, failure, or empty payload) a styled,
    visible notice is returned instead of an invisible comment so the Charts
    panel is never mysteriously blank.

    The chart document is delivered inside an ``<iframe srcdoc="...">`` wrapper.
    Gradio injects ``gr.HTML`` content via ``innerHTML``, which does NOT execute
    ``<script>`` tags — so a bare Chart.js template would silently fail to draw
    (and log a warning). An iframe loads its own document where scripts run
    normally, sidestepping both problems. The full template is HTML-escaped into
    the ``srcdoc`` attribute, preserving the existing JSON-payload injection.
    """
    if status == AI_STATUS_NO_KEY:
        reason = "No <code>OPENAI_API_KEY</code> configured. Add one to " \
                 "<code>alpha-vantage/.env</code> to generate charts."
        return _DISABLED_NOTICE_TEMPLATE.format(reason=reason)
    if status == AI_STATUS_ERROR or not parsed:
        reason = "AI analysis could not be completed. Charts were skipped."
        return _DISABLED_NOTICE_TEMPLATE.format(reason=reason)
    safe_payload = {
        "ticker": ticker,
        "metrics": parsed.get("metrics", []) or [],
        "sentiment": parsed.get("sentiment", {"label": "n/a", "score": 0}) or {},
    }
    # Escape the JSON before embedding so model/user text cannot break out of
    # the script context.
    payload_json = html.escape(json.dumps(safe_payload), quote=True)
    chart_doc = _CHART_TEMPLATE.replace("__DATA__", "JSON.parse('" + payload_json + "')")
    # Escape the whole document into the srcdoc attribute so the iframe renders
    # it verbatim. The script-payload inside was already escaped above.
    return (
        '<iframe srcdoc="{srcdoc}" style="width:100%;height:280px;'
        'border:0;frameborder:0"></iframe>'
    ).format(srcdoc=html.escape(chart_doc, quote=True))


async def call_alpha_vantage_mcp(ticker: str) -> str:
    """
    Executes transaction tasks inside a transient stream context.
    Safely isolated via native async hooks.
    """
    _debug_log(f"=== call_alpha_vantage_mcp START ===")
    _debug_log(f"Input ticker: {ticker}")
    
    try:
        mcp_endpoint_url = load_mcp_config_from_vscode("alphavantage")
        _debug_log(f"MCP endpoint URL: {mcp_endpoint_url}")
    except Exception as config_err:
        _debug_log(f"Configuration error: {config_err}")
        return f"### Configuration Error\n{str(config_err)}"
    
    try:
        _debug_log("Opening streamable HTTP client connection...")
        async with streamablehttp_client(mcp_endpoint_url) as (read_stream, write_stream, _):
            _debug_log("Streamable HTTP client connection established")
            
            async with ClientSession(read_stream, write_stream) as session:
                _debug_log("ClientSession created, initializing...")
                await session.initialize()
                _debug_log("Session initialized successfully")

                # The Alpha Vantage MCP server exposes a meta-tool interface
                # (TOOL_LIST / TOOL_GET / TOOL_CALL) rather than individual
                # endpoints. To fetch a quote we invoke TOOL_CALL which wraps
                # the underlying GLOBAL_QUOTE Alpha Vantage function. The inner
                # arguments MUST be a JSON-encoded string (per the TOOL_CALL
                # schema) and GLOBAL_QUOTE expects a "symbol" parameter.
                tool_call_args = {
                    "tool_name": "GLOBAL_QUOTE",
                    "arguments": json.dumps({"symbol": ticker}),
                }
                _debug_log(f"Calling tool 'TOOL_CALL' with arguments: {tool_call_args}")
                response = await session.call_tool(
                    name="TOOL_CALL",
                    arguments=tool_call_args,
                )
                _debug_log(f"Tool response received, content length: {len(response.content) if response.content else 0}")
                _debug_log(f"Full response metadata: isError={getattr(response, 'isError', 'N/A')}")
                
                if getattr(response, "isError", False):
                    error_text = _extract_text_from_content(response.content)
                    _debug_log(f"Server reported tool error: {error_text}")
                    return f"### Tool Error\nThe server reported an error executing the tool.\n{error_text}"
                
                if response.content and len(response.content) > 0:
                    result_text = _extract_text_from_content(response.content)
                    if result_text is not None:
                        _debug_log(f"Response content text length: {len(result_text)}")
                        return result_text
                    _debug_log("No text-bearing content items found in response")
                    return "Server executed successfully but returned no text content."
                
                _debug_log("Empty response content received")
                return "Server executed successfully but returned an empty context payload data block."
                
    except Exception as protocol_err:
        _debug_log(f"Protocol error: {type(protocol_err).__name__}: {protocol_err}")
        _debug_log(f"Full traceback:\n{traceback.format_exc()}")

        # Recursively unwrap ExceptionGroup/BaseExceptionGroup instances so the
        # actionable root cause (e.g. McpError: Session terminated) is reported
        # instead of the opaque "unhandled errors in a TaskGroup" wrapper.
        leaf_errors = _unwrap_exceptions(protocol_err)
        _debug_log(f"Unwrapped leaf exceptions: {leaf_errors}")

        if leaf_errors:
            error_details = "\n".join(f"  - {leaf}" for leaf in leaf_errors)
        else:
            error_details = f"{type(protocol_err).__name__}: {protocol_err}"

        return (
            "### Protocol Transport Fault\n"
            "Unable to fulfill network transaction. Root cause(s):\n"
            f"{error_details}"
        )

async def chat_with_mcp(message: str, history: list) -> str:
    """
    Native asynchronous Gradio execution hook. Prevents thread-blocking
    and handles state transformations cleanly under concurrent access.
    """
    _debug_log(f"=== chat_with_mcp START ===")
    _debug_log(f"Received message: '{message}'")
    _debug_log(f"History length: {len(history)}")
    
    ticker = extract_ticker(message)
    _debug_log(f"Extracted ticker: {ticker}")
    
    if not ticker:
        _debug_log("No ticker extracted, returning error message")
        return "I couldn't isolate a clean ticker tracking label in your input. Try specifying a clear target like `AAPL` or `TSLA`.", "<!-- no ticker: no chart -->"
    
    _debug_log(f"Calling MCP for ticker: {ticker}")
    mcp_response = await call_alpha_vantage_mcp(ticker)
    _debug_log(f"MCP response received (length: {len(mcp_response)})")

    # If the MCP call itself failed, surface that as text without chart output.
    if mcp_response.startswith("### "):
        _debug_log("MCP returned an error header; skipping AI analysis")
        return mcp_response, "<!-- MCP error: no chart -->"

    parsed, ai_status = await analyze_with_openai(mcp_response, ticker)
    markdown = render_analysis_markdown(ticker, mcp_response, parsed, ai_status)
    chart_html = render_chartjs_html(parsed, ticker, ai_status)
    _debug_log("=== chat_with_mcp END ===")
    return markdown, chart_html

demo = gr.ChatInterface(
    fn=chat_with_mcp,
    title="Alpha Vantage Assistant",
    description="Async MCP stock quotes + OpenAI analysis with Chart.js visuals.",
    additional_outputs=[gr.HTML(label="Charts")],
    examples=["What's happening with TSLA?", "Check current quote value for NVDA", "AAPL"]
)

if __name__ == "__main__":
    _debug_log("Application starting...")
    demo.launch()