"""gta6-twitch-ccu-forecast-01: forecast GTA VI's launch-day Twitch viewers.

Model: a shape model over past big launches (the case's comparables).
For each comparable launch, take its release-day hourly viewers and express
every hour as a log ratio to that launch's own hour-1 viewers:
    r_h = ln(viewers_h / viewers_1).
For the target case, hour h's forecast is hour1_print * exp(quantile of r_h),
where the quantiles come from the distribution of r_h across comparables.

Two filters make the distribution relevant to a rolling-midnight console
launch like GTA VI (and like the four practice launches):
  - late-peak only: keep comparables whose release-day peak falls at hour 12
    or later. Simultaneous global launches peak at hour 1 and fall all day;
    a rolling midnight unlock climbs through the day as time zones wake up.
    The five early-peak comparables (ELDEN RING, Cyberpunk 2077, Starfield,
    Borderlands 4, Elden Ring Nightreign) are dropped.
  - scale weighting: a comparable's weight is a Gaussian kernel on the log
    distance between its hour-1 viewers and the target's hour-1 print
    (sigma = 0.8 in log units). A launch's growth ratio depends on its scale:
    small hour-1 launches grow many times over the day, huge ones barely
    double. GTA VI's hour 1 will be enormous, so the big launches
    (Diablo IV, Hogwarts Legacy, The Last of Us Part II) carry the most
    weight. Without this the median ratio is dragged up by tiny launches
    that exploded 100x from a few hundred viewers.

Quantiles are the weighted 5th/25th/50th/75th/95th percentiles of the log
ratios at each hour (an honest spread: the 90% band covers about 90% of
comparable hours). Where a comparable lacks an hour it is skipped for that
hour; a comparable with no hour-1 point (e.g. the GTA VI category's own
pre-release history, whose day is its premiere) is skipped entirely.

Edge cases: hour-1 print below 1 counts as 1; a comparable hour of 0 is
skipped; if no comparable is usable for an hour, that hour falls back to
the house baseline's persistence forecast (spread widening as
0.15 * sqrt(h - 1) in log space).

Deterministic: no randomness, no dict-order dependence (all percentiles are
computed on sorted lists). Standard library only, no network.
"""

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so `import model`
# finds a model.py shipped beside this file (kept for parity with the starter).
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]
# Gaussian kernel width (log units) for scale weighting on hour-1 viewers.
BANDWIDTH = 0.8
# Baseline log spread per sqrt hour, used only as a fallback.
BASE_SIGMA = 0.15
# A comparable counts as a rolling-midnight launch when its release-day peak
# falls at this hour or later.
LATE_PEAK_HOUR = 12
# Minimum release-day hours a comparable must carry to be used.
MIN_DAY_HOURS = 20
# The 90% band (q05 to q95) is never narrower than this many log units.
# It only bites when the target's hour 1 sits far outside the comparable
# range and a handful of comparables happen to agree: a 5% band would be a
# false certainty, and the pinball loss punishes it hard.
MIN_LOG_WIDTH = 0.5


def _parse_time(text):
    """ISO 8601 UTC timestamp -> datetime (handles the trailing Z)."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def round2(x):
    """x rounded to 2 decimals, half up (as the starter rounds it)."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def day_series(comp):
    """A comparable's release-day hourly viewers as {hour 0..23: viewers}."""
    try:
        start = _parse_time(comp["day_start"])
    except (KeyError, ValueError, TypeError):
        return {}
    out = {}
    for point in comp.get("hourly") or []:
        try:
            viewers = point["viewers"]
            at = _parse_time(point["from"])
        except (KeyError, ValueError, TypeError):
            continue
        if not isinstance(viewers, (int, float)) or viewers <= 0:
            continue
        hour = (at - start).total_seconds() / 3600.0
        if 0 <= hour < 24 and hour == int(hour):
            out[int(hour)] = float(viewers)
    return out


def weighted_percentile(pairs, q):
    """The weighted q-th percentile of [(value, weight), ...]."""
    ordered = sorted(pairs)
    total = sum(w for _, w in ordered)
    if total <= 0:
        return ordered[len(ordered) // 2][0]
    acc = 0.0
    for value, weight in ordered:
        acc += weight
        if acc >= q * total:
            return value
    return ordered[-1][0]


def baseline_row(p1, h):
    """House baseline row for hour h (fallback only)."""
    return [max(1.0, p1 * math.exp(z * BASE_SIGMA * math.sqrt(h - 1))) for z in Z]


def forecast_case(case, name):
    if case.get("levels") != LEVELS:
        raise ValueError(f"{name} asks for levels {case.get('levels')}, not {LEVELS}")
    first = next((k for k in case.get("known") or [] if k.get("hour") == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1.0, float(first["viewers"]))
    log_p1 = math.log(p1)

    # Collect the usable comparables: rolling launches with a real hour 1.
    weighted = []
    for comp in case.get("comparables") or []:
        series = day_series(comp)
        if 0 not in series or len(series) < MIN_DAY_HOURS:
            continue
        peak_hour = max(series, key=lambda h: series[h])
        if peak_hour < LATE_PEAK_HOUR:
            continue
        weight = math.exp(-0.5 * ((math.log(series[0]) - log_p1) / BANDWIDTH) ** 2)
        weighted.append((series, weight))

    rows = []
    for row in case["forecast"]:
        h = row["hour"]
        pairs = []
        for series, weight in weighted:
            if h - 1 in series:
                pairs.append((math.log(series[h - 1] / series[0]), weight))
        if not pairs:
            quantiles = baseline_row(p1, h)
        else:
            log_q = [weighted_percentile(pairs, q) for q in LEVELS]
            log_med = log_q[2]
            width = log_q[4] - log_q[0]
            if width < MIN_LOG_WIDTH:
                # Widen symmetrically around the median in log space so the
                # 90% band is never a false certainty. A zero width (all
                # comparables agreeing exactly) gets the baseline shape.
                if width <= 1e-9:
                    log_q = [log_med + z * BASE_SIGMA * math.sqrt(h - 1) for z in Z]
                else:
                    factor = MIN_LOG_WIDTH / width
                    log_q = [log_med + (x - log_med) * factor for x in log_q]
            quantiles = [max(1.0, p1 * math.exp(x)) for x in log_q]
            for i in range(1, 5):
                quantiles[i] = max(quantiles[i], quantiles[i - 1])
        rows.append({"hour": h, "q": [round2(q) for q in quantiles]})
    return {"hours": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        text = json.dumps(forecast, separators=(",", ":")) + "\n"
        if len(text.encode("utf-8")) > 65536:
            raise ValueError(f"{path.name}: forecast over the 65,536-byte cap")
        (OUTPUT_DIR / f"{path.stem}.out").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
