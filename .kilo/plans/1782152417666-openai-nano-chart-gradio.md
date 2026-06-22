# Plan: OpenAI "nano" Integration in Alpha Vantage Gradio App

## Goal
Extend `alpha-vantage/hello-alpha-python-gradio.py` to call an OpenAI model on the MCP stock quote, returning both a textual analysis and a Chart.js visualization (metrics bar chart + sentiment gauge).

## Decisions
- **Target app**: `alpha-vantage/hello-alpha-python-gradio.py` (Gradio).
- **Model**: `OPENAI_MODEL` env var, default `gpt-4o-mini`. (OpenAI has no "nano" model; `gpt-4o-mini` is the smallest/cheapest.)
- **SDK**: Official `openai` Python SDK, `AsyncOpenAI` (matches existing async architecture).
- **Chart library**: Chart.js (CDN) rendered through a `gr.HTML` Gradio component.
- **Chart content**: Model-derived metric breakdown + qualitative sentiment gauge.
- **Key storage**: `OPENAI_API_KEY` in `alpha-vantage/.env` (already gitignored), loaded by existing `python-dotenv` block; read via `os.environ`.
- **Missing key**: Graceful fallback — raw MCP quote only, charts omitted with a notice; chat still works.

## Architecture / Data Flow
```
User message
  -> extract_ticker()
  -> call_alpha_vantage_mcp(ticker)        # existing, returns quote text
  -> analyze_with_openai(quote, ticker)    # NEW: AsyncOpenAI, response_format=JSON schema
       returns { analysis: str,
                 metrics:  [{label, value}],
                 sentiment:{label, score} }
  -> render_analysis_markdown()            # NEW: text branch
  -> render_chartjs_html()                 # NEW: injects JSON into Chart.js template
  -> Gradio returns (markdown, html)
```

## Step-by-step tasks

### 1. Dependencies
Add to `alpha-vantage/requirements.txt`:
```
openai>=1.40.0
```
Chart.js needs no pip package — loaded from CDN at render time.

### 2. Secret handling
`alpha-vantage/.env` already loaded by the existing `load_dotenv(env_path)` block (hello-alpha-python-gradio.py:10-16). Add the key there:
```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```
- `.env` is already gitignored (.gitignore:108).
- Access via `os.environ.get("OPENAI_API_KEY")` and `os.environ.get("OPENAI_MODEL", "gpt-4o-mini")`.
- Never log the key; `_debug_log` may print model name and call success but never headers/key.

### 3. OpenAI client + invocation (`analyze_with_openai`)
New module-level async function. Pseudocode:
```python
from openai import AsyncOpenai
import os

MODEL_NAME = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

async def analyze_with_openai(quote_text: str, ticker: str) -> dict | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None  # caller falls back gracefully

    client = AsyncOpenAI(api_key=api_key)  # create per call (or cache at module level)
    schema = {
        "type": "object",
        "properties": {
            "analysis":  {"type": "string"},
            "metrics":   {"type": "array", "items": {"type": "object",
                          "properties": {
                              "label": {"type": "string"},
                              "value": {"type": "number"}}}},
            "sentiment": {"type": "object", "properties": {
                              "label": {"type": "string"},
                              "score": {"type": "number"}}}
        },
        "required": ["analysis", "metrics", "sentiment"],
        "additionalProperties": False
    }
    resp = await client.beta.chat.completions.parse(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": (
                "You are a financial analyst. Given a stock quote, return: "
                "(1) a concise 3-5 sentence analysis; "
                "(2) up to 6 numeric metrics (price, change_percent, volume_in_millions, "
                "pe_ratio, day_range_midpoint, etc.) using only numbers present or derivable "
                "from the quote; (3) a sentiment label (bullish|bearish|neutral) and score 0-1.")},
            {"role": "user", "content": f"Ticker: {ticker}\nQuote:\n{quote_text}"}
        ],
        response_format={"type": "json_schema", "json_schema": {
            "name": "stock_analysis", "schema": schema, "strict": True}}
    )
    return resp.choices[0].message.parsed  # dict
```
Wrap in try/except; on any error return `None` so the caller can fall back to raw quote.

### 4. Markdown renderer (`render_analysis_markdown`)
```python
def render_analysis_markdown(ticker: str, quote: str, parsed: dict | None) -> str:
    base = f"### Analysis for **{ticker}** via Workspace Protocol Hub:\n\n{quote}"
    if not parsed:
        return base + "\n\n_OpenAI analysis unavailable (set OPENAI_API_KEY in .env)._"
    sent = parsed.get("sentiment", {})
    return (
        f"{base}\n\n"
        f"#### AI Analysis ({sent.get('label','n/a').upper()}, "
        f"confidence {sent.get('score','n/a')})\n\n"
        f"{parsed.get('analysis','')}"
    )
```

### 5. Chart.js HTML renderer (`render_chartjs_html`)
Inject the validated JSON into a CDN template. Pseudocode:
```python
import json, html

CHART_TEMPLATE = """
<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
  .wrap{{font-family:"Courier New",monospace;color:#EAECEF;background:#0B0E11;padding:8px}}
  canvas{{max-width:480px}}
</style></head>
<body><div class="wrap">
  <canvas id="metrics"></canvas>
  <canvas id="sentiment"></canvas>
</div>
<script>
const DATA = __DATA__;
new Chart(document.getElementById('metrics'),{{
  type:'bar',
  data:{{labels:DATA.metrics.map(m=>m.label),
         datasets:[{{label:'Value',data:DATA.metrics.map(m=>m.value),
                     backgroundColor:'#1D4ED8'}}]}},
  options:{{plugins:{{legend:{{display:false}}}}}}
}});
const s=DATA.sentiment.score||0;
new Chart(document.getElementById('sentiment'),{{
  type:'doughnut',
  data:{{datasets:[{{data:[s,1-s],
                     backgroundColor:['#3AC569','#1F2730']}}]}},
  options:{{cutout:'70%',plugins:{{legend:{{display:false}}}}}}
}});
</script></body></html>
"""

def render_chartjs_html(parsed: dict | None, ticker: str) -> str:
    if not parsed:
        return "<!-- OpenAI analysis disabled: no API key -->"
    safe = {"ticker": ticker, "metrics": parsed.get("metrics", []),
            "sentiment": parsed.get("sentiment", {"label":"n/a","score":0})}
    payload = html.escape(json.dumps(safe))
    # embed escaped JSON, decode at runtime to avoid script-injection
    return CHART_TEMPLATE.replace("__DATA__", "JSON.parse('" + payload + "')")
```
Note: escape all user/model-controlled strings (`html.escape`) before embedding to prevent XSS via the injected HTML.

### 6. Wire into `chat_with_mcp` (hello-alpha-python-gradio.py:173)
Change the function to return a tuple for Gradio's `additional_output_components`. Replace:
```python
result = f"### Analysis for **{ticker}** ..."
return result
```
with:
```python
parsed = await analyze_with_openai(mcp_response, ticker)
markdown = render_analysis_markdown(ticker, mcp_response, parsed)
chart_html = render_chartjs_html(parsed, ticker)
return markdown, chart_html
```

### 7. Update the `gr.ChatInterface` (hello-alpha-python-gradio.py:198)
Add an HTML output component so the returned tuple renders:
```python
demo = gr.ChatInterface(
    fn=chat_with_mcp,
    title="Alpha Vantage Assistant",
    description="Async MCP stock quotes + OpenAI analysis with Chart.js visuals.",
    additional_outputs=[gr.HTML(label="Charts")],
    examples=["What's happening with TSLA?", "Check NVDA", "AAPL"]
)
```
(If the installed Gradio version lacks `additional_outputs`, fall back to a `gr.Blocks` layout with a `gr.Chatbot` + a state-bound `gr.HTML`. Confirm version during implementation.)

### 8. Tests (`alpha-vantage/test_hello_alpha.py`)
Add (using `pytest` + `pytest-asyncio`, monkeypatch):
- `test_render_analysis_markdown_with_parsed` — markdown contains sentiment + analysis text.
- `test_render_analysis_markdown_fallback` — `parsed=None` returns raw quote + notice.
- `test_render_chartjs_html_includes_canvas` — output contains `id="metrics"` and Chart.js CDN; JSON payload is escaped.
- `test_render_chartjs_html_disabled` — `parsed=None` returns the disabled comment.
- `test_analyze_with_openai_missing_key` — monkeypatch `os.environ` to drop key; returns `None`.
- `test_analyze_with_openai_success` — monkeypatch a fake `AsyncOpenAI` returning a fixed JSON dict; asserts schema fields present and no key logged.
- Update existing `TestChatWithMcp` so the chat function's tuple return is asserted.

### 9. Docs
Update `alpha-vantage/README.md` Environment Variables table to add:
```
OPENAI_API_KEY  -   OpenAI API key for AI analysis (omit to disable AI features)
OPENAI_MODEL    gpt-4o-mini  OpenAI model id
```

## Validation
1. `cd alpha-vantage; pip install -r requirements.txt`
2. `pytest test_hello_alpha.py -v` — all tests green.
3. Set `OPENAI_API_KEY` + `OPENAI_MODEL=gpt-4o-mini` in `.env`; start a mock MCP or live one; run `python hello-alpha-python-gradio.py`; query "TSLA" and confirm both the markdown analysis and the two Chart.js canvases render.
4. Unset `OPENAI_API_KEY`, restart, query again — chat returns raw quote + notice, no chart canvas, no errors.

## Risks / Open Items
- **Gradio `additional_outputs` availability**: depends on Gradio version (unpinned in requirements). If unsupported, switch to a `gr.Blocks` layout.
- **MCP quote shape variability**: `gpt-4o-mini` structured output will only populate metrics derivable from the quote text; some fields may be omitted. Renderer must tolerate empty `metrics` arrays.
- **CDN dependency**: Chart.js requires outbound internet at the browser; offline users see blank canvases. Acceptable for this tool.
- **Cost/latency**: each chat turn adds one model call; acceptable for a demo. No caching planned in v1.
