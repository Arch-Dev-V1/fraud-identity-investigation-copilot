"""Load a .env file into the environment.

The Anthropic SDK resolves credentials from os.environ (or an `ant auth login`
profile); it does not read .env. This project shipped a .env.example from the
first commit, which implied otherwise — so the file is loaded here rather than
leaving a key sitting in a file nothing consults.

Deliberately not a dependency: the format in use is KEY=VALUE, and a parser for
that is shorter than the import. What it handles: blank lines, # comments, an
optional `export ` prefix, and values wrapped in single or double quotes. What
it does NOT handle, and would need python-dotenv for: multi-line values,
${VAR} interpolation, and escape sequences inside quotes.

A real environment variable always wins over the file, so an exported key is
never silently shadowed by a stale .env.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

_ASSIGNMENT = re.compile(
    r"""^\s*(?:export\s+)?        # optional shell-style export
         ([A-Za-z_][A-Za-z0-9_]*) # name
         \s*=\s*                  # separator
         (.*)$                    # raw value
    """,
    re.VERBOSE,
)


def load_env(path: Path | None = None, override: bool = False) -> list[str]:
    """Copy assignments from ``path`` into ``os.environ``.

    Returns the names that were set, so a caller can report what it picked up
    without ever touching the values.
    """
    env_path = path or ENV_PATH
    if not env_path.exists():
        return []

    loaded: list[str] = []
    try:
        lines = env_path.read_text().splitlines()
    except OSError:
        return []

    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _ASSIGNMENT.match(line)
        if not match:
            continue
        name, raw = match.group(1), match.group(2).strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
            raw = raw[1:-1]
        if not raw:
            continue
        if name in os.environ and not override:
            continue   # the real environment wins
        os.environ[name] = raw
        loaded.append(name)
    return loaded
