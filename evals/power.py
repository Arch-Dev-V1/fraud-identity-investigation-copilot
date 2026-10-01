"""How much resolution does this eval actually have, and how many reps buy more.

The `1/sqrt(n·reps)` rule of thumb is a conservative bound: it assumes a binary
metric at maximum variance and independent samples. This eval's headline is
continuous (0 / 0.5 / 1.0) and the comparisons that matter are paired — the
same cases under two configs — and both of those beat the bound. By how much is
a property of the measured data, not something to guess.

    python -m evals.power                       # read the baseline run
    python -m evals.power --target 0.05         # reps needed to resolve 5 points

Run it after a real pass. Demo-mode rows are deterministic, so their
rep-to-rep variance is zero and they cannot inform rep sizing — the tool says
so rather than returning a flattering number.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOW_DIR = ROOT / ".claude" / "hillclimb" / "investigation"
Z = 1.96


def load(variant: str, metric: str) -> dict[str, list[float]]:
    path = FLOW_DIR / variant / "results.jsonl"
    if not path.exists():
        raise SystemExit(f"No results at {path}. Run `python -m evals.run` first.")
    by_case: dict[str, list[float]] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("status") != "ok":
            continue
        value = (row.get("grade") or {}).get(metric)
        if value is None:
            continue
        by_case.setdefault(row["prompt_id"], []).append(float(value))
    if not by_case:
        raise SystemExit(f"No graded rows for metric {metric!r}.")
    return by_case


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", default="baseline")
    parser.add_argument("--metric", default="confidence")
    parser.add_argument("--target", type=float, default=0.05,
                        help="smallest difference you would act on (0.05 = 5 points)")
    args = parser.parse_args(argv)

    by_case = load(args.variant, args.metric)
    n = len(by_case)
    reps = min(len(v) for v in by_case.values())
    means = [statistics.fmean(v) for v in by_case.values()]

    # Between-case spread drives the CI on a single config's mean.
    sd_between = statistics.stdev(means) if n > 1 else 0.0
    # Within-case (rep-to-rep) spread is what a paired comparison has to beat.
    within = [statistics.variance(v) for v in by_case.values() if len(v) > 1]
    var_within = statistics.fmean(within) if within else 0.0
    sd_within = math.sqrt(var_within)

    print(f"{args.variant} · metric {args.metric} · {n} cases × {reps} reps "
          f"({sum(len(v) for v in by_case.values())} graded rows)")
    print(f"  mean                      {statistics.fmean(means):.3f}")
    print(f"  SD across cases           {sd_between:.3f}")
    print(f"  SD across reps (within)   {sd_within:.3f}")
    print()

    bound = 1.0 / math.sqrt(n * reps)
    print(f"  conservative bound  1/sqrt(n·reps)        ±{100*bound:.1f} points")
    if n > 1:
        unpaired = Z * sd_between / math.sqrt(n)
        print(f"  measured, this config's mean             ±{100*unpaired:.1f} points")

    if not within:
        print()
        print("  Rep-to-rep variance is unmeasurable here: only one rep per case.")
        print("  Re-run with --reps 2 or more to size a paired comparison.")
        return 0
    if var_within == 0:
        print()
        print("  Rep-to-rep variance is exactly zero — these rows are deterministic")
        print("  (demo mode). That cannot inform rep sizing for a live comparison;")
        print("  run a real pass first.")
        return 0

    # Paired comparison, limited by rep noise: sd of the per-case difference is
    # at least sqrt(2·var_within/reps).
    def paired_half_width(r: int) -> float:
        return Z * math.sqrt(2 * var_within / r) / math.sqrt(n)

    print(f"  paired comparison at {reps} reps              ±{100*paired_half_width(reps):.1f} points")
    print()
    print(f"  To resolve a {100*args.target:.0f}-point difference, paired, at {n} cases:")
    needed = None
    for r in range(1, 41):
        if paired_half_width(r) <= args.target:
            needed = r
            break
    if needed:
        print(f"    reps needed: {needed}  →  {n*needed} runs per configuration")
    else:
        print("    more than 40 reps — add cases instead, or accept a coarser call")
    print()
    print("  The paired figure is a floor: it counts rep noise only. A real")
    print("  comparison also carries systematic per-case shifts between configs,")
    print("  which only a second variant can measure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
