import traceback
import os
import json
import re
import gradio as gr
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

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
                
                _debug_log(f"Calling tool 'get_stock_quote' with arguments: {{'ticker': '{ticker}'}}")
                response = await session.call_tool(
                    name="get_stock_quote",
                    arguments={"ticker": ticker}
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
        
        # Extract sub-exceptions from ExceptionGroup for better error reporting
        error_details = str(protocol_err)
        if hasattr(protocol_err, "exceptions"):
            for sub_exc in protocol_err.exceptions:
                _debug_log(f"  Sub-exception: {type(sub_exc).__name__}: {sub_exc}")
                error_details += f"\n  Sub: {type(sub_exc).__name__}: {sub_exc}"
        return f"### Protocol Transport Fault\nUnable to fulfill network transaction. Details: `{error_details}`"

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
        return "I couldn't isolate a clean ticker tracking label in your input. Try specifying a clear target like `AAPL` or `TSLA`."
    
    _debug_log(f"Calling MCP for ticker: {ticker}")
    mcp_response = await call_alpha_vantage_mcp(ticker)
    _debug_log(f"MCP response received (length: {len(mcp_response)})")
    
    result = f"### Analysis for **{ticker}** via Workspace Protocol Hub:\n\n{mcp_response}"
    _debug_log(f"Returning formatted result")
    _debug_log("=== chat_with_mcp END ===")
    return result

demo = gr.ChatInterface(
    fn=chat_with_mcp,
    title="Alpha Vantage Assistant",
    description="Async implementation using MCP protocol for stock quotes.",
    examples=["What's happening with TSLA?", "Check current quote value for NVDA", "AAPL"]
)

if __name__ == "__main__":
    _debug_log("Application starting...")
    demo.launch()