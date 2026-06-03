import pandas as pd

from event_alpha.pead_factor import build_pead_signals, run_equal_weight_backtest


def test_build_pead_signals_uses_positive_surprise_and_reaction_filter():
    dates = pd.bdate_range("2024-01-01", periods=10)
    close = pd.DataFrame(
        {
            "AAA": [100, 104, 105, 106, 107, 108, 109, 110, 111, 112],
            "BBB": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
        },
        index=dates,
    )
    earnings = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "earn_date": [dates[0], dates[0]],
            "eps_estimate": [1.0, 1.0],
            "eps_reported": [1.2, 1.2],
        }
    )

    signals = build_pead_signals(earnings, close, hold_days=3, min_reaction=0.02)

    assert len(signals) == 1
    assert signals.loc[0, "ticker"] == "AAA"
    assert signals.loc[0, "entry_date"] == dates[2]
    assert signals.loc[0, "reaction_1d"] >= 0.02


def test_backtest_allows_overlapping_same_ticker_events():
    dates = pd.bdate_range("2024-01-01", periods=8)
    close = pd.DataFrame({"AAA": [100, 101, 102, 103, 104, 105, 106, 107], "SPY": [100] * 8}, index=dates)
    open_ = close - 0.5
    signals = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA"],
            "entry_date": [dates[1], dates[2]],
            "exit_date": [dates[4], dates[5]],
        }
    )

    curves, diagnostics = run_equal_weight_backtest(close, open_, signals, one_way_cost=0.0)

    assert curves["strategy"].iloc[-1] > 1.0
    assert diagnostics.loc[dates[2], "active_positions"] == 2
