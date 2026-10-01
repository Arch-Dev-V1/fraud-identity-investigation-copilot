"""Estimate what a full eval pass will cost, before spending anything.

This is an ESTIMATE FROM CODE, not from measured usage: it profiles the request
payloads offline through demo mode and converts characters to tokens with a
ratio. The first real run replaces it with measured numbers from
response.usage, and those should be trusted over this.

    python -m evals.estimate_cost --reps 3
"""

from __future__ import annotations

import argparse
import json

from agent import loop
from agent.demo import _DemoMessages
from evals import cases

# Rates per million tokens, from the published pricing page (fetched 2026-10-01).
# Cache writes are 1.25x input; cache reads are the per-model rate below.
RATES = {
    "claude-opus-5":   {"in": 5.00, "out": 25.00, "cache_read": 0.50},
    "claude-opus-5-5": {"in": 4.00, "out": 20.00, "cache_read": 0.20},
    "claude-sonnet-5-5": {"in": 2.00, "out": 10.00, "cache_read": 0.20},
}
WEB_SEARCH_PER_SEARCH = 10.0 / 1000      # $10 per 1,000 searches

# Claude 4.7+ models use a tokenizer that produces roughly 30% more tokens for
# the same text, so the usual ~4 chars/token does not hold. ~3 is closer.
CHARS_PER_TOKEN = 3.0
# Output is the band this estimate is least sure about: adaptive thinking is
# billed as output and its volume is not knowable without running.
OUTPUT_TOKENS_LOW, OUTPUT_TOKENS_HIGH = 1_500, 6_000


def profile_one_investigation() -> dict:
    """Measure the request payloads for one case, offline and free.

    Sizes are computed AT CALL TIME, not from stored kwargs: the loop mutates a
    single messages list in place, so holding a reference and measuring later
    reports the final turn's size for every turn — which overstated this
    estimate by nearly 2x before it was caught.
    """
    turns: list[dict[str, int]] = []
    original = _DemoMessages.create

    def spy(self, **kw):
        turns.append({
            "system": len(json.dumps(kw.get("system") or "")),
            "tools": len(json.dumps(kw.get("tools") or [], default=str)),
            "messages": len(json.dumps(kw.get("messages") or [], default=str)),
        })
        return original(self, **kw)

    _DemoMessages.create = spy
    try:
        list(loop.run_investigation(1, demo_mode=True, transport="direct"))
    finally:
        _DemoMessages.create = original

    prefix = turns[0]["system"] + turns[0]["tools"]
    total = sum(t["system"] + t["tools"] + t["messages"] for t in turns)
    return {"turns": len(turns), "prefix_chars": prefix, "total_chars": total,
            "per_turn": turns}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=loop.MODEL)
    parser.add_argument("--judge-model", default="claude-sonnet-5-5")
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--searches-per-case", type=float, default=1.0)
    args = parser.parse_args(argv)

    rates = RATES.get(args.model)
    if rates is None:
        print(f"No rate on file for {args.model}. Add it to RATES from the pricing page.")
        return 1
    judge_rates = RATES[args.judge_model]

    profile = profile_one_investigation()
    runs = len(cases.case_ids()) * args.reps
    in_tok = profile["total_chars"] / CHARS_PER_TOKEN
    prefix_tok = profile["prefix_chars"] / CHARS_PER_TOKEN
    # The prefix is written once and read on every later turn.
    cached_reads = prefix_tok * (profile["turns"] - 1)
    uncached = max(in_tok - cached_reads, 0)

    def dollars(out_tok: float) -> float:
        return (uncached * rates["in"]
                + prefix_tok * rates["in"] * 1.25
                + cached_reads * rates["cache_read"]
                + out_tok * rates["out"]) / 1_000_000

    low, high = dollars(OUTPUT_TOKENS_LOW), dollars(OUTPUT_TOKENS_HIGH)
    judge = (1_200 * judge_rates["in"] + 250 * judge_rates["out"]) / 1_000_000
    search = args.searches_per_case * WEB_SEARCH_PER_SEARCH

    print(f"ESTIMATE FROM CODE — not measured. Replace with response.usage after the first run.\n")
    print(f"  model {args.model} · judge {args.judge_model} · "
          f"{len(cases.case_ids())} cases x {args.reps} reps = {runs} runs")
    print(f"  one investigation: {profile['turns']} turns, "
          f"{profile['total_chars']:,} chars of request payload "
          f"(~{in_tok:,.0f} input tokens at {CHARS_PER_TOKEN} chars/token)")
    print(f"  of which the cached prefix accounts for ~{cached_reads:,.0f} read tokens\n")
    print(f"  per case   agent ${low:.3f}-${high:.3f}  + judge ${judge:.3f}"
          f"  + search ${search:.3f}")
    per_low, per_high = low + judge + search, high + judge + search
    print(f"             total ${per_low:.3f}-${per_high:.3f}")
    print(f"  FULL PASS  {runs} runs x ${per_low:.3f}-${per_high:.3f} = "
          f"${runs*per_low:.2f}-${runs*per_high:.2f}\n")
    print("  The output band is the loose part: adaptive thinking bills as output and")
    print("  its volume is not knowable without running. Search assumes "
          f"{args.searches_per_case} search(es) per case at $10/1,000.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
