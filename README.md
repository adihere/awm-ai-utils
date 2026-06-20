# awm-ai-utils

Asset wealth management utilities with a Yahoo Finance dashboard and Alpha Vantage MCP integration.

## Yahoo Finance Dashboard (`yahoo-finance-wrap/`)

A Streamlit-based stock performance dashboard with technical analysis, fundamental analysis, and portfolio risk metrics.

### Running the Application

```bash
cd yahoo-finance-wrap
streamlit run yf.py
```

The dashboard provides:
- Technical workspace (candlestick charts, RSI, MACD oscillator)
- Fundamental analysis (peer valuation, earnings, free cash flow)
- Portfolio & risk metrics (weight distribution, correlation heatmap)

### Running Tests

```bash
cd yahoo-finance-wrap
pytest test_yf.py -v
```

## Alpha Vantage MCP Integration (`alpha-vantage/`)

A Gradio-based chat interface for querying stock quotes via MCP protocol.

### Running the Application

```bash
cd alpha-vantage
python hello-alpha-python-gradio.py
```

Requires `.vscode/mcp.json` with an `alphavantage` server configuration.

### Running Tests

```bash
cd alpha-vantage
pytest test_hello_alpha.py -v
```

## Installation

Install dependencies for each module:

```bash
pip install yfinance streamlit altair pandas pytest
# For alpha-vantage
pip install gradio python-dotenv
``` 
