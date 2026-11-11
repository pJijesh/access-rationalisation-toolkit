"""Exceptions raised by access-rat."""

from __future__ import annotations


class ValidationError(Exception):
    """Raised when input CSV files are missing, malformed or inconsistent.

    All problems found are collected so that a data owner can fix them in one
    pass instead of discovering them one run at a time.
    """

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems[:3]) + (" ..." if len(self.problems) > 3 else ""))

    def format(self, limit: int = 25) -> str:
        shown = self.problems[:limit]
        lines = [f"Input validation failed with {len(self.problems)} problem(s):"]
        lines += [f"  - {p}" for p in shown]
        if len(self.problems) > limit:
            lines.append(f"  ... and {len(self.problems) - limit} more")
        return "\n".join(lines)
