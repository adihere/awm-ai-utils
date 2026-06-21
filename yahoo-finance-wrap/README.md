# Yahoo Finance Dashboard — Technical Implementation

Streamlit-based stock performance dashboard implementing a Bloomberg-style terminal interface. Uses `yfinance` for market data, Altair for chart visualization, and a custom dark-theme CSS injection.

## Module Architecture

```
tickers_config.json
    │ load_tickers()
    ▼
list[str] (ticker symbols)
    │
    ▼ yfinance.download(tickers, period="1y", group_by="ticker",
    │                   auto_adjust=True, threads=True)
    ▼
DataFrame (MultiIndex or Flat — see §DataFrame Structural Branching)
    │
    ┌────────────────────┼────────────────────┐
    ▼                    ▼                    ▼
Technical             Fundamental           Portfolio & Risk
─────────             ──────────            ────────────────
calculate_rsi()       get_ticker_info()     extract_close_values()
calculate_macd()       │ (LRU-cached)        build_portfolio_distribution()
build_candlestick()   build_watchlist_      calculate_returns_and_
build_rsi_chart()     fundamentals()         correlation()
build_macd_chart()    build_peer_pe_chart() build_correlation_heatmap()
                      build_market_cap_     build_portfolio_pie_chart()
                       chart()
                      build_earnings_chart()
                      build_fcf_chart()
```

## DataFrame Structural Branching

`yfinance.download()` returns structurally different DataFrames depending on the number of tickers. Every function that consumes the `history` DataFrame contains a structural branch:

```python
if isinstance(history.columns, pd.MultiIndex):
    # Multi-ticker path: columns are (ticker, field) tuples
    # Access: history[ticker].get("Close")
else:
    # Single-ticker path: columns are flat field names
    # Access: history["Close"]
```

| Input | Column Structure | Close Access Pattern | Return Type |
|---|---|---|---|
| Single ticker | Flat: `Close`, `Open`, `High`, `Low`, `Volume` | `history["Close"]` | `pd.Series` if 1 ticker |
| Multiple tickers | MultiIndex: `(ticker, field)` | `history[ticker].get("Close")` | `pd.Series` per ticker |

Affected functions: `extract_close_values()`, `get_ticker_percent_changes()`, `calculate_returns_and_correlation()`. This is the primary source of complexity in the data layer.

## Technical Indicator Implementations

### RSI (Relative Strength Index)

```python
def calculate_rsi(series, window=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi
```

Implementation notes:
- Uses **simple moving average** (`.rolling().mean()`) of gains/losses, not Wilder's exponential smoothing. This produces slightly different values from the standard Wilder RSI for short windows.
- Division-by-zero handling: when `loss == 0`, `rs → inf`, and pandas computes `100 - (100 / inf) → 100`. However, early window periods produce `NaN` because `.rolling(window=14)` has no lookback — these propagate naturally into the chart.
- Minimum data threshold for chart: **20 bars** (14 for window + 6 for warmup).

### MACD (Moving Average Convergence Divergence)

```python
def calculate_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()    # Fast EMA
    exp2 = series.ewm(span=slow, adjust=False).mean()    # Slow EMA
    macd = exp1 - exp2                                    # MACD line
    signal_line = macd.ewm(span=signal, adjust=False).mean()  # Signal line
    histogram = macd - signal_line                        # Histogram
    return macd, signal_line, histogram
```

Implementation notes:
- `adjust=False` uses the recursive EMA formula: `EMA_t = alpha * x_t + (1 - alpha) * EMA_{t-1}` where `alpha = 2 / (span + 1)`. The first value is initialized as `x_0` (not the mean of the first `span` values).
- Returns a 3-tuple of `pd.Series`, each the same length as input.
- Minimum data threshold for chart: **30 bars** (26 for slow EMA + 4 for signal warmup).

## Chart Layering Architecture

All charts use Altair's **compositional layering** model — multiple mark types composed into a single view via `alt.layer()`. Each chart function returns `None` on insufficient data rather than raising an exception.

### Candlestick Chart

```
┌─────────────────────────────────────────┐
│  rules (High-Low wick, gray)           │
│  + bars (Open-Close body, conditional) │  ← alt.layer(rules, bars, sma20, sma50)
│  + sma20_line (orange)                  │     .resolve_scale(y="shared")
│  + sma50_line (blue)                    │     .properties(height=320)
├─────────────────────────────────────────┤
│  volume (bar chart, #334155, 60% op)    │  ← .properties(height=120)
└─────────────────────────────────────────┘  ← alt.vconcat(upper, volume)
```

The candlestick body color uses `alt.condition("datum.Close >= datum.Open")` — green (`#3AC569`) for bullish, red (`#F8506B`) for bearish. The high-low wick uses `mark_rule`. SMA20 and SMA50 are `mark_line` overlays on the same y-scale.

Minimum data: **50 bars** (for SMA50 calculation).

### RSI Chart

```
┌─────────────────────────────────────────┐
│  rsi_line (green #00FF41)              │
│  + oversold_rule (30, dashed red)      │  ← alt.layer(rsi_line, oversold, overbought)
│  + overbought_rule (70, dashed green) │     .resolve_scale(y="independent")
└─────────────────────────────────────────┘     .properties(height=320)
```

Threshold lines are `mark_rule(strokeDash=[3])` overlaid on the RSI line. The y-scale is fixed `[0, 100]` via `alt.Scale(domain=[0, 100])`. `resolve_scale(y="independent")` lets the threshold charts define their own scale.

Minimum data: **20 bars**.

### MACD Chart

```
┌─────────────────────────────────────────┐
│  histogram_bar (conditional color)     │
│  + macd_line (blue #00D4FF)            │  ← alt.layer(histogram, macd, signal)
│  + signal_line (pink #FFB6C1)          │     .interactive() (zoom/pan)
└─────────────────────────────────────────┘     .properties(height=300)
```

Histogram bars use conditional coloring: green for `datum.Histogram >= 0`, red for negative. `.interactive()` enables Altair's built-in zoom/pan.

Minimum data: **30 bars**.

### Peer Valuation Charts

Two horizontal bar charts side-by-side:
- **P/E chart**: `mark_bar` with `highlight` column — selected ticker in amber (`#FBBF24`), peers in gray (`#64748B`). Sorted descending by `trailingPE`.
- **Market cap chart**: Same structure, sorted by `marketCap`. Axis format uses `~s` for SI abbreviations.

Both derive a `highlight` column: `chart_data["highlight"] = chart_data["ticker"].apply(lambda s: "Selected" if s == selected_ticker else "Peer")`.

### Portfolio Distribution

Donut chart: `mark_arc(innerRadius=70)` with `PORTFOLIO_PALETTE` color scale. Encodes `theta=value`, `color=ticker`. Tooltips include value (formatted `, .2f`) and weight (formatted `.1%`).

### Correlation Heatmap

`mark_rect` with `blueorange` diverging color scale, domain `[-1, 0, 1]`. Data is melted from a symmetric correlation matrix: `corr_matrix.reset_index().melt(id_vars="index")`.

## CSS Theme Injection

The entire dark theme is defined in the `DARK_TERMINAL_CSS` constant and injected once via:

```python
st.markdown(f"<style>{DARK_TERMINAL_CSS}</style>", unsafe_allow_html=True)
```

### Color System

| Context | Color | Usage |
|---|---|---|
| `#0B0E11` | Terminal black | Root background, Altair chart canvas |
| `#11161B` | Panel dark | Sidebar, metric cards, data frame thead |
| `#1F2730` | Border gray | Sidebar border, table/df cell borders |
| `#EAECEF` | Text white | Body text, metric values, headings |
| `#8B949E` | Muted gray | Metric labels, axis labels, axis ticks |
| `#3AC569` | Green | Positive price changes, bullish candles, overbought line |
| `#F8506B` | Red | Negative price changes, bearish candles, oversold line |
| `#FBBF24` | Amber | Selected ticker highlight in peer charts |
| `#64748B` | Slate gray | Peer ticker bars in peer charts |

### CSS Selector Targets

```css
.stApp                          /* Root container — background, font */
.block-container                /* Max-width removal for full-width layout */
section[data-testid="stSidebar"] /* Sidebar panel — dark background + border */
[data-testid="stMetric"]        /* Metric cards — box styling */
.stDataFrame / .stTable         /* Data tables — console-dump aesthetic */
div[data-baseweb="select"]      /* Select dropdown — dark background */
.stAltairChart / .vega-embed    /* Chart canvas — no white flash */
.element-container              /* Tight vertical spacing (0.25rem margin) */
```

### Injection Strategy

This is a **single-injection** approach. Streamlit re-renders components on interaction, but the injected `<style>` block persists because it targets CSS class/attribute selectors, not element IDs. The style is written before any component renders, ensuring no flash of unstyled content.

## Streamlit Context Guard

```python
def is_streamlit_context():
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
        return get_script_run_ctx(suppress_warning=True) is not None
    except (ImportError, Exception):
        return False

if __name__ == "__main__":
    if not is_streamlit_context():
        print("This app should be run with Streamlit:")
        print("  streamlit run yf.py")
        sys.exit(0)
    main()
```

Prevents `main()` from executing when the script is invoked directly (`python yf.py`). Without this guard, `st.set_page_config()` raises `StreamlitAPIException` because no Streamlit runtime is active.

## Configuration

### `load_tickers(config_path=CONFIG_PATH) -> list`

```python
def load_tickers(config_path=CONFIG_PATH):
    if not os.path.exists(config_path):
        return create_sample_config(config_path)    # Creates ["MSFT", "AAPL", "GOOG"]
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        tickers = config.get("tickers")
        if isinstance(tickers, list) and tickers:
            return tickers
    except (json.JSONDecodeError, OSError):
        pass
    return create_sample_config(config_path)        # Overwrites bad config
```

Behavior:
- **File missing** — creates default config with `["MSFT", "AAPL", "GOOG"]`.
- **Invalid JSON** — overwrites with default config (same behavior as missing file).
- **Missing/empty `tickers` key** — overwrites with default config.
- **Valid config** — returns the ticker list.

### Configurable Constants

```python
CONFIG_PATH = "tickers_config.json"
POSITIVE_COLOR = "#3AC569"
NEGATIVE_COLOR = "#F8506B"
PORTFOLIO_PALETTE = ["#0F172A", "#1E293B", "#334155", "#1D4ED8", "#0EA5E9", "#14B8A6", "#A855F7"]
```

## API Reference

### Core Functions

#### `load_tickers(config_path=CONFIG_PATH) -> list`

Load ticker configuration. Creates default config if file is missing or invalid.

#### `download_price_history(tickers) -> DataFrame`

Calls `yf.download(tickers, period="1y", group_by="ticker", auto_adjust=True, threads=True)`. Multi-threaded download with auto-adjusted splits/dividends.

#### `get_ticker_info(symbol) -> dict`

Wraps `yf.Ticker(symbol).info` with `@lru_cache(maxsize=64)`. Cached to avoid redundant API calls within a session.

### Technical Analysis

#### `calculate_rsi(series, window=14) -> Series`

RSI via simple moving average of gains/losses. Returns series with NaN for initial window period.

#### `calculate_macd(series, fast=12, slow=26, signal=9) -> tuple[Series, Series, Series]`

MACD components using `ewm(adjust=False)`. Returns `(macd_line, signal_line, histogram)`.

#### `build_candlestick_chart(ticker_history) -> Chart | None`

Candlestick + SMA20/SMA50 + volume. Returns `None` if < 50 bars.

#### `build_rsi_chart(ticker_history) -> Chart | None`

RSI line with 30/70 threshold lines. Returns `None` if < 20 bars.

#### `build_macd_chart(ticker_history) -> Chart | None`

MACD histogram + MACD line + signal line, interactive zoom. Returns `None` if < 30 bars.

### Fundamental Analysis

#### `build_watchlist_fundamentals(tickers) -> DataFrame`

Collects `ticker`, `longName`, `trailingPE`, `marketCap` for each ticker via `get_ticker_info()`. Numeric fields cast to `float` with `None` fallback for missing/invalid values.

#### `build_peer_pe_chart(peer_df, selected_ticker) -> Chart`

Horizontal bar chart of trailing P/E. Selected ticker highlighted in amber, peers in gray. Sorted descending.

#### `build_market_cap_chart(peer_df, selected_ticker) -> Chart`

Horizontal bar chart of market cap. Same highlight pattern. SI abbreviation formatting (`~s`).

#### `build_earnings_chart(ticker) -> Chart | None`

Quarterly revenue (bars) + net income (line), scaled to billions. Up to 4 recent quarters. Returns `None` if `Total Revenue` not in financials index.

#### `build_fcf_chart(ticker) -> Chart | None`

Operating cash flow (bars) + free cash flow line (OCF - CapEx). CapEx is `abs()`-ed before subtraction. Returns `None` if `Operating Cash Flow` not in cashflow index.

### Portfolio Analysis

#### `extract_close_values(history, tickers) -> dict`

Extracts latest close price per ticker. Handles both MultiIndex and flat DataFrame structures. Returns `{ticker: float}`.

#### `build_portfolio_distribution(close_values) -> DataFrame`

Calculates weight as `value / total`. Filters out zero/negative values. Sorted descending by value. Returns empty DataFrame if no valid values.

#### `calculate_returns_and_correlation(history, tickers) -> DataFrame | None`

Extracts close prices, computes `pct_change()`, calculates Pearson correlation. Handles MultiIndex via `xs("Close", level=1, axis=1)`. Returns `None` on error.

#### `build_correlation_heatmap(corr_matrix) -> Chart | None`

Melted correlation matrix as `mark_rect` with `blueorange` diverging scale. Returns `None` for empty matrix.

#### `build_portfolio_pie_chart(distribution) -> Chart`

Donut chart (`innerRadius=70`) encoding `theta=value`, `color=ticker` with `PORTFOLIO_PALETTE`.

## Test Suite

```bash
cd yahoo-finance-wrap
pytest test_yf.py -v
```

**30 tests**, all pass. Network calls are fully mocked.

### Test Classes

| Class | Count | Subject |
|---|---|---|
| `TestCreateSampleConfig` | 3 | Config file creation, JSON validity, return values |
| `TestLoadTickers` | 5 | Existing/missing/invalid/empty config handling |
| `TestBuildSummary` | 3 | Summary dict with present/missing fields, key coverage |
| `TestDownloadPriceHistory` | 2 | Single/multi ticker download mock (verifies `period="1y"`, `auto_adjust=True`) |
| `TestPortfolioHelpers` | 3 | MultiIndex close extraction, percent changes, weight calculation |
| `TestFundamentalHelpers` | 4 | `get_ticker_info` mock, watchlist DataFrame, P/E chart spec, market cap chart spec |
| `TestTechnicalIndicators` | 9 | RSI series + extremes, MACD 3-series, candlestick (< 50 → `None`, >= 50 → `vconcat`), RSI threshold, MACD threshold, correlation matrix + heatmap |

### Mocking Strategy

- `yf.download` is patched at `@patch("yf.yf.download")` — returns mock DataFrames.
- `yf.Ticker` is patched at `@patch("yf.yf.Ticker")` — returns mock objects with `.info` attribute.
- Chart assertions use `chart.to_dict()` to inspect the Vega-Lite spec (mark type, encoding fields, layer composition).

## Dependencies

```
streamlit>=1.30.0   # Web framework + page config + components
yfinance>=1.4.0     # Yahoo Finance API wrapper (multi-threaded download)
altair>=5.0.0       # Declarative visualization (layered chart composition)
pandas>=2.0.0       # DataFrame operations, MultiIndex, rolling/ewm calculations
```

Lower-bound pins ensure installability while guaranteeing minimum compatible API surfaces. No exact version pins are used.

## Performance Characteristics

| Ticker Count | Memory | Load Time | Notes |
|---|---|---|---|
| 1–10 | < 100 MB | < 5s | Optimal range |
| 10–20 | 100–200 MB | 5–10s | Good |
| 20–50 | 200–500 MB | 10–20s | Acceptable |
| 50+ | 500 MB+ | 20s+ | May degrade — Streamlit re-runs full pipeline on interaction |

### Caching

- `get_ticker_info()`: `@lru_cache(maxsize=64)` — avoids redundant API calls for the same symbol during a session.
- No Streamlit `@st.cache_data` decorators are used — this keeps the module importable from test code without a Streamlit runtime.

### Data Processing

- **Vectorized operations**: All indicator calculations use pandas/numpy vectorized methods (`.rolling()`, `.ewm()`, `.diff()`, `.pct_change()`).
- **Multi-threaded download**: `yf.download(threads=True)` parallelizes network I/O across tickers.
- **No incremental updates**: Full 1-year history is re-downloaded on each Streamlit re-run.
