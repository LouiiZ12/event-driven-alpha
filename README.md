# Event-Driven Alpha Across Markets

This repository upgrades a coursework PEAD module into a research-style event-driven alpha project. The public component focuses on a U.S. **Post-Earnings Announcement Drift (PEAD)** signal built from Yahoo Finance data.

## Research Question

Do large-cap U.S. stocks continue to drift after a positive earnings surprise once the market has already confirmed the news through a strong one-day price reaction?

The implemented signal is a **confirmed positive earnings surprise drift factor**:

```text
Long signal = 1
if Reported EPS > Consensus EPS
and close[T+1] / close[T] - 1 >= 2%
```

Positions enter at the **T+2 open**, after the T+1 close is known, and are held for five trading days. This deliberately gives up the initial earnings jump to reduce look-ahead bias and isolate residual post-announcement drift.

## Factor Construction

1. Universe: first `N` S&P 500 tickers from the public constituents file, with `SPY` added as benchmark.
2. Price data: adjusted daily open and close from `yfinance`.
3. Earnings data: earnings date, EPS estimate, and reported EPS from `yfinance`.
4. Surprise filter: `eps_reported - eps_estimate > 0`.
5. Confirmation filter: the stock must rise by at least `min_reaction` from event-day close to next-day close.
6. Entry rule: buy at T+2 open.
7. Exit rule: hold for `hold_days` trading days.
8. Portfolio: equal-weight active event positions.
9. Cost model: one-way commission plus slippage, defaulting to 10 bps total.

The signal table also includes:

- `eps_surprise`
- `surprise_pct`
- `reaction_1d`
- `surprise_z`
- `reaction_z`
- `pead_score = surprise_z + reaction_z`

This makes the project more than a binary trading rule: it creates a ranked event factor that can later be tested by quantiles, holding periods, and thresholds.

## What Was Improved

- Deterministic ticker ordering instead of unordered `set` sampling.
- Explicit signal metadata instead of only entry and exit dates.
- T+2 entry after T+1 confirmation to avoid look-ahead bias.
- Multiple events for the same ticker can coexist without overwriting each other.
- Daily diagnostics track active positions, new positions, and transaction costs.
- Outputs are saved as tables and figures for GitHub/research presentation.
- Data limitations are documented instead of hidden.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python scripts/run_pead.py --max-tickers 300 --start-date 2020-01-01 --end-date 2024-12-31
```

Outputs are written to:

```text
reports/tables/pead_signals.csv
reports/tables/pead_equity_curves.csv
reports/tables/pead_daily_diagnostics.csv
reports/tables/pead_performance_summary.csv
reports/figures/pead_equity_curve.png
reports/figures/pead_score_distribution.png
```

## Example Interview Pitch

I built a public-data PEAD event study to test whether positive earnings surprises still generate residual drift in large-cap U.S. equities. The factor requires both an accounting surprise and a market-confirmed price reaction, then enters at T+2 to avoid look-ahead bias. I implemented an equal-weight event portfolio with transaction costs and daily diagnostics, and documented the limits of Yahoo Finance data, especially the lack of point-in-time earnings timestamps.

## Data Caveats

Yahoo Finance data is public and convenient, but it is not institutional-grade point-in-time data. Earnings estimates, reported EPS, and announcement timestamps may be revised. The current S&P 500 constituents file also introduces survivorship bias. These constraints make the project methodologically reproducible, but exact backtest numbers may change over time.

For a production-grade study, the next upgrade would use point-in-time constituents, timestamped earnings releases, analyst estimate histories, and pre-market/post-market announcement classification.
