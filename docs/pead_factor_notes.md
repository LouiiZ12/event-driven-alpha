# PEAD Factor Notes

## Signal Definition

The original coursework script used a simple long-only PEAD strategy:

```text
Reported EPS > EPS Estimate
and next-day close reaction >= 2%
```

The upgraded version keeps that economic idea but stores the event-level variables needed for research:

```text
eps_surprise = eps_reported - eps_estimate
surprise_pct = eps_surprise / max(abs(eps_estimate), 0.01)
reaction_1d = close[T+1] / close[T] - 1
pead_score = z(surprise_pct) + z(reaction_1d)
```

## Why T+2 Entry Matters

The reaction filter uses the T+1 close. Entering before T+2 would use information that was not fully available at order time. The upgraded implementation enters at T+2 open, which makes the signal weaker but cleaner.

## Current Research Interpretation

This is best presented as a test of whether public U.S. PEAD alpha has decayed. Weak results are not necessarily a failure. They support the broader research idea that event-driven alpha depends on market structure, investor composition, data quality, and competition.
