# PEAD Upgrade Summary

## New Positioning

The PEAD component is now framed as a **confirmed positive earnings surprise drift factor**:

```text
Reported EPS > Consensus EPS
and close[T+1] / close[T] - 1 >= min_reaction
```

Entry occurs at T+2 open, after the T+1 confirmation close is observable.

## Problems Fixed

- Replaced nondeterministic ticker sampling caused by `set(tickers)`.
- Stored full event metadata instead of only entry/exit dates.
- Added ranked factor fields: `surprise_pct`, `reaction_1d`, `surprise_z`, `reaction_z`, and `pead_score`.
- Avoided same-ticker event overwrites by keying active positions by `(ticker, entry_date)`.
- Added daily diagnostics for active positions, new positions, and transaction costs.
- Added CSV and figure output hooks for GitHub presentation.
- Documented Yahoo Finance data limitations and survivorship bias.

## Research Pitch

This project tests whether PEAD still exists in large-cap U.S. equities after requiring both an accounting surprise and market-confirmed price reaction. Weak or unstable results are not a failure; they support the broader claim that event-driven alpha is market-structure dependent and harder to capture in highly efficient markets with public non-point-in-time data.

## Created Files

- `README.md`
- `pyproject.toml`
- `requirements.txt`
- `src/event_alpha/pead_factor.py`
- `scripts/run_pead.py`
- `docs/pead_factor_notes.md`
- `tests/test_pead_factor.py`
