"""
Pytest test suite for Alpha Vantage MCP integration.
Tests critical functionality: config loading, ticker extraction, and MCP calls.
"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Inject lightweight stubs for gradio and mcp BEFORE importing the main module.
# The real `import gradio` can hang during collection in some environments, and
# the `mcp` package may not be installed in the interpreter running pytest. The
# tests mock streamablehttp_client / ClientSession anyway, so stubs suffice.
if "gradio" not in sys.modules:
    gradio_stub = MagicMock()
    gradio_stub.ChatInterface = MagicMock()
    sys.modules["gradio"] = gradio_stub

if "mcp" not in sys.modules:
    sys.modules["mcp"] = MagicMock()
if "mcp.client" not in sys.modules:
    sys.modules["mcp.client"] = MagicMock()
if "mcp.client.streamable_http" not in sys.modules:
    streamable_stub = MagicMock()
    sys.modules["mcp.client.streamable_http"] = streamable_stub

# Import functions to test from the script file directly
script_path = Path(__file__).resolve().parent / "hello-alpha-python-gradio.py"
spec = importlib.util.spec_from_file_location("hello_alpha_python_gradio", script_path)
hello_alpha_python_gradio = importlib.util.module_from_spec(spec)
sys.modules["hello_alpha_python_gradio"] = hello_alpha_python_gradio
spec.loader.exec_module(hello_alpha_python_gradio)

load_mcp_config_from_vscode = hello_alpha_python_gradio.load_mcp_config_from_vscode
extract_ticker = hello_alpha_python_gradio.extract_ticker
call_alpha_vantage_mcp = hello_alpha_python_gradio.call_alpha_vantage_mcp
chat_with_mcp = hello_alpha_python_gradio.chat_with_mcp
analyze_with_openai = hello_alpha_python_gradio.analyze_with_openai
render_analysis_markdown = hello_alpha_python_gradio.render_analysis_markdown
render_chartjs_html = hello_alpha_python_gradio.render_chartjs_html


@pytest.fixture(autouse=True)
def _no_openai_key(monkeypatch):
    """Ensure tests run without a real OpenAI key by default."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


class TestExtractTicker:
    """Test ticker extraction from user messages."""

    def test_extract_ticker_with_valid_symbol(self):
        """Test extraction of valid ticker symbol from message."""
        result = extract_ticker("What's happening with TSLA?")
        assert result == "TSLA", f"Expected 'TSLA', got '{result}'"

    def test_extract_ticker_with_multiple_symbols(self):
        """Test extraction prioritizes ticker over common words."""
        result = extract_ticker("Check current value for AAPL")
        assert result == "AAPL", f"Expected 'AAPL', got '{result}'"

    def test_extract_ticker_with_no_valid_symbol(self):
        """Test returns None when no valid ticker found."""
        result = extract_ticker("What's the weather today?")
        assert result is None, f"Expected None, got '{result}'"

    def test_extract_ticker_with_lowercase(self):
        """Test handles lowercase input."""
        result = extract_ticker("show me the price of nvda")
        assert result == "NVDA", f"Expected 'NVDA', got '{result}'"


class TestLoadMcpConfig:
    """Test MCP configuration loading from .vscode/mcp.json."""

    def test_load_mcp_config_success(self):
        """Test successful loading of valid MCP config."""
        mock_config = {
            "servers": {
                "alphavantage": {
                    "type": "http",
                    "url": "http://localhost:3000"
                }
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .vscode directory and config file
            vscode_dir = Path(tmpdir) / ".vscode"
            vscode_dir.mkdir()
            config_file = vscode_dir / "mcp.json"

            with open(config_file, "w") as f:
                json.dump(mock_config, f)

            # Patch os.path.join to use our temp directory
            with patch("os.path.join") as mock_join:
                def join_side_effect(*args):
                    if ".vscode" in args:
                        return str(config_file)
                    return os.path.join(*args)

                mock_join.side_effect = join_side_effect

                with patch("os.path.exists", return_value=True):
                    with patch("builtins.open", create=True) as mock_open:
                        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(mock_config)

                        with patch("json.load", return_value=mock_config):
                            # Reset global cache
                            import hello_alpha_python_gradio
                            hello_alpha_python_gradio._cached_mcp_url = None

                            result = load_mcp_config_from_vscode("alphavantage")
                            assert result == "http://localhost:3000"

    def test_load_mcp_config_file_not_found(self):
        """Test error handling when config file is missing."""
        with patch("os.path.exists", return_value=False):
            import hello_alpha_python_gradio
            hello_alpha_python_gradio._cached_mcp_url = None

            with pytest.raises(FileNotFoundError) as exc_info:
                load_mcp_config_from_vscode("alphavantage")

            assert "Configuration profile missing" in str(exc_info.value)

    def test_load_mcp_config_server_not_found(self):
        """Test error when server name not in config."""
        mock_config = {
            "servers": {
                "otherserver": {
                    "type": "http",
                    "url": "http://example.com"
                }
            }
        }

        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", create=True):
                with patch("json.load", return_value=mock_config):
                    import hello_alpha_python_gradio
                    hello_alpha_python_gradio._cached_mcp_url = None

                    with pytest.raises(KeyError) as exc_info:
                        load_mcp_config_from_vscode("alphavantage")

                    assert "Target profile label" in str(exc_info.value)

    def test_load_mcp_config_invalid_type(self):
        """Test error when server type is not 'http'."""
        mock_config = {
            "servers": {
                "alphavantage": {
                    "type": "websocket",
                    "url": "ws://localhost:3000"
                }
            }
        }

        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", create=True):
                with patch("json.load", return_value=mock_config):
                    import hello_alpha_python_gradio
                    hello_alpha_python_gradio._cached_mcp_url = None

                    with pytest.raises(ValueError) as exc_info:
                        load_mcp_config_from_vscode("alphavantage")

                    assert "Invalid transport schema" in str(exc_info.value)


@pytest.mark.asyncio
class TestCallAlphaVantageMcp:
    """Test MCP server calls for stock quotes."""

    async def test_call_alpha_vantage_mcp_success(self):
        """Test successful MCP call returns stock quote."""
        mock_config = {
            "servers": {
                "alphavantage": {
                    "type": "http",
                    "url": "http://localhost:3000"
                }
            }
        }

        # Mock the MCP response
        mock_response = MagicMock()
        mock_response.isError = False
        mock_response.content = [MagicMock(text="AAPL: $150.00")]

        with patch("hello_alpha_python_gradio.load_mcp_config_from_vscode", return_value="http://localhost:3000"):
            with patch("hello_alpha_python_gradio.streamablehttp_client") as mock_client:
                mock_session = AsyncMock()
                mock_session.call_tool = AsyncMock(return_value=mock_response)
                mock_session.initialize = AsyncMock()

                # Set up context manager
                mock_client.return_value.__aenter__.return_value = (AsyncMock(), AsyncMock(), AsyncMock())

                # Mock ClientSession
                with patch("hello_alpha_python_gradio.ClientSession") as mock_cs:
                    mock_cs.return_value.__aenter__.return_value = mock_session

                    result = await call_alpha_vantage_mcp("AAPL")
                    assert "AAPL: $150.00" in result

    async def test_call_alpha_vantage_mcp_config_error(self):
        """Test MCP call handles config loading errors."""
        with patch("hello_alpha_python_gradio.load_mcp_config_from_vscode", side_effect=FileNotFoundError("Config missing")):
            result = await call_alpha_vantage_mcp("AAPL")
            assert "Configuration Error" in result
            assert "Config missing" in result

    async def test_call_alpha_vantage_mcp_empty_response(self):
        """Test MCP call handles empty response from server."""
        mock_response = MagicMock()
        mock_response.isError = False
        mock_response.content = []

        with patch("hello_alpha_python_gradio.load_mcp_config_from_vscode", return_value="http://localhost:3000"):
            with patch("hello_alpha_python_gradio.streamablehttp_client") as mock_client:
                mock_session = AsyncMock()
                mock_session.call_tool = AsyncMock(return_value=mock_response)
                mock_session.initialize = AsyncMock()

                mock_client.return_value.__aenter__.return_value = (AsyncMock(), AsyncMock(), AsyncMock())

                with patch("hello_alpha_python_gradio.ClientSession") as mock_cs:
                    mock_cs.return_value.__aenter__.return_value = mock_session

                    result = await call_alpha_vantage_mcp("AAPL")
                    assert "empty context payload" in result.lower()

    async def _run_with_mocks(self, mock_response):
        with patch("hello_alpha_python_gradio.load_mcp_config_from_vscode", return_value="http://localhost:3000"):
            with patch("hello_alpha_python_gradio.streamablehttp_client") as mock_client:
                mock_session = AsyncMock()
                mock_session.call_tool = AsyncMock(return_value=mock_response)
                mock_session.initialize = AsyncMock()
                mock_client.return_value.__aenter__.return_value = (AsyncMock(), AsyncMock(), AsyncMock())
                with patch("hello_alpha_python_gradio.ClientSession") as mock_cs:
                    mock_cs.return_value.__aenter__.return_value = mock_session
                    return await call_alpha_vantage_mcp("AAPL")

    async def test_call_alpha_vantage_mcp_server_error(self):
        """Test MCP call surfaces server-reported tool errors (isError=True)."""
        mock_response = MagicMock()
        mock_response.isError = True
        mock_response.content = [MagicMock(text="Invalid ticker")]

        result = await self._run_with_mocks(mock_response)
        assert "Tool Error" in result
        assert "Invalid ticker" in result

    async def test_call_alpha_vantage_mcp_non_text_content(self):
        """Test MCP call handles non-text content items without crashing."""
        mock_response = MagicMock()
        mock_response.isError = False
        # Items without a .text attribute (e.g. ImageContent)
        mock_response.content = [MagicMock(spec=[]), MagicMock(spec=[])]

        result = await self._run_with_mocks(mock_response)
        assert "no text content" in result.lower()


@pytest.mark.asyncio
class TestChatWithMcp:
    """Test chat interface with MCP integration."""

    async def test_chat_with_valid_ticker(self):
        """Test chat function with valid ticker extraction."""
        with patch("hello_alpha_python_gradio.call_alpha_vantage_mcp", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "Stock data here"

            result = await chat_with_mcp("What about TSLA?", [])

            assert isinstance(result, tuple)
            markdown, chart_html = result
            assert "TSLA" in markdown
            assert "Stock data here" in markdown
            mock_call.assert_called_once_with("TSLA")

    async def test_chat_with_invalid_input(self):
        """Test chat function with no extractable ticker."""
        result = await chat_with_mcp("Hello there, how are you?", [])

        assert isinstance(result, tuple)
        markdown, chart_html = result
        assert "couldn't isolate" in markdown.lower()


@pytest.mark.asyncio
class TestAnalyzeWithOpenai:
    """Test the OpenAI analysis wrapper."""

    async def test_missing_key_returns_none(self):
        assert await analyze_with_openai("quote", "AAPL") is None

    async def test_success_returns_parsed_payload(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        parsed_payload = {
            "analysis": "Bullish momentum.",
            "metrics": [{"label": "price", "value": 150.0}],
            "sentiment": {"label": "bullish", "score": 0.8},
        }

        fake_message = MagicMock()
        fake_message.parsed = parsed_payload
        fake_choice = MagicMock()
        fake_choice.message = fake_message
        fake_resp = MagicMock()
        fake_resp.choices = [fake_choice]

        fake_client = MagicMock()
        fake_client.beta.chat.completions.parse = AsyncMock(return_value=fake_resp)

        with patch("hello_alpha_python_gradio.AsyncOpenAI", return_value=fake_client):
            result = await analyze_with_openai("AAPL: $150.00", "AAPL")

        assert result == parsed_payload
        assert result["metrics"][0]["value"] == 150.0

    async def test_exception_returns_none(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        fake_client = MagicMock()
        fake_client.beta.chat.completions.parse = AsyncMock(side_effect=RuntimeError("boom"))

        with patch("hello_alpha_python_gradio.AsyncOpenAI", return_value=fake_client):
            assert await analyze_with_openai("quote", "AAPL") is None


class TestRenderAnalysisMarkdown:
    """Test the markdown renderer."""

    def test_with_parsed_payload(self):
        parsed = {
            "analysis": "Strong quarter.",
            "sentiment": {"label": "bullish", "score": 0.82},
        }
        md = render_analysis_markdown("AAPL", "AAPL: $150", parsed)
        assert "AAPL" in md
        assert "Strong quarter." in md
        assert "BULLISH" in md
        assert "0.82" in md

    def test_fallback_when_none(self):
        md = render_analysis_markdown("AAPL", "AAPL: $150", None)
        assert "AAPL: $150" in md
        assert "unavailable" in md.lower()


class TestRenderChartjsHtml:
    """Test the Chart.js HTML renderer."""

    def test_disabled_when_no_payload(self):
        out = render_chartjs_html(None, "AAPL")
        assert "disabled" in out

    def test_includes_canvas_and_cdn(self):
        parsed = {
            "metrics": [{"label": "price", "value": 150.0}],
            "sentiment": {"label": "bullish", "score": 0.8},
        }
        out = render_chartjs_html(parsed, "AAPL")
        assert "cdn.jsdelivr.net/npm/chart.js" in out
        assert 'id="av-metrics"' in out
        assert 'id="av-sentiment"' in out
        assert "JSON.parse(" in out

    def test_payload_is_escaped(self):
        """Model text must not be able to break out of the script context."""
        parsed = {
            "metrics": [{"label": "price</script><script>alert(1)</script>", "value": 1}],
            "sentiment": {"label": "neutral", "score": 0.5},
        }
        out = render_chartjs_html(parsed, "AAPL")
        assert "</script>" not in out.split("JSON.parse(")[1].split("');")[0]
        assert "&lt;/script&gt;" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
