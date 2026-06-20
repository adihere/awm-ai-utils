# AWM AI Utils

Asset wealth management utilities with comprehensive financial analysis tools, including a professional Bloomberg-style terminal for Yahoo Finance data and an Alpha Vantage MCP integration for AI-powered stock queries.

## 🚀 Overview

This repository provides two distinct financial analysis applications:

1. **Yahoo Finance Dashboard** (`yahoo-finance-wrap/`) - A professional-grade Bloomberg-style terminal for comprehensive stock analysis
2. **Alpha Vantage MCP Integration** (`alpha-vantage/`) - A Gradio-based AI chat interface for stock queries via MCP protocol

Both applications are designed for financial professionals, quantitative analysts, and developers seeking comprehensive market analysis tools.

## 📊 Yahoo Finance Dashboard

A Streamlit-based stock performance dashboard with advanced technical analysis, fundamental analysis, and portfolio risk metrics in a professional Bloomberg-terminal style.

### Key Features

- **Technical Workspace**: Candlestick charts with moving averages, RSI (Relative Strength Index), and MACD oscillator analysis
- **Fundamental Analysis**: Peer valuation comparisons, earnings profiles, and free cash flow analysis
- **Portfolio & Risk Metrics**: Weight distribution visualization, correlation heatmaps, and portfolio diversification analysis
- **Professional Terminal UI**: Dark-themed Bloomberg-style interface optimized for financial data presentation

### Running the Application

```bash
cd yahoo-finance-wrap
streamlit run yf.py
```

### Configuration

Create or edit `tickers_config.json` to customize your watchlist:

```json
{
  "tickers": ["MSFT", "AAPL", "GOOG", "NVDA", "TSLA"]
}
```

### Running Tests

```bash
cd yahoo-finance-wrap
pytest test_yf.py -v
```

The test suite covers configuration loading, technical indicator calculations, chart generation, and portfolio analysis functions.

## 🔗 Alpha Vantage MCP Integration

A Gradio-based chat interface that uses the Model Context Protocol (MCP) to query stock quotes through an Alpha Vantage backend.

### Key Features

- **Natural Language Interface**: Chat-based interaction for stock queries
- **Automatic Ticker Extraction**: Intelligently extracts stock symbols from user messages
- **MCP Protocol Integration**: Uses standardized Model Context Protocol for AI tool integration
- **Async Architecture**: Non-blocking asynchronous design for responsive performance

### Running the Application

```bash
cd alpha-vantage
python hello-alpha-python-gradio.py
```

### Configuration

Requires `.vscode/mcp.json` with an `alphavantage` server configuration:

```json
{
  "servers": {
    "alphavantage": {
      "type": "http",
      "url": "http://localhost:3000"
    }
  }
}
```

### Environment Variables

Create `.env` file for optional debug mode:
```
ALPHA_VANTAGE_DEBUG=true
```

### Running Tests

```bash
cd alpha-vantage
pytest test_hello_alpha.py -v
```

Tests cover MCP configuration loading, ticker extraction, and protocol error handling.

## 🛠️ Installation

Install dependencies for each module:

### Yahoo Finance Dashboard
```bash
cd yahoo-finance-wrap
pip install -r requirements.txt
```

Required packages:
- `streamlit==1.58.0` - Web application framework
- `yfinance==1.4.1` - Yahoo Finance API wrapper
- `altair==6.1.0` - Declarative visualization library
- `pandas==3.0.3` - Data manipulation and analysis

### Alpha Vantage MCP Integration
```bash
cd alpha-vantage
pip install -r requirements.txt
```

Required packages:
- `gradio` - Chat interface framework
- `mcp` - Model Context Protocol client
- `python-dotenv` - Environment variable management
- `pytest>=7.0.0` - Testing framework
- `pytest-asyncio>=0.21.0` - Async testing support

## 📁 Project Structure

```
awm-ai-utils/
├── alpha-vantage/                 # Alpha Vantage MCP integration
│   ├── hello-alpha-python-gradio.py  # Main Gradio application
│   ├── test_hello_alpha.py           # Comprehensive test suite
│   ├── requirements.txt               # Python dependencies
│   └── .env                          # Environment configuration (optional)
│
├── yahoo-finance-wrap/            # Yahoo Finance dashboard
│   ├── yf.py                        # Main Streamlit application
│   ├── test_yf.py                   # Comprehensive test suite
│   ├── requirements.txt              # Python dependencies
│   └── tickers_config.json           # Watchlist configuration
│
├── .vscode/                       # VS Code configuration
│   └── mcp.json                   # MCP server configurations
│
├── README.md                      # Root documentation (this file)
└── LICENSE                        # License information
```

## 🔧 Technical Architecture

### Yahoo Finance Dashboard

The Yahoo Finance dashboard is built with a modular architecture:

- **Data Layer**: Uses `yfinance` for real-time and historical market data
- **Analysis Layer**: Implements technical indicators (RSI, MACD, moving averages) and fundamental analysis functions
- **Visualization Layer**: Uses Altair for professional-grade financial charts
- **UI Layer**: Streamlit provides the terminal-style interface with custom CSS theming

### Alpha Vantage MCP Integration

The MCP integration follows async/await patterns for optimal performance:

- **Protocol Layer**: Implements MCP HTTP client using `streamablehttp_client`
- **Parsing Layer**: Natural language processing for ticker extraction from user queries
- **Session Layer**: Async session management for non-blocking operations
- **Interface Layer**: Gradio ChatInterface for user interaction

## 🧪 Testing

Both applications include comprehensive test suites using pytest:

### Yahoo Finance Tests
- Configuration loading and validation
- Technical indicator calculations (RSI, MACD)
- Chart generation and rendering
- Portfolio distribution analysis
- Correlation matrix calculations

### Alpha Vantage Tests
- MCP configuration parsing and validation
- Ticker extraction from natural language
- Async MCP protocol handling
- Error scenarios and edge cases

## 🎯 Use Cases

### For Financial Professionals
- Real-time market monitoring with professional-grade visualizations
- Technical analysis with customizable indicators
- Peer comparison and fundamental analysis
- Portfolio risk assessment and correlation analysis

### For Quantitative Analysts
- Rapid prototyping of trading strategies
- Backtesting with historical data
- Risk metric calculations and visualization
- Multi-asset portfolio analysis

### For Developers
- Reference implementation for financial applications
- MCP protocol integration examples
- Async Python patterns in financial contexts
- Streamlit and Gradio best practices

## 📝 API Reference

### Yahoo Finance Dashboard Functions

#### Core Functions
- `load_tickers()` - Load and validate ticker configuration
- `download_price_history(tickers)` - Fetch historical price data
- `get_ticker_info(symbol)` - Retrieve company information (cached)

#### Technical Analysis
- `calculate_rsi(series, window=14)` - Calculate Relative Strength Index
- `calculate_macd(series, fast=12, slow=26, signal=9)` - Calculate MACD oscillator
- `build_candlestick_chart(ticker_history)` - Generate candlestick chart with SMAs
- `build_rsi_chart(ticker_history)` - Generate RSI visualization
- `build_macd_chart(ticker_history)` - Generate MACD visualization

#### Fundamental Analysis
- `build_watchlist_fundamentals(tickers)` - Get fundamental data for watchlist
- `build_peer_pe_chart(peer_df, selected_ticker)` - Peer P/E comparison
- `build_earnings_chart(ticker)` - Quarterly earnings visualization
- `build_fcf_chart(ticker)` - Free cash flow analysis

#### Portfolio Analysis
- `build_portfolio_distribution(close_values)` - Calculate portfolio weights
- `calculate_returns_and_correlation(history, tickers)` - Compute correlation matrix
- `build_correlation_heatmap(corr_matrix)` - Visualize correlations

### Alpha Vantage Functions

#### Configuration
- `load_mcp_config_from_vscode(server_name)` - Load MCP server configuration

#### Natural Language Processing
- `extract_ticker(message)` - Extract stock ticker from user query

#### MCP Integration
- `call_alpha_vantage_mcp(ticker)` - Async MCP server call
- `chat_with_mcp(message, history)` - Main chat interface function

## 🤝 Contributing

Contributions are welcome! Please ensure:
- All tests pass with `pytest -v`
- Code follows existing style conventions
- New features include appropriate tests
- Documentation is updated for new functionality

## 📄 License

See LICENSE file for details.

## 🔗 Resources

- [Streamlit Documentation](https://docs.streamlit.io/)
- [Gradio Documentation](https://www.gradio.app/docs)
- [yfinance Documentation](https://github.com/ranaroussi/yfinance)
- [Altair Documentation](https://altair-viz.github.io/)
- [Model Context Protocol](https://modelcontextprotocol.io/) 
