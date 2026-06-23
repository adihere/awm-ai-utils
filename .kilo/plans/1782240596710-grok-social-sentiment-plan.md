# Grok x.ai Social Media Sentiment Integration — Technical Implementation Plan

## Goal

Add an optional x.ai (Grok) social-media-sentiment layer to `hello-alpha-python-gradio.py` via a Gradio `gr.Checkbox` UI toggle. When enabled, Grok supplements (not replaces) OpenAI: Grok handles social-media sentiment scoring; OpenAI retains core analysis. The normalized combined score is presented to the user.

---

## Affected Boundaries

| Layer | Current State | Post-Change |
|---|---|---|
| **UI** | `gr.ChatInterface` with no AI toggle | Adds `gr.Checkbox(label="Use Grok social sentiment", value=False)` to the ChatInterface footer via `additional_outputs` trick or a sibling `gr.Blocks` row |
| **Fetch pipeline** | Single `analyze_with_openai()` call | Conditional second parallel call: `analyze_with_grok(ticker)` when checkbox is True |
| **Data model** | `StockAnalysis.sentiment = {label, score}` | Unchanged externally; emitted score is a weighted blend of OpenAI (0.5) and Grok (0.5) when Grok is active, pure OpenAI score when disabled |
| **Env/config** | `OPENAI_API_KEY`, `OPENAI_MODEL` | `XAI_API_KEY` added; optional `XAI_MODEL` (default `grok-4.3`) in `.env` or env-var |
| **Dependencies** | `openai>=1.40.0` | Add `httpx` (or reuse existing HTTPX if present). `grok` uses xAI-compatible endpoint |

---

## Architectural Workflow

```
User submits message + checkbox state
    │
    ▼
extract_ticker(message)            ← unchanged
    │
    ▼
call_alpha_vantage_mcp(ticker)     ← unchanged
    ▼ returns quote_text
    │
    ▼
if use_grok:
    ┌─────────────────────────────────┐
    │ [Parallel]                       │
    │  Task A: analyze_with_openai()   │
    │  Task B: analyze_with_grok()     │
    └────────────┬────────────────────┘
                 │ both complete
                 ▼
         merge_sentiment(openai_result, grok_result)
                 │
                 ▼
         combined parsed dict
else:
    analyze_with_openai() only  ← unchanged
    │
    ▼
render_analysis_markdown()        ← unchanged (uses combined/original sent.)
render_chartjs_html()             ← unchanged
return (markdown, chart_html)
```

---

## Grok API Integration — `analyze_with_grok()`

### Authentication
- Read key via existing `get_api_key("XAI_API_KEY")` helper (supports env-var and `.env`, env wins).
- Endpoint: `https://api.x.ai/v1/chat/completions`
- Header: `Authorization: Bearer {XAI_API_KEY}`, `Content-Type: application/json`

### Request Contract
Model: `grok-4.3` (configurable via `XAI_MODEL`, same env-priority pattern as OpenAI).

```python
{
  "model": XAI_MODEL,
  "messages": [
    {
      "role": "system",
      "content": (
        "You are a financial sentiment analyst trained on social media discourse. "
        "Given a stock ticker and recent market context, return a JSON object with: "
        "(1) 'social_sources': a list of 2-3 representative themes found across "
        "social platforms (X/Twitter, Reddit, StockTwits); "
        "(2) 'sentiment': label (bullish|bearish|neutral) and confidence score 0-1; "
        "(3) 'volume_bias': 'high|moderate|low' — relative social discussion volume. "
        "Return ONLY valid JSON, no additional commentary."
      )
    },
    {"role": "user", "content": f"Ticker: {ticker}\nContext:\n{quote_text[:400]}"}
  ],
  "temperature": 0.3,
  "response_format": {"type": "json_object"}
}
```

`response_format: json_object` keeps output parseable without structured-output support (Grok provider uses OpenAI-compatible JSON mode, not Pydantic).

### Response Contract
```python
{
  "social_sources": ["Reddit bullish options flow", "X/Twitter earnings optimism", "StockTwits holder base strong"],
  "sentiment": {"label": "bullish", "score": 0.73},
  "volume_bias": "high"
}
```

### Rate Limiting
- x.ai free/pro tiers: existing quota. Implement same envelope as OpenAI — failure surfaces as `AI_STATUS_GK_ERROR` instead of aborting the whole request.
- No per-source throttling within the prompt; keep the request len(<400 chars quote) to minimize token spend.

---

## Data Mapping & Normalization — `merge_sentiment()`

### When Grok is DISABLED
Behavior identical to current code. `parsed.sentiment = openai_sentiment`.

### When Grok is ENABLED
```python
def _blend_scores(openai_label, openai_score, grok_label, grok_score) -> dict:
    """
    Blend OpenAI and Grok sentiment scores into the StockAnalysis contract.
    Weight: 50% OpenAI intrinsic, 50% Grok social.
    Disagreement resolution: if labels conflict, apply a penalty to confidence.
    """
    label_agreement = (openai_label == grok_label)
    blended_score = round(0.5 * openai_score + 0.5 * grok_score, 3)
    if not label_agreement:
        blended_score = round(blended_score * 0.8, 3)   # 20% penalty

    # Majority label wins; neutral if split
    if label_agreement:
        final_label = openai_label
    else:
        final_label = "neutral"
        blended_score = max(blended_score, 0.5)            # cap at weak-neutral

    # Publish social themes into the analysis text append
    return {"label": final_label, "score": blended_score}
```

### Display Format
The merged sentiment label/score is injected into the existing `render_analysis_markdown` header. Social themes are appended as a new subsection:

```
#### Social Sentiment (BULLISH, confidence 0.72)

**Social themes:** Reddit bullish options flow · X/Twitter earnings optimism

{AAPL analysis text}
```

When `grok_analysis` fails but `use_grok=True`, fall back to OpenAI-only sentiment with a visible notice:

> ℹ️ Social sentiment unavailable — falling back to core analysis only. Set `ALPHA_VANTAGE_DEBUG=true` to diagnose.

---

## Error-Handling & Status Codes

Current constants stay | Extended for Grok:

| Constant | Meaning | Wall Impact |
|---|---|---|
| `AI_STATUS_OK` | Both providers succeeded (or only OpenAI when toggle off) | Charts render, markdown renders full |
| `AI_STATUS_NO_KEY` | No `OPENAI_API_KEY` | Charts hidden, no markdown analysis header |
| `AI_STATUS_ERROR` | OpenAI call failed | Charts hidden, degraded markdown |
| **`AI_STATUS_GK_NO_KEY`** | *(new)* Toggle on but no `XAI_API_KEY` | Treated same as `AI_STATUS_OK` (Grok skipped, analysis via OpenAI only) with notice |
| **`AI_STATUS_GK_ERROR`** | *(new)* Grok call failed (network, 4xx, 5xx, rate limit) | Same wall: OpenAI still renders; markdown surfaces `AI_STATUS_GK_ERROR` with notice |
| **`AI_STATUS_DISABLED`** | *(new)* Toggle off (Grok explicitly skipped) | OpenAI-only path, no notice needed |

`chat_with_mcp` returns `(markdown, chart_html, grok_status)` using the gradio pattern:

```python
async def chat_with_mcp(message, history, use_grok=False):
    ...
    openai_parsed, openai_status = await analyze_with_openai(mcp_response, ticker)

    if use_grok and openai_status != AI_STATUS_NO_KEY:
        grok_parsed, grok_status, social_notes = await analyze_with_grok(mcp_response, ticker)
        if grok_status == AI_STATUS_OK:
            merged_parsed = _merge_results(openai_parsed, grok_parsed)
        else:
            merged_parsed = openai_parsed
            social_notes = _gk_error_note(grok_status)
    else:
        merged_parsed = openai_parsed
        grok_status = AI_STATUS_DISABLED if use_grok else AI_STATUS_DISABLED
        social_notes = None

    markdown = render_analysis_markdown(ticker, mcp_response, merged_parsed, openai_status, social_notes)
    chart_html = render_chartjs_html(merged_parsed, ticker, openai_status)
    return markdown, chart_html
```

---

## UI Addition — Gradio Checkbox

```python
with gr.Blocks() as demo:
    with gr.Row():
        ticker_input = gr.Textbox(label="Ticker", placeholder="e.g. AAPL")
        use_grok_cb = gr.Checkbox(label="Use Grok social sentiment", value=False)
    gr.ChatInterface(
        fn=chat_with_mcp,
        title="Alpha Vantage Assistant",
        description="Async MCP stock quotes + OpenAI analysis with optional Grok social sentiment.",
        additional_outputs=[charts_output],
        examples=[...],
    )
    charts_output.render()
```

`gr.ChatInterface` does **not** natively accept a checkbox input. Two approaches:

1. **Preferred:** Wrap `gr.ChatInterface` in `gr.Blocks` and add a top-level `gr.Row` containing a copy of the ChatInterface's own textbox (`chatbot` + `textbox` can be accessed via `.bot`/`.textbox` after `.render()`) plus the checkbox, or use the `chatbot` standalone pattern.

2. **Simpler fallback:** Replace `gr.ChatInterface` with a manual chat loop using `gr.Chatbot` + `gr.Textbox` + submit button. Gives full control over the checkbox input at the cost of losing ChatInterface's built-in examples/UX. **Recommended against** unless ChatInterface exposes the input component in the current Gradio version.

**Concrete implementation path (preferred):**
```python
with gr.Blocks() as demo:
    use_grok_cb = gr.Checkbox(label="Use Grok social sentiment", value=False)
    ci = gr.ChatInterface(
        fn=chat_with_mcp,
        title="...",
        additional_outputs=[charts_output],
    )
    ci.render()   # then attach checkbox above via gr.Row if possible
```

If the Gradio version in use does not wrap cleanly, the checkbox will be positioned to the right of the ChatInterface's default text input by injecting via `ci.textbox.parent` or overriding the render order. Accept a slight layout compromise if needed.

---

## Test Strategy

New test classes added to `test_hello_alpha.py` or a new `test_grok_sentiment.py`:

| Class | Tests | Notes |
|---|---|---|
| `TestAnalyzeWithGrok` | success, no-key, error, response-parse | Mock `httpx.AsyncClient.post` or a thin `_call_xai()` helper |
| `TestGrokKeyResolution` | env-var priority, `.env` fallback, none | Reuse `get_api_key` helper |
| `TestMergeSentiment` | agreeing labels, disagreeing labels, edge scores 0/1, neutral split | Pure-sync tests, no network |
| `TestChatWithGrokToggle` | toggle off (OpenAI only), toggle on + key, toggle on + no key, toggle on + error | Mock both providers |
| `TestGrokDisabledNoNotice` | verify no social-data notice when toggle is off | |
| `TestErrorCodes` | all 6 status constants surface correctly in markdown/chart | |

All new Grok tests use `monkeypatch.delenv("XAI_API_KEY", raising=False)` by default so they pass without a real key. Network is never hit.

Run: `pytest test_hello_alpha.py -v` (or `pytest -v` both files).

---

## Implementation Task Sequence (for executing agent)

1. **Add Grok helper functions** to `hello-alpha-python-gradio.py`:
   - `XAI_MODEL`, `AI_STATUS_GK_NO_KEY`, `AI_STATUS_GK_ERROR`, `AI_STATUS_DISABLED` constants
   - `get_api_key("XAI_API_KEY")` reuse (no new I/O code)
   - `_call_xai_chat_completions(ticker, quote_text)` — single-threaded `httpx` POST
   - `analyze_with_grok(quote_text, ticker)` → `(dict|None, str status, list|None social_notes)`
   - `_blend_scores(openai_sentiment, grok_sentiment)` → merged `{label, score}`
   - `_merge_results(openai_parsed, grok_parsed)` → single dict matching `StockAnalysis` shape

2. **Update `chat_with_mcp` signature**:
   - Add `use_grok: bool = False` parameter
   - Add conditional Grok branch
   - Pass `grok_status` to renderers

3. **Update renderers**:
   - `render_analysis_markdown(ticker, quote, parsed, status, social_notes=None)` — append social themes section
   - `render_chartjs_html` — unchanged (chart shows blended score)

4. **Update UI in `__main__` block**:
   - Add `gr.Checkbox` for `use_grok`
   - Wire checkbox as input to `chat_with_mcp`

5. **Add tests** (as above). Target ≥95% branch coverage on new code.

6. **Run existing test suite** — verify all 21 existing tests still pass unchanged.

7. **Update `requirements.txt`** — confirm `openai>=1.40.0` is present (it is — xAI endpoint uses same client); no new package strictly required if `httpx` is already a transitive dependency of `openai`. If not, add `httpx` explicitly.

---

## Dependencies Decision

`openai>=1.40.0` already imports `httpx` transitively in most environments. To avoid lockfile drift, attempt to reuse it. If `import httpx` fails in CI, add it explicitly to `requirements.txt`:

```
httpx>=0.25.0,<1.0
```

---

## Data Normalization Notes

- **Score normalization**: Both providers return 0-1 floats. No scaling needed before blending.
- **Label normalization**: Both return `bullish|bearish|neutral` with no other values expected. Defensive: `.lower().strip()` before comparison.
- **Quote truncation**: Grok prompt uses `quote_text[:400]` to keep token cost predictable; full quote forwarded to OpenAI (which already handles length internally).
- **Parallelism**: `asyncio.gather(openai_task, grok_task)` runs both provider calls concurrently. If either fails, the successful result is still usable — no all-or-nothing semantics required.

---

## Out of Scope

- Caching social-media data between sessions
- Persisting sentiment history to a database
- Multi-ticker batch sentiment
- OAuth / SSO for x.ai
- Rate-limit backoff/retry (one-shot fail-soft is sufficient for first iteration)

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `async def chat_with_mcp(message, history)` signature change breaks Gradio | New param `use_grok=False` is defaulted, so existing calls are unchanged |
| x.ai API changes or goes down | Defensive error path: `AI_STATUS_GK_ERROR` falls back to OpenAI-only output, user never sees a blank page |
| Gradio version mismatch on checkbox wiring | Document hook requirements; fallback: manual Chatbot + Textbox if ChatInterface blocks multi-input |
| Token cost with Grok 4.3 | Truncate quote to 400 chars in Grok prompt; disable toggle defaults to `False` |
