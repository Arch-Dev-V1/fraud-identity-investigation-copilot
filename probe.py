"""Call the provider gateway directly and print the response.

Useful for reading an endpoint's exact payload without the agent in the way.

    python probe.py 1                       # every lookup for applicant 1
    python probe.py 1 --only ssn            # just one
    python probe.py 1 --compact             # one status line per call
"""

from __future__ import annotations

import argparse
import json
import os
import sys

try:
    import httpx2 as httpx
except ModuleNotFoundError:  # pragma: no cover
    print("httpx2 is required: pip install -r requirements.txt", file=sys.stderr)
    raise SystemExit(1)

BASE = os.environ.get("PROVIDER_API_URL", "http://127.0.0.1:8000").rstrip("/")

ENDPOINTS = {
    "ssn": "ssn-verification",
    "credit": "credit-trajectory",
    "au": "authorized-user-history",
    "shared": "shared-identifiers",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("applicant_id", type=int)
    parser.add_argument("--only", choices=sorted(ENDPOINTS), action="append",
                        help="limit to one or more lookups (repeatable)")
    parser.add_argument("--compact", action="store_true",
                        help="print status and size instead of the body")
    args = parser.parse_args(argv)

    try:
        health = httpx.get(f"{BASE}/health", timeout=5)
    except httpx.HTTPError as exc:
        print(f"Gateway unreachable at {BASE}: {exc}\n"
              f"Start it with: uvicorn provider_api.main:app --port 8000", file=sys.stderr)
        return 1
    print(f"# {BASE} · health {health.status_code} {health.json()}\n")

    for key in (args.only or sorted(ENDPOINTS)):
        path = f"/v1/applicants/{args.applicant_id}/{ENDPOINTS[key]}"
        response = httpx.get(f"{BASE}{path}", timeout=20)
        header = f"GET {path} → {response.status_code} ({len(response.content)} bytes)"
        print(header)
        if not args.compact:
            print("-" * len(header))
            try:
                print(json.dumps(response.json(), indent=2))
            except ValueError:
                print(response.text)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
