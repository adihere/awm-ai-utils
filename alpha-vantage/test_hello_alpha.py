"""
Pytest test suite for Alpha Vantage MCP integration.
Ten critical tests covering primary application behavior without redundant or
negative-path verification.
"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

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

script_path = Path(__file__).resolve().parent / "hello-alpha-python-gradio.py"
spec = importlib.util.spec_from_file_location("hello_alpha_python_gradio", script_path)
hello_alpha_python_gradio = importlib.util.module_from_spec(spec)
sys.modules["hello_alpha_python_gradio"] = hello_alpha_python_gradio
spec.loader.exec_module(hello_alpha_python_gradio)

extract_ticker = hello_alpha_python_gradio.extract_ticker
load_mcp_config_from_vscode = hello_alpha_python_gradio.load_mcp_config_from_vscode
call_alpha_vantage_mcp = hello_alpha_python_gradio.call_alpha_vantage_mcp
chat_with_mcp = hello_alpha_python_gradio.chat_with_mcp
analyze_with_openai = hello_alpha_python_gradio.analyze_with_openai
render_analysis_markdown = hello_alpha_python_gradio.render_analysis_markdown
render_chartjs_html = hello_alpha_python_gradio.render_chartjs_html
get_api_key = hello_alpha_python_gradio.get_api_key
AI_STATUS_OK = hello_alpha_python_gradio.AI_STATUS_OK
AI_STATUS_NO_KEY = hello_alpha_python_gradio.AI_STATUS_NO_KEY
AI_STATUS_ERROR = hello_alpha_python_gradio.AI_STATUS_ERROR
StockAnalysis = hello_alpha_python_gradio.StockAnalysis


@pytest.fixture(autouse=True)
def _no_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


class TestExtractTicker:
    """Core: normal user messages are parsed into valid ticker symbols."""

    def test_extract_ticker_with_valid_symbol(self):
        result = extract_ticker("What's happening with TSLA?")
        assert result == "TSLA"


class TestLoadMcpConfig:
    """Core: valid MCP configuration is loaded and the endpoint is resolved."""

    def test_load_mcp_config_success(self):
        mock_config = {
            "servers": {
                "alphavantage": {
                    "type": "http",
                    "url": "http://localhost:3000"
                }
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            vscode_dir = Path(tmpdir) / ".vscode"
            vscode_dir.mkdir()
            config_file = vscode_dir / "mcp.json"
            with open(config_file, "w") as f:
                json.dump(mock_config, f)

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
                            import hello_alpha_python_gradio
                            hello_alpha_python_gradio._cached_mcp_url = None
                            result = load_mcp_config_from_vscode("alphavantage")
                            assert result == "http://localhost:3000"


@pytest.mark.asyncio
class TestCallAlphaVantageMcp:
    """Core: MCP protocol call returns a stock quote on success."""

    async def test_call_alpha_vantage_mcp_success(self):
        mock_response = MagicMock()
        mock_response.isError = False
        mock_response.content = [MagicMock(text="AAPL: $150.00")]

        with patch("hello_alpha_python_gradio.load_mcp_config_from_vscode", return_value="http://localhost:3000"):
            with patch("hello_alpha_python_gradio.streamablehttp_client") as mock_client:
                mock_session = AsyncMock()
                mock_session.call_tool = AsyncMock(return_value=mock_response)
                mock_session.initialize = AsyncMock()
                mock_client.return_value.__aenter__.return_value = (AsyncMock(), AsyncMock(), AsyncMock())

                with patch("hello_alpha_python_gradio.ClientSession") as mock_cs:
                    mock_cs.return_value.__aenter__.return_value = mock_session
                    result = await call_alpha_vantage_mcp("AAPL")
                    assert "AAPL: $150.00" in result


@pytest.mark.asyncio
class TestChatWithMcp:
    """Core: end-to-end chat flow extracts ticker, calls MCP, and returns markdown."""

    async def test_chat_with_valid_ticker(self):
        with patch("hello_alpha_python_gradio.call_alpha_vantage_mcp", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "Stock data here"
            result = await chat_with_mcp("What about TSLA?", [])
            assert isinstance(result, tuple)
            markdown, chart_html = result
            assert "TSLA" in markdown
            assert "Stock data here" in markdown
            mock_call.assert_called_once_with("TSLA")


@pytest.mark.asyncio
class TestAnalyzeWithOpenai:
    """Core: OpenAI analysis returns structured parsed output when key is present."""

    async def test_success_returns_parsed_payload(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        parsed_payload = {
            "analysis": "Bullish momentum.",
            "metrics": [{"label": "price", "value": 150.0}],
            "sentiment": {"label": "bullish", "score": 0.8},
        }
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
            parsed, status = await analyze_with_openai("TSLA: $150.00", "TSLA")
        assert status == AI_STATUS_OK
        assert parsed == parsed_payload


class TestRenderAnalysisMarkdown:
    """Core: markdown renderer emits AI analysis, sentiment, and optional social themes."""

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


class TestRenderChartjsHtml:
    """Core: chart renderer produces valid iframe-srcdoc HTML with Chart.js payload."""

    def test_includes_canvas_and_cdn(self):
        parsed = {
            "metrics": [{"label": "price", "value": 150.0}],
            "sentiment": {"label": "bullish", "score": 0.8},
        }
        out = render_chartjs_html(parsed, "AAPL")
        assert out.startswith('<iframe srcdoc="') and out.endswith("</iframe>")
        assert "cdn.jsdelivr.net/npm/chart.js" in out
        assert "JSON.parse(" in out


class TestGetApiKey:
    """Core: an explicitly set environment variable takes precedence over .env."""

    def test_env_var_takes_priority_over_dotenv(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("OPENAI_API_KEY=from-dotenv-file\n")
        monkeypatch.setenv("OPENAI_API_KEY", "from-environment")
        result = get_api_key("OPENAI_API_KEY", env_path=str(env_file))
        assert result == "from-environment"


class TestBlendScores:
    """Core: agreeing sentiment labels are preserved and average score is returned."""

    def test_agreeing_labels_preserves_label(self):
        blend = hello_alpha_python_gradio._blend_scores("bullish", 0.8, "bullish", 0.9)
        assert blend["label"] == "bullish"
        assert abs(blend["score"] - 0.85) < 0.01


class TestMergeResults:
    """Core: OpenAI and Grok parsed outputs are combined correctly."""

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
