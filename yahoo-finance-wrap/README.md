# Yahoo Finance Dashboard - Bloomberg Terminal Replica

A professional-grade Streamlit-based stock performance dashboard featuring comprehensive technical analysis, fundamental analysis, and portfolio risk metrics in a Bloomberg-terminal style interface.

## 🚀 Overview

This module provides enterprise-level financial analysis capabilities with a dark-themed terminal interface optimized for financial data presentation. It combines real-time market data retrieval, advanced technical indicators, fundamental analysis, and portfolio risk metrics in a single unified application.

## 🎯 Key Features

### Technical Analysis Workspace
- **Candlestick Charts**: Professional candlestick visualizations with SMA20 and SMA50 moving averages
- **RSI Analysis**: Relative Strength Index with overbought (70) and oversold (30) thresholds
- **MACD Oscillator**: Moving Average Convergence Divergence with signal lines and histogram
- **Volume Analysis**: Integrated volume charts with price data

### Fundamental Analysis
- **Peer Valuation**: Compare P/E ratios and market caps across watchlist
- **Earnings Profile**: Quarterly revenue and net income trends
- **Free Cash Flow**: Operating cash flow and capital expenditure analysis
- **Company Fundamentals**: Market cap, P/E ratio, company name and symbol

### Portfolio & Risk Metrics
- **Weight Distribution**: Visual portfolio allocation with pie charts
- **Correlation Heatmap**: 30-day asset correlation matrix
- **Portfolio Summary**: Total value, top holdings, diversification metrics
- **Multi-asset Support**: Analyze entire portfolios simultaneously

### Bloomberg Terminal Interface
- **Dark Terminal Theme**: Professional command-center aesthetic
- **Monospace Typography**: Optimized for numerical data readability
- **Real-time Ticker Tape**: Live price changes across watchlist
- **Tabbed Navigation**: Separate workspaces for technical, fundamental, and risk analysis

## 📁 Project Structure

```
yahoo-finance-wrap/
├── yf.py                        # Main Streamlit application (705 lines)
├── test_yf.py                   # Comprehensive test suite (446 lines)
├── requirements.txt              # Python dependencies
└── tickers_config.json           # Watchlist configuration
```

## 🛠️ Installation

### Prerequisites
- Python 3.11 or higher
- Internet connection for real-time data
- Sufficient memory for multi-asset analysis

### Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

Required packages:
- `streamlit==1.58.0` - Web application framework
- `yfinance==1.4.1` - Yahoo Finance API wrapper
- `altair==6.1.0` - Declarative visualization library
- `pandas==3.0.3` - Data manipulation and analysis

2. Configure your watchlist:
Edit `tickers_config.json` or let the application create a default one:
```json
{
  "tickers": ["MSFT", "AAPL", "GOOG", "NVDA", "TSLA", "AMD", "META", "AMZN"]
}
```

## 🚦 Running the Application

### Start the Dashboard

```bash
streamlit run yf.py
```

This will:
- Load ticker configuration from `tickers_config.json`
- Download 1-year historical data for all tickers
- Start the Streamlit web server (default: http://localhost:8501)
- Display the Bloomberg Terminal interface

### Interface Overview

The dashboard is organized into three main tabs:

1. **📊 Technical Workspace** - Price charts and technical indicators
2. **🔍 Fundamental Analysis** - Company fundamentals and peer comparison
3. **🧮 Portfolio & Risk** - Portfolio metrics and correlation analysis

## 🔧 Configuration

### Ticker Configuration

Create or edit `tickers_config.json`:

```json
{
  "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]
}
```

**Features:**
- Supports unlimited tickers (performance scales with network)
- Auto-creates default configuration if missing
- Handles invalid configurations gracefully
- YAML and JSON formats supported

### Application Settings

Modify these constants in `yf.py`:

```python
CONFIG_PATH = "tickers_config.json"          # Configuration file location
POSITIVE_COLOR = "#3AC569"                   # Green for positive changes
NEGATIVE_COLOR = "#F8506B"                   # Red for negative changes
PORTFOLIO_PALETTE = ["#0F172A", "#1E293B"]   # Chart color palette
```

## 🧪 Testing

### Run All Tests

```bash
pytest test_yf.py -v
```

### Test Categories

#### Configuration Tests
- ✅ Configuration file creation and validation
- ✅ Ticker loading from existing configurations
- ✅ Invalid JSON and error handling
- ✅ Empty ticker list handling

#### Technical Analysis Tests
- ✅ RSI calculation with edge cases
- ✅ MACD calculation (MACD, signal, histogram)
- ✅ Candlestick chart generation
- ✅ RSI and MACD chart rendering

#### Fundamental Analysis Tests
- ✅ Company information retrieval and caching
- ✅ Watchlist fundamentals building
- ✅ Peer P/E and market cap charts
- ✅ Earnings and cash flow analysis

#### Portfolio Analysis Tests
- ✅ Close value extraction from multi-index data
- ✅ Portfolio distribution calculation
- ✅ Returns and correlation matrix calculation
- ✅ Correlation heatmap generation

### Example Test Commands

```bash
# Run specific test class
pytest test_yf.py::TestTechnicalIndicators -v

# Run with coverage
pytest test_yf.py --cov=. --cov-report=html

# Run specific test
pytest test_yf.py::TestCalculateRsi::test_calculate_rsi_returns_series -v
```

## 🔌 API Reference

### Core Functions

#### `load_tickers(config_path=CONFIG_PATH) -> list`

Load and validate ticker configuration from JSON file.

**Parameters:**
- `config_path` - Path to configuration file (default: "tickers_config.json")

**Returns:**
- `list` - List of ticker symbols

**Behavior:**
- Creates default configuration if file missing
- Handles invalid JSON gracefully
- Validates ticker list structure
- Returns default tickers: ["MSFT", "AAPL", "GOOG"]

---

#### `download_price_history(tickers) -> DataFrame`

Download 1-year historical price data for specified tickers.

**Parameters:**
- `tickers` - List of ticker symbols

**Returns:**
- `DataFrame` - Multi-index DataFrame with OHLCV data

**Data Coverage:**
- Period: 1 year of daily data
- Fields: Open, High, Low, Close, Volume
- Auto-adjusted for splits and dividends
- Multi-threaded download for performance

---

#### `get_ticker_info(symbol) -> dict`

Retrieve company information with LRU caching.

**Parameters:**
- `symbol` - Stock ticker symbol

**Returns:**
- `dict` - Company information dictionary

**Caching:**
- LRU cache with max 64 entries
- Reduces API calls for repeated queries
- Automatic cache invalidation

### Technical Analysis Functions

#### `calculate_rsi(series, window=14) -> Series`

Calculate Relative Strength Index (RSI).

**Parameters:**
- `series` - Price series (typically closing prices)
- `window` - Calculation window (default: 14 periods)

**Returns:**
- `Series` - RSI values between 0-100

**Formula:**
```
RS = Average Gain / Average Loss
RSI = 100 - (100 / (1 + RS))
```

**Usage:**
- RSI > 70: Overbought condition
- RSI < 30: Oversold condition
- Typical signals: divergence, overbought/oversold

---

#### `calculate_macd(series, fast=12, slow=26, signal=9) -> tuple`

Calculate MACD oscillator components.

**Parameters:**
- `series` - Price series
- `fast` - Fast EMA period (default: 12)
- `slow` - Slow EMA period (default: 26)
- `signal` - Signal line period (default: 9)

**Returns:**
- `tuple` - (MACD line, Signal line, Histogram)

**Components:**
- **MACD Line**: Fast EMA - Slow EMA
- **Signal Line**: EMA of MACD line
- **Histogram**: MACD - Signal line

---

#### `build_candlestick_chart(ticker_history) -> Chart`

Generate candlestick chart with moving averages.

**Parameters:**
- `ticker_history` - Historical price data DataFrame

**Returns:**
- `Chart` - Altair chart object or None if insufficient data

**Requirements:**
- Minimum 50 trading days of data
- OHLCV data columns present
- Valid datetime index

**Features:**
- Green candles for price increases
- Red candles for price decreases
- SMA20 (orange) and SMA50 (blue) overlays
- Volume chart below price chart

---

#### `build_rsi_chart(ticker_history) -> Chart`

Generate RSI visualization with threshold lines.

**Parameters:**
- `ticker_history` - Historical price data DataFrame

**Returns:**
- `Chart` - Altair chart object or None if insufficient data

**Requirements:**
- Minimum 20 trading days of data
- Closing price series available

**Features:**
- Green line for RSI values
- Dashed lines at 70 (overbought) and 30 (oversold)
- Auto-scaled Y-axis (0-100)

---

#### `build_macd_chart(ticker_history) -> Chart`

Generate MACD oscillator visualization.

**Parameters:**
- `ticker_history` - Historical price data DataFrame

**Returns:**
- `Chart` - Altair chart object or None if insufficient data

**Requirements:**
- Minimum 30 trading days of data
- Sufficient data for EMA calculations

**Features:**
- Blue line: MACD
- Pink line: Signal line
- Colored histogram: MACD vs Signal
- Interactive zoom and pan

### Fundamental Analysis Functions

#### `build_watchlist_fundamentals(tickers) -> DataFrame`

Retrieve fundamental data for entire watchlist.

**Parameters:**
- `tickers` - List of ticker symbols

**Returns:**
- `DataFrame` - Fundamental data for all tickers

**Data Fields:**
- `ticker` - Symbol
- `longName` - Company name
- `trailingPE` - Trailing P/E ratio
- `marketCap` - Market capitalization

---

#### `build_peer_pe_chart(peer_df, selected_ticker) -> Chart`

Create peer P/E comparison bar chart.

**Parameters:**
- `peer_df` - DataFrame with peer fundamental data
- `selected_ticker` - Ticker to highlight

**Returns:**
- `Chart` - Altair horizontal bar chart

**Features:**
- Selected ticker highlighted in amber
- Peers shown in slate gray
- Sorted by P/E ratio (descending)

---

#### `build_earnings_chart(ticker) -> Chart`

Generate quarterly earnings visualization.

**Parameters:**
- `ticker` - Stock ticker symbol

**Returns:**
- `Chart` - Altair chart or None if data unavailable

**Data Shown:**
- Quarterly revenue (bars, in billions)
- Net income (line, in billions)
- 4 most recent quarters

---

#### `build_fcf_chart(ticker) -> Chart`

Generate free cash flow analysis chart.

**Parameters:**
- `ticker` - Stock ticker symbol

**Returns:**
- `Chart` - Altair chart or None if data unavailable

**Components:**
- Operating cash flow (bars)
- Free cash flow (line)
- Capital expenditure (calculated)
- 4 most recent quarters

### Portfolio Analysis Functions

#### `build_portfolio_distribution(close_values) -> DataFrame`

Calculate portfolio weight distribution.

**Parameters:**
- `close_values` - Dictionary of ticker: current price

**Returns:**
- `DataFrame` - Portfolio allocation with weights

**Columns:**
- `ticker` - Symbol
- `value` - Current value
- `weight` - Portfolio weight percentage

**Features:**
- Sorted by value (descending)
- Excludes zero/negative values
- Normalized weights (sum to 100%)

---

#### `calculate_returns_and_correlation(history, tickers) -> DataFrame`

Calculate correlation matrix from price history.

**Parameters:**
- `history` - Historical price data
- `tickers` - List of ticker symbols

**Returns:**
- `DataFrame` - Correlation matrix or None if insufficient data

**Method:**
- Extract closing prices
- Calculate daily returns
- Compute Pearson correlation
- Handle missing data gracefully

---

#### `build_correlation_heatmap(corr_matrix) -> Chart`

Generate correlation heatmap visualization.

**Parameters:**
- `corr_matrix` - Correlation matrix DataFrame

**Returns:**
- `Chart` - Altair heatmap or None if empty matrix

**Features:**
- Blue-orange color scheme
- -1 to 1 scale
- Interactive tooltips
- Symmetric display

## 🏗️ Technical Architecture

### Data Flow Architecture

```
User Configuration (tickers_config.json)
    ↓
Price Data Download (yfinance)
    ↓
Technical Analysis Calculation
    ↓
Chart Generation (Altair)
    ↓
Streamlit UI Display
```

### Performance Optimizations

#### Caching Strategy
- **LRU Cache**: Ticker info cached with max 64 entries
- **Memoization**: Technical indicators calculated once per session
- **Parallel Downloads**: Multi-threaded yfinance requests

#### Data Processing
- **Vectorized Operations**: Pandas/numpy for bulk calculations
- **Multi-index Handling**: Efficient multi-asset data structures
- **Lazy Loading**: Charts generated on-demand

#### Memory Management
- **Streaming**: Large datasets processed incrementally
- **Cleanup**: Temporary data cleared after use
- **Optimization**: Minimal data retention in memory

### Chart Architecture

All charts use Altair's declarative grammar:

**Common Features:**
- Dark theme integration
- Responsive sizing
- Interactive tooltips
- Consistent color palette
- Professional typography

**Chart Types:**
- **Candlestick**: Layered composite chart
- **Line Charts**: Time series with points/lines
- **Bar Charts**: Horizontal/vertical comparisons
- **Heatmaps**: Correlation matrices
- **Pie Charts**: Portfolio allocation

## 🎨 Customization

### Color Scheme

Modify constants in `yf.py`:

```python
# Price change colors
POSITIVE_COLOR = "#3AC569"  # Green
NEGATIVE_COLOR = "#F8506B"  # Red

# Portfolio chart palette
PORTFOLIO_PALETTE = [
    "#0F172A", "#1E293B", "#334155", 
    "#1D4ED8", "#0EA5E9", "#14B8A6", "#A855F7"
]
```

### Terminal Theme

CSS is defined in `DARK_TERMINAL_CSS` constant:

```python
DARK_TERMINAL_CSS = """
    html, body, .stApp {
        background-color: #0B0E11;
        color: #EAECEF;
        font-family: "Courier New", "Consolas", "Menlo", monospace;
    }
    /* Additional styling rules... */
"""
```

### Technical Indicators

Adjust indicator parameters:

```python
# RSI calculation
rsi = calculate_rsi(prices, window=14)  # Change window

# MACD calculation
macd, signal, hist = calculate_macd(
    prices, fast=12, slow=26, signal=9
)
```

## 🎓 Usage Examples

### Basic Dashboard Usage

```python
# Start dashboard with default configuration
streamlit run yf.py

# Access technical analysis tab
# Select ticker from dropdown
# Choose "Candlestick & SMA" view
# View real-time chart with moving averages
```

### Custom Configuration

```python
# Create custom watchlist
import json

config = {"tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]}
with open("tickers_config.json", "w") as f:
    json.dump(config, f)
```

### Programmatic Usage

```python
# Download historical data
from yf import download_price_history, calculate_rsi

history = download_price_history(["AAPL"])
rsi = calculate_rsi(history["Close"], window=14)

# Get company info
from yf import get_ticker_info

info = get_ticker_info("AAPL")
print(f"Company: {info['longName']}")
print(f"P/E Ratio: {info['trailingPE']}")
```

### Portfolio Analysis

```python
# Build portfolio distribution
from yf import extract_close_values, build_portfolio_distribution

values = extract_close_values(history, ["AAPL", "MSFT"])
portfolio = build_portfolio_distribution(values)

# Calculate correlations
from yf import calculate_returns_and_correlation

corr_matrix = calculate_returns_and_correlation(history, ["AAPL", "MSFT"])
print(corr_matrix)
```

## 🔍 Troubleshooting

### Common Issues

**Configuration File Not Found:**
```python
# Application creates default config automatically
# Check: tickers_config.json exists
# Solution: Run application once to generate default
```

**Data Download Errors:**
```python
# yfinance rate limiting or network issues
# Solution: Check internet connection
# Reduce number of tickers in config
# Wait and retry (API limits reset periodically)
```

**Insufficient Data for Charts:**
```python
# New IPOs or delisted stocks may lack history
# Solution: Use tickers with longer trading history
# Check minimum data requirements:
# - Candlestick: 50+ days
# - RSI: 20+ days
# - MACD: 30+ days
```

**Empty Fundamental Data:**
```python
# Some tickers lack complete fundamental data
# Solution: Check data availability
# Use try-except for missing fields
# Validate data before charting
```

### Debug Mode

Enable verbose output by modifying the application:

```python
# Add debug prints in key functions
def download_price_history(tickers):
    print(f"Downloading data for: {tickers}")
    # ... rest of function
```

## 📊 Performance Considerations

### Scaling Guidelines

| Tickers | Memory Usage | Load Time | Performance |
|---------|--------------|-----------|-------------|
| 1-10    | < 100MB      | < 5s      | Excellent   |
| 10-20   | 100-200MB    | 5-10s     | Good        |
| 20-50   | 200-500MB    | 10-20s    | Acceptable  |
| 50+     | 500MB+       | 20s+      | May degrade |

### Optimization Tips

1. **Reduce Ticker Count**: Focus on key holdings
2. **Use Caching**: Enable LRU cache for repeated queries
3. **Batch Operations**: Process multiple tickers together
4. **Limit History**: Reduce data period if not needed
5. **Monitor Memory**: Watch for memory leaks in long sessions

## 🔒 Security & Privacy

### Data Handling
- No data stored locally or transmitted externally
- All processing happens in-memory
- No user credentials required
- Configuration files contain only public ticker symbols

### Network Security
- Uses HTTPS for all data transfers
- No API keys required (uses public yfinance endpoints)
- Rate limiting respected to prevent blocking

### Best Practices
- Regular dependency updates
- Validate ticker inputs
- Handle API errors gracefully
- Monitor for unusual activity

## 📚 Additional Resources

- [Streamlit Documentation](https://docs.streamlit.io/)
- [yfinance Documentation](https://github.com/ranaroussi/yfinance)
- [Altair Documentation](https://altair-viz.github.io/)
- [Pandas Documentation](https://pandas.pydata.org/docs/)
- [Technical Analysis Guide](https://www.investopedia.com/technical-analysis-4427699)

## 🤝 Contributing

Contributions are welcome! Areas for enhancement:

- Additional technical indicators
- More fundamental analysis metrics
- Enhanced portfolio optimization tools
- Real-time streaming data support
- Export functionality for reports

## 📄 License

See parent LICENSE file for details.