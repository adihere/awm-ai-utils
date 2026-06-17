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
    return yf.download(tickers, period="1y", group_by="ticker", auto_adjust=True, threads=True)


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
    if ticker_history is None or ticker_history.empty or len(ticker_history) < 50:
        return None

    if not isinstance(ticker_history.index, pd.DatetimeIndex):
        ticker_history = ticker_history.copy()
        ticker_history.index = pd.to_datetime(ticker_history.index)

    history_df = ticker_history.reset_index().rename(columns={"index": "Date"}).copy()
    history_df["SMA20"] = history_df["Close"].rolling(window=20).mean()
    history_df["SMA50"] = history_df["Close"].rolling(window=50).mean()

    base_chart = alt.Chart(history_df)

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
    )

    sma20_line = base_chart.mark_line(color="#FFA500", point=False, size=2).encode(
        x=alt.X("Date:T"),
        y=alt.Y("SMA20:Q"),
    )

    sma50_line = base_chart.mark_line(color="#1E90FF", point=False, size=2).encode(
        x=alt.X("Date:T"),
        y=alt.Y("SMA50:Q"),
    )

    volume = base_chart.mark_bar(opacity=0.6).encode(
        x=alt.X("Date:T", axis=alt.Axis(labelColor="#EAECEF", titleColor="#EAECEF", domainColor="#8B949E", tickColor="#8B949E")),
        y=alt.Y("Volume:Q", title="Volume", axis=alt.Axis(labelColor="#EAECEF", titleColor="#EAECEF", domainColor="#8B949E", tickColor="#8B949E")),
        color=alt.value("#334155"),
    )

    upper = alt.layer(rules, bars, sma20_line, sma50_line).resolve_scale(y="shared").properties(height=320)
    return alt.vconcat(upper, volume.properties(height=120)).configure_view(strokeOpacity=0)


def calculate_rsi(series, window=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def build_rsi_chart(ticker_history):
    if ticker_history is None or ticker_history.empty or len(ticker_history) < 20:
        return None

    if not isinstance(ticker_history.index, pd.DatetimeIndex):
        ticker_history = ticker_history.copy()
        ticker_history.index = pd.to_datetime(ticker_history.index)

    history_df = ticker_history.reset_index().rename(columns={"index": "Date"}).copy()
    history_df["RSI"] = calculate_rsi(history_df["Close"], 14)

    base = alt.Chart(history_df).encode(
        x=alt.X("Date:T", axis=alt.Axis(labelColor="#EAECEF", titleColor="#EAECEF", domainColor="#8B949E", tickColor="#8B949E")),
    )

    rsi_line = base.mark_line(color="#00FF41", point=False, size=2).encode(
        y=alt.Y("RSI:Q", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(labelColor="#EAECEF", titleColor="#EAECEF", domainColor="#8B949E", tickColor="#8B949E")),
    )

    oversold = alt.Chart(pd.DataFrame({"threshold": [30]})).mark_rule(color="#F8506B", strokeDash=[3]).encode(
        y=alt.Y("threshold:Q", scale=alt.Scale(domain=[0, 100])),
    )

    overbought = alt.Chart(pd.DataFrame({"threshold": [70]})).mark_rule(color="#3AC569", strokeDash=[3]).encode(
        y=alt.Y("threshold:Q", scale=alt.Scale(domain=[0, 100])),
    )

    return alt.layer(rsi_line, oversold, overbought).properties(height=320).resolve_scale(y="independent")


def calculate_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram


def build_macd_chart(ticker_history):
    if ticker_history is None or ticker_history.empty or len(ticker_history) < 30:
        return None

    if not isinstance(ticker_history.index, pd.DatetimeIndex):
        ticker_history = ticker_history.copy()
        ticker_history.index = pd.to_datetime(ticker_history.index)

    history_df = ticker_history.reset_index().rename(columns={"index": "Date"}).copy()
    macd, signal, histogram = calculate_macd(history_df["Close"])
    history_df["MACD"] = macd
    history_df["Signal"] = signal
    history_df["Histogram"] = histogram

    base = alt.Chart(history_df).encode(
        x=alt.X("Date:T", axis=alt.Axis(labelColor="#EAECEF", titleColor="#EAECEF", domainColor="#8B949E", tickColor="#8B949E")),
    )

    macd_line = base.mark_line(color="#00D4FF", size=2).encode(y=alt.Y("MACD:Q", axis=alt.Axis(labelColor="#EAECEF", titleColor="#EAECEF")))
    signal_line = base.mark_line(color="#FFB6C1", size=2).encode(y=alt.Y("Signal:Q"))

    histogram_bar = base.mark_bar(opacity=0.7).encode(
        y=alt.Y("Histogram:Q"),
        color=alt.condition("datum.Histogram >= 0", alt.value(POSITIVE_COLOR), alt.value(NEGATIVE_COLOR)),
    )

    return alt.layer(histogram_bar, macd_line, signal_line).properties(height=300).interactive()


def get_ticker_quarterly_financials(ticker):
    try:
        t = yf.Ticker(ticker)
        return t.quarterly_financials if hasattr(t, 'quarterly_financials') else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def get_ticker_quarterly_cashflow(ticker):
    try:
        t = yf.Ticker(ticker)
        return t.quarterly_cashflow if hasattr(t, 'quarterly_cashflow') else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def build_earnings_chart(ticker):
    financials = get_ticker_quarterly_financials(ticker)
    if financials.empty or "Total Revenue" not in financials.index:
        return None

    try:
        revenue_data = financials.loc["Total Revenue"].iloc[:4].reset_index()
        revenue_data.columns = ["Date", "Revenue"]
        revenue_data["Revenue"] = revenue_data["Revenue"] / 1e9

        net_income_data = financials.loc["Net Income"] if "Net Income" in financials.index else None
        if net_income_data is not None:
            net_income = net_income_data.iloc[:4].reset_index()
            net_income.columns = ["Date", "Net Income"]
            net_income["Net Income"] = net_income["Net Income"] / 1e9
            revenue_data = revenue_data.merge(net_income, on="Date", how="left")

        base = alt.Chart(revenue_data).encode(x=alt.X("Date:T", axis=alt.Axis(labelColor="#EAECEF")))
        revenue_bars = base.mark_bar(color="#1E90FF", opacity=0.7).encode(y=alt.Y("Revenue:Q", axis=alt.Axis(labelColor="#EAECEF")))

        if "Net Income" in revenue_data.columns:
            net_income_line = base.mark_line(color="#00FF41", size=3).encode(y=alt.Y("Net Income:Q"))
            return alt.layer(revenue_bars, net_income_line).properties(height=300)

        return revenue_bars.properties(height=300)
    except Exception:
        return None


def build_fcf_chart(ticker):
    cashflow = get_ticker_quarterly_cashflow(ticker)
    if cashflow.empty or "Operating Cash Flow" not in cashflow.index:
        return None

    try:
        ocf = cashflow.loc["Operating Cash Flow"].iloc[:4].reset_index()
        ocf.columns = ["Date", "OCF"]
        ocf["OCF"] = ocf["OCF"] / 1e9

        capex = cashflow.loc["Capital Expenditures"] if "Capital Expenditures" in cashflow.index else None
        if capex is not None:
            capex_data = capex.iloc[:4].reset_index()
            capex_data.columns = ["Date", "CapEx"]
            capex_data["CapEx"] = capex_data["CapEx"].abs() / 1e9
            ocf = ocf.merge(capex_data, on="Date", how="left")
            ocf["FCF"] = ocf["OCF"] - ocf["CapEx"]

            base = alt.Chart(ocf).encode(x=alt.X("Date:T", axis=alt.Axis(labelColor="#EAECEF")))
            ocf_bars = base.mark_bar(color="#FFB6C1", opacity=0.6).encode(y=alt.Y("OCF:Q", axis=alt.Axis(labelColor="#EAECEF")))
            fcf_line = base.mark_line(color="#00FF41", size=3).encode(y=alt.Y("FCF:Q"))
            return alt.layer(ocf_bars, fcf_line).properties(height=300)

        return ocf.mark_line(color="#00FF41", size=2).encode(x="Date:T", y="OCF:Q").properties(height=300)
    except Exception:
        return None


def calculate_returns_and_correlation(history, tickers):
    try:
        if isinstance(history.columns, pd.MultiIndex):
            close_data = history.xs("Close", level=1, axis=1) if "Close" in history.columns.get_level_values(1) else history
        else:
            close_data = history[["Close"]] if "Close" in history.columns else history

        if isinstance(close_data, pd.Series):
            close_data = close_data.to_frame()

        close_data.columns = tickers[:len(close_data.columns)]
        daily_returns = close_data.pct_change().dropna()
        corr_matrix = daily_returns.corr()
        return corr_matrix
    except Exception:
        return None


def build_correlation_heatmap(corr_matrix):
    if corr_matrix is None or corr_matrix.empty:
        return None

    corr_flat = corr_matrix.reset_index().melt(id_vars="index", var_name="ticker2", value_name="correlation")
    corr_flat.columns = ["ticker1", "ticker2", "correlation"]

    return alt.Chart(corr_flat).mark_rect().encode(
        x=alt.X("ticker2:N", axis=alt.Axis(labelColor="#EAECEF")),
        y=alt.Y("ticker1:N", axis=alt.Axis(labelColor="#EAECEF")),
        color=alt.Color("correlation:Q", scale=alt.Scale(scheme="blueorange", domain=[-1, 0, 1]), legend=alt.Legend(labelColor="#EAECEF", titleColor="#EAECEF")),
        tooltip=["ticker1:N", "ticker2:N", "correlation:Q"],
    ).properties(width=400, height=400)


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

    st.title("BLOOMBERG TERMINAL REPLICA")
    st.markdown("<div style='color:#8B949E; font-size:0.95rem; margin-bottom:0.5rem;'>Professional multi-workspace financial analysis platform with technical, fundamental, and risk analytics.</div>", unsafe_allow_html=True)

    tickers = load_tickers()
    st.sidebar.header("CONFIGURATION")
    st.sidebar.write(", ".join(tickers))

    with st.spinner("Downloading 1-year history..."):
        history = download_price_history(tickers)
        ticker_changes = get_ticker_percent_changes(history, tickers)

    st.markdown("<div style='margin:0.5rem 0 0.75rem 0; padding:0.5rem 0; border-bottom:1px solid #1F2730;'></div>", unsafe_allow_html=True)
    tape_cols = st.columns(len(tickers))
    for idx, ticker in enumerate(tickers):
        change = ticker_changes.get(ticker, 0)
        label = f"{change:+.2%}" if change else "—"
        color = POSITIVE_COLOR if change and change >= 0 else NEGATIVE_COLOR
        tape_cols[idx].markdown(
            f"<div style='text-align:center; font-size:0.85rem;'><strong style='color:#EAECEF;'>{ticker}</strong><br><span style='color:{color};'>{label}</span></div>",
            unsafe_allow_html=True,
        )

    selected_ticker = st.sidebar.selectbox("SELECT TICKER", tickers)

    if isinstance(history.columns, pd.MultiIndex):
        ticker_history = history[selected_ticker] if selected_ticker in history.columns.levels[0] else history
    else:
        ticker_history = history

    summary_info = get_ticker_info(selected_ticker)
    summary = build_summary(summary_info)

    def format_metric(value):
        if value is None:
            return "—"
        if isinstance(value, (int, float)):
            try:
                return f"{value:,.2f}" if abs(value) < 1e9 else f"{value/1e9:.2f}B"
            except Exception:
                return str(value)
        return str(value)

    tech_ws, fund_ws, risk_ws = st.tabs(["📊 Technical Workspace", "🔍 Fundamental Analysis", "🧮 Portfolio & Risk"])

    with tech_ws:
        st.subheader(f"TECHNICAL: {selected_ticker}")
        session_cols = st.columns(4)
        session_cols[0].markdown(f"<div style='padding:0.3rem 0;'><span style='color:#8B949E; font-size:0.7rem;'>OPEN</span><br><span style='font-size:1rem; font-weight:700; color:#EAECEF;'>{format_metric(summary['Open'])}</span></div>", unsafe_allow_html=True)
        session_cols[1].markdown(f"<div style='padding:0.3rem 0;'><span style='color:#8B949E; font-size:0.7rem;'>PREV CLOSE</span><br><span style='font-size:1rem; font-weight:700; color:#EAECEF;'>{format_metric(summary['Previous Close'])}</span></div>", unsafe_allow_html=True)
        session_cols[2].markdown(f"<div style='padding:0.3rem 0;'><span style='color:#8B949E; font-size:0.7rem;'>52W HIGH</span><br><span style='font-size:1rem; font-weight:700; color:#EAECEF;'>{format_metric(summary['52 Week High'])}</span></div>", unsafe_allow_html=True)
        session_cols[3].markdown(f"<div style='padding:0.3rem 0;'><span style='color:#8B949E; font-size:0.7rem;'>52W LOW</span><br><span style='font-size:1rem; font-weight:700; color:#EAECEF;'>{format_metric(summary['52 Week Low'])}</span></div>", unsafe_allow_html=True)

        tech_view = st.selectbox("Select Technical View:", ["Candlestick & SMA", "Relative Strength Index (RSI)", "MACD Oscillator"])

        if tech_view == "Candlestick & SMA":
            chart = build_candlestick_chart(ticker_history)
            if chart:
                st.altair_chart(chart, width='stretch')
            else:
                st.info("Insufficient data for candlestick chart. Requires at least 50 trading days.")
        elif tech_view == "Relative Strength Index (RSI)":
            chart = build_rsi_chart(ticker_history)
            if chart:
                st.altair_chart(chart, width='stretch')
            else:
                st.info("RSI data unavailable. Requires at least 20 trading days.")
        elif tech_view == "MACD Oscillator":
            chart = build_macd_chart(ticker_history)
            if chart:
                st.altair_chart(chart, width='stretch')
            else:
                st.info("MACD data unavailable. Requires at least 30 trading days.")

    with fund_ws:
        st.subheader(f"FUNDAMENTALS: {selected_ticker}")
        vitals_cols = st.columns(4)
        vitals_cols[0].markdown(f"<div style='padding:0.3rem 0;'><span style='color:#8B949E; font-size:0.7rem;'>NAME</span><br><span style='font-size:0.9rem; font-weight:700; color:#EAECEF;'>{summary.get('Name', '—')[:20]}</span></div>", unsafe_allow_html=True)
        vitals_cols[1].markdown(f"<div style='padding:0.3rem 0;'><span style='color:#8B949E; font-size:0.7rem;'>MKT CAP</span><br><span style='font-size:0.9rem; font-weight:700; color:#EAECEF;'>{format_metric(summary.get('Market Cap'))}</span></div>", unsafe_allow_html=True)
        vitals_cols[2].markdown(f"<div style='padding:0.3rem 0;'><span style='color:#8B949E; font-size:0.7rem;'>TRAILING P/E</span><br><span style='font-size:0.9rem; font-weight:700; color:#EAECEF;'>{format_metric(summary.get('PE Ratio'))}</span></div>", unsafe_allow_html=True)
        vitals_cols[3].markdown(f"<div style='padding:0.3rem 0;'><span style='color:#8B949E; font-size:0.7rem;'>SYMBOL</span><br><span style='font-size:0.9rem; font-weight:700; color:#EAECEF;'>{selected_ticker}</span></div>", unsafe_allow_html=True)

        fund_view = st.selectbox("Select Fundamental View:", ["Peer Valuation", "Earnings Profile", "Free Cash Flow"])

        if fund_view == "Peer Valuation":
            peer_df = build_watchlist_fundamentals(tickers)
            pe_chart = build_peer_pe_chart(peer_df, selected_ticker)
            mc_chart = build_market_cap_chart(peer_df, selected_ticker)
            col1, col2 = st.columns([1, 1])
            if pe_chart:
                col1.altair_chart(pe_chart, width='stretch')
            else:
                col1.info("P/E data unavailable for peers.")
            if mc_chart:
                col2.altair_chart(mc_chart, width='stretch')
            else:
                col2.info("Market cap data unavailable.")
        elif fund_view == "Earnings Profile":
            chart = build_earnings_chart(selected_ticker)
            if chart:
                st.altair_chart(chart, width='stretch')
            else:
                st.warning("Earnings data unavailable for this ticker.")
        elif fund_view == "Free Cash Flow":
            chart = build_fcf_chart(selected_ticker)
            if chart:
                st.altair_chart(chart, width='stretch')
            else:
                st.warning("Free cash flow data unavailable for this ticker.")

    with risk_ws:
        st.subheader("PORTFOLIO ALLOCATION & RISK METRICS")
        portfolio_values = extract_close_values(history, tickers)
        portfolio_distribution = build_portfolio_distribution(portfolio_values)

        left_col, right_col = st.columns([1, 1])

        if not portfolio_distribution.empty:
            with left_col:
                st.markdown("**Portfolio Weight Distribution**")
                portfolio_chart = build_portfolio_pie_chart(portfolio_distribution).configure_view(strokeOpacity=0)
                st.altair_chart(portfolio_chart, width='stretch')

            with right_col:
                st.markdown("**Asset Correlation Matrix (30 Days)**")
                corr_matrix = calculate_returns_and_correlation(history, tickers)
                if corr_matrix is not None and not corr_matrix.empty:
                    heatmap = build_correlation_heatmap(corr_matrix)
                    if heatmap:
                        st.altair_chart(heatmap, width='stretch')
                    else:
                        st.warning("Correlation matrix unavailable.")
                else:
                    st.warning("Insufficient data for correlation calculation.")

            st.markdown("---")
            st.markdown("**Portfolio Summary**")
            summary_cols = st.columns(3)
            if not portfolio_distribution.empty:
                total_value = portfolio_distribution["value"].sum()
                top_holding = portfolio_distribution.iloc[0]
                summary_cols[0].metric("TOTAL VALUE", f"${total_value:,.2f}")
                summary_cols[1].metric("TOP HOLDING", top_holding["ticker"])
                summary_cols[2].metric("DIVERSIFICATION", f"{len(portfolio_distribution)} assets")

            st.dataframe(portfolio_distribution.set_index("ticker"))
        else:
            st.warning("Portfolio data unavailable.")


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
