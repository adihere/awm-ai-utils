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


@pytest.mark.asyncio
class TestChatWithMcp:
    """Test chat interface with MCP integration."""

    async def test_chat_with_valid_ticker(self):
        """Test chat function with valid ticker extraction."""
        with patch("hello_alpha_python_gradio.call_alpha_vantage_mcp", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "Stock data here"

            result = await chat_with_mcp("What about TSLA?", [])

            assert "TSLA" in result
            assert "Stock data here" in result
            mock_call.assert_called_once_with("TSLA")

    async def test_chat_with_invalid_input(self):
        """Test chat function with no extractable ticker."""
        result = await chat_with_mcp("Hello there, how are you?", [])

        assert "couldn't isolate" in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
