# QA Test Coverage — hello-alpha-python-gradio

**Last updated:** 2026-06-27  
**Target module:** `alpha-vantage/hello-alpha-python-gradio.py`  
**Test file:** `alpha-vantage/test_hello_alpha.py`

## Overview

This document summarizes the high-level test scenario coverage for the Alpha Vantage MCP integration. The suite exercises the Gradio chat interface, MCP protocol transport, OpenAI and xAI/Grok analysis pipelines, rendering layers, environment variable resolution, and error-handling paths.

---

## 1. Ticker Extraction
*Class: `TestExtractTicker`*

- **Valid symbol extraction** – verifies that common ticker patterns (e.g., `TSLA`) are correctly isolated from natural language.
- **Multiple symbols** – confirms the chosen ticker is preferred over common dictionary words.
- **No valid symbol** – returns `None` when input contains no recognizable ticker.
- **Lowercase normalization** – ensures lower-case inputs are uppercased and still resolved.

---

## 2. MCP Configuration Loading
*Class: `TestLoadMcpConfig`*

- **Happy path** – loads a valid `.vscode/mcp.json` profile and resolves the HTTP endpoint.
- **Missing file** – raises `FileNotFoundError` with a clear message when the config file is absent.
- **Unknown server** – raises `KeyError` when the requested server name is not defined.
- **Invalid transport** – rejects server profiles whose `type` is not `http`.

---

## 3. MCP Protocol Transport
*Class: `TestCallAlphaVantageMcp`*

- **Successful quote retrieval** – simulates the MCP tool response and confirms the quote text is returned intact.
- **Config errors** – propagates configuration load failures as a user-facing error block.
- **Empty response** – handles the server returning an empty content payload gracefully.
- **Server-side tool error** – surfaces `isError=True` responses with the server detail.
- **Non-text content** – tolerates content items lacking a `.text` attribute without crashing.

---

## 4. Chat Orchestration
*Class: `TestChatWithMcp`*

- **Valid user message** – end-to-end flow from ticker extraction through MCP call to rendered markdown.
- **Unparseable input** – returns a helpful error when no ticker can be extracted.

---

## 5. OpenAI Analysis Wrapper
*Class: `TestAnalyzeWithOpenai`*

- **Missing API key** – yields `AI_STATUS_NO_KEY` when no key is resolvable from env or `.env`.
- **Successful structured response** – validates that the Pydantic model is passed into `response_format` and the parsed payload is returned.
- **API failure** – maps request exceptions to `AI_STATUS_ERROR` with `None` payload.
- **Response format contract** – guards that the SDK receives the Pydantic class directly.

---

## 6. Markdown Rendering
*Class: `TestRenderAnalysisMarkdown`*

- **Normal AI output** – renders ticker, sentiment label, confidence, analysis text, and optional social themes.
- **Missing-key warning** – always shows the raw quote and an actionable `.env` fix hint.
- **Error warning** – distinguishes an API failure from a missing key and points the user to diagnostics.
- **Defensive safety** – treats `None` payload with `AI_STATUS_OK` as unavailable.
- **Social themes** – displays the social-source list when present.
- **Social notes** – prefixes the rendered block with an informational notice when provided.

---

## 7. Chart.js HTML Rendering
*Class: `TestRenderChartjsHtml`*

- **Key missing / error / empty payload** – renders a styled "Charts unavailable" notice instead of going silent.
- **DOM structure** – confirms the output is an `<iframe srcdoc="...">` containing the Chart.js CDN script.
- **Payload escaping** – verifies that model-controlled text is HTML-escaped inside the `srcdoc` attribute to prevent script injection.

---

## 8. API Key Resolution (env-first → .env fallback)
*Class: `TestGetApiKey`*

- **Env var priority** – an explicitly set environment variable always wins over a `.env` value.
- **Fallback to `.env`** – when env var is absent, the `.env` value is loaded and returned.
- **Missing everywhere** – returns `None` when neither source defines the key.
- **Env var immutability** – confirms `.env` loading does not overwrite an already-set process variable.
- **Quoted values** – `python-dotenv`-style quoted values are stripped before returning.
- **Integration with analyzer** – `analyze_with_openai` routes key lookups through the resolver, ensuring env-first precedence.

---

## 9. Exception Unwrapping
*Class: `TestUnwrapExceptions`*

- **Single exception** – a plain exception returns itself.
- **One-level group** – unwraps one `ExceptionGroup` to its leaf.
- **Deeply nested groups** – recurses through multiple layers of `ExceptionGroup` to reach the actionable leaf.
- **Multiple leaves** – collects several distinct leaf messages from a single container.

---

## 10. Protocol Error Reporting
*Class: `TestProtocolErrorReporting`*

- **Nested exception groups** – verifies that the opaque `"unhandled errors in a TaskGroup"` wrapper does not hide the real root cause (`"Session terminated"`).
- **Plain network failures** – surfaces `ConnectionError` type and message.

---

## 11. Sentiment Score Blending
*Class: `TestBlendScores`*

- **Agreeing labels** – preserves the shared label and returns the average score.
- **Disagreeing labels** – down-weights the blended score by 20 % and resolves to `"neutral"`.
- **Neutral agreement** – averages neutral scores normally.
- **Extreme inputs** – handles `0.0` and `1.0` scores on either side.
- **Case insensitivity** – compares labels case-insensitively.
- **Zero/one penalized disagreement** – guarantees the blended score does not drop below the neutral floor after the 0.8 multiplier.

---

## 12. OpenAI / Grok Result Merging
*Class: `TestMergeResults`*

- **Both providers present** – stitches sentiment via `_blend_scores`, preserves OpenAI analysis, appends Grok social sources and volume bias.
- **Grok-only sentiment** – falls back to Grok sentiment when OpenAI omits it.
- **Both missing sentiment** – omits the sentiment key entirely.
- **Metric preservation** – OpenAI metrics pass through the merge unchanged.

---

## 13. xAI / Grok Key Resolution
*Class: `TestGrokKeyResolution`*

- **Env var priority** – mirrors the same precedence rules as `get_api_key` for `XAI_API_KEY`.
- **Fallback to `.env`** – loads `XAI_API_KEY` from the `.env` file when absent from the environment.
- **Missing everywhere** – `get_xai_api_key` and the underlying `get_api_key` return `None`.
- **Delegation** – `get_xai_api_key` forwards calls to `get_api_key("XAI_API_KEY")`.

---

## 14. Grok Analysis Pipeline
*Class: `TestAnalyzeWithGrok`*

- **No key** – returns `AI_STATUS_GK_NO_KEY`.
- **Successful analysis** – parses the Grok JSON response into the expected social-sentiment contract.
- **Request failure** – catches exceptions and returns `AI_STATUS_GK_ERROR`.

---

## 15. Grok Toggle in Chat Flow
*Class: `TestChatWithGrokToggle`*

- **Grok disabled** – OpenAI analysis proceeds; Grok is never invoked.
- **Grok enabled** – both providers are called when OpenAI succeeds.
- **Grok missing key** – chat still succeeds using OpenAI only; a social-sentiment warning appears.
- **OpenAI failure with Grok success** – Grok runs but its data is not rendered when the overall status is an OpenAI error.
- **Both providers fail** – renders an unavailability notice while preserving the quote via the error branch.

---

## Execution Summary

| Metric | Value |
|--------|-------|
| Total tests executed | 67 |
| Passed | 67 |
| Failed | 0 |
| Primary entry point | `python -m pytest alpha-vantage/test_hello_alpha.py -q` |
