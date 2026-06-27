# QA Test Coverage — hello-alpha-python-gradio

**Last updated:** 2026-06-27  
**Target module:** `alpha-vantage/hello-alpha-python-gradio.py`  
**Test file:** `alpha-vantage/test_hello_alpha.py`

## Overview

This document summarizes the high-level test scenario coverage for the Alpha Vantage MCP integration. The suite was streamlined to **10 critical tests** that validate primary application behavior under normal conditions. All negative-path tests (error handling, missing keys, failures, and protocol faults) have been removed, as has redundancy.

The retained tests cover the complete primary flow: input parsing → MCP data retrieval → AI analysis → result merging → output rendering, plus configuration resolution.

---

## 1. Ticker Extraction
*Class: `TestExtractTicker` · `test_extract_ticker_with_valid_symbol`*

- **Valid symbol extraction** – verifies that common ticker patterns (e.g., `TSLA`) are correctly isolated from natural-language user input.

---

## 2. MCP Configuration Loading
*Class: `TestLoadMcpConfig` · `test_load_mcp_config_success`*

- **Happy path** – loads a valid `.vscode/mcp.json` profile and resolves the HTTP endpoint.

---

## 3. MCP Protocol Transport
*Class: `TestCallAlphaVantageMcp` · `test_call_alpha_vantage_mcp_success`*

- **Successful quote retrieval** – simulates the MCP tool response and confirms the quote text is returned intact.

---

## 4. Chat Orchestration
*Class: `TestChatWithMcp` · `test_chat_with_valid_ticker`*

- **Valid user message** – end-to-end flow from ticker extraction through the MCP call to rendered markdown output.

---

## 5. OpenAI Analysis Wrapper
*Class: `TestAnalyzeWithOpenai` · `test_success_returns_parsed_payload`*

- **Successful structured response** – confirms that with a configured key, the OpenAI analysis returns the structured parsed payload under `AI_STATUS_OK`.

---

## 6. Markdown Rendering
*Class: `TestRenderAnalysisMarkdown` · `test_with_parsed_payload`*

- **Normal AI output** – renders ticker, sentiment label, confidence, and analysis text from a parsed AI payload.

---

## 7. Chart.js HTML Rendering
*Class: `TestRenderChartjsHtml` · `test_includes_canvas_and_cdn`*

- **DOM structure** – confirms the output is an `<iframe srcdoc="...">` containing the Chart.js CDN script and an injected JSON payload.

---

## 8. API Key Resolution (env-first → .env fallback)
*Class: `TestGetApiKey` · `test_env_var_takes_priority_over_dotenv`*

- **Env var priority** – an explicitly set environment variable always wins over a `.env` value.

---

## 9. Sentiment Score Blending
*Class: `TestBlendScores` · `test_agreeing_labels_preserves_label`*

- **Agreeing labels** – when both providers agree, the shared label is preserved and the average score is returned.

---

## 10. OpenAI / Grok Result Merging
*Class: `TestMergeResults` · `test_merge_both_present`*

- **Both providers present** – stitches sentiment via `_blend_scores`, preserves OpenAI analysis, and appends Grok social sources and volume bias.

---

## Removed Coverage

The following areas were removed because they verify negative paths (failures, missing input, missing keys, exception unwrapping, and protocol faults) rather than primary behavior:

- Multiple-symbol / no-symbol / lowercase ticker edge cases
- MCP config error paths (missing file, unknown server, invalid transport)
- MCP empty response, server-side error, and non-text content handling
- Unparseable chat input
- OpenAI missing-key, API-failure, and response-format contract checks
- Markdown missing-key / error / defensive / social-notes branches
- Chart key-missing / error / empty-payload notices and payload escaping
- API key fallback / missing-everywhere / immutability / quoted-value / integration checks
- Exception unwrapping (`TestUnwrapExceptions`) and protocol error reporting (`TestProtocolErrorReporting`)
- xAI/Grok key resolution, Grok analysis pipeline, and Grok toggle branches

---

## Execution Summary

| Metric | Value |
|--------|-------|
| Total tests executed | 10 |
| Passed | 10 |
| Failed | 0 |
| Primary entry point | `python -m pytest alpha-vantage/test_hello_alpha.py -q` |
