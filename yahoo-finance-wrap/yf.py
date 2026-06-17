import json
import os
import sys

import altair as alt
import pandas as pd
import yfinance as yf

CONFIG_PATH = "tickers_config.json"


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


def build_portfolio_pie_chart(distribution):
    return alt.Chart(distribution).mark_arc(innerRadius=50).encode(
        theta=alt.Theta(field="value", type="quantitative"),
        color=alt.Color(field="ticker", type="nominal", legend=alt.Legend(title="Ticker")),
        tooltip=[
            alt.Tooltip("ticker:N", title="Ticker"),
            alt.Tooltip("value:Q", title="Value", format=",.2f"),
            alt.Tooltip("weight:Q", title="Weight", format=".1%"),
        ],
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

    st.title("Stock Performance Dashboard")
    st.write("This dashboard loads tickers from `tickers_config.json` and shows the latest performance metrics.")

    tickers = load_tickers()
    st.sidebar.header("Configuration")
    st.sidebar.write("Use `tickers_config.json` to change the symbol list.")
    st.sidebar.write(", ".join(tickers))

    with st.spinner("Downloading history..."):
        history = download_price_history(tickers)

    portfolio_values = extract_close_values(history, tickers)
    portfolio_distribution = build_portfolio_distribution(portfolio_values)

    st.subheader("Portfolio allocation")
    if not portfolio_distribution.empty:
        total_value = portfolio_distribution["value"].sum()
        top_holding = portfolio_distribution.iloc[0]

        cols = st.columns(3)
        cols[0].metric("Total portfolio value", f"${total_value:,.2f}")
        cols[1].metric("Top holding", top_holding["ticker"])
        cols[2].metric("Top allocation", f"{top_holding['weight']:.1%}")

        st.altair_chart(build_portfolio_pie_chart(portfolio_distribution), use_container_width=True)
        st.dataframe(portfolio_distribution.set_index("ticker"))
    else:
        st.write("Portfolio allocation data is not available.")

    selected_ticker = st.sidebar.selectbox("Select ticker", tickers)
    st.subheader(f"Selected ticker: {selected_ticker}")

    summary_info = yf.Ticker(selected_ticker).info
    summary = build_summary(summary_info)
    df_summary = pd.DataFrame.from_dict(summary, orient="index", columns=["Value"])

    def _fmt(v):
        if v is None:
            return ""
        if isinstance(v, (int, float)):
            try:
                return f"{v:,.2f}"
            except Exception:
                return str(v)
        return str(v)

    df_summary["Value"] = df_summary["Value"].apply(_fmt)
    st.table(df_summary)

    if isinstance(history.columns, pd.MultiIndex):
        if selected_ticker in history.columns.levels[0]:
            ticker_history = history[selected_ticker]
        else:
            ticker_history = history
    else:
        ticker_history = history

    if "Close" in ticker_history.columns:
        close = ticker_history["Close"]
        if isinstance(close, pd.Series):
            st.line_chart(close.to_frame(name=selected_ticker))
        else:
            st.line_chart(close.rename(columns={"Close": selected_ticker}))
    else:
        st.write("No close price data available for the selected ticker.")

    st.subheader("Recent history")
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
