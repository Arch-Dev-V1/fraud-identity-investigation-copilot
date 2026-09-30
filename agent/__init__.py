"""The agent module — the only thing the UI talks to.

It is the single point that calls Claude, runs tools, and writes to the
database. Note what is not exported: there is no way to set an analyst
decision from the agent side, and no tool that could.
"""

from .demo import is_demo_mode
from .tools import resolve_transport
from .db import (
    get_case,
    get_memo,
    latest_memo,
    list_cases,
    record_analyst_decision,
)
from .loop import MODEL, build_opening_prompt, memo_to_markdown, run_investigation

__all__ = [
    "MODEL",
    "build_opening_prompt",
    "get_case",
    "is_demo_mode",
    "get_memo",
    "latest_memo",
    "list_cases",
    "memo_to_markdown",
    "resolve_transport",
    "record_analyst_decision",
    "run_investigation",
]
