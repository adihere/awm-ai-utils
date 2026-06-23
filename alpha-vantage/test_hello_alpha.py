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
get_api_key = hello_alpha_python_gradio.get_api_key
AI_STATUS_OK = hello_alpha_python_gradio.AI_STATUS_OK
AI_STATUS_NO_KEY = hello_alpha_python_gradio.AI_STATUS_NO_KEY
AI_STATUS_ERROR = hello_alpha_python_gradio.AI_STATUS_ERROR


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

                    # Verify the corrected invocation: the Alpha Vantage MCP
                    # server uses a meta-tool interface, so we must call
                    # TOOL_CALL wrapping the GLOBAL_QUOTE function with a
                    # JSON-encoded arguments string (NOT a non-existent
                    # "get_stock_quote" tool).
                    mock_session.call_tool.assert_called_once()
                    call_kwargs = mock_session.call_tool.call_args
                    assert call_kwargs.kwargs.get("name") == "TOOL_CALL" or call_kwargs[1].get("name") == "TOOL_CALL"
                    args = call_kwargs.kwargs.get("arguments") or call_kwargs[1].get("arguments")
                    assert args["tool_name"] == "GLOBAL_QUOTE"
                    # Inner arguments must be a JSON string with a "symbol" key
                    parsed = json.loads(args["arguments"])
                    assert parsed == {"symbol": "AAPL"}

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

    async def test_missing_key_returns_no_key_status(self):
        """No key resolvable from env OR .env must yield NO_KEY status.

        Patches get_api_key so the test does not depend on whether a real
        .env file happens to exist beside the script under test.
        """
        with patch("hello_alpha_python_gradio.get_api_key", return_value=None):
            parsed, status = await analyze_with_openai("quote", "AAPL")
        assert parsed is None
        assert status == AI_STATUS_NO_KEY

    async def test_success_returns_parsed_payload(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        parsed_payload = {
            "analysis": "Bullish momentum.",
            "metrics": [{"label": "price", "value": 150.0}],
            "sentiment": {"label": "bullish", "score": 0.8},
        }

        # The SDK parses the response into a StockAnalysis Pydantic instance;
        # model_dump() then converts it back to a dict for the renderers.
        StockAnalysis = hello_alpha_python_gradio.StockAnalysis
        parsed_model = StockAnalysis.model_validate(parsed_payload)

        fake_message = MagicMock()
        fake_message.parsed = parsed_model
        fake_choice = MagicMock()
        fake_choice.message = fake_message
        fake_resp = MagicMock()
        fake_resp.choices = [fake_choice]

        fake_client = MagicMock()
        fake_client.beta.chat.completions.parse = AsyncMock(return_value=fake_resp)

        with patch("hello_alpha_python_gradio.AsyncOpenAI", return_value=fake_client):
            parsed, status = await analyze_with_openai("AAPL: $150.00", "AAPL")

        assert status == AI_STATUS_OK
        assert parsed == parsed_payload
        assert parsed["metrics"][0]["value"] == 150.0

    async def test_exception_returns_error_status(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        fake_client = MagicMock()
        fake_client.beta.chat.completions.parse = AsyncMock(side_effect=RuntimeError("boom"))

        with patch("hello_alpha_python_gradio.AsyncOpenAI", return_value=fake_client):
            parsed, status = await analyze_with_openai("quote", "AAPL")

        assert parsed is None
        assert status == AI_STATUS_ERROR

    async def test_response_format_is_pydantic_model(self, monkeypatch):
        """analyze_with_openai must pass the StockAnalysis Pydantic class
        directly into response_format (not a raw json_schema dict)."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        StockAnalysis = hello_alpha_python_gradio.StockAnalysis
        parsed_model = StockAnalysis.model_validate({
            "analysis": "ok",
            "metrics": [],
            "sentiment": {"label": "neutral", "score": 0.5},
        })

        fake_message = MagicMock()
        fake_message.parsed = parsed_model
        fake_choice = MagicMock()
        fake_choice.message = fake_message
        fake_resp = MagicMock()
        fake_resp.choices = [fake_choice]

        fake_client = MagicMock()
        fake_client.beta.chat.completions.parse = AsyncMock(return_value=fake_resp)

        with patch("hello_alpha_python_gradio.AsyncOpenAI", return_value=fake_client):
            await analyze_with_openai("quote", "AAPL")

        call_kwargs = fake_client.beta.chat.completions.parse.call_args.kwargs
        assert call_kwargs["response_format"] is StockAnalysis


class TestRenderAnalysisMarkdown:
    """Test the markdown renderer."""

    def test_with_parsed_payload(self):
        parsed = {
            "analysis": "Strong quarter.",
            "sentiment": {"label": "bullish", "score": 0.82},
        }
        md = render_analysis_markdown("AAPL", "AAPL: $150", parsed, AI_STATUS_OK)
        assert "AAPL" in md
        assert "Strong quarter." in md
        assert "BULLISH" in md
        assert "0.82" in md

    def test_no_key_warning_shows_quote_and_fix(self):
        """Missing key must still show the quote plus a clear, actionable warning."""
        md = render_analysis_markdown("AAPL", "AAPL: $150", None, AI_STATUS_NO_KEY)
        # Quote is always preserved.
        assert "AAPL: $150" in md
        # Clear, informative warning naming the missing key and the fix.
        assert "AI analysis unavailable" in md
        assert "OPENAI_API_KEY" in md
        assert ".env" in md

    def test_error_warning_shows_quote_and_diagnostics_hint(self):
        """A failed call must show the quote plus a distinct error warning."""
        md = render_analysis_markdown("AAPL", "AAPL: $150", None, AI_STATUS_ERROR)
        assert "AAPL: $150" in md
        assert "AI analysis unavailable" in md
        # Error branch points at diagnostics, not at the missing-key fix.
        assert "ALPHA_VANTAGE_DEBUG" in md

    def test_none_payload_with_ok_status_treated_as_error(self):
        """Defensive: parsed is None but status ok -> still warns (no crash)."""
        md = render_analysis_markdown("AAPL", "AAPL: $150", None, AI_STATUS_OK)
        assert "AAPL: $150" in md
        assert "unavailable" in md.lower()


class TestRenderChartjsHtml:
    """Test the Chart.js HTML renderer."""

    def test_no_key_renders_visible_notice(self):
        out = render_chartjs_html(None, "AAPL", AI_STATUS_NO_KEY)
        assert "Charts unavailable" in out
        assert "OPENAI_API_KEY" in out

    def test_error_renders_visible_notice(self):
        out = render_chartjs_html(None, "AAPL", AI_STATUS_ERROR)
        assert "Charts unavailable" in out

    def test_empty_payload_renders_visible_notice(self):
        out = render_chartjs_html(None, "AAPL", AI_STATUS_OK)
        assert "Charts unavailable" in out

    def test_includes_canvas_and_cdn(self):
        parsed = {
            "metrics": [{"label": "price", "value": 150.0}],
            "sentiment": {"label": "bullish", "score": 0.8},
        }
        out = render_chartjs_html(parsed, "AAPL")
        # The chart is delivered inside an iframe srcdoc so that Gradio's
        # innerHTML injection still executes the Chart.js scripts.
        assert out.startswith('<iframe srcdoc="') and out.endswith("</iframe>")
        assert "cdn.jsdelivr.net/npm/chart.js" in out
        # Markers are HTML-escaped within the srcdoc attribute.
        assert 'id=&quot;av-metrics&quot;' in out
        assert 'id=&quot;av-sentiment&quot;' in out
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


class TestGetApiKey:
    """Test get_api_key: env var priority, .env fallback, override safety."""

    def test_env_var_takes_priority_over_dotenv(self, monkeypatch, tmp_path):
        """When both env var and .env define the key, the env var wins."""
        env_file = tmp_path / ".env"
        env_file.write_text("OPENAI_API_KEY=from-dotenv-file\n")

        monkeypatch.setenv("OPENAI_API_KEY", "from-environment")
        result = get_api_key("OPENAI_API_KEY", env_path=str(env_file))
        assert result == "from-environment"

    def test_falls_back_to_dotenv_when_env_absent(self, monkeypatch, tmp_path):
        """With no env var, the .env file value is loaded and returned."""
        env_file = tmp_path / ".env"
        env_file.write_text("OPENAI_API_KEY=from-dotenv-file\n")

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = get_api_key("OPENAI_API_KEY", env_path=str(env_file))
        assert result == "from-dotenv-file"

    def test_returns_none_when_key_nowhere(self, monkeypatch, tmp_path):
        """None when the key is absent from both env and .env."""
        env_file = tmp_path / ".env"
        env_file.write_text("SOME_OTHER_KEY=irrelevant\n")

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = get_api_key("OPENAI_API_KEY", env_path=str(env_file))
        assert result is None

    def test_env_var_not_overwritten_by_dotenv(self, monkeypatch, tmp_path):
        """load_dotenv(override=False) must not clobber an existing env var.

        Regression guard: calling get_api_key should never change the value
        already present in os.environ, even if the .env file disagrees.
        """
        env_file = tmp_path / ".env"
        env_file.write_text("OPENAI_API_KEY=should-not-win\n")

        monkeypatch.setenv("OPENAI_API_KEY", "real-env-value")
        result = get_api_key("OPENAI_API_KEY", env_path=str(env_file))
        assert result == "real-env-value"
        # The process environment must be untouched after the call.
        assert os.environ["OPENAI_API_KEY"] == "real-env-value"

    def test_quoted_dotenv_values_are_stripped(self, monkeypatch, tmp_path):
        """python-dotenv strips surrounding quotes from .env values."""
        env_file = tmp_path / ".env"
        env_file.write_text('OPENAI_API_KEY="sk-quoted"\n')

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = get_api_key("OPENAI_API_KEY", env_path=str(env_file))
        assert result == "sk-quoted"

    def test_analyze_uses_get_api_key(self, monkeypatch, tmp_path):
        """analyze_with_openai must route key lookup through get_api_key so the
        env-var-over-.env precedence applies to the AI pipeline."""
        env_file = tmp_path / ".env"
        env_file.write_text("OPENAI_API_KEY=from-dotenv-file\n")

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        captured = {}

        def fake_get(key_name="OPENAI_API_KEY", env_path=None):
            captured["called"] = True
            return None

        with patch("hello_alpha_python_gradio.get_api_key", side_effect=fake_get):
            import asyncio
            asyncio.run(analyze_with_openai("quote", "AAPL"))

        assert captured.get("called") is True


class TestUnwrapExceptions:
    """Test recursive unwrapping of nested ExceptionGroups.

    The MCP streamable-HTTP transport wraps the real error (e.g.
    McpError) inside multiple layers of ExceptionGroup. The unwrapper must
    recurse to surface the actionable root cause instead of the opaque
    "unhandled errors in a TaskGroup" message.
    """

    def test_unwraps_single_exception(self):
        leaf = RuntimeError("Session terminated")
        result = hello_alpha_python_gradio._unwrap_exceptions(leaf)
        assert result == ["RuntimeError: Session terminated"]

    def test_unwraps_one_level_exception_group(self):
        leaf = ValueError("bad ticker")
        group = ExceptionGroup("outer", [leaf])
        result = hello_alpha_python_gradio._unwrap_exceptions(group)
        assert result == ["ValueError: bad ticker"]

    def test_unwraps_deeply_nested_exception_groups(self):
        # Mirrors the real failure shape: ExceptionGroup(ExceptionGroup(McpError))
        class McpError(Exception):
            pass

        leaf = McpError("Session terminated")
        inner = ExceptionGroup("inner", [leaf])
        outer = ExceptionGroup("outer", [inner])
        result = hello_alpha_python_gradio._unwrap_exceptions(outer)
        assert len(result) == 1
        assert "Session terminated" in result[0]
        assert "McpError" in result[0]

    def test_unwraps_multiple_leaves(self):
        leaves = [ValueError("a"), KeyError("b")]
        group = ExceptionGroup("grp", leaves)
        result = hello_alpha_python_gradio._unwrap_exceptions(group)
        assert "ValueError: a" in result
        assert "KeyError: 'b'" in result


@pytest.mark.asyncio
class TestProtocolErrorReporting:
    """Test that protocol errors surface the real root cause to the user."""

    async def _run_with_call_tool_raising(self, exc):
        with patch("hello_alpha_python_gradio.load_mcp_config_from_vscode", return_value="http://localhost:3000"):
            with patch("hello_alpha_python_gradio.streamablehttp_client") as mock_client:
                mock_session = AsyncMock()
                mock_session.call_tool = AsyncMock(side_effect=exc)
                mock_session.initialize = AsyncMock()
                mock_client.return_value.__aenter__.return_value = (AsyncMock(), AsyncMock(), AsyncMock())
                with patch("hello_alpha_python_gradio.ClientSession") as mock_cs:
                    mock_cs.return_value.__aenter__.return_value = mock_session
                    return await call_alpha_vantage_mcp("AAPL")

    async def test_nested_exception_group_surfaces_leaf_cause(self):
        """Reproduces the reported NVDA failure shape and verifies the leaf
        cause ('Session terminated') is surfaced instead of the opaque
        'unhandled errors in a TaskGroup' wrapper."""
        class McpError(Exception):
            pass

        leaf = McpError("Session terminated")
        inner = ExceptionGroup("unhandled errors in a TaskGroup (1 sub-exception)", [leaf])
        outer = ExceptionGroup("unhandled errors in a TaskGroup (1 sub-exception)", [inner])

        result = await self._run_with_call_tool_raising(outer)

        assert "Protocol Transport Fault" in result
        assert "Session terminated" in result
        # The opaque wrapper message must NOT be the only thing reported
        assert result.count("unhandled errors in a TaskGroup") <= 0 or "Session terminated" in result

    async def test_plain_exception_surfaces_type_and_message(self):
        result = await self._run_with_call_tool_raising(ConnectionError("refused"))
        assert "Protocol Transport Fault" in result
        assert "ConnectionError" in result
        assert "refused" in result


class TestBlendScores:
    """Test sentiment score blending between OpenAI and Grok."""

    def test_agreeing_labels_preserves_label(self):
        blend = hello_alpha_python_gradio._blend_scores("bullish", 0.8, "bullish", 0.9)
        assert blend["label"] == "bullish"
        assert abs(blend["score"] - 0.85) < 0.01

    def test_disagreeing_labels_penalizes_score(self):
        blend = hello_alpha_python_gradio._blend_scores("bullish", 0.9, "bearish", 0.9)
        assert blend["label"] == "neutral"
        assert abs(blend["score"] - 0.72) < 0.01

    def test_disagreeing_caps_at_neutral(self):
        blend = hello_alpha_python_gradio._blend_scores("bullish", 1.0, "bearish", 1.0)
        assert blend["label"] == "neutral"
        assert blend["score"] >= 0.5

    def test_neutral_labels_agree(self):
        blend = hello_alpha_python_gradio._blend_scores("neutral", 0.5, "neutral", 0.6)
        assert blend["label"] == "neutral"
        assert abs(blend["score"] - 0.55) < 0.01


class TestMergeResults:
    """Test merging OpenAI and Grok parsed outputs."""

    def test_merge_both_present(self):
        openai_parsed = {
            "analysis": "OpenAI read.",
            "sentiment": {"label": "bullish", "score": 0.7},
        }
        grok_parsed = {
            "social_sources": ["Reddit flow", "X optimism"],
            "sentiment": {"label": "bullish", "score": 0.8},
            "volume_bias": "high",
        }
        merged = hello_alpha_python_gradio._merge_results(openai_parsed, grok_parsed)
        assert merged["analysis"] == "OpenAI read."
        assert merged["social_sources"] == ["Reddit flow", "X optimism"]
        assert merged["volume_bias"] == "high"
        assert merged["sentiment"]["label"] == "bullish"
        assert abs(merged["sentiment"]["score"] - 0.75) < 0.01

    def test_merge_falls_back_to_grok_only_sentiment(self):
        openai_parsed = {"analysis": "OpenAI read."}
        grok_parsed = {
            "social_sources": ["StockTwits"],
            "sentiment": {"label": "bearish", "score": 0.6},
            "volume_bias": "moderate",
        }
        merged = hello_alpha_python_gradio._merge_results(openai_parsed, grok_parsed)
        assert merged["sentiment"]["label"] == "bearish"
        assert abs(merged["sentiment"]["score"] - 0.6) < 0.01


class TestGrokKeyResolution:
    """Test get_api_key for XAI_API_KEY."""

    def test_env_var_takes_priority(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("XAI_API_KEY=from-dotenv\n")
        monkeypatch.setenv("XAI_API_KEY", "from-env")
        result = hello_alpha_python_gradio.get_api_key("XAI_API_KEY", env_path=str(env_file))
        assert result == "from-env"

    def test_falls_back_to_dotenv(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("XAI_API_KEY=from-dotenv\n")
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        result = hello_alpha_python_gradio.get_api_key("XAI_API_KEY", env_path=str(env_file))
        assert result == "from-dotenv"


@pytest.mark.asyncio
class TestAnalyzeWithGrok:
    """Test analyze_with_grok error paths and happy path."""

    async def test_no_key_returns_gk_no_key(self, monkeypatch):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        with patch("hello_alpha_python_gradio.get_api_key", return_value=None):
            parsed, status, social = await hello_alpha_python_gradio.analyze_with_grok("quote", "AAPL")
        assert parsed is None
        assert status == hello_alpha_python_gradio.AI_STATUS_GK_NO_KEY
        assert social is None

    async def test_success_returns_parsed(self, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "sk-test")
        payload = {
            "social_sources": ["Reddit"],
            "sentiment": {"label": "bullish", "score": 0.7},
            "volume_bias": "high",
        }

        with patch("hello_alpha_python_gradio._call_xai_chat_completions", new_callable=AsyncMock, return_value={
            "choices": [{"message": {"content": json.dumps(payload)}}],
        }):
            parsed, status, social = await hello_alpha_python_gradio.analyze_with_grok("quote", "AAPL")
        assert status == hello_alpha_python_gradio.AI_STATUS_OK
        assert parsed["sentiment"]["label"] == "bullish"
        assert social == ["Reddit"]

    async def test_exception_returns_gk_error(self, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "sk-test")
        with patch("hello_alpha_python_gradio._call_xai_chat_completions", side_effect=RuntimeError("boom")):
            parsed, status, social = await hello_alpha_python_gradio.analyze_with_grok("quote", "AAPL")
        assert parsed is None
        assert status == hello_alpha_python_gradio.AI_STATUS_GK_ERROR
        assert social is None


@pytest.mark.asyncio
class TestChatWithGrokToggle:
    """Test chat_with_mcp with the use_grok flag."""

    async def test_toggle_off_skips_grok(self):
        with patch("hello_alpha_python_gradio.call_alpha_vantage_mcp", new_callable=AsyncMock, return_value="quote"):
            with patch("hello_alpha_python_gradio.analyze_with_openai", new_callable=AsyncMock) as mock_openai:
                mock_openai.return_value = ({"analysis": "ok", "sentiment": {"label": "neutral", "score": 0.5}}, hello_alpha_python_gradio.AI_STATUS_OK)
                with patch("hello_alpha_python_gradio.analyze_with_grok", new_callable=AsyncMock) as mock_grok:
                    md, chart = await chat_with_mcp("AAPL", [], use_grok=False)
                    mock_grok.assert_not_called()

    async def test_toggle_on_calls_grok(self):
        with patch("hello_alpha_python_gradio.call_alpha_vantage_mcp", new_callable=AsyncMock, return_value="quote"):
            with patch("hello_alpha_python_gradio.analyze_with_openai", new_callable=AsyncMock) as mock_openai:
                mock_openai.return_value = ({"analysis": "ok", "sentiment": {"label": "neutral", "score": 0.5}}, hello_alpha_python_gradio.AI_STATUS_OK)
                with patch("hello_alpha_python_gradio.analyze_with_grok", new_callable=AsyncMock) as mock_grok:
                    mock_grok.return_value = ({"social_sources": [], "sentiment": {"label": "bullish", "score": 0.6}}, hello_alpha_python_gradio.AI_STATUS_OK, [])
                    md, chart = await chat_with_mcp("AAPL", [], use_grok=True)
                    mock_grok.assert_called_once()

    async def test_grok_no_key_uses_openai_only(self):
        with patch("hello_alpha_python_gradio.call_alpha_vantage_mcp", new_callable=AsyncMock, return_value="quote"):
            with patch("hello_alpha_python_gradio.analyze_with_openai", new_callable=AsyncMock) as mock_openai:
                mock_openai.return_value = ({"analysis": "ok", "sentiment": {"label": "neutral", "score": 0.5}}, hello_alpha_python_gradio.AI_STATUS_OK)
                with patch("hello_alpha_python_gradio.analyze_with_grok", new_callable=AsyncMock) as mock_grok:
                    mock_grok.return_value = (None, hello_alpha_python_gradio.AI_STATUS_GK_NO_KEY, None)
                    md, chart = await chat_with_mcp("AAPL", [], use_grok=True)
                    assert "XAI_API_KEY not configured" in md
                    assert "ok" in md


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
