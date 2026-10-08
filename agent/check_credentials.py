"""Check whether the configured credentials actually work. Costs nothing.

    python -m agent.check_credentials

Uses the token-counting endpoint, which authenticates against the API but runs
no inference and is not billed. It answers the question the investigation error
cannot: is there no key, or is there a key the server refuses?
"""

from __future__ import annotations

import os
import re
import sys

import anthropic

from . import loop


def main() -> int:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")

    if not key and not token:
        print("No ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN resolved.")
        print("An `ant auth login` profile would also work; trying the API anyway.")
    elif key:
        # Shape only — never print the value.
        clean = bool(re.fullmatch(r"[A-Za-z0-9_-]+", key))
        print(f"Key found: {len(key)} chars, starts {key[:7]!r}, "
              f"no stray characters: {clean}")
        if not clean:
            print("  Something non-key-safe is in the value — usually a quote, a "
                  "space, or a newline picked up on paste.")

    headers = loop.client_headers()
    if headers:
        print(f"Workspace id set: {headers['anthropic-workspace-id'][:12]}…")

    client = anthropic.Anthropic(default_headers=headers) if headers else anthropic.Anthropic()
    try:
        result = client.messages.count_tokens(
            model=loop.MODEL,
            messages=[{"role": "user", "content": "ping"}],
        )
    except anthropic.AuthenticationError as exc:
        print("\nREJECTED — the server refused these credentials.")
        print(f"  {exc}")
        print("\nThe key is reaching the API, so the .env file or environment "
              "variable is fine. The key itself is revoked, rotated, or from a "
              "workspace that no longer exists. Get a current one from the "
              "Anthropic Console.")
        return 1
    except anthropic.PermissionDeniedError as exc:
        print(f"\nVALID, BUT NO ACCESS to {loop.MODEL}.\n  {exc}")
        return 1
    except anthropic.BadRequestError as exc:
        if "workspace" in str(exc).lower():
            print("\nVALID KEY, BUT NOT SCOPED TO A WORKSPACE.")
            print("  The key authenticates. It just does not say which workspace "
                  "to bill and run in.")
            print("\n  Either: create a key inside a workspace in the Console and "
                  "use that one,")
            print("  or:     set ANTHROPIC_WORKSPACE_ID in .env to the wrkspc_... "
                  "id from the Console URL.")
        else:
            print(f"\nBad request: {exc}")
        return 1
    except anthropic.APIStatusError as exc:
        print(f"\nAPI error {exc.status_code}: {exc}")
        return 1
    except Exception as exc:
        print(f"\n{type(exc).__name__}: {exc}")
        return 1

    print(f"\nOK — credentials are valid and {loop.MODEL} is reachable.")
    print(f"  (token count for a one-word prompt: {result.input_tokens}; "
          "this check runs no inference and is not billed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
