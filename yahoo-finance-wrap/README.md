# Stock Performance Dashboard

A Streamlit-based dashboard for visualizing stock performance and portfolio allocation using real-time financial data from Yahoo Finance.

## Features

- **Real-time Stock Data**: Fetches current stock prices and historical data using yfinance
- **Portfolio Allocation Visualization**: Interactive pie chart showing portfolio distribution using Altair
- **Stock Summary Metrics**: Displays key indicators including current price, previous close, open, 52-week high/low, market cap, and P/E ratio
- **Historical Price Charts**: Line charts showing recent price trends
- **Configurable Ticker List**: Easily customize tracked stocks via `tickers_config.json`

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd yfin
```

2. Create a virtual environment (recommended):
```bash
python -m venv .venv
.venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install Streamlit (included in requirements):
```bash
pip install streamlit
```

## Usage

Run the dashboard with Streamlit:
```bash
streamlit run yf.py
```

The application will start at `http://localhost:8501` by default.

### Configuration

Edit `tickers_config.json` to customize the stocks you want to track:
```json
{
  "tickers": ["NVDA", "MSFT", "AAPL", "GOOG", "AMZN", "TSLA", "META"]
}
```

## Project Structure

```
.
├── yf.py                 # Main Streamlit application
├── tickers_config.json   # Stock ticker configuration
├── test_yf.py            # Unit tests
└── requirements.txt      # Python dependencies
```

## Dependencies

| Package | Version | Description |
|---------|---------|-------------|
| altair | 6.1.0 | Declarative statistical visualization library |
| pandas | 3.0.3 | Data manipulation and analysis |
| streamlit | 1.58.0 | Web application framework |
| yfinance | 1.4.1 | Yahoo Finance API wrapper

## Testing

Run the test suite with pytest:
```bash
pytest test_yf.py -v
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Run tests to ensure they pass
5. Commit your changes (`git commit -m 'Add your feature'`)
6. Push to the branch (`git push origin feature/your-feature`)
7. Open a pull request

## License

This project is provided as-is for educational purposes.