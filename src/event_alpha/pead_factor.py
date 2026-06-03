from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


FALLBACK_TICKERS = [
    "SPY",
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOG",
    "NVDA",
    "TSLA",
    "META",
    "AMD",
    "INTC",
    "NFLX",
]


@dataclass(frozen=True)
class PEADConfig:
    start_date: str = "2020-01-01"
    end_date: str = "2024-12-31"
    max_tickers: int = 300
    hold_days: int = 5
    min_reaction: float = 0.02
    commission: float = 0.0005
    slippage: float = 0.0005
    risk_free_rate: float = 0.03
    output_dir: Path = Path("reports")

    @property
    def one_way_cost(self) -> float:
        return self.commission + self.slippage


def get_sp500_tickers(max_tickers: int = 300) -> list[str]:
    """Load a deterministic S&P 500 ticker sample with SPY as benchmark."""
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
    try:
        df = pd.read_csv(url)
        tickers = (
            df["Symbol"]
            .astype(str)
            .str.replace(".", "-", regex=False)
            .dropna()
            .drop_duplicates()
            .head(max_tickers)
            .tolist()
        )
    except Exception:
        tickers = FALLBACK_TICKERS[1:max_tickers]

    tickers = ["SPY", *[ticker for ticker in tickers if ticker != "SPY"]]
    return tickers[: max_tickers + 1]


def download_price_data(tickers: list[str], start: str, end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Download adjusted open/close prices from Yahoo Finance."""
    import yfinance as yf

    data = yf.download(
        tickers,
        start=start,
        end=end,
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=True,
    )

    if len(tickers) == 1:
        ticker = tickers[0]
        close = data["Close"].to_frame(name=ticker)
        open_ = data["Open"].to_frame(name=ticker)
    else:
        close = data.xs("Close", level=1, axis=1)
        open_ = data.xs("Open", level=1, axis=1)

    close.index = pd.to_datetime(close.index).tz_localize(None)
    open_.index = pd.to_datetime(open_.index).tz_localize(None)
    return close.sort_index().ffill(), open_.sort_index().ffill()


def get_earnings_calendar(tickers: list[str]) -> pd.DataFrame:
    """Fetch Yahoo Finance earnings dates and EPS fields."""
    import yfinance as yf

    frames: list[pd.DataFrame] = []
    for ticker in tickers:
        if ticker == "SPY":
            continue
        try:
            df = yf.Ticker(ticker).earnings_dates
        except Exception:
            continue

        if df is None or df.empty:
            continue

        df = df.reset_index().rename(
            columns={
                "Earnings Date": "earn_date",
                "EPS Estimate": "eps_estimate",
                "Reported EPS": "eps_reported",
            }
        )
        if not {"earn_date", "eps_estimate", "eps_reported"}.issubset(df.columns):
            continue

        df["ticker"] = ticker
        df["earn_date"] = pd.to_datetime(df["earn_date"], errors="coerce").dt.tz_localize(None)
        frames.append(df[["ticker", "earn_date", "eps_estimate", "eps_reported"]])

    if not frames:
        return pd.DataFrame(columns=["ticker", "earn_date", "eps_estimate", "eps_reported"])

    earnings = pd.concat(frames, ignore_index=True)
    return earnings.dropna(subset=["ticker", "earn_date"]).drop_duplicates()


def build_pead_signals(
    earnings: pd.DataFrame,
    close: pd.DataFrame,
    hold_days: int = 5,
    min_reaction: float = 0.02,
) -> pd.DataFrame:
    """Build a confirmed-positive-surprise PEAD signal table.

    The signal goes long after both conditions are known:
    1. reported EPS exceeds consensus EPS;
    2. the stock closes at least `min_reaction` higher from T to T+1.
    Entry is delayed to T+2 open to avoid using the T+1 close before it exists.
    """
    required = {"ticker", "earn_date", "eps_estimate", "eps_reported"}
    missing = required.difference(earnings.columns)
    if missing:
        raise ValueError(f"earnings is missing columns: {sorted(missing)}")

    events: list[dict[str, object]] = []
    trading_days = close.index
    earnings = earnings.dropna(subset=["eps_estimate", "eps_reported"]).copy()

    for row in earnings.itertuples(index=False):
        ticker = row.ticker
        if ticker not in close.columns:
            continue

        event_loc = trading_days.searchsorted(row.earn_date)
        if event_loc >= len(trading_days) - hold_days - 2:
            continue

        event_date = trading_days[event_loc]
        confirm_date = trading_days[event_loc + 1]
        entry_date = trading_days[event_loc + 2]
        exit_date = trading_days[min(event_loc + 2 + hold_days, len(trading_days) - 1)]

        eps_surprise = row.eps_reported - row.eps_estimate
        if eps_surprise <= 0:
            continue

        event_close = close.at[event_date, ticker]
        confirm_close = close.at[confirm_date, ticker]
        if pd.isna(event_close) or pd.isna(confirm_close) or event_close <= 0:
            continue

        reaction = confirm_close / event_close - 1
        if reaction < min_reaction:
            continue

        surprise_pct = eps_surprise / max(abs(row.eps_estimate), 0.01)
        events.append(
            {
                "ticker": ticker,
                "earn_date": row.earn_date,
                "event_date": event_date,
                "confirm_date": confirm_date,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "eps_estimate": row.eps_estimate,
                "eps_reported": row.eps_reported,
                "eps_surprise": eps_surprise,
                "surprise_pct": surprise_pct,
                "reaction_1d": reaction,
            }
        )

    signals = pd.DataFrame(events)
    if signals.empty:
        return signals

    signals["surprise_z"] = _zscore(signals["surprise_pct"])
    signals["reaction_z"] = _zscore(signals["reaction_1d"])
    signals["pead_score"] = signals["surprise_z"] + signals["reaction_z"]
    return signals.sort_values(["entry_date", "pead_score"], ascending=[True, False]).reset_index(drop=True)


def _zscore(series: pd.Series) -> pd.Series:
    std = series.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def run_equal_weight_backtest(
    close: pd.DataFrame,
    open_: pd.DataFrame,
    signals: pd.DataFrame,
    one_way_cost: float = 0.001,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run an equal-weight event portfolio and return curves plus daily diagnostics."""
    dates = close.index
    spy = close["SPY"] / close["SPY"].iloc[0] if "SPY" in close.columns else pd.Series(index=dates, dtype=float)

    if signals.empty:
        curves = pd.DataFrame({"strategy": 1.0, "benchmark": spy}, index=dates)
        diagnostics = pd.DataFrame({"active_positions": 0, "new_positions": 0, "cost": 0.0}, index=dates)
        return curves, diagnostics

    signals = signals.copy()
    signals["entry_date"] = pd.to_datetime(signals["entry_date"])
    signals["exit_date"] = pd.to_datetime(signals["exit_date"])
    entry_dict = {
        entry_date: group.to_dict("records")
        for entry_date, group in signals.groupby("entry_date", sort=False)
    }

    close_ret = close.pct_change(fill_method=None).fillna(0.0)
    active: dict[tuple[str, pd.Timestamp], dict[str, object]] = {}
    strategy_value = 1.0
    curve_values: list[float] = []
    diagnostic_rows: list[dict[str, float]] = []

    for date in dates:
        active = {key: pos for key, pos in active.items() if date <= pos["exit_date"]}

        todays_entries = entry_dict.get(date, [])
        for trade in todays_entries:
            key = (trade["ticker"], pd.Timestamp(trade["entry_date"]))
            active[key] = trade

        returns = []
        for (ticker, entry_date), _trade in active.items():
            if ticker not in close.columns:
                continue
            if date == entry_date:
                day_open = open_.at[date, ticker]
                day_close = close.at[date, ticker]
                ret = day_close / day_open - 1 if pd.notna(day_open) and day_open > 0 else 0.0
            else:
                ret = close_ret.at[date, ticker]
            returns.append(0.0 if pd.isna(ret) else float(ret))

        day_return = float(np.mean(returns)) if returns else 0.0
        cost = one_way_cost * len(todays_entries) / max(len(active), 1) if active else 0.0
        day_return -= cost
        strategy_value *= 1 + day_return
        curve_values.append(strategy_value)
        diagnostic_rows.append(
            {
                "daily_return": day_return,
                "active_positions": float(len(active)),
                "new_positions": float(len(todays_entries)),
                "cost": cost,
            }
        )

    curves = pd.DataFrame({"strategy": curve_values, "benchmark": spy}, index=dates)
    curves = curves / curves.iloc[0]
    diagnostics = pd.DataFrame(diagnostic_rows, index=dates)
    return curves, diagnostics


def performance_stats(curve: pd.Series, risk_free_rate: float = 0.03) -> dict[str, float]:
    returns = curve.pct_change(fill_method=None).dropna()
    if returns.empty:
        return {
            "annual_return": 0.0,
            "annual_volatility": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
        }

    annual_return = returns.mean() * 252
    annual_vol = returns.std(ddof=0) * np.sqrt(252)
    drawdown = curve / curve.cummax() - 1
    max_drawdown = drawdown.min()
    sharpe = (annual_return - risk_free_rate) / annual_vol if annual_vol > 0 else 0.0
    calmar = annual_return / abs(max_drawdown) if max_drawdown < 0 else 0.0
    return {
        "annual_return": annual_return,
        "annual_volatility": annual_vol,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "calmar": calmar,
    }


def summarize_results(curves: pd.DataFrame, diagnostics: pd.DataFrame, config: PEADConfig) -> pd.DataFrame:
    rows = []
    for col, label in [("strategy", "PEAD Strategy"), ("benchmark", "SPY Benchmark")]:
        stats = performance_stats(curves[col], config.risk_free_rate)
        stats["name"] = label
        rows.append(stats)
    summary = pd.DataFrame(rows).set_index("name")
    summary.loc["PEAD Strategy", "active_days"] = float((diagnostics["active_positions"] > 0).sum())
    summary.loc["PEAD Strategy", "avg_active_positions"] = diagnostics["active_positions"].mean()
    summary.loc["PEAD Strategy", "total_new_positions"] = diagnostics["new_positions"].sum()
    return summary


def save_outputs(curves: pd.DataFrame, diagnostics: pd.DataFrame, signals: pd.DataFrame, summary: pd.DataFrame, output_dir: Path) -> None:
    tables_dir = output_dir / "tables"
    figures_dir = output_dir / "figures"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    curves.to_csv(tables_dir / "pead_equity_curves.csv", index_label="date")
    diagnostics.to_csv(tables_dir / "pead_daily_diagnostics.csv", index_label="date")
    signals.to_csv(tables_dir / "pead_signals.csv", index=False)
    summary.to_csv(tables_dir / "pead_performance_summary.csv")

    try:
        import matplotlib.pyplot as plt
    except Exception:
        return

    fig, ax = plt.subplots(figsize=(11, 6))
    curves["strategy"].plot(ax=ax, label="PEAD Strategy", linewidth=2.2)
    curves["benchmark"].plot(ax=ax, label="SPY Benchmark", linestyle="--", alpha=0.8)
    ax.set_title("Confirmed Positive Earnings Surprise Drift")
    ax.set_ylabel("Cumulative value")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(figures_dir / "pead_equity_curve.png", dpi=180)
    plt.close(fig)

    if not signals.empty:
        fig, ax = plt.subplots(figsize=(9, 5))
        signals["pead_score"].hist(bins=30, ax=ax)
        ax.set_title("PEAD Signal Score Distribution")
        ax.set_xlabel("surprise z-score + reaction z-score")
        ax.set_ylabel("event count")
        fig.tight_layout()
        fig.savefig(figures_dir / "pead_score_distribution.png", dpi=180)
        plt.close(fig)


def run_pipeline(config: PEADConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tickers = get_sp500_tickers(config.max_tickers)
    close, open_ = download_price_data(tickers, config.start_date, config.end_date)
    earnings = get_earnings_calendar(tickers)
    signals = build_pead_signals(earnings, close, config.hold_days, config.min_reaction)
    curves, diagnostics = run_equal_weight_backtest(close, open_, signals, config.one_way_cost)
    summary = summarize_results(curves, diagnostics, config)
    save_outputs(curves, diagnostics, signals, summary, config.output_dir)
    return signals, curves, diagnostics, summary


def parse_args() -> PEADConfig:
    parser = argparse.ArgumentParser(description="Run the PEAD event-driven alpha study.")
    parser.add_argument("--start-date", default=PEADConfig.start_date)
    parser.add_argument("--end-date", default=PEADConfig.end_date)
    parser.add_argument("--max-tickers", type=int, default=PEADConfig.max_tickers)
    parser.add_argument("--hold-days", type=int, default=PEADConfig.hold_days)
    parser.add_argument("--min-reaction", type=float, default=PEADConfig.min_reaction)
    parser.add_argument("--commission", type=float, default=PEADConfig.commission)
    parser.add_argument("--slippage", type=float, default=PEADConfig.slippage)
    parser.add_argument("--output-dir", type=Path, default=PEADConfig.output_dir)
    args = parser.parse_args()
    return PEADConfig(**vars(args))


def main() -> None:
    config = parse_args()
    signals, _curves, _diagnostics, summary = run_pipeline(config)
    print(f"Signals generated: {len(signals):,}")
    print(summary.applymap(lambda x: f"{x:.4f}" if isinstance(x, float) else x).to_string())


if __name__ == "__main__":
    main()
