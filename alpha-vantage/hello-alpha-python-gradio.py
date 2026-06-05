import os
import json
import re
import gradio as gr
_IMPORT_ERROR = None
try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
except Exception as e:  # pragma: no cover - fallback when dependency missing
    ClientSession = None
    streamablehttp_client = None
    _IMPORT_ERROR = e

_cached_mcp_url = None

def load_mcp_config_from_vscode(server_name: str = "alphavantage") -> str:
    """Parses .vscode/mcp.json file synchronously to fetch deployment schema."""
    global _cached_mcp_url
    if _cached_mcp_url:
        return _cached_mcp_url

    config_path = os.path.join(".vscode", "mcp.json")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration profile missing at location: '{config_path}'")

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = json.load(f)

    server_info = config_data.get("servers", {}).get(server_name)
    if not server_info:
        raise KeyError(f"Target profile label '{server_name}' not defined inside configuration mappings.")

    if server_info.get("type") != "http":
        raise ValueError(f"Invalid transport schema '{server_info.get('type')}'. Expected 'http'.")

    url = server_info.get("url")
    if not url:
        raise ValueError("Target endpoint connection URL string cannot be blank.")

    _cached_mcp_url = url
    return url

def extract_ticker(message: str) -> str | None:
    """Extract a stock ticker symbol from user message using common ticker patterns."""
    clean_message = message.strip().upper()
    ticker_match = re.search(r'\b([A-Z]{1,5})\b', clean_message)
    if ticker_match:
        return ticker_match.group(1)
    ticker_match = re.search(r'\b([A-Z]{1,4}[.-][A-Z])\b', clean_message)
    if ticker_match:
        return ticker_match.group(1)
    return None

async def call_alpha_vantage_mcp(ticker: str) -> str:
    """
    Executes transaction tasks inside a transient stream context.
    Safely isolated via native async hooks.
    """
    try:
        mcp_endpoint_url = load_mcp_config_from_vscode("alphavantage")
    except Exception as config_err:
        return f"### Configuration Error\n{str(config_err)}"

    if ClientSession is None or streamablehttp_client is None:
        return (
            "### Dependency Error\n"
            "Required package 'mcp' is not available. Install it or ensure it's on PYTHONPATH. "
            f"Underlying error: {str(_IMPORT_ERROR)}"
        )

    try:
        async with streamablehttp_client(mcp_endpoint_url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                response = await session.call_tool(
                    name="get_stock_quote",
                    arguments={"ticker": ticker}
                )

                if response.content and len(response.content) > 0:
                    return response.content[0].text
                return "Server executed successfully but returned an empty context payload data block."

    except Exception as protocol_err:
        return f"### Protocol Transport Fault\nUnable to fulfill network transaction. Details: `{str(protocol_err)}`"

async def chat_with_mcp(message: str, history: list) -> str:
    """
    Native asynchronous Gradio execution hook. Prevents thread-blocking
    and handles state transformations cleanly under concurrent access.
    """
    ticker = extract_ticker(message)

    if not ticker:
        return "I couldn't isolate a clean ticker tracking label in your input. Try specifying a clear target like `AAPL` or `TSLA`."

    mcp_response = await call_alpha_vantage_mcp(ticker)
    return f"### Analysis for **{ticker}** via Workspace Protocol Hub:\n\n{mcp_response}"

demo = gr.ChatInterface(
    fn=chat_with_mcp,
    title="Alpha Vantage Assistant",
    description="Async implementation using MCP protocol for stock quotes.",
    examples=["What's happening with TSLA?", "Check current quote value for NVDA", "AAPL"],
    type="messages"
)

if __name__ == "__main__":
    demo.launch()