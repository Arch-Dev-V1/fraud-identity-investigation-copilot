"""Verify prompt caching is actually working. Spends real API tokens.

Caching cannot be confirmed by reading the code — a single dynamic byte above
the breakpoint silently disables it. This sends the same first turn twice and
checks that the second request reads the prefix from cache.

    python cache_probe.py            # needs ANTHROPIC_API_KEY

Exits non-zero if the second request's cache_read_input_tokens is zero, so it
works as a regression check after any change to the system prompt or tool list.

Cost: two short requests at the configured model's rates, with max_tokens kept
low. It calls no project tools and writes nothing to the database.
"""

from __future__ import annotations

import os
import sys

import anthropic

from agent import db, loop, tools as agent_tools

APPLICANT_ID = 1
MAX_TOKENS = 64          # we only need the usage meters, not an answer
HEALTHY_READ_SHARE = 0.80  # published bar for an agent loop


def _meters(response) -> dict[str, int]:
    usage = response.usage
    return {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
    }


def main() -> int:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("No credentials. Set ANTHROPIC_API_KEY (or run `ant auth login`).",
              file=sys.stderr)
        return 2

    client = anthropic.Anthropic()
    case = db.get_case(APPLICANT_ID)
    # Direct transport: the probe should not depend on the gateway or MCP being up.
    tool_list = agent_tools.build_tool_list(agent_tools.TRANSPORT_DIRECT)
    messages = [{"role": "user", "content": loop.build_opening_prompt(case)}]

    print(f"model {loop.MODEL} · cache TTL {loop.CACHE_TTL} · "
          f"{len(tool_list)} tools · sending the same first turn twice\n")

    results = []
    for attempt in (1, 2):
        response = client.beta.messages.create(
            model=loop.MODEL,
            max_tokens=MAX_TOKENS,
            system=loop._cached_system(),
            cache_control={"type": "ephemeral"},
            thinking={"type": "adaptive", "display": "summarized"},
            tools=tool_list,
            messages=messages,
            betas=[loop.FALLBACK_BETA],
            fallbacks="default",
        )
        meters = _meters(response)
        results.append(meters)
        print(f"request {attempt}:")
        for key, value in meters.items():
            print(f"    {key:<32} {value:>7,}")
        print()

    second = results[1]
    cached = second["cache_read_input_tokens"]
    billed_input = cached + second["input_tokens"]
    share = cached / billed_input if billed_input else 0.0

    print(f"second request read {cached:,} of {billed_input:,} input tokens from cache "
          f"({share:.0%}).")
    if cached == 0:
        print("\nFAIL: nothing was read from cache. Something above the breakpoint "
              "varies between requests — check the system prompt and the tool list "
              "for anything dynamic, and that the tool order is stable.",
              file=sys.stderr)
        return 1
    if share < HEALTHY_READ_SHARE:
        print(f"\nWARNING: below the {HEALTHY_READ_SHARE:.0%} bar published for a "
              "healthy agent loop. Caching is working but something is still "
              "being re-billed.")
        return 0
    print("\nOK: the stable prefix is being served from cache.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
