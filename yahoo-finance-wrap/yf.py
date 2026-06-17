import json
import os
import sys

import altair as alt
import pandas as pd
import yfinance as yf
from functools import lru_cache

CONFIG_PATH = "tickers_config.json"
POSITIVE_COLOR = "#3AC569"
NEGATIVE_COLOR = "#F8506B"
PORTFOLIO_PALETTE = ["#0F172A", "#1E293B", "#334155", "#1D4ED8", "#0EA5E9", "#14B8A6", "#A855F7"]

DARK_TERMINAL_CSS = """
    /* ---- Command-center terminal theme ---- */
    html, body, .stApp {
        background-color: #0B0E11;
        color: #EAECEF;
        font-family: "Courier New", "Consolas", "Menlo", monospace;
    }

    /* Eliminate excess padding and the centered max-width cap */
    .stApp {
        padding-top: 1rem;
    }
    .block-container {
        padding: 1rem 2rem !important;
        max-width: 100% !important;
    }
    section[data-testid="stSidebar"] {
        background-color: #11161B;
        border-right: 1px solid #1F2730;
    }

    /* Headings + body text */
    h1, h2, h3, h4, .stMarkdown, p, span, li {
        color: #EAECEF !important;
        font-family: "Courier New", "Consolas", "Menlo", monospace;
    }
    h1 { letter-spacing: 0.05em; }

    /* Terminal-style metrics: compact bold monospace */
    [data-testid="stMetric"],
    .stMetric {
        background-color: #11161B;
        border: 1px solid #1F2730;
        border-radius: 4px;
        padding: 0.4rem 0.65rem !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #8B949E !important;
    }
    [data-testid="stMetricValue"] {
        font-family: "Courier New", "Consolas", "Menlo", monospace !important;
        font-size: 20px !important;
        font-weight: 700 !important;
        color: #EAECEF !important;
    }

    /* Dataframes / tables read like a console dump */
    .stDataFrame, .stTable {
        font-family: "Courier New", "Consolas", "Menlo", monospace;
    }
    .stDataFrame table, .stTable table {
        background-color: #0B0E11 !important;
        color: #EAECEF !important;
    }
    .stDataFrame thead, .stTable thead {
        background-color: #11161B !important;
        color: #8B949E !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .stDataFrame th, .stDataFrame td, .stTable th, .stTable td {
        border-color: #1F2730 !important;
    }

    /* Inputs blend into the panel */
    .stSelectbox, .stMultiSelect, .stTabs {
        font-family: "Courier New", "Consolas", "Menlo", monospace;
    }
    div[data-baseweb="select"] > div {
        background-color: #11161B !important;
        border-color: #1F2730 !important;
        color: #EAECEF !important;
    }

    /* Strip default widget whitespace */
    .element-container {
        margin-bottom: 0.25rem !important;
    }

    /* Dark canvas behind Altair charts */
    .stAltairChart, .vega-embed, canvas {
        background-color: #0B0E11 !important;
    }
"""


def create_sample_config(config_path):
    sample = {"tickers": ["MSFT", "AAPL", "GOOG"]}
    with open(config_path, "w") as config_file:
        json.dump(sample, config_file, indent=2)
    return sample["tickers"]


def load_tickers(config_path=CONFIG_PATH):
    if not os.path.exists(config_path):
        return create_sample_config(config_path)

    try:
        with open(config_path, "r") as config_file:
            config = json.load(config_file)
        tickers = config.get("tickers")
        if isinstance(tickers, list) and tickers:
            return tickers
    except (json.JSONDecodeError, OSError):
        pass

    return create_sample_config(config_path)


def download_price_history(tickers):
    return yf.download(tickers, period="1mo", group_by="ticker", auto_adjust=True, threads=True)


def extract_close_values(history, tickers):
    values = {}
    if history is None or history.empty:
        return values

    if isinstance(history.columns, pd.MultiIndex):
        for ticker in tickers:
            if ticker in history.columns.levels[0]:
                close_series = history[ticker].get("Close")
                if close_series is not None:
                    close_series = close_series.dropna()
                    if not close_series.empty:
                        values[ticker] = float(close_series.iloc[-1])
    elif "Close" in history.columns:
        close_data = history["Close"]
        if isinstance(close_data, pd.Series):
            if tickers:
                cleaned = close_data.dropna()
                if not cleaned.empty:
                    values[tickers[0]] = float(cleaned.iloc[-1])
        elif isinstance(close_data, pd.DataFrame):
            for ticker in close_data.columns:
                series = close_data[ticker].dropna()
                if not series.empty:
                    values[ticker] = float(series.iloc[-1])

    return values


def build_portfolio_distribution(close_values):
    rows = [
        {"ticker": ticker, "value": value}
        for ticker, value in close_values.items()
        if value is not None and value > 0
    ]
    distribution = pd.DataFrame(rows)
    if distribution.empty:
        return distribution

    distribution = distribution.sort_values(by="value", ascending=False).reset_index(drop=True)
    total = distribution["value"].sum()
    distribution["weight"] = distribution["value"] / total
    return distribution


def get_ticker_percent_changes(history, tickers):
    changes = {}
    if history is None or history.empty:
        return changes

    if isinstance(history.columns, pd.MultiIndex):
        for ticker in tickers:
            if ticker in history.columns.levels[0]:
                close_series = history[ticker].get("Close")
                if close_series is not None and len(close_series.dropna()) >= 2:
                    last = close_series.dropna().iloc[-1]
                    prior = close_series.dropna().iloc[-2]
                    changes[ticker] = (last - prior) / prior
    elif "Close" in history.columns:
        close = history["Close"]
        if isinstance(close, pd.Series):
            cleaned = close.dropna()
            if len(cleaned) >= 2 and tickers:
                last = cleaned.iloc[-1]
                prior = cleaned.iloc[-2]
                changes[tickers[0]] = (last - prior) / prior
        elif isinstance(close, pd.DataFrame):
            for ticker in close.columns:
                series = close[ticker].dropna()
                if len(series) >= 2:
                    last = series.iloc[-1]
                    prior = series.iloc[-2]
                    changes[ticker] = (last - prior) / prior

    return changes


def build_portfolio_pie_chart(distribution):
    return alt.Chart(distribution).mark_arc(innerRadius=70).encode(
        theta=alt.Theta(field="value", type="quantitative"),
        color=alt.Color(
            field="ticker",
            type="nominal",
            scale=alt.Scale(range=PORTFOLIO_PALETTE),
            legend=alt.Legend(title="Ticker", labelColor="#EAECEF", titleColor="#EAECEF"),
        ),
        tooltip=[
            alt.Tooltip("ticker:N", title="Ticker"),
            alt.Tooltip("value:Q", title="Value", format=",.2f"),
            alt.Tooltip("weight:Q", title="Weight", format=".1%"),
        ],
    ).properties(width=420, height=420)


@lru_cache(maxsize=64)
def get_ticker_info(symbol):
    info = yf.Ticker(symbol).info
    return info or {}


def build_watchlist_fundamentals(tickers):
    rows = []
    for ticker in tickers:
        info = get_ticker_info(ticker)
        rows.append(
            {
                "ticker": ticker,
                "longName": info.get("longName", ticker),
                "trailingPE": float(info["trailingPE"]) if isinstance(info.get("trailingPE"), (int, float)) else None,
                "marketCap": float(info["marketCap"]) if isinstance(info.get("marketCap"), (int, float)) else None,
            }
        )
    return pd.DataFrame(rows)


def build_peer_pe_chart(peer_df, selected_ticker):
    chart_data = peer_df.dropna(subset=["trailingPE"]).copy()
    chart_data["highlight"] = chart_data["ticker"].apply(lambda symbol: "Selected" if symbol == selected_ticker else "Peer")
    chart_data = chart_data.sort_values(by="trailingPE", ascending=False)

    return alt.Chart(chart_data).mark_bar().encode(
        x=alt.X("trailingPE:Q", title="Trailing P/E", axis=alt.Axis(labelColor="#EAECEF", titleColor="#EAECEF", domainColor="#8B949E", tickColor="#8B949E")),
        y=alt.Y("ticker:N", sort=alt.EncodingSortField(field="trailingPE", op="sum", order="descending"), title=None, axis=alt.Axis(labelColor="#EAECEF", titleColor="#EAECEF", domainColor="#8B949E", tickColor="#8B949E")),
        color=alt.Color("highlight:N", scale=alt.Scale(domain=["Selected", "Peer"], range=["#FBBF24", "#64748B"]), legend=None),
        tooltip=[
            alt.Tooltip("ticker:N", title="Ticker"),
            alt.Tooltip("trailingPE:Q", title="Trailing P/E", format=",.2f"),
        ],
    ).properties(height=300)


def build_market_cap_chart(peer_df, selected_ticker):
    chart_data = peer_df.dropna(subset=["marketCap"]).copy()
    chart_data["highlight"] = chart_data["ticker"].apply(lambda symbol: "Selected" if symbol == selected_ticker else "Peer")
    chart_data = chart_data.sort_values(by="marketCap", ascending=False)

    return alt.Chart(chart_data).mark_bar().encode(
        x=alt.X("marketCap:Q", title="Market Cap", axis=alt.Axis(labelColor="#EAECEF", titleColor="#EAECEF", domainColor="#8B949E", tickColor="#8B949E", format="~s")),
        y=alt.Y("ticker:N", sort=alt.EncodingSortField(field="marketCap", op="sum", order="descending"), title=None, axis=alt.Axis(labelColor="#EAECEF", titleColor="#EAECEF", domainColor="#8B949E", tickColor="#8B949E")),
        color=alt.Color("highlight:N", scale=alt.Scale(domain=["Selected", "Peer"], range=["#FBBF24", "#64748B"]), legend=None),
        tooltip=[
            alt.Tooltip("ticker:N", title="Ticker"),
            alt.Tooltip("marketCap:Q", title="Market Cap", format=",.2s"),
        ],
    ).properties(height=300)


def build_candlestick_chart(ticker_history):
    if ticker_history is None or ticker_history.empty:
        return None

    if not isinstance(ticker_history.index, pd.DatetimeIndex):
        ticker_history = ticker_history.copy()
        ticker_history.index = pd.to_datetime(ticker_history.index)

    history = ticker_history.reset_index().rename(columns={"index": "Date"})
    base_chart = alt.Chart(history)

    rules = base_chart.mark_rule(color="#8B949E", strokeWidth=1).encode(
        x=alt.X("Date:T", axis=alt.Axis(labelColor="#EAECEF", titleColor="#EAECEF", domainColor="#8B949E", tickColor="#8B949E")),
        y=alt.Y("Low:Q", title=None),
        y2=alt.Y2("High:Q"),
    )

    bars = base_chart.mark_bar().encode(
        x=alt.X("Date:T", axis=alt.Axis(labelColor="#EAECEF", titleColor="#EAECEF", domainColor="#8B949E", tickColor="#8B949E")),
        y=alt.Y("Open:Q", title=None),
        y2=alt.Y2("Close:Q"),
        color=alt.condition("datum.Close >= datum.Open",
            alt.value(POSITIVE_COLOR),
            alt.value(NEGATIVE_COLOR),
        ),
        tooltip=[
            alt.Tooltip("Date:T", title="Date"),
            alt.Tooltip("Open:Q", title="Open", format=",.2f"),
            alt.Tooltip("High:Q", title="High", format=",.2f"),
            alt.Tooltip("Low:Q", title="Low", format=",.2f"),
            alt.Tooltip("Close:Q", title="Close", format=",.2f"),
        ],
    )

    volume = base_chart.mark_bar(opacity=0.8).encode(
        x=alt.X("Date:T", axis=alt.Axis(labelColor="#EAECEF", titleColor="#EAECEF", domainColor="#8B949E", tickColor="#8B949E")),
        y=alt.Y("Volume:Q", title="Volume", axis=alt.Axis(labelColor="#EAECEF", titleColor="#EAECEF", domainColor="#8B949E", tickColor="#8B949E")),
        color=alt.value("#334155"),
        tooltip=[
            alt.Tooltip("Date:T", title="Date"),
            alt.Tooltip("Volume:Q", title="Volume", format=",d"),
        ],
    )

    upper = alt.layer(rules, bars).resolve_scale(y="shared").properties(height=320)
    return alt.vconcat(upper, volume.properties(height=120)).configure_view(strokeOpacity=0)


def build_summary(info):
    return {
        "Symbol": info.get("symbol"),
        "Name": info.get("longName"),
        "Current Price": info.get("regularMarketPrice"),
        "Previous Close": info.get("previousClose"),
        "Open": info.get("open"),
        "52 Week High": info.get("fiftyTwoWeekHigh"),
        "52 Week Low": info.get("fiftyTwoWeekLow"),
        "Market Cap": info.get("marketCap"),
        "PE Ratio": info.get("trailingPE"),
    }


def main():
    import streamlit as st

    st.set_page_config(
        page_title="Stock Performance Dashboard",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(f"<style>{DARK_TERMINAL_CSS}</style>", unsafe_allow_html=True)

    st.title("STOCK COMMAND CENTER")
    st.markdown("<div style='color:#8B949E; font-size:0.95rem; margin-bottom:1rem;'>Bloomberg-inspired terminal view with live portfolio watchlist and high-density analytics.</div>", unsafe_allow_html=True)

    tickers = load_tickers()
    ticker_changes = {}

    st.sidebar.header("CONFIGURATION")
    st.sidebar.write("Update `tickers_config.json` to change symbols.")
    st.sidebar.write(", ".join(tickers))

    with st.spinner("Downloading history..."):
        history = download_price_history(tickers)
        ticker_changes = get_ticker_percent_changes(history, tickers)

    # Horizontal ticker tape
    st.markdown("<div style='margin:0.75rem 0 0.5rem 0; padding:0.5rem 0; border-bottom:1px solid #1F2730;'></div>", unsafe_allow_html=True)
    tape_cols = st.columns(len(tickers))
    for idx, ticker in enumerate(tickers):
        change = ticker_changes.get(ticker)
        if change is None:
            label = "n/a"
            color = "#8B949E"
        else:
            label = f"{change:+.2%}"
            color = POSITIVE_COLOR if change >= 0 else NEGATIVE_COLOR

        tape_cols[idx].markdown(
            f"<div style='text-align:center; font-size:0.90rem; line-height:1.1rem;'>"
            f"<strong style='font-size:1.1rem; color:#EAECEF;'>{ticker}</strong><br>"
            f"<span style='color:{color};'>{label}</span></div>",
            unsafe_allow_html=True,
        )

    portfolio_values = extract_close_values(history, tickers)
    portfolio_distribution = build_portfolio_distribution(portfolio_values)

    st.subheader("PORTFOLIO ALLOCATION")
    if not portfolio_distribution.empty:
        total_value = portfolio_distribution["value"].sum()
        top_holding = portfolio_distribution.iloc[0]

        portfolio_metrics = st.columns([1, 1, 1])
        portfolio_metrics[0].metric("TOTAL VALUE", f"${total_value:,.2f}")
        portfolio_metrics[1].metric("TOP HOLDING", top_holding["ticker"])
        portfolio_metrics[2].metric("TOP ALLOCATION", f"{top_holding['weight']:.1%}")

        left, right = st.columns([1, 1])
        left.altair_chart(build_portfolio_pie_chart(portfolio_distribution).configure_view(strokeOpacity=0), width='stretch')
        right.dataframe(portfolio_distribution.set_index("ticker"))
    else:
        st.write("Portfolio allocation data is not available.")

    selected_ticker = st.sidebar.selectbox("SELECT TICKER", tickers)
    st.subheader(f"SELECTED SECURITY: {selected_ticker}")

    summary_info = get_ticker_info(selected_ticker)
    summary = build_summary(summary_info)
    peer_df = build_watchlist_fundamentals(tickers)

    if isinstance(history.columns, pd.MultiIndex):
        if selected_ticker in history.columns.levels[0]:
            ticker_history = history[selected_ticker]
        else:
            ticker_history = history
    else:
        ticker_history = history

    tech_tab, fund_tab = st.tabs(["📊 Technical Analysis", "🔍 Fundamental Analysis"])

    def format_metric(value):
        if value is None:
            return "—"
        if isinstance(value, (int, float)):
            try:
                return f"{value:,.2f}"
            except Exception:
                return str(value)
        return str(value)

    with tech_tab:
        if "Close" in ticker_history.columns:
            st.altair_chart(build_candlestick_chart(ticker_history), width='stretch')
        else:
            st.write("No close price data available for the selected ticker.")

        metric_columns = st.columns(3)
        compact_metrics = [
            ("Open", summary["Open"]),
            ("Previous Close", summary["Previous Close"]),
            ("52W High", summary["52 Week High"]),
            ("52W Low", summary["52 Week Low"]),
        ]

        metric_columns[0].markdown(
            f"<div style='padding:0.4rem 0; color:#EAECEF;'>"
            f"<span style='color:#8B949E; font-size:0.75rem; letter-spacing:0.08em;'>Open</span><br>"
            f"<span style='font-size:1.05rem; font-weight:700;'>{format_metric(summary['Open'])}</span></div>",
            unsafe_allow_html=True,
        )
        metric_columns[1].markdown(
            f"<div style='padding:0.4rem 0; color:#EAECEF;'>"
            f"<span style='color:#8B949E; font-size:0.75rem; letter-spacing:0.08em;'>Previous Close</span><br>"
            f"<span style='font-size:1.05rem; font-weight:700;'>{format_metric(summary['Previous Close'])}</span></div>",
            unsafe_allow_html=True,
        )
        metric_columns[2].markdown(
            f"<div style='padding:0.4rem 0; color:#EAECEF;'>"
            f"<span style='color:#8B949E; font-size:0.75rem; letter-spacing:0.08em;'>52W Range</span><br>"
            f"<span style='font-size:1.05rem; font-weight:700;'>{format_metric(summary['52 Week Low'])} — {format_metric(summary['52 Week High'])}</span></div>",
            unsafe_allow_html=True,
        )

    with fund_tab:
        peer_columns = st.columns([1, 1])
        peer_columns[0].altair_chart(build_peer_pe_chart(peer_df, selected_ticker), width='stretch')
        peer_columns[1].altair_chart(build_market_cap_chart(peer_df, selected_ticker), width='stretch')

        vitals_cols = st.columns(2)
        vitals = [
            ("Symbol", summary.get("Symbol", selected_ticker)),
            ("Long Name", summary.get("Name", "—")),
            ("Market Cap", summary.get("Market Cap")),
            ("Trailing P/E", summary.get("PE Ratio")),
        ]
        for col, (label, value) in zip(vitals_cols * 2, vitals):
            col.markdown(
                f"<div style='padding:0.5rem 0; color:#EAECEF;'>"
                f"<span style='color:#8B949E; font-size:0.75rem; letter-spacing:0.08em;'>{label}</span><br>"
                f"<span style='font-size:1.05rem; font-weight:700;'>{format_metric(value)}</span></div>",
                unsafe_allow_html=True,
            )

    st.subheader("RECENT HISTORY")
    st.dataframe(ticker_history.tail(10))


def is_streamlit_context():
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
    except ImportError:
        return False

    if get_script_run_ctx is None:
        return False

    try:
        return get_script_run_ctx(suppress_warning=True) is not None
    except Exception:
        return False


if __name__ == "__main__":
    if not is_streamlit_context():
        print("This app should be run with Streamlit:")
        print("  streamlit run yf.py")
        sys.exit(0)
    main()
