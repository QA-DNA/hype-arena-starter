"""The lexicon: every subject, its aliases and attributes, and the events."""
from __future__ import annotations

import json
import re
from pathlib import Path


def norm(s: str) -> str:
    """Case- and space-insensitive form of a name, as the referee matches names."""
    return re.sub(r"\s+", " ", s.strip().lower())


class Lexicon:
    def __init__(self, data: dict):
        self.data = data
        self.subjects: dict[str, dict] = {s["name"]: s for s in data["subjects"]}
        self.events: list[str] = list(data.get("events", []))
        self._by_name: dict[str, str] = {}
        for s in data["subjects"]:
            for n in [s["name"], *s.get("aliases", [])]:
                self._by_name.setdefault(norm(n), s["name"])

    @classmethod
    def load(cls, path: str | Path) -> "Lexicon":
        with open(path, encoding="utf-8-sig") as f:
            return cls(json.load(f))

    def canonical(self, name: str) -> str | None:
        """The canonical subject a name or alias names, or None."""
        return self._by_name.get(norm(name))

    def names(self, subject: str) -> list[str]:
        s = self.subjects[subject]
        return [s["name"], *s.get("aliases", [])]

    def all_names(self) -> dict[str, str]:
        """Every spelling (normalized) -> canonical subject."""
        return dict(self._by_name)

    def attributes(self, subject: str) -> list[str]:
        return list(self.subjects.get(subject, {}).get("attributes", []))

    def has(self, subject: str, attribute: str) -> bool:
        return attribute in self.subjects.get(subject, {}).get("attributes", [])

    def is_event(self, subject: str) -> bool:
        return subject in self.events
