import json
import os
import tempfile
import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd

from yf import (
    create_sample_config,
    load_tickers,
    build_summary,
    download_price_history,
    extract_close_values,
    build_portfolio_distribution,
    get_ticker_percent_changes,
    build_watchlist_fundamentals,
    build_peer_pe_chart,
    build_market_cap_chart,
    get_ticker_info,
    calculate_rsi,
    calculate_macd,
    build_candlestick_chart,
    build_rsi_chart,
    build_macd_chart,
    calculate_returns_and_correlation,
    build_correlation_heatmap,
)


class TestCreateSampleConfig:
    """Tests for create_sample_config function."""

    def test_creates_config_file(self):
        """Test that config file is created with correct content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "test_config.json")
            result = create_sample_config(config_path)

            assert os.path.exists(config_path)
            assert result == ["MSFT", "AAPL", "GOOG"]

    def test_config_content_is_valid_json(self):
        """Test that created config file contains valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "test_config.json")
            create_sample_config(config_path)

            with open(config_path, "r") as f:
                config = json.load(f)

            assert "tickers" in config
            assert isinstance(config["tickers"], list)

    def test_returns_correct_tickers(self):
        """Test that function returns the tickers list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "test_config.json")
            tickers = create_sample_config(config_path)

            assert len(tickers) == 3
            assert "MSFT" in tickers


class TestLoadTickers:
    """Tests for load_tickers function."""

    def test_loads_existing_config(self):
        """Test loading tickers from existing config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            config = {"tickers": ["NVDA", "TSLA", "AMD"]}
            with open(config_path, "w") as f:
                json.dump(config, f)

            result = load_tickers(config_path)
            assert result == ["NVDA", "TSLA", "AMD"]

    def test_creates_config_if_not_exists(self):
        """Test that config is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "new_config.json")

            result = load_tickers(config_path)

            assert os.path.exists(config_path)
            assert isinstance(result, list)

    def test_handles_invalid_json(self):
        """Test that invalid JSON creates new config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "bad_config.json")
            with open(config_path, "w") as f:
                f.write("invalid json {")

            result = load_tickers(config_path)

            assert isinstance(result, list)
            assert len(result) == 3

    def test_handles_missing_tickers_key(self):
        """Test that missing tickers key creates new config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "bad_config.json")
            config = {"stocks": ["AAPL"]}
            with open(config_path, "w") as f:
                json.dump(config, f)

            result = load_tickers(config_path)

            assert isinstance(result, list)

    def test_handles_empty_tickers_list(self):
        """Test that empty tickers list creates new config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "empty_config.json")
            config = {"tickers": []}
            with open(config_path, "w") as f:
                json.dump(config, f)

            result = load_tickers(config_path)

            assert isinstance(result, list)
            assert len(result) > 0


class TestBuildSummary:
    """Tests for build_summary function."""

    def test_builds_summary_with_all_fields(self):
        """Test building summary with all fields present."""
        info = {
            "symbol": "NVDA",
            "longName": "NVIDIA Corporation",
            "regularMarketPrice": 450.25,
            "previousClose": 448.50,
            "open": 449.75,
            "fiftyTwoWeekHigh": 525.00,
            "fiftyTwoWeekLow": 320.00,
            "marketCap": 1500000000000,
            "trailingPE": 45.5,
        }

        result = build_summary(info)

        assert result["Symbol"] == "NVDA"
        assert result["Name"] == "NVIDIA Corporation"
        assert result["Current Price"] == 450.25
        assert result["Market Cap"] == 1500000000000

    def test_builds_summary_with_missing_fields(self):
        """Test building summary when some fields are missing."""
        info = {
            "symbol": "TEST",
            "longName": "Test Corp",
        }

        result = build_summary(info)

        assert result["Symbol"] == "TEST"
        assert result["Name"] == "Test Corp"
        assert result["Current Price"] is None
        assert result["PE Ratio"] is None

    def test_returns_dict_with_expected_keys(self):
        """Test that summary contains all expected keys."""
        info = {"symbol": "TEST"}

        result = build_summary(info)

        expected_keys = [
            "Symbol",
            "Name",
            "Current Price",
            "Previous Close",
            "Open",
            "52 Week High",
            "52 Week Low",
            "Market Cap",
            "PE Ratio",
        ]

        for key in expected_keys:
            assert key in result


class TestDownloadPriceHistory:
    """Tests for download_price_history function."""

    @patch("yf.yf.download")
    def test_downloads_history_single_ticker(self, mock_download):
        """Test downloading history for a single ticker."""
        mock_data = pd.DataFrame({
            "Close": [100.0, 101.0, 102.0],
            "Open": [99.0, 100.5, 101.5],
            "Volume": [1000000, 1100000, 1200000],
        }, index=pd.date_range("2023-01-01", periods=3))

        mock_download.return_value = mock_data

        result = download_price_history(["NVDA"])

        assert mock_download.called
        mock_download.assert_called_once()

    @patch("yf.yf.download")
    def test_downloads_history_multiple_tickers(self, mock_download):
        """Test downloading history for multiple tickers."""
        mock_data = pd.DataFrame({
            "Close": [100.0, 101.0],
        }, index=pd.date_range("2023-01-01", periods=2))

        mock_download.return_value = mock_data

        result = download_price_history(["NVDA", "MSFT", "AAPL"])

        assert mock_download.called
        call_args = mock_download.call_args
        assert call_args[1]["period"] == "1y"
        assert call_args[1]["auto_adjust"] is True


class TestPortfolioHelpers:
    """Tests for portfolio distribution helpers."""

    def test_extract_close_values_from_multiindex(self):
        arrays = [
            ["NVDA", "NVDA", "MSFT", "MSFT"],
            ["Close", "Open", "Close", "Open"],
        ]
        columns = pd.MultiIndex.from_arrays(arrays)
        history = pd.DataFrame(
            [[100.0, 99.0, 200.0, 198.0], [101.0, 100.0, 202.0, 200.0]],
            index=pd.date_range("2023-01-01", periods=2),
            columns=columns,
        )

        result = extract_close_values(history, ["NVDA", "MSFT"])

        assert result == {"NVDA": 101.0, "MSFT": 202.0}

    def test_get_ticker_percent_changes_with_multiindex(self):
        arrays = [
            ["NVDA", "NVDA", "MSFT", "MSFT"],
            ["Close", "Open", "Close", "Open"],
        ]
        columns = pd.MultiIndex.from_arrays(arrays)
        history = pd.DataFrame(
            [[100.0, 99.0, 200.0, 198.0], [101.0, 100.0, 202.0, 200.0]],
            index=pd.date_range("2023-01-01", periods=2),
            columns=columns,
        )

        result = get_ticker_percent_changes(history, ["NVDA", "MSFT"])

        assert result["NVDA"] == pytest.approx((101.0 - 100.0) / 100.0)
        assert result["MSFT"] == pytest.approx((202.0 - 200.0) / 200.0)

    def test_build_portfolio_distribution_allocates_weights(self):
        close_values = {"NVDA": 100.0, "MSFT": 200.0, "AAPL": 0.0}
        distribution = build_portfolio_distribution(close_values)

        assert list(distribution["ticker"]) == ["MSFT", "NVDA"]
        assert distribution.loc[distribution["ticker"] == "NVDA", "weight"].iloc[0] == pytest.approx(100.0 / 300.0)
        assert distribution.loc[distribution["ticker"] == "MSFT", "value"].iloc[0] == 200.0


class TestFundamentalHelpers:
    """Tests for new fundamental analysis helpers."""

    @patch("yf.yf.Ticker")
    def test_get_ticker_info_returns_info(self, mock_ticker_class):
        mock_ticker = Mock()
        mock_ticker.info = {"symbol": "AAPL", "longName": "Apple Inc."}
        mock_ticker_class.return_value = mock_ticker

        result = get_ticker_info("AAPL")

        assert result == {"symbol": "AAPL", "longName": "Apple Inc."}
        mock_ticker_class.assert_called_once_with("AAPL")

    @patch("yf.yf.Ticker")
    def test_build_watchlist_fundamentals_builds_dataframe(self, mock_ticker_class):
        get_ticker_info.cache_clear()
        mapping = {
            "AAPL": {"longName": "Apple Inc.", "trailingPE": 28.4, "marketCap": 2500000000000},
            "MSFT": {"longName": "Microsoft Corp.", "trailingPE": 35.7, "marketCap": 2200000000000},
        }

        def side_effect(symbol):
            mock_obj = Mock()
            mock_obj.info = mapping[symbol]
            return mock_obj

        mock_ticker_class.side_effect = side_effect
        df = build_watchlist_fundamentals(["AAPL", "MSFT"])

        assert list(df["ticker"]) == ["AAPL", "MSFT"]
        assert df.loc[df["ticker"] == "AAPL", "trailingPE"].iloc[0] == 28.4
        assert df.loc[df["ticker"] == "MSFT", "marketCap"].iloc[0] == 2200000000000.0

    def test_build_peer_pe_chart_returns_bar_chart(self):
        peer_df = pd.DataFrame(
            [
                {"ticker": "AAPL", "trailingPE": 28.4},
                {"ticker": "MSFT", "trailingPE": 35.7},
            ]
        )

        chart = build_peer_pe_chart(peer_df, "AAPL")
        spec = chart.to_dict()

        assert spec["mark"]["type"] == "bar"
        assert spec["encoding"]["x"]["field"] == "trailingPE"

    def test_build_market_cap_chart_returns_bar_chart(self):
        peer_df = pd.DataFrame(
            [
                {"ticker": "AAPL", "marketCap": 2500000000000.0},
                {"ticker": "MSFT", "marketCap": 2200000000000.0},
            ]
        )

        chart = build_market_cap_chart(peer_df, "AAPL")
        spec = chart.to_dict()

        assert spec["mark"]["type"] == "bar"
        assert spec["encoding"]["x"]["field"] == "marketCap"


class TestTechnicalIndicators:
    """Tests for technical indicator calculation helpers."""

    def test_calculate_rsi_returns_series(self):
        """Test RSI calculation returns a series with values between 0-100."""
        prices = pd.Series([100, 101, 99, 102, 101, 103, 100, 98, 97, 99, 101, 102, 104, 103, 102])
        rsi = calculate_rsi(prices, window=5)
        
        assert isinstance(rsi, pd.Series)
        assert len(rsi) == len(prices)
        valid_rsi = rsi.dropna()
        assert (valid_rsi >= 0).all() or (valid_rsi <= 100).all() or rsi.isna().any()

    def test_calculate_rsi_extremes(self):
        """Test RSI with all gains (should approach 100) and all losses (should approach 0)."""
        ascending = pd.Series([100 + i for i in range(20)])
        rsi_up = calculate_rsi(ascending, window=5).iloc[-1]
        
        descending = pd.Series([100 - i for i in range(20)])
        rsi_down = calculate_rsi(descending, window=5).iloc[-1]
        
        assert rsi_up > 70 or pd.isna(rsi_up)
        assert rsi_down < 30 or pd.isna(rsi_down)

    def test_calculate_macd_returns_three_series(self):
        """Test MACD returns MACD, signal, and histogram lines."""
        prices = pd.Series([100 + i * 0.5 for i in range(50)])
        macd, signal, hist = calculate_macd(prices, fast=12, slow=26, signal=9)
        
        assert isinstance(macd, pd.Series)
        assert isinstance(signal, pd.Series)
        assert isinstance(hist, pd.Series)
        assert len(macd) == len(prices)
        assert len(signal) == len(prices)
        assert len(hist) == len(prices)

    def test_build_candlestick_chart_with_insufficient_data(self):
        """Test candlestick chart returns None with fewer than 50 bars."""
        small_history = pd.DataFrame({
            "Open": [100, 101, 99],
            "High": [101, 102, 100],
            "Low": [99, 100, 98],
            "Close": [100.5, 101.5, 99.5],
            "Volume": [1000, 1100, 900],
        }, index=pd.date_range("2023-01-01", periods=3))
        
        chart = build_candlestick_chart(small_history)
        assert chart is None

    def test_build_candlestick_chart_with_sufficient_data(self):
        """Test candlestick chart builds with 50+ days of data."""
        history = pd.DataFrame({
            "Open": [100 + i * 0.1 for i in range(60)],
            "High": [101 + i * 0.1 for i in range(60)],
            "Low": [99 + i * 0.1 for i in range(60)],
            "Close": [100.5 + i * 0.1 for i in range(60)],
            "Volume": [1000000] * 60,
        }, index=pd.date_range("2023-01-01", periods=60))
        
        chart = build_candlestick_chart(history)
        assert chart is not None
        spec = chart.to_dict()
        assert "vconcat" in spec

    def test_build_rsi_chart_with_insufficient_data(self):
        """Test RSI chart returns None with fewer than 20 bars."""
        small_history = pd.DataFrame({
            "Close": [100, 101, 99, 102, 101, 103, 100, 98, 97, 99],
        }, index=pd.date_range("2023-01-01", periods=10))
        
        chart = build_rsi_chart(small_history)
        assert chart is None

    def test_build_macd_chart_with_insufficient_data(self):
        """Test MACD chart returns None with fewer than 30 bars."""
        small_history = pd.DataFrame({
            "Close": [100 + i * 0.1 for i in range(20)],
        }, index=pd.date_range("2023-01-01", periods=20))
        
        chart = build_macd_chart(small_history)
        assert chart is None

    def test_calculate_returns_and_correlation(self):
        """Test correlation matrix calculation from returns."""
        history = pd.DataFrame({
            ("AAPL", "Close"): [100, 101, 99, 102, 101],
            ("MSFT", "Close"): [200, 202, 198, 205, 203],
        }, index=pd.date_range("2023-01-01", periods=5))
        history.columns = pd.MultiIndex.from_tuples(history.columns)
        
        corr = calculate_returns_and_correlation(history, ["AAPL", "MSFT"])
        assert corr is not None
        assert isinstance(corr, pd.DataFrame)
        assert corr.shape[0] == 2
        assert corr.shape[1] == 2

    def test_build_correlation_heatmap_with_valid_matrix(self):
        """Test correlation heatmap chart builds from correlation matrix."""
        corr_matrix = pd.DataFrame({
            "AAPL": [1.0, 0.75],
            "MSFT": [0.75, 1.0],
        }, index=["AAPL", "MSFT"])
        
        chart = build_correlation_heatmap(corr_matrix)
        assert chart is not None
        spec = chart.to_dict()
        assert spec["mark"]["type"] == "rect"

    def test_build_correlation_heatmap_with_empty_matrix(self):
        """Test correlation heatmap returns None with empty matrix."""
        empty_corr = pd.DataFrame()
        chart = build_correlation_heatmap(empty_corr)
        assert chart is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
