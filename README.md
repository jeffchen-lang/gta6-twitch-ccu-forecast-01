# GTA VI launch-day Twitch viewers — forecaster

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/jeffchen-lang/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/jeffchen-lang/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Built for the [make.fun bounty](https://make.fun/bounty/gta6-twitch-ccu-forecast-01): forecast GTA VI's launch-day Twitch viewers hour by hour.

`main.py` (Python 3.13, stdlib only, no network) forecasts hours 2–24 of
GTA VI's release day on Twitch, five quantiles per hour, from the case's
comparables (past big launches' hourly counts).

## Model

A shape model over log ratios. For each comparable launch, every release-day
hour is expressed as a log ratio to that launch's own hour-1 viewers,
`r_h = ln(viewers_h / viewers_1)`. Hour h's forecast is
`hour1_print * exp(quantile of r_h)` across comparables.

Two filters make the distribution fit a rolling-midnight console launch:

- **Late-peak only.** Keep comparables whose release-day peak falls at hour
  12 or later. Simultaneous global launches peak at hour 1 and fall all day;
  a rolling midnight unlock climbs as time zones wake up. This drops the five
  early-peak comparables (ELDEN RING, Cyberpunk 2077, Starfield, Borderlands
  4, Elden Ring Nightreign).
- **Scale weighting.** A comparable's weight is a Gaussian kernel on the log
  distance between its hour-1 viewers and the target's hour-1 print
  (sigma = 0.8). A launch's growth ratio depends on its scale: small hour-1
  launches grow many times over the day, huge ones barely double. Without
  this the median is dragged up by tiny launches that exploded 100x from a
  few hundred viewers.

Quantiles are the weighted 5th/25th/50th/75th/95th percentiles of the log
ratios at each hour. A minimum 90% band width of 0.5 log units guards against
a false certainty when the target's hour 1 sits far outside the comparable
range. Hour-1 prints below 1 count as 1; a comparable hour of 0 is skipped;
an hour with no usable comparable falls back to the house baseline's
persistence forecast.

## Practice results (pinball loss, lower is better)

| case | this model | house baseline |
| --- | --- | --- |
| p00 Marvel's Wolverine | 0.356 (miss 94%, cov 0.96) | 0.744 |
| p01 Red Dead Redemption 2 | 0.192 (miss 36%, cov 0.91) | 0.287 |
| p02 God of War Ragnarök | 0.134 (miss 21%, cov 1.00) | 0.215 |
| p03 Marvel's Spider-Man 2 | 0.181 (miss 30%, cov 0.83) | 0.303 |
| **mean** | **0.216** | **0.387** |

Deterministic (two runs byte-identical); ~0.05 s per case, far under the
8 s limit; outputs ~1.5 KB, far under the 65,536-byte cap. Edge cases
verified: hour-1 of 0 or 1, and a final-like case with `streams` and
`categories_hourly` present.
